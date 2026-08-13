from collections import deque
import numpy as np
import settings.config as config

class SpeechSegmenter:
    def __init__(self):
        self.active = False
        self.pre_roll = deque()
        self.pre_roll_bytes = 0
        self.utterance = bytearray()
        self.silence_seconds = 0.0

    @staticmethod
    def _rms_normalized(pcm: bytes) -> float:
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0:
            return 0.0
        samples_f = samples.astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(samples_f * samples_f)))

    @staticmethod
    def _duration_seconds(pcm: bytes) -> float:
        bytes_per_second = (
            config.MIC_SAMPLE_RATE
            * config.MIC_CHANNELS
            * config.MIC_SAMPLE_WIDTH_BYTES
        )
        return len(pcm) / bytes_per_second

    def _trim_pre_roll(self):
        max_bytes = int(
            config.PRE_ROLL_SECONDS
            * config.MIC_SAMPLE_RATE
            * config.MIC_CHANNELS
            * config.MIC_SAMPLE_WIDTH_BYTES
        )
        while self.pre_roll and self.pre_roll_bytes > max_bytes:
            old = self.pre_roll.popleft()
            self.pre_roll_bytes -= len(old)

    def _finish_utterance(self):
        pcm = bytes(self.utterance)
        self.active = False
        self.utterance.clear()
        self.silence_seconds = 0.0

        if self._duration_seconds(pcm) < config.MIN_UTTERANCE_SECONDS:
            return None
        return pcm

    def feed(self, pcm: bytes):
        completed = []
        if not pcm:
            return completed

        rms = self._rms_normalized(pcm)
        block_seconds = self._duration_seconds(pcm)

        if not self.active:
            self.pre_roll.append(pcm)
            self.pre_roll_bytes += len(pcm)
            self._trim_pre_roll()

            if rms >= config.SPEECH_START_RMS:
                self.active = True
                for block in self.pre_roll:
                    self.utterance.extend(block)
                self.pre_roll.clear()
                self.pre_roll_bytes = 0
                self.silence_seconds = 0.0
            return completed

        self.utterance.extend(pcm)

        if rms >= config.SPEECH_CONTINUE_RMS:
            self.silence_seconds = 0.0
        else:
            self.silence_seconds += block_seconds

        utterance_seconds = self._duration_seconds(self.utterance)
        natural_end = self.silence_seconds >= config.END_SILENCE_SECONDS
        forced_end = utterance_seconds >= config.MAX_UTTERANCE_SECONDS

        if natural_end or forced_end:
            finished = self._finish_utterance()
            if finished is not None:
                completed.append(finished)

        return completed
