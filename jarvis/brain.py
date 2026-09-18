"""Conversation loop with tool use and local-first reasoning."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import re
import time
from typing import Any
from zoneinfo import ZoneInfo

from jarvis.actions import Actions
from jarvis.bus import EventBus
from jarvis.config import Settings
from jarvis.llm import (
    LLMEndpoint,
    groq_model_candidates,
    is_missing_model_error,
    is_small_local_model,
    is_tools_unsupported,
    resolve_llm,
)
from jarvis.memory import Memory
from jarvis.personality import (
    build_system_prompt,
    guard_filial_reply,
    messages_with_lock,
    split_system_prompt,
)
from jarvis.security import redact_secrets, secret_values
from jarvis.tools import MEMBER_SAFE_PC, PHONE_BLOCKED_TOOLS, make_executor, schemas_for, tools_for_surface

MAX_HISTORY = 24
MAX_TOOL_ROUNDS = 4
ACTION_TOOL_ROUNDS = 2
# gpt-oss uses inner reasoning; keep headroom on the first/tool passes.
REASONING_MAX_TOKENS = 2500
ACTION_MAX_TOKENS = 900
SYNTHESIS_MAX_TOKENS = 900
REASONING_TEMPERATURE = 0.05
SMALL_MAX_TOKENS = 220
SMALL_TEMPERATURE = 0.35

_ACTION_HINT = (
    r"\b(abr[ií]|abrime|abrir|abre|open|lanz[aá]|ejecut[aá]|corré|corre|inici[aá]|run|"
    r"cerr[aá]|volumen|volume|silenci|"
    r"mute|unmute|captura|screenshot|poneme|pon[eé]|reproduc|paus[aá]|busc[aá]|google|anot[aá]|nota|"
    r"deshac|undo|timer|record[aá]|avis[aá]|whatsapp|mapa|ruta|traduc|llevame|ll[eé]vame|naveg|"
    r"intercomunicador|portero|timbre|doorbell|programa|aplicaci[oó]n|"
    r"portapapeles|clipboard|apag[aá]\s+la\s+pc|reinici[aá]\s+la\s+pc|bloque[aá]|"
    r"sub[ií].{0,12}volumen|baj[aá].{0,12}volumen|siguiente|anterior|escritorio|descargas)\b"
)
_MANAGE_HINT = (
    r"\b(gestion[aá]|organiz[aá]|armame|arm[aá]|planific[aá]|coordin[aá]|resolv[eé]|"
    r"haceme\s+(?:el\s+)?favor|encargate|segu[ií]\s+con|termin[aá]\s+(?:de\s+)?|"
    r"prepar[aá]|resum[ií]|orden[aá]|administr[aá]|manage|organize|handle)\b"
)
_FACT_HINT = (
    r"\b(qu[eé]\s+es|qui[eé]n\s+(?:es|fue|era)\b(?!\s+m[aá]s)|cu[aá]ndo|d[oó]nde|por\s+qu[eé]|"
    r"c[oó]mo\s+(?:se|funciona|hacer|hago|calculo|resuelvo)|precio|cotiz|noticia|últim|ultimo|"
    r"significa|definici[oó]n|explica|explicame|explicá|contame|decime|"
    r"cu[aá]nto\s+(?:es|vale|mide|pesa|dura)|diferencia\s+entre|"
    r"tell me|what is|who is|when was|how to|why\s+is|explain)\b"
    r"|\?"
)
_SCHOOL_HINT = (
    r"\b(tarea|deberes|examen|parcial|trabajo\s+pr[aá]ctico|tp\b|resumen|cuestionario|"
    r"estudi[oa]|materia|colegio|escuela|secundari|primari|universidad|facultad|"
    r"matem[aá]tica|historia|geograf[ií]a|biolog[ií]a|qu[ií]mica|f[ií]sica|literatura|"
    r"lengua|ingl[eé]s|filosof[ií]a|econom[ií]a|ecuaci[oó]n|fracci[oó]n|derivada|"
    r"integrales?|teorema|ensayo|monograf[ií]a|bibliograf[ií]a|ayuda\s+escolar|"
    r"homework|study|quiz|solve|ejercicio)\b"
)
# Subjective taste — answer locally; do NOT force web_search (triggers provider 403/noise).
_OPINION_HINT = (
    r"\b(m[aá]s\s+linda|m[aá]s\s+lindo|m[aá]s\s+hermosa|m[aá]s\s+hermoso|m[aá]s\s+guap[oa]|"
    r"m[aá]s\s+fea|m[aá]s\s+feo|qui[eé]n\s+es\s+m[aá]s|prefer[ií]s|te\s+gusta\s+m[aá]s|"
    r"m[aá]s\s+bonit[oa]|mejor\s+parecida|m[aá]s\s+atractiv|"
    r"qui[eé]n\s+es\s+mejor|qui[eé]n\s+mejor|mejor\s+entre|"
    r"\bo\b.{0,40}\bqui[eé]n\s+(?:es\s+)?mejor|"
    r"messi\s+o\s+cr7|cr7\s+o\s+messi|chaewon\s+o\s+kazuha)\b"
)


class Brain:
    def __init__(
        self,
        settings: Settings,
        memory: Memory | None = None,
        bus: EventBus | None = None,
        workspace: Path | None = None,
        profile_style: str = "",
        enabled_packs: list[str] | None = None,
        custom_tone: str = "equilibrado",
        city: str = "",
        allowed_tools: set[str] | None = None,
        is_owner: bool = False,
    ) -> None:
        self.settings = settings
        self.memory = memory or Memory()
        self.bus = bus or EventBus()
        self.profile_style = profile_style
        self.enabled_packs = list(enabled_packs or [])
        self.custom_tone = custom_tone
        self.city = city
        self.is_owner = is_owner
        self.allowed_tools = allowed_tools
        self.actions = Actions(settings, self.bus, workspace, is_owner=is_owner)
        self._endpoint: LLMEndpoint | None = None
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._chat_path = (self.memory.path.parent / "chat_history.json") if hasattr(self.memory, "path") else None
        self._load_persisted_history()
        raw_execute = make_executor(settings, self.memory, self.actions)

        def execute(name: str, arguments_json: str) -> str:
            if self.allowed_tools is not None and name not in self.allowed_tools:
                return "Permiso denegado: esa accion es solo del dueno."
            surface = (getattr(self.actions, "client_surface", "hud") or "hud").strip().lower()
            if surface in {"android", "ios", "iphone", "ipad"} and name in PHONE_BLOCKED_TOOLS:
                return (
                    "Eso es de la PC. Pedilo desde el HUD del escritorio, "
                    "o usá una acción del celular."
                )
            result = raw_execute(name, arguments_json)
            self._maybe_auto_journal(name, arguments_json, result)
            return redact_secrets(result, extra=secret_values(self.settings))

        self.execute = execute

    def _maybe_auto_journal(self, name: str, arguments_json: str, result: str) -> None:
        """Append a short line to diario_YYYY-MM-DD.txt after important PC tools."""
        journal_tools = {
            "web_search",
            "set_volume",
            "open_app",
            "daily_journal",
            "note",
            "set_reminder",
            "set_timer",
            "compose_whatsapp",
            "mix_tracks",
            "play_music",
            "kitchen_recipe",
            "music_action",
            "wellness_action",
            "screenshot",
            "power_control",
        }
        if name not in journal_tools or name == "daily_journal":
            return
        if not result or result.lower().startswith(("permiso", "eso es de la pc", "unknown")):
            return
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError:
            args = {}
        summary = {
            "web_search": f"Resumen: búsqueda «{str(args.get('query') or '')[:80]}»",
            "set_volume": f"Volumen → {args.get('level')}",
            "open_app": f"Abrió app «{args.get('name') or args.get('app') or ''}»",
            "note": f"Nota: {str(args.get('text') or '')[:100]}",
            "set_reminder": f"Recordatorio: {str(args.get('text') or '')[:80]}",
            "set_timer": f"Timer {args.get('minutes')} min",
            "compose_whatsapp": "Borrador WhatsApp abierto (sin envío silencioso)",
            "mix_tracks": f"Remix Hardtech → {args.get('output_file') or 'remix_generado.mp3'}",
            "play_music": f"Música: {str(args.get('query') or args.get('track') or '')[:80]}",
            "kitchen_recipe": f"Cocina: {str(args.get('dish') or args.get('comida') or '')[:80]}",
            "music_action": f"Música ({args.get('action')}): {str(args.get('track_name') or args.get('track_base') or '')[:60]}",
            "wellness_action": f"Bienestar ({args.get('action')}): {str(args.get('tipo_tema') or '')[:60]}",
            "screenshot": "Captura de pantalla",
            "power_control": f"Power: {args.get('action')}",
        }.get(name)
        if not summary:
            return
        try:
            self.actions.daily_journal(summary)
        except Exception:
            pass

    def _chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        # Keep Ollama model + KV prompt cache warm (default unload is ~5 min).
        if self.endpoint.label in {"ollama", "llamacpp"}:
            extra = dict(kwargs.pop("extra_body", None) or {})
            extra.setdefault("keep_alive", os.getenv("OLLAMA_KEEP_ALIVE", "60m"))
            kwargs["extra_body"] = extra
        if self.endpoint.label == "groq":
            last: BaseException | None = None
            for model in groq_model_candidates(self.settings):
                try:
                    self._endpoint = resolve_llm(self.settings, model=model)
                    return self.endpoint.client.chat.completions.create(
                        model=self.endpoint.model,
                        messages=messages,
                        **kwargs,
                    )
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    if not is_missing_model_error(exc):
                        raise
                    self._endpoint = None
            if last is not None:
                raise last
        return self.endpoint.client.chat.completions.create(
            model=self.endpoint.model,
            messages=messages,
            **kwargs,
        )

    def _finish(self, text: str) -> str:
        clean = redact_secrets(text or "", extra=secret_values(self.settings))
        return guard_filial_reply(
            clean,
            is_owner=self.is_owner,
            address_as=self.settings.user_name,
        )

    def _force_execute_command(self, text: str) -> str | None:
        """When the user ordered open/run/play, execute via Fast-Path/local — never leave a link."""
        from jarvis.fast_path import try_fast_path
        from jarvis.local import try_local_command

        surface = getattr(self.actions, "client_surface", "hud")
        allowed = self.allowed_tools
        hit = try_fast_path(text, self.execute, surface=surface, allowed=allowed)
        if hit:
            return hit
        hit = try_local_command(
            text,
            self.execute,
            self.memory,
            self.settings,
            allowed,
            surface=surface,
        )
        if hit:
            return hit
        # Last resort: extract song/app after youtube/brave/open verbs.
        lower = (text or "").lower()
        m = re.search(
            r"(?:youtube|yt|ytmusic)\s+(?:una\s+canci[oó]n\s+(?:de\s+)?|de\s+|a\s+)?(.+)$",
            lower,
        )
        if m and "open_app" in (allowed or {"open_app"}):
            query = m.group(1).strip(" .")
            if 1 < len(query) <= 100:
                return self.execute(
                    "app_search_action",
                    json.dumps(
                        {"browser": "brave", "platform": "youtube", "query": query},
                        ensure_ascii=False,
                    ),
                )
        m = re.search(
            r"(?:abr[ií]|abrime|abrir|ejecut[aá]|lanz[aá])\s+(?:la\s+|el\s+)?"
            r"(brave|chrome|edge|spotify|discord|notepad|calculadora|excel|word|steam|cursor|telegram|whatsapp)\b",
            lower,
        )
        if m:
            name = m.group(1)
            if allowed is None or "open_app" in allowed:
                return self.execute("open_app", json.dumps({"name": name}, ensure_ascii=False))
        return None

    def _alexa_confirm(self, results: list[tuple[str, str]]) -> str | None:
        """Short spoken confirm after an execute tool — Alexa-style, no URLs/essays."""
        alexa_tools = {
            "open_app",
            "app_search_action",
            "play_music",
            "open_browser",
            "google",
            "set_volume",
            "media",
            "screenshot",
            "open_maps",
            "compose_whatsapp",
            "intercom_action",
            "phone_hands",
            "control_device",
            "note",
            "daily_journal",
            "undo_last",
            "power_control",
            "timer",
            "queue_phone_fix",
        }
        for name, result in reversed(results):
            if name not in alexa_tools:
                continue
            clean = re.sub(r"https?://\S+", "", result or "").strip(" ·.-→>")
            clean = re.sub(r"\s*[→\-:]+\s*$", "", clean)
            clean = re.sub(r"\s{2,}", " ", clean).strip()
            if not clean:
                continue
            # Keep confirmations short (TTS-friendly).
            if len(clean) > 160:
                clean = clean[:157].rstrip() + "…"
            return clean
        return None

    @property
    def endpoint(self) -> LLMEndpoint:
        if self._endpoint is None:
            self._endpoint = resolve_llm(self.settings)
        return self._endpoint

    @property
    def pc_hands(self) -> bool:
        """Owner, or member with PC tools (members_pc_hands / MEMBER_SAFE_PC)."""
        if self.is_owner:
            return True
        allowed = self.allowed_tools
        if allowed is None:
            return True
        return "open_app" in allowed or "set_volume" in allowed

    @property
    def status(self) -> dict[str, str]:
        llm = "local"
        if self.settings.has_llm:
            try:
                llm = f"{self.endpoint.label}:{self.endpoint.model}"
            except RuntimeError:
                llm = "setup"
        return {
            "name": self.settings.assistant_name,
            "llm": llm,
            "net": "online",
            "hands": "full" if self.is_owner else ("pc" if self.pc_hands else "limited"),
            "mail": "on" if self.settings.has_smtp else "off",
            "ha": "on" if self.settings.has_ha else "off",
            "stt": "ready" if self.settings.has_stt else "text-only",
            "telegram": "ready" if self.settings.has_telegram else "off",
        }

    def due_alerts(self) -> list[str]:
        now = datetime.now(ZoneInfo(self.settings.timezone))
        return self.memory.due_reminders(now)

    def _local_answer(self, text: str) -> str:
        from jarvis.local import local_reply

        return local_reply(
            text,
            self.execute,
            self.memory,
            self.settings,
            self.allowed_tools,
            surface=getattr(self.actions, "client_surface", "hud"),
        )

    def _rescue_from_error(self, text: str, exc: BaseException) -> str:
        """Never dump raw provider errors — always try to answer the user."""
        prose = _failed_generation_text(exc)
        if prose and len(prose) > 12 and not prose.strip().startswith("{"):
            return prose
        # If the model tried a tool we can run, execute it.
        parsed = _failed_generation_tool(exc)
        if parsed:
            tool_name, args = parsed
            allowed = self.allowed_tools
            if allowed is None or tool_name in allowed:
                try:
                    return self.execute(tool_name, json.dumps(args, ensure_ascii=False))
                except Exception:  # noqa: BLE001
                    pass
        # Mechanical / wiki / search fallbacks without the LLM.
        try:
            local = self._local_answer(text)
            low = (local or "").lower()
            stub = low.startswith(
                (
                    "no capt",
                    "no entend",
                    "sistemas en",
                    "todavía no armé",
                    "todavia no arme",
                    "sin llm",
                    "modo local",
                    "sin key",
                )
            )
            if local and not stub:
                return local
        except Exception:  # noqa: BLE001
            pass
        # One shot web_search for question-like turns.
        if _looks_like_question(text) or re.search(_SCHOOL_HINT, text, re.I) or re.search(
            _FACT_HINT, text, re.I
        ):
            try:
                hit = self.execute(
                    "web_search",
                    json.dumps({"query": text[:180], "max_results": 5}, ensure_ascii=False),
                )
                if hit and "error" not in hit.lower()[:40] and not hit.startswith("No results"):
                    return (
                        "Busqué esto por vos:\n"
                        f"{hit[:1200]}\n"
                        "Si querés, pedime que te lo explique más simple o con un ejemplo."
                    )
            except Exception:  # noqa: BLE001
                pass
        # Wikipedia one-shot for short fact questions.
        topic = re.sub(
            r"^(qu[eé]\s+es|qui[eé]n\s+es|capital\s+de|defin[ií])\s+",
            "",
            (text or "").strip(),
            flags=re.I,
        ).strip(" ?¿")
        if 2 <= len(topic.split()) <= 6:
            try:
                wiki = self.execute(
                    "wikipedia",
                    json.dumps({"topic": topic[:80]}, ensure_ascii=False),
                )
                if wiki and "failed" not in wiki.lower()[:40] and len(wiki) > 40:
                    return wiki[:900]
            except Exception:  # noqa: BLE001
                pass
        return (
            "Se me trabó el enlace un segundo, pero seguimos. "
            "Reformulá la pregunta en una frase corta o pedime «buscá X» / «explicame X» "
            "y te ayudo (también con tareas y estudio)."
        )

    def _load_persisted_history(self) -> None:
        path = self._chat_path
        if path is None or not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(raw, dict):
            return
        for session_id, turns in raw.items():
            if not isinstance(turns, list):
                continue
            clean: list[dict[str, Any]] = []
            for item in turns[-MAX_HISTORY:]:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                content = item.get("content")
                if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                    clean.append({"role": role, "content": content.strip()[:4000]})
            if clean:
                self._history[str(session_id)] = clean

    def _persist_history(self, session_id: str) -> None:
        path = self._chat_path
        if path is None:
            return
        try:
            existing: dict[str, Any] = {}
            if path.is_file():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
            turns = [
                {"role": item["role"], "content": item["content"]}
                for item in self._history[session_id]
                if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
            ][-MAX_HISTORY:]
            existing[session_id] = turns
            path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, TypeError, ValueError):
            pass

    def continue_hint(self, session_id: str) -> str:
        history = self._history.get(session_id) or []
        for item in reversed(history):
            if item.get("role") == "user" and isinstance(item.get("content"), str):
                text = item["content"].strip()
                if text:
                    return text[:120]
        return ""

    def export_history(self, session_id: str, *, limit: int = 40) -> list[dict[str, str]]:
        """User/assistant turns for HUD chat drawer (no tool dumps)."""
        history = self._history.get(session_id) or []
        out: list[dict[str, str]] = []
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            text = content.strip()
            if not text:
                continue
            out.append({"role": str(role), "content": text[:4000]})
        if limit > 0:
            out = out[-limit:]
        return out

    def _store(self, session_id: str, answer: str) -> str:
        clean = redact_secrets(answer, extra=secret_values(self.settings))
        self._history[session_id].append({"role": "assistant", "content": clean})
        self._persist_history(session_id)
        return clean

    def _last_assistant(self, session_id: str) -> str:
        history = self._history[session_id]
        if history and history[-1].get("role") == "assistant":
            content = history[-1].get("content")
            if isinstance(content, str) and content.strip():
                return content
        return ""

    def _iter_tokens(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]:
        stream = self._chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = choices[0].delta
            piece = getattr(delta, "content", None) or ""
            if piece:
                yield redact_secrets(piece, extra=secret_values(self.settings))

    def reply(self, session_id: str, user_text: str, focus_pack: str = "") -> str:
        pieces: list[str] = []
        for part in self.iter_reply(session_id, user_text, focus_pack):
            pieces.append(part)
        stored = self._last_assistant(session_id)
        if stored:
            return stored
        return "".join(pieces) or "No capté nada. Repetilo, por favor."

    def iter_reply(self, session_id: str, user_text: str, focus_pack: str = "") -> Iterator[str]:
        """Yield reply chunks. History stores the post-filter final text, not LOCK."""
        text = redact_secrets(user_text.strip(), extra=secret_values(self.settings))
        if not text:
            yield "No capté nada. Repetilo, por favor."
            return

        history = self._history[session_id]
        history.append({"role": "user", "content": text})
        self._persist_history(session_id)

        from jarvis.fast_path import try_fast_path
        from jarvis.local import try_local_command

        surface = getattr(self.actions, "client_surface", "hud")
        fast = try_fast_path(
            text,
            self.execute,
            surface=surface,
            allowed=self.allowed_tools,
        )
        if fast:
            answer = self._finish(fast)
            self._store(session_id, answer)
            yield answer
            return

        commanded = try_local_command(
            text,
            self.execute,
            self.memory,
            self.settings,
            self.allowed_tools,
            surface=surface,
        )
        if commanded:
            answer = self._finish(commanded)
            self._store(session_id, answer)
            yield answer
            return

        if not self.settings.has_llm:
            # One fresh probe — a stale miss must not trap the session in "sin Groq".
            from jarvis.config import invalidate_ollama_ping

            invalidate_ollama_ping()
            if not self.settings.has_llm:
                # Last resort: still try resolve_llm (falls back to Ollama when keys empty).
                try:
                    _ = self.endpoint
                except RuntimeError:
                    answer = self._finish(self._local_answer(text))
                    self._store(session_id, answer)
                    yield answer
                    return

        small = is_small_local_model(self.settings, self.endpoint.model)
        actionish = bool(re.search(_ACTION_HINT, text, re.I))
        manageish = bool(re.search(_MANAGE_HINT, text, re.I))
        opinionish = bool(re.search(_OPINION_HINT, text, re.I))
        schoolish = bool(re.search(_SCHOOL_HINT, text, re.I))
        factish = (
            (not actionish)
            and (not opinionish)
            and (
                bool(re.search(_FACT_HINT, text, re.I))
                or schoolish
                or manageish
                or _looks_like_question(text)
            )
        )
        cap = 6 if actionish else (10 if small else MAX_HISTORY)
        history[:] = history[-cap:]

        system_static, system_live = split_system_prompt(
            self.settings,
            self.memory,
            self.actions,
            self.profile_style,
            self.is_owner,
            focus_pack="" if actionish else focus_pack,
            user_message=text,
            enabled_packs=self.enabled_packs,
            custom_tone=self.custom_tone,
            city=self.city,
            compact=small or actionish,
            lean=actionish and not small,
            client_surface=getattr(self.actions, "client_surface", "hud"),
            device_note=getattr(self.actions, "device_note", ""),
            pc_hands=self.pc_hands,
        )
        # Action turns: trim chat context hard for lower TTFT.
        hist_for_llm = _trim_history_for_llm(history, keep=4 if actionish else cap)
        # Static first (KV-cache prefix) → LIVE system → history. Never put the clock
        # inside the static blob or Ollama recomputes the whole prompt every minute.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_static},
        ]
        if system_live.strip():
            messages.append({"role": "system", "content": system_live})
        messages.extend(hist_for_llm)
        if small:
            messages = messages_with_lock(messages, is_owner=self.is_owner)
        if actionish:
            messages.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "ALEXA+GEMINI: execute EVERY concrete command with tools NOW "
                        "(open_app, app_search_action, play_music, set_volume, …). "
                        "If several asks in one turn, do them in order. "
                        "Do it yourself — NEVER paste a URL / YouTube link / 'abrí vos'. "
                        "After pure actions: short “Listo…”. "
                        "If you also researched/managed, close with a clear Gemini-style summary."
                        if manageish
                        else (
                            "ALEXA MODE: this turn is a concrete EXECUTE command. "
                            "Call the matching tool NOW (open_app, app_search_action, play_music, "
                            "set_volume, open_browser, phone_hands, …). "
                            "Do it yourself — NEVER paste a URL / YouTube link / 'abrí vos'. "
                            "After tools: one short Rioplatense confirmation only (Listo…). "
                            "Never claim success without a tool call in this turn."
                        )
                    ),
                },
            )
        elif factish:
            messages.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "GEMINI MANAGE: the user wants you to organize / handle / plan something. "
                        "Use tools as needed (search, notes, maps, apps). Resolve in order. "
                        "Answer clear and useful in Rioplatense; end with a short done-summary. "
                        "Ask at most ONE clarifying question if a critical detail is missing."
                        if manageish
                        else (
                            "RESEARCH / HELP: this is a question, homework, explanation, or public fact. "
                            "If you are not certain, call web_search or wikipedia NOW. "
                            "For school help: explain step-by-step in clear Rioplatense, give a short example, "
                            "then offer a practice question. Never invent citations. "
                            "Never say you don't know without searching first when the topic is public."
                            if schoolish
                            else (
                                "RESEARCH: public fact / news / how-to / general question. "
                                "If you are not certain from memory, call web_search NOW. "
                                "If results are thin, read_page the best URL or wikipedia. "
                                "Never say you don't know without searching first. "
                                "Answer short in Rioplatense; be useful, not theatrical."
                            )
                        )
                    ),
                },
            )
        elif opinionish:
            messages.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "OPINION: subjective taste (beauty, favorites, who is prettier). "
                        "Do NOT call web_search. Answer briefly, playfully, without ranking people "
                        "as objective truth. No tools needed."
                    ),
                },
            )
        tools = tools_for_surface(
            self.allowed_tools,
            getattr(self.actions, "client_surface", "hud"),
        )
        # Small locals often ignore tools; still try a tool loop so PC actions can fire.
        if small:
            max_tokens = SMALL_MAX_TOKENS
            temperature = SMALL_TEMPERATURE
            tool_rounds = ACTION_TOOL_ROUNDS
        elif actionish:
            max_tokens = ACTION_MAX_TOKENS
            temperature = REASONING_TEMPERATURE
            tool_rounds = MAX_TOOL_ROUNDS if manageish else ACTION_TOOL_ROUNDS
        elif factish:
            max_tokens = ACTION_MAX_TOKENS
            temperature = REASONING_TEMPERATURE
            tool_rounds = MAX_TOOL_ROUNDS if manageish else 2  # search → answer
        elif opinionish:
            # Opinions must not touch tools (avoids Groq tool_use_failed 400).
            max_tokens = SMALL_MAX_TOKENS
            temperature = 0.55
            tool_rounds = 1
            tools = []
        else:
            max_tokens = REASONING_MAX_TOKENS
            temperature = REASONING_TEMPERATURE
            tool_rounds = MAX_TOOL_ROUNDS
        choice_mode: str | dict[str, Any] = (
            "required" if (actionish or factish) and not small else "auto"
        )
        executed_actions: list[tuple[str, str]] = []

        try:
            for _ in range(tool_rounds):
                try:
                    chat_kwargs: dict[str, Any] = {
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if tools:
                        chat_kwargs["tools"] = tools
                        chat_kwargs["tool_choice"] = choice_mode
                    response = self._chat(messages, **chat_kwargs)
                except Exception as exc:  # noqa: BLE001
                    recovered = _recover_tool_provider_error(
                        self,
                        exc,
                        messages=messages,
                        tools=tools,
                        choice_mode=choice_mode,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    if recovered is not None:
                        response, tools, choice_mode, early = recovered
                        if early is not None:
                            answer = self._finish(early)
                            yield answer
                            self._store(session_id, answer)
                            return
                        if response is None:
                            continue
                    elif is_tools_unsupported(exc) or (not tools and "tool" in str(exc).lower()):
                        raw_parts = []
                        for piece in self._iter_tokens(
                            messages, temperature=temperature, max_tokens=max_tokens
                        ):
                            raw_parts.append(piece)
                            yield piece
                        answer = self._finish("".join(raw_parts))
                        if not answer:
                            answer = "Sistemas en línea, pero no armé una respuesta. Probá de nuevo."
                            yield answer
                        self._store(session_id, answer)
                        return
                    else:
                        raise
                choice = response.choices[0].message
                tool_calls = choice.tool_calls or []
                if not tool_calls and (actionish or factish) and choice_mode == "required":
                    # Provider accepted required but returned empty — nudge once then loosen.
                    choice_mode = "auto"
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "No llamaste ninguna tool. Ejecutá YA la acción pedida con la tool correcta."
                                if actionish
                                else (
                                    "No buscaste. Llamá web_search YA con la pregunta "
                                    "(o wikipedia/read_page si encaja). No digas que no sabés sin buscar."
                                )
                            ),
                        }
                    )
                    continue
                if tool_calls and _broken_tool_json(tool_calls):
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "La llamada a herramienta no era JSON válido. "
                                "Reintentá la tool con arguments como objeto JSON plano."
                            ),
                        }
                    )
                    continue
                if not tool_calls:
                    raw = choice.content or ""
                    # Fallback: model returned a ReAct JSON blob instead of tool_calls
                    from jarvis.brain_parser import try_parse_tool_blob

                    parsed = try_parse_tool_blob(raw)
                    if parsed:
                        tool_name, tool_params = parsed
                        fake_id = f"json-{time.time_ns()}"
                        result = self.execute(tool_name, json.dumps(tool_params, ensure_ascii=False))
                        executed_actions.append((tool_name, result))
                        assistant_msg = {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": fake_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(tool_params, ensure_ascii=False),
                                    },
                                }
                            ],
                        }
                        messages.append(assistant_msg)
                        history.append(assistant_msg)
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": fake_id,
                            "content": result[:12000],
                        }
                        messages.append(tool_msg)
                        history.append(tool_msg)
                        choice_mode = "auto"
                        continue
                    # Action turns: if the model only talked (or pasted a link), execute ourselves.
                    if actionish:
                        forced = self._force_execute_command(text)
                        if forced:
                            answer = self._finish(forced)
                            yield answer
                            self._store(session_id, answer)
                            return
                    answer = self._finish(raw)
                    if not answer:
                        answer = "Sistemas en línea, pero no armé una respuesta. Probá de nuevo."
                    # Still try to execute if the prose looks like a media/open dodge.
                    if actionish and re.search(
                        r"https?://|youtube\.com|youtu\.be|spotify\.com|abr[ií]\s+vos|abr[ií]\s+el\s+navegador",
                        answer,
                        re.I,
                    ):
                        forced = self._force_execute_command(text)
                        if forced:
                            answer = self._finish(forced)
                    yield answer
                    self._store(session_id, answer)
                    return

                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": choice.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments or "{}",
                            },
                        }
                        for call in tool_calls
                    ],
                }
                messages.append(assistant_msg)
                history.append(assistant_msg)

                for call, result in _execute_tools_parallel(self.execute, tool_calls):
                    executed_actions.append((call.function.name, result))
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result[:12000],
                    }
                    messages.append(tool_msg)
                    history.append(tool_msg)

            # Alexa-style: after pure execute tools, speak the confirm — no second LLM essay.
            # Gemini manage / research turns keep synthesis for a clear summary.
            research_tools = {
                "web_search",
                "wikipedia",
                "read_page",
                "image_search",
                "kitchen_recipe",
                "wellness_action",
                "analyze_workspace",
                "get_system_health",
                "check_lan_status",
            }
            if (
                actionish
                and executed_actions
                and not manageish
                and not any(name in research_tools for name, _ in executed_actions)
            ):
                confirm = self._alexa_confirm(executed_actions)
                if confirm:
                    answer = self._finish(confirm)
                    yield answer
                    self._store(session_id, answer)
                    return

            synth_tokens = SYNTHESIS_MAX_TOKENS if not small else max_tokens
            if actionish and not small:
                synth_tokens = min(synth_tokens, 400)
            raw_parts = []
            for piece in self._iter_tokens(
                messages,
                temperature=temperature,
                max_tokens=synth_tokens,
            ):
                raw_parts.append(piece)
                yield piece
            answer = self._finish("".join(raw_parts))
            if not answer:
                answer = "No pude cerrar la respuesta después de usar las herramientas."
                yield answer
            self._store(session_id, answer)
        except Exception as exc:  # noqa: BLE001
            from jarvis.passive_heal import on_llm_exception, owner_hint

            heal = on_llm_exception(self.settings, exc)
            hint = owner_hint(heal) if self.is_owner else ""
            # Soft cloud failure → one silent retry on local Ollama when available.
            if (
                self.endpoint.label != "ollama"
                and (
                    is_missing_model_error(exc)
                    or _is_soft_llm_failure(exc)
                    or _is_tool_provider_glitch(exc)
                )
            ):
                try:
                    from jarvis.config import _ollama_reachable
                    from jarvis.llm import _ollama_endpoint

                    if _ollama_reachable(self.settings.ollama_base_url):
                        self._endpoint = _ollama_endpoint(self.settings)
                        # Fall through to a single local synthesis without tools.
                        response = self._chat(
                            [
                                {
                                    "role": "system",
                                    "content": (
                                        "Sos Ilaria. Respondé en el idioma del usuario, "
                                        "corto y útil. Sin tools."
                                    ),
                                },
                                {"role": "user", "content": text},
                            ],
                            temperature=0.3,
                            max_tokens=400,
                        )
                        raw = (response.choices[0].message.content or "").strip()
                        if raw:
                            answer = self._finish(raw)
                            self._store(session_id, answer)
                            yield answer
                            return
                except Exception:  # noqa: BLE001
                    pass
            if is_missing_model_error(exc) or _is_soft_llm_failure(exc) or _is_tool_provider_glitch(exc):
                if _is_moderation_block(exc) and not _is_tool_provider_glitch(exc):
                    answer = self._finish(
                        "Eso es gusto personal: no hay una verdad objetiva ahí. "
                        "Decime con qué criterio lo ves vos y lo charlamos en joda, sin pelear."
                    )
                else:
                    answer = self._finish(self._rescue_from_error(text, exc))
                if hint:
                    answer = f"{answer}\n{hint}"
                self._store(session_id, answer)
                yield answer
                return
            # Last resort: still answer — never dump raw provider anomalies to the user.
            answer = self._finish(self._rescue_from_error(text, exc))
            if self.is_owner and hint:
                answer = f"{answer}\n{hint}"
            self._store(session_id, answer)
            yield answer


def _looks_like_question(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if "?" in raw:
        return True
    lower = raw.lower()
    starters = (
        "qué ", "que ", "quién ", "quien ", "cómo ", "como ", "cuándo ", "cuando ",
        "dónde ", "donde ", "por qué", "porque ", "cuánto ", "cuanto ",
        "explic", "contame", "decime", "ayud", "resolv", "calcul",
        "what ", "why ", "how ", "who ", "when ", "where ", "explain",
    )
    return any(lower.startswith(s) for s in starters) or len(raw.split()) >= 6


def _trim_history_for_llm(history: list[dict[str, Any]], keep: int) -> list[dict[str, Any]]:
    """Keep recent turns; drop heavy tool dumps for faster prompts."""
    if keep <= 0 or len(history) <= keep:
        return list(history)
    trimmed = history[-keep:]
    # Avoid starting mid tool-result block.
    while trimmed and trimmed[0].get("role") == "tool":
        trimmed = trimmed[1:]
    return trimmed


def _execute_tools_parallel(
    execute: Any,
    tool_calls: list[Any],
) -> list[tuple[Any, str]]:
    if len(tool_calls) <= 1:
        return [
            (call, execute(call.function.name, call.function.arguments or "{}"))
            for call in tool_calls
        ]
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as pool:
        futures = {
            pool.submit(
                execute,
                call.function.name,
                call.function.arguments or "{}",
            ): call
            for call in tool_calls
        }
        for fut in as_completed(futures):
            call = futures[fut]
            try:
                results[call.id] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[call.id] = f"Tool error: {exc}"
    return [(call, results.get(call.id, "")) for call in tool_calls]


def _broken_tool_json(tool_calls: list[Any]) -> bool:
    for call in tool_calls:
        raw = getattr(getattr(call, "function", None), "arguments", None) or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return True
        if not isinstance(parsed, dict):
            return True
    return False


def _is_soft_llm_failure(exc: BaseException) -> bool:
    text = str(exc).lower()
    needles = (
        "rate limit",
        "429",
        "503",
        "502",
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "overloaded",
        "403",
        "moderation",
        "content_filter",
        "content policy",
        "content_policy",
        "refused",
        "unsafe",
    )
    return any(item in text for item in needles)


def _is_moderation_block(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        item in text
        for item in (
            "403",
            "moderation",
            "content_filter",
            "content policy",
            "content_policy",
            "refused",
            "unsafe",
            "violat",
        )
    )


def _is_tool_provider_glitch(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        item in text
        for item in (
            "tool_use_failed",
            "tool call validation failed",
            "tool choice is required",
            "did not call a tool",
            "not in request.tools",
            "failed_generation",
        )
    )


def _failed_generation_text(exc: BaseException) -> str:
    """Pull prose from Groq/OpenAI tool_use_failed payloads (not tool JSON)."""
    blob = _raw_failed_generation(exc)
    if not blob:
        return ""
    if blob.startswith("{") and '"name"' in blob:
        return ""
    return blob.strip()[:2000]


def _raw_failed_generation(exc: BaseException) -> str:
    raw = str(exc)
    # Prefer the trailing failed_generation payload Groq embeds in the message.
    for pattern in (
        r"failed_generation['\"]?\s*[:=]\s*'((?:\\'|[^'])*)'",
        r'failed_generation[\'"]?\s*[:=]\s*"((?:\\"|[^"])*)"',
        r"failed_generation['\"]?\s*[:=]\s*(['\"])(.+?)\1",
    ):
        match = re.search(pattern, raw, re.S)
        if not match:
            continue
        blob = match.group(match.lastindex or 1)
        blob = (
            blob.replace("\\n", "\n")
            .replace("\\'", "'")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
            .strip()
        )
        if blob:
            return blob
    return ""


def _failed_generation_tool(exc: BaseException) -> tuple[str, dict[str, Any]] | None:
    raw = str(exc)
    name_hit = re.search(r"call tool ['\"]([a-zA-Z0-9_]+)['\"]", raw)
    tool_name = name_hit.group(1) if name_hit else ""
    gen = _raw_failed_generation(exc)
    if gen.startswith("{"):
        try:
            payload = json.loads(gen)
            if isinstance(payload, dict) and payload.get("name"):
                tool_name = str(payload.get("name") or tool_name)
                args_raw = payload.get("arguments", {})
                if isinstance(args_raw, str):
                    try:
                        args = json.loads(args_raw) if args_raw.strip() else {}
                    except json.JSONDecodeError:
                        # Sometimes arguments arrive already partially decoded.
                        args = {}
                        num = re.search(r"(?:value|level|percent)\D+(\d{1,3})", args_raw)
                        if num:
                            args["level"] = int(num.group(1))
                elif isinstance(args_raw, dict):
                    args = args_raw
                else:
                    args = {}
                return tool_name, args if isinstance(args, dict) else {}
        except json.JSONDecodeError:
            num = re.search(r"(?:value|level|percent)\D+(\d{1,3})", gen)
            if tool_name and num:
                return tool_name, {"level": int(num.group(1))}
    if tool_name:
        # Last resort: pull a volume-like number from the whole exception text.
        num = re.search(r"(?:value|level|percent)[\"'\s:=]+(\d{1,3})", raw)
        args: dict[str, Any] = {"level": int(num.group(1))} if num else {}
        return tool_name, args
    return None


def _recover_tool_provider_error(
    brain: Any,
    exc: BaseException,
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    choice_mode: str | dict[str, Any],
    temperature: float,
    max_tokens: int,
) -> tuple[Any, list[dict[str, Any]], str | dict[str, Any], str | None] | None:
    """Return (response, tools, choice_mode, early_answer) or None if not recoverable."""
    if not _is_tool_provider_glitch(exc):
        # Legacy: some providers reject tool_choice=required with that exact token.
        if choice_mode != "auto" and "tool_choice" in str(exc).lower() and tools:
            response = brain._chat(
                messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response, tools, "auto", None
        return None

    prose = _failed_generation_text(exc)
    if prose:
        return None, tools, "auto", prose

    parsed = _failed_generation_tool(exc)
    if parsed:
        tool_name, args = parsed
        allowed = brain.allowed_tools
        can_run = allowed is None or tool_name in allowed
        if can_run:
            result = brain.execute(tool_name, json.dumps(args, ensure_ascii=False))
            fake_id = f"recover-{time.time_ns()}"
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": fake_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(args, ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": fake_id,
                    "content": result[:12000],
                }
            )
            # Ensure the schema is present for the follow-up synthesis call.
            present = {_tool_schema_name(item) for item in tools}
            if tool_name not in present:
                tools = list(tools) + schemas_for({tool_name})
            try:
                response = brain._chat(
                    messages,
                    tools=tools or None,
                    tool_choice="auto" if tools else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except TypeError:
                kwargs: dict[str, Any] = {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                response = brain._chat(messages, **kwargs)
            return response, tools, "auto", None
        # Not allowed — expand tools if schema exists and member should have it after policy.
        present = {_tool_schema_name(item) for item in tools}
        if tool_name not in present:
            extra = schemas_for({tool_name})
            if extra and (allowed is None or tool_name in allowed or tool_name in MEMBER_SAFE_PC):
                tools = list(tools) + extra
                try:
                    response = brain._chat(
                        messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return response, tools, "auto", None
                except Exception:  # noqa: BLE001
                    pass
        return None, tools, "auto", (
            f"No tengo permiso para «{tool_name}» con esta cuenta. "
            "Pedile al dueño manos de PC en /admin, o usá una orden permitida."
        )

    if tools and choice_mode != "auto":
        try:
            response = brain._chat(
                messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response, tools, "auto", None
        except Exception:  # noqa: BLE001
            return None, tools, "auto", (
                "No pude completar esa acción en este turno. Probá de nuevo más corto."
            )
    return None, tools, "auto", (
        "No pude completar esa acción en este turno. Probá de nuevo más corto."
    )


def _tool_schema_name(schema: dict[str, Any]) -> str:
    try:
        return str(schema["function"]["name"])
    except (KeyError, TypeError):
        return ""
