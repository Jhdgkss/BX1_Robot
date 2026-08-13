# ============================================================
# BX1 MASTER MAIN
# ============================================================
#
# SINGLE BX1 ENTRY POINT
# ----------------------
#
# Run this file and choose one of two operating modes:
#
#   1. LOCAL
#      Keyboard -> LLM -> Qwen TTS -> PC speakers
#
#   2. ROBOT
#      Robot microphone -> VAD -> Whisper -> TranscriptProcessor
#      -> LLM -> Qwen TTS -> robot speaker
#
# This file is intentionally self-contained as the orchestration
# layer. Existing BX1 modules are not modified.
#
# ============================================================

import asyncio
import math
import re
import sys
import threading
import time

from settings import config

from colorama import Fore, Back, Style

from llm_client import LLMClient
from tts_engine import QwenTTSEngine
from sound_effects import SoundEffectLibrary


# ============================================================
# SHARED AUDIO BRIDGE
# ============================================================
#
# Qwen TTS and sound effects both pass through this object.
#
# In LOCAL mode:
#     -> pc_audio.py
#
# In ROBOT mode:
#     -> audio_to_robot_streamer.py
#
# The bridge keeps orchestration here in Master_Main.py rather
# than moving control logic into the downstream audio modules.
#
# ============================================================

