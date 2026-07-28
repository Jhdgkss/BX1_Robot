from __future__ import annotations

import json
import requests
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_integrations.base import BaseIntegration, IntegrationCapability, IntegrationResult, IntegrationSettings, SafetyLevel
from bx1_integrations.manager import IntegrationManager
from bx1_integrations.dance_service import Choreography, ChoreographyStep, DanceService, validate_choreography
from bx1_integrations.events import mask_secret_text
from bx1_integrations.octoprint_connector import OctoPrintConnector, migrate_octoprint_config, normalise_octoprint_url
from bx1_integrations.permissions import PermissionManager
from bx1_integrations.registry import IntegrationRegistry
from bx1_integrations.router import route_integration_request
from bx1_integrations.spotify_connector import SpotifyConnector, generate_pkce_pair
from bx1_integrations.spotify_oauth import SpotifyOAuthCallback


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

    def test_duplicate_registry_id_is_rejected(self) -> None:
        registry = IntegrationRegistry()
        registry.register(OctoPrintConnector(IntegrationSettings(mock_mode=True)))
        with self.assertRaisesRegex(ValueError, "Duplicate integration ID"):
            registry.register(OctoPrintConnector(IntegrationSettings(mock_mode=True)))

    def test_disabled_integration_not_initialised(self) -> None:
        class Disabled(BaseIntegration):
            integration_id = "disabled_test"
            called = False
            def initialise(self):
                self.called = True
                return super().initialise()
        item = Disabled(IntegrationSettings({"enabled": False}, mock_mode=False))
        manager = IntegrationManager([item])
        self.assertEqual(manager.initialise_enabled(), {})
        self.assertFalse(item.called)

    def test_initialisation_failure_is_isolated(self) -> None:
        class Broken(BaseIntegration):
            integration_id = "broken_test"
            def initialise(self):
                raise RuntimeError("boom")
        manager = IntegrationManager([Broken(IntegrationSettings({"enabled": True}, mock_mode=False))])
        result = manager.initialise_enabled()["broken_test"]
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "initialisation_failed")

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

    def test_octoprint_url_normalisation(self) -> None:
        self.assertEqual(normalise_octoprint_url("192.168.68.60"), "http://192.168.68.60")
        self.assertEqual(normalise_octoprint_url("[printer](http://192.168.68.60/api/)"), "http://192.168.68.60")
        self.assertEqual(normalise_octoprint_url("octopi.local/"), "http://octopi.local")

    def test_octoprint_endpoint_failover_and_memory(self) -> None:
        session = MockSession()
        session.responses.extend([requests.ConnectionError("connection refused"), MockResponse(200, {"server": "1.10"})])
        settings = IntegrationSettings({"base_urls": ["http://first", "http://second"]}, {"api_key": "secret"}, mock_mode=False)
        connector = OctoPrintConnector(settings, session=session)
        result = connector.health_check()
        self.assertTrue(result.ok)
        self.assertEqual(settings.values["last_successful_endpoint"], "http://second")
        self.assertEqual([item[1] for item in session.requests], ["http://first/api/version", "http://second/api/version"])

    def test_octoprint_authentication_failure(self) -> None:
        session = MockSession()
        session.responses.append(MockResponse(401, {}))
        connector = OctoPrintConnector(IntegrationSettings({"base_urls": ["http://octo"]}, {"api_key": "bad"}, mock_mode=False), session=session)
        self.assertEqual(connector.health_check().error_code, "authentication_failed")

    def test_octoprint_all_endpoints_fail(self) -> None:
        session = MockSession()
        session.responses.extend([requests.Timeout("slow"), requests.ConnectionError("refused")])
        connector = OctoPrintConnector(IntegrationSettings({"base_urls": ["http://one", "http://two"]}, {"api_key": "key"}, mock_mode=False), session=session)
        result = connector.health_check()
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "all_endpoints_failed")
        self.assertIn("could not reach the printer", result.speakable.lower())

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

    def test_spotify_no_active_device(self) -> None:
        session = MockSession()
        session.responses.extend([MockResponse(200, {"id": "john"}), MockResponse(200, {"devices": []})])
        settings = IntegrationSettings({"client_id": "client"}, {"access_token": "access", "expires_at": str(9999999999)}, mock_mode=False)
        result = SpotifyConnector(settings, session=session).health_check()
        self.assertTrue(result.ok)
        self.assertEqual(result.error_code, "no_active_device")
        self.assertIn("no playback device", result.message)

    def test_robot_spotify_request_requires_robot_device(self) -> None:
        route = route_integration_request("Play Pink Floyd", source="robot_microphone", enabled={"spotify"})
        self.assertIsNotNone(route)
        self.assertEqual(route.action_id, "play_request")
        self.assertTrue(route.arguments["require_robot_device"])

    def test_typed_spotify_request_is_routed(self) -> None:
        route = route_integration_request("Play some music from Spotify", source="gui", enabled={"spotify"})
        self.assertEqual((route.integration_id, route.action_id), ("spotify", "play_request"))
        self.assertEqual(route.arguments["query"], "")

    def test_mocked_robot_playback_wording_reflects_success(self) -> None:
        connector = SpotifyConnector(IntegrationSettings({"enabled": True}, mock_mode=True))
        manager = IntegrationManager([connector])
        route = route_integration_request("Play Pink Floyd", source="robot_microphone", enabled={"spotify"})
        result = manager.execute(route.integration_id, route.action_id, route.arguments, initiated_by_ai=False, confirmed=False)
        safe = manager.result_for_llm(result)
        self.assertTrue(safe["ok"])
        self.assertEqual(safe["speakable"], "Playing pink floyd through the robot.")

    def test_informational_requests_are_not_routed(self) -> None:
        for text in ("Who founded Spotify?", "What is OctoPrint?", "Explain how Spotify Connect works.",
                     "I was listening to Pink Floyd yesterday.", "Write me a program that plays music."):
            self.assertIsNone(route_integration_request(text, source="gui", enabled={"spotify", "octoprint"}), text)

    def test_octoprint_status_routes_without_control(self) -> None:
        route = route_integration_request("How long is left on the print?", source="robot_microphone", enabled={"octoprint"})
        self.assertEqual(route.action_id, "get_print_progress")
        self.assertFalse(route.requires_confirmation)

    def test_octoprint_pause_routes_to_confirmation(self) -> None:
        route = route_integration_request("Pause the print", source="robot_microphone", enabled={"octoprint"})
        self.assertEqual(route.action_id, "pause_print")
        self.assertTrue(route.requires_confirmation)

    def test_spotify_device_selection_by_robot_name(self) -> None:
        session = MockSession()
        session.responses.append(MockResponse(200, {"devices": [
            {"id": "phone", "name": "John's Phone", "is_active": True},
            {"id": "robot", "name": "BX1 Robot", "is_active": False},
        ]}))
        settings = IntegrationSettings({"robot_device_name": "BX1 Robot"}, {"access_token": "a", "expires_at": "9999999999"}, mock_mode=False)
        connector = SpotifyConnector(settings, session=session)
        device_id, _ = connector._select_device(require_robot_device=True)
        self.assertEqual(device_id, "robot")

    def test_spotify_robot_device_does_not_fall_back(self) -> None:
        session = MockSession()
        session.responses.append(MockResponse(200, {"devices": [{"id": "phone", "name": "Phone", "is_active": True}]}))
        settings = IntegrationSettings({"robot_device_name": "BX1 Robot"}, {"access_token": "a", "expires_at": "9999999999"}, mock_mode=False)
        device_id, _ = SpotifyConnector(settings, session=session)._select_device(require_robot_device=True)
        self.assertEqual(device_id, "")

    def test_spotify_oauth_callback_state_validation(self) -> None:
        callback = SpotifyOAuthCallback("http://127.0.0.1:8765/callback", timeout=10)
        callback.result = {"state": "wrong", "code": "private-code", "error": ""}
        callback._event.set()
        self.assertEqual(callback.wait()["error"], "state_mismatch")

    def test_spotify_oauth_callback_success(self) -> None:
        callback = SpotifyOAuthCallback("http://127.0.0.1:8765/callback", timeout=10)
        callback.result = {"state": callback.state, "code": "private-code", "error": ""}
        callback._event.set()
        result = callback.wait()
        self.assertEqual(result["error"], "")
        self.assertEqual(result["code"], "private-code")

    def test_spotify_oauth_user_denial(self) -> None:
        callback = SpotifyOAuthCallback("http://127.0.0.1:8765/callback", timeout=10)
        callback.result = {"state": callback.state, "code": "", "error": "access_denied"}
        callback._event.set()
        self.assertEqual(callback.wait()["error"], "user_denied")

    def test_configuration_migration_preserves_unknown_keys(self) -> None:
        source = {"octoprint_url": "[old](http://octopi.local/)", "custom": {"keep": True}}
        migrated, changed = migrate_octoprint_config(source)
        self.assertTrue(changed)
        self.assertEqual(migrated["integrations"]["octoprint"]["base_urls"], ["http://octopi.local"])
        self.assertEqual(migrated["custom"], {"keep": True})

    def test_normalised_result_does_not_claim_failed_success(self) -> None:
        result = IntegrationResult(False, "play", message="Command was not confirmed", error_code="no_active_device", integration="spotify")
        payload = IntegrationManager().result_for_llm(result)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "no_active_device")
        self.assertNotIn("succeeded", payload["speakable"].lower())

    def test_llm_result_redacts_sensitive_fields(self) -> None:
        result = IntegrationResult(True, "status", {"api_key": "secret", "state": "idle", "endpoint": "http://private"}, integration="octoprint")
        payload = IntegrationManager().result_for_llm(result)
        self.assertEqual(payload["data"], {"state": "idle"})

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
