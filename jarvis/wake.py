"""Always-on wake-word listener (Picovoice Porcupine + PvRecorder)."""

from __future__ import annotations

import asyncio
import io
import os
import re
import struct
import threading
import time
import wave
from pathlib import Path

from jarvis.config import DATA_DIR, ROOT
from jarvis.state import AppState
from jarvis.stt import contains_speech, record_command_wav, transcribe_audio
from jarvis.tts import audio_api_path, speak_to_file
from jarvis.wake_control import hud_listening

_WAKE_LOCK = threading.Lock()
_STARTED = False

_HUD_LIBRE_HINT = (
    "Fallback: botón Libre del HUD — decí «Ilaria» por el micrófono "
    "(el HUD filtra VAD del lado cliente). Guía: data/wake/README.txt"
)


def wake_enabled() -> bool:
    raw = os.getenv("WAKE_ENABLED", "1").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(_access_key())


_WAKE_WORD = re.compile(
    r"\b(?:hey\s+|ok\s+|oye\s+)?(ilaria|hilaria|ilaría)\b",
    re.IGNORECASE,
)


def command_after_wake(text: str) -> str | None:
    """Text after «Ilaria», empty string if only the name, None if she was not called."""
    match = _WAKE_WORD.search(text or "")
    if match is None:
        return None
    return (text[match.end() :] or "").strip(" ,.!?…;:")


def start_wake_listener(state: AppState) -> None:
    """Spawn a daemon thread. Local mic first; Picovoice only when a key exists."""
    global _STARTED
    if _STARTED:
        return
    if _access_key():
        _start_picovoice(state)
        return
    if os.getenv("WAKE_LOCAL", "1").strip().lower() in {"0", "false", "no", "off"}:
        return
    _STARTED = True
    thread = threading.Thread(
        target=_local_listen,
        args=(state,),
        name="ilaria-wake-local",
        daemon=True,
    )
    thread.start()
    print("[+] Wake local: escuchando «Ilaria» en esta PC.")


def _start_picovoice(state: AppState) -> None:
    global _STARTED
    try:
        import pvporcupine  # noqa: F401
        from pvrecorder import PvRecorder  # noqa: F401
    except ImportError:
        return
    _STARTED = True
    thread = threading.Thread(
        target=_listen_loop,
        args=(state,),
        name="ilaria-wake",
        daemon=True,
    )
    thread.start()
    print("[+] Wake word: escuchando en segundo plano.")


def _access_key() -> str:
    return (
        os.getenv("PICOVOICE_ACCESS_KEY", "").strip()
        or os.getenv("PICOVOICE_API_KEY", "").strip()
    )


def _keyword_paths() -> list[str]:
    """Custom .ppn files (e.g. Ilaria from Picovoice Console)."""
    raw = os.getenv("WAKE_PPN_PATH", "").strip()
    paths: list[str] = []
    if raw:
        for part in raw.split(";"):
            p = Path(part.strip())
            if not p.is_absolute():
                p = ROOT / p
            if p.is_file():
                paths.append(str(p))
            else:
                print(f"[-] Wake .ppn no encontrado: {p}")
    for default in (
        DATA_DIR / "wake" / "ilaria_windows.ppn",
        DATA_DIR / "models" / "ilaria_windows.ppn",
    ):
        resolved = str(default)
        if default.is_file() and resolved not in paths:
            paths.append(resolved)
    return paths


def _builtin_keywords() -> list[str]:
    """Last resort only when a Picovoice key exists but no custom .ppn."""
    raw = os.getenv("WAKE_KEYWORDS", "computer,jarvis").strip()
    allowed = {
        "alexa",
        "americano",
        "blueberry",
        "bumblebee",
        "computer",
        "grapefruit",
        "grasshopper",
        "hey google",
        "hey siri",
        "jarvis",
        "ok google",
        "picovoice",
        "porcupine",
        "terminator",
    }
    out: list[str] = []
    for item in raw.split(","):
        key = item.strip().lower()
        if key in allowed and key not in out:
            out.append(key)
    return out or ["computer"]


