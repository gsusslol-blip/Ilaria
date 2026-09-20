"""Translation parsing + live HTTP translate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.translate import parse_translate_request, speakable_translation, translate_text


class TranslateTests(unittest.TestCase):
    def test_parse_variants(self) -> None:
        self.assertEqual(
            parse_translate_request("traducí hello world"),
            ("hello world", "auto", "es"),
        )
        self.assertEqual(
            parse_translate_request("traducí al inglés: hola mundo"),
            ("hola mundo", "auto", "en"),
        )
        self.assertEqual(
            parse_translate_request("cómo se dice hola en inglés"),
            ("hola", "auto", "en"),
        )
        self.assertEqual(
            parse_translate_request("qué significa hello"),
            ("hello", "auto", "es"),
        )

    def test_speakable(self) -> None:
        out = speakable_translation(
            {"ok": True, "text": "hola mundo", "target": "es"},
            original="hello world",
        )
        self.assertIn("hola mundo", out)
        self.assertIn("español", out)

    @patch("jarvis.translate.httpx.Client")
    def test_gtx_path(self, client_cls: MagicMock) -> None:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [[["Hola mundo", "Hello world", None, None]], None, "en"]
        client.get.return_value = resp
        result = translate_text("Hello world", target="es")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "Hola mundo")
        self.assertEqual(result["provider"], "gtx")


if __name__ == "__main__":
    unittest.main()
