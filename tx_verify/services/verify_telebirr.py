"""Telebirr payment verification service.

Translated from src/services/verifyTelebirr.ts
"""

from contextlib import suppress
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from tx_verify.models import TransactionResult
from tx_verify.utils.http_client import get_async_client
from tx_verify.utils.logger import logger


class TelebirrVerificationError(Exception):
    """Raised when Telebirr verification encounters a known error."""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.name = "TelebirrVerificationError"
        self.details = details


# ---------------------------------------------------------------------------
# Label map — internal field name → possible label text(s) seen in real HTML
# ---------------------------------------------------------------------------

_LABELS: dict[str, list[str]] = {
    "payer_name": ["የከፋይ ስም/Payer Name"],
    "payer_telebirr_no": ["የከፋይ ቴሌብር ቁ./Payer telebirr no."],
    "payer_account_type": ["የከፋይ አካውንት አይነት/Payer account type"],
    "payer_tin_no": ["የከፋይ ቲን ቁ./ Payer TIN No"],
    "payer_vat_reg_no": ["የከፋይ ተ.እ.ታ.ቁ./VAT Reg. No"],
    "payer_vat_reg_date": ["የከፋይ ተ.እ.ታ.ቁ. ምዝገባ ቀን/VAT Reg. Date"],
    "credited_party_name": ["የገንዘብ ተቀባይ ስም/Credited Party name"],
    "credited_party_account_no": ["የገንዘብ ተቀባይ ቴሌብር ቁ./Credited party account no"],
    "credited_party_tin_no": ["የገንዘብ ተቀባይ ቲን ቁ./Credited party TIN No"],
    "transaction_status": ["የክፍያው ሁኔታ/transaction status"],
    "address": ["አድራሻ/Address"],
    "vehicle_plate_number": ["የመኪናው ሰሌዳ ቁ./Vehicle plate number"],
    "account_service_number": ["የቢል ስልክ ቁ/አካውንት/Account/Service number"],
    "airtime_purchased_for": ["የአየር ሰአት የተገዛለት/Airtime purchased for"],
    "bank_account_number": ["የባንክ አካውንት ቁጥር/Bank account number"],
    # Invoice detail section
    "receipt_no": ["የክፍያ ቁጥር/Invoice No."],
    "payment_date": ["የክፍያ ቀን/Payment date"],
    "settled_amount": ["የተከፈለው መጠን/Settled Amount"],
    "vat_15_percent": ["15% ተ.እ.ታ/VAT"],
    "stamp_duty": ["የማህተም ክፍያ/Stamp Duty"],
    "discount_amount": ["ቅናሽ/Discount Amount"],
    "service_fee": ["የአገልግሎት ክፍያ/Service fee", "የአገልግሎት ክፍያ/service fee"],
    "service_fee_vat": ["የአገልግሎት ክፍያ ተ.እ.ታ/Service fee VAT"],
    "total_paid_amount": ["ጠቅላላ የተከፈለ/Total Paid Amount"],
    # Bottom section
    "total_amount_in_word": ["የገንዘቡ ልክ በፊደል/Total Amount in word"],
    "payment_mode": ["የክፍያ ዘዴ/Payment Mode"],
    "payment_reason": ["የክፍያ ምክንያት/Payment Reason"],
    "payment_channel": ["የክፍያ መንገድ/Payment channel"],
    "customer_note": ["የደንበኛ መልዕክት/Customer Note"],
}

# Fields that belong on the TransactionResult directly (core fields).
_CORE_FIELDS: set[str] = {
    "payer_name",
    "payer_telebirr_no",
    "credited_party_name",
    "credited_party_account_no",
    "transaction_status",
    "receipt_no",
    "payment_date",
    "settled_amount",
    "service_fee",
    "service_fee_vat",
    "total_paid_amount",
    "bank_name",
}

# Fields present on *some* receipts but not all — these go into meta.
_VARIABLE_FIELDS: set[str] = {
    "credited_party_tin_no",
    "address",
    "vehicle_plate_number",
    "account_service_number",
    "airtime_purchased_for",
    "bank_account_number",
    "vat_15_percent",
    "stamp_duty",
    "discount_amount",
    "total_amount_in_word",
    "payment_mode",
    "payment_reason",
    "payment_channel",
    "customer_note",
    "payer_account_type",
    "payer_tin_no",
    "payer_vat_reg_no",
    "payer_vat_reg_date",
}


