# Oroya Video Backend

Backend local de Oroya Video construido con FastAPI para el MVP desktop. La API oficial está congelada bajo `/api/v1` y mantiene `/api` como alias legacy mientras el frontend Angular/Tauri termina de integrarse.

## Requisitos

- Python 3.13+
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
- `CLEANUP_TEMP_ON_SUCCESS`, `CLEANUP_TEMP_OLDER_THAN_HOURS`
- `MAX_JOB_RETRIES`, `PROCESS_SHUTDOWN_TIMEOUT_SECONDS`
- `PREFLIGHT_MIN_FREE_DISK_GB`, `AUDIT_LOG_ENABLED`

## Ejecutar

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

También está preparado:

```bash
python -m app
```

Swagger queda disponible en `http://127.0.0.1:8000/docs`.

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
