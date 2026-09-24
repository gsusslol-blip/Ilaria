# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [
    ("jarvis/static", "jarvis/static"),
    (".env.example", "."),
]
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "pydantic",
    "multipart",
    "httpx",
    "openai",
    "ddgs",
    "primp",
    "lxml",
    "edge_tts",
    "PIL",
    "PIL.ImageGrab",
    "webview",
    "webview.platforms",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr",
    "clr_loader",
    "pythonnet",
    "tzdata",
    "certifi",
    "jarvis",
    "jarvis.runtime",
    "jarvis.hud",
    "jarvis.local",
    "jarvis.stt",
    "jarvis.tts",
    "jarvis.piper_tts",
    "jarvis.security",
    "jarvis.wake",
    "jarvis.telegram_bot",
    "comtypes",
    "pycaw",
    "pvporcupine",
    "pvrecorder",
]

for pkg in (
    "webview",
    "pythonnet",
    "clr_loader",
    "certifi",
    "tzdata",
    "primp",
    "edge_tts",
    "pycaw",
    "comtypes",
    "pvporcupine",
    "pvrecorder",
):
    try:
        extra_datas, extra_binaries, extra_hidden = collect_all(pkg)
    except Exception:
        continue
    datas += extra_datas
    binaries += extra_binaries
    hiddenimports += extra_hidden

datas += collect_data_files("lxml")

from pathlib import Path as _PackPath

_piper_dir = _PackPath("bin/piper")
if (_piper_dir / "piper.exe").is_file() or (_piper_dir / "piper").is_file():
    datas.append((str(_piper_dir), "bin/piper"))
_tts_dir = _PackPath("data/tts")
_voice_names = (
    "es_AR-daniela-high.onnx",
    "es_MX-ald-medium.onnx",
    "it_IT-paola-medium.onnx",
    "it_IT-riccardo-x_low.onnx",
    "en_US-lessac-medium.onnx",
)
if _tts_dir.is_dir():
    _voice_out = _PackPath("build/tts-pack")
    _voice_out.mkdir(parents=True, exist_ok=True)
    for _voice in _voice_names:
        for _suffix in ("", ".json"):
            _src = _tts_dir / (_voice + _suffix)
            if _src.is_file():
                (_voice_out / _src.name).write_bytes(_src.read_bytes())
    if any(_voice_out.glob("*.onnx")):
        datas.append((str(_voice_out), "data/tts"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ilaria",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Ilaria",
)
