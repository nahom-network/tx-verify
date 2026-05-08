"""Bank of Abyssinia payment verification service.

Translated from src/services/verifyAbyssinia.ts
"""

import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from tx_verify.utils.http_client import get_async_client
from tx_verify.utils.logger import logger


@dataclass
class AbyssiniaVerifyResult:
    """Bank of Abyssinia verification result.

    Fields that appear on every successful response are typed attributes.
    Fields that vary by transaction type go into ``meta``.
    """

    success: bool
    transaction_reference: str | None = None
    payer_name: str | None = None
    payer_account: str | None = None
    receiver_name: str | None = None
    receiver_account: str | None = None
    transferred_amount: float | None = None
    total_amount_including_vat: float | None = None
    vat: float | None = None
    service_charge: float | None = None
    currency: str | None = None
    transaction_type: str | None = None
    narrative: str | None = None
    transaction_date: datetime | None = None
    transferred_amount_in_words: str | None = None
    address: str | None = None
    phone: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# Body keys that map directly to typed attributes on AbyssiniaVerifyResult.
_KNOWN_KEYS: dict[str, tuple[str, str]] = {
    "Transaction Reference": ("transaction_reference", "data"),
    "Payer's Name": ("payer_name", "data"),
    "Source Account Name": ("payer_name", "data"),
    "Source Account": ("payer_account", "data"),
    "Payer's Account": ("payer_account", "data"),
    "Receiver's Name": ("receiver_name", "data"),
    "Beneficiary Name": ("receiver_name", "data"),
    "Receiver's Account": ("receiver_account", "data"),
    "Beneficiary Account": ("receiver_account", "data"),
    "Transferred Amount": ("transferred_amount", "numeric"),
    "Total Amount including VAT": ("total_amount_including_vat", "numeric"),
    "VAT (15%)": ("vat", "numeric"),
    "Service Charge": ("service_charge", "numeric"),
    "currency": ("currency", "data"),
    "Transaction Type": ("transaction_type", "data"),
    "Narrative": ("narrative", "data"),
    "Transaction Date": ("transaction_date", "date"),
    "Transferred Amount in word": ("transferred_amount_in_words", "data"),
    "Address": ("address", "data"),
    "Tel.": ("phone", "data"),
}


def _parse_amount(value: str) -> float | None:
    """Parse a numeric amount string like '1,000.00' or '0'."""
    cleaned = re.sub(r"[^\d.]", "", value)
    if not cleaned:
        return None
    with suppress(ValueError):
        return float(cleaned)
    return None


def _parse_date(value: str) -> datetime | None:
    """Best-effort parse of Abyssinia transaction date strings."""
    value = value.strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%y %H:%M",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
    )
    for fmt in formats:
        with suppress(ValueError):
            return datetime.strptime(value, fmt)
    return None


def _title_case(s: str) -> str:
    return s.title()


def _build_result(tx: dict[str, Any]) -> AbyssiniaVerifyResult:
    """Map a raw Abyssinia transaction body dict into a typed result."""
    data: dict[str, Any] = {}
    meta: dict[str, Any] = {}

    for raw_key, val in tx.items():
        mapping = _KNOWN_KEYS.get(raw_key)
        if mapping is None:
            # Unknown key -> meta
            meta[raw_key] = val
            continue

        attr_name, attr_type = mapping

        if attr_type == "numeric":
            parsed = _parse_amount(str(val)) if val is not None else None
            if parsed is not None:
                data[attr_name] = parsed
        elif attr_type == "date":
            parsed_date = _parse_date(str(val)) if val is not None else None
            if parsed_date is not None:
                data[attr_name] = parsed_date
        else:
            data[attr_name] = str(val).strip() if val is not None else None

    # Prefer explicit payer / receiver names when both old and new keys exist
    for attr_name in ("payer_name", "receiver_name"):
        if attr_name in data:
            data[attr_name] = _title_case(data[attr_name])

    # Validate essential fields
    tx_ref = data.get("transaction_reference")
    tx_amt = data.get("transferred_amount")
    if tx_ref and tx_amt is not None:
        success = True
        error = None
    else:
        success = False
        error = "Missing essential fields (Transaction Reference or Transferred Amount)."

    return AbyssiniaVerifyResult(
        success=success,
        transaction_reference=tx_ref,
        payer_name=data.get("payer_name"),
        payer_account=data.get("payer_account"),
        receiver_name=data.get("receiver_name"),
        receiver_account=data.get("receiver_account"),
        transferred_amount=tx_amt,
        total_amount_including_vat=data.get("total_amount_including_vat"),
        vat=data.get("vat"),
        service_charge=data.get("service_charge"),
        currency=data.get("currency"),
        transaction_type=data.get("transaction_type"),
        narrative=data.get("narrative"),
        transaction_date=data.get("transaction_date"),
        transferred_amount_in_words=data.get("transferred_amount_in_words"),
        address=data.get("address"),
        phone=data.get("phone"),
        meta=meta,
        error=error,
    )


async def verify_abyssinia(
    reference: str, suffix: str = "", *, proxies: str | dict[str, str] | None = None
) -> AbyssiniaVerifyResult:
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

        async with get_async_client(timeout=30.0, proxies=proxies) as client:
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
            return AbyssiniaVerifyResult(
                success=False, error="Invalid response structure from Abyssinia API"
            )

        if json_data["header"].get("status") != "success":
            status = json_data["header"].get("status")
            logger.error("\u274c API returned error status: %s", status)
            return AbyssiniaVerifyResult(
                success=False, error=f"API returned error status: {status}"
            )

        if len(json_data["body"]) == 0:
            logger.error("\u274c No transaction data found in response body")
            return AbyssiniaVerifyResult(
                success=False, error="No transaction data found in response body"
            )

        tx = json_data["body"][0]
        logger.debug("\U0001f4cb Raw transaction data from API: %s", tx)

        result = _build_result(tx)

        logger.info(
            "\u2705 Successfully parsed Abyssinia receipt for reference: %s",
            result.transaction_reference,
        )

        return result

    except httpx.HTTPError as e:
        logger.error("\u274c HTTP Error fetching Abyssinia receipt: %s", str(e))
        return AbyssiniaVerifyResult(
            success=False, error="Failed to verify Abyssinia transaction"
        )
    except Exception as e:
        logger.error("\u274c Unexpected error in verify_abyssinia: %s", str(e))
        return AbyssiniaVerifyResult(
            success=False, error="Failed to verify Abyssinia transaction"
        )
