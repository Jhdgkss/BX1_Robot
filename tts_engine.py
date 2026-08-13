from __future__ import annotations

import gc
import queue
import re
import threading
import time
from pathlib import Path

import numpy as np
import torch
from qwen_tts import Qwen3TTSModel

from tts_pipeline.buffered_playback import BufferedTTSPlayback
from tts_pipeline.voice_settings import TTSVoiceSettings


TTS_ENABLED = True
DEVICE = "cuda:0"
DTYPE = torch.bfloat16
ATTENTION_IMPLEMENTATION = "sdpa"


class QwenTTSEngine:
    """BX1 Qwen voice-clone TTS engine.

    Runtime voice settings are owned by this module and persisted by
    tts_pipeline.voice_settings. Master_Main_GUI.py only orchestrates GUI
    requests to this public interface.
    """

    def __init__(self, robot_audio):
        self.enabled = TTS_ENABLED
        self.robot_audio = robot_audio
        self.model = None
        self.voice_prompt = None
        self.speech_queue = queue.Queue()
        self.worker_thread = None
        self.playback = BufferedTTSPlayback(robot_audio)
        self._engine_lock = threading.RLock()

        self.settings_store = TTSVoiceSettings()
        self._settings = self.settings_store.load()
        self._apply_runtime_values(self._settings)

        if not self.enabled:
            print("[TTS] Disabled.")
            return

        print()
        print("====================================================")
        print(" QWEN TTS ENGINE")
        print("====================================================")

        self._check_system()
        self._load_model()
        self._create_voice()

        self.worker_thread = threading.Thread(
            target=self._speech_worker,
            daemon=True,
            name="BX1-Qwen-TTS",
        )
        self.worker_thread.start()

        print()
        print("[TTS] Ready.")
        print("====================================================")
        print()

    # ========================================================
    # SETTINGS
    # ========================================================

    def _apply_runtime_values(self, settings):
        self.model_name = str(settings["model_name"])
        self.reference_audio = Path(str(settings["reference_audio"]))
        self.reference_text = str(settings.get("reference_text", "") or "").strip()
        self.x_vector_only_mode = bool(settings.get("x_vector_only_mode", True))
        self.language = str(settings.get("language", "English") or "English")

        self.max_chunk_chars = int(settings.get("max_chunk_chars", 55))
        self.split_on_commas = bool(settings.get("split_on_commas", True))
        self.max_new_tokens = int(settings.get("max_new_tokens", 128))
        self.max_batch_chunks = int(settings.get("max_batch_chunks", 6))

        self.do_sample = bool(settings.get("do_sample", True))
        self.top_k = int(settings.get("top_k", 50))
        self.top_p = float(settings.get("top_p", 1.0))
        self.temperature = float(settings.get("temperature", 0.9))
        self.repetition_penalty = float(settings.get("repetition_penalty", 1.05))

        self.normalise_quiet_audio = bool(
            settings.get("normalise_quiet_audio", True)
        )
        self.quiet_peak_threshold = float(
            settings.get("quiet_peak_threshold", 0.20)
        )
        self.normalise_target_peak = float(
            settings.get("normalise_target_peak", 0.90)
        )

    def get_settings(self):
        return dict(self._settings)

    @staticmethod
    def _voice_signature(settings):
        return (
            str(settings.get("reference_audio", "")),
            str(settings.get("reference_text", "")),
            bool(settings.get("x_vector_only_mode", True)),
        )

    def _validate_voice_settings(self, settings):
        reference_audio = Path(str(settings.get("reference_audio", "")))

        if not reference_audio.exists():
            raise FileNotFoundError(
                "TTS reference audio not found:\n"
                f"{reference_audio}"
            )

        if reference_audio.suffix.lower() != ".wav":
            raise ValueError("The TTS reference voice must be a .wav file.")

        if (
            not bool(settings.get("x_vector_only_mode", True))
            and not str(settings.get("reference_text", "") or "").strip()
        ):
            raise ValueError(
                "Full ICL voice cloning requires the exact transcript of "
                "the reference WAV. Enter the words spoken in the recording."
            )

    def apply_settings(self, values):
        """Apply GUI TTS settings and persist them after a successful reload.

        Model/reference changes rebuild the appropriate Qwen state. Generation
        and chunking settings take effect without reloading the model.
        """

        candidate = self.settings_store.normalise(values)
        self._validate_voice_settings(candidate)

        old_settings = dict(self._settings)
        model_changed = candidate["model_name"] != old_settings["model_name"]
        voice_changed = (
            self._voice_signature(candidate)
            != self._voice_signature(old_settings)
        )

        with self._engine_lock:
            try:
                self._settings = candidate
                self._apply_runtime_values(candidate)

                if model_changed:
                    print(
                        "[TTS SETTINGS] Model changed -> "
                        f"{self.model_name}. Reloading Qwen..."
                    )
                    self._load_model(reload_existing=True)
                    self._create_voice()

                elif voice_changed:
                    print(
                        "[TTS SETTINGS] Reference voice changed. "
                        "Rebuilding LEO voice profile..."
                    )
                    self._create_voice()

                self._settings = self.settings_store.save(candidate)
                self._apply_runtime_values(self._settings)

                print(
                    "[TTS SETTINGS] Applied. Clone mode: "
                    + (
                        "speaker embedding only"
                        if self.x_vector_only_mode
                        else "full ICL"
                    )
                )

                return self.get_settings()

            except Exception:
                # Restore the known-good runtime configuration. If a model
                # replacement failed after unloading the previous checkpoint,
                # reload the old model as part of the rollback.
                self._settings = old_settings
                self._apply_runtime_values(old_settings)

                if model_changed:
                    try:
                        self._load_model(reload_existing=True)
                        self._create_voice()
                    except Exception as rollback_exc:
                        print(
                            "[TTS SETTINGS] Rollback reload failed: "
                            f"{type(rollback_exc).__name__}: {rollback_exc}"
                        )
                elif voice_changed:
                    try:
                        self._create_voice()
                    except Exception as rollback_exc:
                        print(
                            "[TTS SETTINGS] Voice rollback failed: "
                            f"{type(rollback_exc).__name__}: {rollback_exc}"
                        )

                raise

    # ========================================================
    # STARTUP / MODEL
    # ========================================================

    def _check_system(self):
        self._validate_voice_settings(self._settings)

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available for Qwen TTS.")

        print(f"[TTS] GPU: {torch.cuda.get_device_name(0)}")
        print(f"[TTS] Model: {self.model_name}")
        print(f"[TTS] Voice: {self.reference_audio}")
        print(
            "[TTS] Clone mode: "
            + (
                "speaker embedding only"
                if self.x_vector_only_mode
                else "full ICL (reference audio + transcript)"
            )
        )

        torch.set_float32_matmul_precision("high")
        torch.backends.cuda.matmul.allow_tf32 = True

    def _load_model(self, reload_existing=False):
        if reload_existing and self.model is not None:
            print("[TTS] Unloading current Qwen model...")
            old_model = self.model
            self.model = None
            self.voice_prompt = None
            del old_model
            gc.collect()
            torch.cuda.empty_cache()

        print(f"[TTS] Loading Qwen model: {self.model_name}")
        started = time.perf_counter()

        self.model = Qwen3TTSModel.from_pretrained(
            self.model_name,
            device_map=DEVICE,
            dtype=DTYPE,
            attn_implementation=ATTENTION_IMPLEMENTATION,
        )

        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        print(f"[TTS] Model loaded in {elapsed:.2f}s")

    def _create_voice(self):
        self._validate_voice_settings(self._settings)

        print("[TTS] Creating LEO voice profile...")
        started = time.perf_counter()

        ref_text = None
        if not self.x_vector_only_mode:
            ref_text = self.reference_text

        with torch.inference_mode():
            self.voice_prompt = self.model.create_voice_clone_prompt(
                ref_audio=str(self.reference_audio),
                ref_text=ref_text,
                x_vector_only_mode=self.x_vector_only_mode,
            )

        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        print(f"[TTS] Voice ready in {elapsed:.2f}s")

    # ========================================================
    # PUBLIC SPEECH QUEUE
    # ========================================================

    def speak(self, text: str):
        if not self.enabled or not text:
            return

        text = str(text).strip()
        if not text:
            return

        print(f"[TTS] Queued: {text}")
        self.speech_queue.put(text)

    def _speech_worker(self):
        while True:
            text = self.speech_queue.get()
            try:
                if text is None:
                    return
                self._speak_text(text)
            except Exception as exc:
                print(f"[TTS] Error: {type(exc).__name__}: {exc}")
            finally:
                self.speech_queue.task_done()

    # ========================================================
    # TEXT CHUNKING
    # ========================================================

    def _split_text(self, text: str):
        text = re.sub(r"\s+", " ", text.strip())
        if not text:
            return []

        if self.split_on_commas:
            parts = re.split(r"(?<=[.!?;:,])\s+", text)
        else:
            parts = re.split(r"(?<=[.!?;:])\s+", text)

        parts = [part.strip() for part in parts if part.strip()]
        chunks = []
        current = ""

        for part in parts:
            proposed = f"{current} {part}".strip() if current else part
            if len(proposed) <= self.max_chunk_chars:
                current = proposed
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(part) > self.max_chunk_chars:
                words = part.split()
                temp = ""
                for word in words:
                    proposed_word = f"{temp} {word}".strip() if temp else word
                    if len(proposed_word) <= self.max_chunk_chars:
                        temp = proposed_word
                    else:
                        if temp:
                            chunks.append(temp)
                        temp = word
                current = temp
            else:
                current = part

        if current:
            chunks.append(current)

        return chunks

    # ========================================================
    # AUDIO PREPARATION
    # ========================================================

    def _prepare_audio(self, audio):
        audio = np.asarray(audio, dtype=np.float32)
        audio = np.squeeze(audio)

        if audio.size == 0:
            raise RuntimeError("Qwen returned empty audio.")

        peak = float(np.max(np.abs(audio)))
        if (
            self.normalise_quiet_audio
            and peak > 0
            and peak < self.quiet_peak_threshold
        ):
            audio = audio / peak * self.normalise_target_peak

        return np.clip(audio, -1.0, 1.0)

    @staticmethod
    def _make_pcm16(audio):
        audio = np.clip(audio, -1.0, 1.0)
        pcm16 = (audio * 32767.0).astype("<i2")
        return pcm16.tobytes()

    # ========================================================
    # QWEN GENERATION
    # ========================================================

    def _generate_batch(self, chunks, start_number):
        chunks = [str(chunk).strip() for chunk in chunks if str(chunk).strip()]
        if not chunks:
            return [], 0.0, 0.0

        end_number = start_number + len(chunks) - 1

        print()
        print(f"[TTS GEN] Generating chunk(s) {start_number}-{end_number}...")
        for offset, chunk in enumerate(chunks):
            number = start_number + offset
            print(f"      {number}: {chunk}")

        with self._engine_lock:
            torch.cuda.synchronize()
            started = time.perf_counter()

            if len(chunks) == 1:
                text_input = chunks[0]
                language_input = self.language
            else:
                text_input = chunks
                language_input = [self.language] * len(chunks)

            with torch.inference_mode():
                wavs, sample_rate = self.model.generate_voice_clone(
                    text=text_input,
                    language=language_input,
                    voice_clone_prompt=self.voice_prompt,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=self.do_sample,
                    top_k=self.top_k,
                    top_p=self.top_p,
                    temperature=self.temperature,
                    repetition_penalty=self.repetition_penalty,
                )

            torch.cuda.synchronize()
            generation_seconds = time.perf_counter() - started

        if not wavs:
            print("[TTS GEN] Qwen returned no audio.")
            return [], generation_seconds, 0.0

        results = []
        speech_seconds = 0.0

        for offset, wav in enumerate(wavs):
            number = start_number + offset
            audio = self._prepare_audio(wav)
            duration = len(audio) / float(sample_rate)
            speech_seconds += duration
            pcm16 = self._make_pcm16(audio)

            print(
                f"[TTS GEN {number}] {duration:.2f}s speech "
                f"/ {len(pcm16)} PCM bytes"
            )

            results.append(
                {
                    "number": number,
                    "pcm16": pcm16,
                    "sample_rate": int(sample_rate),
                    "duration": float(duration),
                }
            )

        generation_rtf = (
            generation_seconds / speech_seconds
            if speech_seconds > 0
            else 0.0
        )

        print(
            "[TTS GEN] "
            f"Batch completed in {generation_seconds:.2f}s "
            f"for {speech_seconds:.2f}s speech "
            f"(generation RTF {generation_rtf:.2f})."
        )

        return results, generation_seconds, speech_seconds

    def _generate_complete_reply(self, chunks):
        generated_items = []
        total_generation_seconds = 0.0
        total_speech_seconds = 0.0
        next_number = 1

        for start in range(0, len(chunks), self.max_batch_chunks):
            group = chunks[start:start + self.max_batch_chunks]

            batch_items, generation_seconds, speech_seconds = self._generate_batch(
                group,
                start_number=next_number,
            )

            generated_items.extend(batch_items)
            total_generation_seconds += generation_seconds
            total_speech_seconds += speech_seconds
            next_number += len(group)

        overall_rtf = (
            total_generation_seconds / total_speech_seconds
            if total_speech_seconds > 0
            else 0.0
        )

        print()
        print("[TTS BUFFER] Complete reply generated.")
        print(f"[TTS BUFFER] Generation : {total_generation_seconds:.2f}s")
        print(f"[TTS BUFFER] Speech     : {total_speech_seconds:.2f}s")
        print(f"[TTS BUFFER] Gen RTF    : {overall_rtf:.2f}")

        return generated_items

    def _speak_text(self, text: str):
        chunks = self._split_text(text)
        if not chunks:
            return

        print()
        print(f"[TTS] Reply split into {len(chunks)} chunk(s)")
        for index, chunk in enumerate(chunks, start=1):
            print(f"      {index}: {chunk}")

        generated_items = self._generate_complete_reply(chunks)
        if not generated_items:
            print("[TTS] No speech was generated.")
            return

        self.playback.play(generated_items)

    def close(self):
        if not self.enabled:
            return
        self.speech_queue.put(None)
