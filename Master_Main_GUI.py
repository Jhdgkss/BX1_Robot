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
import queue
import re
import sys
import threading
import time

from settings import config
from settings.personality_manager import PersonalityManager

from colorama import Fore, Back, Style

from llm_client import LLMClient
from tts_engine import QwenTTSEngine
from sound_effects import SoundEffectLibrary
from Conversation.conversation_session import ContinuousConversationSession


_MASTER_PERSONALITY = PersonalityManager()
config.ROBOT_DISPLAY_NAME = _MASTER_PERSONALITY.get_name()


def current_robot_name():
    return str(
        getattr(config, "ROBOT_DISPLAY_NAME", "LEO")
        or "LEO"
    ).strip()


def refresh_llm_personality(llm):
    """
    Reload settings/personality.json and refresh the active LLM prompt.
    """
    _MASTER_PERSONALITY.load()
    config.ROBOT_DISPLAY_NAME = _MASTER_PERSONALITY.get_name()

    llm_personality = getattr(llm, "personality", None)

    if llm_personality is not None:
        loader = getattr(llm_personality, "load", None)
        if callable(loader):
            loader()

    refresh = getattr(llm, "_refresh_system_prompt", None)

    if callable(refresh):
        refresh()
        return True

    return False


# ============================================================
# BRAIN-SIDE LED TASK ENGINE
# ============================================================
#
# The task engine lives on the Brain PC and only uses bx1.robot.v1
# commands.  It never touches GPIO or the Arduino Bridge directly.
# ============================================================

_LED_TASK_ENGINE = None


def set_led_task_engine(engine):
    global _LED_TASK_ENGINE
    _LED_TASK_ENGINE = engine


def run_led_task(task_name):
    engine = _LED_TASK_ENGINE
    if engine is not None:
        engine.trigger(task_name)


