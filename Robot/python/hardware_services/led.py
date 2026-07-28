from __future__ import annotations

import colorsys
import math
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .event_bus import Event, EventBus, EventType
from .state import HardwareServiceBase, HardwareState, HardwareStateManager

RGB = Tuple[int, int, int]
BLACK: RGB = (0, 0, 0)
LED_COUNT = 7
DEFAULT_ZONES = {"head": [0], "body": [1, 2, 3, 4, 5, 6]}


class LEDEffect(str, Enum):
    SOLID = "Solid"
    FADE = "Fade"
    PULSE = "Pulse"
    BREATHE = "Breathe"
    BLINK = "Blink"
    CHASE = "Chase"
    RAINBOW = "Rainbow"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    WARNING = "Warning"
    FAULT = "Fault"


class LEDStripBase(ABC):
    """Output adapter for an exact seven-pixel BX1 strip."""

    pixel_count = LED_COUNT

    @abstractmethod
    def write(self, pixels: Sequence[RGB]) -> None:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> List[RGB]:
        raise NotImplementedError

    @abstractmethod
    def diagnostics(self) -> Dict[str, Any]:
        raise NotImplementedError


class SimulatedLEDStrip(LEDStripBase):
    def __init__(self) -> None:
        self._pixels: List[RGB] = [BLACK] * LED_COUNT
        self._frame_count = 0
        self._lock = threading.Lock()

    def write(self, pixels: Sequence[RGB]) -> None:
        validated = _validate_frame(pixels)
        with self._lock:
            self._pixels = validated
            self._frame_count += 1

    def snapshot(self) -> List[RGB]:
        with self._lock:
            return list(self._pixels)

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "backend": "simulation",
                "pixel_count": LED_COUNT,
                "frame_count": self._frame_count,
                "pixels": list(self._pixels),
            }


class CallbackLEDStrip(LEDStripBase):
    """Physical-strip adapter supplied by the platform layer.

    Construction performs no I/O. The injected callback owns GPIO/MCU details.
    """

    def __init__(self, writer: Callable[[Sequence[RGB]], None]) -> None:
        if not callable(writer):
            raise TypeError("physical LED writer must be callable")
        self._writer = writer
        self._pixels: List[RGB] = [BLACK] * LED_COUNT
        self._frame_count = 0

    def write(self, pixels: Sequence[RGB]) -> None:
        frame = _validate_frame(pixels)
        self._writer(tuple(frame))
        self._pixels = frame
        self._frame_count += 1

    def snapshot(self) -> List[RGB]:
        return list(self._pixels)

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "backend": "physical_adapter",
            "pixel_count": LED_COUNT,
            "frame_count": self._frame_count,
            "pixels": list(self._pixels),
        }


