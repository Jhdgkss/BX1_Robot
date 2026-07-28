from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    data: Any = None
    error_code: str = ""
    error: str = ""

    def as_response(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": (
                None
                if self.ok
                else {"code": self.error_code, "message": self.error}
            ),
        }


class CommandRouter:
    """Routes stable protocol commands only through BX1 service APIs."""

    def __init__(
        self,
        bx1: Any,
        *,
        capability_provider: Callable[[], Dict[str, Any]],
        protocol_version: str,
    ) -> None:
        self.bx1 = bx1
        self._capabilities = capability_provider
        self.protocol_version = str(protocol_version)
        self._routes: Dict[str, Callable[[Mapping[str, Any]], Any]] = {}
        self._route_count = 0
        self._error_count = 0
        self._register_defaults()

    def register(
        self,
        command: str,
        handler: Callable[[Mapping[str, Any]], Any],
        *,
        replace: bool = False,
    ) -> None:
        name = self._normalise(command)
        if name in self._routes and not replace:
            raise ValueError("command is already registered: %s" % name)
        if not callable(handler):
            raise TypeError("command handler must be callable")
        self._routes[name] = handler

    def route(
        self,
        command: str,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> CommandResult:
        name = self._normalise(command)
        handler = self._routes.get(name)
        if handler is None:
            self._error_count += 1
            return CommandResult(
                False,
                error_code="UNKNOWN_COMMAND",
                error="Unsupported BX1 command: %s" % command,
            )
        try:
            value = handler(dict(payload or {}))
            self._route_count += 1
            return CommandResult(True, data=value)
        except (KeyError, TypeError, ValueError) as exc:
            self._error_count += 1
            return CommandResult(
                False,
                error_code="INVALID_PAYLOAD",
                error=str(exc),
            )
        except Exception as exc:
            self._error_count += 1
            return CommandResult(
                False,
                error_code="COMMAND_FAILED",
                error=str(exc),
            )

    def commands(self) -> list[str]:
        return sorted(self._routes)

    def status(self) -> Dict[str, Any]:
        return {
            "service": "command_router",
            "state": "READY",
            "command_count": len(self._routes),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "available": True,
            "state": "READY",
            "reason": "Command router ready",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "commands": self.commands(),
            "route_count": self._route_count,
            "error_count": self._error_count,
        }

    def configuration(self) -> Dict[str, Any]:
        return {"protocol_version": self.protocol_version}

    def _register_defaults(self) -> None:
        self.register("battery.status", lambda payload: self.bx1.battery.status())
        self.register("power.health", lambda payload: self.bx1.power.health())
        self.register("drive.stop", lambda payload: self.bx1.drive.stop())
        self.register("drive.move", self._drive_move)
        self.register("led.set", self._led_set)
        self.register("range.distance", self._range_distance)
        self.register(
            "diagnostics.report", lambda payload: self.bx1.diagnostics.report()
        )
        self.register("health.status", lambda payload: self.bx1.health.status())
        self.register("system.info", self._system_info)
        self.register("capabilities.get", lambda payload: self._capabilities())
        self.register("get.capabilities", lambda payload: self._capabilities())

    def _drive_move(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        required = {"linear_speed", "angular_speed", "duration_s"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError("missing drive payload fields: %s" % ", ".join(missing))
        return self.bx1.drive.drive(
            payload["linear_speed"],
            payload["angular_speed"],
            duration_s=payload["duration_s"],
            acceleration=payload.get("acceleration"),
        )

    def _led_set(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        allowed = {
            "effect",
            "zone",
            "colour",
            "secondary_colour",
            "brightness",
            "period_s",
            "duration_s",
            "level",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError("unknown LED payload fields: %s" % ", ".join(unknown))
        kwargs = dict(payload)
        effect = kwargs.pop("effect", "Solid")
        pixels = self.bx1.led.set_effect(effect, **kwargs)
        return {
            "effect": str(effect),
            "pixels": [list(pixel) for pixel in pixels],
            "simulated": True,
        }

    def _range_distance(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if payload:
            raise ValueError("range.distance does not accept a payload")
        return self.bx1.range.poll().as_dict()

    def _system_info(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if payload:
            raise ValueError("system.info does not accept a payload")
        return {
            "protocol_version": self.protocol_version,
            "system": self.bx1.status(),
            "services": self.bx1.services.names(),
            "capabilities": self._capabilities(),
            "digital_twin": True,
        }

    @staticmethod
    def _normalise(command: str) -> str:
        value = str(command).strip()
        if value == "GET capabilities":
            return "get.capabilities"
        return value.lower()
