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
    receipt_number = "DE321C747J2"
    phone_number = "0910544594"

    result = await verify_cbe_birr(receipt_number, phone_number)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ CBE Birr receipt verified:")
    print(f"  Customer Name    : {result.payer_name}")
    print(f"  Receiver Name    : {result.receiver_name}")
    print(f"  Order ID         : {result.transaction_reference}")
    print(f"  Receipt Number   : {result.receipt_number}")
    print(f"  Transaction Date : {result.transaction_date}")
    print(f"  Amount           : {result.amount}")
    print(f"  Service Charge   : {result.service_charge}")
    print(f"  VAT              : {result.vat}")
    print(f"  Total Paid       : {result.total_amount}")
    print(f"  Payment Reason   : {result.narrative}")
    print(f"  Payment Channel  : {result.payment_channel}")


if __name__ == "__main__":
    asyncio.run(main())
