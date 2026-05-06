"""Example: Universal / auto-routing verification.

Hand any reference number to `verify_universal()` and it automatically
routes to the correct provider based on the reference format:

  • 16 digits starting with 3 → Dashen Bank
  • 12 chars starting with FT → CBE (suffix=8 digits) or Abyssinia (suffix=5 digits)
  • 10 chars alphanumeric      → Telebirr (no phone) or CBE Birr (with phone)
"""

import asyncio

from tx_verify import verify_universal


async def main() -> None:
    # --- Dashen Bank (16 digits) ---
    dashen_ref = "1234567890123456"
    print(f"\n🔹 Dashen reference: {dashen_ref}")
    result = await verify_universal(dashen_ref)
    print(f"   Success: {result.success}")
    if result.error:
        print(f"   Error: {result.error}")

    # --- CBE (12 chars, FT + 8-digit suffix) ---
    cbe_ref = "FT23062669JJ"
    cbe_suffix = "12345678"
    print(f"\n🔹 CBE reference: {cbe_ref}, suffix: {cbe_suffix}")
    result = await verify_universal(cbe_ref, suffix=cbe_suffix)
    print(f"   Success: {result.success}")
    if result.error:
        print(f"   Error: {result.error}")

    # --- Abyssinia (12 chars, FT + 5-digit suffix) ---
    aby_ref = "FT23062669JJ"
    aby_suffix = "90172"
    print(f"\n🔹 Abyssinia reference: {aby_ref}, suffix: {aby_suffix}")
    result = await verify_universal(aby_ref, suffix=aby_suffix)
    print(f"   Success: {result.success}")
    if result.error:
        print(f"   Error: {result.error}")

    # --- Telebirr (10 chars, no phone) ---
    telebirr_ref = "CE12345678"
    print(f"\n🔹 Telebirr reference: {telebirr_ref}")
    result = await verify_universal(telebirr_ref)
    print(f"   Success: {result.success}")
    if result.error:
        print(f"   Error: {result.error}")

    # --- CBE Birr (10 chars, with phone) ---
    cbe_birr_ref = "AB1234CD56"
    phone = "251911234567"
    print(f"\n🔹 CBE Birr reference: {cbe_birr_ref}, phone: {phone}")
    result = await verify_universal(cbe_birr_ref, phone_number=phone)
    print(f"   Success: {result.success}")
    if result.error:
        print(f"   Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
