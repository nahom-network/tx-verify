import asyncio

from verifier_api import *

# telebirr and cbe birr failed

# mpesa partially works


async def main():

    result = await verify_mpesa("UE20VG1GS8")

    print("Verification Result:", result)


if __name__ == "__main__":
    asyncio.run(main())
