"""Home Assistant scene / routine helpers — owner-oriented, allowlisted."""

from __future__ import annotations

import re
from typing import Any

import httpx

from jarvis.config import Settings
from jarvis.ha_guard import HaDenied, authorize_ha_call


def _fold(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n")
        .replace("_", " ")
        .replace(".", " ")
    )


def parse_ha_routine(text: str) -> tuple[str, str] | None:
    """Return (kind, name) where kind is scene|script, or None."""
    raw = (text or "").strip()
    lower = raw.lower()
    if not raw:
        return None
    m = re.search(
        r"\b(?:activ[aá]|ejecut[aá]|cor[r]?[eé]|dispar[aá]|pon[eé])\s+"
        r"(?:la\s+)?(?:escena|scene|rutina|script|automatizaci[oó]n)\s+"
        r"(?:de\s+|del?\s+)?(.+)$",
        raw,
        re.I,
    )
    if m:
        name = m.group(1).strip(" .")
        kind = "script" if re.search(r"\b(script|rutina|automatizaci[oó]n)\b", lower) else "scene"
        if 1 < len(name) <= 80:
            return kind, name
    m = re.search(r"\bmodo\s+([a-záéíóúñ0-9_\-\s]{2,40})$", lower)
    if m:
        return "scene", m.group(1).strip()
    # Direct entity id
    m = re.search(r"\b((?:scene|script)\.[a-z0-9_]+)\b", lower)
    if m:
        eid = m.group(1)
        return eid.split(".", 1)[0], eid
    return None


def _list_entities(settings: Settings, domain: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {settings.ha_token}"}
    with httpx.Client(timeout=12.0) as client:
        response = client.get(settings.ha_url.rstrip("/") + "/api/states", headers=headers)
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("entity_id") or "")
        if not eid.startswith(f"{domain}."):
            continue
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        friendly = str(attrs.get("friendly_name") or eid.split(".", 1)[-1])
        out.append({"entity_id": eid, "name": friendly, "state": item.get("state")})
    return out


def resolve_entity(settings: Settings, domain: str, name: str) -> str | None:
    needle = _fold(name)
    if needle.startswith(f"{domain} "):
        # already entity-like without dot
        candidate = f"{domain}.{needle.split(' ', 1)[-1].replace(' ', '_')}"
        return candidate
    if name.startswith(f"{domain}."):
        return name.strip().lower()
    try:
        rows = _list_entities(settings, domain)
    except Exception:
        return None
    best = None
    best_score = 0
    for row in rows:
        eid = str(row["entity_id"])
        fname = _fold(str(row["name"]))
        slug = _fold(eid.split(".", 1)[-1])
        score = 0
        if needle == fname or needle == slug:
            score = 100
        elif needle in fname or needle in slug:
            score = 60 + min(len(needle), 20)
        elif fname in needle:
            score = 40
        if score > best_score:
            best_score = score
            best = eid
    return best if best_score >= 40 else None


def run_ha_routine(
    settings: Settings,
    *,
    kind: str,
    name: str,
    is_owner: bool,
) -> str:
    if not settings.has_ha:
        return "Home Assistant no está configurado. Agregá HA_URL y HA_TOKEN en .env."
    domain = "script" if kind == "script" else "scene"
    entity = resolve_entity(settings, domain, name) if "." not in name else name.strip().lower()
    if not entity:
        return (
            f"No encontré la {domain} «{name}». "
            "Pedime home_states domain=scene (o script) para ver nombres."
        )
    try:
        spec = authorize_ha_call(
            domain=domain,
            service="turn_on",
            entity_id=entity,
            is_owner=is_owner,
        )
    except HaDenied as exc:
        return str(exc)
    url = settings.ha_url.rstrip("/") + f"/api/services/{spec['domain']}/{spec['service']}"
    headers = {
        "Authorization": f"Bearer {settings.ha_token}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, headers=headers, json=spec["payload"] or None)
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return f"Home Assistant falló: {exc}"
    label = "escena" if domain == "scene" else "rutina"
    return f"Listo, activé la {label} {entity}."
