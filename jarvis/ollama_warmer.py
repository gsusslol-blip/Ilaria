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


def _model_name(settings: Settings) -> str:
    return (
        (getattr(settings, "llm_model", None) or os.getenv("LLM_MODEL") or "gemma2:2b")
        .strip()
        or "gemma2:2b"
    )


def warm_ollama_once(settings: Settings) -> dict[str, Any]:
    """POST a tiny generate so weights stay resident (keep_alive)."""
    if os.getenv("OLLAMA_WARM", "1").strip().lower() in {"0", "false", "off", "no"}:
        return {"status": "skipped", "reason": "OLLAMA_WARM=0"}
    base = _ollama_base(settings)
    model = _model_name(settings)
    keep = os.getenv("OLLAMA_KEEP_ALIVE", "60m").strip() or "60m"
    url = f"{base}/api/generate"
    try:
        with httpx.Client(timeout=90.0) as client:
            # Tags ping — if Ollama is down, skip quietly.
            tags = client.get(f"{base}/api/tags")
            if tags.status_code >= 400:
                return {"status": "down", "code": tags.status_code}
            resp = client.post(
                url,
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
            print("[WARM_UP] Ollama warm skipped")
        elif status == "down":
            print("[WARM_UP] Ollama not reachable — skip warm")
        else:
            print(f"[WARM_UP] Ollama warm: {report}")

    threading.Thread(target=_run, name="ilaria-ollama-warm", daemon=True).start()
