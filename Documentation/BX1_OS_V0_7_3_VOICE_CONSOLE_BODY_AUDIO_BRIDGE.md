# BX1 OS v0.7.3 — Voice Console and Body Audio Bridge

## Boundary

BX1 OS runs in **Body-mediated capability mode**. Robot Body remains the sole
owner of microphone capture, wake/STT, speaker playback, camera capture and
all raw hardware. The OS only requests the existing typed Body → Brain → TTS →
Body speaker route and reads metadata. It never opens an audio or camera device,
stores raw audio, or accepts hardware/action packets through the console.

## Audio bridge

Robot Body exposes `GET /api/bx1-os/audio-bridge` for bounded measurements:
RMS/peak dBFS, a bounded noise-floor estimate, threshold, gate, voice state,
effective input/gain, failure reason and sample age. It contains no waveform,
transcript, prompt, reply or credential.

`POST /api/bx1-os/audio-bridge/settings` accepts only these validated settings:
microphone gain, VAD threshold, minimum speech duration, end-silence timeout
and wake/listen timeout. Body clamps values and writes its configuration through
an atomic temporary-file replacement. When the active Body voice loop is using
an older capture configuration, the response marks a Body restart as required;
an operator must use the approved Body management route. BX1 OS does not restart
Body itself.

## Operator use

The Audio page polls the metadata bridge four times per second while open. The
gauge, peak hold, gate and state are live Body observations, not synthetic
`-120` values. The Brain page is a browser-session-only manual fallback:
Enter sends, Shift+Enter makes a line break, and Repeat/Clear operate only on
the tab’s display state. Brain remains the source of truth for history/memory.
