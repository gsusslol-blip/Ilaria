"""Live market numbers and headlines. Search snippets often omit the fact."""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

_HEADERS = {
    "User-Agent": "IlariaLocalAssistant/1.6 (https://localhost; personal-assistant)",
    "Accept": "application/json",
}


def live_headlines(topic: str, limit: int = 2) -> str | None:
    """Two current headlines. News homepages don't carry the story."""
    q = " ".join((topic or "").split()).strip(" .?¿!")
    if len(q) < 3:
        return None
    try:
        with httpx.Client(timeout=8.0, headers=_HEADERS, follow_redirects=True) as client:
            response = client.get(
                "https://news.google.com/rss/search",
                params={"q": q, "hl": "es-419", "gl": "AR", "ceid": "AR:es-419"},
            )
            response.raise_for_status()
            body = response.text
    except Exception:  # noqa: BLE001
        return None
    titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", body, flags=re.S)
    picked: list[str] = []
    for raw in titles:
        text = " ".join(html.unescape(raw).split())
        low = text.lower()
        if not text or "google" in low and "noticia" in low:
            continue
        picked.append(text)
        if len(picked) >= limit:
            break
    if not picked:
        return None
    return " ".join(item if item.endswith(".") else item + "." for item in picked)


def live_market_quote(text: str) -> str | None:
    """Return a spoken FX/crypto quote, or None so the caller can search."""
    low = (text or "").lower()
    parts: list[str] = []
    try:
        if re.search(r"\b(bitcoin|btc)\b", low):
            hit = _bitcoin()
            if hit:
                parts.append(hit)
        if re.search(r"\b(d[oó]lar(?:es)?|blue|mep|ccl)\b", low):
            hit = _dolar(low)
            if hit:
                parts.append(hit)
        if re.search(r"\b(euro|eur)\b", low):
            hit = _euro()
            if hit:
                parts.append(hit)
    except Exception:  # noqa: BLE001
        if not parts:
            return None
    spoken = " ".join(parts).strip()
    return spoken or None


def _pesos(value: Any) -> str:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return "?"
    return f"{number:,}".replace(",", ".")


def _dolar(low: str) -> str | None:
    with httpx.Client(timeout=8.0, headers=_HEADERS, follow_redirects=True) as client:
        response = client.get("https://dolarapi.com/v1/dolares")
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        return None
    by_casa = {
        str(row.get("casa") or "").lower(): row
        for row in rows
        if isinstance(row, dict)
    }
    if re.search(r"\bblue\b", low):
        wanted = ("blue",)
    elif re.search(r"\bmep\b|\bbolsa\b", low):
        wanted = ("bolsa",)
    elif re.search(r"\bccl\b|contado\s+con\s+liqui", low):
        wanted = ("contadoconliqui",)
    elif re.search(r"\boficial\b", low):
        wanted = ("oficial",)
    else:
        wanted = ("oficial", "blue")
    parts: list[str] = []
    for casa in wanted:
        row = by_casa.get(casa)
        if not row:
            continue
        name = "blue" if casa == "blue" else ("MEP" if casa == "bolsa" else ("CCL" if casa == "contadoconliqui" else "oficial"))
        parts.append(
            f"el dólar {name} está a {_pesos(row.get('compra'))} pesos la compra "
            f"y {_pesos(row.get('venta'))} la venta"
        )
    if not parts:
        return None
    spoken = parts[0][0].upper() + parts[0][1:]
    if len(parts) == 2:
        spoken = f"{spoken}, y {parts[1]}"
    if not spoken.endswith("."):
        spoken += "."
    return spoken


def _euro() -> str | None:
    """EUR oficial from the same cotizaciones feed as the dollar boards."""
    with httpx.Client(timeout=8.0, headers=_HEADERS, follow_redirects=True) as client:
        response = client.get("https://dolarapi.com/v1/cotizaciones")
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        return None
    chosen: dict[str, Any] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("moneda") or "").upper() != "EUR":
            continue
        casa = str(row.get("casa") or "").lower()
        if casa == "oficial":
            chosen = row
            break
        if chosen is None:
            chosen = row
    if not chosen:
        return None
    return (
        f"El euro está a {_pesos(chosen.get('compra'))} pesos la compra "
        f"y {_pesos(chosen.get('venta'))} la venta."
    )


def _bitcoin() -> str | None:
    with httpx.Client(timeout=8.0, headers=_HEADERS, follow_redirects=True) as client:
        response = client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        )
        response.raise_for_status()
        payload = response.json()
    usd = ((payload or {}).get("bitcoin") or {}).get("usd")
    if usd is None:
        return None
    try:
        number = float(usd)
    except (TypeError, ValueError):
        return None
    shown = f"{int(round(number)):,}".replace(",", ".")
    return f"El bitcoin está en {shown} dólares."
