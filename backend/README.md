# Oroya Video Backend

Backend local de Oroya Video construido con FastAPI para el MVP desktop. La API oficial está congelada bajo `/api/v1` y mantiene `/api` como alias legacy mientras el frontend Angular/Tauri termina de integrarse.

## Requisitos

- Python 3.12+ (el instalador empaqueta CPython 3.12; en desarrollo se usa 3.14)
- Entorno virtual recomendado
- FFmpeg y FFprobe en `PATH`
- GPU NVIDIA, PyTorch y CUDA opcionales para Real-ESRGAN

## Instalación

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Opcional: dependencias IA para Real-ESRGAN
pip install -e .[ai]
```

## Variables de entorno

Consulta [`.env.example`](.env.example). Las variables principales del MVP son:

- `HOST`, `PORT`, `DEBUG`
- `STORAGE_PATH`, `DATABASE_URL`
- `CORS_ORIGINS`
- `FRAME_ENHANCER_ENGINE`, `AI_DEVICE`, `AI_ALLOW_CPU`, `AI_HALF_PRECISION`
- `JOB_RECOVERY_ENABLED`, `MARK_RUNNING_JOBS_INTERRUPTED_ON_STARTUP`
- `CLEANUP_TEMP_ON_SUCCESS`, `CLEANUP_KEEP_PREVIEW_FRAMES`, `CLEANUP_TEMP_OLDER_THAN_HOURS`
- `MAX_JOB_RETRIES`, `PROCESS_SHUTDOWN_TIMEOUT_SECONDS`
- `PREFLIGHT_MIN_FREE_DISK_GB`, `AUDIT_LOG_ENABLED`

## Habilitar Real-ESRGAN

Por defecto `FRAME_ENHANCER_ENGINE=mock` (la etapa de mejora solo copia frames,
para que máquinas sin torch no fallen el preflight). Para activar la IA real:

1. Instala el stack de IA desde el asistente (`/setup` → "Instalar runtime de IA") o con
   `POST /api/v1/system/ai/install` (progreso en `GET /api/v1/system/ai/install/progress`).
   Usa el mismo intérprete del backend; sin `ai_extra_site_dir` (desarrollo) instala en
   el entorno del backend. Elige torch CUDA (cu132) si detecta GPU NVIDIA, o CPU.
   No uses `pip install basicsr` directo: su sdist no compila en Python 3.13+ y trae
   `tb-nightly`. El instalador usa un wheel parcheado (`app/services/ai_wheel_builder.py`,
   `scripts/build_ai_wheels.py`). Al terminar, el motor pasa a `realesrgan` si estaba en `mock`.
2. Coloca los pesos en `storage/models/realesrgan/`:
   `realesrgan-x2.pth`, `realesrgan-x4.pth`, `realesrgan-general.pth`.
3. En tu `.env` local: `FRAME_ENHANCER_ENGINE=realesrgan` y reinicia.
4. Valida: `GET /api/v1/ai/runtime` (`available=true`), `POST /api/v1/models/refresh`
   (modelos `is_installed=true`) y `POST /api/v1/ai/realesrgan/dry-run`.

## Parámetros de mejora (denoise / sharpen / compression_cleanup)

Los valores de `enhancement_config` se aplican como filtros FFmpeg en la etapa
de codificación del video final:

- `denoise` (0-100) -> `hqdn3d`
- `sharpen` (0-100) -> `unsharp`
- `compression_cleanup` (bool) -> `deblock`

Limitación: los filtros afectan al video exportado, no a los frames del
preview antes/después (que muestran solo el upscaling del modelo).

## Pausa y reanudación

- La pausa funciona con jobs en cola y durante la etapa `enhancing_frames`
  (ambos motores). Durante la mejora, `POST /jobs/{id}/pause` marca
  `pause_requested` y el worker confirma el estado `paused` en el siguiente
  frame (puede tardar unos segundos con frames grandes).
- `POST /jobs/{id}/resume` re-encola el job; los frames ya mejorados se
  saltan automáticamente, así que reanudar no repite trabajo de GPU.

## Limpieza de temporales

Con `CLEANUP_TEMP_ON_SUCCESS=true` (default), al completar un job se eliminan
los videos intermedios (`encoded/`, `muxed/`) y se conservan solo los primeros
`CLEANUP_KEEP_PREVIEW_FRAMES` frames (default 24) en ambos directorios de
frames, para que el preview antes/después siga funcionando.

## Ejecutar

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

También está preparado:

```bash
python -m app
```

Swagger queda disponible en `http://127.0.0.1:8001/docs`.

