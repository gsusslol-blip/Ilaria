"""Proactive Telegram alerts when smartwatch energy is low (no Home Assistant required).

Called after a successful health-inbox import. Uses the Bot HTTP API synchronously
so it is safe from the inbox watcher thread (no second asyncio loop).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from jarvis.brain_parser import log_to_diario
from jarvis.config import load_settings

_last_sent_at = 0.0
_COOLDOWN_SEC = 6 * 3600  # avoid spam on repeated drops


def _chat_id() -> int | None:
    cfg = load_settings()
    if cfg.telegram_user_id is not None:
        return int(cfg.telegram_user_id)
    raw = (
        os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
        or os.getenv("TELEGRAM_USER_ID", "").strip()
    )
    return int(raw) if raw.isdigit() else None


def should_alert_fatigue(metricas: dict[str, Any]) -> bool:
    energia = str(metricas.get("nivel_energia_estimado") or "").lower()
    try:
        sueno = float(metricas.get("horas_sueno_anoche") or 0)
    except (TypeError, ValueError):
        sueno = 0.0
    if "baja" in energia or "estres" in energia or "estrés" in energia:
        return True
    return sueno > 0 and sueno < 5.5


def build_fatigue_message(metricas: dict[str, Any], usuario: str) -> str:
    sueno = metricas.get("horas_sueno_anoche", "?")
    hrv = metricas.get("hrv_ms", "?")
    pasos = metricas.get("pasos_hoy", "?")
    who = (usuario or "gsuss").strip() or "gsuss"
    return (
        "ILARIA: ALERTA DE BIENESTAR\n\n"
        f"{who}, detecté fatiga alta en tu último volcado del reloj.\n"
        f"- Sueño: {sueno} hs\n"
        f"- HRV: {hrv} ms\n"
        f"- Pasos: {pasos}\n\n"
        "Sugerencia: hoy priorizá un enfoque liviano y evitá entrenamientos de alta intensidad. "
        "Lo dejé anotado en tu bitácora."
    )


def enviar_alerta_fatiga_telegram(
    usuario_activo: str,
    metricas_salud: dict[str, Any],
    *,
    force: bool = False,
) -> bool:
    """Send Telegram alert if metrics show fatigue. Returns True when a message was sent."""
    global _last_sent_at
    if not should_alert_fatigue(metricas_salud):
        return False

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip() or load_settings().telegram_bot_token
    chat_id = _chat_id()
    if not token or chat_id is None:
        print("[NOTIFIER] Fatiga detectada pero falta TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_CHAT_ID")
        return False

    now = time.time()
    if not force and (now - _last_sent_at) < _COOLDOWN_SEC:
        print("[NOTIFIER] Fatiga detectada; alerta en cooldown (evita spam).")
        return False

    mensaje = build_fatigue_message(metricas_salud, usuario_activo)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                url,
                json={"chat_id": chat_id, "text": mensaje},
            )
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"[NOTIFIER] Error enviando alerta de Telegram: {exc}")
        return False

    _last_sent_at = now
    try:
        log_to_diario(
            usuario_activo,
            f"Alerta de fatiga enviada por Telegram (sueno={metricas_salud.get('horas_sueno_anoche')}, "
            f"hrv={metricas_salud.get('hrv_ms')}).",
        )
    except Exception:
        pass
    print(f"[NOTIFIER] Alerta proactiva de fatiga enviada al celular de {usuario_activo}.")
    return True


def maybe_notify_after_inbox(usuario: str, metrics_file: str | None) -> bool:
    """Load written smartwatch_metrics.json and notify if energy is low."""
    if not metrics_file:
        return False
    from pathlib import Path

    path = Path(metrics_file)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    # Ensure energy field exists
    if not data.get("nivel_energia_estimado"):
        from jarvis.smartwatch_processor import estimar_energia

        try:
            sueno = float(data.get("horas_sueno_anoche") or 0)
            hrv = float(data.get("hrv_ms") or 0)
            data["nivel_energia_estimado"] = estimar_energia(sueno, hrv)
        except (TypeError, ValueError):
            pass
    return enviar_alerta_fatiga_telegram(usuario, data)
