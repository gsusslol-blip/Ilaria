# One folder people can unzip and run. No system Python.
# Does not copy .env, accounts, or data/ (secrets stay on this PC).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Root "dist\Ilaria-PC"
$PyVersion = "3.14.4"
$EmbedUrl = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $Out "python") | Out-Null

$embedZip = Join-Path $env:TEMP "python-$PyVersion-embed-amd64.zip"
Write-Host "[+] Python embebido $PyVersion"
if (-not (Test-Path $embedZip) -or (Get-Item $embedZip).Length -lt 1000000) {
    curl.exe -L --fail --retry 3 -o $embedZip $EmbedUrl
}
Expand-Archive -LiteralPath $embedZip -DestinationPath (Join-Path $Out "python") -Force

$pth = Get-ChildItem (Join-Path $Out "python") -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "No encontre python._pth" }
$lines = Get-Content -LiteralPath $pth.FullName
$kept = @()
foreach ($line in $lines) {
    if ($line.Trim() -eq "#import site") { continue }
    $kept += $line
}
$kept += "Lib\site-packages"
$kept += "import site"
Set-Content -LiteralPath $pth.FullName -Value $kept -Encoding ascii

$python = Join-Path $Out "python\python.exe"
$getPip = Join-Path $env:TEMP "get-pip.py"
curl.exe -L --fail --retry 3 -o $getPip $GetPipUrl
Write-Host "[+] pip"
& $python $getPip
if ($LASTEXITCODE -ne 0) { throw "get-pip fallo" }
Write-Host "[+] dependencias"
& $python -m pip install --upgrade pip setuptools wheel
& $python -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install fallo" }

$copyFiles = @("main.py", "requirements.txt", ".env.example", "firewall-ilaria.bat")
foreach ($name in $copyFiles) {
    $src = Join-Path $Root $name
    if (Test-Path $src) { Copy-Item $src (Join-Path $Out $name) }
}
Copy-Item (Join-Path $Root "jarvis") (Join-Path $Out "jarvis") -Recurse
Copy-Item (Join-Path $Root "tools") (Join-Path $Out "tools") -Recurse
Get-ChildItem $Out -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$piper = Join-Path $Root "bin\piper"
if (Test-Path (Join-Path $piper "piper.exe")) {
    Write-Host "[+] voz Piper"
    Copy-Item $piper (Join-Path $Out "bin\piper") -Recurse
    $espeak = Join-Path $Out "bin\piper\espeak-ng-data"
    if (Test-Path $espeak) {
        Get-ChildItem $espeak -Filter "*_dict" -File | Where-Object {
            $_.Name -notmatch '^(es|en|it)'
        } | Remove-Item -Force
    }
}
# Server runtime only. Bench, quantize and the CLI are not how Ilaria talks.
$llama = Join-Path $Root "bin\llama"
if (Test-Path (Join-Path $llama "llama-server.exe")) {
    $llamaDest = Join-Path $Out "bin\llama"
    New-Item -ItemType Directory -Force -Path $llamaDest | Out-Null
    Get-ChildItem $llama -File | Where-Object {
        $_.Name -match '^(llama-server|llama\.dll|llama-common|mtmd|ggml|libomp)'
    } | ForEach-Object { Copy-Item $_.FullName (Join-Path $llamaDest $_.Name) -Force }
}
# Same 1.5B Q4 the installer already ships. A smaller quant answers worse offline.
$brainName = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
$brainSrc = Join-Path $Root "models\$brainName"
if (Test-Path $brainSrc) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Out "models") | Out-Null
    Copy-Item $brainSrc (Join-Path $Out "models\$brainName") -Force
}
$tts = Join-Path $Root "data\tts"
$voices = @(
    "es_AR-daniela-high.onnx",
    "es_MX-ald-medium.onnx",
    "it_IT-paola-medium.onnx",
    "it_IT-riccardo-x_low.onnx",
    "en_US-lessac-medium.onnx"
)
if (Test-Path $tts) {
    $dest = Join-Path $Out "data\tts"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($name in $voices) {
        foreach ($suffix in @("", ".json")) {
            $src = Join-Path $tts ($name + $suffix)
            if (Test-Path $src) { Copy-Item $src (Join-Path $dest ($name + $suffix)) -Force }
        }
    }
}

@'
@echo off
title Ilaria
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HUD_HOST=0.0.0.0
set HUD_PORT=8787
set ILARIA_OPEN_BROWSER=1
set ILARIA_UPDATE_URL=https://github.com/gsusslol-blip/Ilaria/releases/latest/download/version.json
set ILARIA_AUTO_UPDATE=1
set LLM_PROVIDER=auto
set OLLAMA_BASE_URL=http://127.0.0.1:11435/v1
set OLLAMA_MODEL=qwen2.5-1.5b-instruct-q4_k_m.gguf
set STT_PROVIDER=faster-whisper
set FASTER_WHISPER_MODEL=base
set WHISPER_DEVICE=cpu
set HF_HOME=%~dp0data\hf
set HUGGINGFACE_HUB_CACHE=%~dp0data\hf\hub
if not exist .env copy .env.example .env
if exist "%~dp0bin\llama\llama-server.exe" if exist "%~dp0models\qwen2.5-1.5b-instruct-q4_k_m.gguf" (
  curl.exe -s -o nul -m 2 http://127.0.0.1:11435/v1/models
  if errorlevel 1 (
    start "Ilaria cerebro" /MIN "%~dp0bin\llama\llama-server.exe" -m "%~dp0models\qwen2.5-1.5b-instruct-q4_k_m.gguf" --host 127.0.0.1 --port 11435 -c 2048 -t 4
  )
)
echo Ilaria
echo http://localhost:8787
"%~dp0python\python.exe" "%~dp0main.py"
if errorlevel 1 pause
'@ | Set-Content -LiteralPath (Join-Path $Out "Ilaria.bat") -Encoding ascii

Write-Host "[+] Carpeta lista: $Out"
