"""CBE Birr payment verification service.

Translated from src/services/verifyCBEBirr.ts
"""

import io
import re
from dataclasses import dataclass

import httpx
from pypdf import PdfReader

from verifier_api.utils.logger import logger


@dataclass
class CBEBirrReceipt:
    """CBE Birr receipt data."""

    customer_name: str = ""
    debit_account: str = ""
    credit_account: str = ""
    receiver_name: str = ""
    order_id: str = ""
    transaction_status: str = ""
    reference: str = ""
    receipt_number: str = ""
    transaction_date: str = ""
    amount: str = ""
    paid_amount: str = ""
    service_charge: str = ""
    vat: str = ""
    total_paid_amount: str = ""
    payment_reason: str = ""
    payment_channel: str = ""


@dataclass
class CBEBirrError:
    success: bool = False
    error: str = ""


async def verify_cbe_birr(receipt_number: str, phone_number: str) -> CBEBirrReceipt | CBEBirrError:
    """Verify a CBE Birr transaction by fetching and parsing its PDF receipt."""
    try:
        logger.info(
            "[CBEBirr] Starting verification for receipt: %s, phone: %s",
            receipt_number,
            phone_number,
        )

        url = f"https://cbepay1.cbe.com.et/aureceipt?TID={receipt_number}&PH={phone_number}"
        logger.info("[CBEBirr] Fetching PDF from: %s", url)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )

        logger.info("[CBEBirr] PDF response status: %s", response.status_code)
        logger.info("[CBEBirr] PDF content length: %d bytes", len(response.content))

        if response.status_code != 200:
            logger.error("[CBEBirr] Failed to fetch PDF: HTTP %s", response.status_code)
            return CBEBirrError(
                success=False, error=f"Failed to fetch receipt: HTTP {response.status_code}"
            )

        # Parse PDF
        reader = PdfReader(io.BytesIO(response.content))
        pdf_text = ""
        for page in reader.pages:
            pdf_text += page.extract_text() or ""

        logger.info("[CBEBirr] PDF text extracted (%d characters)", len(pdf_text))

        receipt = _parse_cbe_birr_receipt(pdf_text)
        if not receipt:
            logger.error("[CBEBirr] Failed to parse receipt data from PDF")
            return CBEBirrError(success=False, error="Failed to parse receipt data from PDF")

        logger.info("[CBEBirr] Successfully parsed receipt data")
        return receipt

    except Exception as e:
        logger.error("[CBEBirr] Error during verification: %s", e)
        return CBEBirrError(
            success=False,
            error=str(e) if str(e) else "Unknown error occurred",
        )


def _extract_value(text: str, pattern: re.Pattern[str]) -> str:
    m = pattern.search(text)
    result = m.group(1).strip() if m else ""
    return re.sub(r"\s{2,}", " ", result.replace("\n", " "))


def _parse_cbe_birr_receipt(pdf_text: str) -> CBEBirrReceipt | None:
    """Parse CBE Birr receipt fields from extracted PDF text."""
    try:
        logger.info("[CBEBirr] Starting PDF text parsing...")

        customer_name = _extract_value(
            pdf_text, re.compile(r"Sub city:[\s\n]+([A-Z\s]+?)[\s\n]+Wereda/kebele:", re.I)
        )

        debit_m = re.search(r"Debit Account\s*([\s\S]*?)(?=\s*Credit Account)", pdf_text, re.I)
        debit_account = debit_m.group(1).replace("\n", " ").strip() if debit_m else ""

        credit_account = _extract_value(
            pdf_text, re.compile(r"Credit Account\s*([\s\S]*?)(?=\s*Receiver Name)", re.I)
        )
        receiver_name = _extract_value(
            pdf_text, re.compile(r"Receiver Name\s*([\s\S]*?)(?=\s*Order ID)", re.I)
        )

        order_id = _extract_value(pdf_text, re.compile(r"Order ID\s*([A-Z0-9]+)", re.I))
        transaction_status = _extract_value(
            pdf_text, re.compile(r"Transaction Status\s*([a-zA-Z]+)", re.I)
        )

        ref_m = re.search(
            r"Reference[\s:]*(.*?)(?=\s*(?:Transaction Details|Receipt Number|\u12e8\u12a2\u1275\u12ee\u1335\u12eb|Commercial Bank))",
            pdf_text,
            re.I | re.S,
        )
        reference = ref_m.group(1).replace("\n", " ").strip() if ref_m else ""
        reference = re.sub(r"^[\s:]+|[\s:]+$", "", reference)

        receipt_m = re.search(r"([A-Z0-9]{10})(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})([\d.]+)", pdf_text)
        receipt_number = receipt_m.group(1) if receipt_m else ""
        transaction_date = receipt_m.group(2) if receipt_m else ""
        amount = receipt_m.group(3) if receipt_m else ""

        financial_m = re.search(
            r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+Paid amount", pdf_text, re.I
        )
        paid_amount = financial_m.group(1) if financial_m else ""
        service_charge = financial_m.group(2) if financial_m else ""
        vat = financial_m.group(3) if financial_m else ""
        total_paid_amount = financial_m.group(4) if financial_m else ""

        payment_m = re.search(
            r"Payment Channel[\s\n]+([^\n]+)[\s\n]+([^\n]+)[\s\n]+([^\n]+)", pdf_text, re.I
        )
        payment_reason = payment_m.group(2).strip() if payment_m else ""
        payment_channel = payment_m.group(3).strip() if payment_m else ""

        receipt = CBEBirrReceipt(
            customer_name=customer_name,
            debit_account=debit_account,
            credit_account=credit_account,
            receiver_name=receiver_name,
            order_id=order_id,
            transaction_status=transaction_status,
            reference=reference,
            receipt_number=receipt_number,
            transaction_date=transaction_date,
            amount=amount,
            paid_amount=paid_amount,
            service_charge=service_charge,
            vat=vat,
            total_paid_amount=total_paid_amount,
            payment_reason=payment_reason,
            payment_channel=payment_channel,
        )

        if not customer_name and not receipt_number and not amount:
            logger.warning("[CBEBirr] No essential fields found in PDF")
            return None

        return receipt

    except Exception as e:
        logger.error("[CBEBirr] Error parsing PDF text: %s", e)
        return None
