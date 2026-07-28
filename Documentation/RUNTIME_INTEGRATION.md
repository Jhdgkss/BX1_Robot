# BX1 OS Alpha Runtime Integration

## Purpose

Phase 5 is the first runtime integration milestone. BX1 OS now owns service
creation, discovery, lifecycle, scheduling, events, health, diagnostics and
in-memory communication for the existing Robot application.

The existing `BX1RobotBodyService` remains responsible for its established
wake-word, speech, Brain connection, camera, web and user interaction
behaviour. It consumes BX1 services but its behavioural code and external APIs
are unchanged.

This milestone is **BX1 OS Alpha**.

## Startup flow

```text
Robot process
    |
    v
Existing load_config()
  - same config path
  - same command-line/environment overrides
  - same legacy normalisation
    |
    v
bootstrap_bx1_runtime()
  - create isolated BX1 root
  - create Digital Twin hardware/power services
  - attach existing bridge as runtime_hardware
  - validate dependency graph
  - start Service Registry
  - tick cooperative Scheduler
  - run Health Monitor
  - verify Communication Service
  - generate startup report
    |
    +---- failure ----> structured report + stop partial graph + no Robot loops
    |
    v
Atomically bind public `bx1` root
    |
    v
Create BX1RobotBodyService as a BX1 client
    |
    v
Start the unchanged web, telemetry, wake, speech and camera paths
```

Configuration is loaded once. Binding occurs only after successful validation,
so code that imports `from bx1 import bx1` sees either the safe lazy Digital
Twin or the fully validated Alpha root, never a partial runtime graph.

## Bootstrap API

The reusable core entry point is:

```python
result = bootstrap_runtime(
    config_loader=load_config,
    service_factories={...},
    service_dependencies={...},
    required_services={...},
)
```

The public singleton-binding entry point is:

```python
from bx1 import bootstrap_bx1_runtime, bx1

result = bootstrap_bx1_runtime(...)
bx1.communication.status()
```

`BootstrapResult` contains:

- the validated `BX1` instance;
- the unmodified loaded runtime configuration; and
- the structured startup report.

`BootstrapError` includes the failure report so startup code can print clear
diagnostics without starting Robot loops.

## Startup validation

Alpha startup verifies:

- every required service is registered;
- every required lifecycle state is `RUNNING`;
- all dependencies exist;
- the dependency graph is acyclic;
- the cooperative Scheduler has completed a tick and has a live heartbeat;
- Communication is healthy and remains in-memory;
- the Health Monitor is ready and has completed a check; and
- the runtime compatibility bridge is owned by the registry.

The startup report uses schema `bx1.runtime.startup.v1` and records:

- milestone and success;
- start/completion time and duration;
- registered and required services;
- lifecycle states;
- missing services;
- dependency graph, order and validation errors;
- Scheduler, Communication and Health results;
- a redacted configuration summary; and
- fail-safe errors.

No API keys, Brain URL, microphone name or other potentially sensitive runtime
values are included in the configuration summary.

## Runtime ownership

| Concern | Owner in Alpha | Compatibility behaviour |
|---|---|---|
| Service construction | BX1 bootstrap | Composition occurs before Robot loops |
| Service discovery | `bx1.services` | `bx1.service(name)` |
| Lifecycle | `ServiceRegistry` | Existing services without lifecycle methods remain valid |
| Scheduler | `bx1.scheduler` | Ticked cooperatively by the existing body loop |
| Events | `bx1.events` | Hardware-independent Event Bus |
| Health | `bx1.health` | Existing Robot diagnostics remain present |
| Diagnostics | `bx1.diagnostics` | Runtime architecture is added to reports |
| Communication | `bx1.communication` | In-memory protocol only |
| Existing MCU bridge | `runtime_hardware` | Exact bridge interface delegated unchanged |
| Wake and speech | `BX1RobotBodyService` client | No algorithm or timing changes |
| Brain connection | `BX1RobotBodyService` client | Existing client and endpoints unchanged |
| Web interface | `BX1RobotBodyService` client | Existing routes remain compatible |

## Hardware compatibility adapter

The existing `BX1HardwareBridge` is constructed with the same configuration,
at the same startup stage, and wrapped by `CompatibilityServiceAdapter`.

```text
BX1 Service Registry
        |
        v
runtime_hardware
CompatibilityServiceAdapter
        |
        v
existing BX1HardwareBridge
        |
        v
existing App Lab / Router RPC / serial fallback logic
```

