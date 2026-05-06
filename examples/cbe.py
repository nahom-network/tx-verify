"""Example: CBE (Commercial Bank of Ethiopia) receipt verification.

CBE references start with "FT" and are 12 characters long (e.g., "FT23062669JJ").
You must also provide the last 8 digits of the account number as a suffix.
The bank returns a PDF receipt that is parsed automatically.
"""

import asyncio

from tx_verify import verify_cbe


async def main() -> None:
    # Replace with real values from the CBE receipt
    reference = "FT23062669JJ"
    account_suffix = "12345678"  # last 8 digits of the account

    result = await verify_cbe(reference, account_suffix)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ CBE receipt verified:")
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
