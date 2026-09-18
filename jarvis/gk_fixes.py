"""Hard GK answers that small LLMs often invent wrong — checked before search/LLM."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jarvis.config import DATA_DIR, ROOT

# Bundled defaults (shipped with the repo).
_BUILTIN: dict[str, str] = {
    "mamifero mas grande": "La ballena azul.",
    "mamífero más grande": "La ballena azul.",
    "animal terrestre mas rapido": "El guepardo.",
    "animal terrestre más rápido": "El guepardo.",
    "metal liquido temperatura ambiente": "Mercurio.",
    "metal líquido a temperatura ambiente": "Mercurio.",
    "pais forma de bota": "Italia.",
    "país tiene forma de bota": "Italia.",
    "estomagos tiene una vaca": "Uno, con cuatro compartimentos (rumiante).",
    "estómagos tiene una vaca": "Uno, con cuatro compartimentos (rumiante).",
    "touchdown puntos": "6 (7 si cuenta el punto extra).",
    "planetas sistema solar": "Hay ocho planetas en el sistema solar.",
    "cuantos planetas": "Hay ocho planetas en el sistema solar.",
    "temperatura hierve el agua": "100 °C a nivel del mar.",
    "agua hierve": "100 °C a nivel del mar.",
    "simbolo fe": "Fe es hierro.",
    "símbolo fe": "Fe es hierro.",
    "moneda de argentina": "El peso argentino.",
}

_ACCENT = str.maketrans("áéíóúüñ", "aeiouun")


def _norm(text: str) -> str:
    raw = " ".join((text or "").lower().translate(_ACCENT).split())
    raw = re.sub(r"[¿?¡!.,;:]+", " ", raw)
    return " ".join(raw.split())


def _load_overlay() -> dict[str, str]:
    """Optional local overrides in data/gk_fixes.json (not committed)."""
    path = DATA_DIR / "gk_fixes.json"
    if not path.is_file():
        bundled = ROOT / "jarvis" / "gk_fixes.json"
        path = bundled if bundled.is_file() else path
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if str(v).strip()}


def lookup_gk_fix(text: str) -> str | None:
    """Return a fixed answer if the user question matches a known hard fact."""
    q = _norm(text)
    if len(q) < 8:
        return None
    table = dict(_BUILTIN)
    table.update({_norm(k): v for k, v in _load_overlay().items()})
    # Exact / contains key (longest key wins).
    hits = [(k, v) for k, v in table.items() if k and (k in q or q in k)]
    if not hits:
        # Token overlap ≥ 2 meaningful words from key.
        q_toks = set(re.findall(r"[a-z0-9]{3,}", q))
        scored: list[tuple[int, str, str]] = []
        for k, v in table.items():
            k_toks = set(re.findall(r"[a-z0-9]{3,}", k))
            score = len(q_toks & k_toks)
            if score >= max(2, min(3, len(k_toks))):
                scored.append((score, k, v))
        if not scored:
            return None
        scored.sort(key=lambda row: (-row[0], -len(row[1])))
        return scored[0][2]
    hits.sort(key=lambda row: -len(row[0]))
    return hits[0][1]
