"""Example: CBE Birr (CBE mobile wallet) receipt verification.

CBE Birr receipts are 10-character alphanumeric codes.
You need the receipt number AND the phone number linked to the wallet
(in national format starting with 09, e.g., "0911234567").
The service fetches a PDF receipt and extracts transaction details.
"""

import asyncio
from dataclasses import asdict

from tx_verify import verify_cbe_birr


async def main() -> None:
    # Replace with real values
    receipt_number = "DE321C747K7"
    phone_number = "0912345678"

    result = await verify_cbe_birr(receipt_number, phone_number)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ CBE Birr receipt verified:")
    for key, value in asdict(result).items():
        print(f"   {' '.join(key.capitalize().split('_'))}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
