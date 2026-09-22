"""Code / debug assist — open editor + short speakable framing (not a full TTS essay)."""

from __future__ import annotations

import re
from typing import Any, Callable

CODE_HINT = re.compile(
    r"\b("
    r"traceback|exception|syntaxerror|typeerror|nameerror|importerror|"
    r"nullpointer|segmentation\s+fault|stack\s+trace|"
    r"debug(?:uear|ear)?|arreglar\s+(?:el\s+)?(?:bug|error|c[oó]digo)|"
    r"c[oó]digo\s+(?:en|de|python|js|ts|rust|go)|"
    r"refactor(?:iz)?|compile\s+error|error\s+de\s+compilaci[oó]n|"
    r"no\s+compila|falla\s+(?:el\s+)?(?:test|build|pipeline)|"
    r"abr[ií]\s+(?:cursor|vs\s*code|vscode)|"
    r"explicame\s+(?:este\s+)?(?:error|traceback|stack)|"
    r"qu[eé]\s+significa\s+(?:este\s+)?(?:error|traceback)"
    r")\b",
    re.I,
)

_EDITOR_HINT = re.compile(r"\b(cursor|vs\s*code|vscode|visual\s+studio\s+code)\b", re.I)


def looks_like_code_help(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if CODE_HINT.search(raw):
        return True
    # Triple-backtick or long paste with "Error" / "File \"" patterns.
    if "```" in raw and len(raw) > 40:
        return True
    if len(raw) > 120 and re.search(r"(File \".+\", line \d+|at .+\(.+:\d+:\d+\))", raw):
        return True
    return False


def digest_error(text: str, *, max_lines: int = 4) -> str:
    """Pull a short spoken digest from a traceback / error paste."""
    raw = (text or "").strip()
    if not raw:
        return ""
    # Prefer fenced code body.
    fence = re.search(r"```(?:\w+)?\s*([\s\S]+?)```", raw)
    body = fence.group(1).strip() if fence else raw
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    # Keep last error-ish lines (traceback climax is usually at the end).
    interesting = [
        ln
        for ln in lines
        if re.search(
            r"error|exception|traceback|failed|fatal|warning|line \d+",
            ln,
            re.I,
        )
    ]
    pick = interesting[-max_lines:] if interesting else lines[:max_lines]
    spoken = " | ".join(re.sub(r"\s+", " ", ln)[:120] for ln in pick)
    return spoken[:320]


def preferred_editor(text: str) -> str:
    low = (text or "").lower()
    if re.search(r"\bvs\s*code\b|\bvscode\b|visual\s+studio", low):
        return "vscode"
    return "cursor"


def speakable_code_assist(text: str, *, opened: str = "") -> str:
    digest = digest_error(text)
    head = opened.strip() if opened else "Listo para mirar el código."
    if digest:
        return (
            f"{head} Digest del error: {digest}. "
            "En el chat del HUD pegá el archivo o pedime el fix paso a paso — "
            "no lo leo entero por voz."
        )
    return (
        f"{head} Contame el lenguaje y el síntoma en una frase, "
        "o pegá el traceback en el HUD para el digest."
    )


def run_code_assist(
    text: str,
    *,
    open_app_fn: Callable[[str], str] | None = None,
) -> str:
    editor = preferred_editor(text)
    opened = ""
    if callable(open_app_fn):
        try:
            opened = str(open_app_fn(editor) or "").strip()
        except Exception:
            opened = ""
        if not opened:
            try:
                alt = "vscode" if editor == "cursor" else "cursor"
                opened = str(open_app_fn(alt) or "").strip()
            except Exception:
                opened = ""
    return speakable_code_assist(text, opened=opened or f"Abrí {editor}." if open_app_fn else "")
