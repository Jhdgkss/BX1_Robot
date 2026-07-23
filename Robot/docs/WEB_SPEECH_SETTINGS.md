# BX1 v10.24 Speech and Audio Responsibilities

## Desktop Brain App

The desktop Brain App owns the active TTS engine, Chatterbox voice/model and emotional speech delivery. The UNO Q asks the Brain TTS service to speak without sending an engine or voice override.

Change Leo’s voice in the desktop Brain App, not in the UNO Q web console.

## UNO Q body client

The body console owns settings that depend on physical robot hardware:

- microphone capture device and level;
- DSP filters and noise gate;
- STT endpointing and acceptance gates;
- wake/session capture;
- speaker playback device and local output volume;
- TTS transport URL/status;
- mouth LED waveform response.

The body may retain local voice fields for emergency compatibility, but v10.24 prevents old web/API controls from switching the active route away from Brain-owned TTS.

## Recommended diagnostic sequence

1. Select the correct microphone device.
2. Check that normal speech peaks roughly between -18 and -6 dBFS without clipping.
3. Run **Listen once**.
4. Compare raw, filtered and submitted WAVs.
5. Adjust endpointing before adding stronger filters.
6. Test the Brain TTS connection.
7. Run the mouth waveform test and confirm MCU command count/effective brightness change.

## Endpointing guidance

- Lost first word: increase pre-roll or reduce speech-start confirmation.
- Speech cut off: increase end silence.
- Too much delay after speech: reduce end silence cautiously.
- Fan noise starts recording: increase adaptive margin or gate slightly.
- Filtered WAV loses consonants: reduce noise suppression/compression.
