from __future__ import annotations

import base64
import math
import os
import re
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


def analyse_transcript_quality(text: str, duration_s: float = 0.0, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Backend-independent rejection of prompt leakage and decoder repetition."""
    cfg = cfg or {}
    clean = " ".join(str(text or "").split()).strip()
    tokens = re.findall(r"[a-z0-9']+", clean.lower())
    report: Dict[str, Any] = {
        "ok": bool(tokens),
        "reason": "accepted" if tokens else "no recognised speech",
        "word_count": len(tokens),
        "unique_word_ratio": round(len(set(tokens)) / max(1, len(tokens)), 3),
        "max_consecutive_repeat": 1 if tokens else 0,
        "repeated_phrase_words": 0,
        "repeated_phrase_count": 0,
        "words_per_second": round(len(tokens) / max(0.001, float(duration_s or 0.0)), 2) if duration_s else None,
    }
    if not tokens or not bool(cfg.get("stt_repetition_guard_enabled", True)):
        return report
    low = " ".join(tokens)
    prompt_leaks = (
        "the speaker may begin with a wake phrase such as",
        "preserve the wake phrase in the transcript",
        "the speaker may begin with a wake phrase",
    )
    if bool(cfg.get("stt_reject_prompt_leakage", True)) and any(item in low for item in prompt_leaks):
        report.update({"ok": False, "reason": "STT prompt leakage detected", "prompt_leakage": True})
        return report
    max_words = max(10, int(cfg.get("stt_max_transcript_words", 90) or 90))
    if len(tokens) > max_words:
        report.update({"ok": False, "reason": f"transcript exceeds {max_words} words"})
        return report
    longest = run = 1
    for index in range(1, len(tokens)):
        if tokens[index] == tokens[index - 1]:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    report["max_consecutive_repeat"] = longest
    max_repeat = max(2, int(cfg.get("stt_max_consecutive_word_repeats", 3) or 3))
    if longest > max_repeat:
        report.update({"ok": False, "reason": f"word repeated {longest} times consecutively"})
        return report
    allowed_phrase = max(1, int(cfg.get("stt_max_repeated_phrase_count", 2) or 2))
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
            if count > allowed_phrase:
                report.update({"ok": False, "reason": f"phrase repeated {count} times consecutively"})
                return report
            index = cursor if count > 1 else index + 1
    min_unique = max(0.05, min(0.95, float(cfg.get("stt_min_unique_word_ratio", 0.30) or 0.30)))
    if len(tokens) >= 10 and report["unique_word_ratio"] < min_unique:
        report.update({"ok": False, "reason": "abnormally repetitive transcript"})
        return report
    if duration_s and float(duration_s) >= 0.5:
        max_wps = max(2.0, float(cfg.get("stt_max_words_per_second", 7.0) or 7.0))
        if float(report["words_per_second"] or 0.0) > max_wps:
            report.update({"ok": False, "reason": "word rate is impossible for the captured audio"})
            return report
    return report


class FasterWhisperSTTService:
    """Thread-safe, lazy faster-whisper service for the BX1 Robot API.

    The Arduino Q captures and endpoints the utterance.  The desktop Brain PC
    performs the accurate transcription.  A model is loaded once and retained
    between requests.  When ``stt_device`` is ``auto`` the service tries CUDA
    first, then falls back to CPU int8 so the Robot API remains usable.
    """

    def __init__(self, cfg: Dict[str, Any], logger: Optional[Callable[[str], None]] = None) -> None:
        self.cfg = cfg
        self.log = logger or (lambda _message: None)
        self._lock = threading.RLock()
        self._model: Any = None
        self._model_signature: Tuple[str, str, str] = ("", "", "")
        self._loading = False
        self._last_error = ""
        self._last_backend = ""
        self._last_transcription_at = ""
        self._last_latency_ms: Optional[float] = None
        self._last_text = ""
        self._vocabulary: Dict[str, Any] = {"revision": 0, "terms": [], "updated_at": "", "rejected_terms": []}
        self._preload_thread: Optional[threading.Thread] = None
        self._package_available_cache: Optional[bool] = None

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z")

    def enabled(self) -> bool:
        return bool(self.cfg.get("stt_enabled", True))

    def _configured_model(self) -> str:
        return str(self.cfg.get("stt_model", "large-v3-turbo") or "large-v3-turbo").strip()

    def _configured_device(self) -> str:
        return str(self.cfg.get("stt_device", "auto") or "auto").strip().lower()

    def _configured_compute(self) -> str:
        return str(self.cfg.get("stt_compute_type", "int8_float16") or "int8_float16").strip()

    def _download_root(self) -> Optional[str]:
        raw = str(self.cfg.get("stt_model_cache_dir", "") or "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _candidates(self) -> List[Tuple[str, str]]:
        device = self._configured_device()
        compute = self._configured_compute()
        if device != "auto":
            return [(device, compute)]
        candidates: List[Tuple[str, str]] = [("cuda", compute)]
        if compute != "int8_float16":
            candidates.append(("cuda", "int8_float16"))
        candidates.append(("cpu", str(self.cfg.get("stt_cpu_compute_type", "int8") or "int8")))
        # Preserve order while removing duplicates.
        seen = set()
        unique: List[Tuple[str, str]] = []
        for item in candidates:
            if item not in seen:
                unique.append(item)
                seen.add(item)
        return unique

    def package_available(self) -> bool:
        # Importing faster_whisper can be relatively expensive on Windows.
        # Cache the result so UI status refreshes never repeat that import.
        cached = self._package_available_cache
        if cached is not None:
            return bool(cached)
        try:
            import faster_whisper  # noqa: F401
            available = True
        except Exception:
            available = False
        self._package_available_cache = available
        return available

    def _load_model_locked(self) -> Any:
        if not self.enabled():
            raise RuntimeError("Desktop faster-whisper STT is disabled in the Brain profile.")
        model_name = self._configured_model()
        current = self._model_signature
        if self._model is not None and current[0] == model_name:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError(
                "faster-whisper is not installed in the Brain virtual environment. "
                "Run INSTALL_FASTER_WHISPER_STT.bat, then restart the Brain App. "
                f"Import error: {exc}"
            ) from exc

        self._loading = True
        errors: List[str] = []
        try:
            for device, compute_type in self._candidates():
                try:
                    self.log(
                        f"Loading faster-whisper model {model_name!r} on {device} "
                        f"with compute type {compute_type!r}."
                    )
                    model = WhisperModel(
                        model_name,
                        device=device,
                        compute_type=compute_type,
                        download_root=self._download_root(),
                        cpu_threads=max(0, int(self.cfg.get("stt_cpu_threads", 0) or 0)),
                        num_workers=max(1, int(self.cfg.get("stt_num_workers", 1) or 1)),
                    )
                    self._model = model
                    self._model_signature = (model_name, device, compute_type)
                    self._last_backend = f"{device}/{compute_type}"
                    self._last_error = ""
                    self.log(
                        f"faster-whisper ready: model={model_name}, "
                        f"device={device}, compute={compute_type}."
                    )
                    return model
                except Exception as exc:
                    errors.append(f"{device}/{compute_type}: {exc}")
                    self.log(f"faster-whisper load attempt failed on {device}/{compute_type}: {exc}")
            raise RuntimeError("; ".join(errors) or "No faster-whisper backend could be loaded.")
        finally:
            self._loading = False

    def ensure_loaded(self) -> Any:
        with self._lock:
            try:
                return self._load_model_locked()
            except Exception as exc:
                self._last_error = str(exc)
                raise

    def preload_async(self) -> None:
        if not self.enabled() or not bool(self.cfg.get("stt_preload_on_start", True)):
            return
        with self._lock:
            if self._preload_thread and self._preload_thread.is_alive():
                return

            def worker() -> None:
                try:
                    self.ensure_loaded()
                except Exception as exc:
                    self.log(f"faster-whisper preload unavailable: {exc}")

            self._preload_thread = threading.Thread(
                target=worker,
                name="bx1-faster-whisper-preload",
                daemon=True,
            )
            self._preload_thread.start()

    def status(self) -> Dict[str, Any]:
        # IMPORTANT: do not acquire the model-load lock here. The first model
        # download/load can take several minutes. The old implementation made
        # the Qt status timer wait on that lock, which froze the main window and
        # produced a white/unpainted application while Whisper was downloading.
        # These simple attribute reads are safe enough for a diagnostic snapshot
        # under CPython; a status field may be one refresh behind at worst.
        model_name, device, compute = self._model_signature
        return {
            "enabled": self.enabled(),
            "package_available": self.package_available(),
            "loaded": self._model is not None,
            "loading": bool(self._loading),
            "configured_model": self._configured_model(),
            "configured_device": self._configured_device(),
            "configured_compute_type": self._configured_compute(),
            "active_model": model_name,
            "active_device": device,
            "active_compute_type": compute,
            "backend": self._last_backend,
            "last_error": self._last_error,
            "last_transcription_at": self._last_transcription_at,
            "last_latency_ms": self._last_latency_ms,
            "last_text": self._last_text,
        }

    @staticmethod
    def _decode_audio_payload(payload: Dict[str, Any]) -> bytes:
        encoded = str(payload.get("audio_base64") or "").strip()
        if not encoded:
            raise ValueError("audio_base64 is required")
        try:
            return base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError(f"audio_base64 is invalid: {exc}") from exc

    @staticmethod
    def _validate_wav(audio_bytes: bytes) -> Dict[str, Any]:
        if len(audio_bytes) < 44:
            raise ValueError("audio payload is too small to be a WAV file")
        tmp = tempfile.NamedTemporaryFile(prefix="bx1_stt_validate_", suffix=".wav", delete=False)
        try:
            tmp.write(audio_bytes)
            tmp.close()
            with wave.open(tmp.name, "rb") as wf:
                channels = int(wf.getnchannels())
                width = int(wf.getsampwidth())
                rate = int(wf.getframerate())
                frames = int(wf.getnframes())
            if channels != 1 or width != 2:
                raise ValueError("WAV must be mono 16-bit PCM")
            duration = frames / float(rate or 16000)
            return {
                "channels": channels,
                "sample_width": width,
                "sample_rate": rate,
                "frames": frames,
                "duration_s": round(duration, 3),
            }
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    @staticmethod
    def _segment_dict(segment: Any) -> Dict[str, Any]:
        words = []
        for word in (getattr(segment, "words", None) or []):
            words.append({
                "start": round(float(getattr(word, "start", 0.0) or 0.0), 3),
                "end": round(float(getattr(word, "end", 0.0) or 0.0), 3),
                "word": str(getattr(word, "word", "") or "").strip(),
                "probability": round(float(getattr(word, "probability", 0.0) or 0.0), 4),
            })
        return {
            "start": round(float(getattr(segment, "start", 0.0) or 0.0), 3),
            "end": round(float(getattr(segment, "end", 0.0) or 0.0), 3),
            "text": str(getattr(segment, "text", "") or "").strip(),
            "avg_logprob": round(float(getattr(segment, "avg_logprob", 0.0) or 0.0), 4),
            "no_speech_prob": round(float(getattr(segment, "no_speech_prob", 0.0) or 0.0), 4),
            "words": words,
        }

    def update_vocabulary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        terms = payload.get("terms", [])
        if not isinstance(terms, list) or len(terms) > 2000 or any(not isinstance(item, dict) for item in terms):
            return {"ok": False, "error": "invalid_terms"}
        cleaned, rejected = [], []
        for item in terms:
            term = str(item.get("term") or "").strip()
            if 1 <= len(term) <= 80 and any(ch.isalnum() for ch in term):
                cleaned.append({"term": term, "enabled": bool(item.get("enabled", True)), "variants": list(item.get("variants", []))[:12], "category": str(item.get("category") or "")[:40], "speaker_id": str(item.get("speaker_id") or "")[:80]})
            else:
                rejected.append(term[:80])
        with self._lock:
            self._vocabulary = {"revision": int(payload.get("revision") or 0), "terms": cleaned, "updated_at": self._now_iso(), "rejected_terms": rejected}
        return {"ok": True, "accepted": True, "active_hotword_count": sum(1 for item in cleaned if item["enabled"]), "vocabulary_revision": self._vocabulary["revision"], "last_update_time": self._vocabulary["updated_at"], "rejected_terms": rejected, "model": self._model_signature[0] or self._configured_model()}

    def vocabulary_status(self) -> Dict[str, Any]:
        with self._lock:
            return {"accepted": True, "active_hotword_count": sum(1 for item in self._vocabulary.get("terms", []) if item.get("enabled", True)), "vocabulary_revision": self._vocabulary.get("revision", 0), "last_update_time": self._vocabulary.get("updated_at", ""), "rejected_terms": list(self._vocabulary.get("rejected_terms", [])), "model": self._model_signature[0] or self._configured_model()}

    def transcribe_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        request_id = str(metadata.get("request_id") or payload.get("request_id") or "").strip()[:96]
        if not self.enabled():
            return {"ok": False, "outcome": "service_failure", "request_id": request_id,
                    "error": "Desktop faster-whisper STT is disabled.", "stt": self.status()}
        audio_bytes = self._decode_audio_payload(payload)
        max_bytes = max(128 * 1024, int(self.cfg.get("stt_max_audio_bytes", 8 * 1024 * 1024) or 8 * 1024 * 1024))
        if len(audio_bytes) > max_bytes:
            return {"ok": False, "outcome": "rejected", "request_id": request_id,
                    "error": f"Audio payload exceeds the {max_bytes} byte limit.", "stt": self.status()}
        wav_info = self._validate_wav(audio_bytes)

        suffix = ".wav"
        tmp = tempfile.NamedTemporaryFile(prefix="bx1_brain_stt_", suffix=suffix, delete=False)
        started = time.perf_counter()
        try:
            tmp.write(audio_bytes)
            tmp.close()
            model = self.ensure_loaded()
            language = str(payload.get("language") or self.cfg.get("stt_language", "en") or "en").strip() or "en"
            dynamic_terms = [str(item.get("term") or "").strip() for item in self._vocabulary.get("terms", []) if isinstance(item, dict) and item.get("enabled", True)]
            hotwords = ", ".join(dict.fromkeys([part.strip() for source in (str(payload.get("hotwords") or ""), str(self.cfg.get("stt_hotwords", "") or ""), ", ".join(dynamic_terms)) for part in source.split(",") if part.strip()])) or None
            if "initial_prompt" in payload:
                initial_prompt = str(payload.get("initial_prompt") or "").strip() or None
            else:
                initial_prompt = str(self.cfg.get("stt_initial_prompt", "") or "").strip() or None
            segments_iter, info = model.transcribe(
                tmp.name,
                language=language,
                task="transcribe",
                beam_size=max(1, min(10, int(self.cfg.get("stt_beam_size", 5) or 5))),
                best_of=max(1, min(10, int(self.cfg.get("stt_best_of", 5) or 5))),
                temperature=0.0,
                condition_on_previous_text=False,
                word_timestamps=True,
                vad_filter=bool(self.cfg.get("stt_vad_filter", True)),
                vad_parameters={
                    "min_silence_duration_ms": max(100, int(self.cfg.get("stt_vad_min_silence_ms", 350) or 350)),
                    "speech_pad_ms": max(0, int(self.cfg.get("stt_vad_speech_pad_ms", 120) or 120)),
                } if bool(self.cfg.get("stt_vad_filter", True)) else None,
                initial_prompt=initial_prompt,
                hotwords=hotwords,
                no_speech_threshold=float(self.cfg.get("stt_no_speech_threshold", 0.6) or 0.6),
                log_prob_threshold=float(self.cfg.get("stt_log_prob_threshold", -1.0) or -1.0),
            )
            segments = [self._segment_dict(seg) for seg in segments_iter]
            text = " ".join(seg["text"] for seg in segments if seg["text"]).strip()
            avg_logs = [float(seg["avg_logprob"]) for seg in segments if seg.get("text")]
            avg_logprob = sum(avg_logs) / len(avg_logs) if avg_logs else None
            # This is an indicative score for diagnostics, not a calibrated probability.
            confidence = None if avg_logprob is None else max(0.0, min(1.0, math.exp(avg_logprob)))
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
            duration_after_vad = float(getattr(info, "duration_after_vad", wav_info.get("duration_s", 0.0)) or 0.0)
            quality = analyse_transcript_quality(text, duration_after_vad, self.cfg)
            accepted = bool(text) and bool(quality.get("ok", True))
            with self._lock:
                self._last_error = "" if accepted else str(quality.get("reason") or "No speech was transcribed.")
                self._last_transcription_at = self._now_iso()
                self._last_latency_ms = elapsed_ms
                self._last_text = text
            return {
                "ok": accepted,
                "outcome": "accepted" if accepted else "rejected",
                "request_id": request_id,
                "text": text,
                "raw_text": text,
                "vocabulary_biased_text": text,
                "hotword_context": {"revision": self._vocabulary.get("revision", 0), "terms": dynamic_terms, "accepted": True, "count": len(dynamic_terms)},
                "language": str(getattr(info, "language", language) or language),
                "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 4),
                "duration_s": round(float(getattr(info, "duration", wav_info.get("duration_s", 0.0)) or 0.0), 3),
                "duration_after_vad_s": round(duration_after_vad, 3),
                "confidence": None if confidence is None else round(confidence, 4),
                "average_logprob": None if avg_logprob is None else round(avg_logprob, 4),
                "segments": segments,
                "latency_ms": elapsed_ms,
                "backend": "faster-whisper",
                "model": self._model_signature[0],
                "device": self._model_signature[1],
                "compute_type": self._model_signature[2],
                "wav": wav_info,
                "transcript_quality": quality,
                "error": "" if accepted else str(quality.get("reason") or "No speech was transcribed."),
            }
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._last_latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
            return {"ok": False, "outcome": "service_failure", "request_id": request_id,
                    "error": str(exc), "backend": "faster-whisper", "stt": self.status(), "wav": wav_info}
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
