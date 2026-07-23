# Desktop Brain App Setup for BX1 v10.36

## Ownership

The desktop Brain App owns identity/personality, LLM/model settings, prompts, memory/internet policy, TTS engine/voice/emotion, spoken thinking cues, autonomous spoken dialogue and semantic vision reasoning.

The UNO Q body client owns microphone/DSP/endpointing, wake capture, speaker device/volume, camera capture, MCU/GPIO, servo safety/calibration and LED animation.

## Required Brain endpoints

- `GET /api/status`
- `POST /api/body_state`
- `POST /api/chat`
- `POST /api/vision_frame`
- `POST /api/vision`
- `POST /api/command_ack`
- Reply-audio route `/api/audio/<filename>`
- Optional manual voice test routes `/api/tts` and `/api/tts/status`

## Desktop settings

1. Start the Robot API on host `0.0.0.0` or the PC LAN address.
2. Use port `8765` unless deliberately changed.
3. Enable robot action packets.
4. Select Leo’s LLM, personality, memory/web behaviour and Dot.TTS voice in the Brain App.
5. Let Robot Brain start and warm Dot.TTS in WSL2.

## UNO Q connection

Set the Brain API address in the body console or `python/config.json`, for example:

```json
"brain_base_url": "http://192.168.68.53:8765"
```

The body uses this one address for chat, status and reply-audio downloads. It does not connect directly to WSL2 or the Dot.TTS service port.

## Basic test

```bash
curl http://YOUR_PC_IP:8765/api/status
```

Then open `http://BX1.local:8088`, check **Overview**, and run the Brain connection test from **Advanced**.
