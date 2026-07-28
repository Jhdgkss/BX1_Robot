# BX1 Integration Hub

The Integration Hub keeps external services outside conversation generation. The desktop Brain calls an integration through the registry/manager, receives an `IntegrationResult`, and only the manager's sanitised `normalised()` representation may be supplied to an LLM. Raw API payloads, endpoints, credentials, headers, HTML and stack traces must not enter prompts or speech.

## Layout and lifecycle

- `base.py`: metadata, configuration contract, connection state, safety levels and normalised results.
- `registry.py`: stable-ID registration and action permission enforcement. Duplicate IDs are rejected.
- `manager.py`: controlled built-in discovery, enabled-only initialisation, fault isolation, invocation, health collection, result sanitising and shutdown.
- `octoprint_connector.py`: multi-address printer integration.
- `spotify_connector.py`: OAuth/Spotify Connect integration.
- `permissions.py`: confirmation rules and optional OS credential storage.
- `events.py`: sanitised integration activity.
- `example_integration.py`: copyable developer template; it is deliberately not discovered.

Startup creates known built-ins only; arbitrary Python files are never executed. An import or initialisation failure is recorded without preventing Brain startup. Disabled integrations are discovered for Workshop display but are not initialised. On shutdown, each enabled service is stopped independently.

## Configuration

Non-secret values live below `integrations` in the active `config/app_config_<profile>.json`. Secrets live in the ignored profile-specific `secrets_<profile>.local.json` file (or may be moved through `SecretStore` to Windows Credential Manager). Workshop password fields are blank/masked after saving.

```json
{
  "integrations": {
    "mock_mode": false,
    "octoprint": {
      "enabled": true,
      "base_urls": ["http://printer-one", "http://printer-two"],
      "connect_timeout": 2.0,
      "request_timeout": 8.0,
      "last_successful_endpoint": "http://printer-two"
    },
    "spotify": {
      "enabled": true,
      "client_id": "...",
      "redirect_uri": "http://127.0.0.1:8765/spotify/callback",
      "preferred_device": "Workshop speaker",
      "request_timeout": 8.0
    }
  }
}
```

Legacy `octoprint_url`, `octoprint_server_url`, or `server_url` values are copied into `base_urls`. Unknown keys remain intact. Before the first on-disk migration the Brain creates an adjacent `.pre-integrations.bak`.

## Adding an integration

Copy `example_integration.py`, choose a unique stable ID, define metadata, `configuration_schema`, validation and capabilities, then implement bounded-timeout actions returning `IntegrationResult`. Mark state-changing capabilities `CONTROL` or `SAFETY_CRITICAL`. Add the module/class to the fixed built-in list in `IntegrationManager.builtins`; do not scan arbitrary folders. Add mocked registration, disabled, failure, redaction and action tests. Workshop should render/adapt the schema rather than contain service implementation.

## OctoPrint troubleshooting

Enter addresses separated by semicolons in Workshop. Inputs may be bare IPs/hostnames, full HTTP(S) URLs or pasted Markdown links. A trailing `/api` is removed so API paths are not duplicated. The last successful address is tried first, followed by configured order, with finite connect/request timeouts. `X-Api-Key` is the only API authentication header used.

Connection test distinguishes timeout, refused connection, unreachable host, DNS/`.local` failure, rejected API key and unexpected responses. “Could not reach” does not imply the printer itself is offline. Once the server is reachable, printer state may separately show disconnected. Printer-changing operations remain behind existing Workshop confirmation/safety levels.

## Spotify reconnection

Create a Spotify developer application and register the redirect URI exactly as shown in Workshop. Save the client ID, optional client secret, redirect URI and preferred device. Connect/Reconnect generates PKCE authorization data; the returned authorization code must be exchanged and its refresh token saved. Playback control requires appropriate scopes, usually Spotify Premium, and an available Spotify Connect device. Open Spotify on the preferred device if the account is authenticated but no device appears. Authentication expiry, Premium/permission denial, no device and rate limiting are reported separately.

Connect/Reconnect starts a one-use loopback callback listener, opens the browser, validates OAuth state, exchanges the PKCE code, persists the refresh token in the local secret store, tests the account, and then stops the listener. The redirect URI in Spotify Developer Dashboard must exactly match Workshop.

### Playing through the physical robot

Spotify audio is delivered by Spotify Connect, not by the Web API or BX1's TTS audio download path. The physical robot must therefore run a Spotify-capable client and appear in Spotify's device list. In Workshop, set **Robot playback device** to that device's exact Spotify Connect name (or set `robot_device_id` in configuration).

Requests arriving from `robot_microphone` use this robot device strictly. Brain will transfer playback to it before playing. It will not fall back to a phone or Brain PC, because that would make a robot voice command play in the wrong place. If the configured robot device is missing, Brain asks the operator to start Spotify Connect on the robot and does not claim playback began.

Typed desktop requests continue to use the ordinary preferred/active-device policy.

## Tests

From `Brain`:

```powershell
python tests/test_integration_hub.py -v
python tests/test_gui_workflow_v212.py
```

All service calls in tests use mocks; a printer and Spotify account are not required.
