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
        if model in {"", "tiny", "base", "small", "medium"}:
            current["faster_whisper_model"] = model
    if "stt_language" in patch:
        lang = str(patch["stt_language"] or "").strip().lower()
        if lang in {"", "es", "en", "auto"}:
            current["stt_language"] = lang or "es"
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Reflect into process env so wake/whisper pick up without restart when possible.
    os.environ["WAKE_SENSITIVITY"] = str(current["wake_sensitivity"])
    os.environ["WAKE_MIC_INDEX"] = str(current["wake_mic_index"])
    if current.get("faster_whisper_model"):
        os.environ["FASTER_WHISPER_MODEL"] = str(current["faster_whisper_model"])
    if current.get("stt_language"):
        os.environ["STT_LANGUAGE"] = str(current["stt_language"])
    return current


def apply_voice_prefs_to_env() -> None:
    prefs = load_voice_prefs()
    os.environ.setdefault("WAKE_SENSITIVITY", str(prefs["wake_sensitivity"]))
    os.environ.setdefault("WAKE_MIC_INDEX", str(prefs["wake_mic_index"]))
    if prefs.get("faster_whisper_model"):
        os.environ.setdefault("FASTER_WHISPER_MODEL", str(prefs["faster_whisper_model"]))
    if prefs.get("stt_language"):
        os.environ.setdefault("STT_LANGUAGE", str(prefs["stt_language"]))
