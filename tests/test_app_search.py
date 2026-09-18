"""Deep-link app search helpers (no real browser launch)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.actions import Actions, _search_url
from jarvis.bus import EventBus
from jarvis.config import load_settings


class AppSearchTests(unittest.TestCase):
    def test_youtube_url(self) -> None:
        url = _search_url("youtube", "yzy a")
        self.assertIn("youtube.com/results", url)
        self.assertIn("yzy", url)

    def test_app_search_launches_without_crash(self) -> None:
        settings = load_settings()
        actions = Actions(settings, EventBus())
        with patch("jarvis.actions._launch_url", return_value="Abrí brave → https://x") as launch:
            out = actions.app_search_action(
                browser="brave",
                platform="youtube",
                query="cerati crimson",
            )
            self.assertIn("cerati", out.lower())
            launch.assert_called_once()
            args, kwargs = launch.call_args
            self.assertIn("youtube.com", args[0])
            self.assertEqual(kwargs.get("browser"), "brave")


if __name__ == "__main__":
    unittest.main()
