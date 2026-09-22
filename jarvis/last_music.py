"""Last played music — resolve vague 'poné eso / lo de ayer'."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_LAST_NAME = "last_music.json"


def _path(workspace: Path) -> Path:
    return workspace / _LAST_NAME


def save_last_music(
    workspace: Path,
    query: str,
    platform: str = "youtube",
    *,
    timezone: str = "America/Argentina/Buenos_Aires",
) -> None:
    q = " ".join((query or "").split()).strip()
    if not q:
        return
    now = datetime.now(ZoneInfo(timezone))
    payload = {
        "query": q,
        "platform": (platform or "youtube").strip().lower() or "youtube",
        "when_iso": now.isoformat(timespec="seconds"),
        "day": now.strftime("%Y-%m-%d"),
    }
    try:
        _path(workspace).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def load_last_music(workspace: Path) -> dict[str, Any] | None:
    path = _path(workspace)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    q = str(data.get("query") or "").strip()
    if not q:
        return None
    return data


def _music_from_journal(workspace: Path, day: str) -> dict[str, Any] | None:
    path = workspace / f"diario_{day}.txt"
    if not path.exists():
        return None
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    # Prefer the last music line of that day.
    for line in reversed(rows):
        m = re.search(r"M[uú]sica:\s*(.+)$", line, re.I)
        if m:
            q = m.group(1).strip()
            if q:
                return {"query": q, "platform": "youtube", "day": day, "source": "journal"}
    return None


def resolve_replay_music(
    text: str,
    workspace: Path,
    *,
    timezone: str = "America/Argentina/Buenos_Aires",
) -> dict[str, Any] | None:
    """If the ask is vague replay, return {query, platform}."""
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if not re.search(
        r"\b("
        r"pon(?:eme|[eé])?\s+(?:eso|eso\s+mismo|lo\s+mismo|lo\s+de\s+antes|lo\s+anterior|"
        r"lo\s+de\s+ayer|lo\s+[uú]ltimo|la\s+[uú]ltima(?:\s+canci[oó]n)?|"
        r"esa\s+canci[oó]n|el\s+tema)|"
        r"reproduc[ií]\s+(?:eso|lo\s+mismo|lo\s+de\s+ayer|lo\s+[uú]ltimo)|"
        r"otra\s+vez\s+(?:eso|lo\s+mismo|la\s+canci[oó]n)|"
        r"de\s+nuevo\s+(?:eso|lo\s+mismo)|"
        r"la\s+[uú]ltima\s+canci[oó]n|"
        r"lo\s+que\s+(?:escuch[eé]|puse|pusimos)\s+(?:ayer|antes|hoy)"
        r")\b",
        lower,
    ):
        return None

    want_yesterday = bool(re.search(r"\bayer\b", lower))
    now = datetime.now(ZoneInfo(timezone))
    today = now.strftime("%Y-%m-%d")
    yday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    if want_yesterday:
        hit = _music_from_journal(workspace, yday)
        if hit:
            return hit
        last = load_last_music(workspace)
        if last and str(last.get("day") or "") == yday:
            return last
        # Fall through: still try last known track with a note via caller.
        if last:
            return {**last, "fallback": "not_yesterday"}
        return None

    last = load_last_music(workspace)
    if last:
        return last
    hit = _music_from_journal(workspace, today) or _music_from_journal(workspace, yday)
    return hit
