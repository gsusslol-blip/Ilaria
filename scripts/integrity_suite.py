"""Integrity suite: clear answers, no junk, and action routing (HUD + phone surfaces).

Run (HUD optional for live chat):
  .venv\\Scripts\\python.exe scripts\\integrity_suite.py
  .venv\\Scripts\\python.exe scripts\\integrity_suite.py --live
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.accounts import AccountStore
from jarvis.config import load_settings
from jarvis.fast_path import try_fast_path
from jarvis.gk_fixes import lookup_gk_fix
from jarvis.local import try_local_command
from jarvis.memory import Memory
from jarvis.search_speak import looks_like_search_dump, speakable_from_search
from jarvis.state import AppState


def _ok(name: str, passed: bool, detail: str = "") -> bool:
    mark = "OK" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def test_gk_clarity() -> int:
    print("\n== GK clarity ==")
    cases = [
        ("cual es el mamifero mas grande", "ballena"),
        ("metal liquido a temperatura ambiente", "mercurio"),
        ("quien descubrio America segun la historia", "col"),
        ("simbolo Fe", "hierro"),
        ("pais forma de bota", "italia"),
        ("cuantos planetas hay en el sistema solar", "ocho"),
    ]
    fails = 0
    for q, needle in cases:
        ans = (lookup_gk_fix(q) or "").lower()
        if not _ok(q, needle in ans and "qatar" not in ans and "http" not in ans, ans[:80]):
            fails += 1
    return fails


def test_speakable_rejects_junk() -> int:
    print("\n== Speakable rejects junk ==")
    junk = (
        "Source: bing (5 hits).\n"
        "- Gran Premio del Qatar 2024 - Formula 1\n"
        "  https://www.formula1.com/qatar\n"
        "  Qatar Grand Prix 2024 - F1 Race - Formula 1.\n"
    )
    out = speakable_from_search(junk, "quien descubrio America")
    fails = 0
    if not _ok("reject F1 dump", out == "", repr(out)):
        fails += 1
    if not _ok("detect dump", looks_like_search_dump(junk)):
        fails += 1
    good = (
        "Source: yahoo (1 hits).\n"
        "- París - Wikipedia\n"
        "  https://es.wikipedia.org/wiki/París\n"
        "  París es la capital de Francia y su ciudad más poblada.\n"
    )
    spoken = speakable_from_search(good, "capital de Francia")
    if not _ok("paris speakable", "par" in spoken.lower() and "http" not in spoken.lower(), spoken[:100]):
        fails += 1
    return fails


def test_actions_routing() -> int:
    print("\n== Action routing (fast_path / local) ==")
    fails = 0
    captured: list[tuple[str, dict]] = []

    def execute(name: str, arguments_json: str) -> str:
        args = json.loads(arguments_json or "{}")
        captured.append((name, args))
        if name == "calculate":
            return "42"
        if name == "now":
            return "Hoy es sábado."
        if name == "set_volume":
            return f"Volumen {args.get('level')}%."
        if name == "open_app":
            return f"Abrí {args.get('name')}."
        if name == "phone_hands":
            return f"OK phone {args.get('action')}"
        return "OK"

    settings = load_settings()
    mem = Memory()

    cases = [
        ("cuanto es 6 por 7", "calculate", "hud"),
        ("que hora es", "now", "hud"),
        ("volumen al 35", "set_volume", "hud"),
        ("abrí el bloc de notas", "open_app", "hud"),
        ("volumen al 40", "phone_hands", "android"),
        ("cómo llego a Palermo", "phone_hands", "ios"),
    ]
    for text, expect_tool, surface in cases:
        captured.clear()
        hit = try_fast_path(text, execute, surface=surface)
        if not hit:
            try_local_command(text, execute, mem, settings, surface=surface)
        tools = [t for t, _ in captured]
        ok = expect_tool in tools
        detail = f"got={tools} args={captured[-1][1] if captured else {}}"
        if not _ok(f"{surface}: {text}", ok, detail):
            fails += 1
    return fails


def test_brain_offline_clarity(username: str | None = None) -> int:
    print("\n== Brain clarity (in-process) ==")
    fails = 0
    accounts = AccountStore()
    owner = accounts.owner()
    if owner is None:
        print("  [SKIP] no owner")
        return 0
    state = AppState(load_settings(), accounts)
    brain = state.brain_for(owner)

    checks = [
        ("cual es el mamifero mas grande del mundo", r"ballena", r"qatar|http://|source:"),
        ("quien descubrio America segun la historia", r"col[oó]n", r"qatar|grand prix|teor[ií]as"),
        ("cuanto es 15 por 8", r"120", r"no s[eé]|error"),
        ("que hora es", r".{4,}", r"wikipedia failed|source:"),
        ("volumen al 28", r"28|volumen", r"source:|http"),
    ]
    for msg, good, bad in checks:
        reply = "".join(
            chunk for chunk in brain.iter_reply(f"integrity-{hash(msg) & 0xFFFF}", msg, None) if isinstance(chunk, str)
        )
        clean = reply.strip()
        passed = bool(re.search(good, clean, re.I)) and not re.search(bad, clean, re.I)
        if not looks_like_search_dump(clean) and len(clean) < 400:
            pass
        else:
            if looks_like_search_dump(clean):
                passed = False
        if not _ok(msg, passed, clean[:120].replace("\n", " ")):
            fails += 1
    return fails


def test_live_hud(base: str) -> int:
    print(f"\n== Live HUD {base} ==")
    fails = 0
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as resp:
            health = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"  [SKIP] HUD down: {exc}")
        return 0

    if not _ok("health", health.get("ok") == "1" and health.get("app") == "Ilaria", str(health)[:80]):
        fails += 1

    for path in ("/version.json", "/static/version.json"):
        try:
            with urllib.request.urlopen(base + path, timeout=5) as resp:
                body = json.loads(resp.read().decode())
            ver = str(body.get("version") or "")
            android = body.get("android") or {}
            ok = ver.startswith("1.5.") and str(android.get("versionName") or "").startswith("1.5.")
            if not _ok(path, ok, f"v={ver} android={android.get('versionName')}"):
                fails += 1
        except Exception as exc:  # noqa: BLE001
            if not _ok(path, False, str(exc)):
                fails += 1

    accounts = AccountStore()
    owner = accounts.owner()
    if owner is None:
        print("  [SKIP] chat — no owner")
        return fails
    token = accounts.create_session(owner.id)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Ilaria-Token": token,
        "Content-Type": "application/json",
    }

    def chat(message: str) -> str:
        data = json.dumps({"message": message, "speak": False}).encode()
        req = urllib.request.Request(base + "/api/chat", data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
        return str(payload.get("reply") or payload.get("text") or "")

    live_cases = [
        ("cual es el mamifero mas grande del mundo", r"ballena", r"qatar|source:"),
        ("quien descubrio America", r"col[oó]n", r"qatar|grand prix"),
        ("cuanto es 9 por 9", r"81", r"error"),
        ("que hora es", r".{3,}", r"failed"),
    ]
    for msg, good, bad in live_cases:
        try:
            reply = chat(msg)
            passed = bool(re.search(good, reply, re.I)) and not re.search(bad, reply, re.I)
            passed = passed and not looks_like_search_dump(reply)
            if not _ok(f"chat: {msg}", passed, reply[:100].replace("\n", " ")):
                fails += 1
        except Exception as exc:  # noqa: BLE001
            if not _ok(f"chat: {msg}", False, str(exc)):
                fails += 1
    return fails


def test_version_alignment() -> int:
    print("\n== Version alignment PC/Android/iOS ==")
    fails = 0
    from jarvis import __version__

    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    m_name = re.search(r'versionName\s*=\s*"([^"]+)"', gradle)
    m_code = re.search(r"versionCode\s*=\s*(\d+)", gradle)
    ios_plist = (ROOT / "ios" / "Ilaria" / "Info.plist").read_text(encoding="utf-8")
    ios_yml = (ROOT / "ios" / "project.yml").read_text(encoding="utf-8")
    channel = json.loads((ROOT / "jarvis" / "channel.json").read_text(encoding="utf-8"))

    android_name = m_name.group(1) if m_name else ""
    android_code = int(m_code.group(1)) if m_code else 0
    plist_ver = re.search(r"CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", ios_plist)
    ios_ver = plist_ver.group(1) if plist_ver else ""
    yml_ver = re.search(r'MARKETING_VERSION:\s*"([^"]+)"', ios_yml)
    ios_mkt = yml_ver.group(1) if yml_ver else ""

    target = __version__
    if not _ok("python == channel", channel.get("version") == target, f"{channel.get('version')} vs {target}"):
        fails += 1
    if not _ok("android versionName", android_name == target, android_name):
        fails += 1
    if not _ok("android versionCode>=24", android_code >= 24, str(android_code)):
        fails += 1
    if not _ok("ios Info.plist", ios_ver == target, ios_ver):
        fails += 1
    if not _ok("ios project.yml", ios_mkt == target, ios_mkt):
        fails += 1
    return fails


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Also hit live HUD :8787")
    parser.add_argument("--host", default="http://127.0.0.1:8787")
    args = parser.parse_args()

    print("Ilaria integrity suite")
    fails = 0
    fails += test_version_alignment()
    fails += test_gk_clarity()
    fails += test_speakable_rejects_junk()
    fails += test_actions_routing()
    fails += test_brain_offline_clarity()
    if args.live:
        fails += test_live_hud(args.host.rstrip("/"))

    print(f"\nRESULT: {'PASS' if fails == 0 else f'FAIL ({fails})'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
