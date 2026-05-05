"""Example: Telebirr payment verification.

Telebirr receipts are 10-character alphanumeric codes (e.g., "CE12345678").
The verifier fetches the receipt HTML from Ethio Telecom and parses it.
"""
import asyncio

from tx_verify import verify_telebirr


async def main() -> None:
    # Replace with a real Telebirr reference number
    reference = "CE12345678"

    receipt = await verify_telebirr(reference)

    if receipt is None:
        print("❌ Could not verify the Telebirr transaction.")
        return

    print("✅ Telebirr receipt found:")
    print(f"  Payer Name        : {receipt.payer_name}")
    print(f"  Payer Telebirr No : {receipt.payer_telebirr_no}")
    print(f"  Credited Party    : {receipt.credited_party_name}")
    print(f"  Account No        : {receipt.credited_party_account_no}")
    print(f"  Settled Amount    : {receipt.settled_amount}")
    print(f"  Service Fee       : {receipt.service_fee}")
    print(f"  Total Paid        : {receipt.total_paid_amount}")
    print(f"  Receipt No        : {receipt.receipt_no}")
    print(f"  Payment Date      : {receipt.payment_date}")
    print(f"  Transaction Status: {receipt.transaction_status}")


if __name__ == "__main__":
    asyncio.run(main())
