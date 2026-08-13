# ============================================================
# BX1 / LEO - LINUX SIDE LED CONTROLLER
# ============================================================
#
# Runs on the Arduino UNO Q Linux / Debian side.
#
# The Linux code does not drive D3 directly.  Commands are sent
# through the UNO Q Bridge to the MCU sketch, which owns the
# WS2812/NeoPixel timing on D3.
#
# PHYSICAL BX1 LED LAYOUT
# -----------------------
#   Physical LEDs : 1 .. 7
#   MCU indexes   : 0 .. 6
#   Mouth         : physical LED 7 = MCU index 6
# ============================================================

try:
    from arduino.app_utils import Bridge
except Exception as exc:
    Bridge = None
    _BRIDGE_IMPORT_ERROR = exc
else:
    _BRIDGE_IMPORT_ERROR = None


class LEDController:
    """High-level BX1 LED interface."""

    MODE_OFF = 0
    MODE_IDLE = 1
    MODE_LISTENING = 2
    MODE_THINKING = 3
    MODE_SPEAKING = 4
    MODE_ERROR = 5

    LED_COUNT = 7
    MOUTH_LED_NUMBER = 7
    MOUTH_LED_INDEX = 6

    def __init__(
        self,
        enabled=True,
        verbose=True,
        *,
        led_count=None,
        mouth_led_number=None,
        mouth_led_index=None,
    ):
        self.verbose = bool(verbose)
        self.enabled = bool(enabled) and Bridge is not None

        if led_count is not None:
            self.LED_COUNT = int(led_count)
        if mouth_led_number is not None:
            self.MOUTH_LED_NUMBER = int(mouth_led_number)
        if mouth_led_index is not None:
            self.MOUTH_LED_INDEX = int(mouth_led_index)

        if not 0 <= self.MOUTH_LED_INDEX < self.LED_COUNT:
            raise ValueError("Configured mouth LED index is outside LED chain")

        if not self.enabled:
            if Bridge is None:
                print(
                    "[LEDS] Disabled - Arduino Bridge Python package "
                    f"is not available: {_BRIDGE_IMPORT_ERROR}"
                )
            else:
                print("[LEDS] Disabled by configuration.")
        elif self.verbose:
            print(
                "[LEDS] Linux LED controller ready "
                f"({self.LED_COUNT} LEDs; mouth = LED {self.MOUTH_LED_NUMBER})."
            )

    def _call(self, method, *args):
        if not self.enabled:
            return False

        try:
            result = Bridge.call(method, *args)

            if self.verbose:
                print(f"[LEDS] {method}{args} -> {result}")

            return result

        except Exception as exc:
            print(
                f"[LEDS] Bridge call '{method}' failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return False

    # --------------------------------------------------------
    # CONNECTION TEST
    # --------------------------------------------------------

    def ping(self):
        return self._call("bx1_led_ping")

    # --------------------------------------------------------
    # BASIC LED COMMANDS
    # --------------------------------------------------------

    def off(self):
        return self._call("bx1_led_mode", self.MODE_OFF)

    def clear(self):
        return self.off()

    def set_colour(self, red, green, blue):
        """Set the complete seven-LED chain to one RGB colour."""
        return self._call(
            "bx1_led_set_all",
            int(red),
            int(green),
            int(blue),
        )

    def set_led(self, index, red, green, blue):
        """Set one LED using the zero-based MCU index (0..6)."""
        index = int(index)

        if not 0 <= index < self.LED_COUNT:
            print(
                f"[LEDS] Invalid LED index {index}. "
                f"Valid MCU indexes are 0..{self.LED_COUNT - 1}."
            )
            return False

        return self._call(
            "bx1_led_set_pixel",
            index,
            int(red),
            int(green),
            int(blue),
        )

    def set_led_number(self, number, red, green, blue):
        """Set one LED using human-friendly physical numbering (1..7)."""
        number = int(number)

        if not 1 <= number <= self.LED_COUNT:
            print(
                f"[LEDS] Invalid physical LED number {number}. "
                f"Valid LED numbers are 1..{self.LED_COUNT}."
            )
            return False

        return self.set_led(
            number - 1,
            red,
            green,
            blue,
        )

    def set_mouth_colour(self, red, green, blue):
        """Set physical LED 7, the mouth LED."""
        return self.set_led(
            self.MOUTH_LED_INDEX,
            red,
            green,
            blue,
        )

    def set_brightness(self, brightness):
        """Set global brightness as either 0.0..1.0 or 0..255."""
        value = float(brightness)

        if 0.0 <= value <= 1.0:
            value = round(value * 255.0)

        value = max(0, min(255, int(value)))

        return self._call("bx1_led_brightness", value)

    # --------------------------------------------------------
    # BX1 ROBOT STATES
    # --------------------------------------------------------

    def idle(self):
        return self._call("bx1_led_mode", self.MODE_IDLE)

    def listening(self):
        return self._call("bx1_led_mode", self.MODE_LISTENING)

    def thinking(self):
        return self._call("bx1_led_mode", self.MODE_THINKING)

    def speaking(self):
        return self._call("bx1_led_mode", self.MODE_SPEAKING)

    def error(self):
        return self._call("bx1_led_mode", self.MODE_ERROR)

    # --------------------------------------------------------
    # SPEECH / MOUTH LEVEL
    # --------------------------------------------------------

    def mouth_level(self, level):
        """Set mouth brightness level from 0..100 while speaking."""
        level = max(0, min(100, int(level)))
        return self._call("bx1_led_mouth_level", level)