def _create_porcupine():
    import pvporcupine

    key = _access_key()
    paths = _keyword_paths()
    sensitivity = float(os.getenv("WAKE_SENSITIVITY", "0.55").strip() or "0.55")
    try:
        from jarvis.voice_prefs import load_voice_prefs

        sensitivity = float(load_voice_prefs().get("wake_sensitivity") or sensitivity)
    except Exception:
        pass
    sensitivity = max(0.1, min(1.0, sensitivity))
    if paths:
        print(f"[+] Wake: usando .ppn custom ({paths[0]}) sens={sensitivity}")
        return pvporcupine.create(
            access_key=key,
            keyword_paths=paths,
            sensitivities=[sensitivity] * len(paths),
        )
    keywords = _builtin_keywords()
    print(
        "[+] Wake: sin data/wake/ilaria_windows.ppn ni data/models/ilaria_windows.ppn — "
        f"last resort built-in {keywords}. Para «Ilaria» entrená el .ppn "
        f"(data/wake/README.txt). {_HUD_LIBRE_HINT}"
    )
    return pvporcupine.create(
        access_key=key,
        keywords=keywords,
        sensitivities=[sensitivity] * len(keywords),
    )


def _listen_loop(state: AppState) -> None:
    from pvrecorder import PvRecorder

    porcupine = None
    recorder = None
    try:
        porcupine = _create_porcupine()
        device = int(os.getenv("WAKE_MIC_INDEX", "-1").strip() or "-1")
        try:
            from jarvis.voice_prefs import load_voice_prefs

            device = int(load_voice_prefs().get("wake_mic_index", device))
        except Exception:
            pass
        recorder = PvRecorder(device_index=device, frame_length=porcupine.frame_length)
        recorder.start()
        print(
            f"[+] Mic wake listo @ {porcupine.sample_rate} Hz "
            f"(device={recorder.selected_device} index={device}). Esperando keyword…"
        )
        while True:
            if hud_listening():
                time.sleep(0.15)
                continue
            pcm = recorder.read()
            index = porcupine.process(pcm)
            if index < 0:
                continue
            if not _WAKE_LOCK.acquire(blocking=False):
                continue
            try:
                print("[!] Wake word detectada — grabando comando…")
                # Reuse the same PvRecorder (no reopen) so Windows keeps the mic.
                _handle_wake(
                    state,
                    porcupine.sample_rate,
                    porcupine.frame_length,
                    recorder=recorder,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[-] Wake handler error: {exc}")
            finally:
                try:
                    if not recorder.is_recording:
                        recorder.start()
                except Exception:
                    pass
                _WAKE_LOCK.release()
    except Exception as exc:  # noqa: BLE001
        print(f"[-] Wake word runtime error: {exc}")
        print(f"    {_HUD_LIBRE_HINT}")
    finally:
        try:
            if recorder is not None:
                if recorder.is_recording:
                    recorder.stop()
                recorder.delete()
        except Exception:
            pass
        try:
            if porcupine is not None:
                porcupine.delete()
        except Exception:
            pass


def _pcm_wav(samples: list[int], rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def _local_listen(state: AppState) -> None:
    """Energy gate + the Whisper already on disk. No Picovoice, no new download."""
    try:
        import sounddevice as sd
    except ImportError:
        print("[+] Wake: usá el botón Libre del HUD.")
        return
    from jarvis.vad import _rms

    rate = 16000
    frame = 1600
    silence_need = 7
    speech: list[int] = []
    quiet = 0
    try:
        stream = sd.RawInputStream(
            samplerate=rate,
            channels=1,
            dtype="int16",
            blocksize=frame,
        )
        stream.start()
    except Exception as exc:  # noqa: BLE001
        print(f"[+] Wake local no abrió el micrófono ({exc}). Botón Libre del HUD.")
        return
    try:
        while True:
            if hud_listening():
                speech.clear()
                quiet = 0
                time.sleep(0.2)
                continue
            block, _overflow = stream.read(frame)
            samples = list(struct.unpack(f"<{len(block) // 2}h", bytes(block)))
            if _rms(samples) >= 450:
                speech.extend(samples)
                quiet = 0
                if len(speech) > rate * 4:
                    _flush_local(state, stream, speech, rate)
                    speech = []
                    quiet = 0
                continue
            if not speech:
                continue
            quiet += 1
            speech.extend(samples)
            if quiet >= silence_need and len(speech) >= int(rate * 0.45):
                _flush_local(state, stream, speech, rate)
                speech = []
                quiet = 0
    except Exception as exc:  # noqa: BLE001
        print(f"[-] Wake local: {exc}")
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass


def _flush_local(state: AppState, stream: object, speech: list[int], rate: int) -> None:
    wav = _pcm_wav(speech, rate)
    if not contains_speech(wav, "wake.wav"):
        return
    if not _WAKE_LOCK.acquire(blocking=False):
        return
    start = None
    try:
        stop = getattr(stream, "stop", None)
        start = getattr(stream, "start", None)
        if stop is not None:
            stop()
        try:
            owner = state.accounts.owner()
            if owner is None:
                return
            settings = state.brain_for(owner).settings
            heard = transcribe_audio(settings, wav, "wake.wav")
        except Exception as exc:  # noqa: BLE001
            print(f"[-] Wake local STT: {exc}")
            return
        rest = command_after_wake(heard)
        if rest is None:
            return
        print(f"[!] Wake local: {heard}")
        if rest:
            _handle_wake(state, rate, 512, preset_text=rest, preset_wav=wav)
        else:
            _handle_wake(state, rate, 512)
    finally:
        if start is not None:
            try:
                start()
            except Exception:
                pass
        _WAKE_LOCK.release()


def _handle_wake(
    state: AppState,
    sample_rate: int,
    frame_length: int,
    *,
    recorder: object | None = None,
    preset_text: str | None = None,
    preset_wav: bytes | None = None,
) -> None:
    owner = state.accounts.owner()
    if owner is None:
        print("[-] Wake: no hay owner registrado.")
        return
    seconds = float(os.getenv("WAKE_LISTEN_SECONDS", "8").strip() or "8")
    seconds = max(3.0, min(12.0, seconds))
    brain = state.brain_for(owner)
    settings = brain.settings
    if not settings.has_stt:
        print("[-] Wake: falta Faster-Whisper local o GROQ/OPENAI para STT.")
        return
    brain.bus.push("Te escucho…", audio_url=None)
    if preset_wav is not None:
        wav = preset_wav
    else:
        try:
            wav = record_command_wav(
                sample_rate=sample_rate,
                frame_length=frame_length,
                max_seconds=seconds,
                recorder=recorder,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[-] Wake STT record error: {exc}")
            wav = b""
    if len(wav) < 800 or not contains_speech(wav):
        print("[-] Wake: VAD descartó el clip (sin voz) antes de Whisper.")
        reply = "No te escuché bien. Decilo otra vez después de llamarme."
        _announce(brain, reply)
        return

    # Speaker ID: switch brain to the enrolled voice when possible.
    speaker_user = owner
    speaker_name = owner.display_name
    try:
        from jarvis.speaker_id import identify_speaker, speakable_identify

        hit = identify_speaker(wav, filename="wake.wav")
        if hit is not None:
            print(f"[+] Wake speaker: {hit.label} score={hit.score:.3f}")
            if hit.username:
                matched = state.accounts.get_by_username(hit.username)
                if matched is not None and not matched.disabled:
                    speaker_user = matched
            speaker_name = hit.display_name
            brain = state.brain_for(speaker_user)
            settings = brain.settings
            brain.bus.push(speakable_identify(hit), audio_url=None)
    except Exception as exc:  # noqa: BLE001
        print(f"[-] Wake speaker-id: {exc}")

    try:
        if preset_text is not None:
            text = preset_text
        else:
            text = transcribe_audio(settings, wav, "wake.wav")
    except Exception as exc:  # noqa: BLE001
        print(f"[-] Wake STT error: {exc}")
        text = ""
    if not text.strip():
        reply = "No te escuché bien. Decilo otra vez después de llamarme."
        _announce(brain, reply)
        return
    print(f"[+] Wake STT ({speaker_name}): {text}")
    brain.bus.push(f"({speaker_name}) {text}", audio_url=None)
    answer = brain.reply(f"wake-{speaker_user.id}", text)
    _announce(brain, answer)


def _announce(brain, text: str) -> None:
    audio_url = None
    path = None
    try:
        path = asyncio.run(
            speak_to_file(brain.settings, text, f"tts-wake-{time.time_ns()}.mp3")
        )
        audio_url = audio_api_path(path.name)
    except Exception as exc:  # noqa: BLE001
        print(f"[-] Wake TTS: {exc}")
    brain.bus.push(text, audio_url=audio_url)
    # Never os.startfile here: Windows Media Player / default app steals focus and pauses Spotify.
