"""Universal payment verification endpoint logic.

Translated from src/routes/verifyUniversalRoute.ts
The TS version lived in a route handler; here it's a pure service function.
"""

import re
from dataclasses import dataclass
from typing import Any

from tx_verify.services.verify_abyssinia import verify_abyssinia
from tx_verify.services.verify_cbe import verify_cbe
from tx_verify.services.verify_cbe_birr import CBEBirrError, verify_cbe_birr
from tx_verify.services.verify_dashen import verify_dashen
from tx_verify.services.verify_telebirr import (
    TelebirrVerificationError,
    verify_telebirr,
)
from tx_verify.utils.logger import logger


@dataclass
class UniversalResult:
    """Unified result from the universal verification endpoint."""

    success: bool
    data: Any = None
    error: str | None = None
    details: str | None = None


async def verify_universal(
    reference: str,
    suffix: str | None = None,
    phone_number: str | None = None,
    *,
    proxies: str | dict[str, str] | None = None,
) -> UniversalResult:
    """Route a verification request to the correct provider based on reference format.

    Args:
        reference: The transaction reference string.
        suffix: Account suffix (for CBE / Abyssinia).
        phone_number: Phone number (for CBE Birr).
        api_key: API key header value (for CBE Birr).
    """
    if not reference or not isinstance(reference, str):
        return UniversalResult(success=False, error="Missing or invalid reference.")

    trimmed = reference.strip()
    length = len(trimmed)

    if length not in (10, 12, 16):
        return UniversalResult(
            success=False, error="Invalid reference length for automatic sorting."
        )

    try:
        # --- DASHEN BANK ---
        if length == 16 and re.match(r"^\d{3}", trimmed):
            if suffix or phone_number:
                return UniversalResult(
                    success=False,
                    error="Dashen bank verification expects only a reference number. Exclude suffix and phoneNumber.",
                )
            dashen_result = await verify_dashen(trimmed, proxies=proxies)
            return UniversalResult(success=dashen_result.success, data=dashen_result, error=dashen_result.error)

        # --- CBE & ABYSSINIA ---
        if length == 12 and trimmed.upper().startswith("FT"):
            if not suffix:
                return UniversalResult(
                    success=False,
                    error='Transactions starting with "FT" require a suffix (8 digits for CBE, 5 digits for Abyssinia).',
                )
            trimmed_suffix = suffix.strip()
            if len(trimmed_suffix) == 8:
                cbe_result = await verify_cbe(trimmed, trimmed_suffix, proxies=proxies)
                return UniversalResult(success=cbe_result.success, data=cbe_result, error=cbe_result.error)
            elif len(trimmed_suffix) == 5:
                aby_result = await verify_abyssinia(trimmed, trimmed_suffix, proxies=proxies)
                return UniversalResult(success=aby_result.success, data=aby_result, error=aby_result.error)
            else:
                return UniversalResult(
                    success=False,
                    error="Suffix must be exactly 8 digits (CBE) or 5 digits (Abyssinia).",
                )

        # --- CBE BIRR & TELEBIRR ---
        if length == 10:
            if not re.match(r"^[A-Za-z0-9]{10}$", trimmed):
                return UniversalResult(
                    success=False,
                    error="10-character reference must be alphanumeric.",
                )
            if suffix:
                return UniversalResult(
                    success=False,
                    error="Suffix is not expected for 10-character transactions.",
                )

            if phone_number:
                trimmed_phone = phone_number.strip()
                if not re.match(r"^09\d{8}$", trimmed_phone):
                    return UniversalResult(
                        success=False,
                        error="Invalid phone number format. Must be a local Ethiopian number starting with 09 and 10 digits long.",
                    )
                cbe_birr_result = await verify_cbe_birr(trimmed, trimmed_phone, proxies=proxies)
                if isinstance(cbe_birr_result, CBEBirrError):
                    return UniversalResult(success=False, error=cbe_birr_result.error)
                return UniversalResult(success=True, data=cbe_birr_result)
            else:
                telebirr_result = await verify_telebirr(trimmed, proxies=proxies)
                if not telebirr_result:
                    return UniversalResult(
                        success=False,
                        error="Receipt not found or could not be processed.",
                    )
                return UniversalResult(success=True, data=telebirr_result)

        return UniversalResult(
            success=False,
            error="The provided reference does not match any recognized provider format for automatic sorting.",
        )

    except TelebirrVerificationError as e:
        return UniversalResult(success=False, error=str(e), details=e.details)
    except Exception as e:
        logger.error("\U0001f4a5 Universal verification failed: %s", e)
        return UniversalResult(
            success=False,
            error="Server error verifying payment through the universal endpoint.",
        )
