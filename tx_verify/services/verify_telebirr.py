"""Telebirr payment verification service.

Translated from src/services/verifyTelebirr.ts
"""

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup

from tx_verify.utils.logger import logger


@dataclass
class TelebirrReceipt:
    """Telebirr receipt data."""

    # Core fields — present on every receipt and needed for verification
    payer_name: str = ""
    payer_telebirr_no: str = ""
    credited_party_name: str = ""
    credited_party_account_no: str = ""
    transaction_status: str = ""
    receipt_no: str = ""
    payment_date: str = ""
    settled_amount: str = ""
    service_fee: str = ""
    service_fee_vat: str = ""
    total_paid_amount: str = ""
    bank_name: str = ""

    # Variable / receipt-type-specific fields that don't appear on every receipt
    meta: dict = field(default_factory=dict)


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

# Fields that belong on the TelebirrReceipt dataclass directly (core fields).
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
}


def _match_label(line: str) -> str | None:
    """Return the internal field name if `line` matches any known label."""
    line_lower = line.lower()
    for field_name, labels in _LABELS.items():
        for label_text in labels:
            if label_text.lower() in line_lower:
                return field_name
    return None


def _scrape_telebirr_receipt(html: str) -> TelebirrReceipt:
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
    # Build core attributes and meta dict
    # ------------------------------------------------------------------
    meta: dict[str, str] = {}
    for key, val in raw.items():
        if key in _VARIABLE_FIELDS and val:
            meta[key] = val

    return TelebirrReceipt(
        payer_name=raw.get("payer_name", ""),
        payer_telebirr_no=raw.get("payer_telebirr_no", ""),
        credited_party_name=raw.get("credited_party_name", ""),
        credited_party_account_no=raw.get("credited_party_account_no", ""),
        transaction_status=raw.get("transaction_status", ""),
        receipt_no=raw.get("receipt_no", ""),
        payment_date=raw.get("payment_date", ""),
        settled_amount=raw.get("settled_amount", ""),
        service_fee=raw.get("service_fee", ""),
        service_fee_vat=raw.get("service_fee_vat", ""),
        total_paid_amount=raw.get("total_paid_amount", ""),
        bank_name=bank_name,
        meta=meta,
    )


def _parse_telebirr_json(json_data: Any) -> TelebirrReceipt | None:
    """Parse receipt from a proxy JSON response."""
    try:
        if not json_data or not json_data.get("success") or not json_data.get("data"):
            logger.warning("Invalid JSON structure from proxy endpoint")
            return None

        d = json_data["data"]

        # Core fields
        receipt = TelebirrReceipt(
            payer_name=d.get("payerName", ""),
            payer_telebirr_no=d.get("payerTelebirrNo", ""),
            credited_party_name=d.get("creditedPartyName", ""),
            credited_party_account_no=d.get("creditedPartyAccountNo", ""),
            transaction_status=d.get("transactionStatus", ""),
            receipt_no=d.get("receiptNo", ""),
            payment_date=d.get("paymentDate", ""),
            settled_amount=d.get("settledAmount", ""),
            service_fee=d.get("serviceFee", ""),
            service_fee_vat=d.get("serviceFeeVAT", ""),
            total_paid_amount=d.get("totalPaidAmount", ""),
            bank_name=d.get("bankName", ""),
        )

        # Any leftover keys that aren't core go into meta
        core_json_keys = {
            "payerName", "payerTelebirrNo", "creditedPartyName",
            "creditedPartyAccountNo", "transactionStatus", "receiptNo",
            "paymentDate", "settledAmount", "serviceFee", "serviceFeeVAT",
            "totalPaidAmount", "bankName", "success", "error", "details",
        }
        for key, val in d.items():
            if key not in core_json_keys and val:
                receipt.meta[key] = str(val)

        return receipt
    except Exception as e:
        logger.error("Error parsing JSON from proxy endpoint: %s", e)
        return None


def _is_valid_receipt(receipt: TelebirrReceipt) -> bool:
    return bool(receipt.receipt_no and receipt.payer_name and receipt.transaction_status)


async def _fetch_from_primary_source(reference: str, base_url: str) -> TelebirrReceipt | None:
    url = f"{base_url}{reference}"
    try:
        logger.info("Attempting to fetch Telebirr receipt from primary source: %s", url)
        async with httpx.AsyncClient(timeout=30.0) as client:
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
        return None


async def _fetch_from_proxy_source(reference: str, proxy_url: str) -> TelebirrReceipt | None:
    proxy_key = os.getenv("TELEBIRR_PROXY_KEY", "")
    url = f"{proxy_url}{reference}"
    if proxy_key:
        url += f"&key={proxy_key}"

    try:
        logger.info("Attempting to fetch Telebirr receipt from proxy: %s", url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "VerifierAPI/1.0",
                },
            )
        logger.debug("Received proxy response with status: %s", response.status_code)

        # Try JSON first
        try:
            data = response.json()
        except Exception:
            logger.warning("Proxy response is not valid JSON, attempting to scrape as HTML")
            return _scrape_telebirr_receipt(response.text)

        if isinstance(data, dict) and data.get("success") is False and data.get("error"):
            raise TelebirrVerificationError(data["error"], data.get("details"))

        extracted = _parse_telebirr_json(data)
        if not extracted:
            logger.warning("Failed to parse JSON from proxy, attempting HTML scrape")
            return _scrape_telebirr_receipt(response.text)

        logger.info(
            "Successfully extracted Telebirr data from proxy for reference: %s",
            reference,
        )
        return extracted

    except TelebirrVerificationError:
        raise
    except httpx.ConnectError as e:
        raise TelebirrVerificationError(
            "The fallback proxy server is unreachable or timed out.",
            str(e),
        ) from e
    except httpx.TimeoutException as e:
        raise TelebirrVerificationError(
            "The fallback proxy server is unreachable or timed out.",
            str(e),
        ) from e
    except Exception as e:
        logger.error("Error fetching Telebirr receipt from proxy %s: %s", url, e)
        return None


async def verify_telebirr(reference: str) -> TelebirrReceipt | None:
    """Verify a Telebirr transaction using primary source then fallback proxies."""
    primary_url = "https://transactioninfo.ethiotelecom.et/receipt/"

    env_proxies = os.getenv("FALLBACK_PROXIES", "")
    fallback_proxies = [u.strip() for u in env_proxies.split(",") if u.strip()]
    skip_primary = os.getenv("SKIP_PRIMARY_VERIFICATION") == "true"

    if not skip_primary:
        logger.info("Attempting primary verification for: %s", reference)
        primary_result = await _fetch_from_primary_source(reference, primary_url)
        if primary_result and _is_valid_receipt(primary_result):
            return primary_result
        logger.warning("Primary verification failed. Moving to fallback proxy pool...")
    else:
        logger.info("Skipping primary verifier (SKIP_PRIMARY_VERIFICATION=true).")

    if not fallback_proxies and skip_primary:
        logger.error("CRITICAL: Primary check skipped, but no FALLBACK_PROXIES defined!")
        return None

    for proxy_url in fallback_proxies:
        try:
            logger.info("Attempting verification with proxy: %s", proxy_url)
            result = await _fetch_from_proxy_source(reference, proxy_url)
            if result and _is_valid_receipt(result):
                logger.info("Successfully verified using proxy: %s", proxy_url)
                return result
        except TelebirrVerificationError:
            raise
        except Exception:
            logger.warning("Proxy %s failed or timed out. Trying next...", proxy_url)

    logger.error(
        "All primary and proxy verification methods failed for reference: %s",
        reference,
    )
    return None
