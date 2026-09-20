"""Local speaker identification — who is talking (not STT).

Enroll short clips per person, then match new audio via mel-stat embeddings
(numpy only — no torch). Good enough to separate household voices on one mic.
"""

from __future__ import annotations

import io
import json
import math
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

from jarvis.config import DATA_DIR

SPEAKERS_DIR = DATA_DIR / "speakers"
_INDEX = SPEAKERS_DIR / "index.json"
_LOCK = Lock()

# Cosine threshold: higher = stricter (fewer false accepts).
DEFAULT_THRESHOLD = 0.78
MIN_SECONDS = 1.2
TARGET_SR = 16000
N_MELS = 40
N_FFT = 512
HOP = 160  # 10 ms @ 16 kHz
EMBED_DIM = N_MELS * 4 + 1  # mean + std + p25 + p75 + slope

_LABEL_RE = re.compile(r"^[a-zA-Z0-9_]{2,24}$")


@dataclass(frozen=True)
class SpeakerHit:
    label: str
    display_name: str
    score: float
    username: str = ""


def speakers_ready() -> bool:
    return len(list_speakers()) > 0


def list_speakers() -> list[dict[str, Any]]:
    idx = _load_index()
    out: list[dict[str, Any]] = []
    for label, meta in sorted(idx.items()):
        out.append(
            {
                "label": label,
                "display_name": str(meta.get("display_name") or label),
                "username": str(meta.get("username") or ""),
                "samples": int(meta.get("samples") or 0),
                "updated": float(meta.get("updated") or 0),
            }
        )
    return out


def enroll_speaker(
    audio: bytes,
    label: str,
    *,
    filename: str = "enroll.wav",
    display_name: str = "",
    username: str = "",
) -> dict[str, Any]:
    """Add / update a voiceprint from one utterance (≥ ~1.2 s of speech)."""
    key = _normalize_label(label)
    if not _LABEL_RE.match(key):
        raise ValueError("Etiqueta de voz: 2–24 letras, números o _")
    emb = embed_audio(audio, filename)
    if emb is None:
        raise ValueError(
            "No pude sacar huella de voz. Grabá al menos 2 segundos hablando claro (WAV preferido)."
        )
    with _LOCK:
        SPEAKERS_DIR.mkdir(parents=True, exist_ok=True)
        idx = _load_index()
        meta = dict(idx.get(key) or {})
        old = _read_embedding(key)
        if old is not None and old.shape == emb.shape:
            n = max(1, int(meta.get("samples") or 1))
            blended = (old * n + emb) / (n + 1)
            samples = n + 1
        else:
            blended = emb
            samples = 1
        _write_embedding(key, blended)
        meta.update(
            {
                "display_name": (display_name or meta.get("display_name") or key).strip()[:64],
                "username": (username or meta.get("username") or "").strip().lower()[:24],
                "samples": samples,
                "updated": time.time(),
                "dim": int(blended.shape[0]),
            }
        )
        idx[key] = meta
        _save_index(idx)
    return {
        "ok": True,
        "label": key,
        "display_name": meta["display_name"],
        "username": meta.get("username") or "",
        "samples": samples,
    }


def remove_speaker(label: str) -> bool:
    key = _normalize_label(label)
    with _LOCK:
        idx = _load_index()
        if key not in idx:
            return False
        del idx[key]
        _save_index(idx)
        path = SPEAKERS_DIR / f"{key}.npy"
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    return True


def identify_speaker(
    audio: bytes,
    *,
    filename: str = "audio.wav",
    threshold: float | None = None,
) -> SpeakerHit | None:
    """Return best enrolled match above threshold, else None."""
    emb = embed_audio(audio, filename)
    if emb is None:
        return None
    thr = float(threshold if threshold is not None else _env_threshold())
    idx = _load_index()
    best: SpeakerHit | None = None
    for label, meta in idx.items():
        ref = _read_embedding(label)
        if ref is None or ref.shape != emb.shape:
            continue
        score = float(_cosine(emb, ref))
        if best is None or score > best.score:
            best = SpeakerHit(
                label=label,
                display_name=str(meta.get("display_name") or label),
                score=score,
                username=str(meta.get("username") or ""),
            )
    if best is None or best.score < thr:
        return None
    return best


