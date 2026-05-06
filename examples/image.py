"""Example: Image-based receipt verification using Mistral Vision AI.

This example shows how to analyse a receipt image and optionally
auto-verify the detected transaction.  Requires a Mistral API key.
"""

import asyncio
import os

from tx_verify import verify_image


async def main() -> None:
    # Set your Mistral API key
    os.environ["MISTRAL_API_KEY"] = "your-mistral-api-key"

    # Load a receipt image (JPEG or PNG)
    image_path = "/path/to/receipt.jpg"
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # 1️⃣  Detect only (do NOT auto-verify)
    detection = await verify_image(image_bytes, auto_verify=False)
    if detection.error:
        print(f"❌ Detection failed: {detection.error}")
        return

    print("🔍 Image analysed:")
    print(f"  Detected type  : {detection.type}")
    print(f"  Reference      : {detection.reference}")
    print(f"  Forward to     : {detection.forward_to}")
    if detection.account_suffix:
        print(f"  Account suffix : {detection.account_suffix}")

    # 2️⃣  Auto-verify (requires account_suffix for CBE)
    verification = await verify_image(
        image_bytes,
        auto_verify=True,
        account_suffix="12345678",  # required for CBE; ignored for Telebirr
    )

    if verification.error:
        print(f"❌ Auto-verification failed: {verification.error}")
        return

    if verification.verified:
        print("✅ Auto-verification succeeded:")
        print(f"  Provider  : {verification.type}")
        print(f"  Reference : {verification.reference}")
        print(f"  Details   : {verification.details}")


if __name__ == "__main__":
    asyncio.run(main())
