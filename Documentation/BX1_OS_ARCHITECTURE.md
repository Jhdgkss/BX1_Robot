# BX1 OS Architecture

## Safety boundary

> The Brain chooses the goal. The Robot performs it safely.

High-level intent crosses the Brain/Robot boundary. Raw, unchecked actuator control
does not. Robot-side validation, limits, timeouts, state and telemetry remain
authoritative even when the Brain requests an action.

## Brain responsibilities

- Conversation and personality.
- Vision, object recognition and person recognition.
- World model and memory.
- Navigation planning, skill selection and high-level commands.
- Internet and document retrieval.

## Robot responsibilities

- IMU sampling, balance control and wheel control.
- RS485 communication and encoder feedback.
- Head control, distance sensing and LEDs.
- Safety, command validation and command timeout.
- Telemetry and diagnostics.

## Current phase boundary

This phase establishes the baseline and adds read-only diagnostics. Wheel drive,
balancing, RS485 motor commands and automatic firmware deployment remain disabled.
Existing voice, wake, STT, TTS, camera, touchscreen, web, servo and LED behaviour
is preserved.

Sensor readiness is freshness-gated. Router connectivity, a fresh MCU heartbeat,
IMU detection, IMU initialisation, a fresh IMU sample and overall IMU health are
separate states. Cached telemetry cannot satisfy future balance readiness.

## Runtime model

The desktop Windows Brain is a PyQt application with an embedded HTTP API and
background workers. The UNO Q Linux processor runs the Robot Python body service,
web server, voice/camera clients and Router RPC client. The UNO Q STM32 MCU runs
the Arduino sketch for deterministic I/O, head servos, addressable LEDs and
Modulino Movement sampling.

The present protocol has three layers:

1. Robot-to-Brain HTTP (`Robot/python/bx1_robot_client.py`).
2. Robot web HTTP (`Robot/python/web_control.py`).
3. Linux-to-MCU MessagePack Router RPC, with serial fallback
   (`Robot/python/hardware_bridge.py`, `Robot/sketch/sketch.ino`).

This is a baseline, not yet the final shared versioned Brain/Robot safety protocol.

## Phase 1B hardware service boundary

Permanent hardware-facing code lives under
`Robot/python/hardware_services/`. Higher-level behavior consumes the
`HardwareServices` interface returned by `create_hardware_services()` and does
not import GPIO, serial, LED, motor or sensor drivers. The selected configuration
mode supplies either a Digital Twin or explicitly injected physical adapters.

The service graph is:

```text
Brain / robot behavior
        |
        +-- EventBus (hardware-independent intent and lifecycle events)
        |
        +-- LEDService ------ LEDStripBase
        |                         +-- SimulatedLEDStrip
        |                         +-- CallbackLEDStrip (future platform writer)
        |
        +-- DriveService ---- CommandValidator ---- MotorController
        |                                             |
        |                                        RS485Transport
        |                                      (Phase 1B hard lockout)
        |
        +-- RangeService ---- DistanceSensorBase
                                  +-- MockDistanceSensor
                                  +-- FutureToFSensor
```

Every public service exposes `status()`, `health()`, `diagnostics()` and
`configuration()`. `HardwareStateManager` is the lifecycle authority for
`NOT_FITTED`, `DISABLED`, `INITIALISING`, `READY`, `STALE` and `FAULT`.
Illegal transitions are rejected rather than silently rewriting device state.

The Event Bus delivers events synchronously from a snapshot of its subscriber
list. Subscriber exceptions are isolated and recorded in diagnostics. The
standard event vocabulary begins with `WakeDetected`, `SpeechStarted`,
`SpeechFinished`, `ThinkingStarted`, `ThinkingFinished`, `HardwareFault`,
`BatteryLow`, `ObstacleDetected`, `RobotReady` and `RobotSleeping`.

BX1 has exactly seven logical LED addresses: head/mouth is zero and body is one
through six. The service enforces this count. Default event bindings animate
only the body zone, leaving LED 0 to the existing audio-reactive mouth path.
The existing runtime mouth implementation has not been replaced or modified.

