"""CBE (Commercial Bank of Ethiopia) payment verification service.

Translated from src/services/verifyCBE.ts
"""

import io
import re
import ssl
from datetime import datetime

from pypdf import PdfReader

from tx_verify.models import TransactionResult
from tx_verify.utils.http_client import get_async_client
from tx_verify.utils.logger import logger


def _title_case(s: str) -> str:
    return s.title()


def _make_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that does not verify certificates (mirrors rejectUnauthorized: false)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def verify_cbe(
    reference: str, account_suffix: str = "", *, proxies: str | dict[str, str] | None = None
) -> TransactionResult:
    """Verify a CBE transaction by fetching and parsing its PDF receipt.

    First attempts a direct HTTPS fetch; on failure would fall back to
    a headless browser (not implemented in Python – returns error).
    """
    full_id = f"{reference}{account_suffix}"
    url = f"https://apps.cbe.com.et:100/?id={full_id}"

    try:
        logger.info("🔎 Attempting direct fetch: %s", url)
        async with get_async_client(
            verify=_make_ssl_context(), timeout=30.0, proxies=proxies
        ) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/pdf",
                },
            )
            response.raise_for_status()

        logger.info("✅ Direct fetch success, parsing PDF")
        return _parse_cbe_receipt(response.content)

    except Exception as direct_err:
        logger.warning("⚠️ Direct fetch failed: %s", str(direct_err))
        # The TS version falls back to Puppeteer here.
        # We do not bundle a headless browser; return the error.
        return TransactionResult(
            success=False,
            provider="cbe",
            error=f"Direct fetch failed: {direct_err}",
        )


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract and normalise text from a CBE PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw_text = ""
    for page in reader.pages:
        raw_text += page.extract_text() or ""
    # Normalise horizontal whitespace but preserve line breaks for structure.
    return re.sub(r"[^\S\n]+", " ", raw_text).strip()


def _extract_value(lines: list[str], label: str) -> str | None:
    """Return the value paired with *label* in a two-column CBE section.

    CBE PDFs emit all labels first, then all values.  We count how many
    colon-ending labels appear before *label* and use that as the index
    into the list of non-label lines.
    """
    label_low = label.lower()
    labels_before = 0
    for line in lines:
        if line.lower().rstrip(":") == label_low:
            break
        if line.endswith(":"):
            labels_before += 1
    else:
        return None

    values = [line for line in lines if not line.endswith(":")]
    if labels_before < len(values):
        val = values[labels_before]
        return val if val != "_" else None
    return None


def _extract_meta(text: str) -> dict[str, object]:
    """Extract optional CBE metadata (branch, region, tin)."""
    meta: dict[str, object] = {}

    bank_match = re.search(
        r"Company Address & Other Information\s*\n(.*?)\n\s*Customer Information",
        text,
        re.S | re.I,
    )
    if bank_match:
        bank_lines = [line.strip() for line in bank_match.group(1).split("\n") if line.strip()]
        tin = _extract_value(bank_lines, "Tin")
        if tin:
            meta["tin"] = tin

    customer_match = re.search(
        r"Customer Information\s*\n(.*?)\n\s*Payment / Transaction Information",
        text,
        re.S | re.I,
    )
    if customer_match:
        customer_lines = [
            line.strip() for line in customer_match.group(1).split("\n") if line.strip()
        ]
        branch = _extract_value(customer_lines, "Branch")
        if not branch:
            # CBE PDFs occasionally drop placeholder values ("_"), shifting
            # later values up.  The branch name is almost always the final
            # non-label line in the customer section.
            values = [line for line in customer_lines if not line.endswith(":")]
            if values:
                branch = values[-1]
        if branch:
            meta["branch"] = branch
        region = _extract_value(customer_lines, "Region")
        if region:
            meta["region"] = region

    return meta


