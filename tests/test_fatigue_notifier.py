"""Fatigue Telegram notifier unit tests (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.fatigue_notifier import (
    build_fatigue_message,
    enviar_alerta_fatiga_telegram,
    should_alert_fatigue,
)


class FatigueNotifierTests(unittest.TestCase):
    def test_should_alert_on_baja(self) -> None:
        self.assertTrue(
            should_alert_fatigue({"nivel_energia_estimado": "Baja / Estrés físico", "horas_sueno_anoche": 7})
        )

    def test_should_alert_on_short_sleep(self) -> None:
        self.assertTrue(should_alert_fatigue({"nivel_energia_estimado": "Moderada", "horas_sueno_anoche": 5.0}))

    def test_no_alert_optimal(self) -> None:
        self.assertFalse(
            should_alert_fatigue({"nivel_energia_estimado": "Óptima. Cuerpo recuperado.", "horas_sueno_anoche": 7.5})
        )

    def test_message_contains_metrics(self) -> None:
        msg = build_fatigue_message({"horas_sueno_anoche": 4.5, "hrv_ms": 32, "pasos_hoy": 900}, "gsuss")
        self.assertIn("4.5", msg)
        self.assertIn("32", msg)

    def test_send_skipped_without_token(self) -> None:
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_ALLOWED_CHAT_ID": ""}, clear=False):
            with patch("jarvis.fatigue_notifier.load_settings") as ls:
                cfg = ls.return_value
                cfg.telegram_bot_token = ""
                cfg.telegram_user_id = None
                ok = enviar_alerta_fatiga_telegram(
                    "gsuss",
                    {"nivel_energia_estimado": "Baja", "horas_sueno_anoche": 4, "hrv_ms": 30},
                    force=True,
                )
                self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
