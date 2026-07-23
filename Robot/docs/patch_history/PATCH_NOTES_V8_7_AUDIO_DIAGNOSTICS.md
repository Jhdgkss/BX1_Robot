# BX1 UNO Q Client V8.7 - Audio Diagnostics Patch

Adds microphone audio diagnostics to help debug speech-to-text capture quality.

## Added

- Recorded WAV download link from the Microphone Test page.
- Recorded waveform preview graph.
- Recorded RMS/peak level-over-time graph.
- Recorded FFT/frequency spectrum graph.
- Diagnostic hints for quiet audio, clipping and likely steady/static noise.
- Sample information now includes analysis, graph data and FFT data in `/api/mic_sample_info`.
- `/api/mic_sample.wav?download=1` now returns the recorded WAV with a download filename.
- Safer warning if the BX1 playback device is set to the same ALSA device as the microphone capture device.

## Important playback note

`Play On BX1 Speaker` uses the robot's ALSA output. Do not set the playback override to the webcam microphone device, such as `plughw:2,0`; that is a capture device, not a speaker.

For microphone verification, use:

- `2B. Play In Browser`
- `Download WAV`

These prove what BX1 actually recorded without depending on the robot speaker output.
