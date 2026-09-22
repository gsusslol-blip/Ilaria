"""Local Windows how-to guides — spoken steps + optional Settings URI.

No web search for common PC tasks the owner already has on this machine.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WindowsGuide:
    key: str
    aliases: tuple[str, ...]
    title: str
    steps: tuple[str, ...]
    settings_uri: str = ""
    open_app: str = ""  # alias into Actions.open_app allowlist


_GUIDES: tuple[WindowsGuide, ...] = (
    WindowsGuide(
        key="uninstall",
        aliases=(
            "desinstal",
            "desinstalar",
            "sacar un programa",
            "borrar un programa",
            "quitar un programa",
            "uninstall",
            "apps y caracteristicas",
            "aplicaciones instaladas",
        ),
        title="Desinstalar un programa",
        steps=(
            "Abrí Configuración → Aplicaciones → Aplicaciones instaladas.",
            "Buscá el programa, tocá los tres puntos y elegí Desinstalar.",
            "Confirmá y reiniciá si Windows lo pide.",
        ),
        settings_uri="ms-settings:appsfeatures",
    ),
    WindowsGuide(
        key="hosts",
        aliases=(
            "archivo hosts",
            "archivo de hosts",
            "hosts file",
            "editar hosts",
            "donde esta el hosts",
            "dónde está el hosts",
        ),
        title="Archivo hosts",
        steps=(
            "La ruta es C:\\Windows\\System32\\drivers\\etc\\hosts.",
            "Abrí el Bloc de notas como administrador y abrí ese archivo desde ahí.",
            "Guardá solo si sabés qué línea estás tocando; un error puede romper la red.",
        ),
        open_app="notepad",
    ),
    WindowsGuide(
        key="wifi",
        aliases=(
            "wifi",
            "wi-fi",
            "red inalambrica",
            "red inalámbrica",
            "conectar wifi",
            "ajustes de wifi",
            "configurar wifi",
        ),
        title="Wi‑Fi",
        steps=(
            "Abrí Configuración → Red e Internet → Wi‑Fi.",
            "Elegí la red, conectate e ingresá la clave si pide.",
            "Si no aparece, activá Wi‑Fi y acercate al router.",
        ),
        settings_uri="ms-settings:network-wifi",
    ),
    WindowsGuide(
        key="bluetooth",
        aliases=("bluetooth", "blue tooth", "emparejar", "auriculares bluetooth"),
        title="Bluetooth",
        steps=(
            "Abrí Configuración → Bluetooth y dispositivos.",
            "Activá Bluetooth y tocá Agregar dispositivo.",
            "Poné el periférico en modo emparejamiento y seleccionarlo en la lista.",
        ),
        settings_uri="ms-settings:bluetooth",
    ),
    WindowsGuide(
        key="updates",
        aliases=(
            "actualizaciones",
            "windows update",
            "actualizar windows",
            "buscar actualizaciones",
        ),
        title="Actualizaciones de Windows",
        steps=(
            "Abrí Configuración → Windows Update.",
            "Tocá Buscar actualizaciones e instalá lo pendiente.",
            "Reiniciá cuando Windows lo pida para cerrar el ciclo.",
        ),
        settings_uri="ms-settings:windowsupdate",
    ),
    WindowsGuide(
        key="startup",
        aliases=(
            "inicio de windows",
            "programas al inicio",
            "arranque",
            "startup",
            "apps al iniciar",
            "inicio automático",
        ),
        title="Programas al iniciar",
        steps=(
            "Abrí el Administrador de tareas (Ctrl+Shift+Esc) → pestaña Aplicaciones de inicio.",
            "Deshabilitá lo que no necesités al arrancar.",
            "También podés ir a Configuración → Aplicaciones → Inicio.",
        ),
        settings_uri="ms-settings:startupapps",
        open_app="taskmgr",
    ),
    WindowsGuide(
        key="disk",
        aliases=(
            "liberar espacio",
            "disco lleno",
            "limpiar disco",
            "storage sense",
            "espacio en disco",
            "almacenamiento",
        ),
        title="Liberar espacio en disco",
        steps=(
            "Abrí Configuración → Sistema → Almacenamiento.",
            "Usá Recomendaciones de limpieza y vaciá la Papelera.",
            "Si hace falta, desinstalá apps grandes que no uses.",
        ),
        settings_uri="ms-settings:storagesense",
    ),
    WindowsGuide(
        key="sound",
        aliases=("sonido", "audio", "altavoces", "micrófono", "microfono", "salida de audio"),
        title="Sonido",
        steps=(
            "Abrí Configuración → Sistema → Sonido.",
            "Elegí el dispositivo de salida y de entrada correctos.",
            "Probá el volumen y el micrófono desde esa misma pantalla.",
        ),
        settings_uri="ms-settings:sound",
    ),
    WindowsGuide(
        key="display",
        aliases=("pantalla", "resolucion", "resolución", "brillo", "monitor", "display"),
        title="Pantalla",
        steps=(
            "Abrí Configuración → Sistema → Pantalla.",
            "Ajustá resolución, escala y brillo.",
            "Si hay varios monitores, elegí el principal y la disposición.",
        ),
        settings_uri="ms-settings:display",
    ),
    WindowsGuide(
        key="taskmgr",
        aliases=(
            "administrador de tareas",
            "task manager",
            "ver procesos",
            "que consume",
            "qué consume",
        ),
        title="Administrador de tareas",
        steps=(
            "Abrí el Administrador de tareas con Ctrl+Shift+Esc.",
            "Ordená por CPU o Memoria para ver qué pesa.",
            "Finalizá solo procesos que reconozcas si se trabaron.",
        ),
        open_app="taskmgr",
    ),
    WindowsGuide(
        key="firewall",
        aliases=("firewall", "cortafuegos", "defender firewall"),
        title="Firewall de Windows",
        steps=(
            "Abrí Seguridad de Windows → Firewall y protección de red.",
            "Revisá el perfil de red (privada/pública) activo.",
            "No desactives el firewall salvo diagnóstico puntual.",
        ),
        settings_uri="ms-settings:windowsdefender",
    ),
    WindowsGuide(
        key="proxy",
        aliases=("proxy", "vpn corporativa", "proxy de red"),
        title="Proxy",
        steps=(
            "Abrí Configuración → Red e Internet → Proxy.",
            "Revisá si hay proxy manual o script activo.",
            "Si la web falla raro, probá desactivar el proxy temporalmente.",
        ),
        settings_uri="ms-settings:network-proxy",
    ),
)


_HOWTO_HINT = re.compile(
    r"\b("
    r"c[oó]mo\s+(?:hago|hacer|puedo|desinstal|instal|abrir|encontrar|editar|configur)|"
    r"d[oó]nde\s+(?:est[aá]|queda|encuentro)|"
    r"como\s+(?:hago|hacer|puedo|desinstal)|"
    r"pasos?\s+para|"
    r"ayudame\s+a|ayud[aá]me\s+a"
    r")\b",
    re.I,
)

_PC_CONTEXT = re.compile(
    r"\b("
    r"windows|pc|computadora|ordenador|programa|aplicaci[oó]n|app|"
    r"hosts|wifi|wi[\-\s]?fi|bluetooth|actualizaci|inicio|"
    r"disco|almacenamiento|sonido|pantalla|firewall|proxy|"
    r"administrador\s+de\s+tareas|task\s*manager|desinstal"
    r")\b",
    re.I,
)


def _fold(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n")
    )


def match_windows_howto(text: str) -> WindowsGuide | None:
    """Return a guide when the user asks how to do a common Windows task."""
    raw = (text or "").strip()
    if not raw or len(raw) > 220:
        return None
    folded = _fold(raw)
    # Direct topic without "cómo" still OK when clearly a Windows topic phrase.
    hinted = bool(_HOWTO_HINT.search(raw))
    pcish = bool(_PC_CONTEXT.search(raw))
    if not hinted and not pcish:
        return None
    best: WindowsGuide | None = None
    best_len = 0
    for guide in _GUIDES:
        for alias in guide.aliases:
            a = _fold(alias)
            if a and a in folded and len(a) > best_len:
                best = guide
                best_len = len(a)
    if best is None:
        return None
    # Require how-to framing OR a strong alias (≥10 chars) to avoid stealing "abrí wifi".
    if hinted or best_len >= 10 or (pcish and "como" in folded):
        return best
    return None


def speakable_windows_howto(guide: WindowsGuide, *, opened: str = "") -> str:
    steps = " ".join(f"{i}) {s}" for i, s in enumerate(guide.steps, 1))
    head = f"{guide.title}: {steps}"
    if opened:
        return f"{opened} {head}".strip()
    return head


def open_settings_uri(uri: str) -> str:
    """Launch an ms-settings: URI on Windows. No-op elsewhere."""
    target = (uri or "").strip()
    if not target.startswith("ms-settings:"):
        return ""
    if os.name != "nt":
        return ""
    try:
        os.startfile(target)  # type: ignore[attr-defined]
        return "Abrí Configuración de Windows."
    except OSError:
        return ""


def run_windows_howto(text: str, *, open_app_fn: Any | None = None) -> str | None:
    """Match + optionally open Settings/app, return speakable guide."""
    guide = match_windows_howto(text)
    if guide is None:
        return None
    opened_bits: list[str] = []
    if guide.settings_uri:
        note = open_settings_uri(guide.settings_uri)
        if note:
            opened_bits.append(note)
    if guide.open_app and callable(open_app_fn):
        try:
            msg = str(open_app_fn(guide.open_app) or "").strip()
            if msg:
                opened_bits.append(msg if msg.endswith(".") else msg + ".")
        except Exception:
            pass
    return speakable_windows_howto(guide, opened=" ".join(opened_bits))
