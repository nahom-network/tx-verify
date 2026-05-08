"""Universal payment verification endpoint logic.

Translated from src/routes/verifyUniversalRoute.ts
The TS version lived in a route handler; here it's a pure service function.
"""

import re

from tx_verify.models import TransactionResult
from tx_verify.services.verify_abyssinia import verify_abyssinia
from tx_verify.services.verify_cbe import verify_cbe
from tx_verify.services.verify_cbe_birr import verify_cbe_birr
from tx_verify.services.verify_dashen import verify_dashen
from tx_verify.services.verify_telebirr import (
    TelebirrVerificationError,
    verify_telebirr,
)
from tx_verify.utils.logger import logger


async def verify_universal(
    reference: str,
    suffix: str | None = None,
    phone_number: str | None = None,
    *,
    proxies: str | dict[str, str] | None = None,
) -> TransactionResult:
    """Route a verification request to the correct provider based on reference format.

    Args:
        reference: The transaction reference string.
        suffix: Account suffix (for CBE / Abyssinia).
        phone_number: Phone number (for CBE Birr).
    """
    if not reference or not isinstance(reference, str):
        return TransactionResult(
            success=False,
            error="Missing or invalid reference.",
        )

    trimmed = reference.strip()
    length = len(trimmed)

    if length not in (10, 12, 16):
        return TransactionResult(
            success=False,
            error="Invalid reference length for automatic sorting.",
        )

    try:
        # --- DASHEN BANK ---
        if length == 16 and re.match(r"^\d{3}", trimmed):
            if suffix or phone_number:
                return TransactionResult(
                    success=False,
                    error="Dashen bank verification expects only a reference number. Exclude suffix and phoneNumber.",
                )
            return await verify_dashen(trimmed, proxies=proxies)

        # --- CBE & ABYSSINIA ---
        if length == 12 and trimmed.upper().startswith("FT"):
            if not suffix:
                return TransactionResult(
                    success=False,
                    error='Transactions starting with "FT" require a suffix (8 digits for CBE, 5 digits for Abyssinia).',
                )
            trimmed_suffix = suffix.strip()
            if len(trimmed_suffix) == 8:
                return await verify_cbe(trimmed, trimmed_suffix, proxies=proxies)
            elif len(trimmed_suffix) == 5:
                return await verify_abyssinia(trimmed, trimmed_suffix, proxies=proxies)
            else:
                return TransactionResult(
                    success=False,
                    error="Suffix must be exactly 8 digits (CBE) or 5 digits (Abyssinia).",
                )

        # --- CBE BIRR & TELEBIRR ---
        if length == 10:
            if not re.match(r"^[A-Za-z0-9]{10}$", trimmed):
                return TransactionResult(
                    success=False,
                    error="10-character reference must be alphanumeric.",
                )
            if suffix:
                return TransactionResult(
                    success=False,
                    error="Suffix is not expected for 10-character transactions.",
                )

            if phone_number:
                trimmed_phone = phone_number.strip()
                if not re.match(r"^09\d{8}$", trimmed_phone):
                    return TransactionResult(
                        success=False,
                        error="Invalid phone number format. Must be a local Ethiopian number starting with 09 and 10 digits long.",
                    )
                return await verify_cbe_birr(trimmed, trimmed_phone, proxies=proxies)
            else:
                return await verify_telebirr(trimmed, proxies=proxies)

        return TransactionResult(
            success=False,
            error="The provided reference does not match any recognized provider format for automatic sorting.",
        )

    except TelebirrVerificationError as e:
        return TransactionResult(success=False, error=str(e), meta={"details": e.details})
    except Exception as e:
        logger.error("💥 Universal verification failed: %s", e)
        return TransactionResult(
            success=False,
            error="Server error verifying payment through the universal endpoint.",
        )
