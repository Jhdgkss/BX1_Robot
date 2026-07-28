# BX1 Hardware Services

## Scope and safety

Phase 1B defines the permanent service interfaces without controlling physical
hardware. It does not flash firmware, deploy files, open RS485, transmit motor
packets, enable balance, move motors or servos, or change GPIO assignments.

The implementation is `Robot/python/hardware_services/`. The existing mouth
speech-light code in `Robot/python/main.py` remains authoritative and unchanged.
Default Event Bus bindings target only body LEDs 1–6, so the head/mouth LED at
logical address 0 is not overwritten.

## Stable service surface

`create_hardware_services(config)` returns `HardwareServices` with:

- `event_bus`: publish/subscribe coordination with no hardware dependency.
- `leds`: seven-pixel zone and effect control through an output adapter.
- `drive`: validated motor commands and dry-run state.
- `range`: normalized readings through a sensor adapter.
- `state_manager`: lifecycle records shared by the constructed services.

Each public service provides:

```python
service.status()         # current state and reason
service.health()         # healthy/available summary
service.diagnostics()    # counters, state, recent activity and backend evidence
service.configuration()  # effective configuration
```

Higher-level code uses the same members in `digital_twin` and `physical` modes.
A physical backend is never discovered implicitly: it must be injected into the
factory. This keeps imports and configuration changes from causing hardware I/O.

## Event Bus

`EventBus` provides:

```python
token = bus.subscribe(EventType.THINKING_STARTED, on_thinking)
bus.publish(EventType.THINKING_STARTED, {"request_id": "abc"}, source="brain")
bus.unsubscribe(token)
snapshot = bus.diagnostics()
```

Callbacks receive one immutable `Event` with `type`, `payload`, `source` and
`timestamp`. String event names are supported for future extensions. Subscribe
to `"*"` for diagnostics/telemetry observers.

Delivery is synchronous. The bus snapshots subscribers before callbacks begin,
so subscribe/unsubscribe calls from a callback affect the next publication.
One failing callback does not prevent other subscribers from receiving the
event; the exception is counted and retained in diagnostics.

The initial event vocabulary is:

- `WakeDetected`
- `SpeechStarted`
- `SpeechFinished`
- `ThinkingStarted`
- `ThinkingFinished`
- `HardwareFault`
- `BatteryLow`
- `ObstacleDetected`
- `RobotReady`
- `RobotSleeping`

### Registering a new service

A service keeps the returned subscription tokens and releases them during
shutdown:

```python
class ExampleService:
    def start(self, bus):
        self._tokens = [
            bus.subscribe(EventType.ROBOT_READY, self._on_ready),
            bus.subscribe(EventType.ROBOT_SLEEPING, self._on_sleep),
        ]

    def stop(self, bus):
        for token in self._tokens:
            bus.unsubscribe(token)
        self._tokens = []

    def _on_ready(self, event):
        ...
```

Publishing hardware faults should include the service and a stable reason in
the payload. Event consumers must not treat an event as permission to bypass a
service validator or safety state.

## Hardware states

`HardwareStateManager` owns these states:

| State | Meaning |
| --- | --- |
| `NOT_FITTED` | Device is absent or its future adapter is only a placeholder. |
| `DISABLED` | Device exists but configuration prevents use. |
| `INITIALISING` | Device/adapter is starting or recovering. |
| `READY` | Device has current, healthy evidence and can serve its configured role. |
| `STALE` | Previously valid sensor/state evidence exceeded its freshness limit. |
| `FAULT` | A driver, validation boundary or device reported a fault. |

Allowed transitions are:

```text
NOT_FITTED  -> DISABLED | INITIALISING
DISABLED    -> NOT_FITTED | INITIALISING
INITIALISING-> DISABLED | READY | FAULT
READY       -> DISABLED | STALE | FAULT
STALE       -> DISABLED | READY | FAULT
FAULT       -> DISABLED | INITIALISING
```

Recovery from `FAULT` passes through `INITIALISING`; code cannot jump directly
from `FAULT` to `READY`. Transitions record timestamps and reasons.

## LED Service

BX1 exposes exactly seven logical LEDs:

```json
{
  "head": [0],
  "body": [1, 2, 3, 4, 5, 6]
}
```

Zones are configurable, but all indexes must remain inside 0–6 and the pixel
count cannot change. `LEDService.set_effect()` supports `Solid`, `Fade`, `Pulse`,
`Breathe`, `Blink`, `Chase`, `Rainbow`, `Thinking`, `Speaking`, `Warning` and
`Fault`. `tick()` renders deterministically, which lets tests use a fake clock.

