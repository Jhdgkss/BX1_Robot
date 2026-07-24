# BX1 Integration Hub

The Integration Hub is the Brain-side framework for external services and reusable robot behaviours. Open **Integrations** in the Brain app to use it.

Mock/demo mode is enabled by default. In mock mode, the GUI and action flow can be tested without contacting OctoPrint, Spotify or robot hardware.

## Safety Levels

- `READ_ONLY`: status, progress and information lookups.
- `CONTROL`: state-changing actions such as pause, resume, play, pause Spotify or run a behaviour. AI-initiated control actions require confirmation.
- `SAFETY_CRITICAL`: actions such as starting or cancelling a print. These require explicit confirmation every time and must never run automatically.

## Secrets

Do not store OctoPrint API keys, Spotify tokens or passwords in Git-tracked JSON.

The integration framework prefers Windows Credential Manager through Python `keyring` when available. If keyring is unavailable, secrets are session-only. Activity logs mask API keys, bearer tokens, access tokens and refresh tokens.

## OctoPrint

Available from **Integrations / OctoPrint**.

Fields:

- server URL
- session-only API key
- mock/demo mode

Read-only actions:

- connection/version status
- printer state
- nozzle temperature
- bed temperature
- current job
- progress
- estimated time remaining
- file list

Controlled actions:

- pause print
- resume print
- select file
- start print
- cancel print

Starting or cancelling a print must be explicitly confirmed. Arbitrary G-code is not exposed to the AI.

## Spotify

Available from **Integrations / Spotify**.

The connector uses OAuth Authorization Code with PKCE. Live playback must happen through an existing Spotify client or Spotify Connect device. Robot Brain does not download, proxy, record or stream Spotify audio.

Capabilities:

- get playback state
- list available devices
- transfer playback
- play
- pause
- next
- previous
- volume
- queue a selected track

Live OAuth callback completion is future work. Mock/demo mode lets the GUI and permission flow run without a Spotify login.

## Robot Behaviours

Available from **Integrations / Robot Behaviours**.

Built-in routines:

- `greeting`
- `celebration`
- `curious`
- `listening`
- `simple_dance`

Choreography steps may contain head yaw, head pitch, head roll, mouth LED colour/intensity, an optional spoken phrase, an optional sound cue and a wheel command placeholder.

Head and LED limits are enforced. Wheel movement is disabled by default. The global stop action clears the active routine. Hardware commands are not sent during mock/demo mode.

## Voice Command Status

The Integration Hub exposes structured actions for future conversation-engine routing, but natural-language voice commands are not enabled yet.

Planned read-only commands:

- "What is the printer status?"
- "How is the print going?"
- "What percentage is the print at?"
- "How hot is the nozzle?"
- "How hot is the bed?"
- "What is playing on Spotify?"
- "What Spotify device is active?"

Planned control commands:

- "Pause the print."
- "Resume the print."
- "Cancel the print."
- "Pause Spotify."
- "Resume Spotify."
- "Skip this track."
- "Set Spotify volume to 40 percent."
- "Run greeting behaviour."
- "Do the celebration routine."
- "Stop behaviour."

Until command routing is added, use the Integrations page buttons.
