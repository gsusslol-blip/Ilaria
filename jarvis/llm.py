"""LLM provider selection (OpenAI-compatible: Ollama first, then cloud)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from openai import OpenAI

from jarvis.config import Settings, _ollama_reachable

# Fail the socket quickly so a dead cloud falls through to the local model.
_CLOUD_TIMEOUT = httpx.Timeout(45.0, connect=4.0)

GROQ_MODELS = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
)

_SMALL_MARKERS = (
    ":2b",
    ":3b",
    ":1b",
    ":4b",
    "1.5b",
    "gemma2:2b",
    "phi3",
    "tinyllama",
    "qwen2:1.5b",
    "qwen2.5-1.5",
    "qwen3",
    "1.7b",
)


@dataclass(frozen=True)
class LLMEndpoint:
    label: str
    client: OpenAI
    model: str


def groq_model_candidates(settings: Settings) -> list[str]:
    preferred = settings.llm_model.strip()
    models = list(GROQ_MODELS)
    if preferred and preferred not in {"gemma2:2b", "llama3", "llama3:8b"}:
        return [preferred] + [item for item in models if item != preferred]
    return models


def is_missing_model_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "model_not_found" in text
        or "does not exist" in text
        or "not have access" in text
        or "not found" in text
    )


def is_tools_unsupported(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "tool" in text and any(
        needle in text for needle in ("not support", "unsupported", "does not support", "no tools")
    )


def is_small_local_model(settings: Settings, model: str | None = None) -> bool:
    name = (model or settings.ollama_model or settings.llm_model or "").strip().lower()
    # Groq ids like openai/gpt-oss-20b are not the offline 1.5B installer.
    if looks_like_cloud_model(name):
        return False
    if any(marker in name for marker in _SMALL_MARKERS) or name in {"llama3", "gemma2"}:
        return True
    if settings.llm_provider in {"ollama", "llamacpp"} and name.endswith(".gguf"):
        return True
    if "gemma2:2b" in name or name.endswith(":2b"):
        return True
    return False


def _ollama_model_name(settings: Settings, model: str | None) -> str:
    if model:
        return model
    if settings.llm_provider in {"ollama", "llamacpp"} and settings.llm_model.strip():
        return settings.llm_model.strip()
    return (settings.ollama_model or "gemma2:2b").strip() or "gemma2:2b"


def _ollama_endpoint(settings: Settings, model: str | None = None) -> LLMEndpoint:
    base = (settings.ollama_base_url or "http://127.0.0.1:11434/v1").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return LLMEndpoint(
        label="ollama",
        client=OpenAI(api_key="ollama", base_url=base, timeout=120.0),
        model=_ollama_model_name(settings, model),
    )


def looks_like_cloud_model(name: str) -> bool:
    """True when LLM_MODEL points at Groq/OpenAI/Gemini ids, not local Ollama tags."""
    n = (name or "").strip().lower()
    if not n:
        return False
    if "/" in n:
        return True
    if n.startswith(("gpt-", "o1", "o3", "o4", "gemini-", "claude-")):
        return True
    if n.startswith("llama-3") or n.startswith("llama3."):
        return True
    return False


def resolve_llm(settings: Settings, model: str | None = None) -> LLMEndpoint:
    provider = (settings.llm_provider or "auto").strip().lower() or "auto"
    ollama_up = _ollama_reachable(settings.ollama_base_url)

    if provider == "auto":
        preferred = (settings.llm_model or "").strip()
        # Precision: prefer Groq/cloud whenever a key exists, unless the user pinned a
        # local Ollama tag in LLM_MODEL (e.g. gemma2:2b / llama3.1:8b).
        pinned_local = bool(preferred) and not looks_like_cloud_model(preferred)
        if pinned_local and ollama_up:
            provider = "ollama"
        elif preferred and looks_like_cloud_model(preferred) and settings.groq_api_key:
            provider = "groq"
        elif preferred and looks_like_cloud_model(preferred) and settings.openai_api_key:
            provider = "openai"
        elif preferred and looks_like_cloud_model(preferred) and settings.gemini_api_key:
            provider = "gemini"
        elif settings.groq_api_key:
            provider = "groq"
        elif settings.openai_api_key:
            provider = "openai"
        elif settings.gemini_api_key:
            provider = "gemini"
        elif ollama_up:
            provider = "ollama"
        else:
            raise RuntimeError(
                "No hay cerebro. Levantá Ollama (gemma2:2b) o pegá GROQ_API_KEY en .env."
            )
    elif provider == "groq" and not settings.groq_api_key:
        provider = "ollama" if ollama_up else provider
    elif provider == "openai" and not settings.openai_api_key:
        provider = "ollama" if ollama_up else provider
    elif provider == "gemini" and not settings.gemini_api_key:
        provider = "ollama" if ollama_up else provider

    if provider in {"ollama", "llamacpp"}:
        if not ollama_up and provider == "ollama":
            # Last chance: still return endpoint — caller may get connection errors.
            pass
        return _ollama_endpoint(settings, model)
    if provider == "groq":
        if not settings.groq_api_key:
            if ollama_up:
                return _ollama_endpoint(settings, model)
            raise RuntimeError("GROQ_API_KEY is empty.")
        return LLMEndpoint(
            label="groq",
            client=OpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=_CLOUD_TIMEOUT,
                max_retries=0,
            ),
            model=model or groq_model_candidates(settings)[0],
        )
    if provider == "openai":
        if not settings.openai_api_key:
            if ollama_up:
                return _ollama_endpoint(settings, model)
            raise RuntimeError("OPENAI_API_KEY is empty.")
        return LLMEndpoint(
            label="openai",
            client=OpenAI(api_key=settings.openai_api_key, timeout=_CLOUD_TIMEOUT, max_retries=0),
            model=model or settings.llm_model or "gpt-4o-mini",
        )
    if provider == "gemini":
        if not settings.gemini_api_key:
            if ollama_up:
                return _ollama_endpoint(settings, model)
            raise RuntimeError("GEMINI_API_KEY is empty.")
        return LLMEndpoint(
            label="gemini",
            client=OpenAI(
                api_key=settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=_CLOUD_TIMEOUT,
                max_retries=0,
            ),
            model=model or settings.llm_model or "gemini-2.0-flash",
        )
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")
