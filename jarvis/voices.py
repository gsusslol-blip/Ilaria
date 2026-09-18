"""User-selectable TTS voices (Piper offline + Edge Neural fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis.piper_tts import _voice_dirs

DEFAULT_VOICE_ID = "ilaria"


@dataclass(frozen=True)
class VoiceProfile:
    id: str
    label: str
    style: str
    provider: str  # piper | edge
    piper_file: str = ""
    edge_voice: str = ""
    lang: str = "es"
    edge_rate: str = "+0%"
    edge_pitch: str = "+0Hz"


# Friendly catalog — IDs stored per user in accounts.sqlite.
_VOICE_DEFS: tuple[VoiceProfile, ...] = (
    VoiceProfile(
        id="ilaria",
        label="Ilaria Original",
        style="Femenina rioplatense, táctica (Piper Daniela)",
        provider="piper",
        piper_file="es_AR-daniela-high.onnx",
        edge_voice="es-AR-ElenaNeural",
        lang="es",
    ),
    VoiceProfile(
        id="sofia",
        label="Sofía",
        style="Femenina clara, latam (Piper Ald MX)",
        provider="piper",
        piper_file="es_MX-ald-medium.onnx",
        edge_voice="es-MX-DaliaNeural",
        lang="es",
    ),
    VoiceProfile(
        id="elena",
        label="Elena",
        style="Femenina argentina (Edge Neural)",
        provider="edge",
        edge_voice="es-AR-ElenaNeural",
        lang="es",
    ),
    VoiceProfile(
        id="mateo",
        label="Mateo",
        style="Masculina neutra (Edge)",
        provider="edge",
        edge_voice="es-MX-JorgeNeural",
        lang="es",
    ),
    VoiceProfile(
        id="carlos",
        label="Carlos",
        style="Masculina cálida España (Edge)",
        provider="edge",
        edge_voice="es-ES-AlvaroNeural",
        lang="es",
    ),
    VoiceProfile(
        id="jenny",
        label="Jenny (EN)",
        style="English female — for English replies",
        provider="edge",
        edge_voice="en-US-JennyNeural",
        lang="en",
    ),
    VoiceProfile(
        id="elsa",
        label="Elsa (IT)",
        style="Italiano femminile (Edge Neural)",
        provider="edge",
        edge_voice="it-IT-ElsaNeural",
        lang="it",
    ),
    VoiceProfile(
        id="diego",
        label="Diego (IT)",
        style="Italiano maschile (Edge Neural)",
        provider="edge",
        edge_voice="it-IT-DiegoNeural",
        lang="it",
    ),
    VoiceProfile(
        id="yui",
        label="Yui",
        style="Compañera suave (Edge + pitch) — vibe partner AI, no cosplay de marca",
        provider="edge",
        edge_voice="es-MX-DaliaNeural",
        lang="es",
        edge_rate="+4%",
        edge_pitch="+28Hz",
    ),
)


def _piper_file_exists(name: str) -> bool:
    if not name:
        return False
    for folder in _voice_dirs():
        path = folder / name
        if path.is_file() and Path(str(path) + ".json").is_file():
            return True
    return False


def list_voices(*, available_only: bool = True) -> list[dict[str, Any]]:
    """Public catalog for /api/voices and settings UI."""
    rows: list[dict[str, Any]] = []
    for voice in _VOICE_DEFS:
        piper_ok = _piper_file_exists(voice.piper_file) if voice.provider == "piper" else False
        if voice.provider == "piper" and not piper_ok:
            # Still list with edge fallback so the menu is never empty.
            engine = "edge" if voice.edge_voice else ""
            available = bool(voice.edge_voice)
        else:
            engine = voice.provider
            available = True if voice.provider == "edge" else piper_ok
        if available_only and not available:
            continue
        rows.append(
            {
                "id": voice.id,
                "label": voice.label,
                "style": voice.style,
                "provider": engine or voice.provider,
                "lang": voice.lang,
                "available": available,
                "piper_ready": piper_ok,
            }
        )
    return rows


def get_voice(voice_id: str | None) -> VoiceProfile:
    key = (voice_id or "").strip().lower() or DEFAULT_VOICE_ID
    aliases = {
        "daniela": "ilaria",
        "original": "ilaria",
        "default": "ilaria",
        "nova": "ilaria",
        "shimmer": "sofia",
        "alloy": "mateo",
        "echo": "carlos",
        "ald": "sofia",
        "italiano": "elsa",
        "italian": "elsa",
        "it": "elsa",
        "yui": "yui",
        "sao": "yui",
        "partner": "yui",
    }
    key = aliases.get(key, key)
    for voice in _VOICE_DEFS:
        if voice.id == key:
            return voice
    return _VOICE_DEFS[0]


def normalize_voice_id(raw: str | None) -> str:
    return get_voice(raw).id


def resolve_runtime(voice_id: str | None) -> dict[str, str]:
    """Map catalog id → provider + Edge name + optional Piper onnx filename."""
    voice = get_voice(voice_id)
    if voice.provider == "piper" and _piper_file_exists(voice.piper_file):
        return {
            "id": voice.id,
            "provider": "piper",
            "tts_voice": voice.edge_voice or "es-AR-ElenaNeural",
            "piper_model": voice.piper_file,
            "edge_rate": voice.edge_rate or "+0%",
            "edge_pitch": voice.edge_pitch or "+0Hz",
        }
    # Edge path (chosen or Piper missing).
    return {
        "id": voice.id,
        "provider": "edge",
        "tts_voice": voice.edge_voice or "es-AR-ElenaNeural",
        "piper_model": "",
        "edge_rate": voice.edge_rate or "+0%",
        "edge_pitch": voice.edge_pitch or "+0Hz",
    }


def preview_line(voice_id: str | None) -> str:
    voice = get_voice(voice_id)
    if voice.id == "yui":
        return "Hola… estoy acá con vos. ¿En qué te ayudo?"
    if voice.lang == "en":
        return f"Hi, I'm Ilaria with the {voice.label} voice."
    if voice.lang == "it":
        return f"Ciao, sono Ilaria con la voce {voice.label}."
    return f"Hola, soy Ilaria con la voz {voice.label}."