class MasterAudioBridge:

    def __init__(
        self,
        audio_output,
        sound_library,
        mode_name,
    ):
        self.audio_output = audio_output
        self.sound_library = sound_library
        self.mode_name = str(mode_name).upper()

        # Only one audio item may own the selected output at once.
        self._audio_session_lock = threading.Lock()

        self._tts_session_active = False

        self._waiting_timer = None
        self._waiting_timer_lock = threading.RLock()


    # ========================================================
    # TTS AUDIO
    # ========================================================

    def start_tts(
        self,
        sample_rate=24000,
    ):
        """Called by tts_engine.py when generated speech starts."""

        self.cancel_llm_waiting_timer()

        print(
            f"[MASTER AUDIO:{self.mode_name}] "
            f"New TTS reply received at {sample_rate} Hz."
        )

        self._audio_session_lock.acquire()

        started = False

        try:
            started = bool(
                self.audio_output.start_tts(
                    sample_rate
                )
            )

            self._tts_session_active = started

            return started

        finally:
            if not started:
                self._tts_session_active = False

                if self._audio_session_lock.locked():
                    self._audio_session_lock.release()


    def send_pcm16(
        self,
        pcm_data: bytes,
    ):
        """Pass generated PCM16 to the currently selected output."""

        if not pcm_data:
            return False

        if not self._tts_session_active:
            return False

        # Some BX1 audio outputs return True/False, while the
        # robot streamer historically returns None after successfully
        # queueing PCM. Only an explicit False means failure.
        result = self.audio_output.send_pcm16(
            pcm_data
        )

        return result is not False


    def end_tts(self):
        """Complete the current TTS session."""

        print(
            f"[MASTER AUDIO:{self.mode_name}] "
            "Complete generated reply received."
        )

        try:
            if not self._tts_session_active:
                return False

            return self.audio_output.end_tts()

        finally:
            self._tts_session_active = False

            if self._audio_session_lock.locked():
                self._audio_session_lock.release()


    # ========================================================
    # SOUND EFFECTS
    # ========================================================

    def _start_effect_output(
        self,
        sample_rate,
    ):
        """
        Prefer the robot streamer's dedicated effect interface if
        present. Otherwise use the same proven start_tts path used
        by the local PC player.
        """

        start_effect = getattr(
            self.audio_output,
            "start_effect",
            None,
        )

        if callable(start_effect):
            try:
                return bool(
                    start_effect(sample_rate)
                )
            except TypeError:
                return bool(
                    start_effect()
                )

        return bool(
            self.audio_output.start_tts(
                sample_rate
            )
        )


    def _end_effect_output(self):
        end_effect = getattr(
            self.audio_output,
            "end_effect",
            None,
        )

        if callable(end_effect):
            return end_effect()

        return self.audio_output.end_tts()


    def play_sound_effect(
        self,
        event_name,
    ):
        """Load a configured WAV and route it to the active output."""

        effect = self.sound_library.load(
            event_name
        )

        if effect is None:
            return False

        print(
            f"[SOUNDS:{self.mode_name}] Event: {event_name} -> "
            f"{effect.file_path.name}"
        )

        with self._audio_session_lock:

            started = False

            try:
                started = self._start_effect_output(
                    effect.sample_rate
                )

                if not started:
                    return False

                # IMPORTANT:
                # audio_to_robot_streamer.py historically returns None
                # after successfully queueing PCM. None is therefore not
                # a failure. Only an explicit False is treated as one.
                send_result = self.audio_output.send_pcm16(
                    effect.pcm16
                )

                if send_result is False:
                    return False

                return True

            except Exception as exc:
                print(
                    f"[SOUNDS:{self.mode_name}] "
                    f"Playback error for {event_name}: "
                    f"{type(exc).__name__}: {exc}"
                )
                return False

            finally:
                # Once START has been sent, END must always be sent.
                # Otherwise the robot remains in speaker/TTS mode and
                # its microphone stays disabled.
                if started:
                    try:
                        self._end_effect_output()
                    except Exception as exc:
                        print(
                            f"[SOUNDS:{self.mode_name}] "
                            f"Could not close {event_name} audio session: "
                            f"{type(exc).__name__}: {exc}"
                        )


    def play_sound_effect_async(
        self,
        event_name,
    ):
        """Play a sound cue without blocking LLM/STT processing."""

        if not self.sound_library.is_enabled(
            event_name
        ):
            return False

        thread = threading.Thread(
            target=self.play_sound_effect,
            args=(event_name,),
            daemon=True,
            name=f"BX1Sound-{event_name}",
        )

        thread.start()

        return True


    # ========================================================
    # DELAYED LLM WAITING SOUND
    # ========================================================

    def start_llm_waiting_timer(self):
        """
        Begin the configured silence timer when a request is sent
        to the LLM. It is cancelled when real TTS starts.
        """

        self.cancel_llm_waiting_timer()

        if not self.sound_library.is_enabled(
            "llm_waiting"
        ):
            return False

        delay_seconds = (
            self.sound_library.get_delay_seconds(
                "llm_waiting",
                default=3.0,
            )
        )

        if delay_seconds <= 0:
            return self.play_sound_effect_async(
                "llm_waiting"
            )

        timer = threading.Timer(
            delay_seconds,
            self._llm_waiting_timer_fired,
        )

        timer.daemon = True

        with self._waiting_timer_lock:
            self._waiting_timer = timer

        timer.start()

        print(
            f"[SOUNDS:{self.mode_name}] "
            f"LLM waiting timer started: {delay_seconds:.2f}s"
        )

        return True


    def _llm_waiting_timer_fired(self):
        with self._waiting_timer_lock:
            self._waiting_timer = None

        print(
            f"[SOUNDS:{self.mode_name}] "
            "LLM still waiting - playing delayed cue."
        )

        self.play_sound_effect_async(
            "llm_waiting"
        )


    def cancel_llm_waiting_timer(self):
        with self._waiting_timer_lock:
            timer = self._waiting_timer
            self._waiting_timer = None

        if timer is not None:
            timer.cancel()


    def close(self):
        self.cancel_llm_waiting_timer()


# ============================================================
# SHARED DISPLAY
# ============================================================

def print_leo_reply(
    reply: str,
):
    print()

    print(
        Fore.YELLOW
        + Back.BLUE
        + Style.BRIGHT
        + " LEO "
        + Style.RESET_ALL
        + " "
        + Fore.CYAN
        + reply
        + Style.RESET_ALL
    )

    print()


# ============================================================
# TTS TEXT CLEANER
# ============================================================

