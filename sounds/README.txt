LEO / BX1 — Bright & Engaging Sound Pack
=======================================

Design direction:
- Bright, clean and friendly
- Short UI-style robot cues
- Softer levels so effects do not overpower speech
- No comedy / cartoon effects
- No harsh alarm-style beeps

Audio format:
- WAV
- 24,000 Hz
- mono
- 16-bit PCM

Drop-in event files:
wake.wav               Wake word recognised — friendly rising two-note chime
listening.wav          Listening/STT starts — soft upward digital chirp
stt_complete.wav       Speech captured — short confirmation ping
thinking.wav           Request sent to LLM — three restrained rising motes
still_thinking.wav     Delayed LLM cue — airy, slower unresolved pulse
response_received.wav  Response ready — compact positive three-note chime
error.wav              Error/failure — gentle low double pulse

Extra:
preview_all.wav        All seven cues in sequence for quick auditioning

The seven event filenames match Sound Pack_1 so this pack can be swapped into
the existing application without changing event-name references.
