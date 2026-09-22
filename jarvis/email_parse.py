"""Parse spoken email intents into send_email args or a mailto draft."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote


def parse_email_request(text: str) -> dict[str, Any] | None:
    """
    Return dict with to/subject/body, or None.
    Accepts: 'mandá un mail a x@y.com asunto Hola cuerpo ...'
    """
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if not re.search(r"\b(mail|correo|email|e[\-\s]?mail)\b", lower):
        return None
    if not re.search(r"\b(mand[aá]|envi[aá]|escrib[ií]|redact|draft)\b", lower):
        # "abrí el mail" is open_app, not send
        return None

    to_m = re.search(
        r"\b(?:a|para)\s+([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})\b",
        raw,
        re.I,
    )
    if not to_m:
        return None
    to_addr = to_m.group(1).strip()

    sub_m = re.search(
        r"\b(?:asunto|subject)\s*[:\-]?\s*(.+?)(?=\s+\b(?:cuerpo|body|mensaje)\b|$)",
        raw,
        re.I | re.S,
    )
    body_m = re.search(
        r"\b(?:cuerpo|body|mensaje)\s*[:\-]?\s*(.+)$",
        raw,
        re.I | re.S,
    )
    subject = (sub_m.group(1).strip() if sub_m else "Sin asunto")[:160]
    body = (body_m.group(1).strip() if body_m else "")[:4000]
    if not body:
        # Remainder after address if no explicit body marker.
        rest = raw[to_m.end() :].strip(" ,.-")
        rest = re.sub(r"^(?:asunto|subject)\s*[:\-]?\s*", "", rest, flags=re.I)
        if sub_m:
            body = ""
        else:
            body = rest[:4000] if rest else "(sin cuerpo)"
    return {"to": to_addr, "subject": subject or "Sin asunto", "body": body or "(sin cuerpo)"}


def mailto_url(to: str, subject: str, body: str) -> str:
    return (
        f"mailto:{quote(to, safe='@.')}"
        f"?subject={quote(subject)}&body={quote(body)}"
    )
