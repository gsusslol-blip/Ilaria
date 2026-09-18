"""Verify prior GK fixes, then run a new 100-question set."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from jarvis.accounts import AccountStore
from jarvis.config import invalidate_ollama_ping, load_settings
from jarvis.state import AppState

# Quick regression on previously broken cases.
VERIFY: list[tuple[str, tuple[str, ...]]] = [
    ("¿Cuál es la capital de Japón?", ("tokio", "tokyo")),
    ("¿Cuál es la capital de Argentina?", ("buenos aires",)),
    ("¿A qué temperatura hierve el agua a nivel del mar?", ("100",)),
    ("¿Cuál es el elemento químico con símbolo Fe?", ("hierro",)),
    ("¿Cuánto es 15 por 8?", ("120",)),
    ("¿Cuánto es la raíz cuadrada de 144?", ("12",)),
    ("¿Cuántos minutos tiene una hora?", ("60",)),
    ("¿Cuántos segundos hay en una hora?", ("3600",)),
    ("cuanto es 25 por ciento de 200", ("50",)),
    ("cuanto es 7 al cubo", ("343",)),
]

# New 100 — distinct from bench_gk100.py set.
QUESTIONS: list[str] = [
    # Geografía 2
    "¿Cuál es la capital de Portugal?",
    "¿Cuál es la capital de Grecia?",
    "¿Cuál es la capital de Suecia?",
    "¿Cuál es la capital de Noruega?",
    "¿Cuál es la capital de Polonia?",
    "¿Cuál es la capital de Turquía?",
    "¿Cuál es la capital de Sudáfrica?",
    "¿Cuál es la capital de Nueva Zelanda?",
    "¿Cuál es la capital de Venezuela?",
    "¿Cuál es la capital de Ecuador?",
    "¿En qué país está la Torre Eiffel?",
    "¿En qué país está el Coliseo?",
    "¿Cuál es el lago más profundo del mundo?",
    "¿Qué mar separa Europa de África?",
    "¿Cuál es la isla más grande del mundo?",
    "¿En qué océano está Hawái?",
    "¿Cuál es la capital de Corea del Sur?",
    "¿Dónde queda el Amazonas?",
    "¿Qué país tiene forma de bota?",
    "¿Cuál es el volcán más alto de América?",
    # Historia 2
    "¿En qué año llegó el hombre a la Luna?",
    "¿Quién fue Tutankamón?",
    "¿Qué fue el Imperio Romano?",
    "¿Quién descubrió la penicilina?",
    "¿En qué año empezó la Primera Guerra Mundial?",
    "¿Quién fue Simón Bolívar?",
    "¿Qué fue la Revolución Industrial?",
    "¿Quién inventó la imprenta?",
    "¿En qué año se fundó Buenos Aires por segunda vez?",
    "¿Quién fue Mahatma Gandhi?",
    # Ciencia 2
    "¿Cuál es el planeta más cercano al Sol?",
    "¿Qué es un átomo?",
    "¿Cuántos cromosomas tiene el ser humano?",
    "¿Qué gas es el más abundante en la atmósfera terrestre?",
    "¿Qué es la evolución según Darwin?",
    "¿A qué temperatura se congela el agua?",
    "¿Qué es la energía cinética?",
    "¿Cuál es el símbolo químico del oro?",
    "¿Qué es un eclipse lunar?",
    "¿Cuánto dura un año en la Tierra aproximadamente en días?",
    "¿Qué órgano bombea la sangre?",
    "¿Qué vitamina ayuda a coagular la sangre?",
    "¿Qué es la velocidad del sonido aproximadamente?",
    "¿Cuál es el metal líquido a temperatura ambiente?",
    "¿Qué animal es el mamífero más grande?",
    # Cultura 2
    "¿Quién escribió Hamlet?",
    "¿Quién pintó Guernica?",
    "¿Quién compuso Las Cuatro Estaciones?",
    "¿Quién escribió La Odisea?",
    "¿En qué ciudad está el Museo del Prado?",
    "¿Quién escribió Rayuela?",
    "¿Quién es el autor de El Principito?",
    "¿Qué instrumento es el piano?",
    "¿Quién escribió Faust?",
    "¿Quién dirigió Titanic?",
    # Deportes 2
    "¿Cuántos jugadores hay en un equipo de básquet en cancha?",
    "¿Cada cuántos años es el Mundial de fútbol?",
    "¿Qué país ganó el Mundial 2018?",
    "¿Cuántos puntos vale un touchdown en fútbol americano?",
    "¿Qué es un ace en tenis?",
    "¿En qué deporte se usa un puck?",
    "¿Quién es Serena Williams?",
    "¿Cuántos rings tiene el logo olímpico?",
    # Math / cotidianas 2
    "¿Cuánto es 9 por 9?",
    "¿Cuánto es 144 dividido 12?",
    "¿Cuántos lados tiene un octógono?",
    "¿Cuánto es 10 al cuadrado?",
    "¿Cuánto es 50 por ciento de 80?",
    "¿Cuántos días tiene febrero en año no bisiesto?",
    "¿Cuántas semanas tiene un año aproximadamente?",
    "¿Cuánto es 2 elevado a 10?",
    # Tech 2
    "¿Qué significa RAM?",
    "¿Quién fundó Apple?",
    "¿Qué es un algoritmo?",
    "¿Qué significa URL?",
    "¿Quién creó la World Wide Web?",
    "¿Qué es el phishing?",
    # Curiosidades 2
    "¿Cuántos ojos tiene una araña normalmente?",
    "¿Pueden respirar los peces fuera del agua?",
    "¿De qué está hecha la Luna principalmente?",
    "¿Cuánto tarda la Tierra en dar la vuelta al Sol?",
    "¿Qué animal pone el huevo más grande?",
    "¿Cuántos estómagos tiene una vaca?",
    "¿Por qué parpadeamos?",
    "¿Qué es la Aurora Boreal?",
    # Argentina / LATAM 2
    "¿Quién fue José de San Martín?",
    "¿Cuál es la capital de Córdoba Argentina?",
    "¿En qué provincia está el Aconcagua?",
    "¿Qué es un asado?",
    "¿Quién fue Carlos Gardel?",
    "¿Cuál es el río más largo de Argentina?",
    "¿En qué ciudad está el Teatro Colón?",
    "¿Qué cordillera separa Argentina de Chile?",
    # Asistente cotidianas 2
    "¿Cuántos meses tiene un año?",
    "¿Qué hora es?",
    "¿Cuántos colores tiene el arcoíris?",
    "¿Qué es el WiFi?",
    "¿Cuántos sentidos tiene el ser humano tradicionalmente?",
    "¿Cuál es el animal terrestre más rápido?",
    "¿Qué es la fotosíntesis en una frase?",
    "¿Cuántas patas tiene una araña?",
    "¿Qué planeta es el más frío del sistema solar?",
    "¿Quién inventó el avión?",
    "¿Qué significa OTAN?",
    "¿Cuál es la capital de Perú?",
    "¿Qué gas exhalamos al respirar?",
    "¿Cuánto es 5 factorial?",
    "¿Cuál es un antónimo de grande?",
    "¿Cuál es el mar más salado?",
    "¿En qué país nació Lionel Messi?",
    "¿Qué vitamina tiene el kiwi principalmente?",
]

NEEDLES: dict[str, tuple[str, ...]] = {
    "¿Cuál es la capital de Portugal?": ("lisboa",),
    "¿Cuál es la capital de Grecia?": ("atenas",),
    "¿Cuál es la capital de Suecia?": ("estocolmo",),
    "¿Cuál es la capital de Noruega?": ("oslo",),
    "¿Cuál es la capital de Polonia?": ("varsovia",),
    "¿Cuál es la capital de Turquía?": ("ankara",),
    "¿Cuál es la capital de Nueva Zelanda?": ("wellington",),
    "¿Cuál es la capital de Venezuela?": ("caracas",),
    "¿Cuál es la capital de Ecuador?": ("quito",),
    "¿En qué país está la Torre Eiffel?": ("francia",),
    "¿En qué país está el Coliseo?": ("italia",),
    "¿Cuál es la capital de Corea del Sur?": ("seúl", "seul", "seoul"),
    "¿Qué país tiene forma de bota?": ("italia",),
    "¿En qué año llegó el hombre a la Luna?": ("1969",),
    "¿Quién descubrió la penicilina?": ("fleming",),
    "¿En qué año empezó la Primera Guerra Mundial?": ("1914",),
    "¿Quién inventó la imprenta?": ("gutenberg",),
    "¿Cuál es el planeta más cercano al Sol?": ("mercurio",),
    "¿Cuántos cromosomas tiene el ser humano?": ("46",),
    "¿Qué gas es el más abundante en la atmósfera terrestre?": ("nitrógeno", "nitrogeno", "n2"),
    "¿A qué temperatura se congela el agua?": ("0",),
    "¿Cuál es el símbolo químico del oro?": ("au",),
    "¿Cuánto dura un año en la Tierra aproximadamente en días?": ("365",),
    "¿Qué órgano bombea la sangre?": ("corazón", "corazon"),
    "¿Cuál es el metal líquido a temperatura ambiente?": ("mercurio",),
    "¿Qué animal es el mamífero más grande?": ("ballena",),
    "¿Quién escribió Hamlet?": ("shakespeare",),
    "¿Quién pintó Guernica?": ("picasso",),
    "¿Quién compuso Las Cuatro Estaciones?": ("vivaldi",),
    "¿Quién escribió La Odisea?": ("homero", "homer"),
    "¿En qué ciudad está el Museo del Prado?": ("madrid",),
    "¿Quién escribió Rayuela?": ("cortázar", "cortazar"),
    "¿Quién es el autor de El Principito?": ("saint-exupéry", "saint exupery", "exupéry", "exupery"),
    "¿Cuántos jugadores hay en un equipo de básquet en cancha?": ("5", "cinco"),
    "¿Cada cuántos años es el Mundial de fútbol?": ("4", "cuatro"),
    "¿Qué país ganó el Mundial 2018?": ("francia",),
    "¿Cuántos puntos vale un touchdown en fútbol americano?": ("6", "seis"),
    "¿En qué deporte se usa un puck?": ("hockey",),
    "¿Cuántos rings tiene el logo olímpico?": ("5", "cinco"),
    "¿Cuánto es 9 por 9?": ("81",),
    "¿Cuánto es 144 dividido 12?": ("12",),
    "¿Cuántos lados tiene un octógono?": ("8", "ocho"),
    "¿Cuánto es 10 al cuadrado?": ("100",),
    "¿Cuánto es 50 por ciento de 80?": ("40",),
    "¿Cuántos días tiene febrero en año no bisiesto?": ("28",),
    "¿Cuánto es 2 elevado a 10?": ("1024",),
    "¿Quién fundó Apple?": ("jobs", "wozniak", "steve"),
    "¿Quién creó la World Wide Web?": ("berners-lee", "berners lee", "tim berners"),
    "¿Cuántos ojos tiene una araña normalmente?": ("8", "ocho"),
    "¿Pueden respirar los peces fuera del agua?": ("no",),
    "¿Cuánto tarda la Tierra en dar la vuelta al Sol?": ("365", "año", "ano"),
    "¿Cuántos estómagos tiene una vaca?": ("4", "cuatro"),
    "¿En qué provincia está el Aconcagua?": ("mendoza",),
    "¿En qué ciudad está el Teatro Colón?": ("buenos aires",),
    "¿Qué cordillera separa Argentina de Chile?": ("andes",),
    "¿Cuántos meses tiene un año?": ("12", "doce"),
    "¿Cuántos colores tiene el arcoíris?": ("7", "siete"),
    "¿Cuántos sentidos tiene el ser humano tradicionalmente?": ("5", "cinco"),
    "¿Cuál es el animal terrestre más rápido?": ("guepardo", "chita", "cheetah"),
    "¿Cuántas patas tiene una araña?": ("8", "ocho"),
    "¿Quién inventó el avión?": ("wright",),
    "¿Cuál es la capital de Perú?": ("lima",),
    "¿Qué gas exhalamos al respirar?": ("dióxido", "dioxido", "co2", "carbónico", "carbonico"),
    "¿En qué país nació Lionel Messi?": ("argentina",),
}

BAD = (
    "sin llm",
    "sin key",
    "modo local",
    "groq.com",
    "traceback",
    "exception",
    "error:",
    "math failed",
)


def score(q: str, ans: str, err: str | None) -> str:
    if err:
        return "fail"
    low = ans.lower()
    if any(n in low for n in BAD):
        return "fail"
    if len(ans.strip()) < 1:
        return "fail"
    needles = NEEDLES.get(q)
    if needles and not any(n in low for n in needles):
        return "weak"
    return "ok"


def ask(brain, sid: str, q: str) -> tuple[int, str, str | None]:
    t0 = time.perf_counter()
    parts: list[str] = []
    err = None
    try:
        for chunk in brain.iter_reply(sid, q, None):
            parts.append(chunk)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}:{exc}"
    ms = round((time.perf_counter() - t0) * 1000)
    ans = ("".join(parts).strip() if parts else "") or (err or "")
    return ms, ans, err


def main() -> None:
    invalidate_ollama_ping()
    state = AppState(load_settings(), AccountStore())
    user = next(u for u in state.accounts.list_users() if u.is_owner)
    brain = state.brain_for(user)
    label = brain.endpoint.label if brain.settings.has_llm else "NONE"
    print(f"LLM: {label}")
    print("=== VERIFY previous fixes ===")
    v_fail = 0
    for i, (q, needles) in enumerate(VERIFY):
        ms, ans, err = ask(brain, f"ver{i}", q)
        low = ans.lower()
        ok = not err and any(n in low for n in needles)
        if not ok:
            v_fail += 1
        print(f"{'OK' if ok else 'FAIL'} {ms:5d}ms | {q} -> {re.sub(r'\\s+', ' ', ans)[:100]}")
    print(f"verify fail={v_fail}/{len(VERIFY)}\n")

    qs = QUESTIONS[:100]
    print(f"=== NEW SET questions={len(qs)} ===")
    rows: list[dict] = []
    out = Path("data") / "bench_gk100_b.json"
    t_all = time.perf_counter()
    for i, q in enumerate(qs, 1):
        ms, ans, err = ask(brain, f"b{i}", q)
        logic = score(q, ans, err)
        preview = re.sub(r"\s+", " ", ans)[:160]
        rows.append({"i": i, "q": q, "ms": ms, "logic": logic, "preview": preview})
        print(f"{i:03d}/{len(qs)} {ms:6d}ms {logic:4} | {q}")
        print(f"         {preview}")
        if i % 5 == 0:
            out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    times = [r["ms"] for r in rows]
    summary = {
        "n": len(rows),
        "ok": sum(1 for r in rows if r["logic"] == "ok"),
        "weak": sum(1 for r in rows if r["logic"] == "weak"),
        "fail": sum(1 for r in rows if r["logic"] == "fail"),
        "ms_min": min(times),
        "ms_med": sorted(times)[len(times) // 2],
        "ms_max": max(times),
        "ms_avg": sum(times) // len(times),
        "elapsed_sec": round(time.perf_counter() - t_all, 1),
        "verify_fail": v_fail,
        "llm": label,
    }
    print("=" * 72)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    bad = [r for r in rows if r["logic"] != "ok"]
    print(f"\nweak/fail ({len(bad)}):")
    for r in bad:
        print(f"  [{r['logic']}] {r['ms']}ms | {r['q']} -> {r['preview'][:110]}")
    out.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("saved", out)


if __name__ == "__main__":
    main()
