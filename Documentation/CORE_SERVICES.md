# BX1 OS Core Services

## System position

Phase 3 introduces a single composition root above all permanent services:

```text
                         Brain
                           |
                           v
                    +-------------+
                    |   BX1 API   |
                    |    bx1      |
                    +-------------+
                           |
             +-------------+--------------+
             |             |              |
             v             v              v
      ServiceRegistry  Scheduler      EventBus
      LoggingService   Diagnostics    HealthMonitor
             \             |              /
              +------------+-------------+
                           |
                           v
         +--------------------------------------+
         | Hardware and Power Service APIs      |
         | LED | Drive | Range | Battery | Power|
         +--------------------------------------+
                           |
                           v
                 Digital Twin adapters
```

The Brain consumes the BX1 API and does not construct hardware adapters,
coordinate dependency order or inspect implementation types. Phase 3 is not
wired into the existing Robot runtime startup.

## BX1 root API

The public module is `Robot/python/bx1.py`:

```python
from bx1 import bx1

bx1.events
bx1.power
bx1.battery
bx1.drive
bx1.led
bx1.range
bx1.scheduler
bx1.logging
bx1.diagnostics
bx1.health
bx1.capabilities
bx1.communication

battery = bx1.service("battery")
```

Importing the module creates a safe default Digital Twin graph. It does not read
the live Robot configuration, modify startup or access hardware.

Applications that need an isolated graph or explicit configuration use:

```python
from bx1_core import create_bx1

system = create_bx1(config)
```

Future services attach through the registry:

```python
bx1.attach(
    "navigation",
    navigation_service,
    dependencies={"range", "drive", "events"},
)
```

Registered future services are also available through `bx1.service(name)` and
attribute fallback (`bx1.navigation`).

## Service Registry

`ServiceRegistry` owns discovery, dependency validation and lifecycle.

Primary API:

```python
registry.register(name, service, dependencies={...})
registry.unregister(name)
registry.service(name)
registry.get(name)
registry.has(name)
registry.discover()
registry.dependencies(name)
registry.dependents(name)
registry.start(name)
registry.stop(name)
registry.start_all()
registry.stop_all()
```

Lifecycle states:

```text
REGISTERED -> STARTING -> RUNNING -> STOPPING -> STOPPED
                   \                    /
                    +------> FAULT <---+
```

Dependencies are started before consumers and stopped after their dependents.
Missing dependencies, cycles, duplicate registration, and unsafe
unregister/stop operations are rejected. Services without explicit
`start()`/`stop()` methods participate as immediately running/stopped logical
services.

The default graph is:

```text
events --------------------+----> led
                           +----> battery ----> power
capabilities --------------+         \           ^
                           +----------+-----------+
logging ------------------------> drive
diagnostics + events -----------> health
scheduler ----------------------> cooperative health checks
range --------------------------> independent sensor service
```

## SchedulerService

The scheduler is cooperative and creates no worker thread. Callbacks run only
when the owner calls `bx1.tick()` or `scheduler.run_pending()`.

```python
scheduler.schedule_periodic(1.0, sample, name="sample")
scheduler.schedule_once(5.0, expire, name="expiry")
scheduler.call_later(0.25, callback)
token = scheduler.add_tick_callback(on_tick)
scheduler.cancel(task_id)
scheduler.remove_tick_callback(token)
scheduler.tick()
scheduler.heartbeat()
```

One-shot, delayed and periodic callbacks are isolated from each other: one
exception is recorded and does not prevent later callbacks in the same tick.
`max_callbacks_per_tick` bounds work. Missed periodic intervals are coalesced
instead of replaying an unbounded backlog.

The heartbeat reports tick count, last tick, age and cooperative status. It is
not a hardware watchdog; future runtime integration must call `tick()` at a
reliable cadence.

## LoggingService

Logging is structured and held in a bounded memory buffer:

```python
bx1.logging.debug("detail", service="vision", frame=42)
bx1.logging.info("ready")
bx1.logging.warning("battery low", state_of_charge=15)
bx1.logging.error("service fault", service="range", code="STALE")

log = bx1.logging.service("battery")
log.info("sample", voltage=12.1)
```

Each record contains timestamp, level, service, message and context. Filtering
supports `DEBUG`, `INFO`, `WARNING` and `ERROR`.

