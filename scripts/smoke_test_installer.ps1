<#
.SYNOPSIS
    Smoke test del instalador: instala en silencio, arranca el backend empaquetado y
    comprueba que responde; después desinstala.

.DESCRIPTION
    Lo ejecuta release.yml antes de publicar: un instalador que no arranca no se publica.
    Con -InstallDir se omite instalar/desinstalar y se prueba una carpeta ya existente
    (por ejemplo frontend/src-tauri/target/release tras un build local).

.PARAMETER Installer
    Ruta del .exe NSIS a instalar (modo silencioso /S).

.PARAMETER InstallDir
    Carpeta de una app ya instalada o compilada (contiene backend\python\python.exe).
#>
param(
    [string]$Installer,
    [string]$InstallDir,
    [int]$Port = 18765,
    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$installedHere = $false

function Find-InstallDir {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Oroya Video"),
        (Join-Path $env:LOCALAPPDATA "Programs\Oroya Video"),
        (Join-Path $env:ProgramFiles "Oroya Video")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "backend\python\python.exe")) { return $candidate }
    }
    throw "Installed app not found in: $($candidates -join ', ')"
}

if (-not $InstallDir) {
    if (-not $Installer) { throw "Pass -Installer or -InstallDir" }
    Write-Host "Installing $Installer (silent)..."
    $setup = Start-Process $Installer -ArgumentList "/S" -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "Installer exited with $($setup.ExitCode)" }
    $InstallDir = Find-InstallDir
    $installedHere = $true
}

$backendDir = Join-Path $InstallDir "backend"
$python = Join-Path $backendDir "python\python.exe"
$dataDir = Join-Path ([IO.Path]::GetTempPath()) "oroya-smoke-$([guid]::NewGuid().ToString('N'))"
$logFile = Join-Path $dataDir "backend-smoke.log"
New-Item -ItemType Directory -Force $dataDir | Out-Null
Write-Host "Backend: $python (data: $dataDir)"

$env:OROYA_DATA_DIR = $dataDir
# Sin esto las exportaciones irían a la carpeta Vídeos real del equipo.
$env:EXPORTS_DIR = Join-Path $dataDir "exports"
$env:ENVIRONMENT = "production"
$env:DEBUG = "false"
$env:PYTHONNOUSERSITE = "1"
$backend = Start-Process $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port `
    -WorkingDirectory $backendDir -PassThru -NoNewWindow `
    -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"

try {
    $base = "http://127.0.0.1:$Port/api/v1"
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $health = $null
    while ((Get-Date) -lt $deadline -and -not $health) {
        if ($backend.HasExited) { throw "Backend exited during startup (code $($backend.ExitCode))" }
        try { $health = Invoke-RestMethod "$base/health" -TimeoutSec 3 } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $health) { throw "Backend did not answer /health within $StartupTimeoutSeconds s" }
    if ($health.service -ne "Oroya Video Backend") { throw "Unexpected service: $($health.service)" }
    Write-Host "health OK (version $($health.version))"

    $bootstrap = Invoke-RestMethod "$base/bootstrap" -TimeoutSec 30
    Write-Host "bootstrap OK (app $($bootstrap.app.version))"
    $null = Invoke-RestMethod "$base/projects" -TimeoutSec 30
    Write-Host "projects OK"
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
} catch {
    Write-Host "SMOKE TEST FAILED: $_" -ForegroundColor Red
    foreach ($file in @($logFile, "$logFile.err")) {
        if (Test-Path $file) { Write-Host "--- $file"; Get-Content $file -Tail 60 }
    }
    throw
} finally {
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    if ($installedHere) {
        $uninstaller = Join-Path $InstallDir "uninstall.exe"
        if (Test-Path $uninstaller) {
            Write-Host "Uninstalling..."
            Start-Process $uninstaller -ArgumentList "/S" -Wait | Out-Null
        }
    }
    Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue
}