`SimulatedLEDStrip` stores the last seven-pixel frame and frame count.
`CallbackLEDStrip` sends the same frame to an injected platform writer.
Constructing either the adapter or service performs no physical write. Future
MCU/platform adapters are responsible for translating the service's zero-based
logical indexes to any legacy wire-protocol addressing.

The optional `LEDService.bind_events()` mappings use the body zone only:

- thinking start/finish → Thinking/clear
- speech start/finish → Speaking/clear
- battery low → Warning
- hardware fault → Fault
- robot sleeping → clear

## Motor Service

The motion path is:

```text
DriveService -> CommandValidator -> MotorController -> RS485Transport
```

`DriveService.drive(linear_speed, angular_speed, duration_s=...,
acceleration=...)` converts a differential-drive request to wheel speeds.
`drive_wheels(left_speed, right_speed, ...)` is the lower-level public form.
Both paths validate finite numbers, speed limits, duration and acceleration.
Accepted and rejected commands are retained in diagnostics and emitted through
Python logging.

`MotorController` applies per-side inversion, attaches controller addresses and
timeout, and updates `MotorState`. `RS485Transport` records the would-be packet
with `transmitted: false`. It imports no serial driver, always reports
`is_open == false`, and `open()` raises a Phase 1B safety error.

Effective defaults include:

```json
{
  "drive_enabled": false,
  "drive_dry_run": true,
  "rs485_enabled": false,
  "serial_port": "",
  "baud_rate": 115200,
  "addresses": {"left": 1, "right": 2},
  "inversion": {"left": false, "right": true},
  "acceleration": 0.5,
  "limits": {
    "max_speed": 1.0,
    "max_acceleration": 1.0,
    "max_duration_s": 5.0
  },
  "timeout_s": 1.0
}
```

Setting `rs485_enabled: true` or `drive_dry_run: false` does not enable output:
the affected component enters `FAULT` and the hard transport interlock remains.

## Range Service

`DistanceSensorBase` normalizes:

- `distance_mm`
- `signal_quality` (0.0–1.0)
- `available`
- `healthy`
- `sample_age_ms`
- `out_of_range`
- `fault_reason`

`RangeService.poll()` requests a reading and updates service health.
`reading()` recalculates age using a monotonic clock and moves a ready service to
`STALE` when `stale_after_ms` is exceeded.

`MockDistanceSensor` accepts a default reading, a configurable sequence, or
runtime `set_reading()` calls. It supports unavailable, unhealthy, malformed and
out-of-range test cases. `FutureToFSensor` is deliberately `NOT_FITTED` and
returns an unavailable reading without importing or accessing a hardware driver.

## Digital Twin

`DigitalTwin.create(config)` constructs:

- `SimulatedLEDStrip` behind `LEDService`
- dry-run `DriveService`, `MotorController` and `RS485Transport`
- `MockDistanceSensor` behind `RangeService`
- shared `EventBus` and `HardwareStateManager`

Useful test controls are `set_distance()` and `step()`. The Digital Twin is the
default mode in all Robot configuration variants.

For an adapter-backed service graph, higher-level code still calls the same
interfaces:

```python
services = create_hardware_services(
    {"mode": "physical"},
    physical_led_writer=platform_led_writer,
    range_sensor=platform_range_sensor,
)
```

Phase 1B does not provide a live platform writer or physical range sensor.

## Future expansion and deployment requirements

Later hardware work must be separately authorized and should:

1. Define and version the MCU LED and RS485 packet protocols.
2. Implement platform adapters behind `LEDStripBase` and
   `DistanceSensorBase`, with no changes to Brain callers.
3. Reconcile zero-based logical LED indexes with the existing MCU's legacy
   address representation while preserving mouth audio ownership.
4. Add serial discovery/open/close only inside a production transport, guarded
   by explicit arming, watchdog, timeout, E-stop and Robot-side limits.
5. Add encoder feedback and distinguish commanded from measured motor state.
6. Add real ToF freshness, signal-quality and calibration evidence.
7. Run bench tests with wheels mechanically unable to move before any powered
   motion test.
8. Add integration/startup wiring only after physical adapters and safety tests
   are approved.

The main design concern is ownership during migration: the legacy runtime
currently controls MCU LEDs and speech animation directly. It must not be wired
to the new LED service until a single-writer policy and address translation are
defined. Motor enablement also requires a production transport and independent
hardware safety review; changing configuration alone is intentionally
insufficient.
