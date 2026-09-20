"""Turn raw web_search dumps into one short speakable sentence (Yui / TTS).

No extra LLM call — regex/parser only, so latency stays flat.
"""

from __future__ import annotations

import re

_ACCENT = str.maketrans("áéíóúüñ", "aeiouun")


def _fold(text: str) -> str:
    return (text or "").lower().translate(_ACCENT)


# Injected into the research synth turn (Groq/Ollama) after tools return.
SEARCH_SPEAK_INSTRUCTION = (
    "Vas a responder la duda del usuario basándote únicamente en el contexto de búsqueda provisto. "
    "Tu respuesta debe ser corta (máximo 2 oraciones), fluida, natural y redactada en español rioplatense. "
    "Está terminantemente prohibido enumerar opciones, usar viñetas, citar páginas web o decir frases como "
    "'según los resultados de búsqueda' / 'Source:' / 'según el sitio'. "
    "Hablalo directo, como si ya lo supieras de memoria."
)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_SOURCE_RE = re.compile(r"^Source:\s*.+$", re.I | re.M)
_CITATION_RE = re.compile(r"\[\d+\]|\(\s*https?://[^)]+\)")
# News/relative dates only — do NOT strip historical "12 de octubre de 1492".
_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z]*\.?\s+20\d{2}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+20\d{2}\b"
    r"|\b\d+\s+(?:d[ií]as?|horas?|semanas?)\s+atr[aá]s\b",
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
_NOISE_CHUNK = re.compile(
    r"\b(prezi|timetoast|l[ií]neas?\s+de\s+nazca|descubriamerica|by\s+\w+\s+rojas|"
    r"countriq|haz\s+clic\s+aqu[ií]|te\s+explicamos\s+qu[eé]|world\s+heritage\s+site|"
    r"descubre\s+el\s+significado|todas\s+las\s+acepciones|mapa\s+y\s+vecinos)\b",
    re.I,
)
_SEO_TITLE = re.compile(
    r"\|\s*\w+\s*$|^\s*·?\s*(mapa|biograf[ií]a|definici[oó]n|c[oó]mo\s+termin|"
    r"qu[eé]\s+a[nñ]o\s+exactamente|esta\s+fecha\s+recuerda)\b",
    re.I,
)
_ANSWER_HINT = re.compile(
    r"\b(es|fue|era|capital|descubri[oó]|naci[oó]|invent[oó]|comandada\s+por)\b",
    re.I,
)
_COLON_HINT = re.compile(r"crist[oó]bal\s+col[oó]n|\bcol[oó]n\b", re.I)


def clean_search_results(
    raw_text: str | list[str] | None,
    max_chars: int = 1000,
) -> str:
    """
    Strip search junk (URLs, dates, brackets) so a small LLM gets clean context.
    Accepts a raw dump string or a list of snippet strings.
    """
    if not raw_text:
        return ""
    if isinstance(raw_text, list):
        parts = [clean_search_results(s, max_chars=max_chars) for s in raw_text if s]
        return "\n".join(p for p in parts if p)[:max_chars]

    text = _SOURCE_RE.sub("", raw_text)
    text = _URL_RE.sub("", text)
    text = _DATE_RE.sub("", text)
    text = _PARENS_RE.sub("", text)
    text = _CITATION_RE.sub("", text)
    text = re.sub(r"[#*_`]+", "", text)
    text = re.sub(r"[—•]+", " ", text)
    cleaned = " ".join(text.split()).strip(" .-–—")
    return cleaned[:max_chars]


def _clean_blob(text: str) -> str:
    return clean_search_results(text, max_chars=4000)


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
        for t in re.findall(r"[a-z0-9]{3,}", _fold(query or ""))
        if t
        not in {
            "que",
            "cual",
            "como",
            "para",
            "por",
            "una",
            "del",
            "los",
            "las",
            "con",
            "capital",
            "quien",
            "segun",
        }
    ][:6]

    best = ""
    best_score = -1
    for chunk in _snippet_bodies(raw):
        clean = _clean_blob(chunk)
        if len(clean) < 12 or _NOISE_LINE.search(clean):
            continue
        # Prefer explicit Q&A bodies ("Respuesta: …").
        ans = re.search(r"respuesta\s*:\s*(.+)$", clean, re.I | re.S)
        if ans and len(ans.group(1).split()) >= 4:
            clean = ans.group(1).strip()
        folded = _fold(clean)
        token_hits = sum(1 for t in q_tokens if t in folded)
        score = float(token_hits)
        for t in q_tokens:
            if len(t) >= 5 and t not in folded and t[:5] in folded:
                score += 0.5
        # Only boost copulas/verbs when the snippet already touches the query.
        if token_hits >= 1 and _ANSWER_HINT.search(clean):
            score += 2
        if ans:
            score += 5
        if _COLON_HINT.search(clean) and (
            "america" in folded or "descubrio" in folded or "descubrimiento" in folded
        ):
            score += 4
        if _NOISE_CHUNK.search(clean) or _NOISE_CHUNK.search(chunk):
            score -= 4
        if _SEO_TITLE.search(clean):
            score -= 3
        # Prefer statements over clickbait questions.
        if clean.strip().startswith("¿") or clean.strip().endswith("?"):
            score -= 3
        if re.search(r"varias teor[ií]as|hay varias", clean, re.I):
            score -= 2
        if len(clean.split()) > 45:
            score -= 1
        if score > best_score or (score == best_score and len(clean) < len(best or " " * 999)):
            best_score = score
            best = clean

    if not best:
        best = clean_search_results(_snippet_bodies(raw), max_chars=400) or cleaned_whole
        if best and q_tokens:
            folded = _fold(best)
            best_score = sum(1 for t in q_tokens if t in folded)
            if _ANSWER_HINT.search(best):
                best_score += 2

    # Refuse to speak off-topic snippets (cache/Bing junk).
    if q_tokens and best_score < 1:
        return ""

    # Pick the strongest sentence inside the winning chunk (not just the first).
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", best) if s.strip()]
    if len(sentences) > 1:
        best_sent = ""
        best_sent_score = -1.0
        for sent in sentences:
            if len(sent.split()) < 4:
                continue
            sf = _fold(sent)
            sc = float(sum(1 for t in q_tokens if t in sf))
            if _COLON_HINT.search(sent):
                sc += 4
            if _ANSWER_HINT.search(sent):
                sc += 1
            if sent.startswith("¿") or sent.endswith("?"):
                sc -= 3
            if re.search(r"varias teor[ií]as|hay varias", sent, re.I):
                sc -= 4
            if sc > best_sent_score:
                best_sent_score = sc
                best_sent = sent
        if best_sent and best_sent_score >= 1:
            best = best_sent
    else:
        m = re.search(r"^(.+?[.!?…])(?:\s|$)", best)
        if m and len(m.group(1).split()) >= 4:
            candidate = m.group(1).strip()
            if not (candidate.startswith("¿") or candidate.endswith("?")):
                best = candidate

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
