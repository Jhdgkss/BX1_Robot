# BX1 Battery Architecture

## BatteryService

`BatteryService` is the normalized battery API used by the rest of BX1 OS.
It consumes a coherent `BatteryMeasurement` from `BatteryMonitorBase`, combines
it with BMS faults/output state, evaluates thresholds and advances the separate
`BatteryStateMachine`.

Public API:

```python
battery.status()
battery.health()
battery.diagnostics()
battery.configuration()
battery.pack_voltage()          # volts
battery.pack_current()          # amps; positive discharge, negative charge
battery.pack_power()            # signed watts
battery.battery_temperature()   # degrees C
battery.state_of_charge()       # percent
battery.estimated_runtime()     # seconds, or None
battery.charging_state()
battery.battery_health()
```

Per-cell API:

```python
battery.cell_voltage(1)
battery.cell_voltage(2)
battery.cell_voltage(3)
battery.cell_voltages()
battery.balance_error()         # max cell - min cell, volts
```

The default pack is three cells. The data model supports a configured cell count
so future platforms can reuse the service API.

## Coherent measurements

One `BatteryMeasurement` contains:

- individual cell voltages;
- pack voltage;
- pack current;
- signed pack power;
- battery temperature;
- state of charge;
- available/healthy flags;
- fault reason;
- charging flag;
- optional runtime override;
- monotonic sample timestamp.

Pack voltage in the Digital Twin is the sum of cell voltages. Pack power is
voltage multiplied by current. A positive current represents discharge; a
negative current represents charging.

Runtime without an override is:

```text
nominal capacity Wh x state of charge / discharge power W x 3600
```

Runtime is unknown while charging or when measured discharge power is not
positive.

## Battery monitor abstraction

`BatteryMonitorBase.read()` returns one `BatteryMeasurement`.

Available classes:

- `MockBatteryMonitor`: the only Phase 2 implementation that returns values;
- `INA219Monitor`: inert interface placeholder;
- `INA226Monitor`: inert interface placeholder;
- `INA228Monitor`: inert interface placeholder.

The INA placeholders are `NOT_FITTED`; `read()` raises a clear placeholder
error. They do not import SMBus/I2C libraries or inspect an address.

INA228 is the preferred future monitor because its measurement range and
precision are better suited to high-side pack current and energy diagnostics.
Selection still depends on final voltage, shunt and isolation design.

## BMS abstraction

`BMSBase` reserves:

```python
enable_output()
disable_output()
faults()
temperature()
cell_voltages()
balancing_state()
reset_fault()
output_enabled()
```

`MockBMS` is in-memory only. `SmartBMS`, `PassiveBMS` and `HardwareOnlyBMS` are
inert future placeholders. Their query methods report no available telemetry and
their output-control methods cannot operate hardware.

The final BMS must remain authoritative for electrical protection. Software
health must never be treated as a replacement for overcurrent, overvoltage,
undervoltage and thermal hardware protection.

## Battery state machine

The battery lifecycle is separate from generic hardware lifecycle:

```text
NOT_FITTED
    |
    v
INITIALISING
    |
    +--> READY <----> LOW <----> CRITICAL
    |      |           |            |
    |      +-----------+------------+--> CHARGING --> FULL
    |                  |                 |
    +------------------+-----------------+--> FAULT
                       |
                       +--> SHUTDOWN_PENDING
```

Legal transitions:

| From | To |
| --- | --- |
| `NOT_FITTED` | `INITIALISING` |
| `INITIALISING` | any operational state, `FAULT`, `SHUTDOWN_PENDING`, `NOT_FITTED` |
| `READY` | `LOW`, `CRITICAL`, `CHARGING`, `FULL`, `FAULT`, `SHUTDOWN_PENDING`, `NOT_FITTED` |
| `LOW` | `READY`, `CRITICAL`, `CHARGING`, `FULL`, `FAULT`, `SHUTDOWN_PENDING`, `NOT_FITTED` |
| `CRITICAL` | `READY`, `LOW`, `CHARGING`, `FULL`, `FAULT`, `SHUTDOWN_PENDING`, `NOT_FITTED` |
| `CHARGING` | `READY`, `LOW`, `CRITICAL`, `FULL`, `FAULT`, `SHUTDOWN_PENDING`, `NOT_FITTED` |
| `FULL` | `READY`, `LOW`, `CRITICAL`, `CHARGING`, `FAULT`, `SHUTDOWN_PENDING`, `NOT_FITTED` |
| `FAULT` | `INITIALISING`, `SHUTDOWN_PENDING`, `NOT_FITTED` |
| `SHUTDOWN_PENDING` | any measured state, `INITIALISING`, `FAULT`, `NOT_FITTED` |

