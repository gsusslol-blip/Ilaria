"""Offline-friendly translation via public HTTP APIs (no extra pip deps).

Primary: Google gtx endpoint. Fallback: MyMemory.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

# Common names → ISO codes (Rioplatense prompts).
_LANG_ALIASES: dict[str, str] = {
    "es": "es",
    "español": "es",
    "espanol": "es",
    "castellano": "es",
    "en": "en",
    "inglés": "en",
    "ingles": "en",
    "english": "en",
    "it": "it",
    "italiano": "it",
    "italian": "it",
    "pt": "pt",
    "portugués": "pt",
    "portugues": "pt",
    "portuguese": "pt",
    "fr": "fr",
    "francés": "fr",
    "frances": "fr",
    "french": "fr",
    "de": "de",
    "alemán": "de",
    "aleman": "de",
    "german": "de",
    "ja": "ja",
    "japonés": "ja",
    "japones": "ja",
    "japanese": "ja",
    "zh": "zh-CN",
    "chino": "zh-CN",
    "chinese": "zh-CN",
    "ko": "ko",
    "coreano": "ko",
    "korean": "ko",
    "ru": "ru",
    "ruso": "ru",
    "russian": "ru",
}

_LANG_LABEL = {
    "es": "español",
    "en": "inglés",
    "it": "italiano",
    "pt": "portugués",
    "fr": "francés",
    "de": "alemán",
    "ja": "japonés",
    "zh-CN": "chino",
    "ko": "coreano",
    "ru": "ruso",
}

_ACCENT = str.maketrans("áéíóúüñ", "aeiouun")


def _fold(text: str) -> str:
    return (text or "").lower().translate(_ACCENT)


def resolve_lang(name: str) -> str | None:
    key = _fold(name or "").strip()
    return _LANG_ALIASES.get(key)


def parse_translate_request(raw: str) -> tuple[str, str, str] | None:
    """
    Return (text, source_lang, target_lang) or None.
    source_lang may be 'auto'.
    """
    text = (raw or "").strip()
    if not text:
        return None
    low = text.lower()

    # "traducí al inglés: hola" / "traducir a francés — bonjour"
    m = re.match(
        r"^(?:traduc[ií]|traducir|translate)\s+"
        r"(?:(?:al?|to|into)\s+([a-záéíóúüñ]+)\s*[:\-–—,]?\s*)(.+)$",
        text,
        re.I,
    )
    if m:
        lang = resolve_lang(m.group(1))
        phrase = m.group(2).strip().strip(" :-,\"'").strip("–—")
        if lang and phrase:
            return phrase, "auto", lang

    # "traducí hello world al español"
    m = re.match(
        r"^(?:traduc[ií]|traducir|translate)\s+(.+?)\s+(?:al?|to|into)\s+([a-záéíóúüñ]+)\s*$",
        text,
        re.I,
    )
    if m:
        phrase = m.group(1).strip().strip(" :-,\"'").strip("–—")
        lang = resolve_lang(m.group(2))
        if lang and phrase:
            return phrase, "auto", lang

    # "traducí hello world" → default to Spanish
    m = re.match(r"^(?:traduc[ií]|traducir|translate)\s+(.+)$", text, re.I)
    if m:
        phrase = m.group(1).strip()
        # Strip leading "al X " if resolve failed above
        phrase = re.sub(
            r"^(?:al?|to|into)\s+[a-záéíóúüñ]+\s+",
            "",
            phrase,
            flags=re.I,
        ).strip()
        if phrase:
            return phrase, "auto", "es"

    # "cómo se dice X en inglés"
    m = re.match(
        r"^(?:c[oó]mo\s+se\s+dice|como\s+se\s+dice|how\s+do\s+you\s+say)\s+"
        r"[«\"']?(.+?)[»\"']?\s+en\s+([a-záéíóúüñ]+)\s*$",
        text,
        re.I,
    )
    if m:
        phrase = m.group(1).strip()
        lang = resolve_lang(m.group(2))
        if lang and phrase:
            return phrase, "auto", lang

    # "qué significa WORD" (short foreign token → Spanish)
    m = re.match(
        r"^(?:qu[eé]\s+significa|what\s+does)\s+[«\"']?([A-Za-zÀ-ÿ][\w\-']{1,40})[»\"']?\s*"
        r"(?:en\s+español)?\s*[?.!]?\s*$",
        text,
        re.I,
    )
    if m:
        phrase = m.group(1).strip()
        if phrase and not re.search(r"\b(inflaci[oó]n|fotos[ií]ntesis|gravedad)\b", phrase, re.I):
            return phrase, "auto", "es"

    if "traduc" in low or "translate" in low or "se dice" in low:
        return None
    return None


def translate_text(
    text: str,
    *,
    target: str = "es",
    source: str = "auto",
) -> dict[str, Any]:
    """Translate and return {ok, text, source, target, provider, error?}."""
    phrase = " ".join((text or "").split()).strip()
    tgt = resolve_lang(target) or (target if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", target or "") else "es")
    src = "auto" if not source or source == "auto" else (resolve_lang(source) or source)
    if not phrase:
        return {"ok": False, "text": "", "source": src, "target": tgt, "error": "empty"}

    # Same language short-circuit.
    if src != "auto" and src.split("-")[0] == tgt.split("-")[0]:
        return {"ok": True, "text": phrase, "source": src, "target": tgt, "provider": "identity"}

    err = ""
    for provider, fn in (("gtx", _via_gtx), ("mymemory", _via_mymemory)):
        try:
            out, detected = fn(phrase, src, tgt)
            if out:
                return {
                    "ok": True,
                    "text": out,
                    "source": detected or src,
                    "target": tgt,
                    "provider": provider,
                }
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            continue
    return {
        "ok": False,
        "text": "",
        "source": src,
        "target": tgt,
        "error": err or "translate failed",
        "provider": "",
    }


def speakable_translation(result: dict[str, Any], *, original: str = "") -> str:
    if not result.get("ok"):
        return "No pude traducir ahora. Probá de nuevo en un toque."
    out = str(result.get("text") or "").strip()
    tgt = str(result.get("target") or "es")
    label = _LANG_LABEL.get(tgt, tgt)
    if original and original.strip() and original.strip() != out:
        return f"En {label}: {out}"
    return out


def _via_gtx(text: str, source: str, target: str) -> tuple[str, str]:
    sl = "auto" if source == "auto" else source
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={quote(sl)}&tl={quote(target)}&dt=t&q={quote(text)}"
    )
    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "IlariaLocalAssistant/1.5"})
        resp.raise_for_status()
        data = resp.json()
    parts: list[str] = []
    detected = source
    if isinstance(data, list) and data:
        chunks = data[0] if isinstance(data[0], list) else []
        for row in chunks:
            if isinstance(row, list) and row and isinstance(row[0], str):
                parts.append(row[0])
        if len(data) > 2 and isinstance(data[2], str):
            detected = data[2]
    return "".join(parts).strip(), detected


def _via_mymemory(text: str, source: str, target: str) -> tuple[str, str]:
    sl = "Autodetect" if source == "auto" else source.split("-")[0]
    tl = target.split("-")[0]
    url = (
        "https://api.mymemory.translated.net/get"
        f"?q={quote(text)}&langpair={quote(sl)}|{quote(tl)}"
    )
    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "IlariaLocalAssistant/1.5"})
        resp.raise_for_status()
        data = resp.json()
    translated = ""
    if isinstance(data, dict):
        translated = str((data.get("responseData") or {}).get("translatedText") or "").strip()
    if not translated or "SELECT TWO DISTINCT" in translated.upper() or "INVALID" in translated.upper():
        return "", sl
    return translated, sl
