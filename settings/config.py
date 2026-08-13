# ============================================================
# BX1 TECHNICAL CONFIGURATION
# ============================================================
#
# Keep hardware/software configuration here.
# LEO's adjustable personality lives in personality.json.
# LEO's behavioural prompt lives in leo_prompt.py.
#
# ============================================================

BRAIN_HOST = "0.0.0.0"
BRAIN_AUDIO_PORT = 8770

MIC_SAMPLE_RATE = 16000
MIC_CHANNELS = 1
MIC_SAMPLE_WIDTH_BYTES = 2
INCOMING_AUDIO_QUEUE_BLOCKS = 400

SPEECH_START_RMS = 0.015
SPEECH_CONTINUE_RMS = 0.010
PRE_ROLL_SECONDS = 0.30
END_SILENCE_SECONDS = 0.60
MIN_UTTERANCE_SECONDS = 0.35
MAX_UTTERANCE_SECONDS = 12.0

STT_MODEL = "small.en"
STT_LANGUAGE = "en"
STT_BEAM_SIZE = 3
STT_PREFER_CUDA = True

WAKE_WORDS = [
    "hey leo",
    "leo",
    "hello",
    "hi",
]

END_PHRASES = [
    "thanks leo",
    "thank you leo",
    "goodbye leo",
    "that's all",
]

KEYWORDS = [
    "bx1",
    "arduino",
    "omron",
    "servo",
    "robot",
]

CONVERSATION_TIMEOUT_SECONDS = 20.0

LLM_ENABLED = True
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"