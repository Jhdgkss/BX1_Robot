"""Local suggestion helper for safe BX1 behaviour capability sketches."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class BehaviourSuggestion:
    title: str
    task: str
    rationale: str
    trigger_phrases: List[str]


SUGGESTION_LIBRARY: List[BehaviourSuggestion] = [
    BehaviourSuggestion(
        "Polite attention cue",
        "Create a polite attention cue with a small head lift, a soft blue mouth-light pulse, the phrase 'I'm listening.', and a return to centre.",
        "Adds a useful non-verbal acknowledgement for voice interaction without wheel movement.",
        ["I'm listening", "show listening cue", "run polite attention cue"],
    ),
    BehaviourSuggestion(
        "Tiny celebration",
        "Create a tiny celebration behaviour with two gentle head tilts, a green mouth-light flash, the phrase 'Nice. That worked.', and a return to centre.",
        "Gives the robot a safe success response after completed tasks.",
        ["celebrate", "do a tiny celebration", "run tiny celebration"],
    ),
    BehaviourSuggestion(
        "Thinking glance",
        "Create a thinking glance with a small yaw to the right, amber mouth light, a short pause, the phrase 'Let me think about that.', and a return to centre.",
        "Makes model latency feel intentional while keeping motion small.",
        ["thinking glance", "show thinking glance", "run thinking glance"],
    ),
    BehaviourSuggestion(
        "Curious check",
        "Create a curious check behaviour with a small head roll, cyan mouth-light cue, the phrase 'Hmm. Curious.', and a return to centre.",
        "Extends the robot's expressive curiosity with bounded head and LED motion.",
        ["curious check", "act curious", "run curious check"],
    ),
    BehaviourSuggestion(
        "Calm acknowledgement",
        "Create a calm acknowledgement with a slow blue mouth-light fade, a subtle nod, the phrase 'Understood.', and a return to centre.",
        "Adds a quiet operator acknowledgement for serious or technical work.",
        ["acknowledge that", "calm acknowledgement", "run calm acknowledgement"],
    ),
]


def _normalise_words(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(word) > 2}


def suggest_behaviour_capability(existing_behaviours: Iterable[Dict[str, Any]] = (), context: str = "") -> BehaviourSuggestion:
    """Choose one safe suggestion that does not duplicate installed behaviour names."""
    installed_names = {
        str(item.get("name") or item.get("display_name") or "").strip().lower().replace("_", " ")
        for item in existing_behaviours
        if not item.get("invalid")
    }
    context_words = _normalise_words(context)
    best = SUGGESTION_LIBRARY[0]
    best_score = -1
    for suggestion in SUGGESTION_LIBRARY:
        title_key = suggestion.title.lower()
        if title_key in installed_names or title_key.replace(" ", "_") in installed_names:
            continue
        score = len(_normalise_words(suggestion.task) & context_words)
        if score > best_score:
            best = suggestion
            best_score = score
    return best


def format_suggestion_for_workshop(suggestion: BehaviourSuggestion) -> str:
    triggers = ", ".join(suggestion.trigger_phrases)
    return (
        f"Suggested capability sketch: {suggestion.title}\n\n"
        f"Why: {suggestion.rationale}\n\n"
        f"Task for the forge:\n{suggestion.task}\n\n"
        f"Suggested trigger phrases: {triggers}"
    )
