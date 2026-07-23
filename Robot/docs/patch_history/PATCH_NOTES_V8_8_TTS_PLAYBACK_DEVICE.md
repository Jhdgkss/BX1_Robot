# BX1 Patch V8.8 - Explicit TTS Playback Device

This patch adds a dedicated TTS playback device setting so Edge TTS, ElevenLabs, Piper and espeak can use the known USB speaker ALSA path instead of relying on the Linux default sound card.

For the current USB speaker, set:

```text
tts_playback_device = plughw:1,0
```

The Speech page now includes a TTS output device selector and manual override. Edge TTS and ElevenLabs now call `mpg123` with the selected ALSA output device, for example:

```bash
mpg123 -q -f <volume_factor> -o alsa -a plughw:1,0 speech.mp3
```

This patch zip does not overwrite `python/config.json`. To set the output device after applying the patch, run:

```bash
cd ~/Arduino_Q_Client_V1
./tools/set_tts_output_device.py plughw:1,0
sudo systemctl restart bx1-web.service
```

Then open the web UI, go to Speech, check the TTS output device is `plughw:1,0`, save speech settings, and run Test Speech.