def end_led_exclusive(base_task="listening"):
    engine = _LED_TASK_ENGINE
    if engine is not None:
        engine.end_exclusive(base_task=base_task)


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
        gui_controller=None,
    ):
        self.audio_output = audio_output
        self.sound_library = sound_library
        self.mode_name = str(mode_name).upper()
        self.gui_controller = gui_controller
        self.active_message_id = None

        # Only one audio item may own the selected output at once.
        self._audio_session_lock = threading.Lock()

        self._tts_session_active = False

        self._waiting_timer = None
        self._waiting_timer_lock = threading.RLock()


    def set_active_message_id(
        self,
        message_id,
    ):
        self.active_message_id = message_id


    # ========================================================
    # TTS AUDIO
    # ========================================================

    def start_tts(
        self,
        sample_rate=24000,
    ):
        """Called by tts_engine.py when generated speech starts."""

        self.cancel_llm_waiting_timer()

        if self.mode_name == "ROBOT":
            run_led_task("speaking")

        if (
            self.gui_controller is not None
            and self.active_message_id is not None
        ):
            self.gui_controller.publish_event(
                "audio_generation_completed",
                source="TTS",
                message_id=self.active_message_id,
            )
            self.gui_controller.publish_event(
                "audio_playback_started",
                source="AUDIO",
                message_id=self.active_message_id,
            )

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

                if self.mode_name == "ROBOT":
                    end_led_exclusive("listening")

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
            if (
                self.gui_controller is not None
                and self.active_message_id is not None
            ):
                self.gui_controller.publish_event(
                    "audio_playback_completed",
                    source="AUDIO",
                    message_id=self.active_message_id,
                )

            self.active_message_id = None
            self._tts_session_active = False

            if self.mode_name == "ROBOT":
                end_led_exclusive("listening")

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
        + f" {current_robot_name()} "
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
    gui_controller=None,
    user_message_id=None,
):
    """Send text to the LLM and speak the returned response.

    When gui_controller is supplied, Master_Main_GUI.py also publishes
    lifecycle events and reply timing data to the GUI.
    """

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

        run_led_task("error")

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

        reply_message_id = None

        if gui_controller is not None:
            reply_message_id = gui_controller.new_message_id()

        run_led_task("thinking")

        llm_started = time.perf_counter()

        if gui_controller is not None:
            gui_controller.publish_event(
                "llm_started",
                source="LLM",
                message_id=reply_message_id,
                data={"text": str(user_text), "user_message_id": user_message_id},
            )

        reply = llm.ask(
            user_text
        )

        llm_ms = (time.perf_counter() - llm_started) * 1000.0

        if gui_controller is not None:
            gui_controller.publish_event(
                "llm_completed",
                source="LLM",
                message_id=reply_message_id,
                data={"duration_ms": round(llm_ms, 1), "user_message_id": user_message_id},
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
            run_led_task("error")

            return False

        audio_bridge.play_sound_effect_async(
            "llm_response_received"
        )

        print_leo_reply(
            reply
        )

        if gui_controller is not None:
            gui_controller.publish_leo_message(
                reply,
                message_id=reply_message_id,
            )

        tts_ms = 0.0

        if tts.enabled:
            audio_bridge.set_active_message_id(
                reply_message_id
            )

            speech_reply = prepare_text_for_tts(
                reply
            )

            if not speech_reply:
                speech_reply = str(reply).strip()

            if gui_controller is not None:
                gui_controller.publish_event(
                    "tts_started",
                    source="TTS",
                    message_id=reply_message_id,
                )

            tts_started = time.perf_counter()

            tts.speak(
                speech_reply
            )

            # Qwen works on its own worker thread. Waiting here
            # keeps one conversational request orderly while the
            # audio bridge still cancels the waiting cue at the
            # point actual TTS audio begins.
            tts.speech_queue.join()

            tts_ms = (time.perf_counter() - tts_started) * 1000.0

            if gui_controller is not None:
                gui_controller.publish_event(
                    "tts_completed",
                    source="TTS",
                    message_id=reply_message_id,
                    data={"duration_ms": round(tts_ms, 1)},
                )

            request_has_speech_pending = False

        else:
            audio_bridge.set_active_message_id(
                None
            )
            audio_bridge.cancel_llm_waiting_timer()
            request_has_speech_pending = False

        if gui_controller is not None and reply_message_id is not None:
            gui_controller.publish_reply_metrics(
                reply_message_id,
                {
                    "user_message_id": user_message_id,
                    "llm_ms": round(llm_ms, 1),
                    "tts_ms": round(tts_ms, 1),
                    "mode": gui_controller.mode,
                },
            )

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
        run_led_task("error")

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
# GUI LOCAL MODE
# ============================================================

def run_local_gui_mode(
    gui_controller,
    command_queue,
    stop_event,
):
    """LOCAL mode using GUI input instead of blocking console input()."""
    from pc_audio import PCAudioOutput

    gui_controller.set_mode("LOCAL")
    gui_controller.set_robot_connection(False, current_robot_name())

    print()
    print("====================================================")
    print(" BX1 MASTER GUI - OFFLINE / LOCAL MODE")
    print("====================================================")
    print()
    print("Microphone input : DISABLED")
    print("Whisper / STT    : DISABLED")
    print("Robot audio link : DISABLED")
    print("Input            : GUI")
    print("Speech generator : tts_engine.py / Qwen")
    print("Audio bridge     : Master_Main_GUI.py")
    print("Sound events     : sound_effects.py")
    print("Playback         : pc_audio.py -> PC speakers")
    print()

    gui_controller.publish_event(
        "local_initialising",
        source="MASTER",
    )

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

    gui_controller.publish_tts_settings(
        tts.get_settings()
    )

    gui_controller.publish_event(
        "local_ready",
        source="MASTER",
        data={
            "llm_enabled": bool(llm.enabled),
            "tts_enabled": bool(tts.enabled),
            "sound_effects_enabled": bool(sound_library.enabled),
        },
    )

    try:
        while not stop_event.is_set():
            try:
                command = command_queue.get(timeout=0.20)
            except queue.Empty:
                continue

            if command is None:
                continue

            if command.name == "personality_changed":
                refreshed = refresh_llm_personality(llm)

                gui_controller.publish_event(
                    "personality_updated",
                    source="MASTER",
                    data={
                        "name": current_robot_name(),
                        "llm_prompt_refreshed": bool(refreshed),
                    },
                )
                continue

            if command.name == "tts_apply_settings":
                try:
                    updated = tts.apply_settings(
                        command.data.get("settings", {})
                    )
                    gui_controller.publish_tts_settings(updated)
                    gui_controller.publish_event(
                        "tts_settings_applied",
                        source="TTS",
                        data={
                            "model_name": updated.get("model_name"),
                            "reference_audio": updated.get("reference_audio"),
                            "x_vector_only_mode": updated.get("x_vector_only_mode"),
                        },
                    )
                except Exception as exc:
                    gui_controller.publish_event(
                        "tts_settings_error",
                        source="TTS",
                        data={
                            "error": f"{type(exc).__name__}: {exc}"
                        },
                    )
                continue

            if command.name == "tts_test_voice":
                test_text = str(
                    command.data.get("text", "")
                ).strip()
                if test_text and tts.enabled:
                    try:
                        tts.speak(test_text)
                        tts.speech_queue.join()
                        gui_controller.publish_event(
                            "tts_test_completed",
                            source="TTS",
                        )
                    except Exception as exc:
                        gui_controller.publish_event(
                            "tts_test_error",
                            source="TTS",
                            data={
                                "error": f"{type(exc).__name__}: {exc}"
                            },
                        )
                continue

            if command.name != "user_message":
                continue

            user_text = str(
                command.data.get("text", "")
            ).strip()

            if not user_text:
                continue

            message_id = gui_controller.publish_user_message(
                user_text
            )

            process_llm_request(
                user_text=user_text,
                llm=llm,
                tts=tts,
                audio_bridge=audio_bridge,
                gui_controller=gui_controller,
                user_message_id=message_id,
            )

    finally:
        gui_controller.publish_event(
            "local_stopping",
            source="MASTER",
        )

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
    gui_controller=None,
    request_lock=None,
):
    """Robot conversation pipeline from utterance to spoken reply.

    Classification is performed before a transcript is published to the GUI.
    Speech not addressed to LEO is published as BACKGROUND and is never sent
    to the LLM.
    """

    conversation_mode = str(
        conversation_mode
        or "STANDARD"
    ).upper()

    continuous_mode = (
        conversation_mode
        == "CONTINUOUS"
    )

    continuous_session = ContinuousConversationSession(
        wake_words=getattr(config, "WAKE_WORDS", ()),
        end_phrases=getattr(config, "END_PHRASES", ()),
    )

    async def send_request(
        command_text,
        message_id,
        console_label,
    ):
        command_text = str(
            command_text
            or ""
        ).strip()

        if not command_text or not llm.enabled:
            return

        print(
            Fore.GREEN
            + console_label
            + Style.RESET_ALL
        )

        if request_lock is not None:
            async with request_lock:
                await asyncio.to_thread(
                    process_llm_request,
                    command_text,
                    llm,
                    tts,
                    audio_bridge,
                    gui_controller,
                    message_id,
                )
        else:
            await asyncio.to_thread(
                process_llm_request,
                command_text,
                llm,
                tts,
                audio_bridge,
                gui_controller,
                message_id,
            )

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

        raw_text = str(
            result.text
            or ""
        ).strip()

        if not raw_text:
            print(
                Fore.MAGENTA
                + "[STT] No speech recognised."
                + Style.RESET_ALL
            )
            continue

        event = transcript.process(
            raw_text
        )

        transcript.print_event(
            event,
            result,
        )

        wake_detected = _event_indicates_wake(
            event,
            raw_text,
        )

        if wake_detected:
            audio_bridge.play_sound_effect_async(
                "wake_detected"
            )
            run_led_task("listening")

        # ====================================================
        # STANDARD MODE
        # ====================================================

        if not continuous_mode:
            command_text = str(
                event.command_text
                or ""
            ).strip()

            accepted = bool(
                event.send_to_llm
                and command_text
            )

            # A bare wake word is still addressed to LEO even when
            # TranscriptProcessor has no command to send yet.
            addressed = bool(
                wake_detected
                or event.send_to_llm
            )

            message_id = None

            if gui_controller is not None:
                if addressed:
                    message_id = (
                        gui_controller.publish_user_message(
                            raw_text
                        )
                    )
                else:
                    message_id = (
                        gui_controller.publish_background_message(
                            raw_text
                        )
                    )

                gui_controller.publish_event(
                    "stt_completed",
                    source="STT",
                    message_id=message_id,
                    data={
                        "text": raw_text,
                        "classification": (
                            "user"
                            if addressed
                            else "background"
                        ),
                        "send_to_llm": accepted,
                        "conversation_mode": "STANDARD",
                    },
                )

            if accepted:
                await send_request(
                    command_text,
                    message_id,
                    "    -> Sending to LLM...",
                )

            continue

        # ====================================================
        # CONTINUOUS MODE
        # ====================================================
        #
        # This state machine is deliberately independent of
        # TranscriptProcessor's timed standard session. Once woken, the
        # conversation remains open until a configured END_PHRASE.
        # ====================================================

        preferred_command = ""

        if (
            event.send_to_llm
            and str(
                event.command_text
                or ""
            ).strip()
        ):
            preferred_command = str(
                event.command_text
            ).strip()

        decision = continuous_session.process(
            raw_text,
            wake_detected=wake_detected,
            preferred_command=preferred_command,
        )

        if decision.session_opened:
            print(
                Fore.CYAN
                + (
                    "[CONVERSATION] OPEN - wake word accepted; "
                    "no further wake word required."
                )
                + Style.RESET_ALL
            )

        if decision.session_closed:
            print(
                Fore.CYAN
                + (
                    "[CONVERSATION] CLOSED - end phrase detected; "
                    "wake word required again."
                )
                + Style.RESET_ALL
            )
            run_led_task("idle")

        message_id = None

        if gui_controller is not None:
            if decision.kind == "background":
                message_id = (
                    gui_controller.publish_background_message(
                        decision.display_text
                    )
                )
            else:
                message_id = (
                    gui_controller.publish_user_message(
                        decision.display_text
                    )
                )

            gui_controller.publish_event(
                "stt_completed",
                source="STT",
                message_id=message_id,
                data={
                    "text": decision.display_text,
                    "classification": decision.kind,
                    "send_to_llm": bool(
                        decision.send_to_llm
                    ),
                    "conversation_active": bool(
                        decision.session_active
                    ),
                    "conversation_mode": "CONTINUOUS",
                },
            )

        if decision.send_to_llm:
            await send_request(
                decision.command_text,
                message_id,
                "    -> Sending to LLM [CONTINUOUS SESSION]...",
            )