class LEDService(HardwareServiceBase):
    """Zone-aware, backend-independent effects service for exactly seven LEDs."""

    def __init__(
        self,
        output: LEDStripBase,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = {
            "enabled": True,
            "pixel_count": LED_COUNT,
            "backend": "simulation",
            "zones": {name: list(pixels) for name, pixels in DEFAULT_ZONES.items()},
            **dict(config or {}),
        }
        if int(cfg.get("pixel_count", LED_COUNT)) != LED_COUNT:
            raise ValueError("BX1 LED service requires exactly 7 pixels")
        if output.pixel_count != LED_COUNT:
            raise ValueError("LED output must provide exactly 7 pixels")
        self._zones = self._validate_zones(cfg.get("zones", DEFAULT_ZONES))
        cfg["pixel_count"] = LED_COUNT
        cfg["zones"] = {name: list(pixels) for name, pixels in self._zones.items()}
        enabled = bool(cfg.get("enabled", True))
        super().__init__(
            "led_service",
            cfg,
            state_manager=state_manager,
            fitted=True,
            enabled=enabled,
        )
        self.output = output
        self._clock = clock
        self._lock = threading.RLock()
        self._effect = LEDEffect.SOLID
        self._zone = "body"
        self._colour: RGB = BLACK
        self._secondary: RGB = BLACK
        self._brightness = 1.0
        self._period_s = 1.0
        self._duration_s = 1.0
        self._level = 1.0
        self._started_at = self._clock()
        self._start_pixels = self.output.snapshot()
        self._event_subscriptions: List[str] = []
        if enabled:
            self._transition(HardwareState.READY, "LED output adapter ready")

    def set_effect(
        self,
        effect: Any,
        *,
        zone: str = "body",
        colour: Any = (0, 170, 255),
        secondary_colour: Any = (128, 0, 255),
        brightness: float = 1.0,
        period_s: float = 1.0,
        duration_s: float = 1.0,
        level: float = 1.0,
    ) -> List[RGB]:
        if self.status()["state"] == HardwareState.DISABLED.value:
            raise RuntimeError("LED service is disabled")
        selected = self._parse_effect(effect)
        zone_name = str(zone).strip()
        if zone_name != "all" and zone_name not in self._zones:
            raise ValueError("unknown LED zone: %s" % zone_name)
        with self._lock:
            self._effect = selected
            self._zone = zone_name
            self._colour = _parse_colour(colour)
            self._secondary = _parse_colour(secondary_colour)
            self._brightness = _unit_float(brightness, "brightness")
            self._period_s = _positive_float(period_s, "period_s")
            self._duration_s = _positive_float(duration_s, "duration_s")
            self._level = _unit_float(level, "level")
            self._started_at = self._clock()
            self._start_pixels = self.output.snapshot()
        return self.tick(0.0)

    def tick(self, elapsed_s: Optional[float] = None) -> List[RGB]:
        with self._lock:
            elapsed = (
                max(0.0, self._clock() - self._started_at)
                if elapsed_s is None
                else max(0.0, float(elapsed_s))
            )
            frame = self._render(elapsed)
            try:
                self.output.write(frame)
            except Exception as exc:
                self._transition(HardwareState.FAULT, "LED output failed: %s" % exc)
                raise
            return self.output.snapshot()

    def clear(self, zone: str = "all") -> List[RGB]:
        return self.set_effect(LEDEffect.SOLID, zone=zone, colour=BLACK)

    def bind_events(self, event_bus: EventBus) -> None:
        """Bind high-level events to the body zone; LED 0/mouth stays untouched."""
        if (
            self._event_subscriptions
            or self.status()["state"] == HardwareState.DISABLED.value
        ):
            return
        bindings = {
            EventType.THINKING_STARTED: lambda event: self.set_effect(
                LEDEffect.THINKING, zone="body"
            ),
            EventType.THINKING_FINISHED: lambda event: self.clear("body"),
            EventType.SPEECH_STARTED: lambda event: self.set_effect(
                LEDEffect.SPEAKING,
                zone="body",
                level=event.payload.get("level", 1.0),
            ),
            EventType.SPEECH_FINISHED: lambda event: self.clear("body"),
            EventType.HARDWARE_FAULT: lambda event: self.set_effect(
                LEDEffect.FAULT, zone="body"
            ),
            EventType.BATTERY_LOW: lambda event: self.set_effect(
                LEDEffect.WARNING, zone="body"
            ),
            EventType.ROBOT_SLEEPING: lambda event: self.clear("body"),
        }
        self._event_subscriptions = [
            event_bus.subscribe(event_type, callback)
            for event_type, callback in bindings.items()
        ]

    def unbind_events(self, event_bus: EventBus) -> None:
        for token in self._event_subscriptions:
            event_bus.unsubscribe(token)
        self._event_subscriptions = []

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        with self._lock:
            base.update(
                {
                    "effect": self._effect.value,
                    "zone": self._zone,
                    "zones": {name: list(pixels) for name, pixels in self._zones.items()},
                    "output": self.output.diagnostics(),
                    "event_bindings": len(self._event_subscriptions),
                }
            )
        return base

    def _render(self, elapsed: float) -> List[RGB]:
        frame = self.output.snapshot()
        indexes = list(range(LED_COUNT)) if self._zone == "all" else self._zones[self._zone]
        phase = (elapsed % self._period_s) / self._period_s
        colour = _scale(self._colour, self._brightness)
        secondary = _scale(self._secondary, self._brightness)

        if self._effect == LEDEffect.SOLID:
            values = [colour] * len(indexes)
        elif self._effect == LEDEffect.FADE:
            amount = min(1.0, elapsed / self._duration_s)
            values = [_mix(self._start_pixels[index], colour, amount) for index in indexes]
        elif self._effect == LEDEffect.PULSE:
            amount = 1.0 - abs((2.0 * phase) - 1.0)
            values = [_scale(colour, amount)] * len(indexes)
        elif self._effect == LEDEffect.BREATHE:
            amount = 0.12 + (0.88 * ((1.0 - math.cos(phase * 2.0 * math.pi)) / 2.0))
            values = [_scale(colour, amount)] * len(indexes)
        elif self._effect == LEDEffect.BLINK:
            values = [colour if phase < 0.5 else BLACK] * len(indexes)
        elif self._effect == LEDEffect.CHASE:
            active = int(phase * len(indexes)) % len(indexes)
            values = [colour if offset == active else BLACK for offset in range(len(indexes))]
        elif self._effect == LEDEffect.RAINBOW:
            values = [
                _scale(_hsv((phase + (offset / max(1, len(indexes)))) % 1.0), self._brightness)
                for offset in range(len(indexes))
            ]
        elif self._effect == LEDEffect.THINKING:
            active = int(phase * len(indexes)) % len(indexes)
            values = [
                colour if offset == active else _scale(secondary, 0.18)
                for offset in range(len(indexes))
            ]
        elif self._effect == LEDEffect.SPEAKING:
            wave = 0.35 + (0.65 * abs(math.sin(phase * 2.0 * math.pi)))
            lit = max(1, int(math.ceil(len(indexes) * self._level * wave)))
            values = [colour if offset < lit else _scale(secondary, 0.08) for offset in range(len(indexes))]
        elif self._effect == LEDEffect.WARNING:
            values = [_scale((255, 110, 0), self._brightness) if phase < 0.65 else BLACK] * len(indexes)
        else:  # Fault
            on = phase < 0.25 or 0.5 <= phase < 0.75
            values = [_scale((255, 0, 0), self._brightness) if on else BLACK] * len(indexes)

        for index, value in zip(indexes, values):
            frame[index] = value
        return frame

    @staticmethod
    def _parse_effect(effect: Any) -> LEDEffect:
        if isinstance(effect, LEDEffect):
            return effect
        value = str(effect).strip().lower()
        for item in LEDEffect:
            if value in {item.name.lower(), item.value.lower()}:
                return item
        raise ValueError("unsupported LED effect: %s" % effect)

    @staticmethod
    def _validate_zones(raw: Any) -> Dict[str, List[int]]:
        if not isinstance(raw, Mapping) or not raw:
            raise ValueError("LED zones must be a non-empty mapping")
        result: Dict[str, List[int]] = {}
        for name, indexes in raw.items():
            zone = str(name).strip()
            if not zone or zone == "all":
                raise ValueError("invalid LED zone name: %s" % name)
            if not isinstance(indexes, Iterable) or isinstance(indexes, (str, bytes)):
                raise ValueError("LED zone %s must contain pixel indexes" % zone)
            pixels = [int(index) for index in indexes]
            if not pixels or len(set(pixels)) != len(pixels):
                raise ValueError("LED zone %s must contain unique pixel indexes" % zone)
            if any(index < 0 or index >= LED_COUNT for index in pixels):
                raise ValueError("LED zone %s uses a pixel outside 0..6" % zone)
            result[zone] = pixels
        return result


def _parse_colour(value: Any) -> RGB:
    names = {
        "black": BLACK,
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "cyan": (0, 255, 255),
        "amber": (255, 110, 0),
        "orange": (255, 80, 0),
        "purple": (128, 0, 255),
        "white": (255, 255, 255),
    }
    if isinstance(value, str):
        text = value.strip().lower()
        if text in names:
            return names[text]
        if len(text) == 7 and text.startswith("#"):
            try:
                return tuple(int(text[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore
            except ValueError as exc:
                raise ValueError("invalid LED colour: %s" % value) from exc
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 3:
        result = tuple(int(channel) for channel in value)
        if all(0 <= channel <= 255 for channel in result):
            return result  # type: ignore
    raise ValueError("LED colour must be RGB, #RRGGBB, or a supported name")


def _validate_frame(pixels: Sequence[RGB]) -> List[RGB]:
    if len(pixels) != LED_COUNT:
        raise ValueError("LED frame must contain exactly 7 pixels")
    return [_parse_colour(pixel) for pixel in pixels]


def _unit_float(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise ValueError("%s must be between 0 and 1" % label)
    return result


def _positive_float(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError("%s must be greater than zero" % label)
    return result


def _scale(colour: RGB, amount: float) -> RGB:
    return tuple(max(0, min(255, int(round(channel * amount)))) for channel in colour)  # type: ignore


def _mix(first: RGB, second: RGB, amount: float) -> RGB:
    return tuple(
        int(round(left + ((right - left) * amount)))
        for left, right in zip(first, second)
    )  # type: ignore


def _hsv(hue: float) -> RGB:
    red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return int(red * 255), int(green * 255), int(blue * 255)
