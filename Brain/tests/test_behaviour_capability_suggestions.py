from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_modules.behaviour_suggestions import format_suggestion_for_workshop, suggest_behaviour_capability
from bx1_modules.behaviour_workshop import BehaviourStore, example_behaviour


class BehaviourCapabilitySuggestionTests(unittest.TestCase):
    def test_local_suggestion_produces_safe_workshop_task(self) -> None:
        suggestion = suggest_behaviour_capability([], "I want the robot to listen politely.")
        text = format_suggestion_for_workshop(suggestion)
        self.assertIn("Suggested capability sketch", text)
        self.assertIn("Task for the forge", text)
        self.assertNotIn("wheel", suggestion.task.lower())
        self.assertTrue(suggestion.trigger_phrases)

    def test_suggestion_avoids_installed_display_name(self) -> None:
        suggestion = suggest_behaviour_capability([{"name": "polite_attention_cue", "display_name": "Polite attention cue"}])
        self.assertNotEqual(suggestion.title, "Polite attention cue")

    def test_installed_trigger_phrase_matches_main_capability_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BehaviourStore(Path(tmp))
            behaviour = example_behaviour()
            behaviour["trigger_phrases"] = ["show me your curious look", "act curious"]
            store.install(behaviour)
            self.assertEqual(store.match_explicit_request("show me your curious look"), "curious_look")
            self.assertEqual(store.match_explicit_request("please do act curious"), "curious_look")

    def test_broad_command_does_not_capture_ordinary_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BehaviourStore(Path(tmp))
            store.install(example_behaviour())
            self.assertIsNone(store.match_explicit_request("do you know what time it is"))


if __name__ == "__main__":
    unittest.main()
