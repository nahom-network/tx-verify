"""Example: Telebirr payment verification.

Telebirr receipts are 10-character alphanumeric codes (e.g., "CE12345678").
The verifier fetches the receipt HTML from Ethio Telecom and parses it.
"""

import asyncio
from dataclasses import asdict

from tx_verify import verify_telebirr


async def main() -> None:
    # Replace with a real Telebirr reference number
    reference = "CGA6FL0MI0"

    result = await verify_telebirr(reference)

    if not result.success:
        print("❌ Could not verify the Telebirr transaction.")
        return

    print("✅ Telebirr receipt found:")
    for key, value in asdict(result).items():
        print(f"   {' '.join(key.capitalize().split('_'))}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
