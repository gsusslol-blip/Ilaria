"""Internet, memory, and PC tools Ilaria can call."""

from __future__ import annotations

import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import httpx
from ddgs import DDGS

from jarvis.actions import Actions
from jarvis.config import Settings
from jarvis.memory import Memory

# Fastest usable backend here is Bing (~300ms, high quality when healthy).
# Bing can occasionally return junk — relevance gate falls through to Yahoo / DDG.
_SEARCH_CHAIN = ("bing", "yahoo", "duckduckgo")
_SEARCH_TIMEOUT_S = 4.0
_SEARCH_REGION = "ar-es"


def _fn(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        parameters["required"] = required
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "list_capabilities",
        "List what you can actually do right now (configured vs not).",
        {},
    ),
    _fn(
        "web_search",
        "Search the live internet FAST via Bing (Yahoo/DuckDuckGo fallback). "
        "ALWAYS use for facts you do not have locally — news, prices, people, how-to, "
        "distances, capitals, science. Prefer one quick search over guessing. "
        "Not for subjective taste/opinion (who is prettier, favorites).",
        {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        ["query"],
    ),
    _fn(
        "image_search",
        "Find illustrations / photos / diagrams FAST. Opens Google Images in the browser "
        "and returns a few image URLs. Use when the user asks for ilustración, imagen, "
        "foto, dibujo, diagrama, meme visual, or 'mostrame cómo se ve X'.",
        {
            "query": {"type": "string", "description": "What to illustrate / find images of"},
            "max_results": {"type": "integer", "default": 5},
            "open_browser": {
                "type": "boolean",
                "default": True,
                "description": "Open Google Images tab (default true on PC HUD)",
            },
        },
        ["query"],
    ),
    _fn(
        "read_page",
        "Fetch and read a web page (does not open a browser window).",
        {"url": {"type": "string"}},
        ["url"],
    ),
    _fn("weather", "Current weather and short forecast.", {"city": {"type": "string"}}, ["city"]),
    _fn("wikipedia", "Wikipedia summary in Spanish, English fallback.", {"topic": {"type": "string"}}, ["topic"]),
    _fn(
        "now",
        "Current date, time, and timezone. Prefer system_status if the user also wants which apps are open.",
        {},
    ),
    _fn(
        "system_status",
        "Local clock plus whether key apps are running (Chrome, Cursor, Discord, Excel, etc). Use this instead of web_search for PC/day status.",
        {},
    ),
    _fn(
        "daily_journal",
        "Append a thought, reminder, market note, or task to today's local journal file. Use when the user says tomá nota, anotá en el diario, bitácora, or wants a daily log.",
        {"content": {"type": "string"}},
        ["content"],
    ),
    _fn(
        "read_daily_journal",
        "Read local journal. which=today|yesterday|recent. "
        "Use recent for 'en qué me quedé', 'qué anoté ayer', bitácora context.",
        {
            "which": {
                "type": "string",
                "description": "today | yesterday | recent (default today)",
            },
        },
    ),
    _fn(
        "set_volume",
        "Set Windows master volume to an exact percent from 0 to 100. Use this instead of media vol_up/vol_down when a number is given.",
        {"level": {"type": "integer"}},
        ["level"],
    ),
    _fn(
        "undo_last",
        "Undo the last reversible PC action within ~30s (volume or clipboard). Use when the user says deshacer/undo.",
        {},
    ),
    _fn("calculate", "Exact arithmetic. Expression like 12.5 * 1.21", {"expression": {"type": "string"}}, ["expression"]),
    _fn(
        "remember",
        "Store a durable fact about the user.",
        {"key": {"type": "string"}, "value": {"type": "string"}},
        ["key", "value"],
    ),
    _fn("recall", "Read stored facts. Omit key to list all.", {"key": {"type": "string"}}),
    _fn("forget", "Delete a stored fact by key.", {"key": {"type": "string"}}, ["key"]),
    _fn("note", "Save a short note, or list notes if text is empty.", {"text": {"type": "string"}}),
    _fn(
        "set_reminder",
        "Set a reminder at local ISO-8601 datetime. HUD will beep at that time.",
        {
            "when_iso": {"type": "string", "description": "e.g. 2026-08-20T18:30:00"},
            "text": {"type": "string"},
        },
        ["when_iso", "text"],
    ),
    _fn(
        "set_timer",
        "Timer from now, in minutes. HUD beeps when it fires.",
        {"minutes": {"type": "number"}, "text": {"type": "string"}},
        ["minutes", "text"],
    ),
    _fn("list_reminders", "List pending reminders and timers.", {}),
    _fn("cancel_reminder", "Cancel pending reminder(s) matching text.", {"query": {"type": "string"}}, ["query"]),
    _fn(
        "open_browser",
        "Open a URL in the user's default browser on this PC.",
        {"url": {"type": "string"}},
        ["url"],
    ),
    _fn("google", "Open a Google search in the browser.", {"query": {"type": "string"}}, ["query"]),
    _fn(
        "open_maps",
        "Open Google Maps directions (GPS-aware when the client has location). "
        "destination required; origin optional (lat,lng or place). "
        "On phone sessions prefer phone_hands action=navigate instead.",
        {"destination": {"type": "string"}, "origin": {"type": "string"}},
        ["destination"],
    ),
    _fn(
        "intercom_action",
        "Building intercom / doorbell if linked in .env (HA_INTERCOM_*). "
        "action: status | answer/atender (press button) | open/abrir door lock (owner) | "
        "view/ver camera stream. Only works when configured — never invents devices.",
        {
            "action": {
                "type": "string",
                "description": "status | answer | open | view",
            },
        },
        ["action"],
    ),
    _fn(
        "compose_whatsapp",
        "Open WhatsApp with a draft message. User must tap send. Phone with country code.",
        {"phone": {"type": "string"}, "text": {"type": "string"}},
        ["phone", "text"],
    ),
    _fn(
        "open_app",
        "Open a PC app: chrome, edge, brave, firefox, notepad, calculadora, paint, explorer, "
        "spotify, discord, whatsapp, telegram, cursor, vscode, word, excel, steam, "
        "taskmgr, terminal, powershell, snip/recortes, configuracion, wifi, bluetooth, sonido. "
        "Also resolves Start Menu shortcuts by name.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _fn(
        "open_folder",
        "Open desktop, downloads, documents, or workspace in Explorer.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _fn(
        "list_files",
        "List files in THIS user's workspace (data/users/<username>/workspace). "
        "Optional relative subfolder. Prefer for 'qué hay en el workspace / archivos'.",
        {"relative": {"type": "string"}},
    ),
    _fn(
        "analyze_workspace",
        "JSON telemetry of THIS user's workspace: file counts, today's diario present, "
        "sample filenames. Use before mix_tracks or when asked what is in the workspace.",
        {},
    ),
    _fn(
        "kitchen_recipe",
        "Kitchen assistant (alias kitchen_action). "
        "action=listar → local catalog. "
        "action=buscar (default) → local first, then FAST web search; returns speakable recipe. "
        "Optional recipe_text saves a custom recipe. Never tell the user to call tools.",
        {
            "action": {
                "type": "string",
                "description": "buscar | listar (default buscar)",
            },
            "dish": {"type": "string", "description": "Food / dish name (when buscar)"},
            "recipe_text": {
                "type": "string",
                "description": "Optional full recipe text to save",
            },
        },
    ),
    _fn(
        "wellness_action",
        "Local wellness (training, nutrition, menstrual/pregnancy notes, smartwatch dump). "
        "PRIVATE to the active user sandbox. "
        "action=registrar → save event; resumen → last events; leer_reloj → "
        "workspace/smartwatch_metrics.json (steps/sleep/HR/HRV); consejo → free-text advice "
        "(must include health Safe-Disclaimer). Not a doctor — informational only.",
        {
            "action": {
                "type": "string",
                "description": "consejo | registrar | resumen | leer_reloj",
            },
            "tipo_tema": {
                "type": "string",
                "description": "nutricion | entrenamiento | menstruacion | embarazo | smartwatch | general",
            },
            "notas_registro": {
                "type": "string",
                "description": "Symptom / milestone notes when action=registrar",
            },
        },
        ["action"],
    ),
    _fn(
        "music_action",
        "Everyday music: action=play_standard (opens YouTube/Spotify via play_music) "
        "or mix_tracks (Hardtech remix from workspace audio files). "
        "play params: track_name, optional platform. "
        "mix params: track_base, track_overlay, target_bpm (default 142).",
        {
            "action": {"type": "string", "description": "play_standard | mix_tracks"},
            "track_name": {"type": "string"},
            "platform": {"type": "string"},
            "track_base": {"type": "string"},
            "track_overlay": {"type": "string"},
            "target_bpm": {"type": "number"},
            "output_file": {"type": "string"},
        },
        ["action"],
    ),
    _fn(
        "purge_tts_cache",
        "Delete Piper phrase-cache WAV/MP3 older than N days (default 7). Owner maintenance.",
        {"days": {"type": "number", "description": "Age limit in days (default 7)"}},
    ),
    _fn(
        "backup_notes",
        "Zip synced notes (memory notes + optional notes/ folder) into workspace/backup_notes_*.zip.",
        {},
    ),
    _fn(
        "read_file",
        "Read a UTF-8 file from THIS user's workspace only (relative path). "
        "Use for notes, diario_YYYY-MM-DD.txt, or files they mention in their sandbox.",
        {"relative": {"type": "string"}},
        ["relative"],
    ),
    _fn(
        "write_file",
        "Write a UTF-8 file inside THIS user's workspace only.",
        {
            "relative": {"type": "string"},
            "content": {"type": "string"},
            "append": {"type": "boolean", "default": False},
        },
        ["relative", "content"],
    ),
    _fn("screenshot", "Capture the PC screen into workspace/screenshot.png.", {}),
    _fn("set_clipboard", "Copy text to the Windows clipboard.", {"text": {"type": "string"}}, ["text"]),
    _fn(
        "get_clipboard",
        "Read the Windows clipboard text. Use when the user asks to review, summarize, "
        "fix, or look at what they just copied (Ctrl+C / portapapeles / 'lo que copié').",
        {},
    ),
    _fn(
        "power_control",
        "OWNER power on this Windows PC: action=shutdown (/s /t 30), restart (/r /t 10), "
        "abort (/a), or lock (LockWorkStation). Only when the user clearly orders "
        "apagar/reiniciar/cancelar apagado/bloquear pantalla.",
        {"action": {"type": "string", "description": "shutdown | restart | abort | lock"}},
        ["action"],
    ),
    _fn(
        "media",
        "Media/volume keys: play_pause, next, prev, stop, vol_up, vol_down, mute.",
        {"action": {"type": "string"}},
        ["action"],
    ),
    _fn(
        "play_music",
        "Play or search a song/artist/playlist via deep-link URL (no keyboard macros). "
        "YouTube/Brave by default, or Spotify app. "
        "Use when the user asks to hear music (poneme, reproducí, YouTube, Cerati, etc.).",
        {
            "query": {
                "type": "string",
                "description": "Song, artist, album, or playlist name.",
            },
            "platform": {
                "type": "string",
                "description": "youtube (default) | ytmusic | spotify",
            },
            "browser": {
                "type": "string",
                "description": "brave (default) | chrome | edge",
            },
        },
        ["query"],
    ),
    _fn(
        "app_search_action",
        "Open Brave/Chrome/Edge directly on a search URL (YouTube, Google, YT Music, Spotify web). "
        "Prefer this for 'abrí brave y poné youtube …' — zero keyboard macros, Fast-Path friendly.",
        {
            "browser": {
                "type": "string",
                "description": "brave | chrome | edge (default brave)",
            },
            "platform": {
                "type": "string",
                "description": "youtube | ytmusic | google | images | spotify",
            },
            "query": {"type": "string", "description": "Search / song / artist string"},
        },
        ["query"],
    ),
    _fn(
        "send_email",
        "Send email via SMTP if configured in .env.",
        {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
        ["to", "subject", "body"],
    ),
    _fn(
        "home_assistant",
        "Call a Home Assistant service if HA_URL and HA_TOKEN are set. "
        "Lights/switches: turn_on/off. Climate temperature is hard-capped 18–26 C in Python. "
        "Locks/covers/alarm: owner only. Never shell_command.",
        {
            "domain": {"type": "string"},
            "service": {"type": "string"},
            "entity_id": {"type": "string"},
            "temperature": {"type": "number"},
        },
        ["domain", "service"],
    ),
    _fn(
        "control_device",
        "Turn a Home Assistant light/switch/fan on or off by entity_id "
        "(e.g. light.living, action=on|off|toggle). Owner may also set climate 18–26 C.",
        {
            "entity_id": {"type": "string"},
            "action": {"type": "string"},
            "temperature": {"type": "number"},
        },
        ["entity_id", "action"],
    ),
    _fn(
        "home_states",
        "List Home Assistant entity states (lights/switches; owner also climate/locks).",
        {"domain": {"type": "string"}},
    ),
    _fn(
        "phone_hands",
        "Control the user's phone when they are talking from the Ilaria Android or iOS app. "
        "action: call, sms, whatsapp, maps, navigate, browser, search, youtube, music, "
        "open_app, torch, camera, gallery, settings, wifi, bluetooth, volume, share, "
        "clipboard, alarm, timer, calendar, contacts, email, "
        "open_wifi_settings, open_app_settings, clear_http, refresh_device_snap. "
        "maps/navigate: destination place or address; phone uses GPS origin when permitted. "
        "target: phone number, place, URL, or any installed app name except banking apps, "
        "torch on/off, volume up/down/mute/0-100, alarm HH:MM, timer minutes. "
        "text: SMS/WhatsApp/share body. Never open bank/wallet banking apps. "
        "Opens the system UI so the user confirms calls and messages. Never silent SMS.",
        {
            "action": {"type": "string"},
            "target": {"type": "string"},
            "text": {"type": "string"},
        },
        ["action"],
    ),
    _fn(
        "queue_phone_fix",
        "Enqueue Android maintenance for the CURRENT phone session only "
        "(open_wifi_settings, open_app_settings, clear_http, refresh_device_snap). "
        "Uses the same phone_actions SSE queue. Android client surface required.",
        {
            "action": {
                "type": "string",
                "description": "open_wifi_settings | open_app_settings | clear_http | refresh_device_snap",
            },
        },
        ["action"],
    ),
    _fn(
        "get_system_health",
        "Diagnose ILARIA local stack: HUD /health, Ollama API, Piper voice files, "
        "Home Assistant (if configured), UDP discover 8788, RAM. "
        "Use for 'diagnostica', 'qué está caído', stack health — not for open apps list "
        "(that is system_status).",
        {},
    ),
    _fn(
        "diagnose_pc",
        "Measure THIS PC performance right now: CPU%%, RAM%%, free disk C:, top RAM processes, "
        "and short upgrade/cleanup advice (bottlenecks). "
        "Use for 'por qué anda lenta la PC', 'cuello de botella', 'qué me conviene mejorar'. "
        "Do NOT web_search for that — inspect the machine.",
        {},
    ),
    _fn(
        "translate_text",
        "Translate a phrase to another language and return the translated text (spoken answer). "
        "Use for 'traducí…', 'cómo se dice X en inglés', 'qué significa hello'. "
        "Prefer this over opening Google Translate in the browser.",
        {
            "text": {"type": "string", "description": "Phrase to translate"},
            "target": {
                "type": "string",
                "description": "Target language code or name (es, en, it, pt, fr, de…). Default es.",
            },
            "source": {
                "type": "string",
                "description": "Source language or 'auto'. Default auto.",
            },
        },
        ["text"],
    ),
    _fn(
        "windows_howto",
        "Local Windows how-to: spoken steps and open Settings when useful "
        "(uninstall, hosts, wifi, bluetooth, updates, startup, disk, sound, display, taskmgr). "
        "Use for 'cómo desinstalo…', 'dónde está el hosts', 'cómo libero espacio'. "
        "Do NOT web_search for these common PC tasks.",
        {
            "query": {"type": "string", "description": "User how-to phrase"},
        },
        ["query"],
    ),
    _fn(
        "shop_compare",
        "Live shopping comparison summary (notebook/celu/TV/etc.) with anti-SEO filtering. "
        "Use for 'mejor notebook por X', 'cuál celular conviene'. Returns a short spoken summary.",
        {
            "query": {"type": "string", "description": "Product / budget question"},
        },
        ["query"],
    ),
    _fn(
        "replay_last_music",
        "Replay the last remembered track or yesterday's journal music. "
        "Use for vague 'poné eso', 'lo de ayer', 'la última canción'.",
        {
            "hint": {"type": "string", "description": "Original vague phrase"},
        },
    ),
    _fn(
        "code_assist",
        "Programming / debug help: open Cursor or VS Code and return a short error digest. "
        "Use for traceback, bug, 'no compila', 'explicame este error'. "
        "Do NOT read a whole file aloud — keep the spoken reply short.",
        {
            "query": {"type": "string", "description": "Error text or coding ask"},
        },
        ["query"],
    ),
    _fn(
        "calendar_event",
        "Local calendar in the user workspace (no Google sync). "
        "action=add|next|today|day. For add pass title + when_iso. "
        "Use for 'agendá mañana a las 10…', 'qué tengo hoy'.",
        {
            "action": {"type": "string", "description": "add | next | today | day"},
            "title": {"type": "string"},
            "when_iso": {"type": "string"},
            "offset_days": {"type": "integer"},
        },
        ["action"],
    ),
    _fn(
        "run_ha_routine",
        "Activate a Home Assistant scene or owner script by friendly name or entity_id. "
        "Use for 'activá la escena noche', 'modo cine', 'ejecutá script.xxx'.",
        {
            "kind": {"type": "string", "description": "scene | script"},
            "name": {"type": "string", "description": "Friendly name or entity_id"},
        },
        ["name"],
    ),
    _fn(
        "draft_or_send_email",
        "Send email via SMTP if configured; otherwise open a mailto draft. "
        "Use for 'mandá un mail a user@x.com asunto … cuerpo …'.",
        {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        ["to", "subject", "body"],
    ),
    _fn(
        "relaunch_service",
        "One-step allowlisted remediación of ILARIA stack only. "
        "service: ollama | piper | ha_ping. No arbitrary shell. Owner-oriented.",
        {
            "service": {
                "type": "string",
                "description": "ollama, piper, or ha_ping",
            },
        },
        ["service"],
    ),
    _fn(
        "check_lan_status",
        "Deep home LAN check: local IP, internet, gateway reachability, DNS servers, "
        "Wi‑Fi SSID/signal, HUD URLs for the phone, UDP discover 8788. "
        "Returns a short spoken diagnosis (also structured fields).",
        {},
    ),
    _fn(
        "mix_tracks",
        "Hardtech BPM remix: overlay two audio files from the user workspace via "
        "music/music_remixer.py (librosa+pydub). Owner/PC only. "
        "base_file and overlay_file are filenames inside the workspace. "
        "bpm_target default 140. Writes remix_generado.mp3 (or output_file).",
        {
            "base_file": {"type": "string", "description": "Base track filename in workspace"},
            "overlay_file": {"type": "string", "description": "Overlay/vocals filename in workspace"},
            "bpm_target": {"type": "number", "description": "Target BPM (default 140)"},
            "output_file": {"type": "string", "description": "Optional output filename"},
        },
        ["base_file", "overlay_file"],
    ),
]


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(text)


def _image_search(
    query: str,
    max_results: int = 5,
    *,
    open_browser: bool = True,
    actions: Actions | None = None,
) -> str:
    """Fast image/illustration lookup + optional Google Images tab."""
    q = " ".join((query or "").split())
    if not q:
        return "Empty image query."
    limit = max(1, min(int(max_results or 5), 8))
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for backend in ("bing", "duckduckgo", "yahoo"):
        try:
            found = list(
                DDGS(timeout=int(_SEARCH_TIMEOUT_S)).images(
                    q, max_results=limit, backend=backend
                )
                or []
            )
            if found:
                rows = found
                break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{backend}: {exc}")
    opened = ""
    surface = ""
    if actions is not None:
        surface = (getattr(actions, "client_surface", "hud") or "hud").strip().lower()
    if open_browser and actions is not None and surface not in {
        "android",
        "ios",
        "iphone",
        "ipad",
    }:
        try:
            opened = actions.app_search_action(
                browser="brave",
                platform="images",
                query=q,
            )
        except Exception as exc:  # noqa: BLE001
            opened = f"(browser open failed: {exc})"
    if not rows:
        detail = "; ".join(errors[:2]) if errors else "sin hits"
        if opened:
            return f"Abrí Google Imágenes para «{q}». ({detail})"
        return f"No image results. ({detail})"
    lines = [f"Images for «{q}» ({len(rows)} hits)."]
    if opened:
        lines.append(f"Browser: {opened}")
    for item in rows[:limit]:
        title = str(item.get("title") or item.get("name") or "").strip()
        url = str(item.get("image") or item.get("url") or item.get("thumbnail") or "").strip()
        page = str(item.get("url") or item.get("source") or "").strip()
        if not url and not page:
            continue
        lines.append(f"- {title or 'imagen'}\n  {url or page}")
    lines.append("Decile al usuario que ya abrí las ilustraciones en el navegador.")
    return "\n".join(lines)


def _search_relevance(query: str, rows: list[dict[str, Any]]) -> float:
    """0–1-ish score: how many query tokens appear in the top snippets."""
    keys = [w.lower() for w in re.findall(r"[a-záéíóúñü0-9]{3,}", (query or "").lower())]
    # Drop ultra-common Spanish fillers that inflate false matches.
    stop = {
        "que",
        "qué",
        "cual",
        "cuál",
        "como",
        "cómo",
        "para",
        "por",
        "una",
        "unos",
        "unas",
        "del",
        "los",
        "las",
        "con",
        "sin",
        "hoy",
        "entre",
        "desde",
        "hasta",
        "sobre",
        "quien",
        "quién",
        "donde",
        "dónde",
        "cuando",
        "cuándo",
        "cuanto",
        "cuánto",
        "http",
        "https",
        "www",
    }
    keys = [k for k in keys if k not in stop][:8]
    if not keys or not rows:
        return 0.0
    hits = 0
    for item in rows[:3]:
        blob = f"{item.get('title') or ''} {item.get('body') or item.get('snippet') or ''}".lower()
        hits += sum(1 for k in keys if k in blob)
    return hits / max(len(keys), 1)


def _clean_search_query(query: str) -> str:
    """Strip question wrappers so Bing does not match RAE 'cuál'."""
    t = " ".join((query or "").split()).strip().strip("¿?¡!")
    t = re.sub(
        r"^(?:cu[aá]l\s+es|qu[eé]\s+es|qui[eé]n\s+(?:es|fue)|d[oó]nde\s+(?:est[aá]|queda)|"
        r"cu[aá]nto\s+(?:es|vale)|decime|contame)\s+",
        "",
        t,
        flags=re.I,
    )
    return " ".join(t.split()).strip(" .") or (query or "").strip()


def _search(query: str, max_results: int = 5, *, workspace: Path | None = None) -> str:
    """Bing-first live search (fast); Yahoo/DDG fallback if relevance is poor."""
    from jarvis.search_cache import format_hit, lookup, store

    q = _clean_search_query(" ".join((query or "").split()))
    if not q:
        return "Empty query."
    from jarvis.search_cache import is_freshness_query

    # FX / news / weather: always hit the live web (no semantic cache).
    fresh = is_freshness_query(q)
    if not fresh:
        cached = lookup(q, workspace, kind="web")
        if cached:
            print(f"[SEARCH_CACHE] hit score={cached.get('score')} for «{q[:60]}»")
            return format_hit(cached)

    limit = max(1, min(int(max_results or 5), 8))
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    errors: list[str] = []
    engine_used = ""

    def _take(rows: list[dict[str, Any]] | None, engine: str) -> None:
        collected.clear()
        seen.clear()
        for item in rows or []:
            href = str(item.get("href") or item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or item.get("snippet") or "").strip()
            key = (href.split("?")[0].lower() if href else "") or title[:48].lower()
            if not key or key in seen:
                continue
            seen.add(key)
            collected.append({"title": title, "href": href, "body": body, "engine": engine})

    best_rows: list[dict[str, Any]] = []
    best_engine = ""
    best_score = -1.0
    # One DDGS client for the whole chain (connection reuse).
    try:
        ddgs = DDGS(timeout=int(_SEARCH_TIMEOUT_S))
    except Exception as exc:  # noqa: BLE001
        return f"No results. (ddgs: {exc})"

    def _engine(backend: str) -> tuple[str, list[dict[str, Any]], str]:
        try:
            rows = ddgs.text(
                q,
                max_results=limit,
                backend=backend,
                region=_SEARCH_REGION,
            )
            return backend, list(rows or []), ""
        except Exception as exc:  # noqa: BLE001
            return backend, [], f"{backend}: {exc}"

    for backend in _SEARCH_CHAIN:
        eng, rows, err = _engine(backend)
        if err:
            errors.append(err)
        if not rows:
            continue
        score = _search_relevance(q, rows)
        print(f"[SEARCH] {eng} score={score:.2f} n={len(rows)}")
        if score > best_score:
            best_score = score
            best_rows = rows
            best_engine = eng
        # Good enough — stop early (Bing usually wins here).
        if score >= 0.7 or (eng == "bing" and len(rows) >= 3 and score >= 0.45):
            break

    if best_rows:
        engine_used = best_engine
        _take(best_rows, best_engine)

    # Refuse to ship / cache junk when no engine matched the query tokens.
    if best_score < 0.25:
        detail = "; ".join(errors[:2]) if errors else f"score={best_score:.2f}"
        return f"No results. (baja relevancia: {detail})"

    if not collected:
        detail = "; ".join(errors[:2]) if errors else "sin detalle"
        return f"No results. ({detail})"

    collected = collected[:limit]
    lines = [f"Source: {engine_used} ({len(collected)} hits)."]
    for item in collected:
        lines.append(f"- {item['title']}\n  {item['href']}\n  {item['body']}")

    # One top page only when snippets are very thin AND relevance was weak.
    thin = sum(1 for item in collected if len(item.get("body") or "") < 40)
    body_chars = sum(len(item.get("body") or "") for item in collected)
    top = next((item["href"] for item in collected if item.get("href")), "")
    if best_score < 0.7 and thin >= max(2, len(collected) // 2) and body_chars < 180 and top:
        try:
            text = _read_page(top, timeout_s=3.5)
            if text and not text.startswith(("Fetch failed", "Invalid", "Empty", "Blocked")):
                lines.append(f"\n--- Top page extract ---\nPage extract ({top}):\n{text[:1200]}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Page extract skipped: {exc}")

    result = "\n".join(lines)
    # Do not cache FX/news/weather — next ask must be live again.
    if best_score >= 0.35 and not fresh:
        store(q, result, workspace, kind="web")
    return result


def _read_page(url: str, timeout_s: float = 8.0) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "Invalid URL."
    headers = {"User-Agent": "Ilaria/1.5 personal-assistant"}
    try:
        with httpx.Client(timeout=float(timeout_s), follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            if response.status_code in {401, 403, 429}:
                return f"Blocked ({response.status_code}): the site refused the fetch. Use another result."
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return f"Fetch failed: {exc}"
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and not url.endswith((".html", ".htm")):
        text = response.text[:6000]
        return text or f"Non-HTML response ({content_type})."
    parser = _VisibleText()
    try:
        parser.feed(response.text)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", response.text)
        return re.sub(r"\s+", " ", text)[:8000]
    joined = " ".join(parser.parts)
    return joined[:8000] or "Empty page."


def _weather(city: str) -> str:
    q = city.strip() or "Buenos Aires"
    url = f"https://wttr.in/{quote(q)}"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params={"format": "j1"})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return f"Weather failed: {exc}"
    current = payload.get("current_condition", [{}])[0]
    nearest = payload.get("nearest_area", [{}])[0]
    area = (nearest.get("areaName") or [{}])[0].get("value", q)
    country = (nearest.get("country") or [{}])[0].get("value", "")
    desc = (current.get("weatherDesc") or [{}])[0].get("value", "")
    temp = current.get("temp_C", "?")
    feels = current.get("FeelsLikeC", "?")
    humidity = current.get("humidity", "?")
    wind = current.get("windspeedKmph", "?")
    days = payload.get("weather", [])[:2]
    forecast = []
    for day in days:
        forecast.append(f"{day.get('date')}: {day.get('mintempC')}–{day.get('maxtempC')} C")
    return (
        f"{area}, {country}: {desc}, {temp} C (feels {feels} C), "
        f"humidity {humidity}%, wind {wind} km/h. "
        + " | ".join(forecast)
    )


def weather_now(city: str) -> str:
    return _weather(city)


def make_executor(
    settings: Settings,
    memory: Memory,
    actions: Actions,
) -> Callable[[str, str], str]:
    def execute(name: str, arguments_json: str) -> str:
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError:
            return (
                "ERROR: tool arguments must be a JSON object. "
                "Retry the same tool with valid JSON."
            )
        if not isinstance(args, dict):
            args = {}

        if name == "list_capabilities":
            return actions.capabilities()
        if name == "web_search":
            return _search(
                str(args.get("query", "")),
                int(args.get("max_results") or 5),
                workspace=actions.workspace,
            )
        if name == "image_search":
            open_flag = args.get("open_browser")
            if open_flag is None:
                open_flag = True
            return _image_search(
                str(args.get("query", "")),
                int(args.get("max_results") or 5),
                open_browser=bool(open_flag),
                actions=actions,
            )
        if name in {"read_page", "open_url"}:
            return _read_page(str(args.get("url", "")))
        if name == "weather":
            return _weather(str(args.get("city", "")))
        if name == "wikipedia":
            topic = str(args.get("topic", ""))
            from jarvis.search_cache import format_hit, lookup, store

            cached = lookup(topic, actions.workspace, kind="wiki")
            if cached:
                print(f"[SEARCH_CACHE] wiki hit score={cached.get('score')}")
                return format_hit(cached)
            answer = actions.wikipedia(topic)
            store(topic, answer, actions.workspace, kind="wiki")
            return answer
        if name == "now":
            stamp = datetime.now(ZoneInfo(settings.timezone))
            return stamp.strftime("%Y-%m-%d %H:%M:%S %Z")
        if name == "system_status":
            return actions.system_status()
        if name == "daily_journal":
            return actions.daily_journal(str(args.get("content", "")))
        if name == "read_daily_journal":
            return actions.read_daily_journal(str(args.get("which") or args.get("day") or "today"))
        if name == "set_volume":
            raw_level = args.get("level", args.get("value", args.get("percent", args.get("volumen"))))
            try:
                level = int(float(raw_level if raw_level is not None else 0))
            except (TypeError, ValueError):
                return "Nivel de volumen: un numero de 0 a 100."
            return actions.set_volume(level)
        if name == "undo_last":
            return actions.undo_last()
        if name == "mix_tracks":
            from jarvis.music_bridge import run_hardtech_remix

            if not getattr(actions, "is_owner", False):
                return "Remix Hardtech solo lo puede disparar el dueño desde la PC."
            surface = (getattr(actions, "client_surface", "hud") or "hud").strip().lower()
            if surface in {"android", "ios", "iphone", "ipad"}:
                return "El remix se hace en la PC, no desde el celular."
            bpm = args.get("bpm_target")
            try:
                bpm_f = float(bpm) if bpm is not None else 140.0
            except (TypeError, ValueError):
                bpm_f = 140.0
            out_name = str(args.get("output_file") or "remix_generado.mp3").strip() or "remix_generado.mp3"
            return run_hardtech_remix(
                track_base=str(args.get("base_file") or ""),
                track_overlay=str(args.get("overlay_file") or ""),
                output=out_name,
                bpm_target=bpm_f,
                workspace=actions.workspace,
            )
        if name == "calculate":
            return actions.calculate(str(args.get("expression", "")))
        if name == "remember":
            return memory.remember(str(args.get("key", "")), str(args.get("value", "")))
        if name == "recall":
            key = args.get("key")
            return memory.recall(str(key) if key else None)
        if name == "forget":
            return memory.forget(str(args.get("key", "")))
        if name == "note":
            text = str(args.get("text", "")).strip()
            return memory.add_note(text) if text else memory.list_notes()
        if name == "set_reminder":
            return memory.add_reminder(str(args.get("when_iso", "")), str(args.get("text", "")))
        if name == "set_timer":
            return memory.add_timer(float(args.get("minutes") or 0), str(args.get("text", "")), settings.timezone)
        if name == "list_reminders":
            return memory.pending_reminders()
        if name == "cancel_reminder":
            return memory.cancel_reminder(str(args.get("query", "")))
        if name == "open_browser":
            return actions.open_browser(str(args.get("url", "")))
        if name == "google":
            return actions.google(str(args.get("query", "")))
        if name == "open_maps":
            return actions.open_maps(str(args.get("destination", "")), str(args.get("origin", "")))
        if name == "intercom_action":
            from jarvis.intercom import run_intercom

            return run_intercom(
                settings,
                str(args.get("action") or "status"),
                is_owner=bool(getattr(actions, "is_owner", False)),
                open_url=lambda url: actions.open_browser(url),
            )
        if name == "compose_whatsapp":
            return actions.compose_whatsapp(str(args.get("phone", "")), str(args.get("text", "")))
        if name == "open_app":
            return actions.open_app(str(args.get("name", "")))
        if name == "open_folder":
            return actions.open_folder(str(args.get("name", "")))
        if name == "list_files":
            return actions.list_files(str(args.get("relative", "") or ""))
        if name == "analyze_workspace":
            return actions.analyze_workspace()
        if name == "kitchen_recipe":
            return actions.kitchen_recipe(
                str(args.get("dish") or args.get("comida") or ""),
                str(args.get("recipe_text") or args.get("receta_texto_completo") or ""),
                action=str(args.get("action") or "buscar"),
            )
        if name == "wellness_action":
            return actions.wellness_action(
                action=str(args.get("action") or "consejo"),
                tipo_tema=str(args.get("tipo_tema") or args.get("tema") or "general"),
                notas_registro=str(args.get("notas_registro") or args.get("notas") or ""),
            )
        if name == "music_action":
            action = str(args.get("action") or "").strip()
            params = {k: v for k, v in args.items() if k != "action"}
            return actions.music_action(action, **params)
        if name == "purge_tts_cache":
            try:
                days = int(float(args.get("days") or 7))
            except (TypeError, ValueError):
                days = 7
            return actions.purge_tts_cache(days)
        if name == "backup_notes":
            return actions.backup_notes()
        if name == "read_file":
            return actions.read_file(str(args.get("relative", "")))
        if name == "write_file":
            return actions.write_file(
                str(args.get("relative", "")),
                str(args.get("content", "")),
                bool(args.get("append")),
            )
        if name == "screenshot":
            return actions.screenshot()
        if name == "set_clipboard":
            return actions.set_clipboard(str(args.get("text", "")))
        if name == "get_clipboard":
            return actions.get_clipboard()
        if name == "power_control":
            return actions.power_control(str(args.get("action", "")))
        if name == "media":
            return actions.media(str(args.get("action", "")))
        if name == "play_music":
            return actions.play_music(
                str(args.get("query", "")),
                platform=str(args.get("platform", "youtube") or "youtube"),
                browser=str(args.get("browser", "") or ""),
            )
        if name == "app_search_action":
            return actions.app_search_action(
                browser=str(args.get("browser", "brave") or "brave"),
                platform=str(args.get("platform", "youtube") or "youtube"),
                query=str(args.get("query", "") or args.get("busqueda", "")),
            )
        if name == "send_email":
            return actions.send_email(
                str(args.get("to", "")),
                str(args.get("subject", "")),
                str(args.get("body", "")),
            )
        if name == "home_assistant":
            temp = args.get("temperature")
            try:
                temperature = float(temp) if temp is not None and str(temp) != "" else None
            except (TypeError, ValueError):
                return "Temperatura inválida."
            return actions.home_assistant(
                str(args.get("domain", "")),
                str(args.get("service", "")),
                str(args.get("entity_id", "")),
                temperature,
            )
        if name == "control_device":
            temp = args.get("temperature")
            try:
                temperature = float(temp) if temp is not None and str(temp) != "" else None
            except (TypeError, ValueError):
                return "Temperatura inválida."
            return actions.control_device(
                str(args.get("entity_id", "")),
                str(args.get("action", "")),
                temperature,
            )
        if name == "home_states":
            return actions.home_states(str(args.get("domain", "") or ""))
        if name == "phone_hands":
            if getattr(actions, "client_surface", "hud") not in {"android", "ios"}:
                return "Eso se hace en el celular. Pedilo desde la app Ilaria (Wi-Fi)."
            from jarvis.phone_hands import queue_action

            return queue_action(actions.phone_queue, args)
        if name == "queue_phone_fix":
            if getattr(actions, "client_surface", "hud") not in {"android", "ios"}:
                return "Eso se hace en el celular. Pedilo desde la app Ilaria (Wi-Fi)."
            from jarvis.phone_hands import queue_phone_fix

            return json.dumps(
                queue_phone_fix(actions.phone_queue, str(args.get("action", ""))),
                ensure_ascii=False,
            )
        if name == "get_system_health":
            from jarvis.self_healing import health_report_text

            return health_report_text(settings)
        if name == "diagnose_pc":
            return actions.diagnose_pc()
        if name == "translate_text":
            return actions.translate_text(
                str(args.get("text") or args.get("query") or ""),
                target=str(args.get("target") or args.get("to") or "es"),
                source=str(args.get("source") or args.get("from") or "auto"),
            )
        if name == "windows_howto":
            return actions.windows_howto(str(args.get("query") or args.get("text") or ""))
        if name == "shop_compare":
            from jarvis.shop_compare import run_shop_compare

            q = str(args.get("query") or args.get("text") or "")
            return run_shop_compare(q, execute)
        if name == "replay_last_music":
            return actions.replay_last_music(str(args.get("hint") or args.get("query") or ""))
        if name == "code_assist":
            return actions.code_assist(str(args.get("query") or args.get("text") or ""))
        if name == "calendar_event":
            return actions.calendar_event(
                action=str(args.get("action") or "next"),
                title=str(args.get("title") or ""),
                when_iso=str(args.get("when_iso") or args.get("when") or ""),
                offset_days=int(args.get("offset_days") or 0),
            )
        if name == "run_ha_routine":
            return actions.run_ha_routine(
                kind=str(args.get("kind") or "scene"),
                name=str(args.get("name") or args.get("entity_id") or ""),
            )
        if name == "draft_or_send_email":
            return actions.draft_or_send_email(
                str(args.get("to") or ""),
                str(args.get("subject") or ""),
                str(args.get("body") or ""),
            )
        if name == "relaunch_service":
            from jarvis.self_healing import relaunch_service

            result = relaunch_service(settings, str(args.get("service", "")))
            return json.dumps(result, ensure_ascii=False)
        if name == "check_lan_status":
            return actions.check_lan_speakable()
        return f"Unknown tool: {name}"

    return execute


def _tool_name(schema: dict[str, Any]) -> str:
    return str(schema["function"]["name"])


ALL_TOOL_NAMES = {_tool_name(item) for item in TOOL_SCHEMAS}
# Owner-only even when members_pc_hands is enabled.
OWNER_ONLY_TOOLS = {"power_control", "relaunch_service", "mix_tracks", "purge_tts_cache"}
PC_TOOLS = {
    "open_app",
    "open_folder",
    "screenshot",
    "media",
    "play_music",
    "app_search_action",
    "replay_last_music",
    "windows_howto",
    "code_assist",
    "calendar_event",
    "run_ha_routine",
    "draft_or_send_email",
    "set_volume",
    "undo_last",
    "send_email",
    "home_assistant",
    "compose_whatsapp",
    "write_file",
    "set_clipboard",
    "get_clipboard",
    "power_control",
    "relaunch_service",
    "mix_tracks",
    "purge_tts_cache",
    "backup_notes",
}
# Always available to members on the PC HUD (within policy). Still blocked on phone surfaces.
MEMBER_SAFE_PC = frozenset({"set_volume", "media", "undo_last"})
# webbrowser / PC shell openers — never expose these on phone surfaces
PHONE_BLOCKED_TOOLS = PC_TOOLS | {
    "open_browser",
    "google",
    "open_maps",
    "system_status",
    "list_files",
    "read_file",
    "control_device",
    "get_system_health",
    "check_lan_status",
}
MEMBER_TOOLS = (ALL_TOOL_NAMES - PC_TOOLS) | MEMBER_SAFE_PC


def schemas_for(allowed: set[str]) -> list[dict[str, Any]]:
    return [item for item in TOOL_SCHEMAS if _tool_name(item) in allowed]


def tools_for_surface(allowed: set[str] | None, surface: str) -> list[dict[str, Any]]:
    """Filter tool schemas so phone sessions cannot trigger PC-side openers."""
    base = set(ALL_TOOL_NAMES) if allowed is None else set(allowed)
    if (surface or "hud").strip().lower() in {"android", "ios", "iphone", "ipad"}:
        base -= PHONE_BLOCKED_TOOLS
    return schemas_for(base)
