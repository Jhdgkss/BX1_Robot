# Capability Workshop

The normal workflow has three stages:

1. **Describe** — explain the outcome. Brain suggests Tool, Integration, Behaviour, or Hardware with a confidence and reason. The operator may override it.
2. **Build and Test** — generate a bounded review package, validate its manifest/files/permissions, scan source, run isolated tests, and perform a mock action.
3. **Review and Install** — installation remains disabled until checks pass and always asks for explicit human confirmation.

Advanced exposes the original import, individual validation/test, quarantine, manifest/source viewer, export, rollback, and removal controls. Those systems remain the safety authority.

## Shared type meanings

- **Tool:** Brain-local scheduling, reminders, calculations, notes, and local processing.
- **Integration:** external APIs and services such as Spotify, OctoPrint, calendars, or databases.
- **Behaviour:** bounded character routines using pose, movement, lights, or speech.
- **Hardware:** drivers/interfaces for sensors, motors, cameras, microphones, displays, and serial devices.

`bx1_capabilities.design.classify_capability()` is shared by conversation and Workshop.

## Missing capability suggestions

The conversation pipeline checks installed and disabled capabilities before suggesting a new one. Action requests such as “remind me…” can create a bounded pending proposal; informational and hypothetical questions do not. A proposal expires after five minutes or is cleared when the topic changes.

“Yes, create it” generates a structured review package and populates Workshop. It does not install or enable anything. The generated package is mock-only until the operator runs Build and Test and explicitly confirms Install Capability.

The LLM cannot approve permissions, bypass quarantine, modify Brain core, execute shell commands, add dependencies, or install the package.

## Capability-aware responses

Capability-status questions and reminder action requests are resolved from the live capability registry before ordinary LLM generation. Brain distinguishes missing, disabled, and enabled Reminder Clock packages. A concrete action is described as successful only when the capability returns `ok=true`, a reminder ID, and an ISO trigger datetime.

Incomplete enabled-capability requests retain only the parsed trigger time for a short clarification. A final claim guard replaces unsupported reminder, Spotify playback, and OctoPrint command-success claims. The ordinary LLM receives a secret-free capability summary for explanatory context but cannot override controlled routing.

## Capability Studio

Capability Studio is the single operator surface for capability creation and
management. It contains:

- **Create Capability** for the guided describe, build, test, review, and
  install workflow. The original Behaviour Forge controls remain available
  under **Advanced Behaviour Tools**.
- **Installed Capabilities** for behaviours, tools, integrations, and hardware.
  Records can be filtered by type and show their identifier, version, enabled
  state, functional status, permissions, last test result, and runtime status.
- **Capability Activity** for design, test, install, enable/disable, action,
  reminder, and TTS events.

The installed list is the management authority for configure, test,
enable/disable, rollback, and removal actions. It does not create a second
capability registry.

## Built-in Reminder Clock

Reminder Clock is a functional built-in Tool capability with these actions:
`create_reminder`, `create_alarm`, `list_reminders`, `cancel_reminder`,
`snooze_reminder`, `dismiss_reminder`, and `get_reminder_status`.

Reminder records are stored in the active Brain profile runtime directory at
`reminder_clock/reminders.db`. Times are persisted as timezone-aware ISO
datetimes, with `Europe/London` as the default interpretation timezone. The
background scheduler reloads pending reminders after restart and delivers due
messages through Brain's existing TTS path.

An installed mock package with the `reminder_clock` identifier is archived as
`replaced_by_builtin_<timestamp>` when the built-in capability is loaded. Brain
then exposes exactly one Reminder Clock record. Disabling that record stops its
scheduler and blocks reminder actions; enabling it starts the scheduler again.
The built-in record cannot be removed or replaced by a package with the same
identifier.