def _match_label(line: str) -> str | None:
    """Return the internal field name if `line` matches any known label."""
    line_lower = line.lower()
    for field_name, labels in _LABELS.items():
        for label_text in labels:
            if label_text.lower() in line_lower:
                return field_name
    return None


def _parse_amount(value: str) -> float | None:
    """Parse a numeric amount string like '1,000.00', '100 ETB' or '100 Birr'."""
    cleaned = value.replace(",", "").replace("ETB", "").replace("Birr", "").strip()
    with suppress(ValueError):
        return float(cleaned)
    return None


def _parse_date(value: str) -> datetime | None:
    """Best-effort parse of Telebirr payment date strings."""
    value = value.strip()
    formats = (
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in formats:
        with suppress(ValueError):
            return datetime.strptime(value, fmt)
    return None


def _scrape_telebirr_receipt(html: str) -> TransactionResult:
    """Scrape Telebirr receipt data from HTML using a flat line-scanning approach.

    The Ethio Telecom receipt HTML contains nested <table> structures with
    inconsistent nesting (some rows have their sibling <td> inside the same
    <tr>, others have broken markup).  Rather than relying on the DOM tree,
    we flatten the text and scan for label → value pairs in order.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    raw: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Pass 1 — extract label → value pairs
    # ------------------------------------------------------------------
    i = 0
    while i < len(lines):
        field = _match_label(lines[i])
        if field:
            # If the next line is also a label, the current label's value is empty.
            if i + 1 < len(lines) and _match_label(lines[i + 1]):
                raw[field] = ""
                i += 1
                continue
            # Otherwise the next line is the value.
            if i + 1 < len(lines):
                raw[field] = lines[i + 1]
                i += 2
                continue
            raw[field] = ""
            i += 1
            continue
        i += 1

    # ------------------------------------------------------------------
    # Pass 2 — fix the invoice-detail section
    #
    # The receipt has a 3-column header row:
    #   Invoice No. | Payment date | Settled Amount
    # followed immediately by the three values on the next three lines.
    # ------------------------------------------------------------------
    for idx, line in enumerate(lines):
        if "የክፍያ ዝርዝር/ Invoice details" in line or "የክፍያ ዝርዝር/Invoice details" in line:
            val_start = idx + 4  # skip "Invoice details" + 3 header labels
            if val_start + 2 < len(lines):
                raw["receipt_no"] = lines[val_start]
                raw["payment_date"] = lines[val_start + 1]
                raw["settled_amount"] = lines[val_start + 2]
            break

    # ------------------------------------------------------------------
    # Pass 3 — bank-transfer detection
    # ------------------------------------------------------------------
    bank_name = ""
    if raw.get("bank_account_number"):
        # When a bank account number is present the credited party *is* the bank.
        bank_name = raw.get("credited_party_name", "")

    # ------------------------------------------------------------------
    # Build meta dict for optional/variable fields
    # ------------------------------------------------------------------
    meta: dict[str, str] = {}
    for key, val in raw.items():
        if key in _VARIABLE_FIELDS and val:
            meta[key] = val
    if bank_name:
        meta["bank_name"] = bank_name

    # ------------------------------------------------------------------
    # Build TransactionResult
    # ------------------------------------------------------------------
    return TransactionResult(
        success=bool(
            raw.get("receipt_no") and raw.get("payer_name") and raw.get("transaction_status")
        ),
        provider="telebirr",
        payer_name=raw.get("payer_name") or None,
        payer_account=raw.get("payer_telebirr_no") or None,
        receiver_name=raw.get("credited_party_name") or None,
        receiver_account=raw.get("credited_party_account_no") or None,
        transaction_status=raw.get("transaction_status") or None,
        receipt_number=raw.get("receipt_no") or None,
        transaction_date=_parse_date(raw["payment_date"]) if raw.get("payment_date") else None,
        amount=_parse_amount(raw["settled_amount"]) if raw.get("settled_amount") else None,
        service_charge=_parse_amount(raw["service_fee"]) if raw.get("service_fee") else None,
        vat=_parse_amount(raw["service_fee_vat"]) if raw.get("service_fee_vat") else None,
        total_amount=_parse_amount(raw["total_paid_amount"])
        if raw.get("total_paid_amount")
        else None,
        meta=meta,
        error=None,
    )


def _parse_telebirr_json(json_data: Any) -> TransactionResult:
    """Parse receipt from a proxy JSON response."""
    try:
        if not json_data or not json_data.get("success") or not json_data.get("data"):
            logger.warning("Invalid JSON structure from proxy endpoint")
            return TransactionResult(
                success=False,
                provider="telebirr",
                error="Invalid JSON structure from proxy endpoint",
            )

        d = json_data["data"]

        meta: dict[str, Any] = {}
        core_json_keys = {
            "payerName",
            "payerTelebirrNo",
            "creditedPartyName",
            "creditedPartyAccountNo",
            "transactionStatus",
            "receiptNo",
            "paymentDate",
            "settledAmount",
            "serviceFee",
            "serviceFeeVAT",
            "totalPaidAmount",
            "bankName",
            "success",
            "error",
            "details",
        }
        for key, val in d.items():
            if key not in core_json_keys and val:
                meta[key] = str(val)

        if d.get("bankName"):
            meta["bank_name"] = str(d["bankName"])

        return TransactionResult(
            success=True,
            provider="telebirr",
            payer_name=d.get("payerName") or None,
            payer_account=d.get("payerTelebirrNo") or None,
            receiver_name=d.get("creditedPartyName") or None,
            receiver_account=d.get("creditedPartyAccountNo") or None,
            transaction_status=d.get("transactionStatus") or None,
            receipt_number=d.get("receiptNo") or None,
            transaction_date=_parse_date(d["paymentDate"]) if d.get("paymentDate") else None,
            amount=_parse_amount(d["settledAmount"]) if d.get("settledAmount") else None,
            service_charge=_parse_amount(d["serviceFee"]) if d.get("serviceFee") else None,
            vat=_parse_amount(d["serviceFeeVAT"]) if d.get("serviceFeeVAT") else None,
            total_amount=_parse_amount(d["totalPaidAmount"]) if d.get("totalPaidAmount") else None,
            meta=meta,
        )
    except Exception as e:
        logger.error("Error parsing JSON from proxy endpoint: %s", e)
        return TransactionResult(
            success=False,
            provider="telebirr",
            error=f"Error parsing JSON from proxy endpoint: {e}",
        )


async def _fetch_from_primary_source(
    reference: str, base_url: str, *, proxies: str | dict[str, str] | None = None
) -> TransactionResult:
    url = f"{base_url}{reference}"
    try:
        logger.info("Attempting to fetch Telebirr receipt from primary source: %s", url)
        async with get_async_client(timeout=30.0, proxies=proxies) as client:
            response = await client.get(url)
        logger.debug("Received response with status: %s", response.status_code)

        extracted = _scrape_telebirr_receipt(response.text)
        logger.info(
            "Successfully extracted Telebirr data for reference: %s",
            reference,
        )
        return extracted
    except Exception as e:
        logger.error("Error fetching Telebirr receipt from primary source %s: %s", url, e)
        return TransactionResult(
            success=False,
            provider="telebirr",
            error=f"Error fetching Telebirr receipt: {e}",
        )


async def verify_telebirr(
    reference: str, *, proxies: str | dict[str, str] | None = None
) -> TransactionResult:
    """Verify a Telebirr transaction.

    Args:
        reference: Telebirr transaction reference.
        proxies: Optional proxy URL or per-scheme mapping for HTTP requests.
            Example: ``"http://proxy.example.com:8080"`` or
            ``{"http://": "socks5://localhost:1080"}``.
    """
    primary_url = "https://transactioninfo.ethiotelecom.et/receipt/"

    primary_result = await _fetch_from_primary_source(reference, primary_url, proxies=proxies)
    if primary_result.success:
        return primary_result
    logger.error(
        "Primary verification failed for reference: %s",
        reference,
    )
    return TransactionResult(
        success=False,
        provider="telebirr",
        error="Receipt not found or could not be processed.",
    )
