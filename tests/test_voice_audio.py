"""Voice prefs + wake pause + search cache smoke."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.search_cache import format_hit, lookup, store
from jarvis.voice_prefs import load_voice_prefs, save_voice_prefs
from jarvis.wake_control import hud_listening, set_hud_listening


class VoiceAudioTests(unittest.TestCase):
    def test_wake_pause_flag(self) -> None:
        set_hud_listening(False)
        self.assertFalse(hud_listening())
        set_hud_listening(True)
        self.assertTrue(hud_listening())
        set_hud_listening(False)
        self.assertFalse(hud_listening())

    def test_voice_prefs_roundtrip(self) -> None:
        before = load_voice_prefs()
        saved = save_voice_prefs(
            {
                "wake_sensitivity": 0.7,
                "wake_mic_index": -1,
                "faster_whisper_model": "tiny",
                "stt_language": "es",
            }
        )
        self.assertEqual(saved["wake_sensitivity"], 0.7)
        self.assertEqual(saved["faster_whisper_model"], "tiny")
        # restore prior model preference without wiping file structure
        save_voice_prefs(
            {
                "wake_sensitivity": before.get("wake_sensitivity", 0.55),
                "faster_whisper_model": before.get("faster_whisper_model") or "",
                "stt_language": before.get("stt_language") or "es",
            }
        )

    def test_search_cache_no_meta_header(self) -> None:
        td = Path(tempfile.mkdtemp())
        store("capital de francia", "Source: bing\n- París", td, kind="web")
        hit = lookup("capital de francia", td, kind="web")
        self.assertIsNotNone(hit)
        assert hit is not None
        text = format_hit(hit)
        self.assertNotIn("SEARCH_CACHE", text)
        self.assertIn("París", text)


if __name__ == "__main__":
    unittest.main()