Motor commands pass through validation, inversion/address mapping and an audit
log. `RS485Transport` cannot open a serial port and never transmits in Phase 1B,
even if configuration mistakenly enables RS485 or disables dry-run. The default
remains:

```json
{
  "drive_enabled": false,
  "drive_dry_run": true,
  "rs485_enabled": false
}
```

The current application startup is intentionally not switched to this new
service graph in Phase 1B. Configuration selects `digital_twin`, and physical
adapters require explicit dependency injection. Deployment, platform-driver
integration, MCU protocol definition and hardware acceptance testing belong to
a later, separately authorized phase.

## Phase 2 power-management boundary

Power management extends the hardware-services package without adding a live
driver path. `create_power_services()` returns the stable service graph:

```text
CapabilityRegistry
        |
EventBus +-- BatteryService -- BatteryStateMachine
        |          |                 (battery-specific lifecycle)
        |          +-- BatteryMonitorBase
        |          |       +-- MockBatteryMonitor
        |          |       +-- INA219/INA226/INA228 placeholders
        |          +-- BMSBase
        |                  +-- MockBMS
        |                  +-- Smart/Passive/HardwareOnly placeholders
        |
        +-- PowerService -- budgets, runtime, rails, movement/charge policy
                                      |
                                DockInterface (contract only)
```

The battery state machine is intentionally separate from
`HardwareStateManager`. Hardware lifecycle describes whether an adapter is
fitted and operational; battery lifecycle describes energy and charge state:
`NOT_FITTED`, `INITIALISING`, `READY`, `LOW`, `CRITICAL`, `CHARGING`, `FULL`,
`FAULT` and `SHUTDOWN_PENDING`.

`BatteryService` consumes coherent per-cell measurements and exposes pack
voltage, current, signed power, temperature, state of charge, runtime, charging
state and health. Cell imbalance is derived from individual cell values rather
than inferred from pack voltage. `PowerService` owns system budget allocation,
required-rail health, remaining runtime, movement eligibility, charge
eligibility and shutdown policy.

Power events use the same hardware-independent Event Bus. Phase 2 adds
`BatteryCritical`, `BatteryCharging`, `BatteryFull`, `BatteryFault`,
`PowerRailFault`, `PowerRestored`, `ShutdownRequested`, `ShutdownCancelled`,
`BatteryRemoved` and `BatteryInserted`; the existing `BatteryLow` event remains
the low-energy notification.

All checked-in configurations select `digital_twin`, `mock` monitor/BMS
backends, an interface-only disabled dock, and simulated capability metadata.
Selecting a non-mock backend without an explicitly injected future adapter is
rejected. Phase 2 imports no GPIO, ADC, I2C or serial library and is not wired
into Robot startup.

## Phase 3 core operating-system boundary

Phase 3 adds a composition and governance layer above the hardware/power
services:

```text
Brain
  |
  v
BX1 Root API (`bx1`)
  |
  +-- ServiceRegistry
  +-- SchedulerService
  +-- LoggingService
  +-- DiagnosticsService
  +-- HealthMonitor
  +-- EventBus / CapabilityRegistry
  |
  v
LED | Drive | Range | Battery | Power
  |
  v
Digital Twin adapters
```

`Robot/python/bx1.py` is the future public entry point. It exposes events,
power, battery, drive, LED, range, scheduler, logging, diagnostics, health and
capabilities, plus `service(name)` for discovery. Importing it constructs safe
Digital Twins only. Existing Robot startup does not import it.

`ServiceRegistry` validates dependencies and orders lifecycle operations.
`SchedulerService` is cooperative: timers, heartbeats and tick callbacks execute
only when `tick()` is called, with no background thread. `LoggingService`
retains structured records in bounded memory; file logging is a disabled future
sink. `DiagnosticsService` aggregates every registered service, while
`HealthMonitor` separately detects missing, faulted, stale and recovered
services and publishes health-change events.

