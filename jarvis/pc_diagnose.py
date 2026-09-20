"""Local PC performance diagnose — bottlenecks, not web search.

Windows-first (PowerShell CIM). No psutil / no arbitrary shell beyond allowlisted probes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

_PS_PROBE = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cpu = [int]((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average)
$ram = Get-CimInstance Win32_OperatingSystem
$total = [double]$ram.TotalVisibleMemorySize
$free = [double]$ram.FreePhysicalMemory
$ramPct = if ($total -gt 0) { [int](100 - (($free / $total) * 100)) } else { 0 }
$ramFreeGb = [math]::Round(($free * 1KB) / 1GB, 2)
$ramTotalGb = [math]::Round(($total * 1KB) / 1GB, 2)
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$diskFreeGb = if ($disk) { [math]::Round([double]$disk.FreeSpace / 1GB, 1) } else { 0 }
$diskTotalGb = if ($disk) { [math]::Round([double]$disk.Size / 1GB, 1) } else { 0 }
$diskPct = if ($diskTotalGb -gt 0) { [int](100 - (($diskFreeGb / $diskTotalGb) * 100)) } else { 0 }
$top = Get-Process | Sort-Object -Property WorkingSet64 -Descending |
  Select-Object -First 6 Name,
    @{N='ram_mb';E={[math]::Round($_.WorkingSet64/1MB,0)}},
    @{N='cpu';E={[math]::Round($_.CPU,1)}}
[pscustomobject]@{
  cpu_load_pct = $cpu
  ram_load_pct = $ramPct
  ram_available_gb = $ramFreeGb
  ram_total_gb = $ramTotalGb
  disk_c_free_gb = $diskFreeGb
  disk_c_total_gb = $diskTotalGb
  disk_c_used_pct = $diskPct
  top_ram = @($top | ForEach-Object { [pscustomobject]@{ name=$_.Name; ram_mb=$_.ram_mb; cpu=$_.cpu } })
} | ConvertTo-Json -Compress -Depth 4
"""


def diagnose_pc_performance() -> dict[str, Any]:
    """Snapshot CPU/RAM/disk + top memory hogs."""
    report: dict[str, Any] = {
        "cpu_load_pct": 0,
        "ram_load_pct": 0,
        "ram_available_gb": 0.0,
        "ram_total_gb": 0.0,
        "disk_c_free_gb": 0.0,
        "disk_c_total_gb": 0.0,
        "disk_c_used_pct": 0,
        "top_ram": [],
        "ok": False,
    }
    if os.name == "nt":
        raw = _powershell_json(_PS_PROBE)
        if isinstance(raw, dict):
            report.update({k: raw.get(k, report.get(k)) for k in report if k != "ok"})
            tops = raw.get("top_ram") or []
            if isinstance(tops, dict):
                tops = [tops]
            report["top_ram"] = [t for t in tops if isinstance(t, dict)][:6]
            report["ok"] = True
    if not report["ok"]:
        # Portable fallback: disk + RAM via ctypes helpers.
        try:
            from jarvis.self_healing import _ram_snapshot

            ram = _ram_snapshot()
            report["ram_load_pct"] = int(ram.get("ram_load_pct") or 0)
            report["ram_available_gb"] = float(ram.get("ram_available_gb") or 0)
        except Exception:
            pass
        try:
            usage = shutil.disk_usage("C:\\" if os.name == "nt" else "/")
            report["disk_c_free_gb"] = round(usage.free / (1024**3), 1)
            report["disk_c_total_gb"] = round(usage.total / (1024**3), 1)
            if usage.total:
                report["disk_c_used_pct"] = int(100 - (usage.free / usage.total) * 100)
            report["ok"] = True
        except OSError:
            pass
    report["advice"] = _advice(report)
    return report


