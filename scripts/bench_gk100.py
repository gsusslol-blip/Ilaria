"""~100 general-knowledge questions against live Ilaria brain."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from jarvis.accounts import AccountStore
from jarvis.config import invalidate_ollama_ping, load_settings
from jarvis.state import AppState

# Diverse general-knowledge prompts people ask a voice assistant.
QUESTIONS: list[str] = [
    # Geografía
    "¿Cuál es la capital de Francia?",
    "¿Cuál es la capital de Japón?",
    "¿Cuál es la capital de Argentina?",
    "¿Cuál es la capital de Brasil?",
    "¿Cuál es la capital de España?",
    "¿Cuál es la capital de Italia?",
    "¿Cuál es la capital de Alemania?",
    "¿Cuál es la capital de Australia?",
    "¿Cuál es la capital de Canadá?",
    "¿Cuál es la capital de Egipto?",
    "¿Cuál es el río más largo del mundo?",
    "¿Cuál es la montaña más alta del mundo?",
    "¿En qué continente está Nigeria?",
    "¿Qué océano baña la costa este de Estados Unidos?",
    "¿Cuál es el desierto más grande del mundo?",
    "¿Dónde queda Machu Picchu?",
    "¿Cuál es la ciudad más poblada del mundo?",
    "¿En qué país está el Taj Mahal?",
    "¿Cuál es la capital de Marruecos?",
    "¿Qué países limitan con Argentina?",
    # Historia
    "¿En qué año llegó Colón a América?",
    "¿Quién fue Napoleón Bonaparte?",
    "¿En qué año terminó la Segunda Guerra Mundial?",
    "¿Quién inventó la bombilla?",
    "¿Quién fue Cleopatra?",
    "¿En qué año cayó el Muro de Berlín?",
    "¿Quién escribió la Declaración de Independencia de EE.UU.?",
    "¿Qué fue la Revolución Francesa?",
    "¿Quién fue Julio César?",
    "¿En qué año se independizó Argentina?",
    # Ciencia
    "¿Qué es la fotosíntesis?",
    "¿Cuántos planetas hay en el sistema solar?",
    "¿Cuál es el planeta más grande del sistema solar?",
    "¿Qué gas respiramos principalmente?",
    "¿Cuál es la fórmula del agua?",
    "¿Qué es la gravedad?",
    "¿A qué temperatura hierve el agua a nivel del mar?",
    "¿Qué es el ADN?",
    "¿Quién propuso la teoría de la relatividad?",
    "¿Qué es un agujero negro?",
    "¿Cuántos huesos tiene el cuerpo humano adulto?",
    "¿Qué vitamina produce el sol en la piel?",
    "¿Qué es la velocidad de la luz aproximadamente?",
    "¿Cuál es el elemento químico con símbolo Fe?",
    "¿Qué animal es un mamífero que pone huevos?",
    # Cultura / arte
    "¿Quién pintó la Mona Lisa?",
    "¿Quién escribió Don Quijote?",
    "¿Quién escribió Romeo y Julieta?",
    "¿Quién compuso la Novena Sinfonía?",
    "¿Quién pintó la última cena?",
    "¿En qué museo está la Mona Lisa?",
    "¿Quién escribió Cien años de soledad?",
    "¿Quién es el autor de Harry Potter?",
    "¿Qué instrumento tocaba Mozart principalmente como compositor?",
    "¿Quién escribó Martín Fierro?",
    # Deportes
    "¿Cada cuántos años son los Juegos Olímpicos de verano?",
    "¿Cuántos jugadores hay por equipo en un partido de fútbol?",
    "¿Qué país ganó el Mundial de fútbol 2022?",
    "¿Cuántos sets se necesitan para ganar un partido de tenis Grand Slam masculino?",
    "¿Qué es un hat-trick en fútbol?",
    "¿En qué deporte se usa un bate y una pelota blanca con costuras?",
    "¿Cuántos puntos vale un try en rugby union?",
    "¿Quién es Lionel Messi?",
    # Matemática / cotidianas
    "¿Cuánto es 15 por 8?",
    "¿Cuánto es la raíz cuadrada de 144?",
    "¿Cuántos lados tiene un hexágono?",
    "¿Cuántos minutos tiene una hora?",
    "¿Cuántos días tiene un año bisiesto?",
    "¿Cuánto es 25 por ciento de 200?",
    "¿Cuántos segundos hay en una hora?",
    # Tecnología / internet
    "¿Qué significa CPU?",
    "¿Quién fundó Microsoft?",
    "¿Qué es Wi-Fi?",
    "¿Qué significa HTTP?",
    "¿Quién creó Linux?",
    "¿Qué es la inteligencia artificial?",
    # Idioma / curiosidades
    "¿Cuál es el idioma más hablado del mundo como lengua nativa?",
    "¿Cuántas letras tiene el abecedario español?",
    "¿Qué significa carpe diem?",
    "¿De qué color es el sol realmente?",
    "¿Por qué el cielo es azul?",
    "¿Cuántos corazones tiene un pulpo?",
    "¿Pueden volar los pingüinos?",
    "¿Cuánto tarda la luz del sol en llegar a la Tierra?",
    # Argentina / LATAM cotidianas
    "¿Quién fue Eva Perón?",
    "¿Cuál es la moneda de Argentina?",
    "¿En qué provincia está Iguazú?",
    "¿Qué es el mate?",
    "¿Quién fue Diego Maradona?",
    "¿Cuál es el plato típico argentino más famoso?",
    "¿En qué ciudad está el Obelisco?",
    "¿Qué río separa Argentina de Uruguay?",
    # Miscelánea “alguien le preguntaría a un asistente”
    "¿Cuántas horas tiene un día?",
    "¿Qué día es hoy?",
    "¿En qué estación del año estamos en el hemisferio sur?",
    "¿Qué es Bitcoin?",
    "¿Cuántos continentes hay?",
    "¿Cuál es el animal más rápido del mundo?",
    "¿Qué es un eclipse solar?",
    "¿Cuántos dientes tiene un adulto normalmente?",
    "¿Qué planeta es conocido como el planeta rojo?",
    "¿Quién inventó el teléfono?",
    "¿Qué es la democracia?",
    "¿Cuántas cuerdas tiene una guitarra estándar?",
    "¿Qué significa ONU?",
    "¿Cuál es la capital de México?",
    "¿Qué gas usan las plantas en la fotosíntesis?",
    "¿Cuánto es 7 al cubo?",
    "¿Qué es un sinónimo de feliz?",
    "¿Cuál es el océano más grande?",
    "¿En qué país nació Shakira?",
    "¿Qué vitaminas tiene el limón principalmente?",
]

# Optional answer needles (lowercase substrings). Missing => weak if answer otherwise ok.
NEEDLES: dict[str, tuple[str, ...]] = {
    "¿Cuál es la capital de Francia?": ("parís", "paris"),
    "¿Cuál es la capital de Japón?": ("tokio", "tokyo"),
    "¿Cuál es la capital de Argentina?": ("buenos aires",),
    "¿Cuál es la capital de Brasil?": ("brasília", "brasilia"),
    "¿Cuál es la capital de España?": ("madrid",),
    "¿Cuál es la capital de Italia?": ("roma",),
    "¿Cuál es la capital de Alemania?": ("berlín", "berlin"),
    "¿Cuál es la capital de Australia?": ("canberra",),
    "¿Cuál es la capital de Canadá?": ("ottawa", "otáwa"),
    "¿Cuál es la capital de Egipto?": ("cairo", "el cairo"),
    "¿Cuál es la montaña más alta del mundo?": ("everest",),
    "¿En qué continente está Nigeria?": ("africa", "áfrica"),
    "¿En qué país está el Taj Mahal?": ("india",),
    "¿Cuál es la capital de Marruecos?": ("rabat",),
    "¿En qué año llegó Colón a América?": ("1492",),
    "¿En qué año terminó la Segunda Guerra Mundial?": ("1945",),
    "¿Quién inventó la bombilla?": ("edison",),
    "¿En qué año cayó el Muro de Berlín?": ("1989",),
    "¿En qué año se independizó Argentina?": ("1816",),
    "¿Cuántos planetas hay en el sistema solar?": ("8", "ocho"),
    "¿Cuál es el planeta más grande del sistema solar?": ("júpiter", "jupiter"),
    "¿Cuál es la fórmula del agua?": ("h2o", "h₂o"),
    "¿A qué temperatura hierve el agua a nivel del mar?": ("100",),
    "¿Quién propuso la teoría de la relatividad?": ("einstein",),
    "¿Cuál es el elemento químico con símbolo Fe?": ("hierro",),
    "¿Quién pintó la Mona Lisa?": ("leonardo", "da vinci", "vinci"),
    "¿Quién escribió Don Quijote?": ("cervantes",),
    "¿Quién escribió Romeo y Julieta?": ("shakespeare",),
    "¿Quién compuso la Novena Sinfonía?": ("beethoven",),
    "¿Quién pintó la última cena?": ("leonardo", "da vinci", "vinci"),
    "¿Quién escribió Cien años de soledad?": ("garcía márquez", "garcia marquez", "márquez", "marquez"),
    "¿Quién es el autor de Harry Potter?": ("rowling", "jk rowling", "j.k."),
    "¿Quién escribó Martín Fierro?": ("hernández", "hernandez"),
    "¿Cada cuántos años son los Juegos Olímpicos de verano?": ("4", "cuatro"),
    "¿Cuántos jugadores hay por equipo en un partido de fútbol?": ("11", "once"),
    "¿Qué país ganó el Mundial de fútbol 2022?": ("argentina",),
    "¿Cuánto es 15 por 8?": ("120",),
    "¿Cuánto es la raíz cuadrada de 144?": ("12",),
    "¿Cuántos lados tiene un hexágono?": ("6", "seis"),
    "¿Cuántos minutos tiene una hora?": ("60", "sesenta"),
    "¿Cuántos días tiene un año bisiesto?": ("366",),
    "¿Cuánto es 25 por ciento de 200?": ("50",),
    "¿Cuántos segundos hay en una hora?": ("3600", "3.600"),
    "¿Quién fundó Microsoft?": ("gates", "bill"),
    "¿Quién creó Linux?": ("torvalds", "linus"),
    "¿Pueden volar los pingüinos?": ("no",),
    "¿Cuál es la moneda de Argentina?": ("peso",),
    "¿En qué ciudad está el Obelisco?": ("buenos aires",),
    "¿Cuántas horas tiene un día?": ("24", "veinticuatro"),
    "¿Cuántos continentes hay?": ("7", "seis", "5", "cinco", "ocho"),  # varies by model
    "¿Qué planeta es conocido como el planeta rojo?": ("marte",),
    "¿Quién inventó el teléfono?": ("bell",),
    "¿Cuántas cuerdas tiene una guitarra estándar?": ("6", "seis"),
    "¿Qué significa ONU?": ("naciones unidas",),
    "¿Cuál es la capital de México?": ("ciudad de méxico", "mexico city", "cdmx", "méxico"),
    "¿Qué gas usan las plantas en la fotosíntesis?": ("dióxido", "dioxido", "co2", "carbónico", "carbonico"),
    "¿Cuánto es 7 al cubo?": ("343",),
    "¿Cuál es el océano más grande?": ("pacífico", "pacifico"),
    "¿En qué país nació Shakira?": ("colombia",),
}


BAD_NEEDLES = (
    "sin llm",
    "sin key",
    "modo local",
    "groq.com",
    "recipe_text",
    "traceback",
    "exception",
    "error:",
    "no pude",
    "no tengo acceso",
)


def score(q: str, ans: str, err: str | None) -> str:
    if err:
        return "fail"
    low = ans.lower()
    if len(ans.strip()) < 3 or any(n in low for n in BAD_NEEDLES):
        return "fail"
    needles = NEEDLES.get(q)
    if needles and not any(n in low for n in needles):
        return "weak"
    return "ok"


def main() -> None:
    qs = QUESTIONS[:100]
    print(f"questions={len(qs)}")
    invalidate_ollama_ping()
    state = AppState(load_settings(), AccountStore())
    user = next(u for u in state.accounts.list_users() if u.is_owner)
    brain = state.brain_for(user)
    label = brain.endpoint.label if brain.settings.has_llm else "NONE"
    print(f"LLM: {label} | has_llm={brain.settings.has_llm}")
    print()

    out = Path("data") / "bench_gk100.json"
    rows: list[dict] = []
    t_all = time.perf_counter()

    for i, q in enumerate(qs, 1):
        t0 = time.perf_counter()
        parts: list[str] = []
        err = None
        try:
            for chunk in brain.iter_reply(f"gk{i}", q, None):
                parts.append(chunk)
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}:{exc}"
        ms = round((time.perf_counter() - t0) * 1000)
        ans = ("".join(parts).strip() if parts else "") or (err or "")
        logic = score(q, ans, err)
        preview = re.sub(r"\s+", " ", ans)[:160]
        row = {"i": i, "q": q, "ms": ms, "logic": logic, "preview": preview}
        rows.append(row)
        print(f"{i:03d}/{len(qs)} {ms:6d}ms {logic:4} | {q}")
        print(f"         {preview}")
        # checkpoint every 5
        if i % 5 == 0 or i == len(qs):
            out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.perf_counter() - t_all
    times = [r["ms"] for r in rows]
    ok = sum(1 for r in rows if r["logic"] == "ok")
    weak = sum(1 for r in rows if r["logic"] == "weak")
    fail = sum(1 for r in rows if r["logic"] == "fail")
    summary = {
        "n": len(rows),
        "ok": ok,
        "weak": weak,
        "fail": fail,
        "ms_min": min(times),
        "ms_med": sorted(times)[len(times) // 2],
        "ms_max": max(times),
        "ms_avg": sum(times) // len(times),
        "elapsed_sec": round(elapsed, 1),
        "llm": label,
    }
    print("=" * 72)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    weak_fail = [r for r in rows if r["logic"] != "ok"]
    print(f"\nweak/fail ({len(weak_fail)}):")
    for r in weak_fail:
        print(f"  [{r['logic']}] {r['ms']}ms | {r['q']} -> {r['preview'][:100]}")
    out.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("saved", out)


if __name__ == "__main__":
    main()
