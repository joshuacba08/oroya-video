<#
.SYNOPSIS
    Release sin GitHub Actions: compila el instalador firmado en este equipo, lo prueba y,
    con -Publish, lo publica con el CLI de GitHub.

.DESCRIPTION
    Hace lo mismo que release.yml:
    1. versiones;
    2. build firmado;
    3. smoke test;
    4. SHA256SUMS y latest.json;
    5. GitHub Release con las notas de docs/releases/<tag>.md.
    Sirve cuando no quedan minutos de Actions.

    El smoke test usa -InstallDir sobre el build (target/release): nunca instala ni
    desinstala, así que no toca la app que el usuario tiene instalada.

    La clave del actualizador se lee de archivos locales y solo se pasa al build por
    variables de entorno de este proceso: nunca se imprime.

.PARAMETER Publish
    Crea el tag, lo sube y publica el release. Sin este switch solo compila y prueba.

.EXAMPLE
    ./scripts/release_local.ps1             # compilar y probar
    ./scripts/release_local.ps1 -Publish    # además, publicar
#>
param(
    [switch]$Publish,
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".tauri\oroya-updater.key"),
    [string]$PasswordPath = (Join-Path $env:USERPROFILE ".tauri\oroya-updater.password.txt"),
    [string]$Gh = "C:\Program Files\GitHub CLI\gh.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$bundleDir = Join-Path $repoRoot "frontend\src-tauri\target\release\bundle\nsis"
$python = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"

Push-Location $repoRoot
try {
    if (git status --porcelain) { throw "Hay cambios sin commit: el release debe salir de un commit." }

    & $python scripts/check_versions.py
    if ($LASTEXITCODE -ne 0) { throw "Las versiones no coinciden." }
    $version = (& $python -c "import sys; sys.path.insert(0, 'backend'); from app.version import __version__; print(__version__)").Trim()
    $tag = "v$version"
    $notes = Join-Path $repoRoot "docs\releases\$tag.md"
    if ($Publish -and -not (Test-Path $notes)) { throw "Faltan las notas: $notes" }

    if (-not (Test-Path $KeyPath) -or -not (Test-Path $PasswordPath)) {
        throw "No se encuentra la clave del actualizador en $KeyPath."
    }
    $env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content -Raw $KeyPath).Trim()
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = (Get-Content -Raw $PasswordPath).Trim()
    try {
        if (Test-Path $bundleDir) { Remove-Item -Recurse -Force $bundleDir }
        & ./scripts/build_installer.ps1
    } finally {
        Remove-Item Env:TAURI_SIGNING_PRIVATE_KEY, Env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD -ErrorAction SilentlyContinue
    }

    & ./scripts/smoke_test_installer.ps1 -InstallDir (Join-Path $repoRoot "frontend\src-tauri\target\release")

    $installer = Get-ChildItem "$bundleDir\*_x64-setup.exe" | Select-Object -First 1
    if (-not $installer -or -not (Test-Path "$($installer.FullName).sig")) {
        throw "No se generó el instalador firmado."
    }
    Get-ChildItem "$bundleDir\*.exe" | ForEach-Object {
        "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant())  $($_.Name)"
    } | Set-Content -Encoding ascii "$bundleDir\SHA256SUMS.txt"
    & $python scripts/make_update_manifest.py --tag $tag --bundle-dir $bundleDir
    if ($LASTEXITCODE -ne 0) { throw "No se pudo generar latest.json." }

    $assets = @($installer.FullName, "$($installer.FullName).sig", "$bundleDir\latest.json", "$bundleDir\SHA256SUMS.txt")
    Write-Host "Listo para publicar ${tag}:" -ForegroundColor Green
    $assets | ForEach-Object { Write-Host "  $_" }
    if (-not $Publish) { return }

    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    git push origin $branch
    git tag -a $tag -m "Oroya Video $version"
    git push origin $tag
    & $Gh release create $tag @assets --title "Oroya Video $version" --notes-file $notes --verify-tag
    if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
    Write-Host "Publicado: $tag" -ForegroundColor Green
} finally {
    Pop-Location
}
