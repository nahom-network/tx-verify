"""Bank of Abyssinia payment verification service.

Translated from src/services/verifyAbyssinia.ts
"""

from dataclasses import dataclass
from datetime import datetime

import httpx

from tx_verify.services.verify_cbe import VerifyResult
from tx_verify.utils.logger import logger


@dataclass
class AbyssiniaReceipt:
    """Raw receipt fields returned by the Abyssinia API."""

    source_account_name: str = ""
    vat: str = ""
    transferred_amount_in_word: str = ""
    address: str = ""
    transaction_type: str = ""
    service_charge: str = ""
    source_account: str = ""
    payment_reference: str = ""
    tel: str = ""
    payer_name: str = ""
    narrative: str = ""
    transferred_amount: str = ""
    transaction_reference: str = ""
    transaction_date: str = ""
    total_amount_including_vat: str = ""


async def verify_abyssinia(reference: str, suffix: str = "") -> VerifyResult:
    """Verify an Abyssinia bank transaction via their public API.

    Args:
        reference: Transaction reference (e.g. "FT23062669JJ")
        suffix: Last 5 digits of the user's account (e.g. "90172")
    """
    try:
        logger.info(
            "\U0001f3e6 Starting Abyssinia verification for reference: %s with suffix: %s",
            reference,
            suffix,
        )

        api_url = (
            f"https://cs.bankofabyssinia.com/api/onlineSlip/getDetails/?id={reference}{suffix}"
        )
        logger.info("\U0001f4e1 Fetching from URL: %s", api_url)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                api_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/91.0.4472.124 Safari/537.36"
                    ),
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )

        logger.info("\u2705 Successfully fetched response with status: %s", response.status_code)

        json_data = response.json()

        # Validate response structure
        if (
            not json_data
            or "header" not in json_data
            or "body" not in json_data
            or not isinstance(json_data["body"], list)
        ):
            logger.error("\u274c Invalid response structure from Abyssinia API")
            return VerifyResult(
                success=False, error="Invalid response structure from Abyssinia API"
            )

        if json_data["header"].get("status") != "success":
            status = json_data["header"].get("status")
            logger.error("\u274c API returned error status: %s", status)
            return VerifyResult(success=False, error=f"API returned error status: {status}")

        if len(json_data["body"]) == 0:
            logger.error("\u274c No transaction data found in response body")
            return VerifyResult(success=False, error="No transaction data found in response body")

        tx = json_data["body"][0]
        logger.debug("\U0001f4cb Raw transaction data from API: %s", tx)

        # Extract and parse amount
        transferred_amount_str = (
            tx.get("Transferred Amount") or tx.get("Total Amount including VAT") or ""
        )
        amount: float | None = None
        if transferred_amount_str:
            import re

            cleaned = re.sub(r"[^\d.]", "", transferred_amount_str)
            if cleaned:
                amount = float(cleaned)

        transaction_date_str = tx.get("Transaction Date") or ""
        date: datetime | None = None
        if transaction_date_str:
            try:
                date = datetime.fromisoformat(transaction_date_str)
            except ValueError:
                # Try other common formats
                for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
                    try:
                        date = datetime.strptime(transaction_date_str, fmt)
                        break
                    except ValueError:
                        continue

        result = VerifyResult(
            success=True,
            payer=tx.get("Payer's Name") or tx.get("Source Account Name") or None,
            payer_account=tx.get("Source Account") or tx.get("Payer's Account") or None,
            receiver=tx.get("Receiver's Name") or tx.get("Beneficiary Name") or None,
            receiver_account=tx.get("Receiver's Account") or tx.get("Beneficiary Account") or None,
            amount=amount,
            date=date,
            reference=tx.get("Transaction Reference") or tx.get("Payment Reference") or None,
            reason=tx.get("Narrative") or tx.get("Transaction Type") or None,
        )

        logger.info(
            "\u2705 Successfully parsed Abyssinia receipt for reference: %s", result.reference
        )

        # Validate essential fields
        if not result.reference or not result.amount:
            logger.error("\u274c Missing essential fields in transaction data")
            return VerifyResult(success=False, error="Missing essential fields in transaction data")

        return result

    except httpx.HTTPError as e:
        logger.error("\u274c HTTP Error fetching Abyssinia receipt: %s", str(e))
        return VerifyResult(success=False, error="Failed to verify Abyssinia transaction")
    except Exception as e:
        logger.error("\u274c Unexpected error in verify_abyssinia: %s", str(e))
        return VerifyResult(success=False, error="Failed to verify Abyssinia transaction")