def _parse_cbe_receipt(pdf_bytes: bytes) -> TransactionResult:
    """Extract transaction fields from a CBE PDF receipt."""
    try:
        text = _extract_text(pdf_bytes)

        payer_match = re.search(r"Payer\s*:?\s*(.*?)\s+Account", text, re.I)
        payer_name = payer_match.group(1).strip() if payer_match else None

        receiver_match = re.search(r"Receiver\s*:?\s*(.*?)\s+Account", text, re.I)
        receiver_name = receiver_match.group(1).strip() if receiver_match else None

        account_matches = re.findall(r"Account\s*:?\s*([A-Z0-9]?\*{4}\d{4})", text, re.I)
        payer_account = account_matches[0] if len(account_matches) > 0 else None
        receiver_account = account_matches[1] if len(account_matches) > 1 else None

        reason_match = re.search(
            r"Reason\s*/\s*Type of service\s*:?\s*(.*?)\s+Transferred Amount",
            text,
            re.I,
        )
        reason = reason_match.group(1).strip() if reason_match else None

        amount_match = re.search(r"Transferred Amount\s*:?\s*([\d,]+\.\d{2})\s*ETB", text, re.I)
        amount_text = amount_match.group(1) if amount_match else None

        service_charge_match = re.search(
            r"Commission or Service Charge\s*:?\s*([\d,]+\.\d{2})\s*ETB", text, re.I
        )
        service_charge_text = service_charge_match.group(1) if service_charge_match else None

        vat_match = re.search(r"VAT on Commission\s*:?\s*([\d,]+\.\d{2})\s*ETB", text, re.I)
        vat_text = vat_match.group(1) if vat_match else None

        total_match = re.search(
            r"Total amount debited from customers account\s*:?\s*([\d,]+\.\d{2})\s*ETB",
            text,
            re.I,
        )
        total_text = total_match.group(1) if total_match else None

        words_match = re.search(r"Amount in Word\s*:?\s*ETB\s*(.*?)\s*cents", text, re.I)
        amount_in_words = words_match.group(1).strip() if words_match else None

        ref_match = re.search(
            r"Reference No\.?\s*\(VAT Invoice No\)\s*:?\s*([A-Z0-9]+)",
            text,
            re.I,
        )
        reference_val = ref_match.group(1).strip() if ref_match else None

        date_match = re.search(r"Payment Date & Time\s*:?\s*([\d/,: ]+[APM]{2})", text, re.I)
        date_raw = date_match.group(1).strip() if date_match else None

        amount = float(amount_text.replace(",", "")) if amount_text else None
        service_charge = (
            float(service_charge_text.replace(",", "")) if service_charge_text else None
        )
        vat = float(vat_text.replace(",", "")) if vat_text else None
        total_amount = float(total_text.replace(",", "")) if total_text else None
        date = _parse_date(date_raw) if date_raw else None

        if payer_name:
            payer_name = _title_case(payer_name)
        if receiver_name:
            receiver_name = _title_case(receiver_name)

        # Infer payment channel from narrative when possible.
        payment_channel = None
        if reason:
            if "mobile" in reason.lower():
                payment_channel = "Mobile"
            elif "internet" in reason.lower() or "online" in reason.lower():
                payment_channel = "Internet Banking"
            elif "branch" in reason.lower():
                payment_channel = "Branch"

        meta = _extract_meta(text)

        if (
            payer_name
            and payer_account
            and receiver_name
            and receiver_account
            and amount
            and date
            and reference_val
        ):
            return TransactionResult(
                success=True,
                provider="cbe",
                payer_name=payer_name,
                payer_account=payer_account,
                receiver_name=receiver_name,
                receiver_account=receiver_account,
                amount=amount,
                transaction_date=date,
                transaction_reference=reference_val,
                narrative=reason,
                currency="ETB",
                service_charge=service_charge,
                vat=vat,
                total_amount=total_amount,
                amount_in_words=f"ETB {amount_in_words} cents" if amount_in_words else None,
                payment_channel=payment_channel,
                meta=meta,
            )
        else:
            return TransactionResult(
                success=False,
                provider="cbe",
                error="Could not extract all required fields from PDF.",
            )

    except Exception as e:
        logger.error("❌ PDF parsing failed: %s", str(e))
        return TransactionResult(
            success=False,
            provider="cbe",
            error="Error parsing PDF data",
        )


def _parse_date(raw: str) -> datetime | None:
    """Best-effort parse of the date string from CBE receipts."""
    for fmt in (
        "%m/%d/%Y, %I:%M:%S %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%d/%m/%Y, %I:%M:%S %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None
