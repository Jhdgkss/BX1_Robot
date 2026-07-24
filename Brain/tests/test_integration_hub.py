from __future__ import annotations

import json
import requests
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_integrations.base import IntegrationCapability, IntegrationSettings, SafetyLevel
from bx1_integrations.dance_service import Choreography, ChoreographyStep, DanceService, validate_choreography
from bx1_integrations.events import mask_secret_text
from bx1_integrations.octoprint_connector import OctoPrintConnector
from bx1_integrations.permissions import PermissionManager
from bx1_integrations.registry import IntegrationRegistry
from bx1_integrations.spotify_connector import SpotifyConnector, generate_pkce_pair


class MockResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self.payload = payload or {}
        self.content = json.dumps(self.payload).encode("utf-8")

    def json(self) -> dict:
        return self.payload


class MockSession:
    def __init__(self) -> None:
        self.responses: list[MockResponse | Exception] = []
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


class IntegrationHubTests(unittest.TestCase):
    def test_registry_loading(self) -> None:
        registry = IntegrationRegistry.load_defaults([
            OctoPrintConnector(IntegrationSettings(mock_mode=True)),
            SpotifyConnector(IntegrationSettings(mock_mode=True)),
            DanceService(IntegrationSettings(mock_mode=True)),
        ])
        self.assertIn("octoprint", registry.capabilities())
        self.assertIn("spotify", registry.capabilities())
        self.assertIn("robot_behaviours", registry.capabilities())

    def test_permission_enforcement(self) -> None:
        manager = PermissionManager()
        control = IntegrationCapability("pause", "Pause", SafetyLevel.CONTROL)
        critical = IntegrationCapability("cancel", "Cancel", SafetyLevel.SAFETY_CRITICAL)
        self.assertTrue(manager.decide(IntegrationCapability("status", "Status")).allowed)
        self.assertTrue(manager.decide(control, initiated_by_ai=True).requires_confirmation)
        self.assertFalse(manager.decide(critical).allowed)
        self.assertTrue(manager.decide(critical, confirmed=True).allowed)

    def test_secret_masking(self) -> None:
        text = "X-Api-Key: abc123 Authorization: Bearer tok987 api_key=secret"
        masked = mask_secret_text(text, ["secret"])
        self.assertNotIn("abc123", masked)
        self.assertNotIn("tok987", masked)
        self.assertNotIn("secret", masked)

    def test_octoprint_response_parsing(self) -> None:
        connector = OctoPrintConnector(IntegrationSettings(mock_mode=True))
        status = connector.printer_status()
        self.assertEqual(status["state"], "Operational")
        self.assertEqual(status["current_job"], "demo.gcode")
        self.assertEqual(status["progress"], 42.5)

    def test_octoprint_timeout_and_error_handling(self) -> None:
        session = MockSession()
        session.responses.append(requests.Timeout("slow"))
        connector = OctoPrintConnector(IntegrationSettings({"server_url": "http://octo"}, {"api_key": "secret"}, mock_mode=False), session=session)
        result = connector.health_check()
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "timeout")

    def test_spotify_pkce_generation(self) -> None:
        verifier, challenge = generate_pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertGreaterEqual(len(challenge), 43)
        self.assertNotEqual(verifier, challenge)

    def test_spotify_token_refresh(self) -> None:
        session = MockSession()
        session.responses.append(MockResponse(200, {"access_token": "new-access", "expires_in": 3600}))
        connector = SpotifyConnector(IntegrationSettings({"client_id": "client"}, {"refresh_token": "refresh"}, mock_mode=False), session=session)
        result = connector.refresh_token()
        self.assertTrue(result.ok)
        self.assertEqual(connector.settings.session_secrets["access_token"], "new-access")

    def test_spotify_401_403_429_handling(self) -> None:
        connector = SpotifyConnector(IntegrationSettings(mock_mode=False))
        for status, code in ((401, "expired_authorization"), (403, "forbidden_or_missing_premium"), (429, "rate_limited")):
            result = connector._spotify_error("play", MockResponse(status, {}))
            self.assertEqual(result.error_code, code)

    def test_behaviour_schema_validation(self) -> None:
        routine = Choreography("test", [ChoreographyStep(duration=0.2, head_yaw=10, mouth_led={"intensity": 0.5})])
        validate_choreography(routine)

    def test_motion_limit_enforcement(self) -> None:
        routine = Choreography("bad", [ChoreographyStep(duration=0.2, head_yaw=120)])
        with self.assertRaisesRegex(ValueError, "head_yaw"):
            validate_choreography(routine)

    def test_wheel_commands_disabled_by_default(self) -> None:
        routine = Choreography("wheel", [ChoreographyStep(duration=0.2, wheel_command={"linear": 0.1})])
        with self.assertRaisesRegex(ValueError, "Wheel commands"):
            validate_choreography(routine)

    def test_global_stop(self) -> None:
        service = DanceService(IntegrationSettings(mock_mode=True))
        service.active_routine = "simple_dance"
        result = service.stop()
        self.assertTrue(result.ok)
        self.assertEqual(service.active_routine, "")

    def test_ai_confirmation_requirements(self) -> None:
        registry = IntegrationRegistry.load_defaults([OctoPrintConnector(IntegrationSettings(mock_mode=True))])
        result = registry.execute("octoprint", "cancel_print", initiated_by_ai=True, confirmed=False)
        self.assertFalse(result.ok)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.error_code, "confirmation_required")


if __name__ == "__main__":
    unittest.main()
