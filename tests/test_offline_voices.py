"""Offline voice fallback stays in the selected language."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.piper_tts import piper_model
from jarvis.voices import resolve_runtime


class OfflineVoiceTests(unittest.TestCase):
    def test_elsa_keeps_italian_piper_when_the_file_exists(self) -> None:
        with patch("jarvis.voices._piper_file_exists", return_value=True):
            runtime = resolve_runtime("elsa")
        self.assertEqual(runtime["provider"], "edge")
        self.assertEqual(runtime["tts_voice"], "it-IT-ElsaNeural")
        self.assertEqual(runtime["piper_model"], "it_IT-paola-medium.onnx")

    def test_jenny_keeps_english_piper_when_the_file_exists(self) -> None:
        with patch("jarvis.voices._piper_file_exists", return_value=True):
            runtime = resolve_runtime("jenny")
        self.assertEqual(runtime["provider"], "edge")
        self.assertEqual(runtime["piper_model"], "en_US-lessac-medium.onnx")

    def test_missing_named_voice_does_not_become_spanish(self) -> None:
        self.assertIsNone(piper_model("it_IT-does-not-exist.onnx"))


if __name__ == "__main__":
    unittest.main()
