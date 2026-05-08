"""Example: CBE (Commercial Bank of Ethiopia) receipt verification.

CBE references start with "FT" and are 12 characters long (e.g., "FT23062669JJ").
You must also provide the last 8 digits of the account number as a suffix.
The bank returns a PDF receipt that is parsed automatically.
"""

import asyncio
from dataclasses import asdict

from tx_verify import verify_cbe


async def main() -> None:
    # Replace with real values from the CBE receipt
    reference = "FT26125ZD8XR84722688"
    # account_suffix = "12345678"  # last 8 digits of the account

    result = await verify_cbe(reference)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ CBE receipt verified:")
    for key, value in asdict(result).items():
        print(f"   {' '.join(key.capitalize().split('_'))}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