Checked-in `core_services` configuration enforces cooperative scheduling,
in-memory logging, bounded diagnostics and periodic health checks. The Phase 3
root is intentionally not connected to runtime startup or live hardware.

## Phase 4 communication boundary

Phase 4 adds the versioned external boundary above the BX1 API:

```text
Brain / Simulator / Future Tools
              |
              v
Communication Framework
  JSON protocol | sessions | routing | state synchronisation
              |
              v
BX1 Root API
              |
              v
Core Services
              |
              v
Hardware and Power Services
              |
              v
Digital Twins
```

`bx1.communication` is the only supported external entry point. Its exact
message envelope carries protocol version, message ID, timestamp, sender,
destination, command, payload, response and status. The codec validates the
complete envelope and bounded message size before a request reaches the command
router.

The command router invokes BX1 service APIs rather than implementation
adapters. Session management provides client registration, version negotiation,
heartbeat and cooperative timeout detection. Capability negotiation is derived
from the registry, while state synchronisation provides change-driven battery,
health, diagnostics and Event Bus updates.

The Phase 4 transport is a bounded, destination-aware in-memory Message Bus.
There are no sockets, HTTP, WebSockets, MQTT or serial connections. A future
transport must remain behind the same service boundary and add authentication,
authorisation, encryption, replay prevention, rate limits and back-pressure
before physical or remote operation is permitted.

Checked-in configuration selects protocol `1.0.0`, in-memory transport and
bounded clients, messages and queues. Communication advances through the
existing cooperative Scheduler. Runtime startup remains unchanged.

## Phase 5 BX1 OS Alpha runtime integration

Phase 5 makes BX1 OS the service owner for the existing Robot runtime:

```text
Existing Robot startup
        |
        v
BX1 OS Alpha Bootstrap
  configuration | composition | dependency validation
        |
        v
BX1 Root API (`bx1`)
        |
        +-- Service Registry / Scheduler
        +-- Events / Logging / Diagnostics / Health
        +-- Communication
        +-- Hardware and Power Digital Twins
        +-- runtime_hardware compatibility adapter
        |
        v
Existing BX1RobotBodyService client
  wake | speech | Brain link | web | telemetry
```

Normal standalone and App Lab startup now load the existing configuration
through the Alpha bootstrap. The public `bx1` proxy is bound only after the
dependency graph, lifecycle, Scheduler, Health Monitor and in-memory
Communication Service pass validation. Failure produces a structured report,
stops the partial graph and does not start Robot worker loops.

The existing `BX1HardwareBridge` is registered as `runtime_hardware` behind a
compatibility adapter. This changes ownership, not its public interface or
transport selection. Existing action packets, status reads, hardware-doctor
calls and App Lab/Router RPC/serial fallbacks continue through the same
delegate. Direct construction remains available only when the Robot body is
created without a BX1 root.

The existing 250 ms body tick now advances the cooperative BX1 Scheduler. No
new Scheduler thread is created. Diagnostics add startup time, service states,
dependency graph, redacted configuration summary, Communication status and the
Alpha startup report.

Phase 5 does not enable hardware, change firmware, alter balancing/motor/servo
behaviour, or add a communication transport.

## Phase 6 permanent deployment boundary

BX1 OS releases are distributed as immutable, hashed payloads with an explicit
file manifest. The Robot-side deployer verifies the package, creates and
validates a complete recovery backup, and only then stops the current service.

```text
Hashed release
    |
    v
Backup program + config + systemd + startup
    |
    v
Install protected payload
    |
    v
Enable/restart bx1-web.service
    |
    v
Bootstrap + service + bridge + Brain + web qualification
    |
    +-- pass --> deployment report
    |
    +-- fail --> exact-manifest rollback --> previous service
```

`config.json`, Brain settings, profiles, calibration, Wi-Fi, virtual
environments, models, runtime data and backups are outside the release payload.
Firmware is explicitly excluded. Rollback restores the pre-deployment program,
configuration hash, service file, drop-ins and enabled state before restarting
the previous version.
