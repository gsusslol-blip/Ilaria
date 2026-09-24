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
        self.assertEqual(runtime["provider"], "piper")
        self.assertEqual(runtime["tts_voice"], "it-IT-ElsaNeural")
        self.assertEqual(runtime["piper_model"], "it_IT-paola-medium.onnx")

    def test_jenny_keeps_english_piper_when_the_file_exists(self) -> None:
        with patch("jarvis.voices._piper_file_exists", return_value=True):
            runtime = resolve_runtime("jenny")
        self.assertEqual(runtime["provider"], "piper")
        self.assertEqual(runtime["piper_model"], "en_US-lessac-medium.onnx")

    def test_missing_named_voice_does_not_become_spanish(self) -> None:
        self.assertIsNone(piper_model("it_IT-does-not-exist.onnx"))

    def test_wake_phrase_keeps_the_command(self) -> None:
        from jarvis.wake import command_after_wake

        self.assertEqual(command_after_wake("Ilaria qué hora es"), "qué hora es")
        self.assertEqual(command_after_wake("hey ilaria"), "")
        self.assertIsNone(command_after_wake("qué hora es"))

    def test_warm_picks_local_model_when_the_brain_is_cloud(self) -> None:
        from jarvis.ollama_warmer import pick_warm_model

        picked = pick_warm_model(
            "openai/gpt-oss-20b",
            ["gemma2:2b"],
            "gemma2:2b",
        )
        self.assertEqual(picked, "gemma2:2b")

    def test_warm_prefers_qwen3_and_keeps_gemma(self) -> None:
        from jarvis.ollama_warmer import pick_warm_model

        both = pick_warm_model(
            "openai/gpt-oss-20b",
            ["gemma2:2b", "qwen3:1.7b"],
            "gemma2:2b",
        )
        only_gemma = pick_warm_model(
            "openai/gpt-oss-20b",
            ["gemma2:2b"],
            "gemma2:2b",
        )
        self.assertEqual(both, "qwen3:1.7b")
        self.assertEqual(only_gemma, "gemma2:2b")


if __name__ == "__main__":
    unittest.main()
