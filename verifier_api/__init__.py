"""Payment Verification API - Python library for verifying Ethiopian payment transactions."""

from verifier_api.services.verify_abyssinia import AbyssiniaReceipt, verify_abyssinia
from verifier_api.services.verify_cbe import VerifyResult, verify_cbe
from verifier_api.services.verify_cbe_birr import CBEBirrReceipt, verify_cbe_birr
from verifier_api.services.verify_dashen import DashenVerifyResult, verify_dashen
from verifier_api.services.verify_image import verify_image
from verifier_api.services.verify_mpesa import MpesaVerifyResult, verify_mpesa
from verifier_api.services.verify_telebirr import (
    TelebirrReceipt,
    TelebirrVerificationError,
    verify_telebirr,
)
from verifier_api.services.verify_universal import verify_universal
from verifier_api.utils.error_handler import AppError, ErrorType
from verifier_api.utils.logger import logger

__version__ = "0.1.0"

__all__ = [
    "verify_cbe",
    "verify_telebirr",
    "verify_dashen",
    "verify_abyssinia",
    "verify_cbe_birr",
    "verify_mpesa",
    "verify_image",
    "verify_universal",
    "VerifyResult",
    "TelebirrReceipt",
    "TelebirrVerificationError",
    "DashenVerifyResult",
    "AbyssiniaReceipt",
    "CBEBirrReceipt",
    "MpesaVerifyResult",
    "AppError",
    "ErrorType",
    "logger",
]
