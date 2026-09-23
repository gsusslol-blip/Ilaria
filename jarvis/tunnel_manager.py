"""Optional WAN tunnel (ngrok) so phones can reach HUD :8787 off LAN.

Soft-depends on ``pyngrok``. Without NGROK_AUTHTOKEN, Ilaria stays LAN-only.
Invoked from runtime after the HUD is healthy — not as a second ``run.bat`` process.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from jarvis.config import Settings, load_settings
from jarvis.remote_bridge import remote_workspace

_lock = threading.Lock()
_public_url: str | None = None
_started = False


def sync_path(settings: Settings | None = None) -> Path:
    return remote_workspace(settings=settings) / "network_sync.json"


def read_sync_url(settings: Settings | None = None) -> str | None:
    path = sync_path(settings)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    url = str(data.get("remote_url") or "").strip().rstrip("/")
    if url.startswith("https://") or url.startswith("http://"):
        return url
    return None


def write_sync_url(public_url: str, settings: Settings | None = None) -> Path:
    path = sync_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    deep = f"ilaria://sync?url={public_url.rstrip('/')}"
    payload = {
        "remote_url": public_url.rstrip("/"),
        "deep_link": deep,
        "last_update": time.time(),
        "tunnel_active": True,
        "proto": "https" if public_url.startswith("https://") else "http",
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def qr_svg_path() -> Path:
    from jarvis.config import DATA_DIR

    folder = DATA_DIR / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "sync_qr.svg"


def generar_qr_deep_link(public_url: str) -> Path | None:
    """Write SVG QR for ilaria://sync?url=… (phone camera / Profile scanner)."""
    deep_link = f"ilaria://sync?url={public_url.rstrip('/')}"
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        print("[TUNNEL] Falta qrcode. Instalá: pip install qrcode")
        return None
    try:
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(deep_link, image_factory=factory, box_size=8, border=2)
        path = qr_svg_path()
        with path.open("wb") as handle:
            img.save(handle)
        print(f"[TUNNEL] Código QR de sincronización: {path}")
        return path
    except Exception as exc:  # noqa: BLE001
        print(f"[TUNNEL] No pude generar QR: {exc}")
        return None


