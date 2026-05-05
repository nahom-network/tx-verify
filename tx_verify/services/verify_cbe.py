"""CBE (Commercial Bank of Ethiopia) payment verification service.

Translated from src/services/verifyCBE.ts
"""

import io
import re
import ssl
from dataclasses import dataclass
from datetime import datetime

import httpx
from pypdf import PdfReader

from tx_verify.utils.logger import logger


@dataclass
class VerifyResult:
    """Standard verification result used across multiple services."""

    success: bool
    payer: str | None = None
    payer_account: str | None = None
    receiver: str | None = None
    receiver_account: str | None = None
    amount: float | None = None
    date: datetime | None = None
    reference: str | None = None
    reason: str | None = None
    error: str | None = None


def _title_case(s: str) -> str:
    return s.title()


def _make_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that does not verify certificates (mirrors rejectUnauthorized: false)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def verify_cbe(reference: str, account_suffix: str = "") -> VerifyResult:
    """Verify a CBE transaction by fetching and parsing its PDF receipt.

    First attempts a direct HTTPS fetch; on failure would fall back to
    a headless browser (not implemented in Python – returns error).
    """
    full_id = f"{reference}{account_suffix}"
    url = f"https://apps.cbe.com.et:100/?id={full_id}"

    try:
        logger.info("\U0001f50e Attempting direct fetch: %s", url)
        async with httpx.AsyncClient(verify=_make_ssl_context(), timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/pdf",
                },
            )
            response.raise_for_status()

        logger.info("\u2705 Direct fetch success, parsing PDF")
        return _parse_cbe_receipt(response.content)

    except Exception as direct_err:
        logger.warning("\u26a0\ufe0f Direct fetch failed: %s", str(direct_err))
        # The TS version falls back to Puppeteer here.
        # We do not bundle a headless browser; return the error.
        return VerifyResult(
            success=False,
            error=f"Direct fetch failed: {direct_err}",
        )


def _parse_cbe_receipt(pdf_bytes: bytes) -> VerifyResult:
    """Extract transaction fields from a CBE PDF receipt."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        raw_text = ""
        for page in reader.pages:
            raw_text += page.extract_text() or ""

        # Normalise whitespace
        raw_text = re.sub(r"\s+", " ", raw_text).strip()

        payer_match = re.search(r"Payer\s*:?\s*(.*?)\s+Account", raw_text, re.I)
        payer_name = payer_match.group(1).strip() if payer_match else None

        receiver_match = re.search(r"Receiver\s*:?\s*(.*?)\s+Account", raw_text, re.I)
        receiver_name = receiver_match.group(1).strip() if receiver_match else None

        account_matches = re.findall(r"Account\s*:?\s*([A-Z0-9]?\*{4}\d{4})", raw_text, re.I)
        payer_account = account_matches[0] if len(account_matches) > 0 else None
        receiver_account = account_matches[1] if len(account_matches) > 1 else None

        reason_match = re.search(
            r"Reason\s*/\s*Type of service\s*:?\s*(.*?)\s+Transferred Amount",
            raw_text,
            re.I,
        )
        reason = reason_match.group(1).strip() if reason_match else None

        amount_match = re.search(r"Transferred Amount\s*:?\s*([\d,]+\.\d{2})\s*ETB", raw_text, re.I)
        amount_text = amount_match.group(1) if amount_match else None

        ref_match = re.search(
            r"Reference No\.?\s*\(VAT Invoice No\)\s*:?\s*([A-Z0-9]+)",
            raw_text,
            re.I,
        )
        reference_val = ref_match.group(1).strip() if ref_match else None

        date_match = re.search(r"Payment Date & Time\s*:?\s*([\d/,: ]+[APM]{2})", raw_text, re.I)
        date_raw = date_match.group(1).strip() if date_match else None

        amount = float(amount_text.replace(",", "")) if amount_text else None
        date = _parse_date(date_raw) if date_raw else None

        if payer_name:
            payer_name = _title_case(payer_name)
        if receiver_name:
            receiver_name = _title_case(receiver_name)

        if (
            payer_name
            and payer_account
            and receiver_name
            and receiver_account
            and amount
            and date
            and reference_val
        ):
            return VerifyResult(
                success=True,
                payer=payer_name,
                payer_account=payer_account,
                receiver=receiver_name,
                receiver_account=receiver_account,
                amount=amount,
                date=date,
                reference=reference_val,
                reason=reason,
            )
        else:
            return VerifyResult(
                success=False,
                error="Could not extract all required fields from PDF.",
            )

    except Exception as e:
        logger.error("\u274c PDF parsing failed: %s", str(e))
        return VerifyResult(success=False, error="Error parsing PDF data")


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
