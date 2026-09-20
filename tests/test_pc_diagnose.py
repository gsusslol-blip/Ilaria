"""PC slow → local diagnose_pc, not web search."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.config import load_settings
from jarvis.fast_path import try_fast_path
from jarvis.local import try_local_command
from jarvis.memory import Memory
from jarvis.pc_diagnose import looks_like_pc_slow, speakable_pc_diagnosis


class PcDiagnoseTests(unittest.TestCase):
    def test_looks_like_pc_slow(self) -> None:
        self.assertTrue(looks_like_pc_slow("por qué mi PC anda lenta"))
        self.assertTrue(looks_like_pc_slow("hay un cuello de botella"))
        self.assertTrue(looks_like_pc_slow("qué componente me conviene cambiar"))
        self.assertFalse(looks_like_pc_slow("capital de Francia"))

    def test_local_routes_to_diagnose_pc(self) -> None:
        calls: list[str] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append(name)
            return "CPU al 10%, RAM al 40%."

        out = try_local_command(
            "por qué anda lenta la PC",
            execute,
            Memory(),
            load_settings(),
        )
        self.assertEqual(calls, ["diagnose_pc"])
        self.assertIn("CPU", out or "")

    def test_fast_path_routes(self) -> None:
        calls: list[str] = []

        def execute(name: str, arguments_json: str) -> str:
            calls.append(name)
            return "Diagnóstico listo."

        out = try_fast_path("mi computadora anda lenta", execute, surface="hud")
        self.assertIsNotNone(out)
        self.assertEqual(calls, ["diagnose_pc"])

    def test_speakable_runs(self) -> None:
        text = speakable_pc_diagnosis(
            {
                "cpu_load_pct": 90,
                "ram_load_pct": 92,
                "ram_available_gb": 0.4,
                "disk_c_free_gb": 5.0,
                "top_ram": [{"name": "chrome", "ram_mb": 1200}],
                "advice": ["Cuello principal: RAM llena."],
            }
        )
        self.assertIn("RAM", text)
        self.assertIn("chrome", text.lower())


if __name__ == "__main__":
    unittest.main()
