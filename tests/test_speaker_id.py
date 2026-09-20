"""Speaker identification — enroll / match without torch."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis import speaker_id as sid


class SpeakerIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old = sid.SPEAKERS_DIR
        self._old_index = sid._INDEX
        sid.SPEAKERS_DIR = Path(self._tmp.name) / "speakers"
        sid._INDEX = sid.SPEAKERS_DIR / "index.json"
        sid.SPEAKERS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        sid.SPEAKERS_DIR = self._old
        sid._INDEX = self._old_index

    def test_enroll_and_identify_same_voice(self) -> None:
        wav_a = sid._synth_tone_wav(180.0, seconds=2.2)
        wav_b = sid._synth_tone_wav(180.0, seconds=2.0)
        out = sid.enroll_speaker(wav_a, "alice", display_name="Alice", username="alice")
        self.assertTrue(out["ok"])
        hit = sid.identify_speaker(wav_b, filename="probe.wav", threshold=0.55)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.label, "alice")
        self.assertGreaterEqual(hit.score, 0.55)

    def test_reject_different_voice(self) -> None:
        low = sid._synth_tone_wav(110.0, seconds=2.2, seed=1)
        high = sid._synth_tone_wav(260.0, seconds=2.2, seed=99)
        sid.enroll_speaker(low, "bob", display_name="Bob")
        same = sid.identify_speaker(sid._synth_tone_wav(110.0, seconds=2.0, seed=1), threshold=0.70)
        self.assertIsNotNone(same)
        hit = sid.identify_speaker(high, filename="other.wav", threshold=0.85)
        # Different glottal + formants should fall under a high threshold.
        self.assertTrue(hit is None or hit.score < 0.85)

    def test_list_and_remove(self) -> None:
        wav = sid._synth_tone_wav(200.0, seconds=2.0)
        sid.enroll_speaker(wav, "cara")
        self.assertEqual(len(sid.list_speakers()), 1)
        self.assertTrue(sid.remove_speaker("cara"))
        self.assertEqual(sid.list_speakers(), [])


if __name__ == "__main__":
    unittest.main()