def speakable_identify(hit: SpeakerHit | None) -> str:
    if hit is None:
        return "No reconozco esa voz todavía. Enrolala desde Ajustes → Voces."
    return f"Te escucho, {hit.display_name}."


def embed_audio(audio: bytes, filename: str = "audio.wav") -> np.ndarray | None:
    """Build L2-normalized mel mean+std embedding, or None if too short / silent."""
    pcm, sr = decode_mono_pcm16(audio, filename)
    if pcm is None or sr <= 0 or len(pcm) < int(sr * MIN_SECONDS):
        return None
    if sr != TARGET_SR:
        pcm = _resample_linear(pcm, sr, TARGET_SR)
        sr = TARGET_SR
    # Drop near-silence frames by energy.
    x = pcm.astype(np.float32) / 32768.0
    if float(np.sqrt(np.mean(x * x))) < 0.008:
        return None
    mel = _log_mel(x, sr)
    if mel.shape[0] < 8:
        return None
    # Absolute long-term spectrum (no CMVN — that would erase speaker color).
    mean = mel.mean(axis=0)
    stdv = mel.std(axis=0)
    # Extra shape cues: spectral slope + energy percentiles.
    freqs = np.linspace(0.0, 1.0, N_MELS, dtype=np.float32)
    slope = float(np.polyfit(freqs, mean, 1)[0])
    p25, p75 = np.percentile(mel, [25, 75], axis=0)
    emb = np.concatenate(
        [
            mean,
            stdv,
            p25.astype(np.float32),
            p75.astype(np.float32),
            np.array([slope], dtype=np.float32),
        ]
    ).astype(np.float32)
    n = float(np.linalg.norm(emb))
    if n < 1e-8:
        return None
    return emb / n


def decode_mono_pcm16(data: bytes, filename: str = "") -> tuple[np.ndarray | None, int]:
    """Decode wav directly; webm/ogg/mp4 via PyAV when available."""
    lower = (filename or "").lower()
    if data[:4] == b"RIFF" or lower.endswith(".wav"):
        return _decode_wav(data)
    # Compressed HUD blobs
    try:
        return _decode_av(data)
    except Exception:
        return None, 0


# --- internals -------------------------------------------------------------


def _normalize_label(label: str) -> str:
    return (label or "").strip().lower().replace(" ", "_")


def _env_threshold() -> float:
    import os

    try:
        return max(0.55, min(0.95, float(os.getenv("SPEAKER_THRESHOLD", str(DEFAULT_THRESHOLD)))))
    except ValueError:
        return DEFAULT_THRESHOLD