# ============================================================
# ONLINE GUI CHAT WORKER
# ============================================================

async def online_gui_chat_worker(
    command_queue,
    gui_controller,
    llm,
    tts,
    audio_bridge,
    request_lock,
    vision_processor=None,
    head_controller=None,
    robot_api=None,
):
    """
    Allow typed GUI chat while ROBOT mode continues listening to the
    robot microphone.

    Typed and spoken requests share the same LLM/TTS path. A request lock
    prevents two replies from being generated at the same time.
    """

    while True:
        command = await asyncio.to_thread(
            command_queue.get
        )

        if command is None:
            return

        if command.name == "personality_changed":
            refreshed = refresh_llm_personality(llm)

            gui_controller.publish_event(
                "personality_updated",
                source="MASTER",
                data={
                    "name": current_robot_name(),
                    "llm_prompt_refreshed": bool(refreshed),
                },
            )
            continue

        if command.name == "tts_apply_settings":
            try:
                async with request_lock:
                    updated = await asyncio.to_thread(
                        tts.apply_settings,
                        command.data.get("settings", {}),
                    )

                gui_controller.publish_tts_settings(updated)
                gui_controller.publish_event(
                    "tts_settings_applied",
                    source="TTS",
                    data={
                        "model_name": updated.get("model_name"),
                        "reference_audio": updated.get("reference_audio"),
                        "x_vector_only_mode": updated.get("x_vector_only_mode"),
                    },
                )
            except Exception as exc:
                gui_controller.publish_event(
                    "tts_settings_error",
                    source="TTS",
                    data={
                        "error": f"{type(exc).__name__}: {exc}"
                    },
                )
            continue

        if command.name == "tts_test_voice":
            test_text = str(
                command.data.get("text", "")
            ).strip()

            if test_text and tts.enabled:
                try:
                    async with request_lock:
                        tts.speak(test_text)
                        await asyncio.to_thread(
                            tts.speech_queue.join
                        )

                    gui_controller.publish_event(
                        "tts_test_completed",
                        source="TTS",
                    )
                except Exception as exc:
                    gui_controller.publish_event(
                        "tts_test_error",
                        source="TTS",
                        data={
                            "error": f"{type(exc).__name__}: {exc}"
                        },
                    )
            continue

        if command.name == "vision_enable":
            if vision_processor is not None:
                vision_processor.set_enabled(True)
            continue

        if command.name == "vision_disable":
            if vision_processor is not None:
                vision_processor.set_enabled(False)
            continue

        if command.name == "head_move":
            if head_controller is not None:
                await head_controller.move(
                    pan_delta=float(command.data.get("pan_delta", 0.0)),
                    pitch_delta=float(command.data.get("pitch_delta", 0.0)),
                    roll_delta=float(command.data.get("roll_delta", 0.0)),
                )
            continue

        if command.name == "head_center":
            if head_controller is not None:
                await head_controller.center()
            continue

        if command.name == "head_set":
            if head_controller is not None:
                await head_controller.set_pose(
                    pan=float(command.data.get("pan", 0.0)),
                    pitch=float(command.data.get("pitch", 0.0)),
                    roll=float(command.data.get("roll", 0.0)),
                )
            continue

        if command.name == "head_state_request":
            if head_controller is not None:
                await head_controller.request_state()
            continue

        # ====================================================
        # BALANCE / MOVEMENT COMMANDS
        # ====================================================
        #
        # The GUI never talks to the robot directly.  All balance tuning,
        # calibration and movement requests are routed through this master
        # orchestration layer and the unified Robot API.  The MCU remains the
        # final authority and rejects unsafe changes while balance is armed.
        # ====================================================

        balance_commands = {
            "balance_arm": ("balance.arm", {}),
            "balance_disarm": ("balance.disarm", {}),
            "balance_status_request": ("balance.status", {}),
            "balance_zero": ("balance.zero", {}),
            "balance_gyrozero": ("balance.gyrozero", {}),
            "balance_clear_fault": ("balance.clear_fault", {}),
            "balance_get_parameters": ("balance.get_parameters", {}),
            "balance_save_parameters": ("balance.save_parameters", {}),
            "balance_load_saved_parameters": ("balance.load_saved_parameters", {}),
            "balance_restore_defaults": (
                "balance.restore_config_defaults",
                {"save": bool(command.data.get("save", False))},
            ),
        }

        if command.name == "balance_set_parameter":
            balance_commands[command.name] = (
                "balance.set_parameter",
                {
                    "parameter": str(command.data.get("parameter", "")),
                    "value": command.data.get("value"),
                    "save": bool(command.data.get("save", False)),
                },
            )

        elif command.name == "balance_set_parameters":
            balance_commands[command.name] = (
                "balance.set_parameters",
                {
                    "values": dict(command.data.get("values") or {}),
                    "save": bool(command.data.get("save", False)),
                },
            )

        if command.name in balance_commands:
            api_name, api_params = balance_commands[command.name]

            try:
                if robot_api is None:
                    raise ConnectionError("Robot API is not available")

                response = await robot_api.send_command(
                    api_name,
                    api_params,
                    timeout=(8.0 if api_name == "balance.gyrozero" else 6.0),
                )

                gui_controller.publish_event(
                    "balance_command_result",
                    source="ROBOT_API",
                    data={
                        "command": api_name,
                        "ok": True,
                        "response": response,
                    },
                )

            except Exception as exc:
                gui_controller.publish_event(
                    "balance_command_result",
                    source="ROBOT_API",
                    data={
                        "command": api_name,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )

                print(
                    Fore.RED
                    + f"[ROBOT API] {api_name} failed: {type(exc).__name__}: {exc}"
                    + Style.RESET_ALL
                )

            continue

        drive_commands = {
            "drive_forward": (
                "drive.forward",
                ({"percent": float(command.data["percent"])} if command.data.get("percent") is not None else {}),
            ),
            "drive_reverse": (
                "drive.reverse",
                ({"percent": float(command.data["percent"])} if command.data.get("percent") is not None else {}),
            ),
            "drive_left": (
                "drive.left",
                ({"percent": float(command.data["percent"])} if command.data.get("percent") is not None else {}),
            ),
            "drive_right": (
                "drive.right",
                ({"percent": float(command.data["percent"])} if command.data.get("percent") is not None else {}),
            ),
            "drive_hold": ("drive.hold", {}),
            "drive_stop": ("drive.stop", {}),
            "drive_estop": ("drive.estop", {}),
            "drive_status_request": ("drive.status", {}),
        }

        if command.name == "drive_set_motion":
            drive_commands[command.name] = (
                "drive.set_motion",
                {
                    "forward_percent": float(command.data.get("forward_percent", 0.0)),
                    "turn_percent": float(command.data.get("turn_percent", 0.0)),
                },
            )

        if command.name in drive_commands:
            api_name, api_params = drive_commands[command.name]

            try:
                if robot_api is None:
                    raise ConnectionError("Robot API is not available")

                response = await robot_api.send_command(
                    api_name,
                    api_params,
                    timeout=4.0 if api_name in {"drive.stop", "drive.estop"} else 2.0,
                )

                gui_controller.publish_event(
                    "drive_command_result",
                    source="ROBOT_API",
                    data={
                        "command": api_name,
                        "ok": True,
                        "response": response,
                    },
                )

            except Exception as exc:
                gui_controller.publish_event(
                    "drive_command_result",
                    source="ROBOT_API",
                    data={
                        "command": api_name,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )

                print(
                    Fore.RED
                    + f"[ROBOT API] {api_name} failed: {type(exc).__name__}: {exc}"
                    + Style.RESET_ALL
                )

            continue

        # ====================================================
        # DISARMED MOTOR BENCH / ANALYSIS RECORDING
        # ====================================================

        motor_test_commands = {
            "motor_bench_status_request": ("motor.test_status", {}),
            "motor_bench_stop": ("motor.test_stop", {}),
        }

        if command.name == "motor_bench_prepare":
            motor_test_commands[command.name] = (
                "motor.test_prepare",
                {"motor": str(command.data.get("motor", ""))},
            )

        if command.name == "motor_bench_jog":
            motor_test_commands[command.name] = (
                "motor.test_jog",
                {
                    "motor": str(command.data.get("motor", "")),
                    "rpm": int(command.data.get("rpm", 0)),
                    "duration_ms": int(command.data.get("duration_ms", 400)),
                },
            )

        elif command.name == "motor_bench_run":
            motor_test_commands[command.name] = (
                "motor.test_run",
                {
                    "motor": str(command.data.get("motor", "")),
                    "rpm": int(command.data.get("rpm", 0)),
                    "duration_ms": int(command.data.get("duration_ms", 3000)),
                },
            )

        elif command.name == "motor_bench_reversal":
            motor_test_commands[command.name] = (
                "motor.test_reversal",
                {
                    "motor": str(command.data.get("motor", "")),
                    "rpm": int(command.data.get("rpm", 2)),
                    "run_ms": int(command.data.get("run_ms", 3000)),
                    "dwell_ms": int(command.data.get("dwell_ms", 500)),
                },
            )

        if command.name in motor_test_commands:
            api_name, api_params = motor_test_commands[command.name]
            try:
                if robot_api is None:
                    raise ConnectionError("Robot API is not available")
                response = await robot_api.send_command(
                    api_name,
                    api_params,
                    timeout=3.0,
                )
                gui_controller.publish_event(
                    "motor_test_command_result",
                    source="ROBOT_API",
                    data={
                        "command": api_name,
                        "ok": True,
                        "response": response,
                    },
                )
            except Exception as exc:
                gui_controller.publish_event(
                    "motor_test_command_result",
                    source="ROBOT_API",
                    data={
                        "command": api_name,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                print(
                    Fore.RED
                    + f"[ROBOT API] {api_name} failed: {type(exc).__name__}: {exc}"
                    + Style.RESET_ALL
                )
            continue

        if command.name in {
            "analysis_live_start",
            "analysis_live_stop",
            "analysis_recording_start",
            "analysis_recording_stop",
            "learning_live_start",
            "learning_live_stop",
        }:
            try:
                if robot_api is None:
                    raise ConnectionError("Robot API is not available")

                if command.name == "analysis_live_start":
                    # Hardware page visible: useful live plots without requiring
                    # the user to start a recording. MKS readback remains modest
                    # at 4 Hz and the robot suppresses those bus reads when armed.
                    response = await robot_api.send_command(
                        "telemetry.subscribe",
                        {
                            "subscriptions": [
                                {"topic": "balance.state", "interval_ms": 100},
                                {"topic": "motor.bench", "interval_ms": 250},
                            ]
                        },
                        timeout=3.0,
                    )

                elif command.name == "learning_live_start":
                    # Balance Learning uses the same 10 Hz balance stream but
                    # deliberately does not poll MKS readback while learning.
                    response = await robot_api.send_command(
                        "telemetry.subscribe",
                        {"subscriptions": [{"topic": "balance.state", "interval_ms": 100}]},
                        timeout=3.0,
                    )

                elif command.name == "analysis_recording_start":
                    # Recording uses 10 Hz balance and 10 Hz DISARMED motor
                    # readback. The robot itself blocks direct MKS polling while
                    # balance is armed, so measurement traffic cannot disturb the
                    # balancing wheel-command bus.
                    response = await robot_api.send_command(
                        "telemetry.subscribe",
                        {
                            "subscriptions": [
                                {"topic": "balance.state", "interval_ms": 100},
                                {"topic": "motor.bench", "interval_ms": 100},
                            ]
                        },
                        timeout=3.0,
                    )

                else:
                    # Leaving the Hardware page or ending a recording returns to
                    # the normal low-rate balance stream and removes MKS readback.
                    response = await robot_api.send_command(
                        "telemetry.subscribe",
                        {
                            "subscriptions": [
                                {"topic": "balance.state", "interval_ms": 500}
                            ]
                        },
                        timeout=3.0,
                    )
                    await robot_api.send_command(
                        "telemetry.unsubscribe",
                        {"topics": ["motor.bench"]},
                        timeout=3.0,
                    )

                gui_controller.publish_event(
                    "analysis_recording_result",
                    source="ROBOT_API",
                    data={
                        "command": command.name,
                        "ok": True,
                        "response": response,
                    },
                )
            except Exception as exc:
                gui_controller.publish_event(
                    "analysis_recording_result",
                    source="ROBOT_API",
                    data={
                        "command": command.name,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
            continue

        if command.name != "user_message":
            continue

        user_text = str(
            command.data.get(
                "text",
                "",
            )
        ).strip()

        if not user_text:
            continue

        message_id = gui_controller.publish_user_message(
            user_text
        )

        async with request_lock:
            await asyncio.to_thread(
                process_llm_request,
                user_text,
                llm,
                tts,
                audio_bridge,
                gui_controller,
                message_id,
            )


# ============================================================
# ROBOT MODE
# ============================================================

async def run_robot_mode(
    conversation_mode="STANDARD",
    gui_controller=None,
    gui_command_queue=None,
):
    """
    Robot microphone -> VAD -> Whisper -> TranscriptProcessor ->
    LLM -> Qwen -> AudioToRobotStreamer.
    """

    if gui_controller is not None:
        gui_controller.set_mode("ROBOT")
        gui_controller.set_robot_connection(True, current_robot_name())

    # Robot-only imports prevent LOCAL mode from needing to bring
    # up the robot communications stack.
    from incoming_audio import IncomingAudioServer
    from speech_segmenter import SpeechSegmenter
    from stt_engine import STTEngine
    from transcript_processor import TranscriptProcessor
    from audio_to_robot_streamer import AudioToRobotStreamer
    from Vision.incoming_video import IncomingVideoServer
    from Vision.vision_yolo import YOLOVisualProcessor
    from Vision import vision_config
    from Head_Control.head_servo_server import HeadServoServer
    from Robot_Control.robot_api_server import RobotAPIServer
    from LED_Control.led_task_engine import LEDTaskEngine
    from brain_api.server import BrainAPIServer
    from brain_modules.module_manager import BrainModuleManager

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
    print(
        "Video receiver   : "
        f"ws://{vision_config.VIDEO_HOST}:"
        f"{vision_config.VIDEO_PORT}"
    )
    print(
        "Vision processor : YOLO / "
        f"{vision_config.YOLO_MODEL}"
    )
    print("Head control     : ws://0.0.0.0:8773")
    print("Robot API        : ws://0.0.0.0:8774")
    print("Brain module API : ws://127.0.0.1:8775")
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
        gui_controller=gui_controller,
    )

    tts = QwenTTSEngine(
        audio_bridge
    )

    if gui_controller is not None:
        gui_controller.publish_tts_settings(
            tts.get_settings()
        )

    utterance_queue = asyncio.Queue(
        maxsize=10
    )

    request_lock = asyncio.Lock()

    def publish_vision_status(status):
        if gui_controller is not None:
            gui_controller.publish_vision_status(
                status
            )

        event_name = str(
            status.get(
                "event",
                "vision_status",
            )
        )

        if gui_controller is not None:
            gui_controller.publish_event(
                event_name,
                source="VISION",
                data=status,
            )

    def publish_vision_result(
        annotated_jpeg,
        result,
    ):
        if gui_controller is not None:
            gui_controller.publish_vision_result(
                annotated_jpeg,
                result,
            )

    vision_processor = YOLOVisualProcessor(
        model_name=vision_config.YOLO_MODEL,
        confidence=vision_config.YOLO_CONFIDENCE,
        iou=vision_config.YOLO_IOU,
        image_size=vision_config.YOLO_IMAGE_SIZE,
        max_fps=vision_config.YOLO_MAX_FPS,
        result_callback=publish_vision_result,
        status_callback=publish_vision_status,
    )

    vision_processor.set_enabled(
        bool(
            vision_config.YOLO_ENABLED
        )
    )
    vision_processor.start()

    def on_video_frame(
        jpeg_bytes,
        metadata,
    ):
        # MASTER owns both routes:
        #   1. raw frame -> GUI
        #   2. raw frame -> YOLO processor
        if gui_controller is not None:
            gui_controller.publish_video_frame(
                jpeg_bytes,
                metadata,
            )

        vision_processor.submit_frame(
            jpeg_bytes,
            metadata,
        )

    incoming_video = IncomingVideoServer(
        host=vision_config.VIDEO_HOST,
        port=vision_config.VIDEO_PORT,
        frame_callback=on_video_frame,
        status_callback=publish_vision_status,
        max_jpeg_bytes=vision_config.MAX_JPEG_BYTES,
    )

    def publish_head_state(state):
        if gui_controller is not None:
            gui_controller.publish_head_state(state)
            gui_controller.publish_telemetry({
                "head_pan_deg": state.get("pan", 0.0),
                "head_pitch_deg": state.get("pitch", 0.0),
                "head_roll_deg": state.get("roll", 0.0),
            })

    def publish_head_status(status):
        if gui_controller is not None:
            gui_controller.publish_head_status(status)
            gui_controller.publish_event(
                str(status.get("event", "head_status")),
                source="HEAD",
                data=status,
            )

    head_control = HeadServoServer(
        host="0.0.0.0",
        port=8773,
        state_callback=publish_head_state,
        status_callback=publish_head_status,
    )

    led_tasks = None

    # --------------------------------------------------------
    # UNIFIED ROBOT API / BALANCE TELEMETRY
    # --------------------------------------------------------
    #
    # The Robot connects outward to this PC server on port 8774.
    # Audio, video and head control retain their existing ports.
    # --------------------------------------------------------

    def publish_robot_api_telemetry(packet):
        packet = dict(packet or {})

        topic = str(
            packet.get(
                "topic",
                "",
            )
        )

        data = (
            packet.get("data")
            if isinstance(
                packet.get("data"),
                dict,
            )
            else {}
        )

        if led_tasks is not None and topic == "balance.state" and data:
            fault = data.get("fault", data.get("fault_code", 0))
            if isinstance(fault, dict):
                fault = fault.get("code", fault.get("fault", 0))

            if fault not in (None, 0, "0", "none", "None", ""):
                led_tasks.trigger("balance_fault")
            elif bool(data.get("armed", False)):
                led_tasks.trigger("balance_armed")
            else:
                led_tasks.trigger("balance_disarmed")

        if gui_controller is None:
            return

        gui_controller.publish_robot_api_telemetry(
            packet
        )

        if not data:
            return

        if topic == "balance.state":
            flattened = {
                "balance_" + str(key): value
                for key, value in data.items()
            }

        elif topic == "imu.state":
            flattened = {
                "imu_" + str(key): value
                for key, value in data.items()
            }

        elif topic == "system.health":
            flattened = {
                "system_" + str(key): value
                for key, value in data.items()
            }

        else:
            flattened = {
                str(key): value
                for key, value in data.items()
            }

        gui_controller.publish_telemetry(
            flattened
        )

    def publish_robot_api_status(status):
        event_name = str(status.get("event", ""))

        if led_tasks is not None and event_name in {
            "robot_api_socket_connected",
            "robot_api_connected",
        }:
            led_tasks.trigger("startup")

        if gui_controller is None:
            return

        gui_controller.publish_robot_api_status(
            status
        )

        gui_controller.publish_event(
            str(
                status.get(
                    "event",
                    "robot_api_status",
                )
            ),
            source="ROBOT_API",
            data=status,
        )

    robot_api = RobotAPIServer(
        host="0.0.0.0",
        port=8774,
        telemetry_callback=publish_robot_api_telemetry,
        status_callback=publish_robot_api_status,
    )

    led_tasks = LEDTaskEngine(
        robot_api,
        loop=asyncio.get_running_loop(),
        verbose=True,
    )
    set_led_task_engine(led_tasks)

    # Optional Brain modules use this local API instead of importing this
    # Master file or opening their own connection to the robot.
    brain_api = BrainAPIServer(
        robot_api=robot_api,
        host="127.0.0.1",
        port=8775,
        allow_arm=False,
        led_task_callback=run_led_task,
    )
    module_manager = BrainModuleManager(
        brain_api_url="ws://127.0.0.1:8775",
    )

    server = None
    video_server = None
    head_server = None
    robot_api_server = None
    brain_api_server = None
    segment_task = None
    transcription_task = None
    gui_chat_task = None

    try:
        server = await incoming.start()
        video_server = await incoming_video.start()
        head_server = await head_control.start()
        robot_api_server = await robot_api.start()
        brain_api_server = await brain_api.start()
        module_manager.start_autostart_modules()

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
                gui_controller,
                request_lock,
            )
        )

        if (
            gui_controller is not None
            and gui_command_queue is not None
        ):
            gui_chat_task = asyncio.create_task(
                online_gui_chat_worker(
                    gui_command_queue,
                    gui_controller,
                    llm,
                    tts,
                    audio_bridge,
                    request_lock,
                    vision_processor,
                    head_control,
                    robot_api,
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

        tasks = [
            server.wait_closed(),
            video_server.wait_closed(),
            head_server.wait_closed(),
            robot_api_server.wait_closed(),
            brain_api_server.wait_closed(),
            segment_task,
            transcription_task,
        ]

        if gui_chat_task is not None:
            tasks.append(
                gui_chat_task
            )

        await asyncio.gather(
            *tasks
        )

    finally:
        if gui_controller is not None:
            gui_controller.set_robot_connection(False, current_robot_name())

        print()
        print("[BX1] Shutting down ROBOT mode...")

        audio_bridge.close()

        if segment_task is not None:
            segment_task.cancel()

        if transcription_task is not None:
            transcription_task.cancel()

        if gui_chat_task is not None:
            gui_chat_task.cancel()

        vision_processor.stop()

        if video_server is not None:
            await incoming_video.stop()

        if head_server is not None:
            await head_control.stop()

        if led_tasks is not None:
            led_tasks.trigger("off")
            await asyncio.sleep(0.08)
            led_tasks.close()
            set_led_task_engine(None)

        module_manager.stop_all()

        if brain_api_server is not None:
            await brain_api.stop()

        if robot_api_server is not None:
            await robot_api.stop()

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



# ============================================================
# GUI ENTRY POINT
# ============================================================

def master_gui_main():
    """Open the GUI first and select OFFLINE or ONLINE using a dialog."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from GUI.gui_controller import GUIController
    from GUI.gui_main import BX1MainWindow
    from GUI.connection_settings import RobotConnectionSettings

    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    gui_controller = GUIController()
    robot_connections = RobotConnectionSettings()
    command_queue = queue.Queue()
    stop_event = threading.Event()

    def handle_gui_command(command):
        # Master_Main_GUI.py remains the authority over GUI commands.
        if command.name == "export_debug":
            gui_controller.publish_event(
                "export_debug_requested",
                source="GUI",
            )
            return

        # Conversation, personality, vision and head-servo commands are
        # routed through the Master queue. Downstream modules never receive
        # GUI commands directly.
        command_queue.put(command)

    gui_controller.set_command_handler(
        handle_gui_command
    )

    window = BX1MainWindow(
        controller=gui_controller,
    )
    window.show()

    def start_offline():
        thread = threading.Thread(
            target=run_local_gui_mode,
            args=(
                gui_controller,
                command_queue,
                stop_event,
            ),
            daemon=True,
            name="BX1-GUI-LOCAL",
        )
        thread.start()

    def start_online(
        connection_type,
        robot_ip,
    ):
        # The selected robot endpoint is held by Master_Main_GUI.py.
        # Existing downstream modules remain unchanged.
        config.ROBOT_CONNECTION_TYPE = str(
            connection_type
        ).upper()
        config.ROBOT_IP = str(
            robot_ip
        ).strip()

        gui_controller.publish_event(
            "robot_connection_selected",
            source="MASTER",
            data={
                "connection_type": config.ROBOT_CONNECTION_TYPE,
                "robot_ip": config.ROBOT_IP,
            },
        )

        print(
            f"[BX1] Robot connection: "
            f"{config.ROBOT_CONNECTION_TYPE} -> "
            f"{config.ROBOT_IP}"
        )

        conversation_box = QMessageBox(window)
        conversation_box.setWindowTitle("BX1 Robot Conversation Mode")
        conversation_box.setText(
            "How should LEO handle the conversation?"
        )
        conversation_box.setInformativeText(
            "STANDARD uses the existing wake/session behaviour.\n\n"
            "CONTINUOUS lets you say the wake word once and continue "
            "until an end phrase is spoken."
        )

        standard_button = conversation_box.addButton(
            "Standard",
            QMessageBox.AcceptRole,
        )
        continuous_button = conversation_box.addButton(
            "Continuous",
            QMessageBox.ActionRole,
        )
        conversation_box.setDefaultButton(
            standard_button
        )
        conversation_box.exec()

        if conversation_box.clickedButton() is continuous_button:
            conversation_mode = "CONTINUOUS"
        else:
            conversation_mode = "STANDARD"

        def robot_worker():
            try:
                asyncio.run(
                    run_robot_mode(
                        conversation_mode=conversation_mode,
                        gui_controller=gui_controller,
                        gui_command_queue=command_queue,
                    )
                )
            except Exception as exc:
                gui_controller.publish_event(
                    "robot_mode_error",
                    source="MASTER",
                    data={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )

        thread = threading.Thread(
            target=robot_worker,
            daemon=True,
            name="BX1-GUI-ROBOT",
        )
        thread.start()

    def choose_operating_mode():
        mode_box = QMessageBox(window)
        mode_box.setWindowTitle("BX1 Operating Mode")
        mode_box.setIcon(QMessageBox.Question)
        mode_box.setText(
            "How do you want to use BX1?"
        )
        mode_box.setInformativeText(
            "OFFLINE uses the PC only and does not connect to the robot.\n\n"
            "ONLINE starts the robot connection and uses the robot "
            "microphone and speaker."
        )

        offline_button = mode_box.addButton(
            "Offline - No Robot",
            QMessageBox.AcceptRole,
        )
        online_button = mode_box.addButton(
            "Online - Use Robot",
            QMessageBox.ActionRole,
        )
        mode_box.addButton(
            "Cancel",
            QMessageBox.RejectRole,
        )

        mode_box.setDefaultButton(
            offline_button
        )
        mode_box.exec()

        clicked = mode_box.clickedButton()

        if clicked is offline_button:
            start_offline()
            return

        if clicked is online_button:
            connection = robot_connections.connection()

            connection_box = QMessageBox(window)
            connection_box.setWindowTitle(
                "BX1 Robot Connection"
            )
            connection_box.setText(
                "How do you want to reach LEO?"
            )
            connection_box.setInformativeText(
                "Local: "
                + connection.get("local_ip", "")
                + "\n\nTailscale: "
                + connection.get("tailscale_ip", "")
            )

            local_button = connection_box.addButton(
                "Local Network",
                QMessageBox.AcceptRole,
            )
            tailscale_button = connection_box.addButton(
                "Tailscale",
                QMessageBox.ActionRole,
            )
            connection_box.addButton(
                "Cancel",
                QMessageBox.RejectRole,
            )

            preferred = connection.get(
                "preferred",
                "LOCAL",
            )

            if preferred == "TAILSCALE":
                connection_box.setDefaultButton(
                    tailscale_button
                )
            else:
                connection_box.setDefaultButton(
                    local_button
                )

            connection_box.exec()

            selected_button = (
                connection_box.clickedButton()
            )

            if selected_button is local_button:
                connection_type = "LOCAL"
            elif selected_button is tailscale_button:
                connection_type = "TAILSCALE"
            else:
                return

            robot_ip = robot_connections.address_for(
                connection_type
            )

            if not robot_ip:
                QMessageBox.warning(
                    window,
                    "BX1 Robot Connection",
                    "No IP address is configured for "
                    + connection_type
                    + ".\n\nOpen Settings and enter the address.",
                )
                return

            start_online(
                connection_type,
                robot_ip,
            )
            return

        window.close()

    def shutdown():
        stop_event.set()
        command_queue.put(None)

    app.aboutToQuit.connect(
        shutdown
    )

    # Main GUI appears before the mode dialog.
    QTimer.singleShot(
        100,
        choose_operating_mode,
    )

    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(
            master_gui_main()
        )

    except KeyboardInterrupt:
        print()
        print("BX1 Master GUI stopped.")