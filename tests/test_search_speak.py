"""Speakable search dump → one short sentence."""

from __future__ import annotations

import unittest

from jarvis.search_speak import clean_search_results, looks_like_search_dump, speakable_from_search


class SearchSpeakTests(unittest.TestCase):
    def test_strips_dump_to_one_line(self) -> None:
        raw = (
            "Source: bing (5 hits).\n"
            "- París - Wikipedia\n"
            "  https://es.wikipedia.org/wiki/París\n"
            "  París es la capital de Francia y su ciudad más poblada.\n"
            "- Otro\n"
            "  https://example.com\n"
            "  Texto irrelevante sobre turismo.\n"
        )
        out = speakable_from_search(raw, "capital de Francia", max_words=40)
        self.assertTrue(out)
        self.assertNotIn("http", out.lower())
        self.assertNotIn("Source:", out)
        self.assertIn("París", out)
        self.assertLessEqual(len(out.split()), 40)

    def test_clean_search_results_string(self) -> None:
        raw = "12 May 2024 — https://x.com [1] París es la capital de Francia."
        out = clean_search_results(raw)
        self.assertNotIn("http", out.lower())
        self.assertNotIn("[1]", out)
        self.assertIn("París", out)

    def test_detects_dump(self) -> None:
        self.assertTrue(looks_like_search_dump("Source: yahoo (3 hits).\n- a\n  http://x.com"))
        self.assertFalse(looks_like_search_dump("La capital de Francia es París."))


if __name__ == "__main__":
    unittest.main()
