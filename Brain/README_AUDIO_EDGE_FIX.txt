BX1 ROBOT BRAIN V2.8.2 - AUDIO EDGE PROTECTION
================================================

Problem fixed
-------------
Dot.TTS audio could lose the first and final phonemes because the generated WAV
started and ended directly on speech samples. USB/HDMI audio devices, speaker
amplifiers and the robot playback route can need a short wake/release margin.

Changes
-------
- 250 ms silent lead-in before Dot.TTS speech.
- 400 ms silent tail after Dot.TTS speech.
- 4 ms anti-click fade at the generated waveform edges.
- Protection is embedded in every WAV, so it applies to Brain-PC playback and
  robot-body playback through /api/audio.
- Values are configurable in config/app_config_bx1.json:
    dottts_leading_silence_ms
    dottts_trailing_silence_ms
    dottts_edge_fade_ms

Installation
------------
1. Close Robot Brain and its Dot.TTS service window.
2. Extract this ZIP over the existing Robot Brain project folder.
3. Allow files to be replaced.
4. Start Robot Brain normally. The Dot.TTS service must restart to load the fix.

Validation
----------
The complete Python test suite passes: 33 tests and 8 subtests.
