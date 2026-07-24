from __future__ import annotations

from bx1_modules.live_web import (
    append_live_sources_to_reply,
    extract_live_source_entries,
    looks_like_general_web_research,
    strip_sources_for_speech,
)


def test_general_factual_questions_use_broad_web_research() -> None:
    assert looks_like_general_web_research("How does a closed-loop stepper motor work?")
    assert looks_like_general_web_research("Explain PID anti-windup methods")
    assert not looks_like_general_web_research("Hi, how are you?")
    assert not looks_like_general_web_research("Please turn your head left")
    assert not looks_like_general_web_research("Can you turn your head left?")
    assert not looks_like_general_web_research("Can you help me?")
    assert not looks_like_general_web_research("Rewrite this email so it sounds professional")


def test_extract_and_append_numbered_web_sources() -> None:
    context = """LIVE WEB SEARCH RESULTS for: example
Provider: DuckDuckGo
[1] Example result
URL: https://example.com/article
Snippet: Evidence.
[2] Other result
URL: https://other.example/info
Snippet: More evidence.
"""
    entries = extract_live_source_entries(context)
    assert len(entries) == 2
    assert entries[0]["title"] == "Example result"
    assert entries[0]["source"] == "example.com"

    visible = append_live_sources_to_reply(
        "This is the answer.",
        {"verified": True, "source_entries": entries},
    )
    assert "Sources (not spoken):" in visible
    assert "https://example.com/article" in visible


def test_source_footer_and_urls_are_not_sent_to_tts() -> None:
    visible = """The current answer is here [1].

Sources (not spoken):
1. Example result — example.com
   https://example.com/article
"""
    speech = strip_sources_for_speech(visible)
    assert speech == "The current answer is here."
    assert "Sources" not in speech
    assert "http" not in speech