def prepare_text_for_tts(
    text,
):
    """
    Create a speech-only copy of an LLM reply.

    The original reply is left untouched for console display and
    conversation memory. This copy removes presentation markup,
    labels and emoji that Qwen should not try to pronounce.
    """

    if text is None:
        return ""

    speech = str(text)

    # Markdown links: speak the visible description, not the URL.
    speech = re.sub(
        r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)",
        r"\1",
        speech,
        flags=re.IGNORECASE,
    )

    # Remove raw web addresses from speech.
    speech = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        speech,
        flags=re.IGNORECASE,
    )

    # Remove common response/formatting labels.
    speech = re.sub(
        r"(?im)^\s*(?:#{1,6}\s*)?"
        r"(?:\*\*|__)?"
        r"(?:answer|response|reply|joke|topic)"
        r"(?:\*\*|__)?\s*:\s*",
        "",
        speech,
    )

    # Markdown headings and bullet/list markers.
    speech = re.sub(
        r"(?m)^\s*#{1,6}\s*",
        "",
        speech,
    )

    speech = re.sub(
        r"(?m)^\s*(?:[-+*]|\d+[.)])\s+",
        "",
        speech,
    )

    # Remove Markdown emphasis/code characters while retaining words.
    speech = speech.replace("**", "")
    speech = speech.replace("__", "")
    speech = speech.replace("`", "")
    speech = speech.replace("~", "")
    speech = speech.replace("*", "")

    # Make a few common symbols natural for speech.
    speech = speech.replace("&", " and ")
    speech = speech.replace("—", ", ")
    speech = speech.replace("–", ", ")
    speech = speech.replace("|", " ")
    speech = speech.replace("_", " ")

    # Remove emoji, pictographs, variation selectors and joiners.
    speech = re.sub(
        "["
        "\U0001F1E6-\U0001F1FF"
        "\U0001F300-\U0001FAFF"
        "\U00002700-\U000027BF"
        "\U00002600-\U000026FF"
        "\uFE0E\uFE0F\u200D"
        "]+",
        " ",
        speech,
    )

    # Collapse line breaks and excess whitespace into normal prose.
    speech = re.sub(
        r"\s+",
        " ",
        speech,
    ).strip()

    return speech


# ============================================================
# SHARED LLM REQUEST HANDLER
# ============================================================
#
# Both LOCAL and ROBOT modes now use the same LLM -> sound cue
# -> Qwen TTS sequence.
#
# ============================================================

def process_llm_request(
    user_text,
    llm,
    tts,
    audio_bridge,
):
    """Send text to the LLM and speak the returned response."""

    if not user_text:
        return False

    if not llm.enabled:
        print(
            Fore.RED
            + "[LLM] LLM is disabled."
            + Style.RESET_ALL
        )

        audio_bridge.play_sound_effect_async(
            "error"
        )

        return False

    print(
        Fore.GREEN
        + "[LLM] Thinking..."
        + Style.RESET_ALL
    )

    request_has_speech_pending = False

    try:
        audio_bridge.play_sound_effect_async(
            "llm_request_sent"
        )

        audio_bridge.start_llm_waiting_timer()

        request_has_speech_pending = True

        reply = llm.ask(
            user_text
        )

        if not reply:
            audio_bridge.cancel_llm_waiting_timer()
            request_has_speech_pending = False

            print(
                Fore.YELLOW
                + "[LLM] No reply returned."
                + Style.RESET_ALL
            )

            audio_bridge.play_sound_effect_async(
                "error"
            )

            return False

        audio_bridge.play_sound_effect_async(
            "llm_response_received"
        )

        print_leo_reply(
            reply
        )

        if tts.enabled:
            speech_reply = prepare_text_for_tts(
                reply
            )

            if not speech_reply:
                speech_reply = str(reply).strip()

            tts.speak(
                speech_reply
            )

            # Qwen works on its own worker thread. Waiting here
            # keeps one conversational request orderly while the
            # audio bridge still cancels the waiting cue at the
            # point actual TTS audio begins.
            tts.speech_queue.join()

            request_has_speech_pending = False

        else:
            audio_bridge.cancel_llm_waiting_timer()
            request_has_speech_pending = False

        return True

    except Exception as exc:
        audio_bridge.cancel_llm_waiting_timer()
        request_has_speech_pending = False

        print(
            Fore.RED
            + (
                f"[LLM] Error: "
                f"{type(exc).__name__}: {exc}"
            )
            + Style.RESET_ALL
        )

        audio_bridge.play_sound_effect_async(
            "error"
        )

        return False

    finally:
        if request_has_speech_pending:
            audio_bridge.cancel_llm_waiting_timer()


# ============================================================
# LOCAL MODE
# ============================================================

