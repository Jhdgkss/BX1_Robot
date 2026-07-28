# BX1 OS Core Developer Guide

## Add a plugin

Create one module under `Robot/python/bx1_core/plugins/`. A plugin has a stable
lowercase name, a version, the five lifecycle methods, and a module-level
`PLUGIN_CLASS`. Discovery uses the package contents; no central import list is
required.

```python
from bx1_core.health import HealthState
from bx1_core.plugins import CorePlugin


class ExamplePlugin(CorePlugin):
    name = "example"
    version = "1.0"

    def register(self, context):
        super().register(context)

    def update(self):
        context = self._require_context()
        context.state.set(
            "example.ready",
            True,
            source="plugin.example",
        )
        self._set_health(
            HealthState.HEALTHY,
            {"reason": "Example observation completed"},
        )

    def health(self):
        return super().health()

    def shutdown(self):
        return None


PLUGIN_CLASS = ExamplePlugin
```

`register()` receives `PluginContext`, which contains state, events, reviewed
configuration, the install root and clocks. Keep external dependencies behind
an injected provider so tests can be deterministic.

## Rules

1. A plugin owns only its documented state namespace.
2. Every update identifies a precise `source`.
3. Values must be JSON-serialisable and must not contain secrets.
4. `health()` returns `PluginHealth`, including state, booleans, timestamp and
   structured details.
5. Expected absence is not an exception. Report `warning` with a reason.
6. Unexpected failures may raise; the registry converts them to plugin faults
   and continues updating other plugins.
7. `shutdown()` must be idempotent and bounded.
8. Observer plugins may read state but must not claim devices or issue control
   operations.

Do not add direct OS or hardware queries to `bx1_management`. Put observation
inside a plugin and let the browser read a Core API projection.

Hardware adapters belong under `Robot/python/bx1_core/hardware/` and return the
shared `DeviceRecord` contract. Use `HardwareEnvironment` for bounded metadata
reads and `ReadOnlyHardwareInventory._safe()` for fault isolation. The complete
adapter rules, state envelope and detection/observation/control distinction are
documented in `BX1_OS_HARDWARE_INTEGRATION.md`.

## State and events

Use dotted paths:

```python
context.state.set_many(
    {
        "example.connected": True,
        "example.mode": "observer",
    },
    source="plugin.example",
)
```

Identical values do not consume a revision or emit an event. Subscribe by event
type or to `CoreEventBus.WILDCARD`:

```python
token = context.events.subscribe("STATE_CHANGED", on_change)
context.events.unsubscribe(token)
```

Callbacks run synchronously. Keep them short, never assume delivery order
across threads, and do not mutate event payloads.

## Telemetry consumers

Start with `/api/core/state`. Retain its `revision`, then poll
`/api/core/state?since=<revision>`. If `resync_required` is true, request a new
snapshot. A future WebSocket adapter will use the same state-change subscription
and envelope schemas.

## Testing

From the repository root:

```powershell
python Robot/tools/test_bx1_core_telemetry.py
python Robot/tools/test_management_interface.py
python Robot/tools/test_hardware_audio_integration.py
python Robot/tools/test_core_services.py
```

Plugin tests must use temporary paths, injected readers or controlled providers.
They must not require the robot, network services, systemd or physical hardware.
Cover successful observation, expected absence, fault containment, health
evidence, shutdown and JSON encoding.

Before a release, also run the deployment, phase-one, observer canary, compile,
JSON, shell syntax, manifest and archive checks documented in
`DEPLOYMENT_GUIDE.md`.
