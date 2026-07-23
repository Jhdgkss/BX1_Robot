# BX1 Arduino Q Client V5 - Speech and Volume Settings

This update adds browser-based speech control to the UNO Q web app.

## Added

- New **Speech / Volume Settings** panel in the BX1 web interface.
- Saveable TTS settings in `python/config.json`.
- Volume slider saved for the next session.
- Test speech button.
- Preset buttons for quick voice tuning.
- Runtime update of the TTS engine without manually editing JSON.
- Backend support for:
  - `espeak-ng` - lightweight and reliable, good for testing.
  - `piper` - natural offline speech if Piper and a voice model are installed.
  - `edge-tts` - natural cloud speech if internet, Python package, and an MP3 player are available.
  - `custom` - advanced command override.

## Default behaviour

The project still defaults to `espeak-ng`, because it is the most likely to work immediately on the UNO Q.
For the more natural voice, select `piper` in the web interface after installing Piper and placing a model at the configured path.

## Files changed

- `python/audio_io.py`
- `python/main.py`
- `python/web_control.py`
- `python/config.json`
- `python/requirements-optional.txt`
- `docs/WEB_SPEECH_SETTINGS.md`

## Run

```bash
cd ~/Arduino_Q_Client_V1
./START_BX1_WEB.sh
```

Then open:

```text
http://BX1.local:8088
```

Use the **Speech / Volume Settings** panel, press **Save Speech Settings**, then press **Test Speech**.
