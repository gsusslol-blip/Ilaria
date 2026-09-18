"""Shared pause flag: HUD Libre owns the mic → Porcupine waits."""

from __future__ import annotations

import threading

_HUD_LISTENING = threading.Event()


def set_hud_listening(active: bool) -> None:
    """True while the HUD hands-free / push-to-talk path holds the mic."""
    if active:
        _HUD_LISTENING.set()
    else:
        _HUD_LISTENING.clear()


def hud_listening() -> bool:
    return _HUD_LISTENING.is_set()
