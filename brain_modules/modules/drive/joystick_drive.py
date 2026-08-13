"""Optional pygame gamepad example. Disabled by default."""

import asyncio
from brain_api.client import AsyncBrainClient

MAX_FORWARD = 10.0
MAX_TURN = 10.0
DEADZONE = 0.10
UPDATE = 0.08


def dz(v):
    v = float(v)
    return 0.0 if abs(v) < DEADZONE else v


async def main():
    try:
        import pygame
    except ImportError:
        raise SystemExit("pygame is not installed. Run: pip install pygame")
    pygame.init(); pygame.joystick.init()
    if pygame.joystick.get_count() < 1:
        raise SystemExit("No gamepad detected")
    pad = pygame.joystick.Joystick(0); pad.init()
    print("Left stick = move/turn. Button 1 = DISARM. ARM from the normal GUI.")
    async with AsyncBrainClient() as leo:
        try:
            while True:
                pygame.event.pump()
                if pad.get_numbuttons() > 1 and pad.get_button(1):
                    await leo.command("balance.disarm", {}, timeout=5.0)
                    await asyncio.sleep(0.3)
                    continue
                turn = dz(pad.get_axis(0)) * MAX_TURN
                forward = -dz(pad.get_axis(1)) * MAX_FORWARD
                if forward == 0.0 and turn == 0.0:
                    await leo.command("drive.hold", {})
                else:
                    await leo.command("drive.set_motion", {"forward_percent": forward, "turn_percent": turn})
                await asyncio.sleep(UPDATE)
        finally:
            try: await leo.command("drive.hold", {})
            except Exception: pass
            pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
