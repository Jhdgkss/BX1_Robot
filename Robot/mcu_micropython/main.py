import time
import config
from movement_imu import MovementIMU
from head_servos import Head
from led_controller import LEDs
from rs485_wheels import Wheels
from safety import Safety
imu=MovementIMU(); head=Head(config); leds=LEDs(config); wheels=Wheels(config); safety=Safety()
imu_ok=imu.begin(); period_ms=max(2,int(1000/config.LOOP_HZ))
while True:
    reading=imu.read() if imu_ok else None
    head.service()
    # Add the board-specific command transport here.
    time.sleep_ms(period_ms)
