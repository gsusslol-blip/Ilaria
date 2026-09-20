"""Grey-area improvements: windows howto, lan, shop, journal, music replay, philosophy."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.actions import Actions
from jarvis.bus import EventBus
from jarvis.config import load_settings
from jarvis.last_music import resolve_replay_music, save_last_music
from jarvis.local import try_local_command
from jarvis.memory import Memory
from jarvis.self_healing import check_lan_status, speakable_lan_status
from jarvis.shop_compare import looks_like_shop_compare, speakable_shop_compare
from jarvis.subjective import PHILOSOPHY_REPLY, fixed_subjective_reply
from jarvis.windows_howto import match_windows_howto, speakable_windows_howto


class GreyAreaImprovementsTests(unittest.TestCase):
    def test_windows_howto_uninstall(self) -> None:
        g = match_windows_howto("cómo desinstalo un programa en Windows")
        self.assertIsNotNone(g)
        assert g is not None
        self.assertEqual(g.key, "uninstall")
        spoken = speakable_windows_howto(g)
        self.assertIn("Desinstalar", spoken)

    def test_windows_howto_hosts(self) -> None:
        g = match_windows_howto("dónde está el archivo de hosts")
        self.assertIsNotNone(g)
        assert g is not None
        self.assertEqual(g.key, "hosts")

    def test_windows_howto_local_route(self) -> None:
        calls: list[tuple[str, dict]] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append((name, json.loads(arguments_json)))
            return "OK"

        out = try_local_command(
            "cómo desinstalo un programa",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertTrue(calls)
        self.assertEqual(calls[0][0], "windows_howto")
        self.assertIsNotNone(out)

    def test_lan_deep_keys(self) -> None:
        settings = load_settings()
        lan = check_lan_status(settings)
        for key in ("gateway", "dns_servers", "dns_ok", "wifi_ssid", "gateway_reachable"):
            self.assertIn(key, lan)
        spoken = speakable_lan_status(settings, lan)
        self.assertRegex(spoken.lower(), r"red|internet|dns")

    def test_lan_local_route(self) -> None:
        calls: list[str] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append(name)
            return "Red local ok."

        out = try_local_command(
            "no me anda el wifi",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertEqual(calls, ["check_lan_status"])
        self.assertEqual(out, "Red local ok.")

    def test_shop_compare_detect(self) -> None:
        self.assertTrue(looks_like_shop_compare("mejor notebook por 800 mil"))
        spoken = speakable_shop_compare(
            "- Lenovo IdeaPad review\n"
            "  https://example.com\n"
            "  La Lenovo IdeaPad con 16GB de RAM es una buena opción de estudio.\n",
            "mejor notebook por 800 mil",
        )
        self.assertRegex(spoken.lower(), r"resumen|ideapad|16")

    def test_shop_local_route(self) -> None:
        calls: list[tuple[str, dict]] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append((name, json.loads(arguments_json)))
            if name == "shop_compare":
                return "Resumen rápido: una IdeaPad con 16GB alcanza."
            return "OK"

        out = try_local_command(
            "cuál notebook conviene por 800 mil",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertEqual(calls[0][0], "shop_compare")
        self.assertIn("IdeaPad", out or "")

    def test_journal_resume_route(self) -> None:
        calls: list[tuple[str, dict]] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append((name, json.loads(arguments_json)))
            return "Te quedaste en: algo."

        out = try_local_command(
            "en qué me quedé ayer",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertEqual(calls[0][0], "read_daily_journal")
        self.assertEqual(calls[0][1].get("which"), "recent")
        self.assertIn("quedaste", (out or "").lower())

    def test_music_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            save_last_music(ws, "Arctic Monkeys", platform="youtube")
            hit = resolve_replay_music("poné eso", ws)
            self.assertIsNotNone(hit)
            assert hit is not None
            self.assertEqual(hit["query"], "Arctic Monkeys")

        calls: list[tuple[str, dict]] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append((name, json.loads(arguments_json)))
            return "Listo."

        out = try_local_command("poné eso", execute, Memory(), load_settings())
        self.assertEqual(calls[0][0], "replay_last_music")
        self.assertEqual(out, "Listo.")

    def test_philosophy_fixed(self) -> None:
        out = fixed_subjective_reply("cuál es el sentido de la vida")
        self.assertEqual(out, PHILOSOPHY_REPLY)

        def execute(name: str, arguments_json: str) -> str:
            raise AssertionError("no tools for philosophy")

        routed = try_local_command(
            "existe dios?",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertEqual(routed, PHILOSOPHY_REPLY)

    def test_actions_journal_speakable(self) -> None:
        settings = load_settings()
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            actions = Actions(settings, EventBus(), workspace=ws)
            actions.daily_journal("Terminé el informe de ventas")
            spoken = actions.speakable_journal_resume()
            self.assertIn("informe", spoken.lower())


if __name__ == "__main__":
    unittest.main()
