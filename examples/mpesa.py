"""Example: M-Pesa (Ethiopia) transaction verification.

M-Pesa references are typically 10-character alphanumeric codes.
The verifier hits the Safaricom primary API.
"""

import asyncio
from dataclasses import asdict

from tx_verify import verify_mpesa


async def main() -> None:
    # Replace with a real M-Pesa transaction ID
    transaction_id = "UE20VGABCDE"

    result = await verify_mpesa(transaction_id)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ M-Pesa receipt verified:")
    for key, value in asdict(result).items():
        print(f"   {' '.join(key.capitalize().split('_'))}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
