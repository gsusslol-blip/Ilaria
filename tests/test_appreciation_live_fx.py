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

    def test_bare_hello_does_not_wait_for_the_model(self) -> None:
        def execute(name: str, arguments_json: str) -> str:
            raise AssertionError(name)

        out = try_local_command("hola", execute, Memory(), load_settings())
        self.assertIsNotNone(out)
        assert out is not None
        self.assertTrue(out.startswith("Hola"))
        self.assertIn("Acá estoy", out)

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

    def test_euro_quote_uses_cotizaciones(self) -> None:
        payload = [
            {"moneda": "USD", "casa": "oficial", "compra": 1485, "venta": 1535},
            {"moneda": "EUR", "casa": "oficial", "compra": 1714.8, "venta": 1760.2},
        ]

        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[dict[str, object]]:
                return payload

        class _Client:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *args: object) -> bool:
                return False

            def get(self, url: str, **kwargs: object) -> _Resp:
                self.url = url
                return _Resp()

        with patch("jarvis.live_facts.httpx.Client", _Client):
            from jarvis.live_facts import live_market_quote

            out = live_market_quote("cuanto esta el euro")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("1.715", out)
        self.assertIn("1.760", out)

    def test_compound_runs_each_local_piece(self) -> None:
        from jarvis.local import try_compound_commands

        def execute(name: str, arguments_json: str) -> str:
            if name == "now":
                return "12:00"
            if name == "weather":
                return "Nublado, 13 C"
            return "no"

        out = try_compound_commands(
            "que hora es y clima",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("12:00", out)
        self.assertIn("Nublado", out)

    def test_compound_leaves_a_single_phrase(self) -> None:
        from jarvis.local import try_compound_commands

        out = try_compound_commands(
            "que hora es",
            lambda name, arguments_json: "12:00",
            Memory(),
            load_settings(),
        )
        self.assertIsNone(out)

    def test_installer_qwen_is_small_and_groq_is_not(self) -> None:
        from jarvis.llm import is_small_local_model

        settings = load_settings()
        self.assertTrue(
            is_small_local_model(settings, "qwen2.5-1.5b-instruct-q4_k_m.gguf")
        )
        self.assertFalse(is_small_local_model(settings, "openai/gpt-oss-20b"))


if __name__ == "__main__":
    unittest.main()
