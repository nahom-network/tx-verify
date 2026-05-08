"""Example: Graceful error handling.

demonstrates catching provider-specific errors and inspecting the
result object to decide what to show the user.
"""

import asyncio

from tx_verify import (
    TelebirrVerificationError,
    TransactionResult,
    verify_cbe,
    verify_telebirr,
    verify_universal,
)


async def main() -> None:
    # --- Telebirr specific error ---
    try:
        result = await verify_telebirr("INVALID_REF")
        if not result.success:
            print("Telebirr: receipt not found")
        else:
            print(f"Telebirr: OK — {result.payer_name}")
    except TelebirrVerificationError as exc:
        print(f"Telebirr specific error: {exc}")
        if exc.details:
            print(f"  Details: {exc.details}")

    # --- CBE with suffix ---
    cbe_result: TransactionResult = await verify_cbe("FTBADREF", "12345678")
    if not cbe_result.success:
        print(f"CBE failed: {cbe_result.error}")
    else:
        print(f"CBE OK — {cbe_result.amount} ETB")

    # --- Universal with wrong format ---
    uni = await verify_universal("TOO_SHORT")
    if not uni.success:
        print(f"Universal routing failed: {uni.error}")


if __name__ == "__main__":
    asyncio.run(main())
