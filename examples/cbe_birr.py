"""Example: CBE Birr (CBE mobile wallet) receipt verification.

CBE Birr receipts are 10-character alphanumeric codes.
You need the receipt number AND the phone number linked to the wallet
(in national format starting with 09, e.g., "0911234567").
The service fetches a PDF receipt and extracts transaction details.
"""
import asyncio

from tx_verify import verify_cbe_birr


async def main() -> None:
    # Replace with real values
    receipt_number = "AB1234CD56"
    phone_number = "0911234567"

    result = await verify_cbe_birr(receipt_number, phone_number)

    # CBEBirrError is a dataclass with .success and .error
    if hasattr(result, "success") and not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    receipt = result
    print("✅ CBE Birr receipt verified:")
    print(f"  Customer Name    : {receipt.customer_name}")
    print(f"  Receiver Name    : {receipt.receiver_name}")
    print(f"  Order ID         : {receipt.order_id}")
    print(f"  Reference        : {receipt.reference}")
    print(f"  Receipt Number   : {receipt.receipt_number}")
    print(f"  Transaction Date : {receipt.transaction_date}")
    print(f"  Amount           : {receipt.amount}")
    print(f"  Paid Amount      : {receipt.paid_amount}")
    print(f"  Service Charge   : {receipt.service_charge}")
    print(f"  VAT              : {receipt.vat}")
    print(f"  Total Paid       : {receipt.total_paid_amount}")
    print(f"  Payment Reason   : {receipt.payment_reason}")
    print(f"  Payment Channel  : {receipt.payment_channel}")


if __name__ == "__main__":
    asyncio.run(main())
