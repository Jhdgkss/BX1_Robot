"""Small Windows-side Edge speech fallback for Robot Brain.

Dot.TTS is the primary voice engine.  This module deliberately has no model or
GPU dependencies so the Brain can still speak while WSL is starting or if the
Dot.TTS service becomes unavailable.
"""
from __future__ import annotations

import asyncio
import tempfile
import threading
from pathlib import Path
from typing import Optional


class EdgeVoice:
    """Generate Edge speech and optionally play it with pygame."""

    def __init__(self) -> None:
        self._play_lock = threading.Lock()

    @staticmethod
    def _signed(value: int, suffix: str) -> str:
        number = int(value or 0)
        return f"{number:+d}{suffix}"

    def generate(
        self,
        text: str,
        output_path: str | Path,
        *,
        voice: str = "en-GB-RyanNeural",
        rate_percent: int = 0,
        pitch_hz: int = 0,
    ) -> Path:
        """Generate an MP3 file synchronously from a worker thread."""
        clean = str(text or "").strip()
        if not clean:
            raise ValueError("Speech text is empty.")
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        async def create() -> None:
            import edge_tts  # type: ignore

            communicator = edge_tts.Communicate(
                clean,
                voice=str(voice or "en-GB-RyanNeural"),
                rate=self._signed(rate_percent, "%"),
                pitch=self._signed(pitch_hz, "Hz"),
            )
            await communicator.save(str(target))

        asyncio.run(create())
        if not target.exists() or target.stat().st_size <= 0:
            raise RuntimeError("Edge generated no audio data.")
        return target

    def play(self, audio_path: str | Path, *, volume: float = 0.9) -> None:
        """Play one local MP3/WAV file and wait until playback completes."""
        import pygame  # type: ignore

        path = Path(audio_path).expanduser().resolve()
        with self._play_lock:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume))))
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            clock = pygame.time.Clock()
            while pygame.mixer.music.get_busy():
                clock.tick(25)
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass

    def speak(
        self,
        text: str,
        *,
        voice: str = "en-GB-RyanNeural",
        rate_percent: int = 0,
        pitch_hz: int = 0,
        volume: float = 0.9,
    ) -> None:
        """Generate and play speech, removing the temporary file afterwards."""
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp:
                temp_path = Path(temp.name)
            self.generate(
                text,
                temp_path,
                voice=voice,
                rate_percent=rate_percent,
                pitch_hz=pitch_hz,
            )
            self.play(temp_path, volume=volume)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def stop(self) -> None:
        try:
            import pygame  # type: ignore

            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
