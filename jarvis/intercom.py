"""Optional building intercom / doorbell via Home Assistant allowlist.

Configure in .env (no defaults that probe random LAN IPs):
  HA_INTERCOM_BUTTON=button.front_gate          # press to answer / buzz
  HA_INTERCOM_LOCK=lock.front_door              # owner may unlock
  HA_INTERCOM_CAMERA=camera.doorbell            # optional HA camera entity
  HA_INTERCOM_STREAM_URL=https://...            # optional live view URL
  HA_INTERCOM_APP_URL=https://... or app deep link
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from jarvis.config import Settings


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def intercom_config() -> dict[str, str]:
    return {
        "button": _env("HA_INTERCOM_BUTTON"),
        "lock": _env("HA_INTERCOM_LOCK"),
        "camera": _env("HA_INTERCOM_CAMERA"),
        "stream_url": _env("HA_INTERCOM_STREAM_URL"),
        "app_url": _env("HA_INTERCOM_APP_URL"),
    }


def intercom_configured() -> bool:
    cfg = intercom_config()
    return any(cfg.values())


def intercom_status(settings: Settings) -> dict[str, Any]:
    cfg = intercom_config()
    linked = intercom_configured()
    return {
        "linked": linked,
        "ha_ready": bool(settings.has_ha),
        "has_button": bool(cfg["button"]),
        "has_lock": bool(cfg["lock"]),
        "has_camera": bool(cfg["camera"] or cfg["stream_url"]),
        "has_app": bool(cfg["app_url"]),
    }


def _ha_call(settings: Settings, domain: str, service: str, entity_id: str) -> str:
    if not settings.has_ha:
        return "Home Assistant no está configurado (HA_URL + HA_TOKEN en .env)."
    url = settings.ha_url.rstrip("/") + f"/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {settings.ha_token}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, headers=headers, json={"entity_id": entity_id})
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return f"Intercomunicador: falló HA ({exc})."
    return "ok"


def run_intercom(
    settings: Settings,
    action: str,
    *,
    is_owner: bool = False,
    open_url=None,
) -> str:
    """Run answer | open | view | status. open_url(url)->str opens browser when provided."""
    key = (action or "").strip().lower()
    cfg = intercom_config()
    if not intercom_configured():
        return (
            "No hay intercomunicador vinculado. En .env podés poner "
            "HA_INTERCOM_BUTTON / HA_INTERCOM_LOCK / HA_INTERCOM_STREAM_URL "
            "(y HA_URL + HA_TOKEN)."
        )
    if key in {"status", "estado", "info"}:
        bits = []
        if cfg["button"]:
            bits.append(f"botón {cfg['button']}")
        if cfg["lock"]:
            bits.append(f"cerradura {cfg['lock']}")
        if cfg["camera"] or cfg["stream_url"]:
            bits.append("cámara")
        if cfg["app_url"]:
            bits.append("app")
        ha = "HA listo" if settings.has_ha else "falta HA_URL/TOKEN"
        return "Intercomunicador: " + (", ".join(bits) or "sin entidades") + f" · {ha}."

    if key in {"answer", "responder", "atender", "buzz", "abrir_portero", "timbre"}:
        if not cfg["button"]:
            return "No hay HA_INTERCOM_BUTTON configurado para atender."
        domain = cfg["button"].split(".", 1)[0]
        service = "press" if domain == "button" else "turn_on"
        result = _ha_call(settings, domain, service, cfg["button"])
        if result != "ok":
            return result
        return "Listo: toqué el intercomunicador / portero."

    if key in {"open", "abrir", "unlock", "abrir_puerta"}:
        if not cfg["lock"]:
            return "No hay HA_INTERCOM_LOCK. Para solo buzz usá «atender intercomunicador»."
        if not is_owner:
            return "Abrir la cerradura del intercomunicador es solo del dueño."
        result = _ha_call(settings, "lock", "unlock", cfg["lock"])
        if result != "ok":
            return result
        return "Cerradura del intercomunicador: unlock enviado."

    if key in {"view", "ver", "camara", "cámara", "video"}:
        url = cfg["stream_url"] or cfg["app_url"]
        if url and open_url is not None:
            return open_url(url)
        if url:
            return f"Abrí la vista del intercomunicador: {url}"
        if cfg["camera"]:
            return (
                f"Cámara HA configurada ({cfg['camera']}). "
                "Seteá HA_INTERCOM_STREAM_URL para abrir la vista en el navegador."
            )
        return "No hay cámara/stream del intercomunicador en .env."

    return (
        "Acciones de intercomunicador: status | answer/atender | open/abrir (dueño) | view/ver."
    )
