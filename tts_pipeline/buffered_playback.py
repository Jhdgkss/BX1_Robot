from __future__ import annotations

import time
from typing import Iterable


ROBOT_END_GUARD_SECONDS = 0.30


class BufferedTTSPlayback:
    """Play a complete set of generated TTS PCM blocks as one continuous speech session."""

    def __init__(self, audio_output, robot_end_guard_seconds=ROBOT_END_GUARD_SECONDS):
        self.audio_output = audio_output
        self.robot_end_guard_seconds = max(0.0, float(robot_end_guard_seconds))

    def _mode_name(self):
        return str(getattr(self.audio_output, "mode_name", "UNKNOWN") or "UNKNOWN").upper()

    @staticmethod
    def _total_duration(items):
        return sum(max(0.0, float(item.get("duration", 0.0))) for item in items)

    @staticmethod
    def _sample_rate(items):
        if not items:
            return None
        sample_rate = int(items[0]["sample_rate"])
        for item in items[1:]:
            item_rate = int(item["sample_rate"])
            if item_rate != sample_rate:
                raise RuntimeError(
                    "TTS reply contains mixed sample rates: "
                    f"{sample_rate} and {item_rate}."
                )
        return sample_rate

    def play(self, generated_items: Iterable[dict]):
        items = [item for item in generated_items if item and item.get("pcm16")]

        if not items:
            print("[TTS PLAYBACK] No generated audio to play.")
            return False

        sample_rate = self._sample_rate(items)
        total_duration = self._total_duration(items)
        mode_name = self._mode_name()

        print()
        print(
            "[TTS PLAYBACK] Complete reply buffered: "
            f"{len(items)} chunk(s), {total_duration:.2f}s speech."
        )
        print(f"[TTS PLAYBACK] Starting continuous {mode_name} playback.")

        started = False
        sent_ok = True

        try:
            started = bool(self.audio_output.start_tts(sample_rate))
            if not started:
                print("[TTS PLAYBACK] Audio output refused TTS session.")
                return False

            for item in items:
                print(f"[TTS PLAY {item['number']}] {item['duration']:.2f}s")
                result = self.audio_output.send_pcm16(item["pcm16"])
                if result is False:
                    sent_ok = False
                    print(
                        "[TTS PLAYBACK] PCM send failed at chunk "
                        f"{item['number']}."
                    )
                    break

            if sent_ok and mode_name == "ROBOT" and total_duration > 0.0:
                print(
                    "[TTS PLAYBACK] "
                    f"Allowing {total_duration:.2f}s for physical robot playback."
                )
                time.sleep(total_duration + self.robot_end_guard_seconds)

            return sent_ok

        finally:
            if started:
                try:
                    self.audio_output.end_tts()
                except Exception as exc:
                    print(
                        "[TTS PLAYBACK] Could not close TTS session: "
                        f"{type(exc).__name__}: {exc}"
                    )
