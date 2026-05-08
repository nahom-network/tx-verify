"""Payment Verification API - Python library for verifying Ethiopian payment transactions."""

from tx_verify.models import TransactionResult
from tx_verify.services.verify_abyssinia import verify_abyssinia
from tx_verify.services.verify_cbe import verify_cbe
from tx_verify.services.verify_cbe_birr import verify_cbe_birr
from tx_verify.services.verify_dashen import verify_dashen
from tx_verify.services.verify_image import verify_image
from tx_verify.services.verify_mpesa import verify_mpesa
from tx_verify.services.verify_telebirr import (
    TelebirrVerificationError,
    verify_telebirr,
)
from tx_verify.services.verify_universal import verify_universal
from tx_verify.utils.error_handler import AppError, ErrorType
from tx_verify.utils.logger import logger

__version__ = "1.0.2"

__all__ = [
    "verify_cbe",
    "verify_telebirr",
    "verify_dashen",
    "verify_abyssinia",
    "verify_cbe_birr",
    "verify_mpesa",
    "verify_image",
    "verify_universal",
    "TransactionResult",
    "TelebirrVerificationError",
    "AppError",
    "ErrorType",
    "logger",
]
