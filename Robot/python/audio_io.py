from __future__ import annotations

import json
import math
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from array import array
from collections import deque
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


def _bx1_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


@dataclass
class AudioConfig:
    tts_enabled: bool = True
    # Backends:
    #   espeak-ng  - reliable, installed through apt, light weight
    #   piper      - much more natural, offline, needs piper binary + model file
    #   edge-tts   - natural cloud voice, needs edge-tts and a player such as mpg123/ffplay
    #   elevenlabs - very natural cloud voice, needs API key + internet + MP3 player
    #   brain-tts  - PC Brain App TTS service, downloads/plays Dot.TTS audio
    #   custom     - uses tts_command exactly, appending text unless {text} is present
    tts_backend: str = "espeak-ng"
    tts_command: str = "espeak-ng -ven-gb -s 155 -p 35"
    tts_voice: str = "en-gb"
    tts_rate: int = 155
    tts_pitch: int = 35
    tts_volume: int = 80
    # ALSA output device used by TTS players. Use "default" or e.g. "plughw:1,0".
    tts_playback_device: str = "default"
    tts_mixer_card: int = 1
    tts_mixer_control: str = "Speaker"
    # Remote Brain App TTS service. Use this when the PC Brain App should generate
    # Dot.TTS audio and the UNO Q should only download/play the finished file.
    # This keeps the robot voice identical to the Brain App without running heavy
    # voice models on the UNO Q.
    brain_tts_base_url: str = ""
    brain_tts_engine: str = "dottts"
    brain_tts_voice: str = "active_profile"
    # When true, the body does not send engine/voice overrides. The desktop Brain
    # App remains the single owner of voice/model selection. Legacy fields stay
    # available only for compatibility fallback.
    brain_tts_use_brain_defaults: bool = True
    brain_tts_format: str = "wav"
    brain_tts_timeout_s: int = 240
    # Robot Brain V1.0.8+ bridge endpoints. Use /api/tts so the PC
    # service applies robot-safe Dot.TTS defaults and returns LAN audio URLs.
    brain_tts_endpoint: str = "/api/tts"
    brain_tts_status_endpoint: str = "/api/tts/status"
    tts_piper_model: str = "models/piper/en_GB-alan-medium.onnx"
    tts_piper_config: str = ""
    tts_edge_voice: str = "en-GB-SoniaNeural"
    tts_elevenlabs_api_key: str = ""
    tts_elevenlabs_voice_id: str = ""
    tts_elevenlabs_model_id: str = "eleven_flash_v2_5"
    tts_elevenlabs_stability: float = 0.45
    tts_elevenlabs_similarity_boost: float = 0.75
    tts_elevenlabs_style: float = 0.10
    tts_elevenlabs_use_speaker_boost: bool = True
    voice_backend: str = "vosk"
    vosk_model_path: str = "models/vosk-model-small-en-us-0.15"
    sample_rate: int = 16000
    record_seconds: int = 5
    # Capture settings used by the live wake-word listener.  The previous
    # implementation used sounddevice's default input, which could ignore the
    # manually selected USB webcam microphone on the UNO Q.
    mic_device: str = "default"
    mic_channels: int = 1
    # Lightweight real-time DSP and STT acceptance gates.  These defaults are
    # intentionally conservative: they suppress fan/mains noise and reject
    # fragments without making normal speech sound unnatural.
    mic_software_gain_db: float = 0.0
    mic_noise_gate_dbfs: float = -48.0
    audio_filter_enabled: bool = True
    audio_highpass_enabled: bool = True
    audio_highpass_hz: float = 90.0
    audio_notch_enabled: bool = True
    audio_notch_hz: float = 50.0
    audio_notch_q: float = 25.0
    audio_notch_harmonics: int = 2
    audio_noise_reduction_enabled: bool = True
    audio_noise_reduction_strength: float = 0.20
    audio_noise_gate_knee_db: float = 10.0
    audio_live_fft_bins: int = 48
    stt_validation_enabled: bool = True
    stt_min_confidence: float = 0.40
    stt_min_voiced_ms: int = 280
    stt_min_longest_voiced_ms: int = 160
    stt_min_words: int = 1
    stt_min_chars: int = 2
    stt_noise_margin_db: float = 6.0
    stt_reject_fillers: bool = True
    # Final transcript sanity gates.  These reject decoder collapse and prompt
    # leakage before a noise-generated phrase can become a Brain command.
    stt_repetition_guard_enabled: bool = True
    stt_max_consecutive_word_repeats: int = 3
    stt_max_repeated_phrase_count: int = 2
    stt_min_unique_word_ratio: float = 0.30
    stt_max_words_per_second: float = 7.0
    stt_max_transcript_words: int = 90
    stt_reject_prompt_leakage: bool = True
    # auto = try ALSA/arecord first, then sounddevice.  ALSA is preferred on the
    # UNO Q because it honours plughw:x,y device strings from the web UI.
    stt_capture_method: str = "alsa"
    # Speech endpointing. Instead of chopping the microphone into fixed five-second
    # blocks, the ALSA capture waits for speech, preserves a short pre-roll and
    # closes only after sustained silence. This is the main defence against lost
    # first words and cut-off sentence endings.
    stt_endpointing_enabled: bool = True
    stt_start_timeout_s: float = 8.0
    stt_max_utterance_s: float = 20.0
    stt_pre_roll_ms: int = 700
    stt_end_silence_ms: int = 1350
    stt_post_roll_ms: int = 300
    stt_start_trigger_ms: int = 80
    # Once an utterance has been quiet for a short period, a new sound must be
    # sustained before it can reset the end-of-speech timer. This prevents a
    # click/chirp/handling spike from adding another full silence interval.
    stt_speech_resume_trigger_ms: int = 140
    stt_transient_guard_after_ms: int = 220
    stt_endpoint_hysteresis_db: float = 3.0
    stt_adaptive_threshold_enabled: bool = True
    stt_adaptive_margin_db: float = 8.0
    stt_debug_keep_audio: bool = True
    # Long natural replies are split and spoken through a single queue so
    # Edge/ElevenLabs/Piper do not time out halfway and then overlap/fall back.
    tts_queue_enabled: bool = True
    tts_chunking_enabled: bool = True
    tts_chunk_max_chars: int = 650
    tts_fallback_to_espeak: bool = False


class SpeakerController:
    """Authoritative ALSA speaker state shared by normal and diagnostic playback."""
    def __init__(self, playback_device: str = "plughw:CARD=Device,DEV=0", mixer_card: int = 1, mixer_control: str = "Speaker") -> None:
        self.requested_volume_percent = 80
        self.effective_volume_percent: Optional[int] = None
        self.muted = False
        self.playback_device = playback_device
        self.mixer_card = int(mixer_card)
        self.mixer_control = mixer_control
        self.apply_ok = False
        self.last_error = ""
        self.last_change_at = ""
        self._lock = threading.RLock()

    def _amixer(self) -> Optional[str]:
        return shutil.which("amixer")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"requested_volume_percent": self.requested_volume_percent, "effective_volume_percent": self.effective_volume_percent,
                    "muted": self.muted, "playback_device": self.playback_device, "mixer_card": self.mixer_card,
                    "mixer_control": self.mixer_control, "apply_ok": self.apply_ok, "last_error": self.last_error,
                    "last_change_at": self.last_change_at}

    def _readback(self) -> Optional[int]:
        exe = self._amixer()
        if not exe: raise RuntimeError("amixer unavailable")
        result = subprocess.run([exe, "-c", str(self.mixer_card), "get", self.mixer_control], capture_output=True, text=True, timeout=2, check=False)
        if result.returncode != 0: raise RuntimeError((result.stderr or result.stdout or "amixer read failed").strip())
        values = [int(x) for x in re.findall(r"\[(\d+)%\]", result.stdout)]
        return values[0] if values else None

    def apply(self, volume_percent: Optional[int] = None, muted: Optional[bool] = None) -> dict[str, Any]:
        with self._lock:
            if volume_percent is not None: self.requested_volume_percent = _bx1_normalised_volume(volume_percent)
            if muted is not None: self.muted = bool(muted)
            target = 0 if self.muted else self.requested_volume_percent
            try:
                exe = self._amixer()
                if not exe: raise RuntimeError("amixer unavailable")
                result = subprocess.run([exe, "-c", str(self.mixer_card), "set", self.mixer_control, f"{target}%"], capture_output=True, text=True, timeout=2, check=False)
                if result.returncode != 0: raise RuntimeError((result.stderr or result.stdout or "amixer set failed").strip())
                readback = self._readback()
                if readback is None: raise RuntimeError("amixer returned no Speaker percentage")
                self.effective_volume_percent = readback
                self.apply_ok = True; self.last_error = ""; self.last_change_at = _bx1_now_iso()
            except Exception as exc:
                self.apply_ok = False; self.last_error = str(exc)
            return self.snapshot()


def _bx1_build_wav_mouth_profile(filename: str | os.PathLike, frame_s: float = 0.055) -> dict:
    """Return a compact RMS envelope for mouth LED animation.

    The profile is intentionally small: it is sent only inside Python memory to
    the mouth LED animator, not over RouterBridge.
    """
    path = Path(filename)
    report: dict[str, Any] = {
        "ok": False,
        "levels": [],
        "frame_s": frame_s,
        "duration_s": 0.0,
        "source": str(path),
    }
    try:
        with wave.open(str(path), "rb") as wf:
            channels = max(1, int(wf.getnchannels()))
            sampwidth = int(wf.getsampwidth())
            framerate = max(1, int(wf.getframerate()))
            nframes = int(wf.getnframes())
            report["duration_s"] = nframes / float(framerate)
            if sampwidth != 2:
                return report
            frames_per_bucket = max(80, int(framerate * frame_s))
            levels: list[float] = []
            while True:
                raw = wf.readframes(frames_per_bucket)
                if not raw:
                    break
                pcm = array("h")
                pcm.frombytes(raw)
                if sys.byteorder != "little":
                    pcm.byteswap()
                if channels > 1:
                    mono = []
                    for i in range(0, len(pcm), channels):
                        mono.append(int(sum(pcm[i:i + channels]) / channels))
                else:
                    mono = pcm
                if not mono:
                    continue
                acc = 0.0
                for sample in mono:
                    acc += float(sample) * float(sample)
                rms = math.sqrt(acc / max(1, len(mono))) / 32768.0
                levels.append(max(0.0, min(1.0, rms)))
            if not levels:
                return report
            peak = max(levels) or 1.0
            # Normalise and apply a soft knee so quiet speech still visibly moves.
            norm = [max(0.0, min(1.0, (x / peak) ** 0.55)) for x in levels]
            report.update({"ok": True, "levels": norm, "peak": peak})
            return report
    except Exception as exc:
        report["error"] = str(exc)
        return report