The adapter supplies `start()`, `stop()`, `status()`, `health()`,
`diagnostics()` and `configuration()` for BX1 lifecycle management. Every
unknown attribute and method is delegated to the original bridge object. It
does not poll hardware during bootstrap and does not change transport
selection.

The Robot body resolves the adapter through:

```python
self.hardware = resolve_runtime_hardware(config, self.bx1)
```

If no BX1 root is supplied, `resolve_runtime_hardware()` retains the original
direct-construction fallback. This protects existing unit tools and recovery
paths without allowing normal Alpha startup to bypass validation.

## Dependency graph

```text
events
  +--> led
  +--> battery --> power
  +--> health
  +--> communication
  +--> runtime_hardware

capabilities
  +--> battery
  +--> power
  +--> communication

logging
  +--> drive
  +--> runtime_hardware

scheduler
  +--> communication

diagnostics
  +--> health
  +--> communication

health
  +--> communication

range
power
communication
runtime_hardware
```

The registry exposes `dependency_graph()` and `validate_dependencies()` for
startup validation and diagnostics.

## Service lifecycle

```text
REGISTERED
    |
    v
STARTING
    |
    +------ exception ------> FAULT
    |
    v
RUNNING
    |
    v
STOPPING
    |
    +------ exception ------> FAULT
    |
    v
STOPPED
```

Dependencies start before dependants. Shutdown uses reverse dependency order.
If an invalid graph prevents ordered shutdown during a failed bootstrap, the
bootstrap attempts an individual safe stop for every registered service.

## Scheduler integration

The existing body loop remains at its current 250 ms cadence. Each call now
advances `bx1.tick()` before the existing sleep. No Scheduler thread was added.
Wake, audio, camera, telemetry and web threads remain owned and timed by the
existing runtime.

Scheduler callback failures are added to the existing web event log. They do
not silently terminate the body loop.

## Diagnostics integration

`bx1.diagnostics.report()` now includes a `runtime` section containing:

- startup time and uptime;
- registered services and lifecycle states;
- dependency graph and validation;
- redacted configuration summary;
- Communication status and health; and
- the Alpha startup report.

The existing web snapshot gains an additive `bx1_os` object. Existing fields,
routes and response shapes are otherwise unchanged.

## Compatibility assessment

Unchanged runtime paths:

- wake matching, microphone ownership and STT;
- speech generation, audio output and mouth-light callbacks;
- Brain API configuration, telemetry and conversation calls;
- web server routes and existing snapshot fields;
- Robot configuration loading and normalisation;
- hardware action packets and bridge fallback priority;
- motor, servo, LED and balancing behaviour;
- existing hardware doctor and diagnostics;
- App Lab and standalone entry points.

The integration adds ownership and diagnostics around these paths; it does not
replace their implementations.

## Safety boundary

- No firmware file or deployment script is changed by Phase 5.
- Bootstrap does not open serial, GPIO, ADC, I2C or network connections.
- No new hardware service is enabled.
- The Phase 1 drive service remains disabled and dry-run.
- Communication remains in-memory.
- The compatibility adapter does not call bridge status or action methods at
  startup.
- A failed bootstrap does not start Robot worker loops.
- Existing hardware and transport fallbacks remain available.

## Remaining integration work

1. Define BX1 service interfaces for audio, camera, Brain link and web runtime.
2. Move those services into bootstrap factories one at a time with contract
   tests.
3. Replace the compatibility bridge with device-specific adapters only after
   their physical validation plans are approved.
4. Add a dedicated startup-report view to the existing web diagnostics page.
5. Add authenticated local communication clients before exposing a transport.
6. Add graceful shutdown deadlines and per-service shutdown diagnostics.
7. Run an approved on-robot behavioural qualification before declaring Beta.

## Phase 5 architectural changelog

- Added atomic BX1 OS Alpha runtime bootstrap.
- Added structured bootstrap failures and startup reports.
- Added public dependency graph and validation APIs.
- Added stable lazy `bx1` proxy binding.
- Added lifecycle/introspection compatibility adapter.
- Moved normal Robot bridge ownership into the Service Registry.
- Connected the cooperative Scheduler to the existing body tick.
- Extended diagnostics with runtime ownership and startup information.
- Added an additive BX1 OS web snapshot.
- Retained the legacy bridge-construction fallback.
- Kept all communication in-memory and all new hardware disabled.
