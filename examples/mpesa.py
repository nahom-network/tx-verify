"""Example: M-Pesa (Ethiopia) transaction verification.

M-Pesa references are typically 10-character alphanumeric codes.
The verifier tries the primary Safaricom API first, then falls back to
a proxy server if needed.  Set MPESA_PROXY_KEY env var for fallback.
"""
import asyncio
import os

from tx_verify import verify_mpesa


async def main() -> None:
    # Replace with a real M-Pesa transaction ID
    transaction_id = "UE20VG1GS8"

    # Optional: configure a proxy key for fallback access
    # os.environ["MPESA_PROXY_KEY"] = "your-proxy-key-here"

    result = await verify_mpesa(transaction_id)

    if not result.success:
        print(f"❌ Verification failed: {result.error}")
        return

    print("✅ M-Pesa receipt verified:")
    print(f"  Payer Name        : {result.payer_name}")
    print(f"  Payer Account     : {result.payer_account}")
    print(f"  Receiver Name     : {result.receiver_name}")
    print(f"  Receiver Account  : {result.receiver_account}")
    print(f"  Transaction ID    : {result.transaction_id}")
    print(f"  Receipt No        : {result.receipt_no}")
    print(f"  Payment Date      : {result.payment_date}")
    print(f"  Amount            : {result.amount} ETB")
    print(f"  Service Fee       : {result.service_fee}")
    print(f"  VAT               : {result.vat}")


if __name__ == "__main__":
    asyncio.run(main())