def speakable_pc_diagnosis(report: dict[str, Any] | None = None) -> str:
    """One short spoken diagnosis for TTS / chat."""
    data = report or diagnose_pc_performance()
    bits: list[str] = []
    cpu = int(data.get("cpu_load_pct") or 0)
    ram = int(data.get("ram_load_pct") or 0)
    free_ram = float(data.get("ram_available_gb") or 0)
    free_disk = float(data.get("disk_c_free_gb") or 0)
    bits.append(f"CPU al {cpu}%, RAM al {ram}% ({free_ram:g} GB libres), disco C con {free_disk:g} GB libres.")
    tops = data.get("top_ram") or []
    names: list[str] = []
    for row in tops[:3]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        mb = row.get("ram_mb")
        if name:
            names.append(f"{name}" + (f" ({mb} MB)" if mb is not None else ""))
    if names:
        bits.append("Más memoria: " + ", ".join(names) + ".")
    advice = list(data.get("advice") or [])
    if advice:
        bits.append(" ".join(str(a) for a in advice[:3]))
    else:
        bits.append("Ahora no veo un cuello grave; si sigue lenta, mirá temperatura o si el disco es HDD.")
    return " ".join(bits)


def _advice(report: dict[str, Any]) -> list[str]:
    tips: list[str] = []
    cpu = int(report.get("cpu_load_pct") or 0)
    ram = int(report.get("ram_load_pct") or 0)
    free_ram = float(report.get("ram_available_gb") or 0)
    free_disk = float(report.get("disk_c_free_gb") or 0)
    tops = report.get("top_ram") or []

    if ram >= 90 or free_ram < 1.0:
        tips.append("Cuello principal: RAM llena. Cerrá pestañas/Chrome/Cursor o sumá memoria.")
    elif ram >= 80:
        tips.append("La RAM está justa; cerrá lo que no uses ayuda ya.")

    if cpu >= 85:
        tips.append("CPU muy alta: algún proceso está pegado; reiniciá ese programa o el PC.")
    elif cpu >= 70:
        tips.append("CPU cargada; evitá abrir más cosas pesadas un rato.")

    if free_disk < 8:
        tips.append("Disco C casi lleno: liberá espacio o mové archivos; eso frena mucho Windows.")
    elif free_disk < 20:
        tips.append("Queda poca libre en C; conviene limpiar actualizaciones/basura.")

    heavy = []
    for row in tops[:4]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").lower()
        mb = float(row.get("ram_mb") or 0)
        if mb >= 800 and name not in {"system", "memory compression", "registry"}:
            heavy.append(str(row.get("name")))
    if heavy and ram >= 75:
        tips.append("Sospechosos de comer RAM: " + ", ".join(heavy[:3]) + ".")

    if not tips:
        tips.append(
            "No hay un cuello obvio ahora. Si se siente lenta igual, puede ser disco HDD, "
            "térmica, o demasiados programas al inicio."
        )
    return tips


def _powershell_json(script: str) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    blob = (completed.stdout or "").strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


_PC_SLOW_RE = re.compile(
    r"\b("
    r"pc\s+lenta|computadora\s+lenta|compu\s+lenta|notebook\s+lenta|"
    r"anda\s+lenta|anda\s+lento|va\s+lenta|va\s+lento|"
    r"se\s+traba|se\s+cuelga|hanguea|lag(?:uea|gea)?|"
    r"cuello\s+de\s+botella|por\s+qu[eé].{0,40}lenta|"
    r"qu[eé]\s+(?:componente|pieza|hardware).{0,30}(?:cambiar|mejorar|actualizar)|"
    r"falta\s+(?:ram|memoria)|cpu\s+(?:al\s+)?(?:100|tope)|"
    r"diagn[oó]stic(?:o|a)?\s+(?:la\s+)?(?:pc|compu|rendimiento)|"
    r"rendimiento\s+(?:de\s+)?(?:la\s+)?pc"
    r")\b",
    re.I,
)


def looks_like_pc_slow(text: str) -> bool:
    return bool(_PC_SLOW_RE.search(text or ""))
