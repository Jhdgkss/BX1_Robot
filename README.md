# BX1 Brain Modular Voice Pipeline

Modules:

- `incoming_audio.py` - receives live PCM from LEO over WebSocket.
- `speech_segmenter.py` - continuous PCM to utterances.
- `stt_engine.py` - persistent Faster-Whisper engine.
- `transcript_processor.py` - wake words, keywords and conversation state.
- `llm_client.py` - Ollama interface.
- `main.py` - small coordinator.
- `config.py` - tunable settings.

Install:

```powershell
python -m pip install -r requirements.txt
```

Run:

```powershell
python main.py
```

For the first test, `LLM_ENABLED = False`.

Terminal colours:
- magenta = wake phrase
- cyan = command/current conversation
- yellow = configured keyword

The network module already provides `send_json()` and `send_binary()`
for adding a separate TTS return module later.
