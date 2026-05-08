"""Example: Bank of Abyssinia receipt verification.

Abyssinia references start with "FT" and are 12 characters long.
You must provide the last 5 digits of the account number as a suffix.
The bank exposes a JSON API that returns structured transaction data.
"""

import asyncio

from tx_verify import verify_abyssinia


async def main() -> None:
    # Replace with real values
    reference = "FT260903SZJW02117"
    suffix = "90172"  # last 5 digits of the account

    result = await verify_abyssinia(reference, suffix)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ Bank of Abyssinia receipt verified:")
    print(f"  Transaction Reference : {result.transaction_reference}")
    print(f"  Payer Name          : {result.payer_name}")
    print(f"  Payer Account       : {result.payer_account}")
    print(f"  Receiver Name       : {result.receiver_name}")
    print(f"  Receiver Account    : {result.receiver_account}")
    print(f"  Transferred Amount  : {result.amount} {result.currency}")
    print(f"  Total Amount (incl. VAT) : {result.total_amount}")
    print(f"  VAT (15%)           : {result.vat}")
    print(f"  Service Charge      : {result.service_charge}")
    print(f"  Transaction Date    : {result.transaction_date}")
    print(f"  Transaction Type    : {result.transaction_type}")
    print(f"  Narrative           : {result.narrative}")
    print(f"  Amount in Words     : {result.amount_in_words}")
    print(f"  META                : {result.meta}")


if __name__ == "__main__":
    asyncio.run(main())
