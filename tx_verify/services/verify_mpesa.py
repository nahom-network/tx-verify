"""M-Pesa payment verification service.

Translated from src/services/verifyMpesa.ts
"""

import base64
import io
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from pypdf import PdfReader

from tx_verify.utils.logger import logger


@dataclass
class MpesaVerifyResult:
    """M-Pesa verification result."""

    success: bool
    payer_name: str | None = None
    payer_account: str | None = None
    receiver_name: str | None = None
    receiver_account: str | None = None
    transaction_id: str | None = None
    receipt_no: str | None = None
    payment_date: datetime | None = None
    amount: float | None = None
    service_fee: float | None = None
    vat: float | None = None
    error: str | None = None


def _title_case(s: str) -> str:
    return s.title()


async def _fetch_from_url(url: str, source: str) -> Any:
    logger.info("\U0001f50e Fetching receipt data from %s: %s", source, url)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://m-pesabusiness.safaricom.et/",
            },
        )
    return response.json()


async def verify_mpesa(transaction_id: str) -> MpesaVerifyResult:
    """Verify an M-Pesa transaction."""
    primary_url = (
        f"https://m-pesabusiness.safaricom.et/api/receipt/getReceipt?trxNo={transaction_id}"
    )
    proxy_key = os.getenv("MPESA_PROXY_KEY", "")
    fallback_url = f"https://leul.et/mpesa.php?reference={transaction_id}&key={proxy_key}"
    skip_primary = os.getenv("SKIP_PRIMARY_VERIFICATION") == "true"

    try:
        data: Any = None

        if not skip_primary:
            try:
                data = await _fetch_from_url(primary_url, "primary API")
            except Exception as e:
                logger.warning(
                    "\u26a0\ufe0f Primary M-Pesa fetch failed: %s. Trying fallback proxy...", e
                )
        else:
            logger.info(
                "\u23ed\ufe0f Skipping primary verifier due to SKIP_PRIMARY_VERIFICATION=true"
            )

        if not data or data.get("responseCode") != "0" or not data.get("base64Data"):
            try:
                data = await _fetch_from_url(fallback_url, "fallback proxy")
            except Exception as e:
                logger.error("\u274c M-Pesa fallback proxy request failed: %s", e)

        if not data:
            return MpesaVerifyResult(
                success=False,
                error="Failed to fetch M-Pesa receipt from both primary and fallback sources.",
            )

        logger.info(
            "\U0001f4e1 API Response Code: %s, Description: %s",
            data.get("responseCode"),
            data.get("responseDescription"),
        )

        if data.get("responseCode") == "0" and data.get("base64Data"):
            logger.info("\u2705 API returned success and base64 data. Converting to buffer...")
            try:
                pdf_bytes = base64.b64decode(data["base64Data"])
                logger.info(
                    "\U0001f4e6 PDF Buffer created (%d bytes). Parsing PDF...", len(pdf_bytes)
                )
                return _parse_mpesa_receipt(pdf_bytes)
            except Exception as e:
                logger.error("\u274c Failed to convert/parse base64 PDF: %s", e)
                return MpesaVerifyResult(success=False, error=f"Failed to process PDF data: {e}")
        else:
            logger.warning("\u26a0\ufe0f M-Pesa returned unsuccessful code or missing data")
            return MpesaVerifyResult(
                success=False,
                error=f"API Error: {data.get('responseDescription', 'Unknown error')}",
            )

    except Exception as e:
        logger.error("\u274c M-Pesa verification failed: %s", e)
        return MpesaVerifyResult(success=False, error=f"Request failed: {e}")


def _parse_mpesa_receipt(pdf_bytes: bytes) -> MpesaVerifyResult:
    """Extract fields from an M-Pesa PDF receipt."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        raw_text = ""
        for page in reader.pages:
            raw_text += page.extract_text() or ""
        raw_text = re.sub(r"\s+", " ", raw_text).strip()

        logger.info("\U0001f4c4 Parsing M-Pesa receipt text")
        logger.debug("\U0001f4dd Raw PDF text length: %d characters", len(raw_text))

        payer_name_m = re.search(
            r"PAYER NAME\s+(.*?)\s+(?:PAYER PHONE|00\d+|Addis Ababa|\+251|\u12e8\u12a8\u134b\u12ed \u1235\u121d)",
            raw_text,
            re.I,
        )
        payer_name = payer_name_m.group(1).strip() if payer_name_m else None

        payer_phone_m = re.search(r"PAYER PHONE NUMBER\s+(\d+)", raw_text, re.I)
        payer_phone = payer_phone_m.group(1).strip() if payer_phone_m else None

        tx_id_m = re.search(r"TRANSACTION ID\s+([A-Z0-9]+)", raw_text, re.I)
        tx_id = tx_id_m.group(1).strip() if tx_id_m else None

        receipt_m = re.search(r"RECEIPT NO.*?([A-Z0-9]{10,})(?:202\d)", raw_text, re.I)
        receipt_no = receipt_m.group(1).strip() if receipt_m else None

        amount_m = re.search(r"TOTAL\s+([\d,]+\.\d{2})", raw_text, re.I)
        amount = float(amount_m.group(1).replace(",", "")) if amount_m else None

        svc_fee_m = re.search(r"([\d,]+\.\d{2})\s*Birr\s*/\s*SERVICE FEE", raw_text, re.I)
        service_fee = float(svc_fee_m.group(1).replace(",", "")) if svc_fee_m else None

        vat_m = re.search(r"SERVICE FEE\s*/\s*([\d,]+\.\d{2})\s*.*?\+ 15% VAT", raw_text, re.I)
        vat: float | None = float(vat_m.group(1).replace(",", "")) if vat_m else None

        if vat is None and service_fee is not None and re.search(r"/ \+ 15% VAT", raw_text):
            vat = 0.0

        date_m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", raw_text)
        payment_date: datetime | None = None
        if date_m:
            with suppress(ValueError):
                payment_date = datetime.strptime(date_m.group(1), "%Y-%m-%d %H:%M:%S")

        receiver_name_m = re.search(
            r"RECEIVER NAME.*?(?:\u12e8\u1270\u1240\u1263\u12e9 \u1262\u12dd\u1290\u1235 \u1235\u121d)?\s+([A-Za-z\s]+?)\s+/",
            raw_text,
            re.I,
        )
        receiver_name = receiver_name_m.group(1).strip() if receiver_name_m else None

        receiver_num_m = re.search(r"RECEIVER NUMBER\s+(\d+)", raw_text, re.I)
        receiver_phone = receiver_num_m.group(1).strip() if receiver_num_m else None

        if not receiver_phone:
            fallback_m = re.search(r"TOTAL\s+[\d,]+\.\d{2}\s+(\d{9,12})", raw_text, re.I)
            if fallback_m:
                receiver_phone = fallback_m.group(1)

        # Clean up payer name
        if payer_name:
            payer_name = re.sub(r"\d+.*", "", payer_name).strip()
            payer_name = _title_case(payer_name)

        return MpesaVerifyResult(
            success=True,
            payer_name=payer_name,
            payer_account=payer_phone,
            receiver_name=_title_case(receiver_name) if receiver_name else None,
            receiver_account=receiver_phone,
            transaction_id=tx_id,
            receipt_no=receipt_no,
            payment_date=payment_date,
            amount=amount,
            service_fee=service_fee,
            vat=vat,
        )

    except Exception as e:
        logger.error("\u274c Error parsing PDF buffer: %s", e)
        return MpesaVerifyResult(success=False, error=f"Failed to parse PDF content: {e}")
