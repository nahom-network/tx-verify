"""Dashen Bank payment verification service.

Translated from src/services/verifyDashen.ts
"""

import asyncio
import io
import re
import ssl
from dataclasses import dataclass
from datetime import datetime

import httpx
from pypdf import PdfReader

from tx_verify.utils.logger import logger


@dataclass
class DashenVerifyResult:
    """Dashen Bank verification result."""

    success: bool
    sender_name: str | None = None
    sender_account_number: str | None = None
    transaction_channel: str | None = None
    service_type: str | None = None
    narrative: str | None = None
    receiver_name: str | None = None
    phone_no: str | None = None
    institution_name: str | None = None
    transaction_reference: str | None = None
    transfer_reference: str | None = None
    transaction_date: datetime | None = None
    transaction_amount: float | None = None
    service_charge: float | None = None
    excise_tax: float | None = None
    vat: float | None = None
    penalty_fee: float | None = None
    income_tax_fee: float | None = None
    interest_fee: float | None = None
    stamp_duty: float | None = None
    discount_amount: float | None = None
    total: float | None = None
    error: str | None = None


def _title_case(s: str) -> str:
    return s.title()


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _extract_amount(text: str, regex: re.Pattern[str]) -> float | None:
    match = regex.search(text)
    if match and match.group(1):
        cleaned = match.group(1).replace(",", "")
        try:
            val = float(cleaned)
            return val
        except ValueError:
            return None
    return None


async def verify_dashen(transaction_reference: str) -> DashenVerifyResult:
    """Verify a Dashen Bank transaction with retry logic."""
    url = f"https://receipt.dashensuperapp.com/receipt/{transaction_reference}"
    max_retries = 5
    retry_delay = 2.0  # seconds

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "\U0001f50e Fetching Dashen receipt (Attempt %d/%d): %s",
                attempt,
                max_retries,
                url,
            )
            async with httpx.AsyncClient(verify=_make_ssl_context(), timeout=60.0) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Accept": "application/pdf",
                    },
                )
                response.raise_for_status()

            logger.info("\u2705 Dashen receipt fetch success, parsing PDF")
            return _parse_dashen_receipt(response.content)

        except Exception as e:
            logger.warning(
                "\u26a0\ufe0f Dashen receipt fetch failed (Attempt %d/%d): %s",
                attempt,
                max_retries,
                str(e),
            )
            if attempt == max_retries:
                logger.error("\u274c All retry attempts failed for Dashen receipt.")
                return DashenVerifyResult(
                    success=False,
                    error=f"Failed to fetch receipt after {max_retries} attempts: {e}",
                )
            logger.info("\u23f3 Waiting %.0fms before retry...", retry_delay * 1000)
            await asyncio.sleep(retry_delay)

    return DashenVerifyResult(success=False, error="Unknown error in retry loop")


