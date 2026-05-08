"""CBE Birr payment verification service.

Translated from src/services/verifyCBEBirr.ts
"""

import io
import re
from contextlib import suppress
from datetime import datetime

from pypdf import PdfReader

from tx_verify.models import TransactionResult
from tx_verify.utils.http_client import get_async_client
from tx_verify.utils.logger import logger


def _parse_amount(value: str) -> float | None:
    """Parse a numeric amount string like '1,000.00' or '0'."""
    cleaned = value.replace(",", "").replace("ETB", "").strip()
    with suppress(ValueError):
        return float(cleaned)
    return None


def _parse_date(value: str) -> datetime | None:
    """Best-effort parse of CBE Birr transaction date strings."""
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


async def verify_cbe_birr(
    receipt_number: str, phone_number: str, *, proxies: str | dict[str, str] | None = None
) -> TransactionResult:
    """Verify a CBE Birr transaction by fetching and parsing its PDF receipt."""
    try:
        logger.info(
            "[CBEBirr] Starting verification for receipt: %s, phone: %s",
            receipt_number,
            phone_number,
        )

        url = f"https://cbepay1.cbe.com.et/aureceipt?TID={receipt_number}&PH={phone_number}"
        logger.info("[CBEBirr] Fetching PDF from: %s", url)

        async with get_async_client(timeout=30.0, proxies=proxies) as client:
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
            return TransactionResult(
                success=False,
                provider="cbe_birr",
                error=f"Failed to fetch receipt: HTTP {response.status_code}",
            )

        # Parse PDF
        reader = PdfReader(io.BytesIO(response.content))
        pdf_text = ""
        for page in reader.pages:
            pdf_text += page.extract_text() or ""

        logger.info("[CBEBirr] PDF text extracted (%d characters)", len(pdf_text))

        receipt = _parse_cbe_birr_receipt(pdf_text)
        if not receipt.success:
            logger.error("[CBEBirr] Failed to parse receipt data from PDF")
            return TransactionResult(
                success=False,
                provider="cbe_birr",
                error="Failed to parse receipt data from PDF",
            )

        logger.info("[CBEBirr] Successfully parsed receipt data")
        return receipt

    except Exception as e:
        logger.error("[CBEBirr] Error during verification: %s", e)
        return TransactionResult(
            success=False,
            provider="cbe_birr",
            error=str(e) if str(e) else "Unknown error occurred",
        )


