"""Zero-LLM Fast-Path Router — mechanical intents before Ollama/Groq.

Flexible enough for spoken variants; still fails closed on ambiguous chat.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

Execute = Callable[[str, str], str]

_WAKE = re.compile(
    r"^(?:hey\s+|ok\s+|hola\s+)?(?:ilaria|friday|fr[ií]day)\b[\s,.:\-]*",
    re.I,
)
_PHONE = frozenset({"android", "ios", "iphone", "ipad"})
_TRAIL_PUNCT = re.compile(r"[?!.,;:…]+$")


def _phone(surface: str) -> bool:
    return (surface or "").strip().lower() in _PHONE


def _clean(text: str) -> str:
    raw = _WAKE.sub("", (text or "").strip()).strip()
    raw = _TRAIL_PUNCT.sub("", raw).strip()
    return re.sub(r"\s+", " ", raw).strip()


def match_fast_path(
    text: str,
    *,
    surface: str = "hud",
) -> tuple[str, dict[str, Any], str] | None:
    """Return (tool, params, rule_name) or None."""
    compact = _clean(text)
    if not compact:
        return None
    lower = compact.lower()
    surf = (surface or "hud").strip().lower()

    # Volume level — allow short trailing politeness ("por favor")
    m = re.fullmatch(
        r"(?:pon(?:eme|[eé])?\s+(?:el\s+)?)?(?:el\s+)?(?:volumen|volume)"
        r"(?:\s+(?:al|a|en|del?|a\s+la))?\s+(\d{1,3})\s*%?"
        r"(?:\s+por\s+favor)?",
        lower,
    )
    if not m:
        m = re.search(
            r"(?:volumen|volume)\s+(?:al|a|en|del?)?\s*(\d{1,3})\s*%?",
            lower,
        )
        # Only accept search form if the phrase is still short/mechanical
        if m and len(lower) > 48:
            m = None
    if m:
        level = max(0, min(100, int(m.group(1))))
        if _phone(surf):
            return "phone_hands", {"action": "volume", "target": str(level)}, "volume_level"
        return "set_volume", {"level": level}, "volume_level"

    if re.fullmatch(
        r"(?:sub[ií]|aument[aá]|subime|subile)\s+(?:el\s+)?(?:volumen|volume|sonido)|"
        r"(?:volumen|volume)\s+(?:para?\s+)?arriba|vol\+|m[aá]s\s+volumen",
        lower,
    ):
        if _phone(surf):
            return "phone_hands", {"action": "volume", "target": "up"}, "volume_up"
        return "media", {"action": "vol_up"}, "volume_up"

    if re.fullmatch(
        r"(?:baj[aá]|reduc[ií]|bajame|bajale)\s+(?:el\s+)?(?:volumen|volume|sonido)|"
        r"(?:volumen|volume)\s+(?:para?\s+)?abajo|vol\-|menos\s+volumen",
        lower,
    ):
        if _phone(surf):
            return "phone_hands", {"action": "volume", "target": "down"}, "volume_down"
        return "media", {"action": "vol_down"}, "volume_down"

    if re.fullmatch(
        r"(?:silenci[aá]|silenciar|mute(?:ar)?|sin\s+sonido|callate|c[aá]llate)"
        r"(?:\s+(?:el\s+)?(?:volumen|sonido|pc|todo))?(?:\s+por\s+favor)?",
        lower,
    ):
        if _phone(surf):
            return "phone_hands", {"action": "volume", "target": "mute"}, "mute"
        return "media", {"action": "mute"}, "mute"

    if re.fullmatch(
        r"(?:desilenci[aá]|unmute(?:ar)?|con\s+sonido|sac[aá]\s+el\s+silencio|"
        r"quit[aá]\s+el\s+silencio)(?:\s+por\s+favor)?",
        lower,
    ):
        if _phone(surf):
            return "phone_hands", {"action": "volume", "target": "unmute"}, "unmute"
        return "media", {"action": "mute"}, "unmute"

    if re.fullmatch(r"(?:deshac[eé]r?|undo|arrepent(?:ite)?|volvé?\s+atr[aá]s)", lower):
        return "undo_last", {}, "undo"

    # Timer / reminder — mechanical only (number + unit).
    m = re.fullmatch(
        r"(?:timer|temporizador|avis[aá]me|record[aá]me|despert[aá]me)\s+"
        r"(?:en\s+)?(\d{1,3}(?:[.,]\d+)?)\s*"
        r"(min|mins|minuto|minutos|hora|horas|seg|segs|segundo|segundos)"
        r"(?:\s+(?:para|que|:|de)\s*(.+))?",
        lower,
    )
    if not m:
        m = re.fullmatch(
            r"en\s+(\d{1,3}(?:[.,]\d+)?)\s*"
            r"(min|mins|minuto|minutos|hora|horas|seg|segs|segundo|segundos)"
            r"(?:\s+(?:para|que|:|de)\s*(.+))?",
            lower,
        )
    if m:
        amount = float(m.group(1).replace(",", "."))
        unit = m.group(2)
        label = (m.group(3) if m.lastindex and m.lastindex >= 3 else "") or "Timer"
        if unit.startswith("hora"):
            amount *= 60
        elif unit.startswith("seg"):
            amount /= 60.0
        if 0.05 <= amount <= 24 * 60:
            return (
                "set_timer",
                {"minutes": round(amount, 2), "text": label.strip() or "Timer"},
                "timer",
            )

    if re.fullmatch(r"pomodoro|foco|timer\s*25", lower):
        return "set_timer", {"minutes": 25, "text": "Pomodoro"}, "timer_pomodoro"

    if re.fullmatch(
        r"(?:qu[eé]\s+hora\s+es(?:\s+por\s+favor)?|hora|fecha|qu[eé]\s+d[ií]a\s+es(?:\s+hoy)?|ahora)",
        lower,
    ):
        return "now", {}, "now"

    if re.fullmatch(
        r"(?:list[aá]|mostr[aá]|decime|dame)\s+(?:mis\s+)?recetas|"
        r"qu[eé]\s+recetas(?:\s+ten[eé]s)?|cat[aá]logo\s+de\s+recetas|recetas\s+disponibles",
        lower,
    ):
        return "kitchen_recipe", {"action": "listar", "dish": ""}, "kitchen_list"

    m = re.fullmatch(
        r"(?:busc[aá]|busca[r]?|mostr[aá]|dame)\s+(?:una?\s+)?"
        r"(?:ilustraci[oó]n(?:es)?|imagen(?:es)?|foto(?:s)?|dibujo(?:s)?|diagrama(?:s)?)\s+"
        r"(?:de\s+|del?\s+|sobre\s+)?(.+)",
        lower,
    )
    if m:
        topic = m.group(1).strip(" .")
        if 1 < len(topic) <= 120:
            if _phone(surf):
                return "phone_hands", {"action": "search", "target": f"{topic} ilustración"}, "image_phone"
            return "image_search", {"query": topic, "max_results": 5, "open_browser": True}, "image_search"

    if re.fullmatch(
        r"(?:le[eé]r?\s+(?:el\s+)?reloj|reloj|smartwatch|m[eé]tricas(?:\s+del\s+reloj)?|"
        r"c[oó]mo\s+estoy(?:\s+de\s+energ[ií]a)?|pasos\s+de\s+hoy|hrv|"
        r"energ[ií]a\s+(?:de\s+)?hoy)",
        lower,
    ):
        return "wellness_action", {"action": "leer_reloj", "tipo_tema": "smartwatch"}, "watch"

    m = re.fullmatch(
        r"(?:c[oó]mo\s+llego(?:\s+a)?|mapas?|ruta(?:\s+a)?|ll[eé]vame\s+a|naveg[aá]\s+(?:a|hacia)|"
        r"direcciones?\s+(?:a|para)|gps\s+(?:a|hacia))\s+(.+)",
        lower,
    )
    if m:
        dest = m.group(1).strip(" .")
        if 1 < len(dest) <= 120:
            if _phone(surf):
                return "phone_hands", {"action": "navigate", "target": dest}, "navigate"
            return "open_maps", {"destination": dest, "origin": ""}, "maps"

    if re.fullmatch(
        r"(?:atend[eé]|responder?|abrir)\s+(?:el\s+)?(?:intercomunicador|portero|timbre)|"
        r"(?:intercomunicador|portero|timbre)(?:\s+por\s+favor)?|"
        r"abrir\s+(?:el\s+)?portero",
        lower,
    ):
        return "intercom_action", {"action": "answer"}, "intercom_answer"

    if re.fullmatch(
        r"(?:ver|abr[ií])\s+(?:la\s+)?(?:c[aá]mara|video|vista)\s+(?:del\s+)?(?:intercomunicador|portero|timbre)|"
        r"(?:intercomunicador|portero)\s+(?:en\s+)?(?:video|c[aá]mara)",
        lower,
    ):
        return "intercom_action", {"action": "view"}, "intercom_view"

    if re.fullmatch(r"(?:estado\s+(?:del\s+)?)?(?:intercomunicador|portero)", lower):
        return "intercom_action", {"action": "status"}, "intercom_status"

    if re.fullmatch(
        r"(?:diario(?:\s+de\s+hoy)?|le[eé]r?\s+el\s+diario|mostr[aá]\s+el\s+diario|"
        r"bit[aá]cora(?:\s+de\s+hoy)?)",
        lower,
    ):
        return "read_daily_journal", {}, "journal_read"

    if re.fullmatch(r"(?:siguiente|next|pr[oó]xima(?:\s+canci[oó]n)?)", lower):
        return "media", {"action": "next"}, "media_next"

    if re.fullmatch(r"(?:anterior|previous|prev)", lower):
        return "media", {"action": "prev"}, "media_prev"

    if re.fullmatch(r"(?:paus[aá]|pause|play|reproduc[ií]|play[\s\-]?pause)", lower):
        return "media", {"action": "play_pause"}, "media_pause"

    if re.fullmatch(
        r"(?:estado(?:\s+de)?(?:\s+la)?\s+pc|system\s*status|qu[eé]\s+hay\s+abierto)",
        lower,
    ):
        return "system_status", {}, "pc_status"

    from jarvis.pc_diagnose import looks_like_pc_slow

    if looks_like_pc_slow(text):
        return "diagnose_pc", {}, "pc_slow"

    from jarvis.translate import parse_translate_request

    parsed_tr = parse_translate_request(text)
    if parsed_tr:
        phrase, src, tgt = parsed_tr
        return (
            "translate_text",
            {"text": phrase, "target": tgt, "source": src},
            "translate",
        )

    if re.fullmatch(
        r"(?:captura(?:\s+de\s+pantalla)?|screenshot|sac[aá]\s+(?:una\s+)?captura)",
        lower,
    ):
        if _phone(surf):
            return "phone_hands", {"action": "screenshot"}, "screenshot"
        return "screenshot", {}, "screenshot"

    # Deep-link music / YouTube — always open the browser, never paste a link.
    if not _phone(surf):
        # "abrí brave y poné youtube …" / "abrí brave youtube …" / "abrime youtube …"
        m = re.search(
            r"(?:abr[ií]|abra|abrir|abrime)\s+"
            r"(?:(brave|chrome|edge|chromium)\s+)?"
            r"(?:y\s+|,\s*)?"
            r"(?:abr[ií]|abra|abrir|abrime|pon(?:eme|[eé])?|ponga|busc[aá]r?|reproduc[ií]|play)?\s*"
            r"(?:en\s+)?"
            r"(youtube|yt|ytmusic|google|spotify)\s+"
            r"(?:y\s+(?:pon(?:eme|[eé])?|busc[aá]r?|reproduc[ií])\s+)?"
            r"(?:una\s+canci[oó]n\s+(?:de\s+)?|un\s+tema\s+(?:de\s+)?|algo\s+(?:de\s+)?|"
            r"a\s+|de\s+|el\s+video\s+(?:de\s+)?)?"
            r"(.+)$",
            lower,
        )
        if m:
            browser = (m.group(1) or "brave").strip()
            platform = m.group(2).strip()
            query = m.group(3).strip(" .")
            query = re.sub(r"^(una\s+canci[oó]n\s+(?:de\s+)?|de\s+)", "", query).strip()
            if 1 < len(query) <= 100:
                return (
                    "app_search_action",
                    {"browser": browser, "platform": platform, "query": query},
                    "app_search_open",
                )

        # "poné / buscá en youtube|spotify …" / "poneme en youtube X"
        m = re.fullmatch(
            r"(?:pon(?:eme|[eé])?|ponga|reproduc[ií]|play|busc[aá]r?|tirame)\s+"
            r"(?:en\s+)?(youtube|yt|ytmusic|spotify)\s+"
            r"(?:una\s+canci[oó]n\s+(?:de\s+)?|algo\s+(?:de\s+)?|a\s+|de\s+)?"
            r"(.+)",
            lower,
        )
        if m:
            query = m.group(2).strip(" .")
            if 1 < len(query) <= 100:
                return (
                    "app_search_action",
                    {
                        "browser": "brave",
                        "platform": m.group(1),
                        "query": query,
                    },
                    "app_search_music",
                )

        # "youtube X" / "canción de X en youtube"
        m = re.fullmatch(
            r"(?:canci[oó]n\s+de\s+|tema\s+de\s+)?(.+?)\s+en\s+(youtube|yt|spotify)",
            lower,
        )
        if m:
            query = m.group(1).strip(" .")
            if 1 < len(query) <= 100 and not re.search(
                r"\b(qu[eé]|por\s+qu[eé]|pens[aá]|explic)\b", query
            ):
                return (
                    "app_search_action",
                    {
                        "browser": "brave",
                        "platform": m.group(2),
                        "query": query,
                    },
                    "app_search_en",
                )

        # "poneme / tirame [una canción de] Artist" (no platform → YouTube Brave)
        m = re.fullmatch(
            r"(?:pon(?:eme|[eé])?|tirame|reproduc[ií]|play)\s+"
            r"(?:una?\s+)?(?:canci[oó]n|tema|video|track)\s+"
            r"(?:de\s+|del?\s+)?"
            r"(.+)",
            lower,
        )
        if m:
            query = m.group(1).strip(" .")
            if 1 < len(query) <= 100 and not re.search(
                r"\b(volumen|timer|nota|diario|brave|chrome)\b", query
            ):
                return (
                    "app_search_action",
                    {"browser": "brave", "platform": "youtube", "query": query},
                    "app_search_song",
                )

        # Generic: "abrí / ejecutá / lanzá <programa>" — always open, never describe.
        m = re.fullmatch(
            r"(?:abr[ií]|abrime|abrir|abre|open|lanz[aá]|ejecut[aá]|corré|corre|inici[aá]|run)\s+"
            r"(?:la\s+|el\s+|app\s+(?:de\s+)?|aplicación\s+(?:de\s+)?|programa\s+(?:de\s+)?)?"
            r"(.+)",
            lower,
        )
        if m:
            target = m.group(1).strip(" .")
            # Bare media apps → open the app itself (not a search).
            bare_media = re.fullmatch(
                r"(brave|chrome|edge|chromium|youtube|yt|ytmusic|spotify|discord|"
                r"steam|telegram|whatsapp|notepad|calculadora|excel|word|cursor|"
                r"vlc|obs|code|vscode)",
                target,
            )
            if bare_media:
                name = {"yt": "youtube", "ytmusic": "youtube", "chromium": "chrome"}.get(
                    bare_media.group(1), bare_media.group(1)
                )
                return "open_app", {"name": name}, "open_app"
            # Music+browser combos with a query already handled above.
            if (
                1 < len(target) <= 80
                and not re.search(r"\b(youtube|ytmusic|spotify)\b", target)
                and not re.search(r"\b(canci[oó]n|tema|video|ilustraci|imagen|foto)\b", target)
                and not re.search(r"\b(intercomunicador|portero|timbre|mapa|ruta)\b", target)
            ):
                # "brave y chrome" → first app; strip polite junk
                target = re.sub(r"\s+(por favor|please)$", "", target).strip()
                name = target.split(",")[0].strip()
                name = re.split(r"\s+y\s+", name)[0].strip()
                if name:
                    return "open_app", {"name": name}, "open_app"

    return None


def _speakable_fast_result(tool: str, params: dict[str, Any], result: str) -> str:
    """Map tool results to short TTS-friendly confirms (phrase-cache friendly)."""
    if tool == "set_volume":
        level = params.get("level")
        spoken = {
            0: "Silenciado.",
            20: "Volumen al veinte.",
            30: "Volumen al treinta.",
            40: "Volumen al cuarenta.",
            50: "Volumen al cincuenta.",
            60: "Volumen al sesenta.",
            70: "Volumen al setenta.",
            80: "Volumen al ochenta.",
            100: "Volumen al cien.",
        }
        if isinstance(level, int) and level in spoken:
            return spoken[level]
        if isinstance(level, int):
            return f"Volumen al {level}%."
        return "Volumen ajustado."
    if tool == "media":
        mapping = {
            "mute": "Silenciado.",
            "vol_up": "Volumen ajustado.",
            "vol_down": "Volumen ajustado.",
            "next": "Siguiente.",
            "prev": "Anterior.",
            "play_pause": "Listo.",
            "stop": "Listo.",
        }
        return mapping.get(str(params.get("action") or "").lower(), "Listo.")
    if tool == "undo_last":
        low = (result or "").lower()
        if "nada" in low or "no hay" in low:
            return "No hay nada para deshacer."
        if "volumen" in low:
            return "Volumen restaurado."
        return "Deshecho."
    if tool == "set_timer":
        return "Timer listo."
    if tool == "open_maps":
        return "Abriendo el mapa."
    if tool == "system_status":
        return (result or "").strip()[:220] or "Estado listo."
    if tool == "diagnose_pc":
        return (result or "").strip()[:400] or "Listo el diagnóstico de la PC."
    if tool == "translate_text":
        return (result or "").strip()[:400] or "Listo."
    if tool == "open_app":
        name = str(params.get("name") or "").strip().lower()
        special = {
            "spotify": "Abriendo Spotify.",
            "chrome": "Abriendo Chrome.",
            "brave": "Listo, abrí brave.",
            "youtube": "Listo, abrí youtube.",
            "notepad": "Listo, abrí notepad.",
            "excel": "Listo, abrí excel.",
            "calculadora": "Listo, abrí calculadora.",
        }
        if name in special:
            return special[name]
        if name:
            return f"Listo, abrí {name}."
        return "Abierto."
    if tool == "app_search_action":
        plat = str(params.get("platform") or "").lower()
        if "spotify" in plat:
            return "Abriendo Spotify."
        if "youtube" in plat or plat in {"yt", "ytmusic"}:
            return "Listo, abrí youtube."
        return "Listo."
    if tool == "screenshot":
        return "Captura lista."
    if tool in {"note", "daily_journal"}:
        return "Anotado."
    return result


def try_fast_path(
    text: str,
    execute: Execute,
    *,
    surface: str = "hud",
    allowed: set[str] | None = None,
) -> str | None:
    """Execute a mechanical tool immediately. None → fall through to local/LLM."""
    t0 = time.perf_counter()
    hit = match_fast_path(text, surface=surface)
    if hit is None:
        return None
    tool, params, rule = hit
    if allowed is not None and tool not in allowed:
        return None
    result = execute(tool, json.dumps(params, ensure_ascii=False))
    ms = (time.perf_counter() - t0) * 1000.0
    print(f"[FAST_PATH] {rule} -> {tool} ({ms:.1f}ms)")
    if tool == "kitchen_recipe":
        try:
            data = json.loads(result)
            if isinstance(data, dict) and data.get("speakable"):
                return str(data["speakable"])
        except (json.JSONDecodeError, TypeError):
            pass
    if tool == "wellness_action":
        try:
            data = json.loads(result)
            if isinstance(data, dict) and data.get("speech"):
                return str(data["speech"])
            if isinstance(data, dict) and data.get("nivel_energia_estimado"):
                return (
                    f"{data.get('pasos_hoy', 0)} pasos · "
                    f"{str(data.get('nivel_energia_estimado', '')).split('.')[0]}"
                )
        except (json.JSONDecodeError, TypeError):
            pass
    return _speakable_fast_result(tool, params, result)


try_fast_path_router = try_fast_path
