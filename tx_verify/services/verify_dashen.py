"""Dashen Bank payment verification service.

Translated from src/services/verifyDashen.ts
"""

import io
import ssl
from datetime import datetime
from typing import Any

from pypdf import PdfReader

from tx_verify.models import TransactionResult
from tx_verify.utils.http_client import fetch_with_retry
from tx_verify.utils.logger import logger

# Labels that appear in the "Transaction Details" section as line pairs:
# Label line followed by an "ETB <amount>" line.
_DETAIL_LABELS: set[str] = {
    "Transaction Amount",
    "Service Charge",
    "Excise Tax (15%)",
    "DRRF Fee",
    "VAT (15%)",
    "Penalty Fee",
    "Income Tax Fee",
    "Tax",
    "Interest Fee",
    "Stamp Duty",
    "Discount Amount",
    "Total",
}

# Lines that mark the end of a multi-line value in the header section.
_HEADER_STOP_LINES: set[str] = {
    "Dashen Bank",
    "Transaction Details",
    "Terms & Conditions",
    "For any support: please call us at",
    "Dashen Bank S.C.",
    "Always One Step Ahead!",
}

# Known typed attribute names (used to decide what goes into meta).
_KNOWN_FIELDS: set[str] = {
    "success",
    "sender_name",
    "sender_account_number",
    "transaction_channel",
    "service_type",
    "narrative",
    "receiver_name",
    "receiver_account_number",
    "institution_name",
    "transaction_reference",
    "transfer_reference",
    "transaction_date",
    "transaction_amount",
    "service_charge",
    "excise_tax",
    "drrf_fee",
    "vat",
    "penalty_fee",
    "income_tax_fee",
    "tax",
    "interest_fee",
    "stamp_duty",
    "discount_amount",
    "total",
    "amount_in_words",
    "meta",
    "error",
}


_KEY_REMAP: dict[str, str] = {
    "instituton_name": "institution_name",
    "excise_tax_15": "excise_tax",
    "vat_15": "vat",
}


def _title_case(s: str) -> str:
    return s.title()


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _snake_case_label(label: str) -> str:
    """Convert a PDF label like 'Excise Tax (15%)' to a snake-case key."""
    return (
        label.strip().lower().replace(" ", "_").replace("(", "").replace(")", "").replace("%", "")
    )


