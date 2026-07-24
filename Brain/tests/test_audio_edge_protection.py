from __future__ import annotations

import numpy as np

from bx1_services.dottts_service.app import protect_audio_edges


def test_protect_audio_edges_adds_requested_padding() -> None:
    rate = 1000
    source = np.ones(100, dtype=np.float32)
    protected, meta = protect_audio_edges(
        source, rate, leading_silence_ms=20, trailing_silence_ms=30, edge_fade_ms=0
    )

    assert protected.shape == (150,)
    assert np.allclose(protected[:20], 0.0)
    assert np.allclose(protected[20:120], 1.0)
    assert np.allclose(protected[120:], 0.0)
    assert meta["raw_audio_duration_sec"] == 0.1
    assert meta["audio_duration_sec"] == 0.15
    assert meta["audio_edge_protection"] is True


def test_protect_audio_edges_preserves_stereo_layout() -> None:
    rate = 1000
    source = np.ones((2, 100), dtype=np.float32)  # channels x frames
    protected, _ = protect_audio_edges(
        source, rate, leading_silence_ms=10, trailing_silence_ms=10, edge_fade_ms=0
    )

    assert protected.shape == (120, 2)
    assert np.allclose(protected[10:110], 1.0)


def test_protect_audio_edges_applies_short_fade() -> None:
    source = np.ones(20, dtype=np.float32)
    protected, meta = protect_audio_edges(
        source, 1000, leading_silence_ms=0, trailing_silence_ms=0, edge_fade_ms=4
    )

    assert protected[0] == 0.0
    assert protected[-1] == 0.0
    assert protected[4] == 1.0
    assert meta["edge_fade_ms"] == 4