def hud_network_state(settings: Settings | None = None) -> dict[str, Any]:
    """Lightweight LAN/WAN telemetry for /api/stack-health + HUD panel."""
    cfg = settings or load_settings()
    url = current_public_url() or read_sync_url(cfg)
    age = 0
    tunnel_flag = bool(current_public_url())
    path = sync_path(cfg)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            last = float(data.get("last_update") or 0)
            if last > 0:
                age = max(0, int(time.time() - last))
            if not url:
                url = str(data.get("remote_url") or "").strip().rstrip("/") or None
            tunnel_flag = tunnel_flag or bool(data.get("tunnel_active"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    mode = "lan"
    if url and age < 86400 and tunnel_flag:
        mode = "wan"
    elif url and age >= 86400:
        mode = "wan_stale"
    short = "N/A"
    if url:
        bare = url.replace("https://", "").replace("http://", "")
        short = (bare[:12] + "...") if len(bare) > 12 else bare
    alive = mode == "wan"
    return {
        "mode": mode,
        "network_mode": mode,
        "remote_url": url or "",
        "remote_url_short": short,
        "wan_url_display": short,
        "wan_tunnel_active": alive,
        "sync_file_age_seconds": age,
        "qr_ready": qr_svg_path().is_file(),
        "deep_link": f"ilaria://sync?url={url}" if url else "",
    }


def current_public_url() -> str | None:
    with _lock:
        return _public_url


_STUCK_ENDPOINT = re.compile(r"endpoint '([^']+)'")


def _ngrok_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Ngrok-Version": "2"}


def _release_tunnel_sessions(token: str) -> int:
    """Stop leftover cloud agents so a free plan can open this PC's tunnel."""
    if not token:
        return 0
    try:
        import httpx
    except ImportError:
        return 0
    headers = _ngrok_headers(token)
    stopped = 0
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.get(
                "https://api.ngrok.com/tunnel_sessions",
                headers=headers,
                params={"limit": "20"},
            )
            response.raise_for_status()
            rows = response.json().get("tunnel_sessions") or []
            print(f"[TUNNEL] Sesiones en la cuenta: {len(rows)}", flush=True)
            for item in rows:
                if not isinstance(item, dict):
                    continue
                session_id = str(item.get("id") or "").strip()
                if not session_id:
                    continue
                gone = client.post(
                    f"https://api.ngrok.com/tunnel_sessions/{session_id}/stop",
                    headers={**headers, "Content-Type": "application/json"},
                    json={},
                )
                print(f"[TUNNEL] Cierre de sesión {gone.status_code}", flush=True)
                if gone.status_code in {200, 204, 404}:
                    stopped += 1
    except Exception as exc:  # noqa: BLE001
        print(f"[TUNNEL] No pude cerrar sesiones viejas ({exc}).", flush=True)
        return stopped
    if stopped:
        print(f"[TUNNEL] Cerré {stopped} sesión(es) que habían quedado abiertas.", flush=True)
    return stopped


def _release_stuck_endpoint(token: str, message: str) -> bool:
    """Stop a cloud endpoint left online after a previous Ilaria process died."""
    match = _STUCK_ENDPOINT.search(message or "")
    if not match or not token:
        return False
    wanted = match.group(1).rstrip("/")
    try:
        import httpx
    except ImportError:
        return False
    headers = _ngrok_headers(token)
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.get(
                "https://api.ngrok.com/endpoints",
                headers=headers,
                params={"limit": "50"},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("endpoints") or payload.get("items") or []
            released = False
            for item in rows:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").rstrip("/")
                if url != wanted:
                    continue
                endpoint_id = str(item.get("id") or "").strip()
                if not endpoint_id:
                    continue
                gone = client.delete(
                    f"https://api.ngrok.com/endpoints/{endpoint_id}",
                    headers=headers,
                )
                if gone.status_code in {200, 204, 404}:
                    released = True
            return released
    except Exception as exc:  # noqa: BLE001
        print(f"[TUNNEL] No pude liberar el dominio ocupado ({exc}).")
        return False


def _open_tunnel(ngrok_mod: object, hud_port: int, token: str) -> object:
    connect = getattr(ngrok_mod, "connect")
    try:
        return connect(hud_port, bind_tls=True)
    except Exception as exc:
        text = str(exc)
        lower = text.lower()
        session_limit = "108" in text or "simultaneous" in lower
        endpoint_busy = "334" in text or "already online" in lower
        if not session_limit and not endpoint_busy:
            raise
        api_key = os.getenv("NGROK_API_KEY", "").strip()
        if session_limit and not api_key:
            print(
                "[TUNNEL] El plan gratis ya tiene 3 agentes abiertos. "
                "Cerrá los viejos en https://dashboard.ngrok.com/agents y volvé a abrir Ilaria. "
                "En la misma Wi-Fi no hace falta el puente.",
                flush=True,
            )
            raise
        print("[TUNNEL] El enlace anterior sigue tomado. Lo suelto y reintento.", flush=True)
        if api_key:
            _release_tunnel_sessions(api_key)
            if endpoint_busy:
                _release_stuck_endpoint(api_key, text)
        kill = getattr(ngrok_mod, "kill", None)
        if kill is not None:
            try:
                kill()
            except Exception:
                pass
        time.sleep(3.0)
        return connect(hud_port, bind_tls=True)


def inicializar_tunel_remoto(
    settings: Settings | None = None,
    *,
    port: int | None = None,
) -> str | None:
    """Bring up ngrok HTTPS reverse tunnel to the HUD port; persist network_sync.json."""
    global _public_url, _started
    cfg = settings or load_settings()
    token = os.getenv("NGROK_AUTHTOKEN", "").strip()
    if not token:
        print("[TUNNEL] Sin NGROK_AUTHTOKEN. Sincronización limitada a LAN (UDP 8788).")
        return None

    hud_port = int(port if port is not None else cfg.hud_port)
    try:
        from pyngrok import ngrok
    except ImportError:
        print("[TUNNEL] Falta pyngrok. Instalá: pip install pyngrok")
        return None

    with _lock:
        if _started and _public_url:
            return _public_url
        _started = True

    try:
        ngrok.set_auth_token(token)
        try:
            ngrok.kill()
        except Exception:
            pass
        # Prefer HTTPS public URL for iOS ATS / Android cleartext policy.
        tunnel = _open_tunnel(ngrok, hud_port, token)
        public_url = str(getattr(tunnel, "public_url", "") or "").rstrip("/")
        if public_url.startswith("http://"):
            # Older pyngrok may still return http:// — upgrade scheme for clients.
            https_url = "https://" + public_url[len("http://") :]
            public_url = https_url
        if not public_url:
            print("[TUNNEL] Ngrok no devolvió public_url.")
            return None
        write_sync_url(public_url, cfg)
        generar_qr_deep_link(public_url)
        with _lock:
            _public_url = public_url
        print(f"[TUNNEL] Sincronización global activa vía WAN: {public_url}")
        print(f"[TUNNEL] Guardado en {sync_path(cfg)}")
        return public_url
    except Exception as exc:  # noqa: BLE001
        print(f"[TUNNEL] Error al inicializar puente seguro: {exc}")
        with _lock:
            _started = False
        return None


def start_tunnel_background(settings: Settings) -> None:
    """Non-blocking warm of the WAN tunnel after HUD bind."""

    def _run() -> None:
        inicializar_tunel_remoto(settings)

    threading.Thread(target=_run, name="ilaria-ngrok", daemon=True).start()


def wants_sync_request(text: str) -> bool:
    lower = (text or "").strip().lower()
    if not lower:
        return False
    # Exact / command forms from Telegram buttons and Profile deep-links.
    if lower in {
        "sincronizar",
        "/sincronizar",
        "ilaria_request_sync_url",
        "/ilaria_request_sync_url",
    }:
        return True
    keys = (
        "ilaria_request_sync_url",
        "sincronizar",
        "sync url",
        "url remota",
        "pedir url",
    )
    return any(k in lower for k in keys)


def sync_ack_message(settings: Settings | None = None) -> str:
    """Plain SYNC_ACK + ilaria:// deep link for Telegram → native apps."""
    cfg = settings or load_settings()
    url = current_public_url() or read_sync_url(cfg)
    if not url:
        return "SYNC_ERR: El túnel reverso aún no ha escrito credenciales de red."
    return (
        f"SYNC_ACK:{url}\n\n"
        f"Toque el siguiente enlace para actualizar la configuración de su app nativa:\n"
        f"ilaria://sync?url={url}"
    )



if __name__ == "__main__":
    inicializar_tunel_remoto()
