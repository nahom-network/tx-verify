"""Example: Telebirr payment verification.

Telebirr receipts are 10-character alphanumeric codes (e.g., "CE12345678").
The verifier fetches the receipt HTML from Ethio Telecom and parses it.
"""

import asyncio

from tx_verify import verify_telebirr


async def main() -> None:
    # Replace with a real Telebirr reference number
    reference = "CHC15IZ2VZ"

    result = await verify_telebirr(reference)

    if not result.success:
        print("❌ Could not verify the Telebirr transaction.")
        return

    print("✅ Telebirr receipt found:")
    print(f"  Payer Name        : {result.payer_name}")
    print(f"  Payer Account     : {result.payer_account}")
    print(f"  Receiver Name     : {result.receiver_name}")
    print(f"  Receiver Account  : {result.receiver_account}")
    print(f"  Amount            : {result.amount}")
    print(f"  Service Charge    : {result.service_charge}")
    print(f"  Total Paid        : {result.total_amount}")
    print(f"  Receipt No        : {result.receipt_number}")
    print(f"  Payment Date      : {result.transaction_date}")
    print(f"  Transaction Status: {result.transaction_status}")
    print(f"  META              : {result.meta}")


if __name__ == "__main__":
    asyncio.run(main())
