"""Image-based payment receipt verification using Mistral Vision AI.

Translated from src/services/verifyImage.ts
"""

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

from tx_verify.services.verify_cbe import verify_cbe
from tx_verify.services.verify_telebirr import verify_telebirr
from tx_verify.utils.logger import logger


@dataclass
class ImageVerifyResult:
    """Result of image-based verification."""

    # When auto_verify is False, these guide the caller to the right endpoint
    type: str | None = None  # "telebirr" or "cbe"
    reference: str | None = None
    forward_to: str | None = None
    account_suffix: str | None = None

    # When auto_verify is True and verification succeeds
    verified: bool | None = None
    details: Any = None

    # Error info
    error: str | None = None
    error_details: str | None = None


async def verify_image(
    image_bytes: bytes,
    auto_verify: bool = False,
    account_suffix: str | None = None,
    mime_type: str = "image/jpeg",
    *,
    proxies: str | dict[str, str] | None = None,
) -> ImageVerifyResult:
    """Analyse a payment receipt image using Mistral Vision and optionally auto-verify.

    Args:
        image_bytes: Raw bytes of the uploaded image.
        auto_verify: If True, attempt to verify the detected transaction automatically.
        account_suffix: Required for CBE auto-verification.
        mime_type: MIME type of the image (default image/jpeg).
    """
    try:
        # Lazy import to avoid hard dependency on mistralai when not needed
        from mistralai import Mistral  # type: ignore[import-untyped]
    except ImportError:
        return ImageVerifyResult(
            error="mistralai package is not installed. Install it to use image verification."
        )

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        return ImageVerifyResult(error="MISTRAL_API_KEY environment variable is not set.")

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "You are a payment receipt analyzer. Based on the uploaded image, determine:\n"
        "- If the receipt was issued by Telebirr or the Commercial Bank of Ethiopia (CBE).\n"
        "- If it's a CBE receipt, extract the transaction ID (usually starts with 'FT').\n"
        "- If it's a Telebirr receipt, extract the transaction number (usually starts with 'CE').\n\n"
        "Rules:\n"
        '- CBE receipts usually include a purple header with the title "Commercial Bank of Ethiopia" '
        "and a structured table.\n"
        "- Telebirr receipts are typically green with a large minus sign before the amount.\n"
        "- CBE receipts may mention Telebirr (as the receiver) but are still CBE receipts.\n\n"
        "Return this JSON format exactly:\n"
        '{\n  "type": "telebirr" | "cbe",\n  "transaction_id"?: "FTxxxx" (if CBE),\n'
        '  "transaction_number"?: "CExxxx" (if Telebirr)\n}'
    )

    logger.info("Sending image to Mistral Vision...")

    try:
        client = Mistral(api_key=api_key)
        chat_response = client.chat.complete(
            model="pixtral-12b",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": f"data:{mime_type};base64,{b64_image}",
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
        )

        content = chat_response.choices[0].message.content  # type: ignore[union-attr]
        if not content or not isinstance(content, str):
            logger.error("Invalid Mistral response")
            return ImageVerifyResult(error="Invalid OCR response")

        result: dict[str, Any] = json.loads(content)
        logger.info("OCR Result: %s", result)

    except Exception as e:
        logger.error("Mistral API error: %s", e)
        return ImageVerifyResult(error="Something went wrong processing the image.")

    # --- Telebirr ---
    if result.get("type") == "telebirr" and result.get("transaction_number"):
        ref = result["transaction_number"]
        if auto_verify:
            try:
                data = await verify_telebirr(ref, proxies=proxies)
                return ImageVerifyResult(
                    verified=True, type="telebirr", reference=ref, details=data
                )
            except Exception as ve:
                logger.error("Telebirr verification failed: %s", ve)
                err_name = getattr(ve, "name", "")
                if err_name == "TelebirrVerificationError":
                    return ImageVerifyResult(
                        error=str(ve),
                        error_details=getattr(ve, "details", None),
                    )
                return ImageVerifyResult(error="Verification failed for Telebirr")
        else:
            return ImageVerifyResult(type="telebirr", reference=ref, forward_to="/verify-telebirr")

    # --- CBE ---
    if result.get("type") == "cbe" and result.get("transaction_id"):
        ref = result["transaction_id"]
        if not auto_verify:
            return ImageVerifyResult(
                type="cbe",
                reference=ref,
                forward_to="/verify-cbe",
                account_suffix="required_from_user",
            )
        if not account_suffix:
            return ImageVerifyResult(
                error="Account suffix is required for CBE verification in autoVerify mode"
            )
        try:
            data = await verify_cbe(ref, account_suffix, proxies=proxies)
            return ImageVerifyResult(verified=True, type="cbe", reference=ref, details=data)
        except Exception as ve:
            logger.error("CBE verification failed: %s", ve)
            return ImageVerifyResult(error="Verification failed for CBE")

    return ImageVerifyResult(error="Unknown or unrecognized receipt type")
