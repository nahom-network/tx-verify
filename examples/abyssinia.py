"""Example: Bank of Abyssinia receipt verification.

Abyssinia references start with "FT" and are 12 characters long.
You must provide the last 5 digits of the account number as a suffix.
The bank exposes a JSON API that returns structured transaction data.
"""

import asyncio

from tx_verify import verify_abyssinia


async def main() -> None:
    # Replace with real values
    reference = "FT23062669JJ"
    suffix = "90172"  # last 5 digits of the account

    result = await verify_abyssinia(reference, suffix)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ Bank of Abyssinia receipt verified:")
    print(f"  Payer            : {result.payer}")
    print(f"  Payer Account    : {result.payer_account}")
    print(f"  Receiver         : {result.receiver}")
    print(f"  Receiver Account : {result.receiver_account}")
    print(f"  Amount           : {result.amount} ETB")
    print(f"  Date             : {result.date}")
    print(f"  Reference        : {result.reference}")
    print(f"  Reason / Service : {result.reason}")


if __name__ == "__main__":
    asyncio.run(main())