class TextToSpeech:
    def __init__(self, cfg: AudioConfig) -> None:
        self.cfg = cfg
        self._last_volume: Optional[int] = None
        self.speaker_controller = SpeakerController(
            playback_device=str(getattr(cfg, "tts_playback_device", "plughw:CARD=Device,DEV=0") or "plughw:CARD=Device,DEV=0"),
            mixer_card=int(getattr(cfg, "tts_mixer_card", 1) or 1),
            mixer_control=str(getattr(cfg, "tts_mixer_control", "Speaker") or "Speaker"),
        )
        self.last_playback_report: dict[str, Any] = {}
        self._speak_queue: "queue.Queue[Optional[tuple[str, str]]]" = queue.Queue(maxsize=max(2, int(getattr(cfg, "tts_queue_max", 20) or 20)))
        self._worker_started = False
        self._worker_lock = threading.Lock()
        # Set while speech is queued, being generated, or being played. The
        # body client uses this to mute STT capture so BX1 does not hear
        # its own speaker and treat the reply as the next command.
        self._speech_active = threading.Event()
        self._mouth_event_handler: Optional[Callable[[str, dict[str, Any]], None]] = None

    def set_mouth_event_handler(self, handler: Optional[Callable[[str, dict[str, Any]], None]]) -> None:
        self._mouth_event_handler = handler

    def _emit_mouth_event(self, event: str, info: Optional[dict[str, Any]] = None) -> None:
        handler = self._mouth_event_handler
        if handler is None:
            return
        try:
            handler(event, info or {})
        except Exception as exc:
            print(f"[audio] mouth LED event handler failed: {exc}")

    def update_config(self, cfg: AudioConfig) -> None:
        self.cfg = cfg
        self.speaker_controller.playback_device = str(getattr(cfg, "tts_playback_device", self.speaker_controller.playback_device) or self.speaker_controller.playback_device)
        self.apply_volume(force=True)

    def clear_queue(self) -> None:
        """Remove queued speech that has not started yet. The currently playing
        audio file cannot be stopped safely here, but old waiting filler/noise
        clips are discarded before a real reply is spoken.
        """
        try:
            while True:
                self._speak_queue.get_nowait()
                self._speak_queue.task_done()
        except queue.Empty:
            if self._speak_queue.empty():
                self._speech_active.clear()
            return

    def is_active_or_pending(self) -> bool:
        """True while TTS is queued, generating, or playing.

        The wake listener checks this before opening the microphone. This is
        intentionally conservative because acoustic echo cancellation is not
        reliable on every Debian/USB-webcam setup.
        """
        try:
            return bool(self._speech_active.is_set() or self._speak_queue.qsize() > 0)
        except Exception:
            return bool(self._speech_active.is_set())

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker_started:
                return
            worker = threading.Thread(target=self._speech_worker, name="bx1-tts-worker", daemon=True)
            worker.start()
            self._worker_started = True

    def _speech_worker(self) -> None:
        while True:
            item = self._speak_queue.get()
            try:
                if item is None:
                    return
                text, tag = item
                if not text or not self.cfg.tts_enabled:
                    continue
                self._speech_active.set()
                self.apply_volume()
                backend = (self.cfg.tts_backend or "espeak-ng").strip().lower()
                brain_backend = backend in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}
                if brain_backend:
                    self._emit_mouth_event("speech_prepare", {"text": text, "tag": tag, "backend": backend})
                    self._speak_selected_backend_blocking(text)
                else:
                    self._emit_mouth_event("speech_start", {"text": text, "tag": tag, "backend": backend})
                    try:
                        self._speak_selected_backend_blocking(text)
                    finally:
                        self._emit_mouth_event("speech_stop", {"text": text, "tag": tag, "backend": backend})
            finally:
                try:
                    self._speak_queue.task_done()
                except Exception:
                    pass
                try:
                    if self._speak_queue.empty():
                        self._speech_active.clear()
                except Exception:
                    pass

    def apply_volume(self, force: bool = False) -> None:
        """Set Linux output volume where possible.

        On the UNO Q this usually means ALSA/amixer. On some desktop images it may
        be PulseAudio/PipeWire, so we try pactl as a fallback. Failure is non-fatal.
        """
        try:
            volume = int(self.cfg.tts_volume)
        except Exception:
            return
        volume = max(0, min(100, volume))
        self.speaker_controller.apply(volume_percent=volume)
        if not force and self._last_volume == volume:
            return
        self._last_volume = volume

        # ALSA first: common on small Debian images.
        amixer = shutil.which("amixer")
        if amixer:
            for control in ("Master", "PCM", "Speaker", "Headphone", "Digital"):
                try:
                    result = subprocess.run(
                        [amixer, "set", control, f"{volume}%"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=2,
                        check=False,
                    )
                    if result.returncode == 0:
                        return
                except Exception:
                    pass

        # PulseAudio/PipeWire fallback.
        pactl = shutil.which("pactl")
        if pactl:
            try:
                subprocess.run(
                    [pactl, "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass

    def speak(self, text: str, flush: bool = False, tag: str = "reply") -> None:
        text = (text or "").strip()
        if not text or not self.cfg.tts_enabled:
            return
        chunks = self._split_text_for_tts(text)
        if bool(getattr(self.cfg, "tts_queue_enabled", True)):
            self._speech_active.set()
            self._ensure_worker()
            if flush:
                self.clear_queue()
                # clear_queue() deliberately clears the flag when the queue is
                # empty. Re-assert it before the replacement reply is enqueued so
                # the wake listener remains muted during Dot.TTS generation.
                self._speech_active.set()
            for chunk in chunks:
                try:
                    self._speak_queue.put_nowait((chunk, tag))
                except queue.Full:
                    print("[audio] TTS queue full; dropping oldest queued speech.")
                    try:
                        self._speak_queue.get_nowait()
                        self._speak_queue.task_done()
                    except queue.Empty:
                        pass
                    try:
                        self._speak_queue.put_nowait((chunk, tag))
                    except queue.Full:
                        pass
            return

        self.apply_volume()
        backend = (self.cfg.tts_backend or "espeak-ng").strip().lower()
        brain_backend = backend in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}
        for chunk in chunks:
            if brain_backend:
                self._emit_mouth_event("speech_prepare", {"text": chunk, "tag": tag, "backend": backend})
                self._speak_selected_backend_blocking(chunk)
            else:
                self._emit_mouth_event("speech_start", {"text": chunk, "tag": tag, "backend": backend})
                try:
                    self._speak_selected_backend_blocking(chunk)
                finally:
                    self._emit_mouth_event("speech_stop", {"text": chunk, "tag": tag, "backend": backend})

    def _split_text_for_tts(self, text: str) -> list[str]:
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return []
        if not bool(getattr(self.cfg, "tts_chunking_enabled", True)):
            return [text]
        max_chars = max(120, min(1400, int(getattr(self.cfg, "tts_chunk_max_chars", 650) or 650)))
        if len(text) <= max_chars:
            return [text]
        parts = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) > max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                for i in range(0, len(part), max_chars):
                    chunks.append(part[i:i + max_chars].strip())
                continue
            candidate = (current + " " + part).strip() if current else part
            if len(candidate) > max_chars and current:
                chunks.append(current.strip())
                current = part
            else:
                current = candidate
        if current:
            chunks.append(current.strip())
        return [c for c in chunks if c]

    def _speak_selected_backend_blocking(self, text: str) -> None:
        backend = (self.cfg.tts_backend or "espeak-ng").strip().lower()
        try:
            if backend in {"espeak", "espeak-ng", "espeakng"}:
                self._speak_espeak_blocking(text)
            elif backend == "piper":
                self._speak_piper_blocking(text)
            elif backend in {"edge", "edge-tts", "edge_tts"}:
                self._speak_edge_blocking(text)
            elif backend in {"elevenlabs", "eleven-labs", "eleven_labs", "11labs"}:
                self._speak_elevenlabs_blocking(text)
            elif backend in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}:
                self._speak_brain_tts_blocking(text)
            elif backend == "custom":
                self._speak_custom_blocking(text)
            else:
                print(f"[audio] Unknown TTS backend '{backend}'.")
                self._fallback_speech(text, "unknown backend")
        except FileNotFoundError as exc:
            print(f"[audio] TTS command not found: {exc}")
            self._fallback_speech(text, str(exc))
        except Exception as exc:
            print(f"[audio] TTS failed: {exc}")
            self._fallback_speech(text, str(exc))

    def _fallback_speech(self, text: str, reason: str = "") -> None:
        if bool(getattr(self.cfg, "tts_fallback_to_espeak", False)):
            try:
                print(f"[audio] Falling back to espeak-ng. Reason: {reason}")
                self._speak_espeak_blocking(text)
            except Exception as exc:
                print(f"[audio] espeak-ng fallback failed: {exc}")
        else:
            print(f"[audio] Natural TTS failed; robotic fallback is disabled. Reason: {reason}")


    def _brain_tts_base_url(self) -> str:
        base = (getattr(self.cfg, "brain_tts_base_url", "") or "").strip()
        if not base:
            # Best effort fallback for old configs: same PC as Brain API but port 8765.
            # The UNO Q config normally sets this explicitly from the web page.
            base = "http://127.0.0.1:8765"
        return base.rstrip("/")

    def _rewrite_local_audio_url(self, audio_url: str, base_url: str) -> str:
        """The PC TTS service may return http://127.0.0.1:8765/audio/...
        That URL is correct on the PC, but wrong from the UNO Q.  Rewrite local
        hostnames to the configured PC host while keeping the returned path.
        """
        raw = str(audio_url or "").strip()
        if not raw:
            return raw
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(raw)
            if parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0"}:
                base = urlparse(base_url)
                return urlunparse((base.scheme or "http", base.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        except Exception:
            pass
        return raw

    def _request_brain_tts_audio(self, text: str) -> dict:
        """Ask the PC Brain App TTS service to generate speech and download it.

        Expected service: Robot Brain / BX1 TTS service on port 8765.
        POST /api/tts with text, engine, voice, play=false.
        Response normally contains audio_url or audio_path.  We use audio_url so
        the UNO Q can download the audio across the LAN and play it locally.
        """
        base_url = self._brain_tts_base_url()
        endpoint = str(getattr(self.cfg, "brain_tts_endpoint", "/api/tts") or "/api/tts").strip()
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        # Robot Brain V1.0.8+ exposes /api/tts specifically for the UNO Q.
        # It applies robot-safe Dot.TTS defaults and returns LAN-reachable audio URLs.
        speak_url = base_url + endpoint
        payload = {
            "text": text,
            "play": False,
            "format": (getattr(self.cfg, "brain_tts_format", "wav") or "wav"),
            "robot_client": "arduino_q_body_client",
            "voice_owner": "brain_app",
        }
        if not bool(getattr(self.cfg, "brain_tts_use_brain_defaults", True)):
            payload["engine"] = (getattr(self.cfg, "brain_tts_engine", "dottts") or "dottts")
            payload["voice"] = (getattr(self.cfg, "brain_tts_voice", "active_profile") or "active_profile")
        timeout = max(20, int(getattr(self.cfg, "brain_tts_timeout_s", 240) or 240))
        report = {
            "ok": False,
            "backend": "brain-tts",
            "speak_url": speak_url,
            "payload": dict(payload),
            "download_url": "",
            "filename": "",
            "playback": {},
        }
        request_started = time.perf_counter()
        tmp_name = ""
        try:
            req = urllib.request.Request(
                speak_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            service_started = time.perf_counter()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            report["service_generation_s"] = round(time.perf_counter() - service_started, 3)
            try:
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                data = {"raw": raw.decode("utf-8", errors="replace")[:1000]}
            report["response"] = data
            report["effective_engine"] = data.get("effective_engine") or data.get("engine")
            report["effective_voice"] = data.get("effective_voice") or data.get("voice")
            report["fallback_reason"] = data.get("fallback_reason", "")
            report["audio_duration_sec"] = data.get("audio_duration_sec") or data.get("duration_sec")
            report["audio_format"] = data.get("format") or payload.get("format")
            if not isinstance(data, dict) or not data.get("ok", False):
                report["error"] = str((data or {}).get("error") or (data or {}).get("detail") or data)
                return report
            audio_url = str(data.get("audio_url") or data.get("relative_audio_url") or data.get("url") or "").strip()
            if audio_url.startswith("/"):
                audio_url = base_url + audio_url
            if not audio_url:
                # Older /speak responses may only contain a PC-local audio_path.
                # That is not useful to the robot over the network, so show a precise hint.
                report["error"] = "TTS service did not return audio_url/relative_audio_url. Check that Robot Brain V1.0.8+ is running and use /api/tts."
                return report
            audio_url = self._rewrite_local_audio_url(audio_url, base_url)
            report["download_url"] = audio_url

            suffix = ".wav"
            fmt = str(data.get("format") or payload.get("format") or "").lower()
            if "mp3" in fmt or audio_url.lower().endswith(".mp3"):
                suffix = ".mp3"
            elif audio_url.lower().endswith(".ogg"):
                suffix = ".ogg"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_name = tmp.name
            download_started = time.perf_counter()
            with urllib.request.urlopen(audio_url, timeout=timeout) as resp:
                audio_bytes = resp.read()
            Path(tmp_name).write_bytes(audio_bytes)
            report["download_s"] = round(time.perf_counter() - download_started, 3)
            report["total_generation_download_s"] = round(time.perf_counter() - request_started, 3)
            report["filename"] = tmp_name
            report["bytes"] = len(audio_bytes)
            if len(audio_bytes) < 1000:
                report["error"] = "Downloaded audio is too small to be a valid speech file."
                return report
            report["ok"] = True
            print(
                "[audio] Brain voice ready: "
                f"service={report.get('service_generation_s', 0):.3f}s "
                f"download={report.get('download_s', 0):.3f}s "
                f"total={report.get('total_generation_download_s', 0):.3f}s "
                f"chars={len(text)} bytes={len(audio_bytes)}"
            )
            return report
        except urllib.error.HTTPError as exc:
            report["total_generation_download_s"] = round(time.perf_counter() - request_started, 3)
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
            except Exception:
                detail = str(exc)
            # Compatibility fallback for an older Brain voice service that still
            # requires explicit engine/voice fields. New Brain builds should use
            # their own selected profile and accept the minimal payload above.
            if exc.code in {400, 422} and bool(getattr(self.cfg, "brain_tts_use_brain_defaults", True)):
                low_detail = detail.lower()
                if "voice" in low_detail or "engine" in low_detail or "required" in low_detail:
                    try:
                        setattr(self.cfg, "brain_tts_use_brain_defaults", False)
                        retry = self._request_brain_tts_audio(text)
                        retry["compatibility_fallback_used"] = "explicit_engine_voice"
                        setattr(self.cfg, "brain_tts_use_brain_defaults", True)
                        return retry
                    except Exception:
                        try:
                            setattr(self.cfg, "brain_tts_use_brain_defaults", True)
                        except Exception:
                            pass
            # Compatibility fallback: if a very old Robot Brain service does not
            # know /api/tts, try /speak once. New builds should not need this.
            if exc.code == 404 and speak_url.endswith("/api/tts"):
                try:
                    old_endpoint = str(getattr(self.cfg, "brain_tts_endpoint", "") or "")
                    setattr(self.cfg, "brain_tts_endpoint", "/speak")
                    retry = self._request_brain_tts_audio(text)
                    retry["compatibility_fallback_used"] = "/speak"
                    setattr(self.cfg, "brain_tts_endpoint", old_endpoint or "/api/tts")
                    return retry
                except Exception:
                    try:
                        setattr(self.cfg, "brain_tts_endpoint", "/api/tts")
                    except Exception:
                        pass
            report["error"] = f"HTTP {exc.code}: {detail}"
            return report
        except Exception as exc:
            report["total_generation_download_s"] = round(time.perf_counter() - request_started, 3)
            report["error"] = str(exc)
            print(f"[audio] Brain voice request failed after {report['total_generation_download_s']:.3f}s: {exc}")
            return report

    def play_response_audio_file(
        self,
        filename: str | os.PathLike,
        text: str,
        *,
        tag: str = "reply",
        delete_after: bool = True,
        timing: Optional[dict] = None,
        emit_mouth_events: bool = True,
        on_playback_started: Optional[Callable[[], None]] = None,
    ) -> dict:
        """Play a Brain-published reply file with real mouth-envelope events."""
        filename = str(filename or "")
        if not filename or not Path(filename).is_file():
            return {"ok": False, "error": "Brain reply audio file is missing."}
        was_active = self._speech_active.is_set()
        self._speech_active.set()
        self.apply_volume()
        try:
            suffix = Path(filename).suffix.lower()
            wav = suffix == ".wav"
            if wav:
                player = shutil.which("aplay") or shutil.which("paplay") or shutil.which("ffplay")
            else:
                player = shutil.which("mpg123") or shutil.which("mpv") or shutil.which("ffplay")
            if not player:
                return {"ok": False, "error": "No suitable player found. Install aplay, mpg123 or ffmpeg."}
            profile = _bx1_build_wav_mouth_profile(filename) if wav else {"ok": False, "levels": [], "frame_s": 0.055, "duration_s": 0.0, "source": filename}
            print(
                "[audio] Reply playback starting: "
                f"generation_download={float((timing or {}).get('total_generation_download_s') or 0.0):.3f}s "
                f"duration={float(profile.get('duration_s') or 0.0):.3f}s chars={len(text)}"
            )
            if emit_mouth_events:
                self._emit_mouth_event("speech_audio_file_start", {
                    "text": text,
                    "tag": tag,
                    "backend": "brain-api-audio",
                    "filename": filename,
                    "wav": wav,
                    "audio_profile": profile,
                    "tts_timing": dict(timing or {}),
                })
            playback_started = time.perf_counter()
            try:
                if on_playback_started is not None:
                    on_playback_started()
                play = _bx1_play_file(player, filename, self.cfg.tts_volume, wav=wav, playback_device=self.cfg.tts_playback_device)
                self.last_playback_report = dict(play)
            finally:
                print(f"[audio] Reply playback finished: elapsed={time.perf_counter() - playback_started:.3f}s")
                if emit_mouth_events:
                    self._emit_mouth_event("speech_audio_file_stop", {
                        "text": text,
                        "tag": tag,
                        "backend": "brain-api-audio",
                        "filename": filename,
                        "wav": wav,
                        "audio_profile": profile,
                    })
            if not play.get("ok"):
                return {"ok": False, "error": str(play.get("error") or play.get("stderr") or "playback failed"), "playback": play}
            return {"ok": True, "filename": filename, "wav": wav, "audio_profile": profile, "playback": play}
        finally:
            if delete_after and filename:
                try:
                    os.unlink(filename)
                except OSError:
                    pass
            if not was_active:
                try:
                    if self._speak_queue.empty():
                        self._speech_active.clear()
                except Exception:
                    self._speech_active.clear()

    def _speak_brain_tts_blocking(self, text: str) -> None:
        """Compatibility path for older separate Brain-TTS configurations."""
        report = self._request_brain_tts_audio(text)
        if not report.get("ok"):
            print(f"[audio] Brain voice failed: {report.get('error') or report}")
            self._fallback_speech(text, str(report.get("error") or "Brain voice failed"))
            return
        result = self.play_response_audio_file(
            str(report.get("filename") or ""),
            text,
            tag="legacy_brain_tts",
            delete_after=True,
            timing=report,
        )
        if not result.get("ok"):
            print(f"[audio] Brain voice playback failed: {result}")
            self._fallback_speech(text, str(result.get("error") or "playback failed"))

    def _speak_espeak(self, text: str) -> None:
        self._speak_espeak_blocking(text)

    def _speak_espeak_blocking(self, text: str) -> None:
        voice = (self.cfg.tts_voice or "en-gb").strip()
        rate = max(80, min(260, int(self.cfg.tts_rate)))
        pitch = max(0, min(99, int(self.cfg.tts_pitch)))
        # espeak-ng amplitude is 0-200. Map web 0-100 to useful speech amplitude.
        amp = max(0, min(200, int(round(int(self.cfg.tts_volume) * 2))))
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise FileNotFoundError("espeak-ng")
        args = [exe, f"-v{voice}", "-s", str(rate), "-p", str(pitch), "-a", str(amp), text]
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=False)

    def _speak_custom(self, text: str) -> None:
        self._speak_custom_blocking(text)

    def _speak_custom_blocking(self, text: str) -> None:
        cmd = (self.cfg.tts_command or "").strip()
        if not cmd:
            return
        if "{text}" in cmd:
            args = shlex.split(cmd.replace("{text}", text))
        else:
            args = shlex.split(cmd) + [text]
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=False)

    def _speak_piper_async(self, text: str) -> None:
        worker = threading.Thread(target=self._speak_piper_blocking, args=(text,), daemon=True)
        worker.start()

    def _speak_piper_blocking(self, text: str) -> None:
        piper = shutil.which("piper")
        if not piper:
            print("[audio] Piper not found. Install piper or select espeak-ng/custom in the web UI.")
            self._fallback_speech(text, "piper command not found")
            return
        model = Path(self.cfg.tts_piper_model or "")
        if not model.exists():
            print(f"[audio] Piper model not found: {model}.")
            self._fallback_speech(text, "piper model not found")
            return
        player = shutil.which("aplay") or shutil.which("paplay") or shutil.which("ffplay")
        if not player:
            print("[audio] No wav player found for Piper output. Install alsa-utils for aplay.")
            self._fallback_speech(text, "no wav player found")
            return

        tmp_name = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_name = tmp.name
            cmd = [piper, "--model", str(model), "--output_file", tmp_name]
            if self.cfg.tts_piper_config:
                config_path = Path(self.cfg.tts_piper_config)
                if config_path.exists():
                    cmd.extend(["--config", str(config_path)])
            subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
                check=False,
            )
            play_cmd = _bx1_player_command(player, tmp_name, self.cfg.tts_volume, wav=True, playback_device=self.cfg.tts_playback_device)
            subprocess.run(play_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45, check=False)
        except Exception as exc:
            print(f"[audio] Piper TTS failed: {exc}")
            self._fallback_speech(text, str(exc))
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

    def _speak_edge_async(self, text: str) -> None:
        worker = threading.Thread(target=self._speak_edge_blocking, args=(text,), daemon=True)
        worker.start()

    def _speak_edge_blocking(self, text: str) -> None:
        python = shutil.which("python3") or shutil.which("python")
        if not python:
            print("[audio] Python not found for edge-tts playback.")
            self._fallback_speech(text, "python not found for edge-tts")
            return
        player = shutil.which("mpg123") or shutil.which("mpv") or shutil.which("ffplay")
        if not player:
            print("[audio] No MP3 player found for edge-tts. Install mpg123/mpv/ffmpeg or use espeak-ng.")
            self._fallback_speech(text, "no MP3 player found for edge-tts")
            return
        tmp_name = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_name = tmp.name
            subprocess.run(
                [python, "-m", "edge_tts", "--voice", self.cfg.tts_edge_voice, "--text", text, "--write-media", tmp_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
                check=False,
            )
            play_cmd = _bx1_player_command(player, tmp_name, self.cfg.tts_volume, wav=False, playback_device=self.cfg.tts_playback_device)
            subprocess.run(play_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
        except Exception as exc:
            print(f"[audio] edge-tts failed: {exc}")
            self._fallback_speech(text, str(exc))
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass


    def _speak_elevenlabs_async(self, text: str) -> None:
        worker = threading.Thread(target=self._speak_elevenlabs_blocking, args=(text,), daemon=True)
        worker.start()

    def _speak_elevenlabs_blocking(self, text: str) -> None:
        api_key = (self.cfg.tts_elevenlabs_api_key or "").strip()
        voice_id = (self.cfg.tts_elevenlabs_voice_id or "").strip()
        model_id = (self.cfg.tts_elevenlabs_model_id or "eleven_flash_v2_5").strip() or "eleven_flash_v2_5"
        if not api_key:
            print("[audio] ElevenLabs API key is empty. Falling back to edge-tts/espeak-ng.")
            self._speak_edge_blocking(text)
            return
        if not voice_id:
            print("[audio] ElevenLabs voice_id is empty. Use Fetch Voices or paste a voice ID. Falling back to edge-tts/espeak-ng.")
            self._speak_edge_blocking(text)
            return
        player = shutil.which("mpg123") or shutil.which("mpv") or shutil.which("ffplay")
        if not player:
            print("[audio] No MP3 player found for ElevenLabs. Install mpg123/mpv/ffmpeg or use edge-tts/espeak-ng.")
            self._speak_edge_blocking(text)
            return

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": max(0.0, min(1.0, float(self.cfg.tts_elevenlabs_stability))),
                "similarity_boost": max(0.0, min(1.0, float(self.cfg.tts_elevenlabs_similarity_boost))),
                "style": max(0.0, min(1.0, float(self.cfg.tts_elevenlabs_style))),
                "use_speaker_boost": bool(self.cfg.tts_elevenlabs_use_speaker_boost),
            },
        }
        tmp_name = ""
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                    "xi-api-key": api_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                audio_bytes = resp.read()
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_name = tmp.name
            play_cmd = _bx1_player_command(player, tmp_name, self.cfg.tts_volume, wav=False, playback_device=self.cfg.tts_playback_device)
            subprocess.run(play_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = str(exc)
            print(f"[audio] ElevenLabs HTTP error {exc.code}: {detail}")
            self._speak_edge_blocking(text)
        except Exception as exc:
            print(f"[audio] ElevenLabs TTS failed: {exc}")
            self._speak_edge_blocking(text)
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass


def list_elevenlabs_voices(api_key: str, show_legacy: bool = True) -> list[dict]:
    """Return available ElevenLabs voices for the account/API key.

    This deliberately uses stdlib urllib so the UNO Q does not need another
    Python dependency just to populate the web dropdown.
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("ElevenLabs API key is empty")
    url = "https://api.elevenlabs.io/v1/voices"
    if show_legacy:
        url += "?show_legacy=true"
    req = urllib.request.Request(url, headers={"xi-api-key": key, "Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    voices = []
    for v in data.get("voices", []) or []:
        voices.append({
            "name": v.get("name", "Unnamed voice"),
            "voice_id": v.get("voice_id", ""),
            "category": v.get("category", ""),
            "description": v.get("description", ""),
        })
    return voices



# ---------------------------------------------------------------------------
# BX1 V8.3: microphone monitor, level metering, recording and basic STT tests.
# This deliberately uses ALSA tools (arecord/aplay/amixer) so it works before
# Vosk/sounddevice are installed. It is intended for UNO Q web diagnostics.
# ---------------------------------------------------------------------------


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp_float(value, lo: float, hi: float, default: float) -> float:
    v = _safe_float(value, default)
    return max(lo, min(hi, v))


def _pcm16_level(data: bytes, software_gain_db: float = 0.0) -> dict:
    """Return level statistics for little-endian signed 16-bit PCM data."""
    if not data:
        return {
            "rms_dbfs": -120.0,
            "peak_dbfs": -120.0,
            "rms_pct": 0.0,
            "peak_pct": 0.0,
            "clipped": False,
            "samples": 0,
        }
    usable = len(data) - (len(data) % 2)
    if usable <= 0:
        return {
            "rms_dbfs": -120.0,
            "peak_dbfs": -120.0,
            "rms_pct": 0.0,
            "peak_pct": 0.0,
            "clipped": False,
            "samples": 0,
        }
    samples = array("h")
    samples.frombytes(data[:usable])
    # UNO Q Debian is little endian; keep this here for desktop testing too.
    if getattr(os, "name", "") == "nt":
        pass
    gain = 10.0 ** (_clamp_float(software_gain_db, -24.0, 36.0, 0.0) / 20.0)
    n = len(samples)
    if n <= 0:
        return {
            "rms_dbfs": -120.0,
            "peak_dbfs": -120.0,
            "rms_pct": 0.0,
            "peak_pct": 0.0,
            "clipped": False,
            "samples": 0,
        }
    peak = 0.0
    total = 0.0
    clipped = False
    for raw in samples:
        v = float(raw) * gain
        av = abs(v)
        if av >= 32700:
            clipped = True
        if av > peak:
            peak = av
        total += v * v
    rms = math.sqrt(total / max(1, n))
    peak = min(32768.0, peak)
    rms = min(32768.0, rms)
    rms_db = 20.0 * math.log10(max(rms, 1.0) / 32768.0)
    peak_db = 20.0 * math.log10(max(peak, 1.0) / 32768.0)
    return {
        "rms_dbfs": round(max(-120.0, rms_db), 1),
        "peak_dbfs": round(max(-120.0, peak_db), 1),
        "rms_pct": round(max(0.0, min(100.0, rms / 32768.0 * 100.0)), 1),
        "peak_pct": round(max(0.0, min(100.0, peak / 32768.0 * 100.0)), 1),
        "clipped": bool(clipped),
        "samples": n,
    }


def _pcm16_to_mono_floats(data: bytes, channels: int = 1) -> list[float]:
    """Convert little-endian signed 16-bit PCM into mono floats (-1..1)."""
    if not data:
        return []
    usable = len(data) - (len(data) % 2)
    pcm = array("h")
    pcm.frombytes(data[:usable])
    if sys.byteorder != "little":
        pcm.byteswap()
    ch = max(1, int(channels or 1))
    if ch == 1:
        return [max(-1.0, min(1.0, float(v) / 32768.0)) for v in pcm]
    out: list[float] = []
    for i in range(0, len(pcm), ch):
        frame = pcm[i:i + ch]
        if not frame:
            continue
        out.append(max(-1.0, min(1.0, (sum(float(v) for v in frame) / len(frame)) / 32768.0)))
    return out


def _mono_floats_to_pcm16(samples: list[float]) -> bytes:
    pcm = array("h")
    for value in samples:
        v = max(-1.0, min(1.0, float(value)))
        pcm.append(int(round(v * 32767.0)))
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def _dbfs_from_floats(samples: list[float]) -> tuple[float, float]:
    if not samples:
        return -120.0, -120.0
    peak = max(abs(v) for v in samples)
    rms = math.sqrt(sum(v * v for v in samples) / max(1, len(samples)))
    rms_db = 20.0 * math.log10(max(rms, 1.0 / 32768.0))
    peak_db = 20.0 * math.log10(max(peak, 1.0 / 32768.0))
    return max(-120.0, rms_db), max(-120.0, peak_db)


class _Biquad:
    def __init__(self, b0: float, b1: float, b2: float, a1: float, a2: float) -> None:
        self.b0, self.b1, self.b2 = b0, b1, b2
        self.a1, self.a2 = a1, a2
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    @classmethod
    def notch(cls, sample_rate: int, frequency_hz: float, q: float = 25.0) -> "_Biquad":
        sr = max(8000.0, float(sample_rate or 16000))
        hz = max(1.0, min(sr * 0.45, float(frequency_hz)))
        qv = max(1.0, min(100.0, float(q)))
        w0 = 2.0 * math.pi * hz / sr
        alpha = math.sin(w0) / (2.0 * qv)
        c = math.cos(w0)
        a0 = 1.0 + alpha
        return cls(1.0 / a0, (-2.0 * c) / a0, 1.0 / a0, (-2.0 * c) / a0, (1.0 - alpha) / a0)

    def process(self, value: float) -> float:
        y = self.b0 * value + self.b1 * self.x1 + self.b2 * self.x2 - self.a1 * self.y1 - self.a2 * self.y2
        self.x2, self.x1 = self.x1, value
        self.y2, self.y1 = self.y1, y
        return y


class StreamingAudioProcessor:
    """Lightweight speech pre-processor suitable for the UNO Q.

    It uses a one-pole high-pass filter, one or more narrow notch filters and a
    soft expander/noise gate.  It deliberately avoids scipy so the live body
    service remains easy to install and recover.
    """

    def __init__(self, sample_rate: int = 16000, settings: Optional[dict[str, Any]] = None) -> None:
        self.sample_rate = max(8000, min(48000, int(sample_rate or 16000)))
        self.settings = dict(settings or {})
        self.hp_prev_x = 0.0
        self.hp_prev_y = 0.0
        self.notches: list[_Biquad] = []
        self._build_notches()

    def _enabled(self, key: str, default: bool) -> bool:
        value = self.settings.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
        return bool(value)

    def _float(self, key: str, default: float, lo: float, hi: float) -> float:
        return _clamp_float(self.settings.get(key, default), lo, hi, default)

    def _build_notches(self) -> None:
        self.notches = []
        if not self._enabled("notch_enabled", True):
            return
        base_hz = self._float("notch_hz", 50.0, 40.0, 70.0)
        harmonics = int(max(1, min(4, _safe_float(self.settings.get("notch_harmonics", 2), 2))))
        q = self._float("notch_q", 25.0, 2.0, 80.0)
        for harmonic in range(1, harmonics + 1):
            hz = base_hz * harmonic
            if hz < self.sample_rate * 0.45:
                self.notches.append(_Biquad.notch(self.sample_rate, hz, q=q))

    def process_floats(self, samples: list[float]) -> list[float]:
        if not samples:
            return []
        if not self._enabled("enabled", True):
            gain = 10.0 ** (self._float("software_gain_db", 0.0, -24.0, 36.0) / 20.0)
            return [max(-1.0, min(1.0, v * gain)) for v in samples]

        highpass_enabled = self._enabled("highpass_enabled", True)
        cutoff = self._float("highpass_hz", 90.0, 20.0, 300.0)
        dt = 1.0 / float(self.sample_rate)
        rc = 1.0 / (2.0 * math.pi * cutoff)
        hp_alpha = rc / (rc + dt)
        gain = 10.0 ** (self._float("software_gain_db", 0.0, -24.0, 36.0) / 20.0)

        filtered: list[float] = []
        for sample in samples:
            value = float(sample)
            if highpass_enabled:
                y = hp_alpha * (self.hp_prev_y + value - self.hp_prev_x)
                self.hp_prev_x, self.hp_prev_y = value, y
                value = y
            for notch in self.notches:
                value = notch.process(value)
            filtered.append(value * gain)

        if self._enabled("noise_reduction_enabled", True):
            rms_db, _ = _dbfs_from_floats(filtered)
            gate_db = self._float("noise_gate_dbfs", -48.0, -90.0, -5.0)
            strength = self._float("noise_reduction_strength", 0.20, 0.0, 1.0)
            knee_db = self._float("noise_gate_knee_db", 10.0, 2.0, 24.0)
            minimum_gain = max(0.02, 1.0 - 0.96 * strength)
            if rms_db <= gate_db:
                scale = minimum_gain
            elif rms_db < gate_db + knee_db:
                frac = (rms_db - gate_db) / knee_db
                scale = minimum_gain + (1.0 - minimum_gain) * frac
            else:
                scale = 1.0
            filtered = [v * scale for v in filtered]

        return [max(-1.0, min(1.0, v)) for v in filtered]

    def process_pcm16(self, data: bytes, channels: int = 1) -> tuple[bytes, dict[str, Any]]:
        raw = _pcm16_to_mono_floats(data, channels=channels)
        processed = self.process_floats(raw)
        raw_rms, raw_peak = _dbfs_from_floats(raw)
        clean_rms, clean_peak = _dbfs_from_floats(processed)
        return _mono_floats_to_pcm16(processed), {
            "raw_rms_dbfs": round(raw_rms, 1),
            "raw_peak_dbfs": round(raw_peak, 1),
            "rms_dbfs": round(clean_rms, 1),
            "peak_dbfs": round(clean_peak, 1),
            "filter_enabled": self._enabled("enabled", True),
        }


def build_audio_dsp_settings(config: Any) -> dict[str, Any]:
    """Build a normalised DSP settings dictionary from AudioConfig or dict."""
    def get(name: str, default: Any) -> Any:
        if isinstance(config, dict):
            return config.get(name, default)
        return getattr(config, name, default)

    return {
        "enabled": bool(get("audio_filter_enabled", True)),
        "highpass_enabled": bool(get("audio_highpass_enabled", True)),
        "highpass_hz": float(get("audio_highpass_hz", 90.0)),
        "notch_enabled": bool(get("audio_notch_enabled", True)),
        "notch_hz": float(get("audio_notch_hz", 50.0)),
        "notch_q": float(get("audio_notch_q", 25.0)),
        "notch_harmonics": int(get("audio_notch_harmonics", 2)),
        "noise_reduction_enabled": bool(get("audio_noise_reduction_enabled", True)),
        "noise_reduction_strength": float(get("audio_noise_reduction_strength", 0.20)),
        "noise_gate_dbfs": float(get("stt_noise_gate_dbfs", get("mic_noise_gate_dbfs", -48.0))),
        "noise_gate_knee_db": float(get("audio_noise_gate_knee_db", 10.0)),
        "software_gain_db": float(get("mic_software_gain_db", 0.0)),
    }


def process_wav_for_speech(input_filename: str | os.PathLike, output_filename: str | os.PathLike, settings: dict[str, Any]) -> dict[str, Any]:
    """Create a filtered mono 16-bit WAV used by Vosk and diagnostics."""
    src = Path(input_filename)
    dst = Path(output_filename)
    if not src.exists():
        return {"ok": False, "error": f"file not found: {src}"}
    try:
        with wave.open(str(src), "rb") as wf:
            channels = int(wf.getnchannels())
            width = int(wf.getsampwidth())
            rate = int(wf.getframerate())
            frames = int(wf.getnframes())
            raw = wf.readframes(frames)
        if width != 2:
            return {"ok": False, "error": f"WAV must be 16-bit PCM, got sample width {width}"}
        processor = StreamingAudioProcessor(rate, settings=settings)
        clean_bytes, stats = processor.process_pcm16(raw, channels=channels)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dst), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(clean_bytes)
        report = {
            "ok": True,
            "input": str(src),
            "output": str(dst),
            "sample_rate": rate,
            "duration_s": round(frames / float(rate or 1), 3),
            "settings": dict(settings),
            **stats,
        }
        return report
    except Exception as exc:
        return {"ok": False, "error": str(exc), "input": str(src), "output": str(dst)}


def analyse_pcm_voice_activity(data: bytes, sample_rate: int, noise_gate_dbfs: float = -48.0, noise_margin_db: float = 6.0, frame_ms: int = 20) -> dict[str, Any]:
    samples = _pcm16_to_mono_floats(data, channels=1)
    sr = max(8000, int(sample_rate or 16000))
    frame_n = max(80, int(sr * max(10, min(50, frame_ms)) / 1000.0))
    frame_levels: list[float] = []
    for start in range(0, len(samples), frame_n):
        chunk = samples[start:start + frame_n]
        if not chunk:
            continue
        rms_db, _ = _dbfs_from_floats(chunk)
        frame_levels.append(rms_db)
    if not frame_levels:
        return {"voiced_ms": 0, "speech_ratio": 0.0, "noise_floor_dbfs": -120.0, "threshold_dbfs": float(noise_gate_dbfs), "frames": 0}
    ordered = sorted(frame_levels)
    noise_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.20)))
    noise_floor = ordered[noise_index]
    threshold = max(float(noise_gate_dbfs), noise_floor + float(noise_margin_db))
    voiced = [level >= threshold for level in frame_levels]
    voiced_count = sum(1 for flag in voiced if flag)
    longest = 0
    current = 0
    for flag in voiced:
        if flag:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    frame_duration_ms = frame_n / float(sr) * 1000.0
    return {
        "voiced_ms": int(round(voiced_count * frame_duration_ms)),
        "longest_voiced_ms": int(round(longest * frame_duration_ms)),
        "speech_ratio": round(voiced_count / max(1, len(voiced)), 3),
        "noise_floor_dbfs": round(noise_floor, 1),
        "threshold_dbfs": round(threshold, 1),
        "frames": len(frame_levels),
    }


def compact_spectrum_from_pcm16(data: bytes, sample_rate: int, bins: int = 48) -> list[dict[str, Any]]:
    """Small log-spaced spectrum for the live browser display."""
    samples = _pcm16_to_mono_floats(data, channels=1)
    if not samples:
        return []
    n = min(1024, len(samples))
    if n < 128:
        return []
    window = samples[-n:]
    if n > 1:
        window = [window[i] * (0.5 - 0.5 * math.cos(2.0 * math.pi * i / float(n - 1))) for i in range(n)]
    sr = max(8000, int(sample_rate or 16000))
    max_hz = min(8000.0, sr / 2.0)
    count = max(16, min(80, int(bins or 48)))
    out: list[dict[str, Any]] = []
    for idx in range(count):
        frac = idx / float(max(1, count - 1))
        hz = 40.0 * ((max_hz / 40.0) ** frac) if max_hz > 40.0 else max_hz * frac
        k = max(1, min(n // 2, int(round(hz * n / sr))))
        re_part = 0.0
        im_part = 0.0
        for i, value in enumerate(window):
            angle = 2.0 * math.pi * k * i / float(n)
            re_part += value * math.cos(angle)
            im_part -= value * math.sin(angle)
        mag = math.sqrt(re_part * re_part + im_part * im_part) / max(1.0, n / 2.0)
        db = max(-120.0, 20.0 * math.log10(max(mag, 1.0e-7)))
        out.append({"hz": int(round(k * sr / n)), "db": round(db, 1)})
    return out

def analyse_wav_file(filename: str | os.PathLike, software_gain_db: float = 0.0) -> dict:
    path = Path(filename)
    if not path.exists():
        return {"ok": False, "error": f"file not found: {path}"}
    try:
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            data = wf.readframes(frames)
        if sample_width != 2:
            return {"ok": False, "error": f"unsupported sample width: {sample_width}", "filename": str(path)}
        level = _pcm16_level(data, software_gain_db=software_gain_db)
        level.update({
            "ok": True,
            "filename": str(path),
            "channels": channels,
            "sample_width": sample_width,
            "sample_rate": sample_rate,
            "frames": frames,
            "duration_s": round(float(frames) / float(sample_rate or 1), 3),
            "size_bytes": path.stat().st_size,
        })
        return level
    except Exception as exc:
        return {"ok": False, "error": str(exc), "filename": str(path)}


def _read_wav_pcm16_mono(filename: str | os.PathLike) -> dict:
    """Read a WAV file and return mono float samples in the range -1..1.

    This deliberately uses only the Python standard library so the UNO Q does not
    need numpy/scipy just for diagnostics.
    """
    path = Path(filename)
    if not path.exists():
        return {"ok": False, "error": f"file not found: {path}", "samples": []}
    try:
        with wave.open(str(path), "rb") as wf:
            channels = int(wf.getnchannels())
            sample_width = int(wf.getsampwidth())
            sample_rate = int(wf.getframerate())
            frames = int(wf.getnframes())
            data = wf.readframes(frames)
        if sample_width != 2:
            return {"ok": False, "error": f"unsupported sample width: {sample_width}", "samples": []}
        ints = array("h")
        usable = len(data) - (len(data) % 2)
        ints.frombytes(data[:usable])
        # Debian/UNO Q is little endian. Keep this safeguard for any big-endian test platform.
        if sys.byteorder != "little":
            ints.byteswap()
        mono: list[float] = []
        if channels <= 1:
            mono = [max(-1.0, min(1.0, float(v) / 32768.0)) for v in ints]
        else:
            # Average channels for display/STT diagnostics.
            for i in range(0, len(ints) - channels + 1, channels):
                acc = 0.0
                for c in range(channels):
                    acc += float(ints[i + c])
                mono.append(max(-1.0, min(1.0, acc / float(channels) / 32768.0)))
        return {
            "ok": True,
            "filename": str(path),
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": frames,
            "duration_s": round(float(frames) / float(sample_rate or 1), 3),
            "samples": mono,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "samples": []}


def analyse_wav_diagnostics(filename: str | os.PathLike, software_gain_db: float = 0.0, max_points: int = 600, fft_bins: int = 80) -> dict:
    """Return waveform, rolling level and a light FFT for web diagnostics.

    The FFT is intentionally small and standard-library-only. It is good enough
    to reveal static, hum and whether speech energy is present without adding
    heavy dependencies to the UNO Q.
    """
    base = analyse_wav_file(filename, software_gain_db=software_gain_db)
    read = _read_wav_pcm16_mono(filename)
    if not read.get("ok"):
        return {"ok": False, "analysis": base, "error": read.get("error", "could not read WAV")}

    samples = read.get("samples", []) or []
    sr = int(read.get("sample_rate") or 16000)
    n = len(samples)
    if n <= 0:
        return {"ok": False, "analysis": base, "error": "WAV contains no samples"}

    gain = 10.0 ** (_clamp_float(software_gain_db, -24.0, 36.0, 0.0) / 20.0)
    g_samples = [max(-1.0, min(1.0, float(v) * gain)) for v in samples]
    duration = float(n) / float(sr or 1)

    # Waveform preview: min/max envelope per display bucket.
    max_points = int(max(100, min(1200, max_points)))
    bucket = max(1, int(math.ceil(n / max_points)))
    waveform = []
    for start in range(0, n, bucket):
        chunk = g_samples[start:start + bucket]
        if not chunk:
            continue
        waveform.append({
            "t": round(start / float(sr or 1), 3),
            "min": round(min(chunk), 4),
            "max": round(max(chunk), 4),
        })

    # Rolling level timeline: RMS and peak every 100 ms.
    win = max(1, int(sr * 0.10))
    timeline = []
    for start in range(0, n, win):
        chunk = g_samples[start:start + win]
        if not chunk:
            continue
        peak = max(abs(v) for v in chunk)
        rms = math.sqrt(sum(v * v for v in chunk) / max(1, len(chunk)))
        rms_db = 20.0 * math.log10(max(rms, 1.0 / 32768.0))
        peak_db = 20.0 * math.log10(max(peak, 1.0 / 32768.0))
        timeline.append({
            "t": round(start / float(sr or 1), 3),
            "rms_dbfs": round(max(-120.0, rms_db), 1),
            "peak_dbfs": round(max(-120.0, peak_db), 1),
        })

    # FFT: use the loudest 2048/4096-sample window so a short spoken phrase is visible.
    fft_n = 2048 if sr <= 24000 else 4096
    fft_n = min(fft_n, n)
    if fft_n < 256:
        fft_n = n
    step = max(1, int(fft_n / 2))
    best_start = 0
    best_energy = -1.0
    for start in range(0, max(1, n - fft_n + 1), step):
        chunk = g_samples[start:start + fft_n]
        energy = sum(v * v for v in chunk)
        if energy > best_energy:
            best_energy = energy
            best_start = start
    window = g_samples[best_start:best_start + fft_n]
    if len(window) < fft_n:
        window = window + [0.0] * (fft_n - len(window))
    # Hann window reduces leakage.
    if fft_n > 1:
        window = [window[i] * (0.5 - 0.5 * math.cos(2.0 * math.pi * i / float(fft_n - 1))) for i in range(fft_n)]

    fft_bins = int(max(16, min(160, fft_bins)))
    max_hz = min(8000.0, float(sr) / 2.0)
    # Log-ish spacing is more useful for speech than equal linear bins.
    freqs = []
    f_min = 50.0
    for i in range(fft_bins):
        frac = i / float(max(1, fft_bins - 1))
        hz = f_min * ((max_hz / f_min) ** frac) if max_hz > f_min else max_hz * frac
        freqs.append(hz)
    spectrum = []
    for hz in freqs:
        k = int(round(hz * fft_n / float(sr or 1)))
        k = max(1, min(int(fft_n / 2), k))
        re_part = 0.0
        im_part = 0.0
        # Direct DFT for selected bins only.
        for i, val in enumerate(window):
            angle = 2.0 * math.pi * k * i / float(fft_n)
            re_part += val * math.cos(angle)
            im_part -= val * math.sin(angle)
        mag = math.sqrt(re_part * re_part + im_part * im_part) / max(1.0, fft_n / 2.0)
        db = 20.0 * math.log10(max(mag, 1.0e-7))
        spectrum.append({"hz": int(round(k * float(sr) / float(fft_n))), "db": round(max(-120.0, db), 1)})

    # Simple noise/speech hints.
    peak_db = float(base.get("peak_dbfs", -120.0) if base.get("ok") else -120.0)
    rms_db = float(base.get("rms_dbfs", -120.0) if base.get("ok") else -120.0)
    warnings: list[str] = []
    if peak_db < -35:
        warnings.append("Recorded sample is very quiet; increase mic gain or speak closer.")
    if peak_db > -1.0 or bool(base.get("clipped")):
        warnings.append("Recorded sample is close to clipping; reduce capture volume or software gain.")
    if (peak_db - rms_db) < 3.0 and rms_db > -35.0:
        warnings.append("Signal has low crest factor; this can indicate steady noise/static rather than speech.")

    return {
        "ok": True,
        "analysis": base,
        "sample_rate": sr,
        "duration_s": round(duration, 3),
        "waveform": waveform,
        "level_timeline": timeline,
        "spectrum": spectrum,
        "fft_window": {"start_s": round(best_start / float(sr or 1), 3), "samples": fft_n},
        "warnings": warnings,
    }


def list_audio_capture_devices() -> dict:
    """List ALSA capture devices and suggest plughw strings."""
    exe = shutil.which("arecord")
    if not exe:
        return {"ok": False, "error": "arecord not found", "devices": []}
    try:
        res = subprocess.run([exe, "-l"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "devices": []}
    raw = (res.stdout or "") + (res.stderr or "")
    devices = [{"id": "default", "label": "default - ALSA default capture device"}]
    pattern = re.compile(r"card\s+(\d+):\s*([^,]+),\s*device\s+(\d+):\s*([^\n]+)", re.IGNORECASE)
    for m in pattern.finditer(raw):
        card = m.group(1)
        card_name = m.group(2).strip()
        dev = m.group(3)
        dev_name = m.group(4).strip()
        devices.append({
            "id": f"plughw:{card},{dev}",
            "label": f"plughw:{card},{dev} - {card_name} / {dev_name}",
            "card": int(card),
            "device": int(dev),
            "card_name": card_name,
            "device_name": dev_name,
        })
    return {"ok": res.returncode == 0, "returncode": res.returncode, "raw": raw.strip(), "devices": devices}


def list_audio_playback_devices() -> dict:
    """List ALSA playback devices and suggest plughw strings for aplay."""
    exe = shutil.which("aplay")
    if not exe:
        return {"ok": False, "error": "aplay not found", "devices": []}
    try:
        res = subprocess.run([exe, "-l"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "devices": []}
    raw = (res.stdout or "") + (res.stderr or "")
    devices = [{"id": "default", "label": "default - ALSA default playback device"}]
    pattern = re.compile(r"card\s+(\d+):\s*([^,]+),\s*device\s+(\d+):\s*([^\n]+)", re.IGNORECASE)
    for m in pattern.finditer(raw):
        card = m.group(1)
        card_name = m.group(2).strip()
        dev = m.group(3)
        dev_name = m.group(4).strip()
        devices.append({
            "id": f"plughw:{card},{dev}",
            "label": f"plughw:{card},{dev} - {card_name} / {dev_name}",
            "card": int(card),
            "device": int(dev),
            "card_name": card_name,
            "device_name": dev_name,
        })
    return {"ok": res.returncode == 0, "returncode": res.returncode, "raw": raw.strip(), "devices": devices}


def set_alsa_capture_volume(percent: int | float | str, control: str = "Capture") -> dict:
    """Best-effort capture gain adjustment through amixer."""
    try:
        pct = int(max(0, min(100, float(percent))))
    except Exception:
        pct = 70
    exe = shutil.which("amixer")
    if not exe:
        return {"ok": False, "error": "amixer not found", "requested_percent": pct}
    controls = []
    if control:
        controls.append(str(control))
    for c in ("Capture", "Mic", "Internal Mic", "Digital", "Input Source"):
        if c not in controls:
            controls.append(c)
    attempts = []
    for c in controls:
        cmd = [exe, "set", c, f"{pct}%", "cap"]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4, check=False)
            attempts.append({"control": c, "returncode": res.returncode, "stdout": (res.stdout or "")[-500:], "stderr": (res.stderr or "")[-500:]})
            if res.returncode == 0:
                return {"ok": True, "control": c, "percent": pct, "attempts": attempts}
        except Exception as exc:
            attempts.append({"control": c, "error": str(exc)})
    return {"ok": False, "error": "no ALSA capture control accepted the requested volume", "percent": pct, "attempts": attempts}


def record_microphone_sample(filename: str | os.PathLike, device: str = "default", sample_rate: int = 16000, seconds: float = 5.0, channels: int = 1, cancel_event: Any = None, frame_sink: Optional[Callable[[bytes], None]] = None, stop_event: Any = None) -> dict:
    exe = shutil.which("arecord")
    if not exe:
        return {"ok": False, "error": "arecord not found"}
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(0.5, min(30.0, _safe_float(seconds, 5.0)))
    rate = int(max(8000, min(48000, _safe_float(sample_rate, 16000))))
    ch = int(max(1, min(2, _safe_float(channels, 1))))
    # Use arecord's bounded duration plus a monotonic watchdog.  Popen lets us
    # forcibly terminate a wedged ALSA process instead of allowing a browser
    # request to remain in recording forever.
    requested = float(seconds)
    if frame_sink is not None:
        cmd = [exe, "-q", "-D", str(device or "default"), "-t", "raw", "-f", "S16_LE", "-r", str(rate), "-c", str(ch), "-"]
        started = time.monotonic()
        proc = None
        raw = bytearray()
        frame_bytes = max(2, int(rate * 0.02) * ch * 2)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = started + requested + 3.0
            while time.monotonic() < deadline and proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    proc.terminate()
                    proc.communicate(timeout=2.0)
                    return {"ok": False, "cancelled": True, "state": "cancelled", "error": "capture cancelled", "filename": str(path), "requested_duration_s": requested, "elapsed_duration_s": round(time.monotonic() - started, 3)}
                if stop_event is not None and stop_event.is_set():
                    break
                block = proc.stdout.read(frame_bytes) if proc.stdout is not None else b""
                if not block:
                    break
                raw.extend(block)
                try:
                    frame_sink(bytes(block))
                except Exception:
                    pass
            if proc.poll() is None:
                proc.terminate()
            stdout, stderr = proc.communicate(timeout=2.0)
            if not raw:
                return {"ok": False, "error": "diagnostic capture returned no audio", "state": "failed", "filename": str(path), "requested_duration_s": requested}
            _write_pcm16_wav(path, bytes(raw), rate, ch)
            elapsed = time.monotonic() - started
            report = {"ok": True, "command": cmd, "returncode": proc.returncode, "stdout": (stdout or b"")[-1000:].decode(errors="replace"), "stderr": (stderr or b"")[-1000:].decode(errors="replace"), "filename": str(path), "requested_duration_s": requested, "elapsed_duration_s": round(elapsed, 3), "actual_duration_s": round(len(raw) / float(rate * ch * 2), 3), "state": "complete"}
            report["analysis"] = analyse_wav_file(path)
            return report
        except Exception as exc:
            try:
                if proc is not None and proc.poll() is None: proc.terminate()
            except Exception:
                pass
            return {"ok": False, "error": str(exc), "state": "failed", "filename": str(path), "requested_duration_s": requested}
    cmd = [exe, "-D", str(device or "default"), "-t", "wav", "-f", "S16_LE", "-r", str(rate), "-c", str(ch), "-d", str(int(round(requested))), str(path)]
    started = time.monotonic()
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = started + requested + 3.0
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                stdout, stderr = proc.communicate(timeout=2.0)
                return {"ok": False, "cancelled": True, "error": "capture cancelled", "state": "cancelled", "command": cmd, "returncode": proc.returncode, "stdout": (stdout or "")[-1000:], "stderr": (stderr or "")[-1000:], "filename": str(path), "requested_duration_s": requested, "elapsed_duration_s": round(time.monotonic() - started, 3)}
            if time.monotonic() >= deadline:
                break
            try:
                proc.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
        if proc.poll() is None:
            proc.terminate()
            try: stdout, stderr = proc.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill(); stdout, stderr = proc.communicate()
            return {"ok": False, "error": "capture watchdog exceeded requested duration", "state": "failed", "command": cmd, "returncode": proc.returncode, "stdout": (stdout or "")[-1000:], "stderr": (stderr or "")[-1000:], "filename": str(path), "requested_duration_s": requested, "elapsed_duration_s": round(time.monotonic() - started, 3)}
        stdout, stderr = proc.communicate()
        elapsed = time.monotonic() - started
        report = {"ok": proc.returncode == 0, "command": cmd, "returncode": proc.returncode, "stdout": (stdout or "")[-1000:], "stderr": (stderr or "")[-1000:], "filename": str(path), "requested_duration_s": requested, "elapsed_duration_s": round(elapsed, 3), "state": "complete" if proc.returncode == 0 else "failed"}
        if proc.returncode == 0:
            report["analysis"] = analyse_wav_file(path)
        return report
    except Exception as exc:
        return {"ok": False, "error": str(exc), "command": cmd, "filename": str(path)}




def _pcm16_rms_dbfs(data: bytes, channels: int = 1, gain_db: float = 0.0) -> float:
    """Return RMS level for little-endian signed 16-bit PCM."""
    if not data:
        return -120.0
    pcm = array("h")
    pcm.frombytes(data[: len(data) - (len(data) % 2)])
    if sys.byteorder != "little":
        pcm.byteswap()
    if not pcm:
        return -120.0
    ch = max(1, int(channels or 1))
    if ch > 1:
        mono = []
        for pos in range(0, len(pcm), ch):
            frame = pcm[pos:pos + ch]
            if frame:
                mono.append(int(sum(frame) / len(frame)))
    else:
        mono = pcm
    if not mono:
        return -120.0
    acc = 0.0
    for sample in mono:
        acc += float(sample) * float(sample)
    rms = math.sqrt(acc / max(1, len(mono))) / 32768.0
    if rms <= 1.0e-9:
        return -120.0
    return max(-120.0, min(6.0, 20.0 * math.log10(rms) + float(gain_db or 0.0)))


def _write_pcm16_wav(filename: str | os.PathLike, pcm_bytes: bytes, sample_rate: int, channels: int = 1) -> None:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(max(1, int(channels or 1)))
        wf.setsampwidth(2)
        wf.setframerate(max(8000, int(sample_rate or 16000)))
        wf.writeframes(pcm_bytes)


def _atomic_copy_file(source: str | os.PathLike, destination: str | os.PathLike) -> None:
    """Publish a completed diagnostic file without exposing a partial WAV."""
    src = Path(source)
    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    temporary = dst.with_name(dst.name + f".{os.getpid()}.tmp")
    shutil.copyfile(src, temporary)
    os.replace(temporary, dst)


def _cleanup_stt_debug_files(root: Path, keep_capture_ids: int = 30) -> None:
    """Bound /tmp growth while retaining recent capture triplets for playback."""
    try:
        files = sorted(
            root.glob("bx1_stt_*_*.wav"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        # Three files are normally generated per capture.
        for path in files[max(3, int(keep_capture_ids) * 3):]:
            try:
                path.unlink()
            except OSError:
                pass
    except Exception:
        pass


def record_microphone_utterance(
    filename: str | os.PathLike,
    *,
    device: str = "default",
    sample_rate: int = 16000,
    channels: int = 1,
    start_timeout_s: float = 8.0,
    max_utterance_s: float = 20.0,
    pre_roll_ms: int = 450,
    end_silence_ms: int = 1100,
    post_roll_ms: int = 250,
    start_trigger_ms: int = 100,
    speech_resume_trigger_ms: int = 140,
    transient_guard_after_ms: int = 220,
    endpoint_hysteresis_db: float = 3.0,
    fixed_gate_dbfs: float = -48.0,
    adaptive_threshold_enabled: bool = True,
    adaptive_margin_db: float = 8.0,
    software_gain_db: float = 0.0,
    frame_ms: int = 20,
    cancel_event: Optional[threading.Event] = None,
    level_observer: Optional[Callable[[dict[str, Any]], None]] = None,
    frame_guard: Optional[Callable[[bytes], bool]] = None,
) -> dict[str, Any]:
    """Capture one natural utterance from ALSA using lightweight endpointing.

    The function deliberately uses ``arecord`` rather than ``sounddevice`` on the
    UNO Q. It honours ``plughw:x,y`` selections and avoids the dependency/fallback
    confusion that previously produced repeated ``sounddevice unavailable`` logs.
    """
    if cancel_event is not None and cancel_event.is_set():
        return {
            "ok": True, "cancelled": True, "speech_started": False,
            "filename": "", "duration_s": 0.0, "close_reason": "cancelled",
            "reason": "capture cancelled for microphone handover",
        }

    exe = shutil.which("arecord")
    if not exe:
        return {"ok": False, "error": "arecord not found", "reason": "arecord not found"}

    rate = int(max(8000, min(48000, _safe_float(sample_rate, 16000))))
    ch = int(max(1, min(2, _safe_float(channels, 1))))
    frame_ms = int(max(10, min(100, frame_ms)))
    samples_per_frame = max(1, int(rate * (frame_ms / 1000.0)))
    frame_bytes = samples_per_frame * ch * 2
    pre_frames = max(1, int(math.ceil(max(0, pre_roll_ms) / frame_ms)))
    start_frames_required = max(1, int(math.ceil(max(frame_ms, start_trigger_ms) / frame_ms)))
    resume_frames_required = max(1, int(math.ceil(max(frame_ms, speech_resume_trigger_ms) / frame_ms)))
    transient_guard_frames = max(0, int(math.ceil(max(0, transient_guard_after_ms) / frame_ms)))
    silence_frames_required = max(1, int(math.ceil(max(frame_ms, end_silence_ms) / frame_ms)))
    post_frames = max(0, int(math.ceil(max(0, post_roll_ms) / frame_ms)))
    start_timeout_s = max(1.0, min(60.0, float(start_timeout_s or 8.0)))
    max_utterance_s = max(1.0, min(120.0, float(max_utterance_s or 20.0)))
    fixed_gate = max(-90.0, min(-5.0, float(fixed_gate_dbfs or -48.0)))
    adaptive_margin = max(0.0, min(30.0, float(adaptive_margin_db or 8.0)))
    endpoint_hysteresis = max(0.0, min(12.0, float(endpoint_hysteresis_db or 0.0)))

    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        exe, "-q", "-D", str(device or "default"), "-t", "raw",
        "-f", "S16_LE", "-r", str(rate), "-c", str(ch), "-",
    ]
    proc: Optional[subprocess.Popen[bytes]] = None
    pre: deque[bytes] = deque(maxlen=pre_frames)
    captured: list[bytes] = []
    noise_levels: deque[float] = deque(maxlen=max(20, int(2000 / frame_ms)))
    level_trace: deque[float] = deque(maxlen=250)
    speech_started = False
    speech_started_at = 0.0
    start_run = 0
    silence_run = 0
    resume_run = 0
    ignored_transients = 0
    post_remaining = 0
    close_reason = ""
    started_mono = time.monotonic()
    peak_dbfs = -120.0
    current_threshold = fixed_gate
    continue_threshold = fixed_gate
    read_error = ""

    try:
        if cancel_event is not None and cancel_event.is_set():
            return {
                "ok": True, "cancelled": True, "speech_started": False,
                "filename": "", "command": cmd, "sample_rate": rate, "channels": ch,
                "duration_s": 0.0, "close_reason": "cancelled",
                "reason": "capture cancelled for microphone handover",
            }
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.stdout is None:
            raise RuntimeError("arecord stdout pipe unavailable")
        while True:
            if cancel_event is not None and cancel_event.is_set():
                close_reason = "cancelled"
                break
            now = time.monotonic()
            if not speech_started and now - started_mono >= start_timeout_s:
                close_reason = "start timeout"
                break
            if speech_started and now - speech_started_at >= max_utterance_s:
                close_reason = "maximum utterance length"
                break
            block = proc.stdout.read(frame_bytes)
            if not block:
                read_error = "arecord stopped before the utterance completed"
                close_reason = "capture ended"
                break
            if len(block) < frame_bytes:
                block += b"\x00" * (frame_bytes - len(block))
            frame_level = _pcm16_level(block, software_gain_db=software_gain_db)
            # The Body-owned speaker gate is evaluated on every frame, not
            # after endpointing has produced a completed utterance. This
            # prevents speaker audio from entering pre-roll, VAD or the STT
            # handoff queue when playback overlaps an open capture.
            if frame_guard is not None:
                try:
                    if frame_guard(block):
                        if level_observer is not None:
                            try:
                                level_observer({"rms_dbfs": float(frame_level["rms_dbfs"]), "peak_dbfs": float(frame_level["peak_dbfs"]), "noise_floor_dbfs": None, "threshold_dbfs": fixed_gate, "gate_open": False, "speech_detected": False, "speaker_inhibited": True, "captured_at": time.time()})
                            except Exception:
                                pass
                        pre.clear()
                        captured.clear()
                        noise_levels.clear()
                        level_trace.clear()
                        speech_started = False
                        speech_started_at = 0.0
                        start_run = 0
                        silence_run = 0
                        resume_run = 0
                        post_remaining = 0
                        started_mono = time.monotonic()
                        close_reason = "speaker inhibited"
                        continue
                except Exception:
                    # A faulty diagnostic guard must not break microphone
                    # capture; the normal generation/suppression checks remain
                    # in the caller as a secondary safety net.
                    pass
            level = float(frame_level["rms_dbfs"])
            peak_dbfs = max(peak_dbfs, level)
            level_trace.append(round(level, 1))

            if not speech_started:
                pre.append(block)
                # Estimate the ambient floor from the lower part of all frames
                # observed before speech starts. Restricting samples to below the
                # fixed gate made a steady fan at -40 dBFS look like speech forever.
                # The lower quintile remains robust when the first syllable is also
                # present in the buffer.
                noise_levels.append(level)
                if noise_levels:
                    ordered = sorted(noise_levels)
                    noise_floor = ordered[max(0, int((len(ordered) - 1) * 0.20))]
                else:
                    noise_floor = fixed_gate - adaptive_margin
                current_threshold = fixed_gate
                if adaptive_threshold_enabled:
                    current_threshold = max(fixed_gate, min(-12.0, noise_floor + adaptive_margin))
                continue_threshold = max(-90.0, current_threshold - endpoint_hysteresis)
                if level >= current_threshold:
                    start_run += 1
                else:
                    start_run = 0
                if start_run >= start_frames_required:
                    speech_started = True
                    speech_started_at = now - ((start_run - 1) * frame_ms / 1000.0)
                    captured.extend(list(pre))
                    pre.clear()
                    silence_run = 0
                    resume_run = 0
                if level_observer is not None:
                    try:
                        level_observer({"rms_dbfs": level, "peak_dbfs": float(frame_level["peak_dbfs"]), "noise_floor_dbfs": round(float(noise_floor), 1), "threshold_dbfs": round(float(current_threshold), 1), "gate_open": bool(level >= current_threshold), "speech_detected": bool(speech_started), "captured_at": time.time()})
                    except Exception:
                        pass
                continue

            captured.append(block)
            if level >= continue_threshold:
                # During normal connected speech, reset immediately. Once the
                # utterance has already been quiet for a while, require a
                # sustained return of speech. A short click/chirp then only
                # delays closing by its own duration instead of restarting the
                # complete end-silence timer.
                if silence_run < transient_guard_frames:
                    silence_run = 0
                    resume_run = 0
                    post_remaining = 0
                else:
                    resume_run += 1
                    if resume_run >= resume_frames_required:
                        silence_run = 0
                        resume_run = 0
                        post_remaining = 0
                    else:
                        silence_run += 1
            else:
                if resume_run > 0:
                    ignored_transients += 1
                resume_run = 0
                silence_run += 1
            if level_observer is not None:
                try:
                    level_observer({"rms_dbfs": level, "peak_dbfs": float(frame_level["peak_dbfs"]), "noise_floor_dbfs": round(float(noise_floor), 1), "threshold_dbfs": round(float(continue_threshold), 1), "gate_open": bool(level >= continue_threshold), "speech_detected": True, "captured_at": time.time()})
                except Exception:
                    pass
            # Do not close in the middle of a possible resumed phrase. Wait up
            # to speech_resume_trigger_ms for it either to prove itself as
            # speech or collapse as an isolated transient.
            if resume_run <= 0:
                if silence_run >= silence_frames_required and post_remaining <= 0:
                    if post_frames <= 0:
                        close_reason = "end silence"
                        break
                    post_remaining = post_frames
                elif post_remaining > 0:
                    post_remaining -= 1
                    if post_remaining <= 0:
                        close_reason = "end silence"
                        break

        if close_reason == "cancelled":
            return {
                "ok": True, "cancelled": True, "speech_started": False,
                "filename": "", "command": cmd, "sample_rate": rate, "channels": ch,
                "duration_s": 0.0, "close_reason": "cancelled",
                "reason": "capture cancelled for microphone handover",
                "threshold_dbfs": round(current_threshold, 1),
                "continue_threshold_dbfs": round(continue_threshold, 1),
                "peak_dbfs": round(peak_dbfs, 1),
                "level_trace_dbfs": list(level_trace),
            }
        if speech_started and captured:
            pcm = b"".join(captured)
            _write_pcm16_wav(path, pcm, rate, ch)
            duration_s = len(pcm) / float(rate * ch * 2)
            noise_floor = sorted(noise_levels)[len(noise_levels) // 2] if noise_levels else None
            return {
                "ok": True,
                "speech_started": True,
                "filename": str(path),
                "command": cmd,
                "sample_rate": rate,
                "channels": ch,
                "duration_s": round(duration_s, 3),
                "waited_for_speech_s": round(max(0.0, speech_started_at - started_mono), 3),
                "close_reason": close_reason or "completed",
                "threshold_dbfs": round(current_threshold, 1),
                "continue_threshold_dbfs": round(continue_threshold, 1),
                "noise_floor_dbfs": round(float(noise_floor), 1) if noise_floor is not None else None,
                "peak_dbfs": round(peak_dbfs, 1),
                "pre_roll_ms": pre_roll_ms,
                "end_silence_ms": end_silence_ms,
                "post_roll_ms": post_roll_ms,
                "speech_resume_trigger_ms": speech_resume_trigger_ms,
                "transient_guard_after_ms": transient_guard_after_ms,
                "endpoint_hysteresis_db": endpoint_hysteresis,
                "ignored_transients": ignored_transients,
                "level_trace_dbfs": list(level_trace),
                "analysis": analyse_wav_file(path),
            }
        return {
            "ok": True,
            "speech_started": False,
            "filename": "",
            "command": cmd,
            "sample_rate": rate,
            "channels": ch,
            "duration_s": 0.0,
            "close_reason": close_reason or "no speech",
            "reason": "no speech detected before start timeout",
            "threshold_dbfs": round(current_threshold, 1),
            "continue_threshold_dbfs": round(continue_threshold, 1),
            "peak_dbfs": round(peak_dbfs, 1),
            "level_trace_dbfs": list(level_trace),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "reason": "capture failed", "command": cmd, "filename": str(path)}
    finally:
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            if read_error:
                try:
                    stderr = (proc.stderr.read() if proc.stderr is not None else b"").decode("utf-8", errors="replace")[-1000:]
                    if stderr:
                        read_error += ": " + stderr.strip()
                except Exception:
                    pass

def play_audio_file(filename: str | os.PathLike, device: str = "default", timeout_s: float = 30.0) -> dict:
    path = Path(filename)
    if not path.exists():
        return {"ok": False, "error": f"file not found: {path}"}
    player = shutil.which("aplay") or shutil.which("paplay") or shutil.which("ffplay")
    if not player:
        return {"ok": False, "error": "no audio player found; install/use aplay"}
    player_name = os.path.basename(player).lower()
    device = str(device or "default")
    if player_name.startswith("ffplay"):
        cmd = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    elif player_name.startswith("aplay"):
        cmd = [player, "-D", device, str(path)]
    else:
        cmd = [player, str(path)]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=max(1.0, float(timeout_s)), check=False)
        return {
            "ok": res.returncode == 0,
            "command": cmd,
            "returncode": res.returncode,
            "stdout": (res.stdout or "")[-1000:],
            "stderr": (res.stderr or "")[-1000:],
            "filename": str(path),
            "device": device,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "command": cmd, "filename": str(path), "device": device}


def _vosk_result_summary(results: list[dict[str, Any]], final: dict[str, Any]) -> dict[str, Any]:
    all_results = list(results) + ([final] if isinstance(final, dict) else [])
    words: list[dict[str, Any]] = []
    texts: list[str] = []
    for result in all_results:
        text = str(result.get("text") or "").strip()
        if text:
            texts.append(text)
        for word in result.get("result", []) or []:
            if isinstance(word, dict):
                words.append(dict(word))
    confidences = [float(w.get("conf", 0.0)) for w in words if w.get("conf") is not None]
    starts = [float(w.get("start", 0.0)) for w in words if w.get("start") is not None]
    ends = [float(w.get("end", 0.0)) for w in words if w.get("end") is not None]
    return {
        "text": " ".join(texts).strip(),
        "words": words,
        "word_count": len(words),
        "average_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "minimum_confidence": round(min(confidences), 3) if confidences else None,
        "maximum_confidence": round(max(confidences), 3) if confidences else None,
        "recognised_start_s": round(min(starts), 3) if starts else None,
        "recognised_end_s": round(max(ends), 3) if ends else None,
        "recognised_duration_s": round(max(ends) - min(starts), 3) if starts and ends else None,
    }


def transcribe_wav_with_vosk(filename: str | os.PathLike, model_path: str, sample_rate: int = 16000) -> dict:
    """Transcribe a mono 16-bit WAV using Vosk and return confidence metadata."""
    path = Path(filename)
    if not path.exists():
        return {"ok": False, "error": f"file not found: {path}", "text": ""}
    analysis = analyse_wav_file(path)
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel  # type: ignore
        try:
            SetLogLevel(-1)
        except Exception:
            pass
    except Exception as exc:
        return {"ok": False, "error": f"vosk import failed: {exc}", "text": "", "analysis": analysis}
    if not os.path.isdir(model_path):
        return {"ok": False, "error": f"Vosk model folder not found: {model_path}", "text": "", "analysis": analysis}
    try:
        model = Model(model_path)
        with wave.open(str(path), "rb") as wf:
            if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
                return {"ok": False, "error": "WAV must be mono 16-bit PCM", "text": "", "analysis": analysis}
            rate = wf.getframerate() or int(sample_rate)
            rec = KaldiRecognizer(model, rate)
            try:
                rec.SetWords(True)
            except Exception:
                pass
            results: list[dict[str, Any]] = []
            chunks = 0
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                chunks += 1
                if rec.AcceptWaveform(data):
                    results.append(json.loads(rec.Result() or "{}"))
            final = json.loads(rec.FinalResult() or "{}")
            summary = _vosk_result_summary(results, final)
            return {
                "ok": True,
                **summary,
                "sample_rate": rate,
                "filename": str(path),
                "analysis": analysis,
                "chunks_processed": chunks,
                "partial_results": results[-8:],
                "final_result": final,
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "text": "", "filename": str(path), "analysis": analysis}


class AlsaMicrophoneMonitor:
    """Continuously samples ALSA and exposes raw/filtered levels and spectra."""

    def __init__(self, device: str = "default", sample_rate: int = 16000, channels: int = 1,
                 noise_gate_dbfs: float = -45.0, software_gain_db: float = 0.0,
                 dsp_settings: Optional[dict[str, Any]] = None, fft_bins: int = 48) -> None:
        self.device = str(device or "default")
        self.sample_rate = int(max(8000, min(48000, sample_rate)))
        self.channels = int(max(1, min(2, channels)))
        self.noise_gate_dbfs = float(noise_gate_dbfs)
        self.software_gain_db = float(software_gain_db)
        self.dsp_settings = dict(dsp_settings or {})
        self.fft_bins = max(16, min(80, int(fft_bins or 48)))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._stats: dict[str, Any] = {
            "running": False, "device": self.device, "sample_rate": self.sample_rate,
            "channels": self.channels, "raw_rms_dbfs": -120.0, "raw_peak_dbfs": -120.0,
            "rms_dbfs": -120.0, "peak_dbfs": -120.0, "rms_pct": 0.0, "peak_pct": 0.0,
            "active": False, "clipped": False, "samples": 0, "updates": 0,
            "last_update": None, "error": "", "spectrum_raw": [], "spectrum_filtered": [],
        }

    def update_settings(self, device: str, sample_rate: int, channels: int = 1,
                        noise_gate_dbfs: float = -45.0, software_gain_db: float = 0.0,
                        dsp_settings: Optional[dict[str, Any]] = None, fft_bins: int = 48) -> None:
        was_running = self.is_running()
        if was_running:
            self.stop()
        self.device = str(device or "default")
        self.sample_rate = int(max(8000, min(48000, sample_rate)))
        self.channels = int(max(1, min(2, channels)))
        self.noise_gate_dbfs = float(noise_gate_dbfs)
        self.software_gain_db = float(software_gain_db)
        self.dsp_settings = dict(dsp_settings or {})
        self.fft_bins = max(16, min(80, int(fft_bins or 48)))
        with self._lock:
            self._stats.update({
                "device": self.device, "sample_rate": self.sample_rate, "channels": self.channels,
                "raw_rms_dbfs": -120.0, "raw_peak_dbfs": -120.0,
                "rms_dbfs": -120.0, "peak_dbfs": -120.0, "rms_pct": 0.0, "peak_pct": 0.0,
                "active": False, "clipped": False, "error": "", "spectrum_raw": [], "spectrum_filtered": [],
            })
        if was_running:
            self.start()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> dict:
        if self.is_running():
            return {"ok": True, "message": "microphone monitor already running", "level": self.snapshot()}
        if not shutil.which("arecord"):
            return {"ok": False, "error": "arecord not found"}
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="bx1-mic-monitor", daemon=True)
        self._thread.start()
        return {"ok": True, "message": "microphone monitor started", "level": self.snapshot()}

    def stop(self) -> dict:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate(); proc.wait(timeout=1.5)
            except Exception:
                try: proc.kill()
                except Exception: pass
        with self._lock:
            self._stats["running"] = False
        return {"ok": True, "message": "microphone monitor stopped", "level": self.snapshot()}

    def snapshot(self) -> dict:
        with self._lock:
            snap = dict(self._stats)
        snap["running"] = self.is_running()
        snap["noise_gate_dbfs"] = round(float(self.noise_gate_dbfs), 1)
        snap["software_gain_db"] = round(float(self.software_gain_db), 1)
        snap["dsp"] = dict(self.dsp_settings)
        return snap

    def _run(self) -> None:
        cmd = [shutil.which("arecord") or "arecord", "-D", self.device, "-q", "-f", "S16_LE",
               "-r", str(self.sample_rate), "-c", str(self.channels), "-t", "raw"]
        processor = StreamingAudioProcessor(self.sample_rate, self.dsp_settings)
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with self._lock:
                self._stats.update({"running": True, "error": "", "command": cmd})
            chunk_bytes = max(2048, int(self.sample_rate * self.channels * 2 * 0.10))
            update_no = 0
            while not self._stop.is_set():
                if self._proc.stdout is None:
                    break
                data = self._proc.stdout.read(chunk_bytes)
                if not data:
                    break
                clean, dsp_stats = processor.process_pcm16(data, channels=self.channels)
                level = _pcm16_level(clean, software_gain_db=0.0)
                active = bool(level["rms_dbfs"] >= float(self.noise_gate_dbfs))
                update_no += 1
                extra: dict[str, Any] = {}
                if update_no % 3 == 0:
                    raw_mono = _mono_floats_to_pcm16(_pcm16_to_mono_floats(data, channels=self.channels))
                    extra["spectrum_raw"] = compact_spectrum_from_pcm16(raw_mono, self.sample_rate, self.fft_bins)
                    extra["spectrum_filtered"] = compact_spectrum_from_pcm16(clean, self.sample_rate, self.fft_bins)
                with self._lock:
                    self._stats.update(level)
                    self._stats.update(dsp_stats)
                    self._stats.update(extra)
                    self._stats["active"] = active
                    self._stats["updates"] = int(self._stats.get("updates", 0) or 0) + 1
                    self._stats["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    self._stats["running"] = True
            err = ""
            try:
                if self._proc.stderr is not None:
                    err = (self._proc.stderr.read() or b"").decode("utf-8", errors="replace")[-1000:]
            except Exception:
                pass
            if err and not self._stop.is_set():
                with self._lock: self._stats["error"] = err.strip()
        except Exception as exc:
            with self._lock: self._stats["error"] = str(exc)
        finally:
            proc = self._proc
            if proc and proc.poll() is None:
                try: proc.terminate()
                except Exception: pass
            with self._lock: self._stats["running"] = False

def analyse_transcript_quality(text: str, duration_s: float = 0.0, cfg: Any = None) -> dict[str, Any]:
    """Reject obvious STT decoder collapse, prompt leakage and impossible text.

    The guard is deliberately backend-independent so the same rules can protect
    local Vosk and desktop faster-whisper results.  It never attempts to repair a
    corrupt command: the whole utterance is rejected and the listener resets.
    """
    def setting(name: str, default: Any) -> Any:
        if cfg is None:
            return default
        if isinstance(cfg, dict):
            return cfg.get(name, default)
        return getattr(cfg, name, default)

    clean = " ".join(str(text or "").split()).strip()
    tokens = re.findall(r"[a-z0-9']+", clean.lower())
    report: dict[str, Any] = {
        "ok": bool(tokens),
        "reason": "accepted" if tokens else "no recognised speech",
        "word_count": len(tokens),
        "unique_word_ratio": round(len(set(tokens)) / max(1, len(tokens)), 3),
        "max_consecutive_repeat": 1 if tokens else 0,
        "repeated_phrase_words": 0,
        "repeated_phrase_count": 0,
        "words_per_second": round(len(tokens) / max(0.001, float(duration_s or 0.0)), 2) if duration_s else None,
    }
    if not tokens:
        return report
    if not bool(setting("stt_repetition_guard_enabled", True)):
        return report

    low = " ".join(tokens)
    leaks = (
        "the speaker may begin with a wake phrase such as",
        "preserve the wake phrase in the transcript",
        "the speaker may begin with a wake phrase",
    )
    if bool(setting("stt_reject_prompt_leakage", True)) and any(leak in low for leak in leaks):
        report.update({"ok": False, "reason": "STT prompt leakage detected", "prompt_leakage": True})
        return report

    max_words = max(10, int(setting("stt_max_transcript_words", 90) or 90))
    if len(tokens) > max_words:
        report.update({"ok": False, "reason": f"transcript exceeds {max_words} words"})
        return report

    longest = 1
    run = 1
    for index in range(1, len(tokens)):
        if tokens[index] == tokens[index - 1]:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    report["max_consecutive_repeat"] = longest
    max_repeat = max(2, int(setting("stt_max_consecutive_word_repeats", 3) or 3))
    if longest > max_repeat:
        report.update({"ok": False, "reason": f"word repeated {longest} times consecutively"})
        return report

    allowed_phrase_repeats = max(1, int(setting("stt_max_repeated_phrase_count", 2) or 2))
    # Find adjacent repeated blocks, e.g. "we will do the work together" x 20.
    for width in range(2, min(12, len(tokens) // 2) + 1):
        index = 0
        while index + (2 * width) <= len(tokens):
            phrase = tokens[index:index + width]
            count = 1
            cursor = index + width
            while cursor + width <= len(tokens) and tokens[cursor:cursor + width] == phrase:
                count += 1
                cursor += width
            if count > report["repeated_phrase_count"]:
                report["repeated_phrase_words"] = width
                report["repeated_phrase_count"] = count
            if count > allowed_phrase_repeats:
                report.update({"ok": False, "reason": f"phrase repeated {count} times consecutively"})
                return report
            index = cursor if count > 1 else index + 1

    min_unique = max(0.05, min(0.95, float(setting("stt_min_unique_word_ratio", 0.30) or 0.30)))
    if len(tokens) >= 10 and report["unique_word_ratio"] < min_unique:
        report.update({"ok": False, "reason": "abnormally repetitive transcript"})
        return report

    if duration_s and float(duration_s) >= 0.5:
        max_wps = max(2.0, float(setting("stt_max_words_per_second", 7.0) or 7.0))
        if float(report["words_per_second"] or 0.0) > max_wps:
            report.update({"ok": False, "reason": "word rate is impossible for the captured audio"})
            return report
    return report


class VoskSpeechToText:
    """Offline Vosk STT with filtered capture and deterministic acceptance gates."""

    FILLERS = {"huh", "uh", "um", "umm", "mm", "mmm", "hmm", "hm", "ah", "oh", "er", "erm", "eh"}

    def __init__(self, cfg: AudioConfig) -> None:
        self.cfg = cfg
        self.ready = False
        self.vosk_ready = False
        self.error = ""
        self.last_result: dict[str, Any] = {"accepted": False, "text": "", "reason": "not run"}
        self.sd = None
        self.model = None
        self.KaldiRecognizer = None
        self._sounddevice_import_ok = False
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel  # type: ignore
            try: SetLogLevel(-1)
            except Exception: pass
            if not os.path.isdir(cfg.vosk_model_path):
                raise RuntimeError(f"Vosk model folder not found: {cfg.vosk_model_path}")
            self.model = Model(cfg.vosk_model_path)
            self.KaldiRecognizer = KaldiRecognizer
            self.vosk_ready = True
        except Exception as exc:
            # Desktop faster-whisper can remain the primary recogniser even when
            # the optional local Vosk fallback model is absent.  ALSA capture is
            # therefore considered ready independently of Vosk.
            self.error = str(exc)
        self.ready = bool(shutil.which("arecord")) or self.vosk_ready
        try:
            import sounddevice as sd  # type: ignore
            self.sd = sd
            self._sounddevice_import_ok = True
        except Exception:
            self.sd = None

    def _recognise_wav(self, filename: str) -> dict[str, Any]:
        if self.KaldiRecognizer is None or self.model is None:
            return {"ok": False, "text": "", "error": "Vosk model is not ready"}
        results: list[dict[str, Any]] = []
        with wave.open(filename, "rb") as wf:
            if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
                return {"ok": False, "text": "", "error": "WAV must be mono 16-bit PCM"}
            rate = int(wf.getframerate() or self.cfg.sample_rate)
            rec = self.KaldiRecognizer(self.model, rate)
            try: rec.SetWords(True)
            except Exception: pass
            while True:
                data = wf.readframes(4000)
                if not data: break
                if rec.AcceptWaveform(data):
                    results.append(json.loads(rec.Result() or "{}"))
            final = json.loads(rec.FinalResult() or "{}")
        return {"ok": True, **_vosk_result_summary(results, final), "results": results[-8:], "final_result": final, "sample_rate": rate}

    def recognise_wav_bytes(self, wav_bytes: bytes, voice: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Run the already-loaded Vosk model only when primary STT needs fallback."""
        if not wav_bytes:
            return {"accepted": False, "text": "", "reason": "no WAV bytes for local fallback", "error": "no WAV bytes"}
        handle = tempfile.NamedTemporaryFile(prefix="bx1_vosk_fallback_", suffix=".wav", delete=False)
        filename = handle.name
        try:
            handle.write(wav_bytes)
            handle.close()
            started = time.monotonic()
            recognition = self._recognise_wav(filename)
            decision = self._validate(recognition, dict(voice or {}))
            return {
                **decision,
                "confidence": recognition.get("average_confidence"),
                "minimum_confidence": recognition.get("minimum_confidence"),
                "words": recognition.get("words", []),
                "local_recognition_ms": round((time.monotonic() - started) * 1000.0, 1),
                "error": str(recognition.get("error") or ""),
            }
        except Exception as exc:
            return {"accepted": False, "text": "", "reason": "local Vosk fallback failed", "error": str(exc)}
        finally:
            try:
                handle.close()
            except Exception:
                pass
            try:
                os.unlink(filename)
            except OSError:
                pass

    def _validate(self, result: dict[str, Any], voice: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(str(result.get("text") or "").lower().split()).strip()
        tokens = re.findall(r"[a-z0-9']+", text)
        reason = "accepted"
        accepted = bool(text)
        if not text:
            accepted, reason = False, "no recognised speech"
        elif bool(getattr(self.cfg, "stt_reject_fillers", True)) and tokens and all(t in self.FILLERS for t in tokens):
            accepted, reason = False, "filler/noise fragment"
        elif bool(getattr(self.cfg, "stt_validation_enabled", True)):
            # Energy VAD can under-count a sentence that occupies nearly the whole
            # capture window because there is little silence from which to estimate
            # a noise floor. Vosk word timings are a second, independent indication
            # of voiced duration and are safe to use only after words were decoded.
            recognised_ms = int(round(float(result.get("recognised_duration_s") or 0.0) * 1000.0))
            energy_voiced_ms = int(voice.get("voiced_ms", 0) or 0)
            energy_longest_ms = int(voice.get("longest_voiced_ms", 0) or 0)
            effective_voiced_ms = max(energy_voiced_ms, recognised_ms)
            effective_longest_ms = max(energy_longest_ms, recognised_ms if len(tokens) > 1 else 0)
            voice["recognised_voiced_ms"] = recognised_ms
            voice["effective_voiced_ms"] = effective_voiced_ms
            voice["effective_longest_voiced_ms"] = effective_longest_ms
            if len(text.replace(" ", "")) < int(getattr(self.cfg, "stt_min_chars", 2) or 2):
                accepted, reason = False, "transcript too short"
            elif len(tokens) < int(getattr(self.cfg, "stt_min_words", 1) or 1):
                accepted, reason = False, "too few words"
            elif effective_voiced_ms < int(getattr(self.cfg, "stt_min_voiced_ms", 280) or 280):
                accepted, reason = False, "insufficient voiced audio"
            elif effective_longest_ms < int(getattr(self.cfg, "stt_min_longest_voiced_ms", 160) or 160):
                accepted, reason = False, "speech was too fragmented"
            else:
                confidence = result.get("average_confidence")
                if confidence is not None and float(confidence) < float(getattr(self.cfg, "stt_min_confidence", 0.40) or 0.40):
                    accepted, reason = False, "low Vosk confidence"
        quality = analyse_transcript_quality(
            text,
            duration_s=float(result.get("recognised_duration_s") or 0.0),
            cfg=self.cfg,
        )
        if accepted and not bool(quality.get("ok", True)):
            accepted, reason = False, str(quality.get("reason") or "corrupt transcript")
        return {"accepted": accepted, "reason": reason, "text": text, "tokens": tokens, "transcript_quality": quality}

    def _listen_once_alsa_detailed(
        self, timeout_s: float, *, defer_local_recognition: bool = False,
        cancel_event: Optional[threading.Event] = None, level_observer: Optional[Callable[[dict[str, Any]], None]] = None,
        frame_guard: Optional[Callable[[bytes], bool]] = None,
    ) -> dict[str, Any]:
        if not shutil.which("arecord"):
            return {"accepted": False, "text": "", "reason": "arecord not found", "error": "arecord not found", "capture_method": "alsa"}
        keep_debug = bool(getattr(self.cfg, "stt_debug_keep_audio", True))
        temp_root = Path(tempfile.gettempdir())
        capture_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        if keep_debug:
            raw_name = str(temp_root / f"bx1_stt_{capture_id}_raw.wav")
            clean_name = str(temp_root / f"bx1_stt_{capture_id}_filtered.wav")
            submitted_name = str(temp_root / f"bx1_stt_{capture_id}_submitted.wav")
            _cleanup_stt_debug_files(temp_root)
        else:
            raw_tmp = tempfile.NamedTemporaryFile(prefix="bx1_stt_raw_", suffix=".wav", delete=False); raw_tmp.close(); raw_name = raw_tmp.name
            clean_tmp = tempfile.NamedTemporaryFile(prefix="bx1_stt_clean_", suffix=".wav", delete=False); clean_tmp.close(); clean_name = clean_tmp.name
            submit_tmp = tempfile.NamedTemporaryFile(prefix="bx1_stt_submit_", suffix=".wav", delete=False); submit_tmp.close(); submitted_name = submit_tmp.name
        capture: dict[str, Any] = {}
        try:
            endpointing = bool(getattr(self.cfg, "stt_endpointing_enabled", True))
            if endpointing:
                capture = record_microphone_utterance(
                    raw_name,
                    device=str(self.cfg.mic_device or "default"),
                    sample_rate=int(self.cfg.sample_rate),
                    channels=int(self.cfg.mic_channels or 1),
                    start_timeout_s=float(getattr(self.cfg, "stt_start_timeout_s", timeout_s) or timeout_s),
                    max_utterance_s=float(getattr(self.cfg, "stt_max_utterance_s", 20.0) or 20.0),
                    pre_roll_ms=int(getattr(self.cfg, "stt_pre_roll_ms", 700) or 700),
                    end_silence_ms=int(getattr(self.cfg, "stt_end_silence_ms", 1350) or 1350),
                    post_roll_ms=int(getattr(self.cfg, "stt_post_roll_ms", 300) or 300),
                    start_trigger_ms=int(getattr(self.cfg, "stt_start_trigger_ms", 80) or 80),
                    speech_resume_trigger_ms=int(getattr(self.cfg, "stt_speech_resume_trigger_ms", 140) or 140),
                    transient_guard_after_ms=int(getattr(self.cfg, "stt_transient_guard_after_ms", 220) or 220),
                    endpoint_hysteresis_db=float(getattr(self.cfg, "stt_endpoint_hysteresis_db", 3.0) or 3.0),
                    fixed_gate_dbfs=float(getattr(self.cfg, "mic_noise_gate_dbfs", -48.0)),
                    adaptive_threshold_enabled=bool(getattr(self.cfg, "stt_adaptive_threshold_enabled", True)),
                    adaptive_margin_db=float(getattr(self.cfg, "stt_adaptive_margin_db", 8.0)),
                    software_gain_db=float(getattr(self.cfg, "mic_software_gain_db", 0.0)),
                    cancel_event=cancel_event,
                    level_observer=level_observer,
                    frame_guard=frame_guard,
                )
            else:
                capture = record_microphone_sample(
                    raw_name,
                    device=str(self.cfg.mic_device or "default"),
                    sample_rate=int(self.cfg.sample_rate),
                    seconds=float(timeout_s),
                    channels=int(self.cfg.mic_channels or 1),
                )
                capture["close_reason"] = "fixed capture window"
                capture["speech_started"] = bool(capture.get("ok"))
            if capture.get("cancelled"):
                return {
                    "accepted": False, "cancelled": True, "text": "",
                    "reason": str(capture.get("reason") or "capture cancelled"),
                    "error": "", "capture": capture, "capture_method": "alsa_endpointed",
                    "capture_id": capture_id,
                    "debug_audio": {"raw": "", "filtered": "", "submitted": ""},
                }
            if not capture.get("ok"):
                err = str(capture.get("error") or capture.get("stderr") or "arecord failed")
                return {"accepted": False, "text": "", "reason": "capture failed", "error": err, "capture": capture, "capture_method": "alsa"}
            if endpointing and not capture.get("speech_started", False):
                return {
                    "accepted": False,
                    "text": "",
                    "reason": str(capture.get("reason") or "no speech detected"),
                    "error": "",
                    "capture": capture,
                    "capture_method": "alsa_endpointed",
                    "capture_id": capture_id,
                    "debug_audio": {"raw": raw_name if Path(raw_name).exists() else "", "filtered": "", "submitted": ""},
                }
            dsp = build_audio_dsp_settings(self.cfg)
            processed = process_wav_for_speech(raw_name, clean_name, dsp)
            if not processed.get("ok"):
                return {"accepted": False, "text": "", "reason": "audio filtering failed", "error": processed.get("error", "filter failed"), "capture": capture, "capture_method": "alsa"}
            try:
                shutil.copyfile(clean_name, submitted_name)
            except Exception:
                submitted_name = clean_name
            with wave.open(clean_name, "rb") as wf:
                clean_pcm = wf.readframes(wf.getnframes()); rate = wf.getframerate()
            voice = analyse_pcm_voice_activity(
                clean_pcm,
                rate,
                noise_gate_dbfs=float(getattr(self.cfg, "mic_noise_gate_dbfs", -48.0)),
                noise_margin_db=float(getattr(self.cfg, "stt_noise_margin_db", 6.0)),
            )
            recognition_started = time.monotonic()
            if defer_local_recognition:
                recognition = {"ok": True, "text": "", "deferred": True}
                decision = {
                    "accepted": False,
                    "reason": "local recognition deferred to primary Brain STT",
                    "text": "",
                    "tokens": [],
                    "transcript_quality": {},
                }
            else:
                recognition = self._recognise_wav(submitted_name)
                decision = self._validate(recognition, voice)
            local_recognition_ms = round((time.monotonic() - recognition_started) * 1000.0, 1)
            try:
                submitted_wav_bytes = Path(submitted_name).read_bytes()
            except Exception:
                submitted_wav_bytes = b""
            if keep_debug:
                # Legacy fixed filenames remain available to existing tools, but
                # the web UI uses capture_id-specific URLs so a rejected/new test
                # can never replay an older utterance by accident.
                try:
                    _atomic_copy_file(raw_name, temp_root / "bx1_stt_last_raw.wav")
                    _atomic_copy_file(clean_name, temp_root / "bx1_stt_last_filtered.wav")
                    _atomic_copy_file(submitted_name, temp_root / "bx1_stt_last_submitted.wav")
                except Exception:
                    pass
            return {
                **decision,
                "_submitted_wav_bytes": submitted_wav_bytes,
                "capture_id": capture_id,
                "local_recognition_deferred": bool(defer_local_recognition),
                "local_recognition_ms": local_recognition_ms,
                "capture_method": "alsa_endpointed" if endpointing else "alsa_fixed",
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "confidence": recognition.get("average_confidence"),
                "minimum_confidence": recognition.get("minimum_confidence"),
                "words": recognition.get("words", []),
                "voice_activity": voice,
                "capture": capture,
                "audio": processed,
                "raw_spectrum": [],
                "filtered_spectrum": compact_spectrum_from_pcm16(clean_pcm, rate, int(getattr(self.cfg, "audio_live_fft_bins", 48))),
                "debug_audio": {"raw": raw_name, "filtered": clean_name, "submitted": submitted_name},
                "error": str(recognition.get("error") or ""),
            }
        except Exception as exc:
            return {"accepted": False, "text": "", "reason": "STT exception", "error": str(exc), "capture": capture, "capture_method": "alsa"}
        finally:
            if not keep_debug:
                for name in (raw_name, clean_name, submitted_name):
                    if name:
                        try:
                            os.unlink(name)
                        except OSError:
                            pass

    def _listen_once_sounddevice_detailed(
        self, timeout_s: float, *, defer_local_recognition: bool = False,
        cancel_event: Optional[threading.Event] = None,
        frame_guard: Optional[Callable[[bytes], bool]] = None,
    ) -> dict[str, Any]:
        if not self._sounddevice_import_ok or self.sd is None or self.KaldiRecognizer is None or self.model is None:
            return {"accepted": False, "text": "", "reason": "sounddevice unavailable", "error": "sounddevice is not available"}
        q: "queue.Queue[bytes]" = queue.Queue()
        collected = bytearray()
        def callback(indata, frames, time_info, status):  # type: ignore[no-untyped-def]
            if status: print(f"[audio] input status: {status}")
            data = bytes(indata)
            try:
                if frame_guard is not None and frame_guard(data):
                    return
            except Exception:
                pass
            collected.extend(data); q.put(data)
        started = time.monotonic()
        try:
            kwargs: dict[str, Any] = {"samplerate": self.cfg.sample_rate, "blocksize": 4000, "dtype": "int16", "channels": 1, "callback": callback}
            dev = str(self.cfg.mic_device or "").strip()
            if dev.isdigit(): kwargs["device"] = int(dev)
            with self.sd.RawInputStream(**kwargs):
                while time.monotonic() - started < timeout_s:
                    if cancel_event is not None and cancel_event.is_set():
                        return {
                            "accepted": False, "cancelled": True, "text": "",
                            "reason": "capture cancelled for microphone handover",
                            "error": "", "capture_method": "sounddevice",
                        }
                    try: q.get(timeout=0.10)
                    except queue.Empty: pass
            processor = StreamingAudioProcessor(self.cfg.sample_rate, build_audio_dsp_settings(self.cfg))
            clean, audio_stats = processor.process_pcm16(bytes(collected), channels=1)
            voice = analyse_pcm_voice_activity(clean, self.cfg.sample_rate,
                noise_gate_dbfs=float(self.cfg.mic_noise_gate_dbfs), noise_margin_db=float(self.cfg.stt_noise_margin_db))
            wav_tmp = tempfile.NamedTemporaryFile(prefix="bx1_sd_submit_", suffix=".wav", delete=False); wav_tmp.close()
            try:
                _write_pcm16_wav(wav_tmp.name, clean, self.cfg.sample_rate, 1)
                wav_bytes = Path(wav_tmp.name).read_bytes()
            finally:
                try: os.unlink(wav_tmp.name)
                except OSError: pass
            if defer_local_recognition:
                recognition = {"ok": True, "text": "", "deferred": True}
                decision = {"accepted": False, "reason": "local recognition deferred to primary Brain STT", "text": "", "tokens": [], "transcript_quality": {}}
            else:
                rec = self.KaldiRecognizer(self.model, self.cfg.sample_rate)
                try: rec.SetWords(True)
                except Exception: pass
                results: list[dict[str, Any]] = []
                for pos in range(0, len(clean), 8000):
                    if rec.AcceptWaveform(clean[pos:pos+8000]): results.append(json.loads(rec.Result() or "{}"))
                final = json.loads(rec.FinalResult() or "{}")
                recognition = {"ok": True, **_vosk_result_summary(results, final)}
                decision = self._validate(recognition, voice)
            return {**decision, "_submitted_wav_bytes": wav_bytes, "local_recognition_deferred": bool(defer_local_recognition),
                    "capture_method": "sounddevice", "confidence": recognition.get("average_confidence"),
                    "words": recognition.get("words", []), "voice_activity": voice, "audio": audio_stats,
                    "filtered_spectrum": compact_spectrum_from_pcm16(clean, self.cfg.sample_rate, int(self.cfg.audio_live_fft_bins)), "error": ""}
        except Exception as exc:
            return {"accepted": False, "text": "", "reason": "sounddevice failed", "error": str(exc)}

    def listen_once_detailed(
        self, timeout_s: Optional[float] = None, *, defer_local_recognition: bool = False,
        cancel_event: Optional[threading.Event] = None, level_observer: Optional[Callable[[dict[str, Any]], None]] = None,
        frame_guard: Optional[Callable[[bytes], bool]] = None,
    ) -> dict[str, Any]:
        if not self.ready:
            self.last_result = {"accepted": False, "text": "", "reason": "STT not ready", "error": self.error}
            return dict(self.last_result)
        timeout = float(timeout_s or self.cfg.record_seconds)
        method = str(getattr(self.cfg, "stt_capture_method", "alsa") or "alsa").lower().strip()
        attempts: list[dict[str, Any]] = []

        if method in {"auto", "alsa", "arecord"}:
            result = self._listen_once_alsa_detailed(
                timeout, defer_local_recognition=defer_local_recognition, cancel_event=cancel_event, level_observer=level_observer
                , frame_guard=frame_guard
            )
            attempts.append(result)
            # ALSA is the selected and preferred UNO Q path. A normal rejection
            # (silence, low confidence, short speech) must be returned as-is rather
            # than being overwritten by the irrelevant sounddevice fallback.
            if method in {"alsa", "arecord"} or result.get("accepted") or not result.get("error"):
                result["attempts"] = [{"method": x.get("capture_method"), "reason": x.get("reason"), "error": x.get("error")} for x in attempts]
                self.last_result = result
                self.error = str(result.get("error") or "")
                return dict(result)
            # In auto mode only try sounddevice when it is genuinely installed.
            if not self._sounddevice_import_ok:
                result["fallback_skipped"] = "sounddevice is not installed; ALSA error retained"
                result["attempts"] = [{"method": x.get("capture_method"), "reason": x.get("reason"), "error": x.get("error")} for x in attempts]
                self.last_result = result
                self.error = str(result.get("error") or "")
                return dict(result)

        result = self._listen_once_sounddevice_detailed(
            timeout, defer_local_recognition=defer_local_recognition, cancel_event=cancel_event,
            frame_guard=frame_guard,
        )
        attempts.append(result)
        self.last_result = result
        self.error = str(result.get("error") or "")
        result["attempts"] = [{"method": x.get("capture_method"), "reason": x.get("reason"), "error": x.get("error")} for x in attempts]
        return dict(result)

    def listen_once(self, timeout_s: Optional[float] = None) -> str:
        result = self.listen_once_detailed(timeout_s)
        return str(result.get("text") or "") if result.get("accepted") else ""

# ---------------------------------------------------------------------------
# BX1 V6.2: explicit TTS diagnostics and blocking web test helpers.
# These are attached to TextToSpeech without disturbing the existing runtime API.
# ---------------------------------------------------------------------------

def _bx1_tts_player_path() -> Optional[str]:
    return shutil.which("mpg123") or shutil.which("mpv") or shutil.which("ffplay")


def _bx1_edge_import_check(python_exe: Optional[str]) -> dict:
    if not python_exe:
        return {"ok": False, "error": "python3/python command not found"}
    try:
        res = subprocess.run(
            [python_exe, "-c", "import edge_tts; print(getattr(edge_tts, '__version__', 'installed'))"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        return {
            "ok": res.returncode == 0,
            "returncode": res.returncode,
            "stdout": (res.stdout or "").strip(),
            "stderr": (res.stderr or "").strip()[:500],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _bx1_internet_check() -> dict:
    try:
        req = urllib.request.Request("https://www.bing.com", headers={"User-Agent": "BX1-TTS-Check"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return {"ok": True, "status": getattr(resp, "status", None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}


def _bx1_normalised_volume(volume: int | float | str) -> int:
    try:
        value = int(float(volume))
    except Exception:
        value = 80
    return max(0, min(100, value))


def _bx1_player_command(player: str, filename: str, volume: int | float | str = 80, wav: bool = False, playback_device: str = "default") -> list[str]:
    """Build a playback command with per-file volume control.

    Edge TTS and ElevenLabs generate MP3 files. Changing the system mixer is not
    reliable on every UNO Q/Debian audio image, so for natural voices we also
    control the playback command itself.
    """
    vol = _bx1_normalised_volume(volume)
    name = os.path.basename(player or "").lower()

    if name.startswith("mpg123"):
        # mpg123 uses a 16-bit scale factor. 32768 is about normal output.
        # Use a slightly non-linear curve so low values are quieter and useful.
        if vol <= 0:
            factor = 1
        else:
            factor = max(1, min(65536, int(round(32768 * (vol / 100.0) ** 1.35))))
        cmd = [player, "-q"]
        dev = str(playback_device or "default").strip()
        if dev and dev.lower() != "default":
            cmd.extend(["-o", "alsa", "-a", dev])
        cmd.extend(["-f", str(factor), filename])
        return cmd

    if name.startswith("mpv"):
        return [player, "--really-quiet", f"--volume={vol}", filename]

    if name.startswith("ffplay"):
        return [player, "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", str(vol), filename]

    if name.startswith("aplay"):
        # aplay itself has no simple volume option. apply_volume() still tries ALSA first.
        dev = str(playback_device or "default").strip()
        if dev and dev.lower() != "default":
            return [player, "-D", dev, filename]
        return [player, filename]

    if name.startswith("paplay"):
        return [player, f"--volume={int(65536 * vol / 100)}", filename]

    return [player, filename]


def _bx1_audio_duration_s(filename: str) -> Optional[float]:
    """Return the media duration when it can be measured without playback."""
    try:
        suffix = Path(filename).suffix.lower()
        if suffix == ".wav":
            with wave.open(filename, "rb") as wf:
                return round(wf.getnframes() / float(wf.getframerate() or 1), 3)
        probe = shutil.which("ffprobe")
        if probe:
            result = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filename],
                capture_output=True, text=True, timeout=3, check=False,
            )
            value = float((result.stdout or "").strip())
            return round(value, 3) if value > 0 else None
    except (OSError, ValueError, TypeError, wave.Error, subprocess.SubprocessError):
        pass
    return None


def _bx1_play_file(player: str, filename: str, volume: int | float | str = 80, wav: bool = False, playback_device: str = "default") -> dict:
    cmd = _bx1_player_command(player, filename, volume, wav=wav, playback_device=playback_device)
    signal: dict[str, Any] = {"output_rms_dbfs": None, "output_peak_dbfs": None, "output_non_silent": False, "output_active": False, "output_source": filename, "output_device": playback_device, "output_started_at": "", "output_finished_at": "", "generated_audio_duration_s": _bx1_audio_duration_s(filename), "playback_elapsed_s": None, "playback_termination_state": "not_started"}
    if wav:
        try:
            with wave.open(filename, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            samples = array("h"); samples.frombytes(raw)
            if sys.byteorder != "little": samples.byteswap()
            if samples:
                peak = max(abs(int(s)) for s in samples) / 32768.0
                rms = math.sqrt(sum(float(s) * float(s) for s in samples) / len(samples)) / 32768.0
                signal.update({"output_rms_dbfs": round(20 * math.log10(max(rms, 1e-9)), 2), "output_peak_dbfs": round(20 * math.log10(max(peak, 1e-9)), 2), "output_non_silent": peak > 0.003, "output_active": peak > 0.003})
        except Exception as exc:
            signal["output_error"] = str(exc)
    signal["output_started_at"] = _bx1_now_iso()
    started = time.perf_counter()
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60, check=False)
        signal["output_finished_at"] = _bx1_now_iso()
        signal["playback_elapsed_s"] = round(time.perf_counter() - started, 3)
        signal["playback_termination_state"] = "completed" if res.returncode == 0 else "returned_nonzero"
        return {
            "ok": res.returncode == 0,
            "command": cmd,
            "returncode": res.returncode,
            "stdout": (res.stdout or "").strip()[:500],
            "stderr": (res.stderr or "").strip()[:500],
            **signal,
        }
    except subprocess.TimeoutExpired as exc:
        signal["output_finished_at"] = _bx1_now_iso()
        signal["playback_elapsed_s"] = round(time.perf_counter() - started, 3)
        signal["playback_termination_state"] = "timeout"
        return {"ok": False, "command": cmd, "error": str(exc), "returncode": None, **signal}
    except Exception as exc:
        signal["output_finished_at"] = _bx1_now_iso()
        signal["playback_elapsed_s"] = round(time.perf_counter() - started, 3)
        signal["playback_termination_state"] = "exception"
        return {"ok": False, "command": cmd, "error": str(exc), **signal}


def _bx1_tts_diagnostics(self: TextToSpeech) -> dict:
    python_exe = shutil.which("python3") or shutil.which("python")
    player = _bx1_tts_player_path()
    diag = {
        "backend_selected": (self.cfg.tts_backend or "espeak-ng"),
        "tts_enabled": bool(self.cfg.tts_enabled),
        "volume_percent": int(max(0, min(100, int(self.cfg.tts_volume)))),
        "tts_playback_device": str(getattr(self.cfg, "tts_playback_device", "default") or "default"),
        "playback_volume_mode": "queued chunk playback + player command + ALSA/Pulse fallback",
        "chunking_enabled": bool(getattr(self.cfg, "tts_chunking_enabled", True)),
        "chunk_max_chars": int(getattr(self.cfg, "tts_chunk_max_chars", 650) or 650),
        "robotic_fallback_enabled": bool(getattr(self.cfg, "tts_fallback_to_espeak", False)),
        "python": python_exe or "missing",
        "espeak_ng": shutil.which("espeak-ng") or shutil.which("espeak") or "missing",
        "mp3_player": player or "missing",
        "aplay": shutil.which("aplay") or "missing",
        "amixer": shutil.which("amixer") or "missing",
        "piper": shutil.which("piper") or "missing",
        "edge_voice": self.cfg.tts_edge_voice,
        "brain_tts_base_url": str(getattr(self.cfg, "brain_tts_base_url", "") or ""),
        "brain_tts_engine": str(getattr(self.cfg, "brain_tts_engine", "dottts") or "dottts"),
        "brain_tts_voice": str(getattr(self.cfg, "brain_tts_voice", "active_profile") or "active_profile"),
        "brain_tts_endpoint": str(getattr(self.cfg, "brain_tts_endpoint", "/api/tts") or "/api/tts"),
        "brain_tts_status_endpoint": str(getattr(self.cfg, "brain_tts_status_endpoint", "/api/tts/status") or "/api/tts/status"),
        "edge_tts_python_module": _bx1_edge_import_check(python_exe),
        "internet": _bx1_internet_check(),
    }
    problems = []
    backend = (self.cfg.tts_backend or "espeak-ng").strip().lower()
    if backend in {"edge", "edge-tts", "edge_tts"}:
        if not diag["edge_tts_python_module"].get("ok"):
            problems.append("edge-tts Python package is not installed or cannot import.")
        if player is None:
            problems.append("No MP3 player found. Install mpg123.")
        if not diag["internet"].get("ok"):
            problems.append("BX1/UNO Q does not appear to have internet access, which Edge TTS needs.")
    if backend in {"elevenlabs", "eleven-labs", "11labs"}:
        if not (self.cfg.tts_elevenlabs_api_key or "").strip():
            problems.append("ElevenLabs API key is not set.")
        if not (self.cfg.tts_elevenlabs_voice_id or "").strip():
            problems.append("ElevenLabs voice ID is not set.")
        if player is None:
            problems.append("No MP3 player found. Install mpg123.")
        if not diag["internet"].get("ok"):
            problems.append("BX1/UNO Q does not appear to have internet access, which ElevenLabs needs.")
    if backend in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}:
        if not str(getattr(self.cfg, "brain_tts_base_url", "") or "").strip():
            problems.append("Brain voice URL is not set. Use http://YOUR_PC_IP:8765")
        if not (shutil.which("aplay") or shutil.which("mpg123") or shutil.which("ffplay") or shutil.which("mpv")):
            problems.append("No local audio player found on UNO Q. Install alsa-utils and mpg123.")
    diag["problems"] = problems
    diag["ok_for_selected_backend"] = len(problems) == 0
    return diag


def _bx1_test_speech_blocking(self: TextToSpeech, text: str, on_audio_ready: Optional[Callable[[dict[str, Any]], None]] = None) -> dict:
    """Blocking diagnostic speech with the same mouth events as normal replies.

    Older diagnostics played the generated file directly and bypassed the TTS
    mouth callback. That proved the speaker worked but left the mouth at a fixed
    speaking colour. This path now emits preparation, playback-start and
    playback-stop events, including a real WAV level profile for Brain voice.
    """
    text = (text or "Speech test. BX1 voice system online. Gravity remains suspicious.").strip()
    if not text:
        text = "Speech test."
    self.apply_volume(force=True)
    backend = (self.cfg.tts_backend or "espeak-ng").strip().lower()
    if backend in {"edge", "edge_tts"}:
        backend = "edge-tts"
    if backend in {"espeak", "espeakng"}:
        backend = "espeak-ng"
    report = {
        "ok": False,
        "backend_requested": backend,
        "voice": None,
        "text_chars": len(text),
        "volume_percent": int(max(0, min(100, int(self.cfg.tts_volume)))),
        "fallback_used": False,
        "message": "",
        "diagnostics": _bx1_tts_diagnostics(self),
    }
    if not self.cfg.tts_enabled:
        report["message"] = "TTS is disabled. Tick 'Enable spoken replies on BX1'."
        return report

    event_info = {"text": text, "tag": "diagnostic", "backend": backend}
    event_closed = False
    self._emit_mouth_event("speech_prepare", dict(event_info))

    def close_event() -> None:
        nonlocal event_closed
        if not event_closed:
            event_closed = True
            self._emit_mouth_event("speech_stop", dict(event_info))

    try:
        if backend == "edge-tts":
            python_exe = shutil.which("python3") or shutil.which("python")
            player = _bx1_tts_player_path()
            report["voice"] = self.cfg.tts_edge_voice
            if not python_exe:
                report["message"] = "python3/python not found on UNO Q."
                return report
            edge_check = _bx1_edge_import_check(python_exe)
            if not edge_check.get("ok"):
                report["message"] = "edge-tts is not installed or cannot import. Run ./INSTALL_EDGE_TTS.sh from PuTTY."
                report["edge_import"] = edge_check
                return report
            if not player:
                report["message"] = "No MP3 player found. Run: sudo apt install -y mpg123"
                return report
            tmp_name = ""
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_name = tmp.name
                cmd = [python_exe, "-m", "edge_tts", "--voice", self.cfg.tts_edge_voice, "--text", text, "--write-media", tmp_name]
                gen = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60, check=False)
                report["edge_generate"] = {
                    "command": cmd,
                    "returncode": gen.returncode,
                    "stdout": (gen.stdout or "").strip()[:500],
                    "stderr": (gen.stderr or "").strip()[:1000],
                }
                size = os.path.getsize(tmp_name) if os.path.exists(tmp_name) else 0
                report["media_bytes"] = size
                if gen.returncode != 0 or size < 1000:
                    report["message"] = "Edge TTS did not generate a valid MP3. Check internet access and the selected Edge voice."
                    return report
                self._emit_mouth_event("speech_start", dict(event_info, filename=tmp_name, wav=False, audio_profile={}))
                if on_audio_ready is not None:
                    on_audio_ready({"generated_audio_duration_s": _bx1_audio_duration_s(tmp_name), "filename": tmp_name, "wav": False, "player": player})
                play = _bx1_play_file(player, tmp_name, self.cfg.tts_volume, wav=False, playback_device=self.cfg.tts_playback_device)
                self.last_playback_report = dict(play)
                report["playback"] = play
                report["speaker"] = self.speaker_controller.snapshot()
                report["generated_audio_duration_s"] = play.get("generated_audio_duration_s")
                report["ok"] = bool(play.get("ok"))
                report["message"] = "Edge TTS natural voice generated and played." if report["ok"] else "Edge TTS generated MP3, but playback failed."
                return report
            finally:
                close_event()
                if tmp_name:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass

        if backend in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}:
            report["voice"] = getattr(self.cfg, "brain_tts_voice", "active_profile")
            tts_report = self._request_brain_tts_audio(text)
            report["brain_tts"] = tts_report
            report["effective_engine"] = tts_report.get("effective_engine") or tts_report.get("backend")
            report["effective_voice"] = tts_report.get("effective_voice") or report["voice"]
            report["fallback_reason"] = tts_report.get("fallback_reason", "")
            report["audio_format"] = tts_report.get("audio_format")
            report["audio_duration_sec"] = tts_report.get("audio_duration_sec")
            report["generated_audio_duration_s"] = tts_report.get("audio_duration_sec")
            if not tts_report.get("ok"):
                report["message"] = "Brain voice service did not generate audio: " + str(tts_report.get("error") or tts_report)
                return report
            filename = str(tts_report.get("filename") or "")
            try:
                suffix = Path(filename).suffix.lower()
                wav = suffix == ".wav"
                player = (shutil.which("aplay") or shutil.which("paplay") or shutil.which("ffplay")) if wav else (shutil.which("mpg123") or shutil.which("mpv") or shutil.which("ffplay"))
                if not player:
                    report["message"] = "Brain voice generated audio, but no local player was found."
                    return report
                profile = _bx1_build_wav_mouth_profile(filename) if wav else {"ok": False, "levels": [], "frame_s": 0.055, "duration_s": 0.0, "source": filename}
                event_name = "speech_audio_file_start" if wav else "speech_start"
                self._emit_mouth_event(event_name, dict(event_info, filename=filename, wav=wav, audio_profile=profile))
                if on_audio_ready is not None:
                    on_audio_ready({"generated_audio_duration_s": profile.get("duration_s") or _bx1_audio_duration_s(filename), "filename": filename, "wav": wav, "player": player})
                play = _bx1_play_file(player, filename, self.cfg.tts_volume, wav=wav, playback_device=self.cfg.tts_playback_device)
                self.last_playback_report = dict(play)
                report["playback"] = play
                report["speaker"] = self.speaker_controller.snapshot()
                report["generated_audio_duration_s"] = play.get("generated_audio_duration_s") or report.get("generated_audio_duration_s")
                report["mouth_profile"] = {
                    "ok": bool(profile.get("ok")),
                    "frames": len(profile.get("levels", [])) if isinstance(profile.get("levels"), list) else 0,
                    "frame_s": profile.get("frame_s"),
                    "duration_s": profile.get("duration_s"),
                }
                report["ok"] = bool(play.get("ok"))
                report["message"] = "Brain App Dot.TTS audio generated on PC and played on BX1 with mouth envelope." if report["ok"] else "Brain voice generated audio, but playback failed."
                return report
            finally:
                if not event_closed:
                    event_closed = True
                    self._emit_mouth_event("speech_audio_file_stop", dict(event_info, filename=filename, wav=filename.lower().endswith('.wav')))
                if filename:
                    try:
                        os.unlink(filename)
                    except OSError:
                        pass

        if backend == "espeak-ng":
            exe = shutil.which("espeak-ng") or shutil.which("espeak")
            report["voice"] = self.cfg.tts_voice
            if not exe:
                report["message"] = "espeak-ng/espeak not installed."
                return report
            voice = (self.cfg.tts_voice or "en-gb").strip()
            rate = max(80, min(260, int(self.cfg.tts_rate)))
            pitch = max(0, min(99, int(self.cfg.tts_pitch)))
            amp = max(0, min(200, int(round(int(self.cfg.tts_volume) * 2))))
            args = [exe, f"-v{voice}", "-s", str(rate), "-p", str(pitch), "-a", str(amp), text]
            self._emit_mouth_event("speech_start", dict(event_info))
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
            report["playback"] = {"command": args, "returncode": res.returncode, "stderr": (res.stderr or "").strip()[:500]}
            report["ok"] = res.returncode == 0
            report["message"] = "espeak-ng played with reactive mouth animation. This is the robotic fallback voice." if report["ok"] else "espeak-ng playback failed."
            return report

        if backend == "elevenlabs":
            if not (self.cfg.tts_elevenlabs_api_key or "").strip():
                report["message"] = "ElevenLabs API key is missing."
                return report
            if not (self.cfg.tts_elevenlabs_voice_id or "").strip():
                report["message"] = "ElevenLabs voice ID is missing."
                return report
            self._emit_mouth_event("speech_start", dict(event_info))
            self._speak_elevenlabs_blocking(text)
            report["ok"] = True
            report["voice"] = self.cfg.tts_elevenlabs_voice_id
            report["message"] = "ElevenLabs test was sent with reactive mouth animation."
            return report

        if backend == "piper":
            self._emit_mouth_event("speech_start", dict(event_info))
            self._speak_piper_blocking(text)
            report["ok"] = True
            report["voice"] = self.cfg.tts_piper_model
            report["message"] = "Piper test was sent with reactive mouth animation."
            return report

        if backend == "custom":
            self._emit_mouth_event("speech_start", dict(event_info))
            self._speak_custom(text)
            report["ok"] = True
            report["message"] = "Custom TTS command launched with reactive mouth animation."
            return report

        report["message"] = f"Unknown backend: {backend}"
        return report
    except Exception as exc:
        report["message"] = f"TTS test failed: {exc}"
        report["exception"] = str(exc)
        return report
    finally:
        close_event()


# Attach helper methods for use by main.py without altering the existing constructor.
TextToSpeech.diagnostics = _bx1_tts_diagnostics  # type: ignore[attr-defined]
TextToSpeech.test_speech_blocking = _bx1_test_speech_blocking  # type: ignore[attr-defined]