Recovery from `FAULT` passes through `INITIALISING`. Insertion similarly passes
from `NOT_FITTED` through `INITIALISING`.

Default threshold order:

```text
fault / unsafe temperature / severe imbalance
shutdown at or below 5%
critical at or below 10%
low at or below 20%
full at or above 98%
```

Charging takes precedence over low/critical classification unless the shutdown
threshold, a fault or an unsafe measurement applies.

## Cell imbalance and health

Balance error is:

```text
highest cell voltage - lowest cell voltage
```

The default warning threshold is 0.10 V and the fault threshold is 0.25 V.
A warning degrades `battery_health()` without changing a usable state. Exceeding
the fault threshold moves the battery to `FAULT`. Final thresholds must be
selected for the actual cell chemistry and BMS behavior.

Health also includes:

- monitor availability and fault reason;
- BMS faults;
- BMS output state;
- temperature limits;
- individual cell voltages;
- balance warning/fault;
- current battery state.

## Events

State transitions publish:

| Battery state/transition | Event |
| --- | --- |
| `LOW` | `BatteryLow` |
| `CRITICAL` | `BatteryCritical` |
| `CHARGING` | `BatteryCharging` |
| `FULL` | `BatteryFull` |
| `FAULT` | `BatteryFault` |
| `SHUTDOWN_PENDING` | `ShutdownRequested` |
| transition to `NOT_FITTED` | `BatteryRemoved` |
| `NOT_FITTED` to `INITIALISING` | `BatteryInserted` |

Events include previous/current state, reason and state of charge. Consumers
must still query current service state because a later transition may supersede
an earlier event.

## Battery Digital Twin

`BatteryDigitalTwin` contains `MockBatteryMonitor`, `MockBMS`,
`BatteryService`, `PowerService`, `CapabilityRegistry` and `EventBus`.

Controls:

```python
twin.set_voltage(11.7)
twin.set_current(2.0)
twin.set_temperature(30)
twin.set_capacity(50)          # 50%, or 0.5
twin.set_runtime(3600)         # seconds; None returns to calculated runtime
twin.set_cell_voltage(2, 3.85)
twin.set_fault("overtemperature")
twin.set_fault(None)
twin.set_charging(True)
```

`set_fitted()` is also available for removal/insertion fault tests. Simulation
controls call the same services and Event Bus observed by future higher-level
code.

## Future hardware impact

### Custom Power Board

The board can aggregate protected pack voltage/current, regulated rail status,
charger presence and temperatures behind one future monitor/rail adapter.
Capability metadata can advertise board revision and available sensors.

### Smart BMS

A protocol-specific class can implement `BMSBase` without altering
`BatteryService`. Cell voltages, fault latches, output state and balancing remain
the stable boundary.

### INA228

The future adapter only needs to produce coherent measurements. Shunt value,
calibration, conversion timing and I2C transport remain private to that adapter.

### Charging dock and autonomy

`DockInterface` separates docking mechanics from charging evidence.
`PowerService.can_charge()` remains the policy gate while a future dock adapter
reports detection, charger voltage/current and charge state.

### Diagnostics and other platforms

Per-cell history, balance trends, pack identity, cycle count and internal
resistance can be added to diagnostics without changing current accessors.
Configurable cell count and capability discovery let later BX1 variants reuse
the services.

## Safety requirements before physical integration

- Select chemistry-specific cell, temperature and charge thresholds.
- Validate shunt power rating, isolation and high-side measurement range.
- Keep hardware BMS protection independent from Linux/Python.
- Add authenticated/versioned transport and freshness evidence.
- Treat stale telemetry as unsafe.
- Make output and charger commands idempotent and fail-safe.
- Require manual bench authorization before energizing a motor or charger load.
- Prove safe shutdown under monitor loss, BMS fault and rail collapse.
