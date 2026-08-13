"""Small Windows keyboard movement example. Disabled by default."""

import asyncio
import msvcrt
from brain_api.client import AsyncBrainClient

MOVE = 8.0
TURN = 8.0


async def main():
    print("W/S forward/reverse | A/D turn | SPACE hold | X disarm | Q quit")
    print("ARM LEO using the normal GUI first.")
    async with AsyncBrainClient() as leo:
        try:
            while True:
                if not msvcrt.kbhit():
                    await asyncio.sleep(0.02)
                    continue
                key = msvcrt.getwch().lower()
                if key == "w": await leo.command("drive.forward", {"percent": MOVE})
                elif key == "s": await leo.command("drive.reverse", {"percent": MOVE})
                elif key == "a": await leo.command("drive.left", {"percent": TURN})
                elif key == "d": await leo.command("drive.right", {"percent": TURN})
                elif key == " ": await leo.command("drive.hold", {})
                elif key == "x": await leo.command("balance.disarm", {}, timeout=5.0)
                elif key == "q": break
        finally:
            try: await leo.command("drive.hold", {})
            except Exception: pass


if __name__ == "__main__":
    asyncio.run(main())
