<#
.SYNOPSIS
    Construye el instalador NSIS de Oroya Video para Windows.

.DESCRIPTION
    1. Descarga (con caché) un runtime CPython portable (python-build-standalone).
    2. Instala las dependencias core del backend en ese runtime.
    3. Copia el código del backend a frontend/src-tauri/resources/backend/.
    4. Construye el wheel parcheado de basicsr (instalación de IA desde el asistente).
    5. Ejecuta pnpm test + pnpm tauri build (NSIS).

    El instalador resultante arranca el backend automáticamente (sidecar) y
    guarda todos los datos de usuario en %LOCALAPPDATA%\dev.oroya.video.

.PARAMETER PythonStandaloneUrl
    URL del asset install_only de python-build-standalone (CPython 3.12 win64).

.PARAMETER SkipFrontendTests
    Omite pnpm test antes del build.
#>
param(
    [string]$PythonStandaloneUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/20241206/cpython-3.12.8+20241206-x86_64-pc-windows-msvc-install_only.tar.gz",
    [switch]$SkipFrontendTests
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$buildCache = Join-Path $repoRoot "build"
$resourcesDir = Join-Path $repoRoot "frontend\src-tauri\resources\backend"
$pythonDir = Join-Path $resourcesDir "python"
$appDir = Join-Path $resourcesDir "app"

Write-Host "== Oroya Video installer build ==" -ForegroundColor Cyan

# 1. Runtime CPython portable (cacheado en build/)
New-Item -ItemType Directory -Force $buildCache | Out-Null
$archiveName = Split-Path -Leaf ([uri]$PythonStandaloneUrl).LocalPath
$archivePath = Join-Path $buildCache $archiveName

if (-not (Test-Path $archivePath)) {
    Write-Host "Descargando CPython portable..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $PythonStandaloneUrl -OutFile $archivePath
} else {
    Write-Host "CPython portable en cache: $archivePath"
}

if (Test-Path $resourcesDir) {
    Get-ChildItem $resourcesDir -Exclude "README.txt" | Remove-Item -Recurse -Force -Confirm:$false
}
New-Item -ItemType Directory -Force $resourcesDir | Out-Null

Write-Host "Extrayendo runtime..." -ForegroundColor Yellow
$extractDir = Join-Path $buildCache "python-extract"
if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory -Force $extractDir | Out-Null
tar -xzf $archivePath -C $extractDir
Move-Item (Join-Path $extractDir "python") $pythonDir

# 2. Dependencias core del backend
Write-Host "Instalando dependencias core del backend..." -ForegroundColor Yellow
& (Join-Path $pythonDir "python.exe") -m pip install --no-warn-script-location `
    -r (Join-Path $repoRoot "backend\requirements-core.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# 3. Código del backend (sin tests, storage ni cachés)
Write-Host "Copiando backend..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force $appDir | Out-Null
robocopy (Join-Path $repoRoot "backend\app") $appDir /E /XD __pycache__ | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with $LASTEXITCODE" }

# 4. Wheel parcheado de basicsr para la instalación de IA desde el asistente
Write-Host "Construyendo wheel de basicsr..." -ForegroundColor Yellow
& (Join-Path $pythonDir "python.exe") (Join-Path $repoRoot "scripts\build_ai_wheels.py") `
    (Join-Path $resourcesDir "wheels")
if ($LASTEXITCODE -ne 0) { throw "basicsr wheel build failed" }

# 5. Build del frontend + instalador NSIS
Push-Location (Join-Path $repoRoot "frontend")
try {
    if (-not $SkipFrontendTests) {
        Write-Host "Ejecutando tests del frontend..." -ForegroundColor Yellow
        pnpm test --watch=false
        if ($LASTEXITCODE -ne 0) { throw "pnpm test failed" }
    }

    Write-Host "Construyendo instalador (pnpm tauri build)..." -ForegroundColor Yellow
    pnpm tauri build
    if ($LASTEXITCODE -ne 0) { throw "tauri build failed" }
} finally {
    Pop-Location
}

$bundleDir = Join-Path $repoRoot "frontend\src-tauri\target\release\bundle\nsis"
Write-Host "`n== Instalador generado ==" -ForegroundColor Green
Get-ChildItem $bundleDir -Filter *.exe | ForEach-Object { Write-Host "  $($_.FullName)" }
