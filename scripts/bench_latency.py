"""Ad-hoc latency + logic smoke for Ilaria brain replies."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from jarvis.accounts import AccountStore
from jarvis.config import invalidate_ollama_ping, load_settings
from jarvis.state import AppState


def main() -> None:
    invalidate_ollama_ping()
    state = AppState(load_settings(), AccountStore())
    user = next(u for u in state.accounts.list_users() if u.is_owner)
    brain = state.brain_for(user)
    label = brain.endpoint.label if brain.settings.has_llm else "NONE"
    print(f"LLM: {label} | has_llm={brain.settings.has_llm}")
    print(
        "provider/model:",
        getattr(brain.settings, "llm_provider", "?"),
        getattr(brain.settings, "llm_model", "?")
        or getattr(brain.settings, "ollama_model", "?"),
    )
    print()

    cases = [
        ("fast_hora", "que hora es"),
        ("fast_vol", "poneme el volumen al 40"),
        ("fast_mute", "silencia"),
        ("fast_timer", "timer de 2 minutos"),
        ("chat", "hola como estas"),
        ("math", "cuanto es 17 por 23"),
        ("fact_local", "capital de Francia"),
        ("search_live", "precio dolar blue argentina hoy"),
        ("explain", "explicame la fotosintesis en 3 lineas"),
        ("distance", "que distancia hay de Buenos Aires a Brasilia"),
        ("recipe", "receta de brownies"),
        ("execute", "abri la calculadora"),
        ("manage", "resumime en una frase que puedo hacer con vos"),
        ("ambiguous", "poneme algo"),
        ("tip", "decime un tip corto para dormir mejor"),
    ]

    bad_needles = (
        "sin llm",
        "sin key",
        "modo local",
        "groq.com",
        "recipe_text",
        "volvé a llamar",
        "volv a llamar",
        "kitchen_recipe",
        "todavía no armé",
        "todavia no arme",
        "traceback",
        "exception",
        "error:",
    )

    rows: list[dict] = []
    for i, (kind, q) in enumerate(cases):
        t0 = time.perf_counter()
        parts: list[str] = []
        err = None
        try:
            for chunk in brain.iter_reply(f"bench{i}", q, None):
                parts.append(chunk)
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}:{exc}"
        ms = (time.perf_counter() - t0) * 1000
        ans = ("".join(parts).strip() if parts else "") or (err or "")
        low = ans.lower()
        bad = bool(err) or any(n in low for n in bad_needles) or len(ans) < 2
        logic = "ok"
        if kind == "fast_hora" and not re.search(r"\d{1,2}:\d{2}|\d{1,2}", ans):
            logic = "weak"
        if kind == "math" and "391" not in ans.replace(" ", ""):
            logic = "weak"
        if kind == "fact_local" and "par" not in low:
            logic = "weak"
        if kind == "execute" and not any(
            x in low for x in ("listo", "abr", "calcul", "ok", "hecho", "ya")
        ):
            logic = "weak"
        if kind == "ambiguous" and len(ans) < 8:
            logic = "weak"
        if bad:
            logic = "fail"
        preview = ans.replace("\n", " ")[:180]
        print(f"{ms:7.0f}ms | {logic:4} | {kind:14} | {q}")
        print(f"         -> {preview}")
        print()
        rows.append(
            {
                "kind": kind,
                "q": q,
                "ms": round(ms),
                "logic": logic,
                "preview": preview,
            }
        )

    ok = sum(1 for r in rows if r["logic"] != "fail")
    weak = sum(1 for r in rows if r["logic"] == "weak")
    fail = sum(1 for r in rows if r["logic"] == "fail")
    times = [r["ms"] for r in rows]
    print("=" * 72)
    print(f"n={len(rows)} ok={ok} weak={weak} fail={fail}")
    print(
        f"ms min={min(times)} med={sorted(times)[len(times) // 2]} "
        f"max={max(times)} avg={sum(times) // len(times)}"
    )
    fast = [r["ms"] for r in rows if r["kind"].startswith("fast_")]
    other = [r["ms"] for r in rows if not r["kind"].startswith("fast_")]
    if fast:
        print(
            f"fast_path avg={sum(fast) // len(fast)}ms "
            f"med={sorted(fast)[len(fast) // 2]}ms"
        )
    if other:
        print(
            f"llm/tools avg={sum(other) // len(other)}ms "
            f"med={sorted(other)[len(other) // 2]}ms"
        )
    out = Path("data") / "bench_latency.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
