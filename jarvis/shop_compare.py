"""Shopping comparison — live search with anti-SEO speakable summary."""

from __future__ import annotations

import re
from typing import Callable

from jarvis.search_speak import speakable_from_search

Execute = Callable[[str, str], str]

_SHOP_HINT = re.compile(
    r"\b("
    r"mejor\s+(?:notebook|laptop|celu|celular|telefono|tel[eé]fono|tv|tele|"
    r"auricular|monitor|placa|gpu|cpu|ssd|disco|mouse|teclado|impresora|"
    r"heladera|aire|lavarropas|tablet|smartwatch|reloj)|"
    r"recomend[aá]\s+(?:una?\s+)?(?:notebook|laptop|celu|celular|tv|monitor)|"
    r"conviene\s+(?:m[aá]s\s+)?(?:comprar|la|el)|"
    r"compar(ar|á|a)\s+(?:precios?|modelos?|notebooks?|celus?|celulares?)|"
    r"cu[aá]l\s+(?:notebook|laptop|celu|celular|tv|monitor)\s+(?:comprar|conviene|es\s+mejor)|"
    r"por\s+(?:menos\s+de\s+)?\$?\d[\d\.]*\s*(?:mil|k|pesos)?|"
    r"presupuesto\s+(?:de\s+)?\$?\d|"
    r"mejor\s+relaci[oó]n\s+precio|"
    r"vale\s+la\s+pena\s+comprar|"
    r"qu[eé]\s+(?:notebook|laptop|celu|celular)\s+(?:me\s+)?(?:compro|conviene)"
    r")\b",
    re.I,
)

_SEO_JUNK = re.compile(
    r"\b("
    r"cup[oó]n|descuento\s+exclusivo|haz\s+clic|click\s+aqu[ií]|affiliate|"
    r"patrocinado|sponsored|mejores\s+ofertas\s+del\s+d[ií]a|"
    r"compr[aá]\s+ahora|env[ií]o\s+gratis\s+hoy|top\s+\d+\s+mejores\s+de\s+20\d{2}"
    r")\b",
    re.I,
)


def looks_like_shop_compare(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or len(raw) > 240:
        return False
    return bool(_SHOP_HINT.search(raw))


def _scrub_seo(raw: str) -> str:
    lines = []
    for line in (raw or "").splitlines():
        if _SEO_JUNK.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def speakable_shop_compare(raw_search: str, query: str) -> str:
    cleaned = _scrub_seo(raw_search)
    spoken = speakable_from_search(cleaned, query=query, max_words=48)
    if not spoken:
        # Last resort: take the first non-empty cleaned line.
        for line in cleaned.splitlines():
            line = line.strip(" -•")
            if len(line) >= 24 and not line.lower().startswith("source:"):
                spoken = line[:220]
                break
    if not spoken:
        return (
            "No encontré una comparación limpia ahora. "
            "Decime presupuesto y uso (estudio, juegos, oficina) y lo afino."
        )
    prefix = "Resumen rápido, sin ranking absoluto: "
    if spoken.lower().startswith("resumen"):
        return spoken
    return prefix + spoken


def run_shop_compare(text: str, execute: Execute) -> str:
    import json

    query = " ".join((text or "").split())
    # Bias search toward reviews/specs, not pure affiliate listicles.
    search_q = f"{query} comparación especificaciones review Argentina 2026"
    raw = execute("web_search", json.dumps({"query": search_q, "max_results": 5}, ensure_ascii=False))
    return speakable_shop_compare(raw, query)