def _parse_amount(value: str) -> float | None:
    """Parse an ETB amount string like 'ETB 100,000.00' or 'ETB 0'."""
    cleaned = value.replace("ETB", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(value: str) -> datetime | None:
    """Parse Dashen receipt date strings."""
    value = value.strip()
    formats = (
        "%b %d, %Y, %I:%M:%S %p",
        "%b %d, %Y %I:%M:%S %p",
        "%m/%d/%Y, %I:%M:%S %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _extract_lines_from_pdf(pdf_bytes: bytes) -> list[str]:
    """Return cleaned, non-empty lines from all pages of a PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def _extract_fields(lines: list[str]) -> dict[str, str]:
    """Build a flat field dictionary from receipt lines."""
    fields: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        lower = line.lower()

        # Special case: "Amount in words:" may span multiple lines.
        if lower.startswith("amount in words"):
            value_lines: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if (
                    nxt.endswith(":")
                    or nxt in _DETAIL_LABELS
                    or nxt.startswith("ETB")
                    or nxt in _HEADER_STOP_LINES
                ):
                    break
                value_lines.append(nxt)
                i += 1
            fields["amount_in_words"] = " ".join(value_lines).strip()
            continue

        # Transaction detail label followed by an ETB amount line.
        if line in _DETAIL_LABELS and i + 1 < len(lines) and lines[i + 1].startswith("ETB"):
            key = _snake_case_label(line)
            fields[key] = lines[i + 1]
            i += 2
            continue

        # Header label ending with ':' followed by a value on the next line(s).
        if line.endswith(":"):
            raw_key = line[:-1].strip().lower().replace(" ", "_").replace(".", "")
            value_lines = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if (
                    nxt.endswith(":")
                    or nxt in _DETAIL_LABELS
                    or nxt.lower().startswith("amount in words")
                    or nxt in _HEADER_STOP_LINES
                ):
                    break
                value_lines.append(nxt)
                i += 1
            fields[raw_key] = " ".join(value_lines).strip()
            continue

        i += 1

    return fields


def _build_result(raw_fields: dict[str, str]) -> TransactionResult:
    """Map raw extracted fields into a typed TransactionResult."""
    meta: dict[str, Any] = {}
    typed: dict[str, Any] = {}

    for key, val in raw_fields.items():
        remapped = _KEY_REMAP.get(key, key)

        if remapped == "transaction_date":
            typed[remapped] = _parse_date(val)
        elif remapped in {
            "transaction_amount",
            "service_charge",
            "excise_tax",
            "drrf_fee",
            "vat",
            "penalty_fee",
            "income_tax_fee",
            "tax",
            "interest_fee",
            "stamp_duty",
            "discount_amount",
            "total",
        }:
            typed[remapped] = _parse_amount(val)
        elif remapped in _KNOWN_FIELDS:
            typed[remapped] = val
        else:
            meta[remapped] = val

    # Required fields for success
    tx_ref = typed.get("transaction_reference") or typed.get("transaction_ref")
    tx_amt = typed.get("transaction_amount")
    if tx_ref and tx_amt is not None:
        success = True
        error = None
        logger.info("✅ PDF parsing successful - all required fields extracted")
    else:
        success = False
        error = "Could not extract required fields (Transaction Reference and Amount) from PDF."
        logger.warning("⚠️ PDF parsing failed - missing required fields")

    # Format names
    for name_key in ("sender_name", "receiver_name", "institution_name"):
        if isinstance(typed.get(name_key), str):
            typed[name_key] = _title_case(typed[name_key])

    # Move provider-specific fields to meta
    for meta_key in (
        "institution_name",
        "transfer_reference",
        "excise_tax",
        "drrf_fee",
        "penalty_fee",
        "income_tax_fee",
        "tax",
        "interest_fee",
        "stamp_duty",
        "discount_amount",
    ):
        if meta_key in typed:
            meta[meta_key] = typed.pop(meta_key)

    return TransactionResult(
        success=success,
        provider="dashen",
        error=error,
        payer_name=typed.get("sender_name"),
        payer_account=typed.get("sender_account_number"),
        payment_channel=typed.get("transaction_channel"),
        transaction_type=typed.get("service_type"),
        narrative=typed.get("narrative"),
        receiver_name=typed.get("receiver_name"),
        receiver_account=typed.get("receiver_account_number"),
        transaction_reference=tx_ref,
        transaction_date=typed.get("transaction_date"),
        amount=typed.get("transaction_amount"),
        service_charge=typed.get("service_charge"),
        vat=typed.get("vat"),
        total_amount=typed.get("total"),
        amount_in_words=typed.get("amount_in_words"),
        meta=meta,
    )


async def verify_dashen(
    transaction_reference: str, *, proxies: str | dict[str, str] | None = None
) -> TransactionResult:
    """Verify a Dashen Bank transaction with retry logic."""
    url = f"https://receipt.dashensuperapp.com/receipt/{transaction_reference}"
    max_retries = 5
    retry_delay = 2.0  # seconds

    try:
        logger.info("🔎 Fetching Dashen receipt: %s", url)
        response = await fetch_with_retry(
            url,
            max_retries=max_retries,
            retry_delay=retry_delay,
            verify=_make_ssl_context(),
            timeout=60.0,
            proxies=proxies,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/pdf",
            },
        )
        logger.info("✅ Dashen receipt fetch success, parsing PDF")
        return _parse_dashen_receipt(response.content)
    except Exception as e:
        logger.error("❌ All retry attempts failed for Dashen receipt: %s", str(e))
        return TransactionResult(
            success=False,
            provider="dashen",
            error=f"Failed to fetch receipt after {max_retries} attempts: {e}",
        )


def _parse_dashen_receipt(pdf_bytes: bytes) -> TransactionResult:
    """Extract fields from a Dashen Bank PDF receipt."""
    try:
        logger.info("📊 PDF buffer size: %d bytes", len(pdf_bytes))
        logger.info("📄 Parsing Dashen receipt text")

        lines = _extract_lines_from_pdf(pdf_bytes)
        logger.debug("📝 Extracted %d lines from PDF", len(lines))

        raw_fields = _extract_fields(lines)
        logger.debug("📝 Extracted %d raw fields", len(raw_fields))

        return _build_result(raw_fields)
    except Exception as e:
        logger.error("❌ Dashen PDF parsing failed: %s", str(e))
        return TransactionResult(
            success=False,
            provider="dashen",
            error="Error parsing PDF data",
        )
