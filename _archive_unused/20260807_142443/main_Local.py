# ============================================================
# BX1 LOCAL TEXT -> LLM -> QWEN TTS -> PC AUDIO
# ============================================================
#
# CENTRAL BX1 LOCAL ORCHESTRATOR
# ------------------------------
#
# All local script orchestration and data flow passes through
# THIS FILE.
#
# Normal speech path:
#
#     keyboard / STT
#          |
#          v
#     main_Local.py
#          |
#          v
#      LLMClient
#          |
#          v
#     main_Local.py
#          |
#          v
#    QwenTTSEngine
#          |
#          | generated PCM16
#          v
#   MainLocalAudioBridge
#     (THIS FILE)
#          |
#          v
#      pc_audio.py
#          |
#          v
#      PC speakers
#
#
# Sound-effect path:
#
#     BX1 event
#          |
#          v
#     main_Local.py
#          |
#          v
#   sound_effects.py
#   loads WAV -> PCM
#          |
#          v
#     main_Local.py
#          |
#          v
#      pc_audio.py
#          |
#          v
#      PC speakers
#
#
# IMPORTANT
# ---------
#
# sound_effects.py does NOT play audio itself.
#
# pc_audio.py is unchanged.
#
# audio_to_robot_streamer.py is unchanged.
#
# The local version currently routes both TTS and sound effects
# to pc_audio.py. When the robot-output version is used later,
# main_Local.py can route effects through the existing
# start_effect()/send_pcm16()/end_effect() interface exposed by
# audio_to_robot_streamer.py.
#
# ============================================================

import threading

from colorama import Fore, Back, Style

from llm_client import LLMClient
from tts_engine import QwenTTSEngine
from pc_audio import PCAudioOutput
from sound_effects import SoundEffectLibrary


# ============================================================
# MAIN LOCAL AUDIO BRIDGE
# ============================================================
#
# This object belongs to main_Local.py and remains the one place
# where generated speech or sound-effect PCM is handed to the
# selected audio output.
#
# ============================================================