Future sinks can be injected with `add_sink()`. Sink exceptions are isolated.
File configuration is reserved, but Phase 3 rejects
`file_logging_enabled: true` and never opens a file.

## DiagnosticsService

`bx1.diagnostics.report()` calls `status()`, `health()` and `diagnostics()` on
every registered service. Optional configuration snapshots are disabled by
default.

Report schema:

```text
bx1.diagnostics.v1
  timestamp
  overall_state: HEALTHY | DEGRADED | FAULT
  service_count
  faulted[]
  stale[]
  degraded[]
  missing[]
  services{
    name: lifecycle, status, health, diagnostics, errors
  }
  registry
```

Missing required services or collection faults produce `FAULT`. Stale or
unhealthy operational services produce `DEGRADED`. `DISABLED`, `NOT_FITTED` and
`STOPPED` are explicit inactive states rather than diagnostic collection
failures.

Collector exceptions are contained within the report so one broken service
cannot suppress evidence from the rest of the system.

## HealthMonitor

The Health Monitor independently checks:

- missing required services;
- registry lifecycle faults;
- service `FAULT`/`ERROR` state;
- `STALE` state;
- unhealthy operational services;
- recovery to healthy state.

It publishes:

- `ServiceHealthChanged`
- `ServiceFault`
- `ServiceRecovered`
- `ServiceMissing`
- `ServiceStale`

The default first check establishes a baseline without flooding the Event Bus.
Later classification/state/health changes emit a general event plus the
specialized event where applicable.

The Health Monitor's own `health()` describes whether monitoring is operating;
system health is returned separately in `status()` and `check()`. This avoids
mistaking a correctly detected downstream fault for a monitor implementation
fault.

## Configuration

Every checked-in Robot configuration contains:

```json
{
  "core_services": {
    "service_registry": {
      "allow_replace": false,
      "auto_start": true
    },
    "scheduler": {
      "enabled": true,
      "cooperative": true,
      "max_callbacks_per_tick": 100,
      "heartbeat_interval_s": 1.0
    },
    "logging": {
      "enabled": true,
      "level": "INFO",
      "buffer_size": 1000,
      "file_logging_enabled": false,
      "file_path": ""
    },
    "diagnostics": {
      "enabled": true,
      "include_service_diagnostics": true,
      "include_configuration": false,
      "history_limit": 20
    },
    "health_monitor": {
      "enabled": true,
      "interval_s": 1.0,
      "publish_initial": false
    }
  }
}
```

`load_core_configuration()` accepts a full Robot config or core-only mapping,
deep-merges defaults and rejects non-cooperative scheduling or active file
logging in Phase 3.

## Phase 3 safety boundary

- No runtime startup file imports or constructs the BX1 root API.
- The default root creates only Digital Twin hardware and battery services.
- The Scheduler creates no thread.
- Logging creates no file.
- Diagnostics and health checks are read-only service calls.
- The core package imports no GPIO, I2C, ADC, serial, SPI or vendor hardware
  library.
- Core services do not import motor or LED implementation modules.
- Registry lifecycle does not arm disabled hardware services.

Phase 5 supersedes the first item by integrating the root through the validated
BX1 OS Alpha bootstrap. Core services remain cooperative and hardware-free;
the existing runtime bridge is attached through a compatibility adapter.

## Future roadmap and technical considerations

Before runtime integration:

1. Define the owner and cadence for cooperative `bx1.tick()`.
2. Add shutdown ordering and time budgets for asynchronous services.
3. Decide whether slow diagnostics require cached or asynchronous collection.
4. Add stable service/interface version metadata.
5. Add structured fault codes and correlation IDs across logs/events.
6. Add optional authenticated remote diagnostics redaction.
7. Implement log persistence through an injected sink with rotation and storage
   limits.
8. Add scheduler monotonic-time jump and callback-duration telemetry.
9. Add health hysteresis to prevent noisy physical sensors causing event churn.

## Phase 3 architectural changelog

- Added the single BX1 public API and Digital Twin composition root.
- Added dependency-aware service discovery and lifecycle.
- Added cooperative periodic, delayed, one-shot and tick scheduling.
- Added scheduler heartbeat and bounded callback execution.
- Added structured in-memory logging and bound service loggers.
- Added combined diagnostics collection and report schema.
- Added missing/fault/stale/recovery health monitoring.
- Added service-health Event Bus vocabulary.
- Added safe core configuration sections and validation.
- Added future service attachment through the BX1 root.