def run_local_mode():
    """Keyboard -> LLM -> Qwen -> PC speakers."""

    # Local-only import keeps robot modules out of the local path.
    from pc_audio import PCAudioOutput

    print()
    print("====================================================")
    print(" BX1 MASTER - LOCAL MODE")
    print("====================================================")
    print()
    print("Microphone input : DISABLED")
    print("Whisper / STT    : DISABLED")
    print("Robot audio link : DISABLED")
    print("Input            : KEYBOARD")
    print("Speech generator : tts_engine.py / Qwen")
    print("Audio bridge     : Master_Main.py")
    print("Sound events     : sound_effects.py")
    print("Playback         : pc_audio.py -> PC speakers")
    print()

    llm = LLMClient()
    sound_library = SoundEffectLibrary()

    pc_audio = PCAudioOutput()
    pc_audio.start()

    audio_bridge = MasterAudioBridge(
        audio_output=pc_audio,
        sound_library=sound_library,
        mode_name="LOCAL",
    )

    tts = QwenTTSEngine(
        audio_bridge
    )

    print(
        "[BX1] LLM is "
        + ("ENABLED" if llm.enabled else "DISABLED")
    )

    print(
        "[BX1] TTS is "
        + ("ENABLED" if tts.enabled else "DISABLED")
    )

    print(
        "[BX1] Sound effects are "
        + (
            "ENABLED"
            if sound_library.enabled
            else "DISABLED"
        )
    )

    print()
    print("Type a message for LEO and press Enter.")
    print("Type /exit or /quit to stop.")
    print()

    try:
        while True:
            try:
                user_text = input(
                    Fore.GREEN
                    + Style.BRIGHT
                    + "YOU > "
                    + Style.RESET_ALL
                )
            except EOFError:
                break

            user_text = user_text.strip()

            if not user_text:
                continue

            if user_text.lower() in {
                "/exit",
                "/quit",
                "exit",
                "quit",
            }:
                break

            process_llm_request(
                user_text=user_text,
                llm=llm,
                tts=tts,
                audio_bridge=audio_bridge,
            )

    finally:
        print()
        print("[BX1] Shutting down LOCAL mode...")

        audio_bridge.close()
        tts.close()

        if (
            tts.worker_thread is not None
            and tts.worker_thread.is_alive()
        ):
            tts.worker_thread.join(
                timeout=2.0
            )

        pc_audio.close()


# ============================================================
# ROBOT MODE - WAKE SOUND HELPER
# ============================================================

def _event_indicates_wake(
    event,
    recognized_text,
):
    """
    Prefer a wake flag/type supplied by TranscriptProcessor if one
    exists. Fall back to the currently used LEO wake wording.

    This helper only triggers a sound effect; TranscriptProcessor
    remains the authority over whether speech is sent to the LLM.
    """

    for flag_name in (
        "wake_detected",
        "is_wake",
        "wake_word_detected",
    ):
        flag_value = getattr(
            event,
            flag_name,
            None,
        )

        if flag_value is True:
            return True

    for type_name in (
        "event_type",
        "type",
        "kind",
    ):
        value = getattr(
            event,
            type_name,
            None,
        )

        if value is not None:
            value_text = str(value).lower()

            if "wake" in value_text:
                return True

    normalized = re.sub(
        r"[^a-z0-9 ]+",
        " ",
        str(recognized_text).lower(),
    )

    normalized = " ".join(
        normalized.split()
    )

    return (
        normalized == "leo"
        or normalized.startswith("hey leo")
        or normalized.startswith("hi leo")
        or normalized.startswith("hello leo")
        or normalized.startswith("leo ")
    )



# ============================================================
# ROBOT MODE - CONVERSATION SESSION HELPERS
# ============================================================

def _normalize_conversation_phrase(
    text,
):
    """Normalize STT text for wake/end phrase matching."""

    normalized = str(
        text
        or ""
    ).lower()

    normalized = normalized.replace(
        "’",
        "'",
    )

    # Apostrophes are discarded so Whisper's "that's all" and
    # "thats all" both match the same configured end phrase.
    normalized = re.sub(
        r"[^a-z0-9 ]+",
        " ",
        normalized,
    )

    return " ".join(
        normalized.split()
    )


def _configured_end_phrases():
    """Return normalized END_PHRASES from config.py."""

    phrases = getattr(
        config,
        "END_PHRASES",
        (),
    )

    return tuple(
        phrase
        for phrase in (
            _normalize_conversation_phrase(
                item
            )
            for item in phrases
        )
        if phrase
    )


