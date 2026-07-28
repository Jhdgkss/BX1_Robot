# BX1 OS Alpha v0.3.0 Release Notes

## Summary

BX1 OS Alpha v0.3.0 introduces BX1 OS Core: a thread-safe, observer-only state,
event, plugin, health and telemetry layer. The Management Interface now gets
its visible runtime values exclusively from Core read-only APIs.

## Added

- central dotted-path state database with immutable snapshots, monotonic
  revisions and bounded incremental history;
- Core event bus with publish, subscribe, unsubscribe, wildcard subscriptions
  and subscriber-failure isolation;
- transport-neutral JSON telemetry snapshots and incremental updates;
- automatic plugin discovery and lifecycle supervision;
- System, Network and Deployment observers;
- Brain and Hardware ownership-free placeholders;
- per-plugin and aggregate health contracts;
- cooperative, thread-free Core update scheduler;
- read-only Core state, health, plugin, service and system endpoints;
- Core architecture and plugin developer documentation; and
- deterministic Core and API tests requiring no robot hardware.

## Management integration

The dashboard now renders Core-owned CPU, memory, disk, temperature, uptime,
network, IP, release, Brain, robot and service state. `bx1_management` no longer
imports `platform` or `socket`. The legacy bootstrap endpoint remains only as a
Core-derived compatibility projection.

## Safety

- observer-only remains mandatory;
- the Hardware plugin opens no device and records ownership as false;
- the Brain plugin opens no connection;
- all management POST requests remain disabled;
- port 8088 and `bx1-web.service` remain protected;
- the existing Robot Body UI is unchanged; and
- no robot was connected to or deployed to while producing this release.

## Release identity

- Version: `0.3.0`
- Tag: `BX1_OS_ALPHA_v0.3.0`
- Default mode: install-only
- Install root: `/home/arduino/BX1_OS`
- Service: `bx1-os-alpha.service`
- Qualification port: `8089`
