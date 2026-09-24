"""Local calendar events in the user workspace (no Google sync required)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def _path(workspace: Path) -> Path:
    return workspace / "calendario.json"


def _load(workspace: Path) -> list[dict[str, Any]]:
    path = _path(workspace)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _save(workspace: Path, rows: list[dict[str, Any]]) -> None:
    _path(workspace).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_when(text: str, *, timezone: str) -> datetime | None:
    """Parse common Rioplatense datetime phrases into aware datetime."""
    raw = (text or "").strip().lower()
    if not raw:
        return None
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("America/Argentina/Buenos_Aires")
    now = datetime.now(tz)

    m = re.search(
        r"\b(?:el\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s+"
        r"(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\b",
        raw,
    )
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3) or now.year)
        if year < 100:
            year += 2000
        hh, mm = int(m.group(4)), int(m.group(5) or 0)
        try:
            return datetime(year, month, day, hh, mm, tzinfo=tz)
        except ValueError:
            return None

    m = re.search(
        r"\b(hoy|ma[nñ]ana|pasado\s+ma[nñ]ana)\b(?:.*?\b(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?)?",
        raw,
    )
    if m:
        base = now.replace(second=0, microsecond=0)
        word = m.group(1)
        if "pasado" in word:
            base = base + timedelta(days=2)
        elif "mañana" in word or "manana" in word:
            base = base + timedelta(days=1)
        hh = int(m.group(2) or 9)
        mm = int(m.group(3) or 0)
        return base.replace(hour=min(hh, 23), minute=min(mm, 59))

    m = re.search(r"\b(?:el\s+)?(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b"
                  r"(?:.*?\b(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?)?", raw)
    if m:
        names = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        folded = (
            raw.replace("é", "e").replace("á", "a")
        )
        target = None
        for i, name in enumerate(names):
            if name in folded:
                target = i
                break
        if target is not None:
            # Python weekday: Monday=0
            delta = (target - now.weekday()) % 7
            if delta == 0:
                delta = 7
            base = (now + timedelta(days=delta)).replace(second=0, microsecond=0)
            hh = int(m.group(1) or 9)
            mm = int(m.group(2) or 0)
            return base.replace(hour=min(hh, 23), minute=min(mm, 59))

    m = re.search(r"\b(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\b", raw)
    if m and re.search(r"\b(agend|calend|reuni[oó]n|cita)\b", raw):
        hh, mm = int(m.group(1)), int(m.group(2) or 0)
        base = now.replace(second=0, microsecond=0)
        candidate = base.replace(hour=min(hh, 23), minute=min(mm, 59))
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return candidate
    return None


def parse_calendar_request(text: str, *, timezone: str) -> tuple[str, dict[str, Any]] | None:
    """Return (action, params) or None."""
    raw = (text or "").strip()
    lower = raw.lower()
    if not raw:
        return None

    if re.search(
        r"\b(qu[eé]\s+tengo|mi\s+agenda|mis\s+eventos|calendario(?:\s+de)?|"
        r"agenda(?:\s+de)?|pr[oó]xim[oa]\s+(?:evento|cita|reuni[oó]n))\b",
        lower,
    ) and not re.search(r"\b(agend[aá]|anot[aá]\s+cita|cre[aá]\s+evento)\b", lower):
        if re.search(r"\bhoy\b", lower):
            return "today", {}
        if re.search(r"\bma[nñ]ana\b", lower):
            return "day", {"offset_days": 1}
        return "next", {"limit": 5}

    m = re.search(
        r"\b(?:agend[aá]|anot[aá]\s+(?:en\s+)?(?:la\s+)?agenda|cre[aá]\s+(?:un\s+)?evento|"
        r"pon[eé]\s+(?:en\s+)?(?:el\s+)?calendario)\s+(.+)$",
        raw,
        re.I | re.S,
    )
    if not m:
        m = re.search(
            r"\b(reuni[oó]n|cita|evento)\s+(?:con\s+|de\s+|para\s+)?(.+)$",
            raw,
            re.I | re.S,
        )
        if m and not re.search(r"\b(agend|calend|anot|record)\b", lower):
            # Bare "reunión X" without schedule verb — skip.
            return None
        if not m:
            return None
        title = m.group(0).strip()
    else:
        title = m.group(1).strip()

    when = parse_when(raw, timezone=timezone)
    if when is None:
        return None
    # Clean title: drop leading time phrases.
    clean = re.sub(
        r"^(?:para\s+)?(?:hoy|ma[nñ]ana|pasado\s+ma[nñ]ana|"
        r"el\s+\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
        r"(?:el\s+)?(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo))\s*"
        r"(?:a\s+las?\s+\d{1,2}(?::\d{2})?\s*)?",
        "",
        title,
        flags=re.I,
    ).strip(" .,")
    clean = re.sub(r"\b(?:a\s+las?\s+\d{1,2}(?::\d{2})?)\b", "", clean, flags=re.I).strip(" .,")
    if not clean:
        clean = "Evento"
    return "add", {"title": clean[:160], "when_iso": when.isoformat(timespec="minutes")}


def add_event(workspace: Path, title: str, when_iso: str) -> str:
    rows = _load(workspace)
    item = {
        "id": uuid.uuid4().hex[:10],
        "title": (title or "Evento").strip()[:160],
        "when": when_iso,
    }
    rows.append(item)
    rows.sort(key=lambda r: str(r.get("when") or ""))
    _save(workspace, rows)
    return f"Agendado: {item['title']} · {item['when']}"


def list_upcoming(
    workspace: Path,
    *,
    timezone: str,
    limit: int = 5,
    day_offset: int | None = None,
) -> str:
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("America/Argentina/Buenos_Aires")
    now = datetime.now(tz)
    rows = _load(workspace)
    out: list[str] = []
    for item in rows:
        try:
            when = datetime.fromisoformat(str(item.get("when") or ""))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=tz)
        if day_offset is not None:
            target = (now + timedelta(days=day_offset)).date()
            if when.date() != target:
                continue
        elif when < now - timedelta(minutes=1):
            continue
        title = str(item.get("title") or "Evento")
        out.append(f"{when.strftime('%a %d/%m %H:%M')} — {title}")
        if len(out) >= max(1, limit):
            break
    if not out:
        if day_offset == 0:
            return "Hoy no tenés eventos en la agenda local."
        if day_offset == 1:
            return "Mañana no tenés eventos en la agenda local."
        return "No hay próximos eventos en la agenda local."
    label = "Agenda"
    if day_offset == 0:
        label = "Hoy"
    elif day_offset == 1:
        label = "Mañana"
    return f"{label}: " + " · ".join(out)


def speakable_calendar(workspace: Path, action: str, params: dict[str, Any], *, timezone: str) -> str:
    act = (action or "").strip().lower()
    if act == "add":
        return add_event(workspace, str(params.get("title") or "Evento"), str(params.get("when_iso") or ""))
    if act == "today":
        return list_upcoming(workspace, timezone=timezone, limit=8, day_offset=0)
    if act == "day":
        return list_upcoming(
            workspace,
            timezone=timezone,
            limit=8,
            day_offset=int(params.get("offset_days") or 0),
        )
    return list_upcoming(workspace, timezone=timezone, limit=int(params.get("limit") or 5))
