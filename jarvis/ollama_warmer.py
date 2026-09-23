"""Warm Ollama model into VRAM/RAM at HUD boot (avoid first-turn cold load)."""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx

from jarvis.config import Settings


def _ollama_base(settings: Settings) -> str:
    raw = (
        getattr(settings, "ollama_base_url", None)
        or os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    )
    base = str(raw).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/") or "http://127.0.0.1:11434"


def pick_warm_model(configured: str, installed: list[str], preferred: str) -> str | None:
    """Choose a model Ollama actually has. Cloud ids are not local weights."""
    from jarvis.llm import looks_like_cloud_model

    names = [str(name).strip() for name in installed if str(name).strip()]
    chosen = (configured or "").strip()
    if chosen and not looks_like_cloud_model(chosen):
        if not names or any(name == chosen or name.split(":", 1)[0] == chosen.split(":", 1)[0] for name in names):
            return chosen
    want = (preferred or "gemma2:2b").strip() or "gemma2:2b"
    family = want.split(":", 1)[0]
    for name in names:
        if name == want or name.split(":", 1)[0] == family:
            return name
    return names[0] if names else None


def _configured_model(settings: Settings) -> str:
    return (
        (getattr(settings, "llm_model", None) or os.getenv("LLM_MODEL") or "")
        .strip()
    )


def warm_ollama_once(settings: Settings) -> dict[str, Any]:
    """POST a tiny generate so the local weights stay resident."""
    if os.getenv("OLLAMA_WARM", "1").strip().lower() in {"0", "false", "off", "no"}:
        return {"status": "skipped", "reason": "OLLAMA_WARM=0"}
    base = _ollama_base(settings)
    keep = os.getenv("OLLAMA_KEEP_ALIVE", "60m").strip() or "60m"
    preferred = (getattr(settings, "ollama_model", None) or "gemma2:2b").strip() or "gemma2:2b"
    try:
        with httpx.Client(timeout=90.0) as client:
            tags = client.get(f"{base}/api/tags")
            if tags.status_code >= 400:
                return {"status": "down", "code": tags.status_code}
            installed = [
                str(item.get("name") or "")
                for item in (tags.json().get("models") or [])
                if isinstance(item, dict)
            ]
            model = pick_warm_model(_configured_model(settings), installed, preferred)
            if not model:
                return {"status": "skipped", "reason": "no-local-model"}
            resp = client.post(
                f"{base}/api/generate",
                json={
                    "model": model,
                    "prompt": ".",
                    "stream": False,
                    "keep_alive": keep,
                    "options": {"num_predict": 1},
                },
            )
            if resp.status_code >= 400:
                return {"status": "error", "code": resp.status_code, "body": resp.text[:200]}
        return {"status": "ok", "model": model, "keep_alive": keep}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:200]}


def start_ollama_warm(settings: Settings) -> None:
    """Background warm so HUD starts immediately."""

    def _run() -> None:
        report = warm_ollama_once(settings)
        status = report.get("status")
        if status == "ok":
            print(f"[WARM_UP] Ollama ready: {report.get('model')} keep_alive={report.get('keep_alive')}")
        elif status == "skipped":
            if report.get("reason") not in {"cloud-model", "no-local-model"}:
                print("[WARM_UP] Ollama warm skipped")
        elif status == "down":
            print("[WARM_UP] Ollama not reachable — skip warm")
        else:
            print(f"[WARM_UP] Ollama warm: {report}")

    threading.Thread(target=_run, name="ilaria-ollama-warm", daemon=True).start()
