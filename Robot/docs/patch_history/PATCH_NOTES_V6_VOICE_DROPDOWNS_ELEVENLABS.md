# BX1 Arduino Q Client V6 - Voice Dropdowns + ElevenLabs

## Added

- Real dropdown selection for espeak-ng voices.
- Real dropdown selection for common Microsoft Edge Neural voices.
- New ElevenLabs TTS backend.
- ElevenLabs API key field, saved locally into `python/config.json`.
- ElevenLabs voice fetch button using the configured API key.
- ElevenLabs voice dropdown populated from the account/API key.
- Manual ElevenLabs voice ID input for voices copied from the ElevenLabs website.
- ElevenLabs model selection:
  - `eleven_flash_v2_5`
  - `eleven_turbo_v2_5`
  - `eleven_multilingual_v2`
  - `eleven_v3`
- ElevenLabs stability, similarity, style and speaker boost controls.
- Natural Edge preset and BX1 ElevenLabs preset.

## Notes

- Edge TTS and ElevenLabs both need internet access from the UNO Q.
- Edge TTS needs the `edge-tts` Python package and an MP3 player such as `mpg123`.
- ElevenLabs needs an API key, a voice ID and an MP3 player such as `mpg123`.
- The patch zip does not overwrite `python/config.json`, so your saved Brain App IP should be preserved.
