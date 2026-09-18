"""Owner voice prefs (wake sensitivity, mic index, Whisper model) — local JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

_PATH = DATA_DIR / "voice_prefs.json"
_DEFAULTS = {
    "wake_sensitivity": 0.55,
    "wake_mic_index": -1,
    "faster_whisper_model": "",
    "stt_language": "es",
}

# Whisper / STT language codes accepted in Settings.
STT_LANGUAGES = frozenset({"", "es", "en", "it", "pt", "fr", "de", "auto"})
WHISPER_MODELS = frozenset({"", "tiny", "base", "small", "medium"})


def prefs_path() -> Path:
    return _PATH


def load_voice_prefs() -> dict[str, Any]:
    raw = dict(_DEFAULTS)
    if not _PATH.is_file():
        return raw
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return raw
    if not isinstance(data, dict):
        return raw
    for key, default in _DEFAULTS.items():
        if key in data and data[key] is not None:
            raw[key] = data[key]
    return raw


def save_voice_prefs(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_voice_prefs()
    if "wake_sensitivity" in patch:
        try:
            current["wake_sensitivity"] = max(0.1, min(1.0, float(patch["wake_sensitivity"])))
        except (TypeError, ValueError):
            pass
    if "wake_mic_index" in patch:
        try:
            current["wake_mic_index"] = int(patch["wake_mic_index"])
        except (TypeError, ValueError):
            pass
    if "faster_whisper_model" in patch:
        model = str(patch["faster_whisper_model"] or "").strip().lower()
        if model in WHISPER_MODELS:
            current["faster_whisper_model"] = model
    if "stt_language" in patch:
        lang = str(patch["stt_language"] or "").strip().lower()
        if lang in STT_LANGUAGES:
            current["stt_language"] = lang or "es"
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _apply_env(current, overwrite=True)
    return current


def _apply_env(prefs: dict[str, Any], *, overwrite: bool) -> None:
    """Push prefs into process env. overwrite=True clears stale keys on save."""
    set_fn = os.environ.__setitem__ if overwrite else os.environ.setdefault
    set_fn("WAKE_SENSITIVITY", str(prefs["wake_sensitivity"]))
    set_fn("WAKE_MIC_INDEX", str(prefs["wake_mic_index"]))
    model = str(prefs.get("faster_whisper_model") or "").strip()
    lang = str(prefs.get("stt_language") or "").strip()
    if overwrite:
        if model:
            os.environ["FASTER_WHISPER_MODEL"] = model
        else:
            os.environ.pop("FASTER_WHISPER_MODEL", None)
        if lang:
            os.environ["STT_LANGUAGE"] = lang
        else:
            os.environ.pop("STT_LANGUAGE", None)
    else:
        if model:
            os.environ.setdefault("FASTER_WHISPER_MODEL", model)
        if lang:
            os.environ.setdefault("STT_LANGUAGE", lang)


def apply_voice_prefs_to_env() -> None:
    _apply_env(load_voice_prefs(), overwrite=False)
