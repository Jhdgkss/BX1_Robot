# BX1 v10.36 Body Diagnostic Console

Open the UNO Q console at:

```text
http://BX1.local:8088
```

The console is for body hardware, capture and fault finding. It deliberately does not duplicate desktop Brain App controls for robot personality, LLM selection, memory, internet policy, TTS engine/voice, spoken thinking cues or autonomous dialogue.

## Pages

- **Overview** — subsystem status rail, active faults and Brain/body ownership.
- **Speech Input** — microphone device, live levels, production STT test, endpointing, filters and diagnostic WAVs.
- **Mouth / Lighting** — speech-envelope test, LED transport and MCU command telemetry.
- **Hardware** — hardware registry, bounded output tests and apply-to-MCU controls.
- **Hardware Doctor** — concise faults, likely causes and relevant actions.
- **Logs** — severity/subsystem filtering with duplicate events collapsed.
- **Advanced** — Brain connection, manual diagnostic message, body telemetry and integration details.

## Speech evidence

**Listen once** uses the same ALSA/Vosk path as normal speech capture. It creates:

```text
/tmp/bx1_stt_last_raw.wav
/tmp/bx1_stt_last_filtered.wav
/tmp/bx1_stt_last_submitted.wav
```

The submitted file is the exact audio passed to the recogniser. Compare these files before changing filters.

## Safety

Hardware tests still pass through body-side limits. Wheel motion remains blocked unless `motor_armed` is explicitly enabled. Servo limits, trims, directions and the head mixer remain body-owned because they protect the mechanics.