class MainLocalAudioBridge:

    def __init__(
        self,
        pc_audio,
        sound_library,
    ):
        self.pc_audio = pc_audio
        self.sound_library = sound_library

        # Only one thing may own the speaker at a time.
        #
        # This prevents a delayed "still thinking" sound from
        # colliding with the start of LEO's spoken answer.
        self._audio_session_lock = threading.Lock()

        self._tts_session_active = False

        self._waiting_timer = None
        self._waiting_timer_lock = threading.RLock()


    # ========================================================
    # TTS AUDIO FROM tts_engine.py
    # ========================================================

    def start_tts(
        self,
        sample_rate=24000,
    ):
        """
        tts_engine.py calls this when the first generated speech
        audio is ready.

        This is also the point at which the user is no longer
        waiting for audible speech, so cancel llm_waiting.
        """

        self.cancel_llm_waiting_timer()

        print(
            f"[MAIN AUDIO] New TTS reply received "
            f"at {sample_rate} Hz."
        )

        # Wait for any short sound effect currently using the
        # PC speaker to finish before starting the spoken reply.
        self._audio_session_lock.acquire()

        started = False

        try:
            started = bool(
                self.pc_audio.start_tts(
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
        """
        Receive generated Qwen PCM from tts_engine.py and pass it
        through main_Local.py to pc_audio.py.
        """

        if not pcm_data:
            return False

        if not self._tts_session_active:
            return False

        return self.pc_audio.send_pcm16(
            pcm_data
        )


    def end_tts(self):
        """
        Complete the TTS session.

        pc_audio.py writes and plays the complete WAV. The audio
        session remains locked until that playback finishes.
        """

        print(
            "[MAIN AUDIO] Complete generated reply received."
        )

        try:
            if not self._tts_session_active:
                return False

            return self.pc_audio.end_tts()

        finally:
            self._tts_session_active = False

            if self._audio_session_lock.locked():
                self._audio_session_lock.release()


    # ========================================================
    # SOUND EFFECT EVENTS
    # ========================================================

    def play_sound_effect(
        self,
        event_name,
    ):
        """
        Load one configured event using sound_effects.py and route
        the returned PCM through pc_audio.py.

        This function is synchronous and is normally called by
        play_sound_effect_async().
        """

        effect = self.sound_library.load(
            event_name
        )

        if effect is None:
            return False

        print(
            f"[SOUNDS] Event: {event_name} -> "
            f"{effect.file_path.name}"
        )

        # Serialise effect playback against Qwen speech.
        with self._audio_session_lock:

            started = self.pc_audio.start_tts(
                effect.sample_rate
            )

            if not started:
                return False

            if not self.pc_audio.send_pcm16(
                effect.pcm16
            ):
                return False

            return self.pc_audio.end_tts()


    def play_sound_effect_async(
        self,
        event_name,
    ):
        """
        Fire a sound effect without delaying LLM processing.

        main_Local.py remains the caller and routing owner.
        """

        if not self.sound_library.is_enabled(
            event_name
        ):
            return False

        thread = threading.Thread(
            target=self.play_sound_effect,
            args=(
                event_name,
            ),
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
        Start the configured llm_waiting timer.

        The timer begins when main_Local.py sends the request to
        the LLM and is cancelled only when actual TTS audio starts
        or the request fails/finishes without speech.

        Therefore the timeout measures USER-PERCEIVED SILENCE,
        not merely LLM text-generation time.
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
            f"[SOUNDS] LLM waiting timer started: "
            f"{delay_seconds:.2f}s"
        )

        return True


    def _llm_waiting_timer_fired(self):
        with self._waiting_timer_lock:
            self._waiting_timer = None

        print(
            "[SOUNDS] LLM still waiting - "
            "playing delayed cue."
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


    # ========================================================
    # SHUTDOWN
    # ========================================================

    def close(self):
        self.cancel_llm_waiting_timer()


# ============================================================
# DISPLAY LEO'S TEXT REPLY
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
# MAIN
# ============================================================

def main():

    print()
    print("====================================================")
    print(" BX1 LOCAL TEXT / VOICE TEST")
    print("====================================================")
    print()
    print("Microphone input : DISABLED")
    print("Whisper / STT    : DISABLED")
    print("Robot audio link : DISABLED")
    print("Input            : KEYBOARD")
    print("Speech generator : tts_engine.py / Qwen")
    print("Audio bridge     : main_Local.py")
    print("Sound events     : sound_effects.py")
    print("Playback         : pc_audio.py -> PC speakers")
    print()


    # ========================================================
    # CREATE LLM CLIENT
    # ========================================================

    llm = LLMClient()


    # ========================================================
    # CREATE SOUND EFFECT LIBRARY
    # ========================================================
    #
    # sound_effects.py loads config and WAV data only.
    #
    # It does NOT know about pc_audio.py.
    # It does NOT know about the robot streamer.
    # ========================================================

    sound_library = SoundEffectLibrary()


    # ========================================================
    # CREATE LOCAL PC AUDIO PLAYER
    # ========================================================

    pc_audio = PCAudioOutput()

    pc_audio.start()


    # ========================================================
    # CREATE MAIN_LOCAL AUDIO BRIDGE
    # ========================================================

    audio_bridge = MainLocalAudioBridge(
        pc_audio=pc_audio,
        sound_library=sound_library,
    )


    # ========================================================
    # CREATE QWEN TTS ENGINE
    # ========================================================

    tts = QwenTTSEngine(
        audio_bridge
    )


    # ========================================================
    # STATUS
    # ========================================================

    print(
        "[BX1] LLM is "
        + (
            "ENABLED"
            if llm.enabled
            else "DISABLED"
        )
    )

    print(
        "[BX1] TTS is "
        + (
            "ENABLED"
            if tts.enabled
            else "DISABLED"
        )
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


    # ========================================================
    # LOCAL TEXT CONVERSATION LOOP
    # ========================================================
    #
    # Wake/STT are disabled in this particular keyboard test,
    # therefore wake_detected and stt_started are NOT faked here.
    #
    # When microphone/STT is restored, the owning code in
    # main_Local.py should call:
    #
    #     audio_bridge.play_sound_effect_async("wake_detected")
    #
    # and:
    #
    #     audio_bridge.play_sound_effect_async("stt_started")
    #
    # at the actual event boundaries.
    #
    # ========================================================

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


            # =================================================
            # CHECK LLM
            # =================================================

            if not llm.enabled:

                print(
                    Fore.RED
                    + "[LLM] LLM is disabled."
                    + Style.RESET_ALL
                )

                audio_bridge.play_sound_effect_async(
                    "error"
                )

                continue


            print(
                Fore.GREEN
                + "[LLM] Thinking..."
                + Style.RESET_ALL
            )


            # =================================================
            # ASK LLM
            # =================================================

            request_has_speech_pending = False

            try:

                # ---------------------------------------------
                # EVENT: REQUEST ABOUT TO BE SENT TO LLM
                # ---------------------------------------------
                #
                # The sound plays on a worker thread so it does
                # not delay llm.ask().
                # ---------------------------------------------

                audio_bridge.play_sound_effect_async(
                    "llm_request_sent"
                )

                # Start the "still thinking" timer at the same
                # boundary as the LLM request.
                audio_bridge.start_llm_waiting_timer()

                request_has_speech_pending = True


                # ---------------------------------------------
                # SEND REQUEST TO LLM
                # ---------------------------------------------

                reply = llm.ask(
                    user_text
                )


                if not reply:

                    # No speech will follow, so the waiting timer
                    # must not remain alive.
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

                    continue


                # ---------------------------------------------
                # OPTIONAL EVENT: LLM TEXT HAS RETURNED
                # ---------------------------------------------
                #
                # Disabled by default in the config because the
                # user is still waiting for audible TTS.
                # ---------------------------------------------

                audio_bridge.play_sound_effect_async(
                    "llm_response_received"
                )


                # =============================================
                # DISPLAY TEXT REPLY
                # =============================================

                print_leo_reply(
                    reply
                )


                # =============================================
                # GENERATE AND PLAY SPEECH
                # =============================================

                if tts.enabled:

                    tts.speak(
                        reply
                    )


                    # Qwen runs in its own background thread.
                    #
                    # MainLocalAudioBridge.start_tts() cancels
                    # llm_waiting when actual audio arrives.
                    #
                    # Do NOT cancel the timer just because the
                    # LLM has returned text; TTS generation may
                    # still take several seconds.

                    tts.speech_queue.join()

                    request_has_speech_pending = False

                else:

                    # No spoken response will occur.
                    audio_bridge.cancel_llm_waiting_timer()

                    request_has_speech_pending = False


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


            finally:

                # Safety cleanup for any path that exits without
                # starting/finishing TTS.
                if request_has_speech_pending:
                    audio_bridge.cancel_llm_waiting_timer()


    # ========================================================
    # SHUTDOWN
    # ========================================================

    finally:

        print()
        print("[BX1] Shutting down...")


        audio_bridge.close()


        # Stop Qwen's worker thread.

        tts.close()


        if (
            tts.worker_thread is not None
            and tts.worker_thread.is_alive()
        ):

            tts.worker_thread.join(
                timeout=2.0
            )


        # Stop local playback.

        pc_audio.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()


    except KeyboardInterrupt:

        print()
        print("BX1 Local test stopped.")
