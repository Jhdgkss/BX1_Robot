from dataclasses import dataclass, field
from datetime import datetime
import re
import time
from typing import List, Optional
from colorama import Fore, Style, init
import settings.config as config

init(autoreset=True)

@dataclass
class TranscriptEvent:
    timestamp: str
    raw_text: str
    wake_word: Optional[str] = None
    end_phrase: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    conversation_active: bool = False
    command_text: str = ""
    send_to_llm: bool = False

def _phrase_pattern(phrase: str):
    return re.compile(
        rf"(?<!\w){re.escape(phrase)}(?!\w)",
        flags=re.IGNORECASE,
    )

class TranscriptProcessor:
    def __init__(self):
        self.conversation_active = False
        self.last_conversation_activity = 0.0

    def _expire_conversation_if_needed(self):
        if not self.conversation_active:
            return
        elapsed = time.monotonic() - self.last_conversation_activity
        if elapsed > config.CONVERSATION_TIMEOUT_SECONDS:
            self.conversation_active = False
            print(Fore.BLUE + "[CONVERSATION] Timeout -> closed")

    @staticmethod
    def _find_phrase(text: str, phrases):
        best = None
        for phrase in phrases:
            match = _phrase_pattern(phrase).search(text)
            if match is not None:
                if best is None or match.start() < best[1].start():
                    best = (phrase, match)
        return best if best else (None, None)

    @staticmethod
    def _find_keywords(text: str):
        return [
            keyword
            for keyword in config.KEYWORDS
            if _phrase_pattern(keyword).search(text)
        ]

    def process(self, text: str) -> TranscriptEvent:
        self._expire_conversation_if_needed()
        text = text.strip()

        wake_word, wake_match = self._find_phrase(text, config.WAKE_WORDS)
        end_phrase, end_match = self._find_phrase(text, config.END_PHRASES)
        keywords = self._find_keywords(text)

        if wake_match is not None:
            self.conversation_active = True
            self.last_conversation_activity = time.monotonic()

        if wake_match is not None:
            command_text = text[wake_match.end():].strip(" ,.!?-")
        elif self.conversation_active:
            command_text = text
        else:
            command_text = ""

        if end_match is not None and command_text:
            command_text = _phrase_pattern(end_phrase).sub(
                "", command_text
            ).strip(" ,.!?-")

        send_to_llm = bool(self.conversation_active and command_text)

        if self.conversation_active:
            self.last_conversation_activity = time.monotonic()

        event = TranscriptEvent(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            raw_text=text,
            wake_word=wake_word,
            end_phrase=end_phrase,
            keywords=keywords,
            conversation_active=self.conversation_active,
            command_text=command_text,
            send_to_llm=send_to_llm,
        )

        if end_match is not None:
            self.conversation_active = False

        return event

    def highlighted_text(self, event: TranscriptEvent) -> str:
        text = event.raw_text
        base = Fore.CYAN if event.conversation_active else Style.RESET_ALL
        colours = [base] * len(text)
        priorities = [0] * len(text)

        def apply(phrases, priority, colour):
            for phrase in phrases:
                for match in _phrase_pattern(phrase).finditer(text):
                    for i in range(match.start(), match.end()):
                        if priority >= priorities[i]:
                            priorities[i] = priority
                            colours[i] = colour

        apply(config.KEYWORDS, 10, Fore.YELLOW)
        apply(config.WAKE_WORDS, 20, Fore.MAGENTA)

        output = []
        current = None
        for char, colour in zip(text, colours):
            if colour != current:
                output.append(colour)
                current = colour
            output.append(char)
        output.append(Style.RESET_ALL)
        return "".join(output)

    def print_event(self, event: TranscriptEvent, stt_result):
        print()
        print(f"[{event.timestamp}] " + self.highlighted_text(event))
        print(
            f"    STT {stt_result.provider} | "
            f"{stt_result.audio_seconds:.2f}s audio | "
            f"{stt_result.processing_seconds:.2f}s processing | "
            f"RTF {stt_result.rtf:.3f} | "
            f"{stt_result.x_realtime:.1f}x realtime"
        )

        if event.wake_word:
            print(Fore.MAGENTA + f"    WAKE: {event.wake_word}")
        if event.keywords:
            print(Fore.YELLOW + "    KEYWORDS: " + ", ".join(event.keywords))
        if event.command_text:
            print(Fore.CYAN + f"    COMMAND/CONTEXT: {event.command_text}")
        if event.end_phrase:
            print(Fore.BLUE + f"    END: {event.end_phrase}")