def _parse_dashen_receipt(pdf_bytes: bytes) -> DashenVerifyResult:
    """Extract fields from a Dashen Bank PDF receipt."""
    try:
        logger.info("\U0001f4ca PDF buffer size: %d bytes", len(pdf_bytes))
        reader = PdfReader(io.BytesIO(pdf_bytes))
        raw_text = ""
        for page in reader.pages:
            raw_text += page.extract_text() or ""

        raw_text = re.sub(r"\s+", " ", raw_text).strip()
        logger.info("\U0001f4c4 Parsing Dashen receipt text")
        logger.debug("\U0001f4dd Raw PDF text length: %d characters", len(raw_text))

        # Sender info
        sender_name_m = re.search(
            r"Sender\s*Name\s*:?\s*(.*?)\s+(?:Sender\s*Account|Account)", raw_text, re.I
        )
        sender_name = sender_name_m.group(1).strip() if sender_name_m else None

        sender_account_m = re.search(
            r"Sender\s*Account\s*(?:Number)?\s*:?\s*([A-Z0-9\*\-]+)", raw_text, re.I
        )
        sender_account_number = sender_account_m.group(1).strip() if sender_account_m else None

        # Transaction details
        channel_m = re.search(
            r"Transaction\s*Channel\s*:?\s*(.*?)\s+(?:Service|Type)", raw_text, re.I
        )
        transaction_channel = channel_m.group(1).strip() if channel_m else None

        service_m = re.search(
            r"Service\s*Type\s*:?\s*(.*?)\s+(?:Narrative|Description)", raw_text, re.I
        )
        service_type = service_m.group(1).strip() if service_m else None

        narrative_m = re.search(r"Narrative\s*:?\s*(.*?)\s+(?:Receiver|Phone)", raw_text, re.I)
        narrative = narrative_m.group(1).strip() if narrative_m else None

        # Receiver info
        receiver_name_m = re.search(
            r"Receiver\s*Name\s*:?\s*(.*?)\s+(?:Phone|Institution)", raw_text, re.I
        )
        receiver_name = receiver_name_m.group(1).strip() if receiver_name_m else None

        phone_m = re.search(r"Phone\s*(?:No\.?|Number)?\s*:?\s*([+\d\-\s]+)", raw_text, re.I)
        phone_no = phone_m.group(1).strip() if phone_m else None

        institution_m = re.search(
            r"Institution\s*Name\s*:?\s*(.*?)\s+(?:Transaction|Reference)", raw_text, re.I
        )
        institution_name = institution_m.group(1).strip() if institution_m else None

        # References
        tx_ref_m = re.search(r"Transaction\s*Reference\s*:?\s*([A-Z0-9\-]+)", raw_text, re.I)
        transaction_ref = tx_ref_m.group(1).strip() if tx_ref_m else None

        xfer_ref_m = re.search(r"Transfer\s*Reference\s*:?\s*([A-Z0-9\-]+)", raw_text, re.I)
        transfer_reference = xfer_ref_m.group(1).strip() if xfer_ref_m else None

        # Date
        date_m = re.search(
            r"Transaction\s*Date\s*(?:&\s*Time)?\s*:?\s*([\d/\-,: ]+(?:[APM]{2})?)", raw_text, re.I
        )
        date_raw = date_m.group(1).strip() if date_m else None
        transaction_date: datetime | None = None
        if date_raw:
            for fmt in (
                "%m/%d/%Y, %I:%M:%S %p",
                "%m/%d/%Y %I:%M:%S %p",
                "%Y-%m-%d %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
            ):
                try:
                    transaction_date = datetime.strptime(date_raw, fmt)
                    break
                except ValueError:
                    continue

        # Amounts
        transaction_amount = _extract_amount(
            raw_text, re.compile(r"Transaction\s*Amount\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        service_charge = _extract_amount(
            raw_text, re.compile(r"Service\s*Charge\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        excise_tax = _extract_amount(
            raw_text,
            re.compile(r"Excise\s*Tax\s*(?:\(15%\))?\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I),
        )
        vat = _extract_amount(
            raw_text, re.compile(r"VAT\s*(?:\(15%\))?\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        penalty_fee = _extract_amount(
            raw_text, re.compile(r"Penalty\s*Fee\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        income_tax_fee = _extract_amount(
            raw_text, re.compile(r"Income\s*Tax\s*Fee\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        interest_fee = _extract_amount(
            raw_text, re.compile(r"Interest\s*Fee\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        stamp_duty = _extract_amount(
            raw_text, re.compile(r"Stamp\s*Duty\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        discount_amount = _extract_amount(
            raw_text, re.compile(r"Discount\s*Amount\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )
        total = _extract_amount(
            raw_text, re.compile(r"Total\s*(?:ETB|Birr)?\s*([\d,]+\.?\d*)", re.I)
        )

        # Format names
        formatted_sender = _title_case(sender_name) if sender_name else None
        formatted_receiver = _title_case(receiver_name) if receiver_name else None
        formatted_institution = _title_case(institution_name) if institution_name else None

        if transaction_ref and transaction_amount:
            logger.info("\u2705 PDF parsing successful - all required fields extracted")
            return DashenVerifyResult(
                success=True,
                sender_name=formatted_sender,
                sender_account_number=sender_account_number,
                transaction_channel=transaction_channel,
                service_type=service_type,
                narrative=narrative,
                receiver_name=formatted_receiver,
                phone_no=phone_no,
                institution_name=formatted_institution,
                transaction_reference=transaction_ref,
                transfer_reference=transfer_reference,
                transaction_date=transaction_date,
                transaction_amount=transaction_amount,
                service_charge=service_charge,
                excise_tax=excise_tax,
                vat=vat,
                penalty_fee=penalty_fee,
                income_tax_fee=income_tax_fee,
                interest_fee=interest_fee,
                stamp_duty=stamp_duty,
                discount_amount=discount_amount,
                total=total,
            )
        else:
            logger.warning("\u26a0\ufe0f PDF parsing failed - missing required fields")
            return DashenVerifyResult(
                success=False,
                error="Could not extract required fields (Transaction Reference and Amount) from PDF.",
            )

    except Exception as e:
        logger.error("\u274c Dashen PDF parsing failed: %s", str(e))
        return DashenVerifyResult(success=False, error="Error parsing PDF data")
