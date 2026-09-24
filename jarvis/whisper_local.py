"""Local Faster-Whisper singleton (CUDA if available, else CPU int8)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from threading import Lock

from jarvis.config import DATA_DIR, Settings

_lock = Lock()
_model = None
_device = ""


def reset_model() -> None:
    """Drop cached Whisper so the next STT loads the preferred size."""
    global _model, _device
    with _lock:
        _model = None
        _device = ""


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def whisper_device() -> str:
    # Default CPU: keep the 6 GB GTX 1660 Ti free for Ollama (gemma2:2b / llama3:8b).
    forced = os.getenv("WHISPER_DEVICE", "cpu").strip().lower()
    if forced in {"cuda", "gpu"}:
        return "cuda"
    if forced == "cpu":
        return "cpu"
    try:
        import ctranslate2

        if int(ctranslate2.get_cuda_device_count()) > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _load(settings: Settings):
    global _model, _device
    with _lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        forced = (getattr(settings, "whisper_device", None) or "").strip().lower()
        _device = forced if forced in {"cpu", "cuda", "gpu"} else whisper_device()
        if _device == "gpu":
            _device = "cuda"
        name = (getattr(settings, "faster_whisper_model", None) or "base").strip() or "base"
        try:
            from jarvis.voice_prefs import load_voice_prefs

            pref = str(load_voice_prefs().get("faster_whisper_model") or "").strip()
            if pref:
                name = pref
        except Exception:
            pass
        env_model = (os.getenv("FASTER_WHISPER_MODEL") or "").strip()
        if env_model:
            name = env_model
        forced_compute = (os.getenv("WHISPER_COMPUTE_TYPE") or "").strip().lower()
        if forced_compute:
            compute = forced_compute
        else:
            compute = "float16" if _device == "cuda" else "int8"
        print(f"[+] Faster-Whisper local: model={name} device={_device} compute={compute}")
        _model = WhisperModel(name, device=_device, compute_type=compute)
        return _model


def transcribe_local(settings: Settings, data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower() or ".wav"
    if suffix not in {".webm", ".wav", ".mp3", ".ogg", ".mp4", ".m4a", ".flac"}:
        suffix = ".wav"
    # System temp — avoid OneDrive sync lag under data/.
    with tempfile.NamedTemporaryFile(prefix="stt-", suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        model = _load(settings)
        forced = (os.getenv("STT_LANGUAGE") or "").strip().lower() or None
        try:
            from jarvis.voice_prefs import load_voice_prefs

            pref_lang = str(load_voice_prefs().get("stt_language") or "").strip().lower()
            if pref_lang:
                forced = pref_lang
        except Exception:
            pass
        if forced in {"auto", "detect", "*"}:
            forced = None
        elif not forced:
            forced = "es"
        # Per-user voice language wins over the PC-wide STT pref (Sara = italiano).
        try:
            from jarvis.voices import get_voice

            voice_lang = get_voice(getattr(settings, "voice_id", "") or "").lang
            if voice_lang in {"es", "it", "en", "pt", "fr", "de"}:
                forced = voice_lang
        except Exception:
            pass
        prompts = {
            "es": "Ilaria, español rioplatense, comandos cortos.",
            "en": "Ilaria assistant, short English voice commands.",
            "it": "Ilaria, assistente vocale, comandi brevi in italiano.",
            "pt": "Ilaria, comandos de voz curtos em português.",
            "fr": "Ilaria, commandes vocales courtes en français.",
            "de": "Ilaria, kurze Sprachbefehle auf Deutsch.",
        }
        initial = prompts.get(forced or "", prompts["es"])
        segments, info = model.transcribe(
            path,
            beam_size=1,
            language=forced,
            vad_filter=True,
            vad_parameters={
                "threshold": 0.5,
                "min_silence_duration_ms": 400,
                "speech_pad_ms": 200,
            },
            condition_on_previous_text=False,
            without_timestamps=True,
            temperature=0.0,
            initial_prompt=initial,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        lang = getattr(info, "language", None) or forced or "es"
        try:
            from jarvis.stt import remember_detected_language

            remember_detected_language(str(lang))
        except Exception:
            pass
        return " ".join(text.split())
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
