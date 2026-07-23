import time
from machine import Pin, PWM


def _clamp(value, low, high):
    return max(low, min(high, value))


class Servo:
    """Readable MicroPython servo with optional quiet PWM release."""

    def __init__(self, pin, home=0.0, invert=False, deadband_us=4):
        self.pin_number = int(pin)
        self.home = float(home)
        self.invert = bool(invert)
        self.deadband_us = max(0, int(deadband_us))
        self.pwm = None
        self.last_pulse_us = 1500
        self.last_write_ms = time.ticks_ms()
        self.attach()

    def attach(self):
        if self.pwm is None:
            self.pwm = PWM(Pin(self.pin_number), freq=50)

    def release(self):
        if self.pwm is not None:
            self.pwm.deinit()
            self.pwm = None

    def write_deg(self, degrees, force=False):
        degrees = _clamp(float(degrees), -60.0, 60.0)
        if self.invert:
            degrees = -degrees
        pulse_us = int(_clamp(1500 + degrees * 10, 900, 2100))
        was_released = self.pwm is None
        self.attach()
        if force or was_released or abs(pulse_us - self.last_pulse_us) >= self.deadband_us:
            self.pwm.duty_u16(int(pulse_us * 65535 / 20000))
            self.last_pulse_us = pulse_us
            self.last_write_ms = time.ticks_ms()


class Head:
    def __init__(self, cfg):
        deadband = getattr(cfg, "SERVO_PULSE_DEADBAND_US", 4)
        self.yaw = Servo(cfg.HEAD_YAW_PIN, cfg.YAW_HOME_DEG, cfg.YAW_INVERT, deadband)
        self.left = Servo(cfg.HEAD_LEFT_PIN, cfg.LEFT_HOME_DEG, False, deadband)
        self.right = Servo(cfg.HEAD_RIGHT_PIN, cfg.RIGHT_HOME_DEG, False, deadband)
        self.cfg = cfg
        self.last_motion_ms = time.ticks_ms()

    def pose(self, yaw=0.0, pitch=0.0, roll=0.0):
        c = self.cfg
        self.yaw.write_deg(c.YAW_HOME_DEG + yaw)
        self.left.write_deg(
            c.LEFT_HOME_DEG
            + pitch * c.PITCH_GAIN * c.LEFT_PITCH_SIGN
            + roll * c.ROLL_GAIN * c.LEFT_ROLL_SIGN
        )
        self.right.write_deg(
            c.RIGHT_HOME_DEG
            + pitch * c.PITCH_GAIN * c.RIGHT_PITCH_SIGN
            + roll * c.ROLL_GAIN * c.RIGHT_ROLL_SIGN
        )
        self.last_motion_ms = time.ticks_ms()

    def service(self):
        if not getattr(self.cfg, "SERVO_QUIET_RELEASE_ENABLED", True):
            return
        release_after = max(250, int(getattr(self.cfg, "SERVO_RELEASE_AFTER_MS", 1200)))
        if time.ticks_diff(time.ticks_ms(), self.last_motion_ms) >= release_after:
            self.yaw.release()
            self.left.release()
            self.right.release()
