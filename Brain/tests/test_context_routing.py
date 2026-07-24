from __future__ import annotations

import unittest

from bx1_modules.context_routing import (
    claims_unverified_robot_observation,
    contains_live_data_denial,
    requests_local_documents,
    should_retrieve_local_documents,
    strip_live_data_denial_sentences,
)
from bx1_modules.document_rag import DocumentRAGStore


class ContextRoutingTests(unittest.TestCase):
    def test_casual_chat_does_not_search_documents(self) -> None:
        for message in (
            "Hi hows things?",
            "So whats new?",
            "Sorry what are you talking about?",
            "What do you mean?",
        ):
            with self.subTest(message=message):
                self.assertFalse(should_retrieve_local_documents(message))

    def test_live_news_route_excludes_documents(self) -> None:
        message = "Can you have a look at the BBC news site and see whats going on?"
        self.assertFalse(should_retrieve_local_documents(message, live_route="news"))
        self.assertFalse(requests_local_documents(message))

    def test_technical_and_explicit_manual_requests_are_retained(self) -> None:
        for message in (
            "What does encoder service life reached mean?",
            "How do I replace the encoder on the servo drive?",
            "Check the manual for AL status code A704",
            "/docs A704 encoder service life",
        ):
            with self.subTest(message=message):
                self.assertTrue(should_retrieve_local_documents(message))

    def test_document_query_terms_drop_conversational_noise(self) -> None:
        self.assertEqual(DocumentRAGStore._query_terms("So whats new?"), [])
        self.assertIn("a704", DocumentRAGStore._query_terms("What does A704 mean?"))

    def test_live_access_disclaimer_is_detected_and_removed(self) -> None:
        reply = "I cannot directly access or browse the BBC website. The Brain App fetched BBC News headlines."
        self.assertTrue(contains_live_data_denial(reply))
        cleaned = strip_live_data_denial_sentences(reply)
        self.assertNotIn("cannot", cleaned.lower())
        self.assertIn("fetched BBC News", cleaned)

    def test_unverified_log_claim_is_detected(self) -> None:
        self.assertTrue(claims_unverified_robot_observation("I noticed a few error codes popping up in the logs."))
        self.assertTrue(claims_unverified_robot_observation("I am just running the usual diagnostics and monitoring system status."))
        self.assertTrue(claims_unverified_robot_observation("Everything seems stable, according to my systems."))
        self.assertFalse(claims_unverified_robot_observation("The manual says A704 is an encoder service-life warning."))


if __name__ == "__main__":
    unittest.main()
