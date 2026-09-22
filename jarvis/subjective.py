"""Subjective taste + soft philosophy — fixed tone, never web_search."""

from __future__ import annotations

import re

# Taste / ranking people or favorites.
APPRECIATION_RE = re.compile(
    r"\b("
    r"m[aá]s\s+lind[oa]|m[aá]s\s+hermos[oa]|m[aá]s\s+guap[oa]|m[aá]s\s+bonit[oa]|"
    r"m[aá]s\s+fea|m[aá]s\s+feo|m[aá]s\s+atractiv|"
    r"qui[eé]n\s+es\s+m[aá]s|prefer[ií]s|te\s+gusta\s+m[aá]s|prefer[ií]s\s+a|"
    r"cu[aá]l\s+(?:te\s+)?gusta\s+m[aá]s|qui[eé]n\s+(?:te\s+)?cae\s+mejor|"
    r"m[aá]s\s+rico|m[aá]s\s+rica|favorit[oa]|tu\s+favorit|"
    r"qui[eé]n\s+es\s+mejor|qui[eé]n\s+mejor|mejor\s+entre|"
    r"messi\s+o\s+cr7|cr7\s+o\s+messi"
    r")\b",
    re.I,
)

APPRECIATION_REPLY = (
    "Eso es gustos, no hay una respuesta objetiva. "
    "Contame qué preferís vos y lo bancamos — yo no armo ranking de personas ni de gustos."
)

# Open-ended philosophy / politics / meaning-of-life — fixed humble tone.
PHILOSOPHY_RE = re.compile(
    r"\b("
    r"sentido\s+de\s+la\s+vida|para\s+qu[eé]\s+vivimos|qu[eé]\s+es\s+la\s+felicidad|"
    r"existe\s+dios|hay\s+dios|dios\s+existe|"
    r"qu[eé]\s+es\s+el\s+amor|qu[eé]\s+es\s+la\s+verdad|"
    r"libre\s+albedr[ií]o|destino\s+o\s+casualidad|"
    r"opin[ií]on\s+(?:pol[ií]tica|sobre\s+pol[ií]tica)|"
    r"qui[eé]n\s+deber[ií]a\s+gobernar|a\s+qui[eé]n\s+voto|"
    r"izquierda\s+o\s+derecha|peronismo\s+o\s+|"
    r"es\s+moral(?:mente)?\s+(?:bien|mal)|est[aá]\s+bien\s+o\s+mal\s+que|"
    r"filosof[ií]a\s+de\s+vida|pens[aá]s\s+que\s+la\s+vida|"
    r"cre[eé]s\s+en\s+(?:dios|el\s+destino|el\s+karma)"
    r")\b",
    re.I,
)

PHILOSOPHY_REPLY = (
    "Eso no tiene una verdad única que yo pueda certificar. "
    "Te doy un marco corto: viví alineado con tus valores, cuidá a los tuyos, "
    "y elegí con información — el resto es conversación, no dogma. "
    "Si querés, bajamos el tema a algo concreto que sí podamos resolver hoy."
)


def fixed_subjective_reply(text: str) -> str | None:
    """Return a fixed reply for appreciation or philosophy, else None."""
    raw = (text or "").strip()
    if not raw:
        return None
    if APPRECIATION_RE.search(raw):
        return APPRECIATION_REPLY
    if PHILOSOPHY_RE.search(raw):
        return PHILOSOPHY_REPLY
    return None
