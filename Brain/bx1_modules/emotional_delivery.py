"""Deliberate, hidden emotional-delivery routing for Dot.TTS.

The language model may put one ``[voice:<delivery>]`` marker at the start of a
reply.  Robot Brain removes that marker from chat and API text, but can turn it
into a short natural-language performance direction for Dot.TTS.  Dot.TTS does
not expose a guaranteed emotion parameter, so inline directions remain an
explicitly labelled experimental option.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping


DELIVERY_DIRECTIONS: Dict[str, str] = {
    "normal": "Natural, relaxed and conversational, with clear British pronunciation",
    "warm": "Warm, emotionally present and gently affectionate, with an easy conversational rhythm",
    "playful": "Playful, lightly teasing and bright, with a small smile in the voice",
    "amused": "Genuinely amused and dryly funny, without becoming exaggerated",
    "excited": "Curious, energised and pleasantly excited, while remaining clear",
    "cautious": "Careful, attentive and slightly concerned, with deliberate pacing",
    "reassuring": "Calm, kind and reassuring, with steady confidence and no forced cheerfulness",
    "serious": "Serious, composed and direct, with crisp emphasis and no flirtation or jokes",
}

DELIVERY_ALIASES = {
    "neutral": "normal",
    "calm": "normal",
    "friendly": "warm",
    "affectionate": "warm",
    "flirty": "playful",
    "teasing": "playful",
    "funny": "amused",
    "humorous": "amused",
    "concerned": "cautious",
    "careful": "cautious",
    "comforting": "reassuring",
    "supportive": "reassuring",
}

_DIRECTION_TAG = re.compile(
    r"^\s*\[(?:voice|emotion|tone)\s*[:=]\s*([a-zA-Z0-9_\- ]+)\]\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DeliveryPlan:
    key: str
    direction: str
    source: str

    def public_dict(self) -> Dict[str, str]:
        return {"delivery": self.key, "source": self.source}


def normalise_delivery(value: Any, default: str = "normal") -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    key = DELIVERY_ALIASES.get(key, key)
    return key if key in DELIVERY_DIRECTIONS else default


def extract_delivery(text: str, default: str = "normal") -> DeliveryPlan:
    """Read a hidden leading direction, with restrained cue-based fallbacks."""
    raw = str(text or "")
    match = _DIRECTION_TAG.match(raw)
    if match:
        key = normalise_delivery(match.group(1), default)
        return DeliveryPlan(key, DELIVERY_DIRECTIONS[key], "model_tag")

    lowered = raw.lower()
    if "[laugh]" in lowered or "[chuckle]" in lowered:
        key = "amused"
        return DeliveryPlan(key, DELIVERY_DIRECTIONS[key], "audible_cue")
    if "[gasp]" in lowered:
        key = "excited"
        return DeliveryPlan(key, DELIVERY_DIRECTIONS[key], "audible_cue")
    if "[sigh]" in lowered or "[groan]" in lowered:
        key = "cautious"
        return DeliveryPlan(key, DELIVERY_DIRECTIONS[key], "audible_cue")
    key = normalise_delivery(default)
    return DeliveryPlan(key, DELIVERY_DIRECTIONS[key], "default")


def strip_delivery_tag(text: str) -> str:
    return _DIRECTION_TAG.sub("", str(text or ""), count=1).strip()


def build_dottts_text(
    text: str,
    delivery: str,
    *,
    enabled: bool = True,
    inline_instructions: bool = True,
    directions: Mapping[str, str] | None = None,
) -> str:
    """Return the experimental Dot.TTS input without leaking internal tags.

    When inline instructions are disabled this returns clean dialogue only.
    This makes it safe to turn the experimental behaviour off per profile.
    """
    clean = strip_delivery_tag(text)
    if not clean or not enabled or not inline_instructions:
        return clean
    key = normalise_delivery(delivery)
    instruction_map = dict(DELIVERY_DIRECTIONS)
    if directions:
        for candidate, value in directions.items():
            normalised = normalise_delivery(candidate, "")
            if normalised and str(value or "").strip():
                instruction_map[normalised] = str(value).strip()
    direction = instruction_map.get(key, DELIVERY_DIRECTIONS["normal"])
    return f"[{direction}]\n{clean}"