## Calidad

```bash
python -m ruff check .
python -m pytest -q
```

## Export OpenAPI

Desde la raíz del repo:

```bash
python scripts/export_openapi.py
```

Salida esperada:

```text
shared/api/openapi.json
```

## Endpoints principales

API oficial:

- `GET /api/v1/health`
- `GET /api/v1/health/full`
- `GET /api/v1/bootstrap`
- `GET /api/v1/dashboard`
- `GET /api/v1/app-state`
- `GET /api/v1/queue`
- `GET /api/v1/settings`
- `PATCH /api/v1/settings`
- `POST /api/v1/videos/probe`
- `POST /api/v1/videos/import`
- `GET /api/v1/projects/{project_id}/workspace`
- `POST /api/v1/jobs`
- `POST /api/v1/jobs/{job_id}/start`
- `GET /api/v1/jobs/{job_id}/progress`
- `GET /api/v1/jobs/{job_id}/diagnostics`
- `GET /api/v1/jobs/{job_id}/pipeline`
- `POST /api/v1/jobs/{job_id}/retry`
- `DELETE /api/v1/jobs/{job_id}/temp`
- `GET /api/v1/system/storage/usage`
- `POST /api/v1/system/cleanup/temp`

Alias legacy:

- `/api/...`

## Flujo MVP

```text
Probe video
  -> Import video
  -> Create project
  -> Create job
  -> Start job
  -> Poll progress
  -> Preview frames
  -> Final export
```

## Pipeline Hardening And Cleanup

REQ-015 hace el pipeline seguro para uso desktop real:

- Recovery de jobs `queued/running/retrying/cleaning` a `interrupted` al reiniciar.
- Preflight por job antes de `start` y `resume`.
- Retry controlado para jobs `failed`, `cancelled` e `interrupted`.
- Cleanup por job y cleanup global de temporales.
- Storage usage detallado.
- Diagnostics por job y pipeline summary.
- Process registry para FFmpeg y Real-ESRGAN.
- Audit log en `storage/logs/audit.log`.

Endpoints de hardening:

- `GET /api/v1/jobs/interrupted`
- `GET /api/v1/jobs/{job_id}/preflight`
- `POST /api/v1/jobs/{job_id}/retry`
- `GET /api/v1/jobs/{job_id}/pipeline`
- `GET /api/v1/jobs/{job_id}/diagnostics`
- `DELETE /api/v1/jobs/{job_id}/temp`
- `GET /api/v1/system/storage/usage`
- `POST /api/v1/system/cleanup/temp`

## Frontend / Tauri

- El contrato oficial para Angular/Tauri es `/api/v1`.
- Tauri abre el file picker; el backend solo recibe rutas locales.
- CORS permitido por defecto:
  - `http://localhost:4200`
  - `http://127.0.0.1:4200`
  - `tauri://localhost`
  - `http://tauri.localhost` (origen por defecto de Tauri 2 en Windows)
  - `https://tauri.localhost`
- El frontend debe usar polling hasta que exista SSE/WebSocket.

Documentación complementaria:

- [Frontend integration](../docs/frontend-integration.md)
- [Backend API contract](../docs/backend-api-contract.md)
- [HTTP collection](../docs/http/oroya-video-api.http)

## Troubleshooting

- Si `start` devuelve `job_preflight_failed`, revisa `details.checks` y `details.errors`.
- Si Real-ESRGAN falla por VRAM, baja `REALESRGAN_TILE_SIZE` o usa un modelo más liviano.
- Si una ejecución queda cortada, revisa `GET /api/v1/jobs/interrupted` y usa `retry`.
- Si el storage crece demasiado, usa `DELETE /api/v1/jobs/{job_id}/temp` o `POST /api/v1/system/cleanup/temp`.
