# BX1 UNO Q Client V8.6 - Microphone Debug / Browser Playback

Adds clearer microphone/STT test diagnostics:

- Recording countdown/progress message while the sample is being captured.
- Clear "recording complete" status including RMS/peak dBFS and warnings for quiet/clipping samples.
- Automatically stops the live meter while recording, then restarts it, so the microphone device is not shared.
- Browser WAV playback endpoint (`/api/mic_sample.wav`) so the recorded sample can be heard through the web browser.
- Separate robot playback command for BX1 speaker output, with ALSA playback device selection.
- New sample debug endpoint (`/api/mic_sample_info`) showing WAV duration, size, level analysis, capture devices and playback devices.
- Vosk STT diagnostics now include Python executable, WAV analysis, raw Vosk final result, partial results and word timing where available.

Use the browser playback button first. If the browser playback is silent, the wrong capture device or capture level is the problem. If browser playback has clear speech but Vosk still returns blank text, the STT tuning/model is the problem.
