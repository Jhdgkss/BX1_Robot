# BX1 Power System

## Architecture and ownership

BX1 OS power policy is Robot-side safety infrastructure. The Brain may ask
whether motion or charging is possible, but it cannot bypass battery state,
power budgets, rail faults, output state or shutdown policy.

Phase 2 is simulation-only:

```text
Behavior / future Brain integration
                |
        create_power_services()
                |
        +-------+-------------------+
        |                           |
  BatteryService               PowerService
        |                           |
  BatteryMonitorBase          Power budgets
        |                      Runtime estimate
  BMSBase                     Rail state
                               can_move()
  BatteryStateMachine          can_charge()
                               shutdown policy
        |
  EventBus + CapabilityRegistry
```

`PowerServices` is the stable container returned in both Digital Twin and future
adapter-backed modes. Physical adapters must be explicitly injected. Factory
construction does not discover a bus or open a device.

## PowerService responsibilities

`PowerService` owns:

- total system power budget;
- reserved power and named load allocation;
- remaining runtime reporting;
- system power state;
- movement eligibility;
- charging eligibility;
- shutdown request/cancellation;
- required and optional rail state;
- rail-fault/restoration event publication.

Public API:

```python
power.status()
power.health()
power.diagnostics()
power.configuration()
power.available_power()       # watts
power.remaining_runtime()     # seconds, or None
power.can_move()
power.can_charge()
power.shutdown_required()
```

Simulation and platform integration helpers include:

```python
power.set_load("compute", 45, essential=True)
power.remove_load("compute")
power.set_rail("logic_5v", False, voltage_v=0, reason="simulated")
power.request_shutdown("operator request")
power.cancel_shutdown()
power.refresh()
```

Available power is:

```text
system budget - reserved power - named loads
```

and is clamped at zero. `can_move()` additionally requires a ready/full battery,
BMS output enabled, healthy required rails and the configured movement reserve.
Low, critical, charging, fault and shutdown states do not permit movement.

`can_charge()` requires charging policy enabled, a discoverable battery monitor
capability and a battery that is fitted and not full, faulted or shutting down.
It does not start a charger or switch a battery.

## System power states

`PowerService` derives one of:

- `READY`
- `CONSERVATION`
- `CRITICAL`
- `CHARGING`
- `FULL`
- `FAULT`
- `SHUTDOWN_PENDING`

A required rail fault or battery fault produces `FAULT`. Battery `LOW` maps to
`CONSERVATION`; battery `CRITICAL`, charging, full and shutdown states map
directly to their system equivalents.

## Rail monitoring

Rails are named configuration records:

```json
{
  "logic_5v": {"required": true, "healthy": true},
  "compute_12v": {"required": true, "healthy": true},
  "motor_bus": {"required": false, "healthy": true}
}
```

Phase 2 only changes these records through test/Digital Twin calls. It samples
no voltage, GPIO or ADC. A healthy-to-fault transition publishes
`PowerRailFault`; recovery publishes `PowerRestored`. A required rail fault
blocks motion and requires shutdown. Optional rails are diagnostic evidence but
do not independently require shutdown.

## Event flow

```text
Mock monitor/BMS control
        |
BatteryService.refresh()
        |
BatteryStateMachine transition
        |
EventBus ---------------------------------------------------+
        |                                                   |
BatteryLow / BatteryCritical / BatteryCharging / BatteryFull|
BatteryFault / BatteryRemoved / BatteryInserted             |
ShutdownRequested                                           |
                                                            |
PowerService rail change -> PowerRailFault / PowerRestored  |
PowerService recovery    -> ShutdownCancelled --------------+
```

Events describe state; they do not grant actuator authority. Consumers must
query `can_move()`, `can_charge()` and `shutdown_required()` at the point of use.

## Capability Registry

`CapabilityRegistry` prevents assumptions about installed hardware:

```python
registry.has("battery_monitor")
registry.query(camera=True, power_monitor=True)
registry.register(
    "custom_power_board",
    True,
    simulated=True,
    metadata={"revision": "A"},
)
```

Each capability records availability, whether it is simulated and optional
metadata. Registry status, diagnostics and configuration are queryable. Future
services should test capabilities before offering actions, while still relying
on the target service's health and safety checks.

## Docking contract

`DockInterface` reserves:

```python
dock()
undock()
charging()
charger_voltage()
charger_current()
dock_detected()
```

There is no Phase 2 dock implementation. Configuration uses
`enabled: false` and `backend: interface_only`. Future autonomous docking must
keep navigation/alignment separate from charger authorization: detection of a
dock is not proof that charging voltage is safe.

## Configuration

All Robot configuration variants contain these sections under
`hardware_services`:

- `power_service`
- `battery_service`
- `battery_monitor`
- `bms`
- `docking`
- `capability_registry`

`load_power_configuration()` accepts either a full Robot configuration or a
service-only mapping and deep-merges safe defaults. Phase 2 accepts only:

```json
{
  "power_service": {"mode": "digital_twin"},
  "battery_monitor": {"backend": "mock"},
  "bms": {"backend": "mock"},
  "docking": {"enabled": false, "backend": "interface_only"}
}
```

## Safety philosophy

- Measurement, policy and actuation are separate layers.
- Pack-level telemetry never substitutes for individual-cell health.
- A configuration flag alone cannot instantiate a physical backend.
- Shutdown is a request/state contract; Phase 2 does not power off a computer.
- Charge eligibility is not charge-switch control.
- Dock detection is not charger validation.
- Faults and recovery are explicit events with diagnostics.
- No GPIO, ADC, I2C, serial, RS485, motor, servo, LED or battery-control path is
  imported or called.

## Future hardware roadmap

1. Define a versioned Custom Power Board telemetry/command protocol.
2. Implement an INA228 adapter behind `BatteryMonitorBase`.
3. Implement a Smart BMS adapter behind `BMSBase`.
4. Add redundant pack-current, charger-voltage and temperature validation.
5. Add immutable calibration and pack-identity records.
6. Implement a dock adapter behind `DockInterface`.
7. Add charger interlocks and supervised charge-state transitions.
8. Bench-test with protected supplies and isolated loads.
9. Integrate startup only after fault-injection and hardware acceptance tests.

## Phase 2 architectural changelog

- Added power budgeting, rail state and shutdown policy.
- Added battery monitoring and BMS contracts.
- Added separate battery state lifecycle.
- Added per-cell voltage and imbalance modeling.
- Added simulated battery/BMS and unified power factory.
- Added power/battery Event Bus vocabulary.
- Added capability-based hardware discovery.
- Reserved a stable autonomous docking API.
- Extended configuration with simulation-only safe defaults.
