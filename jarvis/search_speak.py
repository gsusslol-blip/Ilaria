"""Turn raw web_search dumps into one short speakable sentence (Yui / TTS).

No extra LLM call — regex/parser only, so latency stays flat.
"""

from __future__ import annotations

import re

# Injected into the research synth turn (Groq/Ollama) after tools return.
SEARCH_SPEAK_INSTRUCTION = (
    "Vas a recibir datos de una búsqueda web. Respondé la duda del usuario en "
    "UNA sola oración fluida, natural y en español rioplatense. "
    "No cites fuentes, no uses viñetas, no digas 'según el sitio X' ni 'Source:'. "
    "Hablalo directo, como si ya lo supieras. Máximo ~40 palabras."
)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_SOURCE_RE = re.compile(r"^Source:\s*.+$", re.I | re.M)
_CITATION_RE = re.compile(r"\[\d+\]|\(\s*https?://[^)]+\)")
_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z]*\.?\s+\d{4}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    re.I,
)
_PARENS_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_BULLET_RE = re.compile(r"^\s*[-•*]\s*", re.M)
_NOISE_LINE = re.compile(
    r"(wikipedia,?\s+la\s+enciclopedia|diccionario\s+panhisp|"
    r"page\s+extract|top\s+page|microsoft\s+corporation|"
    r"monde\s+du\s+voyage|yourdictionary)",
    re.I,
)


def clean_search_results(raw_snippets: list[str], max_chars: int = 800) -> str:
    """Strip URLs/dates/brackets so a small LLM does not parrot junk."""
    cleaned: list[str] = []
    for snippet in raw_snippets:
        text = _URL_RE.sub("", snippet or "")
        text = _DATE_RE.sub("", text)
        text = _PARENS_RE.sub("", text)
        text = _CITATION_RE.sub("", text)
        text = re.sub(r"[#*_`]+", "", text)
        text = " ".join(text.split()).strip(" .-–—")
        if text and not _NOISE_LINE.search(text):
            cleaned.append(text)
    return "\n".join(cleaned)[:max_chars]


def _clean_blob(text: str) -> str:
    text = _SOURCE_RE.sub("", text or "")
    text = _URL_RE.sub("", text)
    text = _DATE_RE.sub("", text)
    text = _CITATION_RE.sub("", text)
    text = _PARENS_RE.sub("", text)
    text = re.sub(r"[#*_`]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .-–—")


def _snippet_bodies(raw: str) -> list[str]:
    """Pull title/body pairs from the tool dump format."""
    chunks: list[str] = []
    for block in re.split(r"\n(?=-\s)", raw or ""):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        title = _BULLET_RE.sub("", lines[0]).strip()
        title = re.sub(r"\s*[-–—]\s*Wikipedia.*$", "", title, flags=re.I).strip()
        body_parts: list[str] = []
        for ln in lines[1:]:
            if ln.startswith("http") or ln.startswith("---"):
                continue
            if _NOISE_LINE.search(ln):
                continue
            body_parts.append(ln)
        body = " ".join(body_parts).strip()
        if title and not title.lower().startswith("source:"):
            if body:
                if len(body) >= 20 and (
                    title.lower() in body.lower()
                    or re.search(r"\b(es|fue|está|capital|tiene)\b", body, re.I)
                ):
                    chunks.append(body)
                else:
                    chunks.append(f"{title}. {body}")
            else:
                chunks.append(title)
    if not chunks and (raw or "").strip():
        chunks.append(_clean_blob(raw))
    return chunks


def _trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    cut = " ".join(words[:max_words]).rstrip(",;:")
    if not cut.endswith((".", "!", "?", "…")):
        cut += "."
    return cut


def speakable_from_search(
    raw: str,
    query: str = "",
    *,
    max_words: int = 40,
) -> str:
    """
    Extract one fluent spoken answer from Bing/Yahoo dump or cache text.
    Drops URLs, Source headers, and citation noise. No LLM required.
    """
    if not (raw or "").strip():
        return ""
    low = raw.lower()
    if low.startswith("no results") or low.startswith("empty query"):
        return ""

    cleaned_whole = _clean_blob(raw)
    if (
        len(cleaned_whole.split()) <= max_words
        and "http" not in raw.lower()
        and not raw.lstrip().startswith(("Source:", "-", "•"))
    ):
        return cleaned_whole

    q_tokens = [
        t
        for t in re.findall(r"[a-záéíóúñü0-9]{3,}", (query or "").lower())
        if t
        not in {
            "que",
            "qué",
            "cual",
            "cuál",
            "como",
            "cómo",
            "para",
            "por",
            "una",
            "del",
            "los",
            "las",
            "con",
            "capital",
            "quien",
            "quién",
        }
    ][:6]

    best = ""
    best_score = -1
    for chunk in _snippet_bodies(raw):
        clean = _clean_blob(chunk)
        if len(clean) < 12 or _NOISE_LINE.search(clean):
            continue
        score = sum(1 for t in q_tokens if t in clean.lower())
        if re.search(r"\b(es|fue|está|esta|tiene|son|era|capital)\b", clean, re.I):
            score += 2
        if score > best_score or (score == best_score and len(clean) < len(best or " " * 999)):
            best_score = score
            best = clean

    if not best:
        # Fallback: cleaned joined snippets (user's clean_search_results pattern).
        best = clean_search_results(_snippet_bodies(raw), max_chars=400) or cleaned_whole

    m = re.search(r"^(.+?[.!?…])(?:\s|$)", best)
    if m and len(m.group(1).split()) >= 4:
        best = m.group(1).strip()

    return _trim_words(re.sub(r"\s+", " ", best).strip(), max_words)


def looks_like_search_dump(text: str) -> bool:
    raw = text or ""
    if raw.lstrip().startswith("Source:"):
        return True
    if raw.count("http://") + raw.count("https://") >= 2:
        return True
    if "Busqué esto por vos:" in raw and ("http" in raw or raw.count("\n-") >= 2):
        return True
    return False