def _parse_cbe_birr_receipt(pdf_text: str) -> TransactionResult:
    """Parse CBE Birr receipt fields from extracted PDF text.

    Uses a robust line-by-line scanner that works with the sparse
    layout produced by pypdf.
    """
    try:
        logger.info("[CBEBirr] Starting PDF text parsing...")

        lines = [ln.strip() for ln in pdf_text.split("\n")]

        # ------------------------------------------------------------------
        # Labels that are guaranteed to be structural, never receipt values.
        # ------------------------------------------------------------------
        known_labels = {
            "Commercial Bank of Ethiopia",
            "VAT Invoice/ Customer Receipt",
            "CBEBirr",
            "Company Address & Other Information",
            "Customer Information",
            "Country:",
            "City:",
            "Address:",
            "Postal code:",
            "SWIFT Code:",
            "Email:",
            "Tel:",
            "Fax:",
            "TIN",
            "VAT Invoice No:",
            "VAT Registration No:",
            "VAT Registration Date:",
            "Customer Name:",
            "Region:",
            "Sub city:",
            "Wereda/kebele:",
            "TIN (TAX ID):",
            "Transaction Information",
            "Debit Account",
            "Credit Account",
            "Receiver Name",
            "Order ID",
            "Transaction Status",
            "Reference",
            "Transaction Details",
            "Receipt Number",
            "Transaction Date",
            "Amount",
            "Paid amount",
            "Service Charge",
            "VAT",
            "Total Paid Amount",
            "Total Amount in word",
            "Payment Reason",
            "Payment Channel",
            "Branch:",
            "Tip",
            "The Bank you can always rely on!",
            f"© {datetime.now().year} Commercial Bank of Ethiopia. All rights reserved",
        }

        def _next_value(start_idx: int) -> str:
            """Return the next non-empty line that is not a known label."""
            j = start_idx
            while j < len(lines):
                val = lines[j].strip()
                if val and val not in known_labels:
                    return val
                j += 1
            return ""

        # ---- individual fields ------------------------------------------------
        customer_name = ""
        debit_account = ""
        credit_account = ""
        receiver_name = ""
        order_id = ""
        transaction_status = ""
        reference = ""
        receipt_number = ""
        transaction_date = ""
        amount = ""
        paid_amount = ""
        service_charge = ""
        vat = ""
        total_paid_amount = ""
        total_amount_in_word = ""
        payment_reason = ""
        payment_channel = ""
        branch = ""
        tip = ""

        i = 0
        while i < len(lines):
            line = lines[i]

            # Customer name appears on the line immediately after "Sub city:"
            if line == "Sub city:":
                customer_name = _next_value(i + 1)

            # Single-line labelled values
            elif line == "Debit Account":
                debit_account = _next_value(i + 1)

            elif line == "Credit Account":
                credit_account = _next_value(i + 1)

            elif line == "Receiver Name":
                receiver_name = _next_value(i + 1)

            elif line == "Order ID":
                order_id = _next_value(i + 1)

            elif line == "Transaction Status":
                transaction_status = _next_value(i + 1)

            elif line == "Reference":
                raw_ref = _next_value(i + 1)
                reference = raw_ref.rstrip(":").strip() if raw_ref else ""

            # Transaction Details block:
            #  Receipt Number   Transaction Date   Amount
            #  <receipt>        <date>             <amount>
            #  <paid>           <service>          <vat>    <total>
            #  Paid amount      Service Charge     VAT      Total Paid Amount
            elif "Receipt Number" in line and "Transaction Date" in line and "Amount" in line:
                j = i + 1
                vals: list[str] = []
                while j < len(lines) and len(vals) < 3:
                    val = lines[j].strip()
                    if val and val not in known_labels:
                        vals.append(val)
                    j += 1
                if len(vals) >= 3:
                    receipt_number = vals[0]
                    transaction_date = vals[1]
                    amount = vals[2]

                # Financial breakdown: 4 consecutive numeric values
                fin_vals: list[str] = []
                while j < len(lines) and len(fin_vals) < 4:
                    val = lines[j].strip()
                    if re.match(r"^[\d.]+$", val):
                        fin_vals.append(val)
                    elif val in known_labels:
                        break
                    j += 1
                if len(fin_vals) >= 4:
                    paid_amount = fin_vals[0]
                    service_charge = fin_vals[1]
                    vat = fin_vals[2]
                    total_paid_amount = fin_vals[3]

            # Bottom block: Total Amount in word, Payment Reason, Payment Channel
            # Each label is followed by a value. The values are collected in order.
            elif line == "Total Amount in word":
                j = i + 1
                vals = []
                while j < len(lines) and len(vals) < 3:
                    val = lines[j].strip()
                    if val and val not in known_labels:
                        vals.append(val)
                    j += 1
                if len(vals) >= 3:
                    total_amount_in_word = vals[0]
                    payment_reason = vals[1]
                    payment_channel = vals[2]

            # Optional fields at the very bottom
            elif line == "Branch:":
                branch = _next_value(i + 1)

            elif line == "Tip":
                tip = _next_value(i + 1)

            i += 1

        # ---- validate we got the essentials ----------------------------------
        if not customer_name and not receipt_number and not amount:
            logger.warning("[CBEBirr] No essential fields found in PDF")
            return TransactionResult(
                success=False,
                provider="cbe_birr",
                error="No essential fields found in PDF",
            )

        # ---- assemble meta dict for optional/variable fields -----------------
        meta: dict[str, str] = {}
        if reference:
            meta["reference"] = reference
        if total_amount_in_word:
            meta["total_amount_in_word"] = total_amount_in_word
        if branch and branch != "0.00":
            meta["branch"] = branch
        if tip and tip != "0.00":
            meta["tip"] = tip
        if paid_amount:
            meta["paid_amount"] = paid_amount

        return TransactionResult(
            success=True,
            provider="cbe_birr",
            payer_name=customer_name or None,
            payer_account=debit_account or None,
            receiver_account=credit_account or None,
            receiver_name=receiver_name or None,
            transaction_reference=order_id or None,
            transaction_status=transaction_status or None,
            receipt_number=receipt_number or None,
            transaction_date=_parse_date(transaction_date) if transaction_date else None,
            amount=_parse_amount(amount) if amount else None,
            service_charge=_parse_amount(service_charge) if service_charge else None,
            vat=_parse_amount(vat) if vat else None,
            total_amount=_parse_amount(total_paid_amount) if total_paid_amount else None,
            narrative=payment_reason or None,
            payment_channel=payment_channel or None,
            meta=meta,
        )

    except Exception as e:
        logger.error("[CBEBirr] Error parsing PDF text: %s", e)
        return TransactionResult(
            success=False,
            provider="cbe_birr",
            error="Error parsing PDF text",
        )
