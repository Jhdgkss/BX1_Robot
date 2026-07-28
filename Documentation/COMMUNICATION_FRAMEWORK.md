# BX1 OS Communication Framework

## Purpose and boundary

Phase 4 establishes the sole supported external interface into BX1 OS. It
provides a stable, versioned JSON protocol between the Brain, Robot, simulator
and future tools while keeping command execution behind the BX1 service API.

```text
Brain / Simulator / Future Tool
              |
              v
     Communication Framework
       protocol + sessions
       routing + state sync
              |
              v
          BX1 Root API
              |
              v
          Core Services
              |
              v
 Hardware Services / Digital Twins
```

Phase 4 uses bounded in-memory queues only. It creates no sockets, listeners,
HTTP endpoints, WebSockets, MQTT clients or serial links. Phase 5 makes the
service available through the validated Robot bootstrap while retaining the
same in-memory-only boundary.

## Responsibilities

### CommunicationService

`CommunicationService` is the public facade. It:

- creates, encodes and decodes protocol messages;
- sends and receives through the in-memory `MessageBus`;
- validates protocol compatibility and active client sessions;
- routes requests through `CommandRouter`;
- publishes communication events on the hardware-independent Event Bus;
- manages subscriptions through `StateSynchronizer`;
- exposes registered capabilities and protocol metadata; and
- advances session timeouts and synchronised state from cooperative `tick()`.

### Message and MessageCodec

`Message` is an immutable representation of the protocol envelope.
`MessageCodec` performs strict schema and size validation before accepting or
emitting JSON. Non-finite numbers and non-JSON payload values are rejected.

### MessageBus

`MessageBus` is a bounded, destination-addressed queue. It is the only
transport in this phase. A future transport must preserve its send/receive
contract and sit behind the communication service; command handlers must not
depend on the transport.

### CommandRouter

`CommandRouter` maps stable command names to BX1 service calls. It never calls
GPIO, buses, motors, sensors or other hardware directly. Unknown commands and
invalid payloads produce structured error responses.

### SessionManager

`SessionManager` registers clients, creates session IDs, records heartbeats,
enforces the maximum client count and expires timed-out sessions. Time is
injected for deterministic tests.

### StateSynchronizer

`StateSynchronizer` supports local callback and remote-client subscriptions.
Values are canonicalised and delivered only when they change. Initial delivery
is available so a subscriber can establish its baseline immediately.

## BX1 root API

The safe composition root exposes the framework as:

```python
from bx1 import bx1
from bx1_core import MessageStatus

registration = bx1.communication.register_client("brain")
response = bx1.communication.request("brain", "battery.status")

subscription_id = bx1.communication.subscribe(
    "battery",
    lambda update: print(update),
)

bx1.communication.send(
    destination="brain",
    command="system.info",
    status=MessageStatus.EVENT,
    response={"ready": True},
)

capabilities = bx1.communication.capabilities()
bx1.communication.unsubscribe(subscription_id)
```

The service also provides:

- `receive()` and `process_next()` for BX1-bound messages;
- `receive_for(client_id)` for destination queues;
- `disconnect_client()` and `heartbeat()` for session lifecycle;
- `publish(topic, value)` for explicit synchronised updates;
- `status()`, `health()`, `diagnostics()` and `configuration()`.

`bx1.tick()` advances communication cooperatively through the existing
Scheduler. There is no background thread.

## Message schema

Every message has exactly these fields:

| Field | Type | Meaning |
|---|---|---|
| `protocol_version` | semantic version string | Protocol used by the sender |
| `message_id` | non-empty string | Unique correlation identifier |
| `timestamp` | finite number | Unix time in seconds |
| `sender` | non-empty string | Source client or `bx1` |
| `destination` | non-empty string | Target queue or BX1 endpoint |
| `command` | command string | Requested operation or update topic |
| `payload` | object | Request/event inputs |
| `response` | any JSON value or null | Result body; null on requests |
| `status` | string | `request`, `ok`, `error` or `event` |

Example request:

```json
{
  "protocol_version": "1.0.0",
  "message_id": "0cfcb305fc9d4dad9f2e837c67111b49",
  "timestamp": 1785232800.0,
  "sender": "brain",
  "destination": "bx1",
  "command": "battery.status",
  "payload": {},
  "response": null,
  "status": "request"
}
```

Example successful response:

```json
{
  "protocol_version": "1.0.0",
  "message_id": "0cfcb305fc9d4dad9f2e837c67111b49",
  "timestamp": 1785232800.01,
  "sender": "bx1",
  "destination": "brain",
  "command": "battery.status",
  "payload": {},
  "response": {
    "ok": true,
    "data": {
      "service": "battery"
    },
    "error": null
  },
  "status": "ok"
}
```

