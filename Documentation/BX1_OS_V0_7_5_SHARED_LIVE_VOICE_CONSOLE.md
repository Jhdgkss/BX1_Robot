# BX1 OS v0.7.5 Shared Live Voice Console

Robot Body publishes a six-Hz bounded heartbeat from its active ALSA capture
loop. It contains RMS/peak dBFS, noise floor, threshold, gate, timestamp and
freshness only. If capture stops during recognition, Brain processing, speaking
or a fault, Body reports `stale`/`unavailable` with the callback age instead of
inventing a zero level.

BX1 OS records receiver timestamps for every proxied Body observation. The UI
therefore distinguishes a Body capture heartbeat failure from an OS receiver or
browser refresh failure.

The shared live console is a maximum-200-item in-memory buffer in BX1 OS. It is
shared by all 8089 clients, clearable from the UI and lost on OS restart. It may
hold recognised speech, typed Body→Brain requests, immediate Brain replies,
voice states and bounded failures. It is deliberately excluded from logs,
diagnostics, exports and persistent files; Brain remains the source of truth for
long-term history and personality.
