from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bx1_integrations.base import BaseIntegration, IntegrationCapability, IntegrationResult, IntegrationSettings, SafetyLevel


HEAD_LIMITS = {"head_yaw": (-90, 90), "head_pitch": (-45, 45), "head_roll": (-35, 35)}
LED_INTENSITY_RANGE = (0, 1)


@dataclass
class ChoreographyStep:
    duration: float = 0.5
    timestamp: Optional[float] = None
    head_yaw: Optional[float] = None
    head_pitch: Optional[float] = None
    head_roll: Optional[float] = None
    mouth_led: Dict[str, Any] = field(default_factory=dict)
    spoken_phrase: str = ""
    sound_cue: str = ""
    wheel_command: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Choreography:
    name: str
    steps: List[ChoreographyStep]
    wheel_enabled: bool = False


def built_in_choreographies() -> Dict[str, Choreography]:
    return {
        "greeting": Choreography("greeting", [ChoreographyStep(head_yaw=-12, duration=0.4), ChoreographyStep(head_yaw=12, spoken_phrase="Hello.", duration=0.4)]),
        "celebration": Choreography("celebration", [ChoreographyStep(head_pitch=14, mouth_led={"colour": "green", "intensity": 0.8}), ChoreographyStep(head_roll=-18), ChoreographyStep(head_roll=18)]),
        "curious": Choreography("curious", [ChoreographyStep(head_pitch=-10, head_roll=8), ChoreographyStep(head_yaw=18)]),
        "listening": Choreography("listening", [ChoreographyStep(head_pitch=-4, mouth_led={"colour": "blue", "intensity": 0.35}, duration=1.0)]),
        "simple_dance": Choreography("simple_dance", [ChoreographyStep(head_yaw=-25, duration=0.3), ChoreographyStep(head_yaw=25, duration=0.3), ChoreographyStep(head_roll=15, duration=0.3), ChoreographyStep(head_roll=-15, duration=0.3)]),
    }


def validate_choreography(choreography: Choreography, *, allow_wheels: bool = False) -> None:
    if not choreography.steps:
        raise ValueError("Choreography must contain at least one step.")
    if choreography.wheel_enabled and not allow_wheels:
        raise ValueError("Wheel movement is disabled by default.")
    for index, step in enumerate(choreography.steps):
        if step.duration <= 0:
            raise ValueError(f"Step {index} duration must be positive.")
        for key, (low, high) in HEAD_LIMITS.items():
            value = getattr(step, key)
            if value is not None and not (low <= float(value) <= high):
                raise ValueError(f"Step {index} {key} exceeds limits.")
        if step.mouth_led:
            intensity = float(step.mouth_led.get("intensity", 0))
            if not (LED_INTENSITY_RANGE[0] <= intensity <= LED_INTENSITY_RANGE[1]):
                raise ValueError(f"Step {index} LED intensity exceeds limits.")
        if step.wheel_command and not allow_wheels:
            raise ValueError("Wheel commands are disabled by default.")


class DanceService(BaseIntegration):
    integration_id = "robot_behaviours"
    display_name = "Robot Behaviours"

    def __init__(self, settings: Optional[IntegrationSettings] = None, robot_command_sink: Any = None) -> None:
        super().__init__(settings)
        self.routines = built_in_choreographies()
        self.robot_command_sink = robot_command_sink
        self.active_routine = ""
        self.wheel_commands_enabled = False

    @property
    def capabilities(self) -> List[IntegrationCapability]:
        return [
            IntegrationCapability("run_named_behaviour", "Run named behaviour", SafetyLevel.CONTROL),
            IntegrationCapability("stop_behaviour", "Stop behaviour", SafetyLevel.CONTROL),
        ]

    def run_named(self, name: str) -> IntegrationResult:
        routine = self.routines.get(name)
        if routine is None:
            return IntegrationResult(False, "run_named_behaviour", error_code="unknown_routine", message=f"Unknown routine: {name}")
        if self.active_routine:
            return IntegrationResult(False, "run_named_behaviour", error_code="routine_active", message="Another routine is already active")
        try:
            validate_choreography(routine, allow_wheels=self.wheel_commands_enabled)
        except Exception as exc:
            return IntegrationResult(False, "run_named_behaviour", error_code="invalid_choreography", message=str(exc))
        self.active_routine = name
        if self.robot_command_sink is not None and not self.settings.mock_mode:
            self.robot_command_sink(routine)
        self.active_routine = ""
        return IntegrationResult(True, "run_named_behaviour", {"routine": name, "steps": len(routine.steps)}, f"Routine completed: {name}")

    def stop(self) -> IntegrationResult:
        self.active_routine = ""
        return IntegrationResult(True, "stop_behaviour", message="Behaviour stop requested")

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        params = params or {}
        if action_id == "run_named_behaviour":
            return self.run_named(str(params.get("name") or params.get("routine") or ""))
        if action_id == "stop_behaviour":
            return self.stop()
        return IntegrationResult(False, action_id, error_code="unknown_action", message=f"Unknown action: {action_id}")
