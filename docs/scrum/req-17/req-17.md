# REQ-017 - Release Readiness & One-Click AI Install

## Proyecto

Oroya Video

## Área

Release / Instalador / Backend IA

## Dependencia previa

REQ-001 a REQ-016 y la estabilización de la rama `release/0.2` (CI en GitHub Actions).

## Objetivo

Dejar la app lista para publicar una v0.2 instalable desde GitHub: build de producción
correcto, versión única, CSP en Tauri, instalación del stack de IA con un clic desde el
asistente y publicación automática del instalador.

## Alcance implementado

### Versión y runtime

- Versión única `0.2.0` en `backend/app/version.py`; `Settings.app_version` la expone y ya
  no se puede sobrescribir por `.env`. Alineados `pyproject.toml`, `tauri.conf.json`,
  `Cargo.toml`/`Cargo.lock`, `frontend/package.json` y `frontend/src/app/core/app-version.ts`.
- `requires-python = ">=3.12"` (el instalador empaqueta CPython 3.12.8). La CI prueba 3.12 y 3.14.

### Build de producción y CSP

- `environment.prod.ts` (`production: true`) vía `fileReplacements` en `angular.json`.
- `inlineCritical: false`: Angular dejaba un handler `onload` inline incompatible con CSP.
- CSP en `tauri.conf.json`: `script-src 'self'`; imágenes/video/conexiones solo hacia el
  backend local `http://127.0.0.1:8001` e IPC de Tauri; `style-src` permite inline porque
  Angular inyecta los estilos de componentes en runtime.

### Instalación de IA con un clic

- `POST /api/v1/system/ai/install` y `GET /api/v1/system/ai/install/progress`
  (`app/services/ai_install_service.py`).
- Instala con el intérprete del backend en `ai_extra_site_dir` (pip `--target`), con
  `PYTHONPATH` apuntando al destino para que pip vea lo ya instalado:
  1. `torch`, `torchvision` desde el índice de PyTorch (cu132 si hay GPU NVIDIA, CPU si no).
  2. `basicsr` (wheel parcheado) y `realesrgan==0.3.0` con `--no-deps`.
  3. Dependencias puras (sin `tb-nightly`), incluido `setuptools` (shim de `distutils`).
- Al terminar registra la carpeta sin reiniciar (`ensure_ai_extra_site_dir`), verifica los
  imports y, si el motor era `mock`, lo cambia y persiste a `realesrgan`.
- Setup muestra paso, progreso y última línea de pip; la instalación manual queda como opción.

### basicsr

El sdist de basicsr 1.4.2 no instala en entornos modernos: `setup_requires` con torch,
`get_version()` con `exec()` sobre `locals()` (roto desde Python 3.13, PEP 667),
dependencia `tb-nightly` e import de `torchvision.transforms.functional_tensor` (eliminado
en torchvision 0.17). `app/services/ai_wheel_builder.py` descarga el sdist oficial
(SHA256 fijado), parchea esos puntos y construye un wheel puro. `scripts/build_installer.ps1`
lo empaqueta en `resources/backend/wheels`; si falta, el endpoint lo construye bajo demanda.
Además, `ensure_torchvision_compat()` crea el alias `functional_tensor` en runtime para
entornos con un basicsr sin parchear.

### Publicación

- `.github/workflows/release.yml`: en tags `v*` construye el instalador NSIS en
  `windows-latest` y lo adjunta al GitHub Release; con `workflow_dispatch` lo deja como artefacto.

## Verificación

- Backend: 197 tests en Python 3.12.8 (runtime del instalador) y 3.14; ruff limpio.
- Frontend: vitest y `ng build` de producción.
- CSP: build de producción servida con la misma política; sin violaciones, previews e
  imágenes del backend y video de exports cargan.
- Instalación real en Python 3.12 desde carpeta vacía (torch CPU): completada en ~2 min,
  imports correctos e inferencia Real-ESRGAN x2 ejecutada.
- UI de instalación en backend 3.12 limpio: progreso visible descargando wheels cu132/cp312.

## Pendiente

- Probar el instalador NSIS completo en una máquina Windows limpia (primer `release.yml`).