Responses retain the request `message_id`, so clients can correlate them.
Errors use status `error` and return:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "UNKNOWN_COMMAND",
    "message": "Unsupported BX1 command: example.unknown"
  }
}
```

### Validation rules

- Missing, additional and duplicate JSON fields are rejected.
- Protocol versions must use `major.minor.patch` form.
- IDs, endpoints and commands must be non-empty and length-bounded.
- Normal commands use lowercase dotted names. The textual
  `GET capabilities` alias is accepted exactly.
- Payload must be an object and the complete message must contain JSON-safe
  finite values.
- Requests must have a null `response`.
- Encoded messages must not exceed `maximum_message_size`.
- BX1 accepts only messages addressed to `bx1` or `robot`.
- External senders must have an active session.

Invalid messages publish `InvalidMessage`. Incompatible messages publish
`ProtocolMismatch` and receive a structured error whenever their envelope is
otherwise valid.

## Protocol versioning

The default protocol is `1.0.0`. Compatibility is based on semantic-version
major number:

- equal major versions are compatible;
- different major versions are rejected;
- minor versions may add backward-compatible fields or behaviour only in a
  future schema revision;
- patch versions are corrective and do not alter the public contract.

The current exact-field schema means any future optional envelope field needs a
new negotiated protocol revision and matching codec support. The server reports
its negotiated version during client registration and through
`system.info`/capability responses.

## Sessions

```text
UNREGISTERED
     |
     | register_client()
     v
   ACTIVE <--------- heartbeat()
     |
     +------------- disconnect_client() ------> DISCONNECTED
     |
     +------------- timeout during tick() ----> TIMED_OUT
```

Registration validates protocol compatibility before allocating a session.
Repeated registration of the same active client refreshes that session. A
session records client ID, generated session ID, protocol version, connection
time, last heartbeat and metadata.

## Command routing

| Command | BX1 service/API |
|---|---|
| `battery.status` | `bx1.battery.status()` |
| `power.health` | `bx1.power.health()` |
| `drive.stop` | `bx1.drive.stop()` |
| `drive.move` | validated `bx1.drive.drive(...)` |
| `led.set` | `bx1.led.set_effect(...)` |
| `range.distance` | `bx1.range.poll()` |
| `diagnostics.report` | `bx1.diagnostics.report()` |
| `health.status` | `bx1.health.status()` |
| `system.info` | root status, services and capabilities |
| `capabilities.get` | negotiated capability response |
| `GET capabilities` | alias for capability negotiation |

Drive commands still pass through the Phase 1 dry-run validator. The default
configuration rejects movement and never opens a serial port. LED commands
affect only the simulated strip in the Phase 4 composition root.

## Capability negotiation

`register_client()` returns the negotiated version and the current capability
document. Clients may refresh it with `GET capabilities` or
`capabilities.get`. The result is built automatically from:

- the `CapabilityRegistry`;
- registered BX1 services;
- router command names; and
- supported synchronisation topics.

This avoids encoding installed-hardware assumptions in clients.

## State synchronisation

Supported topics are:

| Topic | Source |
|---|---|
| `battery` | Battery Service status and readings |
| `health` | Health Monitor report |
| `diagnostics` | combined Diagnostics Service report |
| `events` | hardware-independent Event Bus events |

Subscriptions may target a local callback or an active remote client. Remote
updates are event-status protocol messages addressed to that client's queue.
Polling topics are sampled during cooperative `tick()` and emitted only after
a value change. Event subscriptions are driven directly from the Event Bus.
Communication bookkeeping events are excluded from the `events` topic to avoid
recursive message generation.

## Communication events

The Event Bus vocabulary now includes:

- `ClientConnected`
- `ClientDisconnected`
- `HeartbeatTimeout`
- `MessageReceived`
- `MessageSent`
- `InvalidMessage`
- `ProtocolMismatch`

These remain ordinary Event Bus events, so diagnostics and future policy
services can subscribe without depending on the transport implementation.

## Configuration

Safe defaults under `core_services.communication` are:

```json
{
  "enabled": true,
  "transport": "in_memory",
  "protocol_version": "1.0.0",
  "heartbeat_interval_s": 5.0,
  "timeout_s": 15.0,
  "state_sync_interval_s": 1.0,
  "maximum_message_size": 65536,
  "maximum_clients": 32,
  "maximum_queued_messages": 1000
}
```

Configuration loading rejects transports other than `in_memory`, malformed
versions, a timeout not greater than the heartbeat interval, and invalid size,
client or queue limits.

## Safety philosophy

- Communication is a control-plane boundary, not a hardware adapter.
- Every external message is validated before routing.
- Every external command requires an active, compatible session.
- Queue, client and message sizes are bounded.
- Commands call registered BX1 services and retain their existing safety rules.
- Default drive remains disabled and dry-run; RS485 remains disabled.
- No transport opens a socket, HTTP server, WebSocket, MQTT connection or
  serial port.
- No runtime startup file was changed.
- No deployment or physical action is part of this phase.

Authentication, authorisation, encryption, replay protection and rate limiting
are required before any future network transport is allowed.

## Future expansion

1. Define a transport adapter contract and add authenticated local IPC before
   considering network transports.
2. Add client roles and per-command authorisation, with motion commands denied
   by default.
3. Add request expiry, replay protection and monotonic sequence numbers.
4. Publish formal JSON Schema documents and protocol conformance fixtures.
5. Add back-pressure policies, priority lanes and per-client queue quotas.
6. Add snapshot/revision semantics for reconnecting state subscribers.
7. Separate large diagnostics payloads from real-time control traffic.
8. Add transport security, key rotation and audit logging.
9. Gate physical adapters behind capability, health and power policies.

## Phase 4 architectural changelog

- Added an exact, versioned JSON message envelope and strict codec.
- Added a bounded, destination-aware in-memory Message Bus.
- Added version-aware client sessions, heartbeat and timeout detection.
- Added a stable command router that invokes BX1 services only.
- Added automatic capability negotiation.
- Added change-driven battery, health, diagnostics and event synchronisation.
- Added communication lifecycle and validation events.
- Added `bx1.communication` to the root API and service registry.
- Added cooperative communication ticking through the existing Scheduler.
- Added safe communication configuration and validation.
- Retained Digital Twin-only composition and left runtime startup untouched.
