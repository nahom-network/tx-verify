"""Example: Dashen Bank receipt verification.

Dashen Bank references are 16-digit numbers starting with 3 digits
(e.g., "1234567890123456").  The verifier fetches a PDF receipt with
built-in retry logic (up to 5 attempts).
"""

import asyncio
from dataclasses import asdict

from tx_verify import verify_dashen


async def main() -> None:
    # Replace with a real Dashen transaction reference
    reference = "641OBTS2518100WH"

    result = await verify_dashen(reference)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ Dashen Bank receipt verified:")
    for key, value in asdict(result).items():
        print(f"   {' '.join(key.capitalize().split('_'))}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
