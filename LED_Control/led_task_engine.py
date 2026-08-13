"""BX1 Brain-side LED task engine.

This module does not drive GPIO and does not talk to the Arduino MCU directly.
It converts named Brain states into normal bx1.robot.v1 LED API commands.

Physical LED numbers are 1..7.  LED 7 is the mouth on the current robot.
The editable state/task mapping lives in settings/led_tasks.json.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


class LEDTaskEngine:
    """Apply named LED tasks through the unified Robot API."""

    def __init__(
        self,
        robot_api,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        config_path: Optional[Path] = None,
        verbose: bool = True,
    ) -> None:
        self.robot_api = robot_api
        self.loop = loop or asyncio.get_running_loop()
        self.verbose = bool(verbose)

        project_root = Path(__file__).resolve().parent.parent
        self.config_path = Path(
            config_path
            or project_root / "settings" / "led_tasks.json"
        )

        self.config: Dict[str, Any] = {}
        self.enabled = True
        self.master_brightness_percent = 35.0
        self.groups: Dict[str, list[int]] = {}
        self.tasks: Dict[str, dict] = {}

        # Desired state per logical channel.  This lets independent groups,
        # such as general activity and balance status, coexist.
        self._desired_by_channel: Dict[str, str] = {}
        self._running_by_channel: Dict[str, asyncio.Task] = {}
        self._exclusive_active = False
        self._exclusive_name = ""
        self._brightness_sent = False
        self._closed = False
        self._lock = threading.RLock()

        self.load()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load(self) -> dict:
        data: Dict[str, Any] = {}

        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
                if isinstance(loaded, dict):
                    data = loaded
        except FileNotFoundError:
            if self.verbose:
                print(f"[LED TASKS] Config not found: {self.config_path}")
        except Exception as exc:
            print(
                "[LED TASKS] Could not load config: "
                f"{type(exc).__name__}: {exc}"
            )

        self.config = data
        self.enabled = bool(data.get("enabled", True))
        self.master_brightness_percent = max(
            0.0,
            min(100.0, float(data.get("master_brightness_percent", 35.0))),
        )

        groups: Dict[str, list[int]] = {}
        for name, values in dict(data.get("groups") or {}).items():
            clean = []
            for value in list(values or []):
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    continue
                if 1 <= number <= 7 and number not in clean:
                    clean.append(number)
            groups[str(name)] = clean

        self.groups = groups
        self.tasks = {
            str(name): dict(task or {})
            for name, task in dict(data.get("tasks") or {}).items()
            if isinstance(task, dict)
        }

        if self.verbose:
            print(
                "[LED TASKS] Loaded "
                f"{len(self.tasks)} tasks from {self.config_path.name}."
            )

        return dict(self.config)

    # ------------------------------------------------------------------
    # Thread-safe public control
    # ------------------------------------------------------------------

    def trigger(self, task_name: str) -> None:
        """Schedule a named task from either the GUI or worker threads."""
        if self._closed or not self.enabled:
            return

        name = str(task_name or "").strip()
        if not name:
            return

        try:
            self.loop.call_soon_threadsafe(self._schedule_trigger, name)
        except RuntimeError:
            pass

    def end_exclusive(self, *, base_task: Optional[str] = None) -> None:
        """Leave an exclusive MCU mode (normally speaking) and restore layers."""
        if self._closed or not self.enabled:
            return

        def finish() -> None:
            if base_task:
                task = self.tasks.get(str(base_task), {})
                channel = str(task.get("channel", "activity"))
                self._desired_by_channel[channel] = str(base_task)
            asyncio.create_task(self._finish_exclusive())

        try:
            self.loop.call_soon_threadsafe(finish)
        except RuntimeError:
            pass

    def restore(self) -> None:
        if self._closed or not self.enabled:
            return
        try:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._restore_layers())
            )
        except RuntimeError:
            pass

    def close(self) -> None:
        self._closed = True
        try:
            self.loop.call_soon_threadsafe(self._cancel_all)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _schedule_trigger(self, name: str) -> None:
        task = self.tasks.get(name)
        if task is None:
            if self.verbose:
                print(f"[LED TASKS] Unknown task: {name}")
            return

        if bool(task.get("exclusive", False)):
            asyncio.create_task(self._start_exclusive(name, task))
            return

        channel = str(task.get("channel", "activity")).strip() or "activity"

        if (
            self._desired_by_channel.get(channel) == name
            and not bool(task.get("retrigger", False))
        ):
            return

        self._desired_by_channel[channel] = name

        # While speaking (or another exclusive task) we remember the desired
        # layer state but do not take the MCU out of that exclusive mode.
        if self._exclusive_active:
            return

        previous = self._running_by_channel.pop(channel, None)
        if previous is not None and not previous.done():
            previous.cancel()

        runner = asyncio.create_task(self._run_task(name, task))
        self._running_by_channel[channel] = runner

    def _cancel_all(self) -> None:
        for task in list(self._running_by_channel.values()):
            if task is not None and not task.done():
                task.cancel()
        self._running_by_channel.clear()

    async def _start_exclusive(self, name: str, task: dict) -> None:
        self._exclusive_active = True
        self._exclusive_name = name
        self._cancel_all()

        await self._ensure_master_brightness()

        mode = str(task.get("robot_mode", "")).strip().lower()
        if mode:
            await self._send("led.set_mode", {"mode": mode})
        else:
            await self._apply_actions(task.get("actions") or [])

        if self.verbose:
            print(f"[LED TASKS] Exclusive task -> {name}")

    async def _finish_exclusive(self) -> None:
        if not self._exclusive_active:
            await self._restore_layers()
            return

        self._exclusive_active = False
        self._exclusive_name = ""

        # Clear the built-in mode before restoring custom per-pixel layers.
        await self._send("led.set_mode", {"mode": "off"}, quiet=True)
        await self._restore_layers()

    async def _restore_layers(self) -> None:
        if self._exclusive_active or self._closed:
            return

        # Reapply the latest desired task for each channel.  Dict insertion
        # order is intentional: later channels can own overlapping pixels.
        for channel, name in list(self._desired_by_channel.items()):
            task = self.tasks.get(name)
            if task is None:
                continue

            previous = self._running_by_channel.pop(channel, None)
            if previous is not None and not previous.done():
                previous.cancel()

            runner = asyncio.create_task(self._run_task(name, task))
            self._running_by_channel[channel] = runner

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def _run_task(self, name: str, task: dict) -> None:
        try:
            await self._ensure_master_brightness()

            mode = str(task.get("robot_mode", "")).strip().lower()
            if mode:
                await self._send("led.set_mode", {"mode": mode})
                return

            steps = list(task.get("steps") or [])
            if not steps:
                await self._apply_actions(task.get("actions") or [])
                if self.verbose:
                    print(f"[LED TASKS] Task -> {name}")
                return

            repeat = max(1, min(20, int(task.get("repeat", 1))))

            for _ in range(repeat):
                for step in steps:
                    if self._exclusive_active:
                        return
                    step = dict(step or {})
                    await self._apply_actions(step.get("actions") or [])
                    delay_ms = max(0, min(5000, int(step.get("duration_ms", 0))))
                    if delay_ms:
                        await asyncio.sleep(delay_ms / 1000.0)

            final_actions = task.get("final_actions")
            if final_actions:
                await self._apply_actions(final_actions)

            if self.verbose:
                print(f"[LED TASKS] Task -> {name}")

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"[LED TASKS] Task '{name}' failed: "
                f"{type(exc).__name__}: {exc}"
            )

    async def _apply_actions(self, actions: Iterable[dict]) -> None:
        for action in actions:
            action = dict(action or {})
            numbers = self._resolve_leds(action)
            if not numbers:
                continue

            rgb = list(action.get("rgb") or [0, 0, 0])
            while len(rgb) < 3:
                rgb.append(0)

            brightness = max(
                0.0,
                min(100.0, float(action.get("brightness_percent", 100.0))),
            )

            red, green, blue = self._scale_rgb(
                rgb[0], rgb[1], rgb[2], brightness
            )

            for number in numbers:
                await self._send(
                    "led.set_pixel",
                    {
                        "led_number": int(number),
                        "r": red,
                        "g": green,
                        "b": blue,
                    },
                )

    def _resolve_leds(self, action: dict) -> list[int]:
        if "group" in action:
            return list(self.groups.get(str(action.get("group")), []))

        raw = action.get("leds")
        if raw is None and "led" in action:
            raw = [action.get("led")]

        result: list[int] = []
        for value in list(raw or []):
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= 7 and number not in result:
                result.append(number)
        return result

    @staticmethod
    def _scale_rgb(red: Any, green: Any, blue: Any, brightness: float) -> tuple[int, int, int]:
        scale = max(0.0, min(100.0, float(brightness))) / 100.0

        def one(value: Any) -> int:
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = 0
            value = max(0, min(255, value))
            return max(0, min(255, int(round(value * scale))))

        return one(red), one(green), one(blue)

    async def _ensure_master_brightness(self) -> None:
        if self._brightness_sent:
            return

        await self._send(
            "led.set_brightness",
            {"brightness_percent": self.master_brightness_percent},
        )
        self._brightness_sent = True

    async def _send(self, name: str, params: dict, *, quiet: bool = False) -> Optional[dict]:
        if self.robot_api is None or not bool(getattr(self.robot_api, "connected", False)):
            return None

        try:
            return await self.robot_api.send_command(name, params, timeout=3.0)
        except Exception as exc:
            self._brightness_sent = False
            if not quiet:
                print(
                    f"[LED TASKS] {name} failed: "
                    f"{type(exc).__name__}: {exc}"
                )
            return None