def _text_indicates_conversation_end(
    recognized_text,
):
    """
    Return True when the recognized utterance contains one of the
    configured conversation end phrases.

    Examples from config.py currently include:
        thanks leo
        thank you leo
        goodbye leo
        that's all
    """

    normalized = _normalize_conversation_phrase(
        recognized_text
    )

    if not normalized:
        return False

    padded = f" {normalized} "

    for phrase in _configured_end_phrases():
        if f" {phrase} " in padded:
            return True

    return False


def _strip_wake_prefix(
    recognized_text,
):
    """
    Fallback command cleaner for continuous mode.

    TranscriptProcessor remains the preferred source of command_text.
    This only removes a leading LEO wake phrase when the processor
    did not return a command.
    """

    text = str(
        recognized_text
        or ""
    ).strip()

    if not text:
        return ""

    wake_words = getattr(
        config,
        "WAKE_WORDS",
        (),
    )

    ordered_wakes = sorted(
        (
            str(item).strip()
            for item in wake_words
            if str(item).strip()
        ),
        key=len,
        reverse=True,
    )

    for wake in ordered_wakes:
        pattern = (
            r"^\s*"
            + re.escape(wake)
            + r"\b[\s,.:;!?-]*"
        )

        cleaned = re.sub(
            pattern,
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

        if cleaned != text:
            return cleaned

    return text


def select_robot_conversation_mode():
    """
    Choose how wake-word gating behaves in ROBOT mode.

    STANDARD:
        Preserve TranscriptProcessor's existing wake/session timeout.

    CONTINUOUS:
        A wake word opens the conversation and it remains open until
        one of config.END_PHRASES is spoken.
    """

    # Optional command-line shortcut:
    #
    #     python Master_Main.py robot standard
    #     python Master_Main.py robot continuous

    if len(sys.argv) >= 3:
        requested = sys.argv[2].strip().lower()

        if requested in {
            "1",
            "standard",
            "normal",
            "wake",
            "wake-word",
            "wakeword",
        }:
            return "STANDARD"

        if requested in {
            "2",
            "continuous",
            "conversation",
            "open",
            "session",
        }:
            return "CONTINUOUS"

        print(
            Fore.YELLOW
            + (
                f"[BX1] Unknown ROBOT conversation mode "
                f"'{sys.argv[2]}'. Showing menu instead."
            )
            + Style.RESET_ALL
        )

    print()
    print("====================================================")
    print(" ROBOT CONVERSATION MODE")
    print("====================================================")
    print()
    print("  1 - WAKE WORD / STANDARD")
    print("      Use the existing TranscriptProcessor session behaviour.")
    print()
    print("  2 - CONTINUOUS CONVERSATION")
    print("      Say a wake word once to start.")
    print("      Continue speaking without repeating the wake word.")
    print("      The session stays open until an end phrase is heard.")
    print()

    end_phrases = _configured_end_phrases()

    if end_phrases:
        print(
            "      End phrases: "
            + ", ".join(
                f'"{phrase}"'
                for phrase in end_phrases
            )
        )
        print()

    while True:
        try:
            choice = input(
                Fore.GREEN
                + Style.BRIGHT
                + "CONVERSATION > "
                + Style.RESET_ALL
            )
        except EOFError:
            return "STANDARD"

        choice = choice.strip().lower()

        if choice in {
            "1",
            "standard",
            "normal",
            "wake",
            "wake-word",
            "wakeword",
        }:
            return "STANDARD"

        if choice in {
            "2",
            "continuous",
            "conversation",
            "open",
            "session",
        }:
            return "CONTINUOUS"

        print(
            Fore.YELLOW
            + "Please enter 1 for STANDARD or 2 for CONTINUOUS."
            + Style.RESET_ALL
        )


# ============================================================
# ROBOT MODE - AUDIO SEGMENTATION WORKER
# ============================================================

async def segmentation_worker(
    incoming,
    segmenter,
    utterance_queue,
):
    """Receive robot PCM, run VAD, and queue complete utterances."""

    import numpy as np

    diagnostic_start = time.monotonic()

    total_bytes = 0
    total_blocks = 0
    total_samples = 0

    sum_squares = 0.0
    maximum_peak = 0

    while True:
        pcm_block = await incoming.audio_queue.get()

        total_bytes += len(pcm_block)
        total_blocks += 1

        samples = np.frombuffer(
            pcm_block,
            dtype="<i2",
        )

        if samples.size:
            samples_float = samples.astype(
                np.float64
            )

            samples_int = samples.astype(
                np.int32
            )

            sum_squares += float(
                np.sum(
                    samples_float
                    * samples_float
                )
            )

            total_samples += samples.size

            block_peak = int(
                np.max(
                    np.abs(samples_int)
                )
            )

            maximum_peak = max(
                maximum_peak,
                block_peak,
            )

        now = time.monotonic()
        elapsed = now - diagnostic_start

        if elapsed >= 1.0:
            # Retain the diagnostics from main.py but leave their
            # continuous printout disabled exactly as before.
            if total_samples > 0:
                rms = math.sqrt(
                    sum_squares
                    / total_samples
                )

                if rms > 0:
                    rms_dbfs = (
                        20.0
                        * math.log10(
                            rms / 32768.0
                        )
                    )
                else:
                    rms_dbfs = -100.0

                if maximum_peak > 0:
                    peak_dbfs = (
                        20.0
                        * math.log10(
                            maximum_peak / 32768.0
                        )
                    )
                else:
                    peak_dbfs = -100.0
            else:
                rms_dbfs = -100.0
                peak_dbfs = -100.0

            bytes_per_second = (
                total_bytes / elapsed
            )

            # Uncomment for live microphone diagnostics:
            # print(
            #     Fore.CYAN
            #     + (
            #         f"[AUDIO] {bytes_per_second / 1024:5.1f} kB/s | "
            #         f"{total_blocks:3d} blocks/s | "
            #         f"RMS {rms_dbfs:6.1f} dBFS | "
            #         f"PEAK {peak_dbfs:6.1f} dBFS"
            #     )
            #     + Style.RESET_ALL
            # )

            # Keep these calculated variables explicitly used so
            # diagnostic code remains easy to re-enable.
            _ = (
                bytes_per_second,
                total_blocks,
                rms_dbfs,
                peak_dbfs,
            )

            diagnostic_start = now

            total_bytes = 0
            total_blocks = 0
            total_samples = 0

            sum_squares = 0.0
            maximum_peak = 0

        completed = segmenter.feed(
            pcm_block
        )

        for utterance in completed:
            print(
                Fore.YELLOW
                + (
                    f"[VAD] Completed utterance: "
                    f"{len(utterance)} bytes"
                )
                + Style.RESET_ALL
            )

            if utterance_queue.full():
                try:
                    utterance_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

            await utterance_queue.put(
                utterance
            )


# ============================================================
# ROBOT MODE - STT / LLM / TTS WORKER
# ============================================================

async def transcription_worker(
    utterance_queue,
    stt,
    transcript,
    llm,
    tts,
    audio_bridge,
    conversation_mode="STANDARD",
):
    """Robot conversation pipeline from utterance to spoken reply."""

    conversation_mode = str(
        conversation_mode
        or "STANDARD"
    ).upper()

    continuous_mode = (
        conversation_mode
        == "CONTINUOUS"
    )

    # Master_Main owns this latch only in CONTINUOUS mode.
    # STANDARD mode continues to use TranscriptProcessor exactly
    # as it did before this feature was added.
    conversation_active = False

    while True:
        utterance = await utterance_queue.get()

        print(
            Fore.MAGENTA
            + "[STT] Sending utterance to Whisper..."
            + Style.RESET_ALL
        )

        audio_bridge.play_sound_effect_async(
            "stt_started"
        )

        result = await asyncio.to_thread(
            stt.transcribe,
            utterance,
        )

        if not result.text:
            print(
                Fore.MAGENTA
                + "[STT] No speech recognised."
                + Style.RESET_ALL
            )

            continue

        event = transcript.process(
            result.text
        )

        transcript.print_event(
            event,
            result,
        )

        wake_detected = _event_indicates_wake(
            event,
            result.text,
        )

        if wake_detected:
            audio_bridge.play_sound_effect_async(
                "wake_detected"
            )

        # ====================================================
        # STANDARD MODE
        # ====================================================
        #
        # Preserve the existing behaviour completely.
        #
        # ====================================================

        if not continuous_mode:
            if (
                event.send_to_llm
                and llm.enabled
            ):
                print(
                    Fore.GREEN
                    + "    -> Sending to LLM..."
                    + Style.RESET_ALL
                )

                await asyncio.to_thread(
                    process_llm_request,
                    event.command_text,
                    llm,
                    tts,
                    audio_bridge,
                )

            continue

        # ====================================================
        # CONTINUOUS CONVERSATION MODE
        # ====================================================
        #
        # A wake phrase opens the Master_Main conversation latch.
        # It remains open until config.END_PHRASES is heard.
        #
        # No inactivity timeout is applied here. That is the main
        # difference from the standard TranscriptProcessor policy.
        #
        # ====================================================

        if wake_detected and not conversation_active:
            conversation_active = True

            print(
                Fore.CYAN
                + (
                    "[CONVERSATION] OPEN - "
                    "wake word accepted. "
                    "Wake word is no longer required."
                )
                + Style.RESET_ALL
            )

        # End phrases only close a session after it has been opened.
        if (
            conversation_active
            and _text_indicates_conversation_end(
                result.text
            )
        ):
            conversation_active = False

            print(
                Fore.CYAN
                + (
                    "[CONVERSATION] CLOSED - "
                    "end phrase detected. "
                    "Wake word is required again."
                )
                + Style.RESET_ALL
            )

            # Do not send the end phrase to the LLM.
            continue

        # Ignore ordinary room speech until LEO has been explicitly
        # woken at least once.
        if not conversation_active:
            continue

        # Prefer TranscriptProcessor's cleaned command when it has
        # accepted the utterance. If its timed session has expired,
        # use the raw STT text because Master_Main's continuous latch
        # deliberately remains active.
        if (
            event.send_to_llm
            and str(
                event.command_text
                or ""
            ).strip()
        ):
            command_text = str(
                event.command_text
            ).strip()

        else:
            command_text = _strip_wake_prefix(
                result.text
            )

        # A bare wake word opens the session but contains no command.
        if not command_text:
            continue

        if not llm.enabled:
            continue

        print(
            Fore.GREEN
            + "    -> Sending to LLM [CONTINUOUS SESSION]..."
            + Style.RESET_ALL
        )

        await asyncio.to_thread(
            process_llm_request,
            command_text,
            llm,
            tts,
            audio_bridge,
        )


# ============================================================
# ROBOT MODE
# ============================================================

async def run_robot_mode(
    conversation_mode="STANDARD",
):
    """
    Robot microphone -> VAD -> Whisper -> TranscriptProcessor ->
    LLM -> Qwen -> AudioToRobotStreamer.
    """

    # Robot-only imports prevent LOCAL mode from needing to bring
    # up the robot communications stack.
    from incoming_audio import IncomingAudioServer
    from speech_segmenter import SpeechSegmenter
    from stt_engine import STTEngine
    from transcript_processor import TranscriptProcessor
    from audio_to_robot_streamer import AudioToRobotStreamer

    print()
    print("====================================================")
    print(" BX1 MASTER - ROBOT MODE")
    print("====================================================")
    print()
    print("Microphone input : ROBOT")
    print("Whisper / STT    : ENABLED")
    print(
        "Wake/session     : "
        + (
            "CONTINUOUS until END_PHRASE"
            if str(conversation_mode).upper() == "CONTINUOUS"
            else "STANDARD / transcript_processor.py"
        )
    )
    print("Speech generator : tts_engine.py / Qwen")
    print("Audio bridge     : Master_Main.py")
    print("Sound events     : sound_effects.py")
    print("Playback         : audio_to_robot_streamer.py -> robot")
    print()

    incoming = IncomingAudioServer()
    segmenter = SpeechSegmenter()
    stt = STTEngine()
    transcript = TranscriptProcessor()
    llm = LLMClient()
    sound_library = SoundEffectLibrary()

    robot_audio = AudioToRobotStreamer()
    robot_audio.start()

    audio_bridge = MasterAudioBridge(
        audio_output=robot_audio,
        sound_library=sound_library,
        mode_name="ROBOT",
    )

    tts = QwenTTSEngine(
        audio_bridge
    )

    utterance_queue = asyncio.Queue(
        maxsize=10
    )

    server = None
    segment_task = None
    transcription_task = None

    try:
        server = await incoming.start()

        segment_task = asyncio.create_task(
            segmentation_worker(
                incoming,
                segmenter,
                utterance_queue,
            )
        )

        transcription_task = asyncio.create_task(
            transcription_worker(
                utterance_queue,
                stt,
                transcript,
                llm,
                tts,
                audio_bridge,
                conversation_mode,
            )
        )

        print()
        print("[BX1] Robot voice pipeline ready.")

        print(
            "[BX1] LLM is "
            + ("ENABLED" if llm.enabled else "DISABLED")
        )

        print(
            "[BX1] TTS is "
            + ("ENABLED" if tts.enabled else "DISABLED")
        )

        print(
            "[BX1] Sound effects are "
            + (
                "ENABLED"
                if sound_library.enabled
                else "DISABLED"
            )
        )

        print(
            "[BX1] Conversation mode: "
            + str(conversation_mode).upper()
        )

        if str(conversation_mode).upper() == "CONTINUOUS":
            print(
                "[BX1] Say a wake word once, then speak naturally "
                "until an END_PHRASE closes the session."
            )

        print()
        print("[BX1] Waiting for live microphone audio...")
        print()

        await asyncio.gather(
            server.wait_closed(),
            segment_task,
            transcription_task,
        )

    finally:
        print()
        print("[BX1] Shutting down ROBOT mode...")

        audio_bridge.close()

        if segment_task is not None:
            segment_task.cancel()

        if transcription_task is not None:
            transcription_task.cancel()

        robot_audio.stop()

        tts.close()

        if (
            tts.worker_thread is not None
            and tts.worker_thread.is_alive()
        ):
            tts.worker_thread.join(
                timeout=2.0
            )

        if server is not None:
            server.close()
            await server.wait_closed()


# ============================================================
# MASTER MODE SELECTION
# ============================================================

def select_mode():
    """Return LOCAL or ROBOT from command line or interactive menu."""

    # Optional command-line shortcut:
    #
    #     python Master_Main.py local
    #     python Master_Main.py robot

    if len(sys.argv) >= 2:
        requested = sys.argv[1].strip().lower()

        if requested in {
            "1",
            "local",
            "pc",
        }:
            return "LOCAL"

        if requested in {
            "2",
            "robot",
            "remote",
        }:
            return "ROBOT"

        print(
            Fore.YELLOW
            + (
                f"[BX1] Unknown mode '{sys.argv[1]}'. "
                "Showing mode menu instead."
            )
            + Style.RESET_ALL
        )

    print()
    print("====================================================")
    print(" BX1 MASTER MAIN")
    print("====================================================")
    print()
    print("Select operating mode:")
    print()
    print("  1 - LOCAL")
    print("      Keyboard input and PC speaker output")
    print()
    print("  2 - ROBOT")
    print("      Robot microphone input and robot speaker output")
    print()

    while True:
        try:
            choice = input(
                Fore.GREEN
                + Style.BRIGHT
                + "MODE > "
                + Style.RESET_ALL
            )
        except EOFError:
            return None

        choice = choice.strip().lower()

        if choice in {
            "1",
            "local",
            "pc",
        }:
            return "LOCAL"

        if choice in {
            "2",
            "robot",
            "remote",
        }:
            return "ROBOT"

        if choice in {
            "/exit",
            "/quit",
            "exit",
            "quit",
            "q",
        }:
            return None

        print(
            Fore.YELLOW
            + "Please enter 1 for LOCAL or 2 for ROBOT."
            + Style.RESET_ALL
        )


# ============================================================
# ENTRY POINT
# ============================================================

def master_main():
    mode = select_mode()

    if mode is None:
        print("BX1 Master stopped.")
        return

    if mode == "LOCAL":
        run_local_mode()
        return

    if mode == "ROBOT":
        conversation_mode = (
            select_robot_conversation_mode()
        )

        asyncio.run(
            run_robot_mode(
                conversation_mode=conversation_mode,
            )
        )
        return


if __name__ == "__main__":
    try:
        master_main()

    except KeyboardInterrupt:
        print()
        print("BX1 Master stopped.")