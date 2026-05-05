"""Example: Dashen Bank receipt verification.

Dashen Bank references are 16-digit numbers starting with 3 digits
(e.g., "1234567890123456").  The verifier fetches a PDF receipt with
built-in retry logic (up to 5 attempts).
"""
import asyncio

from tx_verify import verify_dashen


async def main() -> None:
    # Replace with a real Dashen transaction reference
    reference = "1234567890123456"

    result = await verify_dashen(reference)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ Dashen Bank receipt verified:")
    print(f"  Sender Name           : {result.sender_name}")
    print(f"  Sender Account        : {result.sender_account_number}")
    print(f"  Transaction Channel     : {result.transaction_channel}")
    print(f"  Service Type          : {result.service_type}")
    print(f"  Narrative             : {result.narrative}")
    print(f"  Receiver Name         : {result.receiver_name}")
    print(f"  Phone No              : {result.phone_no}")
    print(f"  Institution           : {result.institution_name}")
    print(f"  Transaction Reference : {result.transaction_reference}")
    print(f"  Transfer Reference    : {result.transfer_reference}")
    print(f"  Transaction Date      : {result.transaction_date}")
    print(f"  Transaction Amount    : {result.transaction_amount} ETB")
    print(f"  Service Charge        : {result.service_charge}")
    print(f"  Excise Tax            : {result.excise_tax}")
    print(f"  VAT                   : {result.vat}")
    print(f"  Total                 : {result.total} ETB")


if __name__ == "__main__":
    asyncio.run(main())
