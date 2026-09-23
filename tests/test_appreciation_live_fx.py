"""Appreciation replies stay fixed; live FX goes to search."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.config import load_settings
from jarvis.local import _APPRECIATION_REPLY, try_local_command
from jarvis.memory import Memory


class AppreciationAndLiveFxTests(unittest.TestCase):
    def test_appreciation_standard_reply(self) -> None:
        captured: list[str] = []

        def execute(name: str, arguments_json: str) -> str:
            captured.append(name)
            return "OK"

        out = try_local_command(
            "quién es más linda, A o B",
            execute,
            Memory(),
            load_settings(),
            surface="hud",
        )
        self.assertEqual(out, _APPRECIATION_REPLY)
        self.assertEqual(captured, [])

    def test_favorite_also_appreciation(self) -> None:
        def execute(name: str, arguments_json: str) -> str:
            return "OK"

        out = try_local_command(
            "cuál te gusta más",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertEqual(out, _APPRECIATION_REPLY)

    def test_dolar_uses_live_quote_when_available(self) -> None:
        def execute(name: str, arguments_json: str) -> str:
            raise AssertionError(name)

        with patch("jarvis.live_facts.live_market_quote", return_value="El dólar blue está a 1540 pesos la compra y 1560 la venta."):
            out = try_local_command(
                "a cuánto está el dólar blue",
                execute,
                Memory(),
                load_settings(),
            )
        self.assertIn("1540", out or "")
        self.assertNotIn("Source:", out or "")

    def test_dolar_triggers_live_search(self) -> None:
        calls: list[tuple[str, dict]] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append((name, json.loads(arguments_json)))
            return (
                "Source: yahoo (1 hits).\n"
                "- Dólar blue hoy\n"
                "  https://example.com/blue\n"
                "  El dólar blue cotiza a 1200 pesos para la venta.\n"
            )

        with patch("jarvis.live_facts.live_market_quote", return_value=None):
            out = try_local_command(
                "a cuánto está el dólar blue",
                execute,
                Memory(),
                load_settings(),
            )
        self.assertTrue(calls)
        self.assertEqual(calls[0][0], "web_search")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertNotIn("Source:", out)
        self.assertRegex(out.lower(), r"1200|dólar|dolar|peso")


if __name__ == "__main__":
    unittest.main()
