"""Speakable search dump → one short sentence."""

from __future__ import annotations

import unittest

from jarvis.search_speak import clean_search_results, looks_like_search_dump, speakable_from_search


class SearchSpeakTests(unittest.TestCase):
    def test_latest_fact_prefers_this_year(self) -> None:
        raw = (
            "Source: yahoo (2 hits).\n"
            "- Mundial 2022\n"
            "  https://example.com/2022\n"
            "  Argentina ganó el último Mundial, en 2022, venciendo a Francia.\n"
            "- Mundial 2026\n"
            "  https://example.com/2026\n"
            "  España ganó el Mundial 2026 al vencer 1-0 a Argentina.\n"
        )
        out = speakable_from_search(raw, "quien gano el ultimo mundial", max_words=40)
        self.assertIn("2026", out)
        self.assertNotIn("2022", out)

    def test_office_line_leads_with_the_current_holder(self) -> None:
        from jarvis.actions import _wiki_speakable

        out = _wiki_speakable(
            "El presidente es el jefe de Estado. "
            "El actual presidente, Javier Milei, tomó posesión el 10 de diciembre de 2023."
        )
        self.assertTrue(out.lower().startswith("el actual presidente"))
        self.assertIn("Milei", out)

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

    def test_prefers_respuesta_over_timeline_noise(self) -> None:
        raw = (
            "Source: duckduckgo (4 hits).\n"
            "- quien descubrio america - Brainly.lat\n"
            "  https://brainly.lat/tarea/73515900\n"
            "  Respuesta:Cristobal Colon descubrio America el 12 de Octubre de 1492.\n"
            "- Timeline: ¿ Quien descubrio America ? | Timetoast\n"
            "  https://www.timetoast.com/timelines/x\n"
            "  Descubriamerica. ¿ Quien descubrio America ? By Kensy Rojas. "
            "Lineas de Nazca.que algunos creen que es América . Cristobal Colon llega a America.\n"
        )
        out = speakable_from_search(raw, "quien descubrio America", max_words=40)
        self.assertIn("Colon", out)
        self.assertIn("1492", out)
        self.assertNotIn("Nazca", out)
        self.assertNotIn("Descubriamerica", out)

    def test_keeps_historical_dates(self) -> None:
        raw = "Cristóbal Colón llegó a América el 12 de octubre de 1492."
        out = clean_search_results(raw)
        self.assertIn("1492", out)

    def test_rejects_offtopic_f1_junk(self) -> None:
        raw = (
            "Source: bing (5 hits).\n"
            "- Gran Premio del Qatar 2024 - Formula 1\n"
            "  https://www.formula1.com/qatar\n"
            "  Qatar Grand Prix 2024 - F1 Race - Formula 1.\n"
        )
        out = speakable_from_search(raw, "quien descubrio America", max_words=40)
        self.assertEqual(out, "")

    def test_prefers_wikipedia_colon_over_teorias(self) -> None:
        raw = (
            "Source: yahoo (2 hits).\n"
            "- Descubrimiento de América - Wikipedia\n"
            "  https://es.wikipedia.org/wiki/Descubrimiento_de_América\n"
            "  Descubrimiento de América es la denominación del acontecimiento histórico "
            "de la llegada a América el 12 de octubre de 1492, comandada por Cristóbal Colón.\n"
            "- Voz\n"
            "  https://example.com\n"
            "  Oct 12, 2020 · Hay varias teorías. Una dice que los chinos llegaron primero.\n"
        )
        out = speakable_from_search(raw, "quien descubrio America segun la historia", max_words=40)
        self.assertIn("Colón", out)
        self.assertNotIn("teorías", out.lower())


if __name__ == "__main__":
    unittest.main()
