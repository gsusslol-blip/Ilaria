"""Fixed soft refusals — medical diagnosis and payment/banking intents."""

from __future__ import annotations

import re

from jarvis.subjective import fixed_subjective_reply as _subjective

MEDICAL_RE = re.compile(
    r"\b("
    r"me\s+duele\s+(?:la\s+|el\s+|mi\s+)?(?:cabeza|est[oó]mago|garganta|pecho|espalda|"
    r"oido|o[ií]do|muela|diente|pierna|brazo|panza|barriga|vientre)|"
    r"tengo\s+(?:un\s+)?(?:dolor|fiebre|tos|migra[nñ]a|infecci[oó]n|v[oó]mito)|"
    r"qu[eé]\s+(?:tomo|me\s+tomo|medicamento|remedio|antib[ií]otic)|"
    r"me\s+(?:recet[aá]s?|diagnostic|prescrib)|"
    r"(?:tengo|es)\s+(?:c[aá]ncer|diabetes|covid|gripe\s+a)|"
    r"dosis\s+de\s+\w+|cu[aá]ntos?\s+mg\s+(?:de\s+)?\w+|"
    r"debo\s+(?:tomar|inyectar)|autodiagn[oó]stic|"
    r"qu[eé]\s+enfermedad\s+tengo|ser[aá]\s+(?:grave|c[aá]ncer)|"
    r"necesito\s+(?:un\s+)?(?:antibi[oó]tico|analg[eé]sico)"
    r")\b",
    re.I,
)

MEDICAL_REPLY = (
    "No puedo diagnosticar ni indicar medicamentos. "
    "Si el dolor o el síntoma preocupa, consultá a un médico o urgencias. "
    "Puedo anotar el síntoma en tu bitácora de bienestar o leer el reloj — "
    "decime qué preferís."
)

# Habit / watch questions that must NOT hit medical refusal.
WELLNESS_OK_RE = re.compile(
    r"\b("
    r"reloj|smartwatch|pasos|hrv|sue[nñ]o|hidrat|tom[aá]\s+agua|"
    r"estirar|pomodoro|entrenamiento|nutrici[oó]n|ciclo|"
    r"leer\s+el\s+reloj|c[oó]mo\s+estoy\s+de\s+energ"
    r")\b",
    re.I,
)

PAYMENT_RE = re.compile(
    r"\b("
    r"transfer[ií]|pag(?:ar|ame|ale)|devolv[eé]\s+plata|"
    r"envi[aá]\s+(?:plata|dinero|pesos)|"
    r"abr[ií]\s+(?:el\s+)?(?:banco|home\s*banking|mercado\s*pago|uala|brubank)|"
    r"clave\s+(?:del\s+)?(?:banco|tarjeta)|cvv|cbu\s+de|"
    r"comprar\s+con\s+(?:mi\s+)?tarjeta|pag[aá]\s+la\s+factura\s+con"
    r")\b",
    re.I,
)

PAYMENT_REPLY = (
    "Eso no lo hago: no abro bancos, no transfiero ni manejo claves o tarjetas. "
    "Si necesitás un recordatorio de pago o anotar un monto en la bitácora, eso sí."
)


def fixed_policy_reply(text: str) -> str | None:
    """Subjective + medical + payment soft refusals. None = continue routing."""
    raw = (text or "").strip()
    if not raw:
        return None
    sub = _subjective(raw)
    if sub:
        return sub
    if MEDICAL_RE.search(raw) and not WELLNESS_OK_RE.search(raw):
        return MEDICAL_REPLY
    if PAYMENT_RE.search(raw):
        return PAYMENT_REPLY
    return None
