# Robot Brain V2.10.0 patch summary

## Brain-owned identity and wake phrases

The active Robot Brain profile now publishes the physical robot name, wake phrase templates, optional aliases, wake sensitivity and profile-sync interval through `GET /api/body_profile`.

Default templates are:

- `hey {robot_name}`
- `hello {robot_name}`

Changing **Robot → Identity / Personality → Robot name** automatically changes the phrases published to the UNO Q.

## Queued speech library

A new **Body Wake / Queued Speech** workspace provides:

- Save Definitions
- Generate Phrase
- Generate All
- Test Selected
- Refresh

The library covers wake acknowledgements, waiting-for-Brain phrases and the sleep acknowledgement. Generation uses the active Brain voice configuration. Each published item includes its text, filename, format, generation time and SHA-256 checksum.

## API additions

- `GET /api/body_profile`
- `GET /api/body_audio/<filename>`
- `POST /api/body_audio/generate`

Generated files are kept in the active Brain profile runtime directory and are returned with no-cache headers.

## Preserved behaviour

Chat, Faster-Whisper, Dot.TTS, Edge fallback, memory, documents, vision, telemetry and live web research are unchanged.
