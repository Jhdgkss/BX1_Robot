"""Small, hardware-independent contracts for the BX1 voice pipeline.

The Body uses this module for the speaker-active microphone gate and for
diagnostic transcript presentation.  It intentionally contains no device I/O.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass
class SpeakerActiveMicrophoneGate:
    """Coordinate playback, microphone suppression and the echo tail."""

    echo_tail_ms: int = 1500
    event: Optional[Callable[[str, Dict[str, Any]], None]] = None
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _active: bool = field(default=False, init=False)
    _tail_until: float = field(default=0.0, init=False)
    _generation: int = field(default=0, init=False)
    discarded_frames: int = field(default=0, init=False)
    discarded_bytes: int = field(default=0, init=False)

    def _emit(self, name: str, **data: Any) -> None:
        if self.event:
            self.event(name, data)

    def start(self) -> None:
        with self._lock:
            self._active = True
            self._tail_until = 0.0
            self._generation += 1
            generation = self._generation
        self._emit("speaker_started", generation=generation)
        self._emit("microphone_gate_closed", reason="speaker_playback")

    def finish(self) -> None:
        tail = max(0.0, min(5.0, float(self.echo_tail_ms) / 1000.0))
        with self._lock:
            self._active = False
            self._tail_until = time.monotonic() + tail
        self._emit("playback_finished")
        self._emit("echo_tail_started", duration_ms=int(tail * 1000))

    def discard_frame(self, frame: Any = b"", *, force: bool = False) -> bool:
        """Return whether a frame must be excluded from production capture.

        ``force`` is used while the post-playback quiet dwell is still active:
        the playback tail may have elapsed, but production listening must not
        reopen until the Body has observed a quiet microphone.
        """
        with self._lock:
            suppressed = force or self._active or time.monotonic() < self._tail_until
            if suppressed:
                self.discarded_frames += 1
                try:
                    self.discarded_bytes += len(frame)
                except TypeError:
                    pass
        if suppressed:
            self._emit("microphone_frames_discarded", count=self.discarded_frames)
        return suppressed

    def flush(self) -> Dict[str, int]:
        with self._lock:
            result = {"frames": self.discarded_frames, "bytes": self.discarded_bytes}
            self.discarded_frames = 0
            self.discarded_bytes = 0
        self._emit("microphone_buffer_flushed", **result)
        return result

    def open(self) -> bool:
        with self._lock:
            if self._active or time.monotonic() < self._tail_until:
                return False
            self._tail_until = 0.0
        self._emit("microphone_gate_opened")
        return True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            tail = max(0.0, self._tail_until - time.monotonic())
            return {"speaker_active": self._active, "echo_tail": tail > 0,
                    "echo_tail_remaining_s": round(tail, 2),
                    "microphone_gate_closed": self._active or tail > 0,
                    "playback_generation": self._generation,
                    "discarded_frames": self.discarded_frames}


def extract_request(transcript: str, wake_phrases: Iterable[str]) -> Dict[str, Any]:
    """Extract the request after the first configured wake phrase."""
    source = str(transcript or "").strip()
    candidates = sorted((str(x).strip() for x in wake_phrases if str(x).strip()), key=len, reverse=True)
    for phrase in candidates:
        match = re.search(r"(?i)(?<!\w)" + re.escape(phrase) + r"(?!\w)", source)
        if match:
            request = source[match.end():].lstrip(" ,:;.!?-\u2014")
            return {"transcript": source, "wake_phrase": source[match.start():match.end()],
                    "request": request, "wake_range": [match.start(), match.end()],
                    "request_range": [match.end() + (len(source[match.end():]) - len(source[match.end():].lstrip(" ,:;.!?-\u2014"))), len(source)]}
    return {"transcript": source, "wake_phrase": "", "request": "", "wake_range": [], "request_range": []}


def highlight_segments(transcript: str, wake_range: List[int], request_range: List[int], uncertain: Optional[List[List[int]]] = None) -> List[Dict[str, Any]]:
    """Return non-overlapping highlight ranges for the scan UI."""
    text = str(transcript or "")
    points = {0, len(text)}
    for pair in (wake_range, request_range, *(uncertain or [])):
        if len(pair) == 2:
            points.update((max(0, min(len(text), int(pair[0]))), max(0, min(len(text), int(pair[1])))))
    cuts = sorted(points)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b <= a: continue
        kind = "normal"
        if wake_range and a >= wake_range[0] and b <= wake_range[1]: kind = "wake"
        elif request_range and a >= request_range[0] and b <= request_range[1]: kind = "request"
        elif any(len(x) == 2 and a >= x[0] and b <= x[1] for x in (uncertain or [])): kind = "uncertain"
        out.append({"text": text[a:b], "start": a, "end": b, "kind": kind})
    return out
