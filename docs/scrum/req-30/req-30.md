# REQ-030 - Build reproducible y CI

## Proyecto

Oroya Video

## Área

Build / CI / Instalador

## Objetivo

Que dos builds del mismo commit produzcan el mismo instalador, que todo lo que se descarga
esté verificado y que la CI detecte lo que antes solo aparecía al publicar.

## Implementación

- **Backend empaquetado**: `backend/requirements-core.lock` (uv, CPython 3.12 Windows, con
  hashes) instalado con `--require-hashes` por `build_installer.ps1`. La CI de Python 3.12
  instala el mismo lock antes de los tests; la de 3.14 sigue con versiones flotantes para
  detectar roturas futuras.
- **CPython**: 3.12.14 (python-build-standalone 20260924) con SHA-256 fijado; descargas con
  reintentos y sin barra de progreso (mucho más rápidas en PowerShell).
- **FFmpeg**: release permanente 9.0.2 "essentials" de gyan.dev (libx264 + AAC) con SHA-256,
  en lugar de la build rolling "latest" de BtbN (cambiaba a diario y se borra con el tiempo).
- **IA**: torch 2.12.1 / torchvision 0.27.1 (cu132 o CPU) y dependencias con versión exacta:
  la combinación probada con GPU. Hay ruedas cp312 para Windows en ambos índices.
- **CI** (`ci.yml`): versiones iguales en los 8 sitios (`scripts/check_versions.py`), job de
  Rust en Windows (`cargo fmt --check`, `cargo clippy -D warnings`), auditoría informativa
  (`pip-audit` del lock y `pnpm audit --prod`) y `dependabot.yml` mensual.
- **Release** (`release.yml`): la versión debe coincidir con el tag; smoke test del
  instalador (`scripts/smoke_test_installer.ps1`: instala en silencio, arranca el backend
  empaquetado, comprueba `/health`, `/bootstrap` y `/projects`, desinstala) antes de publicar;
  `SHA256SUMS.txt` junto al `.exe`.

## Verificación

- FFmpeg fijado descargado y verificado por el código del backend: hash correcto, incluye
  `libx264` y `aac`; test de rechazo por checksum distinto.
- Smoke test contra la build local de release: health, bootstrap y projects correctos.
- `check_versions.py` detecta un tag distinto de la versión.
