"""Conversation gating for BX1/LEO continuous voice mode.

This module owns only conversation state. It does not call STT, the LLM,
TTS, the GUI or robot hardware. Master_Main_GUI.py remains the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


def _normalise(text: str) -> str:
    value = str(text or "").lower().replace("’", "'")
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return " ".join(value.split())


def _clean_phrases(items: Iterable[str]) -> tuple[str, ...]:
    result = []

    for item in items or ():
        cleaned = _normalise(item)

        if cleaned and cleaned not in result:
            result.append(cleaned)

    return tuple(result)


@dataclass(frozen=True)
class ConversationDecision:
    kind: str
    display_text: str
    command_text: str
    send_to_llm: bool
    session_active: bool
    session_opened: bool = False
    session_closed: bool = False


class ContinuousConversationSession:
    """Wake once, remain open until an explicit end phrase is heard."""

    def __init__(
        self,
        *,
        wake_words=(),
        end_phrases=(),
    ):
        self.wake_words = _clean_phrases(
            wake_words
        )

        self.end_phrases = _clean_phrases(
            end_phrases
        )

        self.active = False

    def reset(self) -> None:
        self.active = False

    def _contains_end_phrase(
        self,
        text: str,
    ) -> bool:
        normal = _normalise(text)

        if not normal:
            return False

        padded = f" {normal} "

        return any(
            f" {phrase} " in padded
            for phrase in self.end_phrases
        )

    def _detect_wake(
        self,
        text: str,
    ) -> bool:
        normal = _normalise(text)

        if not normal:
            return False

        for wake in self.wake_words:
            if (
                normal == wake
                or normal.startswith(
                    wake + " "
                )
            ):
                return True

        return False

    def _strip_leading_wake(
        self,
        text: str,
    ) -> str:
        original = str(
            text
            or ""
        ).strip()

        if not original:
            return ""

        for wake in sorted(
            self.wake_words,
            key=len,
            reverse=True,
        ):
            words = [
                re.escape(word)
                for word in wake.split()
            ]

            pattern = (
                r"^\s*"
                + r"[\s,.:;!?-]+".join(words)
                + r"\b[\s,.:;!?-]*"
            )

            cleaned = re.sub(
                pattern,
                "",
                original,
                count=1,
                flags=re.IGNORECASE,
            ).strip()

            if cleaned != original:
                return cleaned

        return original

    def process(
        self,
        recognized_text: str,
        *,
        wake_detected: bool = False,
        preferred_command: str = "",
    ) -> ConversationDecision:
        text = str(
            recognized_text
            or ""
        ).strip()

        if not text:
            return ConversationDecision(
                kind="empty",
                display_text="",
                command_text="",
                send_to_llm=False,
                session_active=self.active,
            )

        was_active = self.active

        wake_detected = bool(
            wake_detected
            or self._detect_wake(text)
        )

        if (
            wake_detected
            and not self.active
        ):
            self.active = True

        if (
            self.active
            and self._contains_end_phrase(
                text
            )
        ):
            self.active = False

            return ConversationDecision(
                kind="end",
                display_text=text,
                command_text="",
                send_to_llm=False,
                session_active=False,
                session_opened=(
                    not was_active
                    and wake_detected
                ),
                session_closed=True,
            )

        if not self.active:
            return ConversationDecision(
                kind="background",
                display_text=text,
                command_text="",
                send_to_llm=False,
                session_active=False,
            )

        preferred = str(
            preferred_command
            or ""
        ).strip()

        command = (
            preferred
            if preferred
            else self._strip_leading_wake(
                text
            )
        )

        normal_text = _normalise(text)

        bare_wake = (
            wake_detected
            and normal_text in self.wake_words
        )

        if bare_wake:
            command = ""

        return ConversationDecision(
            kind=(
                "wake"
                if wake_detected
                else "conversation"
            ),
            display_text=text,
            command_text=command,
            send_to_llm=bool(command),
            session_active=True,
            session_opened=(
                not was_active
                and wake_detected
            ),
        )
