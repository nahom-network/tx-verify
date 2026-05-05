"""M-Pesa payment verification service."""

import base64
import io
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from pypdf import PdfReader

from tx_verify.utils.logger import logger


@dataclass
class MpesaVerifyResult:
    """M-Pesa verification result.

    Fields present on every receipt are typed attributes.
    Fields that vary by receipt type go into ``meta``.
    """

    success: bool
    transaction_id: str | None = None
    receipt_no: str | None = None
    payment_date: datetime | None = None
    amount: float | None = None
    service_fee: float | None = None
    vat: float | None = None
    payer_name: str | None = None
    payer_account: str | None = None
    payment_method: str | None = None
    transaction_type: str | None = None
    payment_channel: str | None = None
    amount_in_words: str | None = None
    meta: dict = field(default_factory=dict)
    error: str | None = None


def _title_case(s: str) -> str:
    return s.title()


def _clean_amharic(text: str) -> str:
    """Strip Ethiopic/Amharic characters from extracted text."""
    return re.sub(r"[\u1200-\u137F\u1380-\u139F\u2D80-\u2DDF\uAB00-\uAB2F]+", " ", text).strip()


def _extract_layout_lines(pdf_bytes: bytes) -> list[str]:
    """Extract raw text lines from a PDF using layout-aware extraction."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text(extraction_mode="layout") or ""
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def _split_label_value(line: str) -> tuple[str | None, str | None]:
    """Split a layout-extracted line into (label, value).

    M-Pesa PDFs render labels on the left and values on the right,
    separated by two or more spaces.  We strip leading ``/`` and Amharic
    text before splitting.
    """
    line = _clean_amharic(line)
    line = line.lstrip("/").strip()

    # Multi-column detail rows (RECEIPT NO / PAYMENT DATE / SETTLED AMOUNT)
    # are handled separately, so we only care about normal label-value lines.
    parts = re.split(r"\s{2,}", line)
    if len(parts) >= 2:
        label = parts[0].strip().rstrip(":").strip()
        value = parts[-1].strip()
        return label, value
    return None, None


def _is_null_value(value: str) -> bool:
    return value in ("- - -", "null", "---", "")


_LABEL_MAP: dict[str, tuple[str, str]] = {
    "SENDER NAME": ("payer_name", "data"),
    "BUYER NAME": ("payer_name", "data"),
    "SENDER NUMBER": ("payer_account", "data"),
    "BUYER PHONE NUMBER": ("payer_account", "data"),
    "SENDER TIN NO": ("payer_tin", "meta"),
    "BUYER TIN NO": ("payer_tin", "meta"),
    "RECEIVER NAME": ("receiver_name", "meta"),
    "RECEIVER ACCOUNT NUMBER": ("receiver_account", "meta"),
    "RECEIVER BUSINESS NAME": ("receiver_business_name", "meta"),
    "RECEIVER BUSINESS NUMBER": ("receiver_business_number", "meta"),
    "BANK NAME": ("bank_name", "meta"),
    "TRANSACTION ID": ("transaction_id", "data"),
    "SERVICE FEE": ("service_fee", "data"),
    "DISCOUNT": ("discount", "meta"),
    "+ 15% VAT": ("vat", "data"),
    "TOTAL": ("amount", "data"),
    "TOTAL AMOUNT IN WORDS": ("amount_in_words", "data"),
    "PAYMENT METHOD": ("payment_method", "data"),
    "TRANSACTION TYPE": ("transaction_type", "data"),
    "PAYMENT CHANNEL": ("payment_channel", "data"),
    "PAYMENT REASON": ("payment_reason", "meta"),
    "PACKAGE DETAILS": ("package_details", "meta"),
    "VALIDITY PERIOD": ("validity_period", "meta"),
}


def _parse_receipt_lines(lines: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse layout-extracted lines into structured data + meta dict."""
    data: dict[str, Any] = {}
    meta: dict[str, Any] = {}

    # --- Multi-column detail header ---
    receipt_header_idx: int | None = None
    for i, line in enumerate(lines):
        if "RECEIPT NO" in line and "PAYMENT DATE" in line and "SETTLED AMOUNT" in line:
            receipt_header_idx = i
            break

    if receipt_header_idx is not None and receipt_header_idx + 1 < len(lines):
        val_line = _clean_amharic(lines[receipt_header_idx + 1]).strip()
        parts = re.split(r"\s{2,}", val_line)
        if len(parts) >= 3:
            data["receipt_no"] = parts[0].strip()
            date_time_str = " ".join(parts[1:-1]).strip()
            amount_str = parts[-1].strip()
            data["amount"] = float(amount_str)
            m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", date_time_str)
            if m:
                with suppress(ValueError):
                    data["payment_date"] = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")

    # --- Regular label-value pairs ---
    for i, line in enumerate(lines):
        if receipt_header_idx is not None and i in (
            receipt_header_idx,
            receipt_header_idx + 1,
        ):
            continue

        label, value = _split_label_value(line)
        if not label or not value or _is_null_value(value):
            continue

        # Skip section headers and unrelated text
        if label in ("TRANSACTION INFORMATION", "TRANSACTION DETAIL", "SCAN TO VERIFY"):
            continue
        if label.startswith("Safaricom") or label.startswith("THANK YOU"):
            continue

        mapping = _LABEL_MAP.get(label)
        if mapping:
            key, dest = mapping
            container = data if dest == "data" else meta
            container[key] = value

    # --- Clean up payer name ---
    if "payer_name" in data:
        data["payer_name"] = _title_case(data["payer_name"])

    # --- Convert numeric string fields to float ---
    for key in ("amount", "service_fee", "vat"):
        if key in data:
            with suppress(ValueError):
                data[key] = float(str(data[key]).replace(",", ""))

    # Discount only goes to meta, but may still be a string
    if "discount" in meta:
        with suppress(ValueError):
            meta["discount"] = float(str(meta["discount"]).replace(",", ""))

    return data, meta


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _fetch_from_url(url: str, source: str) -> Any:
    logger.info("🔎 Fetching receipt data from %s: %s", source, url)
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
    skip_primary = os.getenv("SKIP_PRIMARY_VERIFICATION") == "true"

    try:
        data: Any = None

        if not skip_primary:
            try:
                data = await _fetch_from_url(primary_url, "primary API")
            except Exception as e:
                logger.warning("⚠️ Primary M-Pesa fetch failed: %s. Trying fallback proxy...", e)
        else:
            logger.info("⏭️ Skipping primary verifier due to SKIP_PRIMARY_VERIFICATION=true")

        if not data:
            return MpesaVerifyResult(
                success=False,
                error="Failed to fetch M-Pesa receipt from both primary and fallback sources.",
            )

        logger.info(
            "📡 API Response Code: %s, Description: %s",
            data.get("responseCode"),
            data.get("responseDescription"),
        )

        if data.get("responseCode") == "0" and data.get("base64Data"):
            logger.info("✅ API returned success and base64 data. Converting to buffer...")
            try:
                pdf_bytes = base64.b64decode(data["base64Data"])
                logger.info("📦 PDF Buffer created (%d bytes). Parsing PDF...", len(pdf_bytes))
                return _parse_mpesa_receipt(pdf_bytes)
            except Exception as e:
                logger.error("❌ Failed to convert/parse base64 PDF: %s", e)
                return MpesaVerifyResult(success=False, error=f"Failed to process PDF data: {e}")
        else:
            logger.warning("⚠️ M-Pesa returned unsuccessful code or missing data")
            return MpesaVerifyResult(
                success=False,
                error=f"API Error: {data.get('responseDescription', 'Unknown error')}",
            )

    except Exception as e:
        logger.error("❌ M-Pesa verification failed: %s", e)
        return MpesaVerifyResult(success=False, error=f"Request failed: {e}")


def _parse_mpesa_receipt(pdf_bytes: bytes) -> MpesaVerifyResult:
    """Extract fields from an M-Pesa PDF receipt."""
    try:
        logger.info("📄 Parsing M-Pesa receipt text")
        lines = _extract_layout_lines(pdf_bytes)
        data, meta = _parse_receipt_lines(lines)

        if not data.get("transaction_id"):
            logger.error("❌ Could not extract transaction_id from PDF")
            return MpesaVerifyResult(
                success=False, error="Could not parse required fields from PDF receipt."
            )

        logger.info("✅ Parsed M-Pesa receipt for transaction %s", data.get("transaction_id"))
        return MpesaVerifyResult(success=True, meta=meta, **data)

    except Exception as e:
        logger.error("❌ Error parsing PDF buffer: %s", e)
        return MpesaVerifyResult(success=False, error=f"Failed to parse PDF content: {e}")