def _load_index() -> dict[str, Any]:
    if not _INDEX.is_file():
        return {}
    try:
        raw = json.loads(_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_index(idx: dict[str, Any]) -> None:
    SPEAKERS_DIR.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _emb_path(label: str) -> Path:
    return SPEAKERS_DIR / f"{label}.npy"


def _read_embedding(label: str) -> np.ndarray | None:
    path = _emb_path(label)
    if not path.is_file():
        return None
    try:
        arr = np.load(path)
    except Exception:
        return None
    if not isinstance(arr, np.ndarray) or arr.ndim != 1:
        return None
    return arr.astype(np.float32)


def _write_embedding(label: str, emb: np.ndarray) -> None:
    np.save(_emb_path(label), emb.astype(np.float32))


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _decode_wav(data: bytes) -> tuple[np.ndarray | None, int]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            if wf.getsampwidth() != 2:
                return None, 0
            rate = wf.getframerate()
            nchan = wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
    except Exception:
        return None, 0
    samples = np.frombuffer(raw, dtype=np.int16)
    if nchan > 1:
        samples = samples.reshape(-1, nchan)[:, 0]
    return samples.copy(), int(rate)


def _decode_av(data: bytes) -> tuple[np.ndarray | None, int]:
    import av

    container = av.open(io.BytesIO(data), mode="r")
    stream = next((s for s in container.streams if s.type == "audio"), None)
    if stream is None:
        return None, 0
    chunks: list[np.ndarray] = []
    rate = 0
    for frame in container.decode(stream):
        arr = frame.to_ndarray()
        if arr.ndim == 2:
            # (channels, samples) or (samples, channels)
            if arr.shape[0] <= 8 and arr.shape[0] < arr.shape[1]:
                arr = arr[0]
            else:
                arr = arr[:, 0]
        if arr.dtype != np.int16:
            # float planar → int16
            flat = arr.astype(np.float32)
            if flat.max() <= 1.5:
                flat = flat * 32767.0
            arr = np.clip(flat, -32768, 32767).astype(np.int16)
        chunks.append(arr.reshape(-1))
        rate = int(frame.sample_rate or rate or TARGET_SR)
    if not chunks:
        return None, 0
    pcm = np.concatenate(chunks)
    return pcm, rate or TARGET_SR


def _resample_linear(pcm: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(pcm) < 2:
        return pcm
    duration = len(pcm) / float(src)
    n = max(2, int(duration * dst))
    x_old = np.linspace(0.0, 1.0, num=len(pcm), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, pcm.astype(np.float64)).astype(np.int16)


def _hz_to_mel(hz: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _mel_filterbank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    f_min, f_max = 20.0, sr / 2.0
    mels = np.linspace(_hz_to_mel(f_min), _hz_to_mel(f_max), n_mels + 2)
    hz = _mel_to_hz(mels)
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = bins[i], bins[i + 1], bins[i + 2]
        if center == left:
            center += 1
        if right == center:
            right += 1
        for j in range(left, center):
            if 0 <= j < fb.shape[1]:
                fb[i, j] = (j - left) / max(1, center - left)
        for j in range(center, right):
            if 0 <= j < fb.shape[1]:
                fb[i, j] = (right - j) / max(1, right - center)
    return fb


def _log_mel(x: np.ndarray, sr: int) -> np.ndarray:
    # Pre-emphasis
    y = np.append(x[0], x[1:] - 0.97 * x[:-1])
    # Framing
    win = np.hamming(N_FFT).astype(np.float32)
    if len(y) < N_FFT:
        y = np.pad(y, (0, N_FFT - len(y)))
    frames = []
    for start in range(0, len(y) - N_FFT + 1, HOP):
        frame = y[start : start + N_FFT] * win
        spec = np.abs(np.fft.rfft(frame)) ** 2
        frames.append(spec)
    if not frames:
        return np.zeros((0, N_MELS), dtype=np.float32)
    power = np.stack(frames, axis=0)
    fb = _mel_filterbank(sr, N_FFT, N_MELS)
    mel = power @ fb.T
    return np.log(np.maximum(mel, 1e-10)).astype(np.float32)


def _synth_tone_wav(freq: float, seconds: float = 2.0, sr: int = TARGET_SR, *, seed: int = 0) -> bytes:
    """Test helper: voiced-like buzz with formants (not a pure sine)."""
    rng = np.random.default_rng(seed if seed else int(freq))
    n = int(sr * seconds)
    t = np.arange(n) / sr
    # Glottal-ish pulse train at `freq` + colored noise.
    phase = (t * freq) % 1.0
    glottal = np.exp(-phase * 8.0) * np.sin(2 * math.pi * phase)
    noise = rng.normal(0.0, 0.08, size=n)
    wave_f = 0.7 * glottal + noise
    # Two simple resonant peaks (fake formants) via biquad-ish feedback.
    f1 = freq * 2.5
    f2 = freq * 5.0
    wave_f += 0.35 * np.sin(2 * math.pi * f1 * t) * np.exp(-t * 0.4)
    wave_f += 0.22 * np.sin(2 * math.pi * f2 * t) * np.exp(-t * 0.6)
    # Mild AM so stats aren't flat.
    wave_f *= 0.85 + 0.15 * np.sin(2 * math.pi * 3.0 * t)
    peak = float(np.max(np.abs(wave_f))) or 1.0
    pcm = (wave_f / peak * 14000.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
