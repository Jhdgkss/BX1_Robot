# BX1 Body Client v10.15 Stability Patch

Purpose: make normal robot interaction faster and easier to debug.

## What changed

- Default speech route now asks the Brain PC TTS service for **Edge TTS** instead of live Chatterbox Turbo.
- Body TTS now has an espeak fallback enabled, so BX1 can still speak if the Brain TTS service is unavailable.
- Brain TTS timeout reduced from long Chatterbox-style waits to a more practical 60 seconds.
- Thinking cues remain local/cached-first and do not call live Chatterbox when missing.
- Body client avoids duplicate speech if the Brain App ever returns audio metadata in the API response.
- App version set to `v10.15-stability`.

## Recommended baseline test

1. Confirm Robot Brain can reach Ollama.
2. In the body web UI, use Brain Connection > Test Brain Connection.
3. Send `Hi` from the body chat page.
4. Check that LLM time and Audio time are shown separately.

If the voice sounds less custom, that is expected in stability mode. Chatterbox can be switched back on later once the text/action loop is reliable.
