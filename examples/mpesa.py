"""Example: M-Pesa (Ethiopia) transaction verification.

M-Pesa references are typically 10-character alphanumeric codes.
The verifier hits the Safaricom primary API.
"""

import asyncio

from tx_verify import verify_mpesa


async def main() -> None:
    # Replace with a real M-Pesa transaction ID
    transaction_id = "UE20VGABCDE"

    result = await verify_mpesa(transaction_id)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ M-Pesa receipt verified:")
    print(f"  Payer Name        : {result.payer_name}")
    print(f"  Payer Account     : {result.payer_account}")
    print(f"  Transaction ID    : {result.transaction_reference}")
    print(f"  Transaction Date  : {result.transaction_date}")
    print(f"  Amount            : {result.amount}")
    print(f"  Transaction Type  : {result.transaction_type}")
    print(f"  Reference         : {result.receipt_number}")
    print(f"  Meta              : {result.meta}")


if __name__ == "__main__":
    asyncio.run(main())
