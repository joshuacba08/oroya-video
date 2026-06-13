# REQ-016 - API Contract Freeze & Frontend Integration Readiness

## Proyecto

Oroya Video

## Área

Backend / Frontend Integration

## Dependencia previa

Este requerimiento asume que ya existen y funcionan:

```text
REQ-001 - Backend Foundation
REQ-002 - System Info & Environment Detection
REQ-003 - Video Probe & Metadata Extraction
REQ-004 - Local Video Import & Storage Registration
REQ-005 - Projects CRUD & Workspace State
REQ-006 - AI Models Registry
REQ-007 - Processing Jobs CRUD & Queue Skeleton
REQ-008 - FFmpeg Frame Extraction Pipeline
REQ-009 - AI Frame Enhancement Pipeline
REQ-010 - Video Encoding from Enhanced Frames
REQ-011 - Audio Mux & Final Export
REQ-012 - Preview & Before/After Frame API
REQ-013 - Real-ESRGAN Integration Preparation
REQ-014 - Real-ESRGAN Batch Frame Enhancement
REQ-015 - Pipeline Hardening, Recovery & Cleanup
```

El backend ya debe tener:

* Pipeline completo.
* Real-ESRGAN funcional.
* Export final.
* Preview API.
* Hardening.
* Recovery.
* Cleanup.
* Diagnostics.
* Logs.
* System info.
* Models registry.
* Project management.
* Job management.

---

# Objetivo

Congelar el contrato API del backend MVP y dejarlo listo para integración con el frontend Angular/Tauri.

Este requerimiento debe convertir el backend en una API estable, documentada y consumible por la UI.

El objetivo es que Angular/Tauri pueda implementar:

* Dashboard.
* Importación de videos.
* Workspace de proyecto.
* Selector de modelos.
* Queue.
* Progreso.
* Preview Before/After.
* Exports.
* Settings.
* Diagnostics.
* System status.

sin que los endpoints cambien constantemente.

---

# Contexto

Hasta REQ-015, el backend ya tiene funcionalidad suficiente para el MVP.

Pero antes de conectar la UI seriamente, se necesita:

1. Normalizar respuestas.
2. Congelar nombres de endpoints.
3. Congelar schemas.
4. Documentar flujos.
5. Generar OpenAPI estable.
6. Preparar cliente TypeScript.
7. Revisar CORS/Tauri.
8. Definir eventos de progreso.
9. Definir convenciones de errores.
10. Preparar settings de desktop.
11. Preparar comandos para arranque local.

Este requerimiento no agrega procesamiento nuevo.
Es una fase de integración y estabilización.

---

# Alcance de este requerimiento

Implementar:

1. API versioning.
2. Respuestas estándar.
3. Error envelope estándar.
4. OpenAPI estable.
5. Tags y documentación por endpoint.
6. Health completo para frontend.
7. Endpoint bootstrap para UI.
8. Endpoint app state.
9. Endpoint dashboard summary.
10. Endpoint settings.
11. Contrato de progreso.
12. Contrato de queue.
13. Cliente TypeScript generado o exportable.
14. CORS definitivo para Tauri/Angular.
15. Documentación de flujos frontend.
16. Colección HTTP para pruebas.
17. Tests de contrato.
18. README final de backend MVP.

No implementar:

* UI Angular.
* Componentes Neural Angular.
* Tauri commands reales.
* Instalador desktop.
* Auto-update.
* Cloud sync.
* Auth/login.
* Multiusuario.

---

# Decisión MVP

La API se congelará bajo versión:

```text
/api/v1
```

Los endpoints actuales bajo `/api/...` pueden mantenerse temporalmente, pero el contrato final debe documentarse como:

```text
/api/v1/health
/api/v1/system
/api/v1/videos
/api/v1/projects
/api/v1/models
/api/v1/jobs
/api/v1/exports
/api/v1/preview
/api/v1/ai
/api/v1/settings
/api/v1/dashboard
```

Regla:

```text
/api/v1 será el contrato oficial para Angular/Tauri.
```

Opcional:

```text
Mantener aliases /api durante desarrollo, pero marcar como legacy.
```

---

# Principios del contrato API

1. Todas las respuestas JSON deben ser consistentes.
2. Todos los errores deben tener `error`, `message` y `details`.
3. Las fechas deben usar ISO 8601.
4. Los IDs deben ser strings UUID.
5. Las rutas de archivos deben devolverse como strings.
6. Las URLs API deben ser relativas cuando sea posible.
7. Los endpoints no deben exponer tracebacks.
8. Las operaciones destructivas deben ser explícitas.
9. Los endpoints pesados deben ser asíncronos vía jobs.
10. La UI debe poder reconstruir estado solo consultando API.

---

# Response envelope

Decisión MVP:

No envolver absolutamente todas las respuestas exitosas en `data`, porque los schemas ya existen y son claros.

Pero sí estandarizar errores y metadatos de paginación.

## List responses

Todas las listas deben usar:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

Actualizar listas existentes para incluir `limit` y `offset` si todavía no lo hacen.

Aplicar a:

```text
GET /api/v1/videos
GET /api/v1/projects
GET /api/v1/models
GET /api/v1/jobs
GET /api/v1/exports
GET /api/v1/jobs/{job_id}/logs
GET /api/v1/jobs/{job_id}/preview/frames
```

---

# Error envelope estándar

Todos los errores deben devolver:

```json
{
  "error": "error_code",
  "message": "Human readable message.",
  "details": {
    "field": "optional",
    "reason": "optional"
  },
  "request_id": "req_...",
  "timestamp": "2026-06-13T12:00:00Z"
}
```

Campos:

```text
error       Código estable para frontend.
message     Texto legible.
details     Objeto opcional.
request_id  ID único de request.
timestamp   Fecha/hora UTC.
```

---

# Request ID middleware

Crear middleware:

```text
app/middleware/request_id.py
```

Responsabilidades:

1. Generar `request_id`.
2. Aceptar `X-Request-ID` si viene del frontend.
3. Adjuntar `X-Request-ID` a response headers.
4. Incluir request_id en logs.
5. Incluir request_id en errores.

Header:

```text
X-Request-ID: req_abc123
```

---

# Logging middleware

Crear middleware:

```text
app/middleware/access_log.py
```

Registrar:

```text
method
path
status_code
duration_ms
request_id
```

No registrar bodies con rutas sensibles por defecto.

---

# API versioning

Actualizar router:

```text
app/api/router.py
```

Crear:

```text
app/api/v1/router.py
```

Estructura recomendada:

```text
app/
├── api/
│   ├── router.py
│   └── v1/
│       ├── __init__.py
│       ├── router.py
│       ├── routes_health.py
│       ├── routes_system.py
│       ├── routes_videos.py
│       ├── routes_projects.py
│       ├── routes_models.py
│       ├── routes_jobs.py
│       ├── routes_exports.py
│       ├── routes_preview.py
│       ├── routes_ai_runtime.py
│       ├── routes_settings.py
│       └── routes_dashboard.py
```

La app debe registrar:

```text
/api/v1
```

Opcional:

```text
/api
```

como alias temporal.

---

# Tags OpenAPI

Organizar endpoints con tags:

```text
Health
System
Settings
Dashboard
Videos
Projects
Models
Jobs
Preview
Exports
AI Runtime
Cleanup
Diagnostics
```

Cada endpoint debe tener:

* `summary`
* `description`
* response model
* errores principales documentados

---

# Endpoint bootstrap para frontend

Crear:

```text
GET /api/v1/bootstrap
```

Objetivo:

La UI llama este endpoint al arrancar para obtener todo lo necesario para pintar estado inicial.

Response:

```json
{
  "app": {
    "name": "Oroya Video Backend",
    "version": "0.1.0",
    "api_version": "v1",
    "environment": "development"
  },
  "system": {
    "ffmpeg_available": true,
    "ffprobe_available": true,
    "gpu_available": true,
    "ai_runtime_available": true
  },
  "settings": {
    "frame_enhancer_engine": "realesrgan",
    "ai_device": "auto",
    "storage_path": "storage"
  },
  "counts": {
    "projects": 3,
    "videos": 5,
    "jobs_running": 0,
    "jobs_interrupted": 1,
    "exports": 2,
    "models_installed": 1
  },
  "warnings": []
}
```

---

# Endpoint dashboard summary

Crear:

```text
GET /api/v1/dashboard
```

Response:

```json
{
  "recent_projects": [],
  "recent_exports": [],
  "active_jobs": [],
  "interrupted_jobs": [],
  "system_status": {
    "ready": true,
    "warnings": []
  },
  "storage": {
    "free_bytes": 200000000000,
    "used_by_oroya_bytes": 12000000000
  },
  "models": {
    "installed": 1,
    "missing": 2,
    "enabled": 3
  }
}
```

Este endpoint está pensado para la pantalla inicial de Oroya Video.

---

# Endpoint app state

Crear:

```text
GET /api/v1/app-state
```

Objetivo:

Permitir que la UI reconstruya estado global sin hacer demasiadas llamadas.

Response:

```json
{
  "backend": {
    "online": true,
    "version": "0.1.0",
    "api_version": "v1"
  },
  "queue": {
    "running": 0,
    "queued": 0,
    "pending": 0,
    "interrupted": 1
  },
  "system": {
    "ready": true,
    "gpu_available": true,
    "ai_runtime_available": true
  },
  "storage": {
    "free_bytes": 200000000000,
    "temp_bytes": 9000000000
  }
}
```

---

# Settings API

Crear:

```text
app/api/v1/routes_settings.py
app/services/settings_service.py
app/schemas/settings_schema.py
```

Objetivo:

Permitir que la UI lea y modifique configuración local.

## GET /api/v1/settings

Response:

```json
{
  "general": {
    "language": "en",
    "theme": "dark"
  },
  "processing": {
    "frame_enhancer_engine": "mock",
    "ai_device": "auto",
    "ai_allow_cpu": true,
    "ai_half_precision": true,
    "realesrgan_tile_size": 0,
    "realesrgan_tile_pad": 10,
    "realesrgan_pre_pad": 0
  },
  "storage": {
    "storage_path": "storage",
    "temp_path": "storage/temp",
    "exports_path": "storage/exports",
    "models_path": "storage/models"
  },
  "cleanup": {
    "cleanup_temp_on_success": false,
    "cleanup_temp_older_than_hours": 72
  }
}
```

## PATCH /api/v1/settings

Request:

```json
{
  "processing": {
    "frame_enhancer_engine": "realesrgan",
    "ai_device": "auto",
    "ai_half_precision": true
  }
}
```

Response:

```json
{
  "updated": true,
  "settings": {}
}
```

Reglas:

* Validar valores permitidos.
* No permitir cambiar rutas críticas mientras hay jobs running.
* Persistir settings en SQLite o archivo JSON local.
* Para MVP, archivo JSON local es aceptable:

```text
storage/settings.json
```

---

# Contrato de progreso para frontend

Congelar response de:

```text
GET /api/v1/jobs/{job_id}/progress
```

Debe incluir todo lo que la UI necesita:

```json
{
  "job_id": "job-id",
  "project_id": "project-id",
  "status": "running",
  "current_stage": "enhancing_frames",
  "progress_percent": 42.5,
  "stage_progress_percent": 50.0,
  "stage_label": "Enhancing frames",
  "frames_total": 3080,
  "frames_processed": 1540,
  "extracted_frames": 3080,
  "enhanced_frames": 1540,
  "estimated_time_seconds": 420,
  "elapsed_time_seconds": 300,
  "can_cancel": true,
  "can_pause": false,
  "can_retry": false,
  "can_cleanup": false,
  "error_code": null,
  "error_message": null,
  "preview_available": false,
  "export_available": false,
  "updated_at": "2026-06-13T12:00:00"
}
```

Campos obligatorios:

```text
job_id
project_id
status
current_stage
progress_percent
stage_progress_percent
stage_label
can_cancel
can_pause
can_retry
can_cleanup
preview_available
export_available
updated_at
```

---

# Contrato de queue para frontend

Crear o congelar:

```text
GET /api/v1/queue
```

Response:

```json
{
  "items": [
    {
      "job_id": "job-id",
      "project_id": "project-id",
      "project_name": "Anime Episode 01",
      "status": "running",
      "current_stage": "enhancing_frames",
      "progress_percent": 42.5,
      "model_slug": "realesrgan-x4",
      "created_at": "2026-06-13T12:00:00",
      "started_at": "2026-06-13T12:05:00"
    }
  ],
  "total": 1,
  "running": 1,
  "queued": 0,
  "pending": 0,
  "interrupted": 0
}
```

Este endpoint alimenta el widget/pantalla de cola en la UI.

---

# Contrato de project workspace

Congelar:

```text
GET /api/v1/projects/{project_id}/workspace
```

Response:

```json
{
  "project": {},
  "video": {},
  "latest_job": {},
  "latest_export": {},
  "models": {
    "selected": {},
    "available": []
  },
  "preview": {
    "available": true,
    "recommended": {
      "frame_index": 1540,
      "original_url": "/api/v1/jobs/job-id/preview/original/1540",
      "enhanced_url": "/api/v1/jobs/job-id/preview/enhanced/1540"
    }
  },
  "actions": {
    "can_create_job": true,
    "can_start_latest_job": false,
    "can_cancel_latest_job": false,
    "can_retry_latest_job": true,
    "can_export": true
  }
}
```

Objetivo:

La UI del workspace debe poder abrir un proyecto con una sola llamada principal.

---

# Contrato de imports para Tauri

La UI Tauri seleccionará archivos localmente.

El backend no abrirá file picker.

Flujo oficial:

```text
Tauri opens file picker
    ↓
Tauri gets absolute file path
    ↓
Angular sends path to backend
    ↓
Backend probes/imports video
```

Endpoints oficiales:

```text
POST /api/v1/videos/probe
POST /api/v1/videos/import
```

Documentar claramente que el backend recibe rutas locales.

---

# CORS definitivo

Actualizar CORS permitido:

```text
http://localhost:4200
http://127.0.0.1:4200
tauri://localhost
https://tauri.localhost
```

En desarrollo permitir configuración por `.env`:

```env
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200,tauri://localhost
```

---

# Backend startup contract para Tauri

Documentar:

```text
Tauri será responsable de iniciar el backend local.
```

El backend debe poder arrancar con:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

También preparar modo futuro:

```bash
python -m app
```

Crear si conviene:

```text
app/__main__.py
```

Para permitir:

```bash
python -m app
```

---

# Health checks finales

Congelar:

```text
GET /api/v1/health
GET /api/v1/health/full
```

## GET /api/v1/health

Response rápida:

```json
{
  "status": "ok",
  "service": "Oroya Video Backend",
  "version": "0.1.0"
}
```

## GET /api/v1/health/full

Response completa:

```json
{
  "status": "ok",
  "service": "Oroya Video Backend",
  "version": "0.1.0",
  "database": {
    "connected": true
  },
  "storage": {
    "writable": true,
    "free_bytes": 200000000000
  },
  "tools": {
    "ffmpeg": true,
    "ffprobe": true
  },
  "ai": {
    "runtime_available": true,
    "engine": "realesrgan"
  },
  "queue": {
    "worker_running": true
  },
  "warnings": []
}
```

---

# Cliente TypeScript

Generar o preparar export de OpenAPI.

Objetivo:

Angular pueda generar tipos.

Agregar script:

```bash
python scripts/export_openapi.py
```

Salida:

```text
shared/api/openapi.json
```

Opcional:

```bash
npx openapi-typescript shared/api/openapi.json -o shared/api/oroya-video-api.d.ts
```

Este requerimiento debe al menos generar:

```text
shared/api/openapi.json
```

Si el proyecto no tiene `shared/`, crearlo:

```text
shared/
└── api/
    └── openapi.json
```

---

# Colección HTTP

Crear:

```text
docs/http/oroya-video-api.http
```

Debe incluir ejemplos para:

```text
health
bootstrap
system
probe video
import video
create project
list models
create job
start job
progress
preview
exports
cleanup
diagnostics
settings
```

---

# Documentación de flujos frontend

Crear:

```text
docs/frontend-integration.md
```

Debe documentar:

1. Startup flow.
2. Dashboard flow.
3. Import video flow.
4. Create project flow.
5. Workspace load flow.
6. Create job flow.
7. Start job flow.
8. Poll progress flow.
9. Preview Before/After flow.
10. Export flow.
11. Cancel job flow.
12. Retry job flow.
13. Cleanup flow.
14. Settings flow.
15. Error handling flow.

---

# Polling recomendado

Hasta que exista WebSocket/SSE, la UI usará polling.

Reglas sugeridas:

```text
Job running: poll /jobs/{id}/progress cada 1s.
Job queued: poll cada 2s.
Job completed/failed/cancelled: detener polling.
Dashboard: refrescar cada 10s si hay jobs activos.
System status: refrescar cada 30s.
```

Documentar en `frontend-integration.md`.

---

# Actions contract

Para evitar que la UI adivine qué botones habilitar, responses principales deben incluir `actions`.

Aplicar al menos a:

```text
GET /api/v1/jobs/{job_id}
GET /api/v1/projects/{project_id}/workspace
GET /api/v1/jobs/{job_id}/progress
```

Ejemplo:

```json
{
  "actions": {
    "can_start": true,
    "can_cancel": false,
    "can_pause": false,
    "can_retry": false,
    "can_cleanup": true,
    "can_delete": true,
    "can_open_export": false
  }
}
```

---

# Normalización de timestamps

Todas las fechas deben serializarse en ISO 8601.

Recomendado:

```text
UTC internally
```

Ejemplo:

```json
{
  "created_at": "2026-06-13T12:00:00Z"
}
```

---

# Tests de contrato

Crear:

```text
tests/test_api_contract.py
```

Pruebas mínimas:

1. `/api/v1/health` responde schema esperado.
2. `/api/v1/health/full` responde schema esperado.
3. `/api/v1/bootstrap` responde app/system/settings/counts.
4. `/api/v1/dashboard` responde recent_projects/recent_exports/active_jobs.
5. Todas las listas incluyen `items`, `total`, `limit`, `offset`.
6. Errores incluyen `error`, `message`, `details`, `request_id`, `timestamp`.
7. Response header incluye `X-Request-ID`.
8. OpenAPI se genera correctamente.
9. OpenAPI incluye tags esperados.
10. `/api/v1/jobs/{id}/progress` incluye campos obligatorios del contrato.
11. `/api/v1/queue` responde contrato.
12. `/api/v1/projects/{id}/workspace` responde contrato.
13. `/api/v1/settings` responde settings.
14. `PATCH /api/v1/settings` valida valores.
15. CORS permite `localhost:4200`.
16. CORS permite `tauri://localhost`.
17. Endpoints legacy `/api` funcionan o redirigen si se decide mantenerlos.
18. No hay tracebacks en errores HTTP.
19. Todos los endpoints principales tienen response_model.
20. OpenAPI export escribe `shared/api/openapi.json`.

---

# README final backend MVP

Actualizar `backend/README.md` con:

1. Descripción del backend.
2. Requisitos.
3. Instalación.
4. Variables `.env`.
5. Cómo ejecutar.
6. Cómo correr tests.
7. Cómo generar OpenAPI.
8. Endpoints principales.
9. Flujo completo MVP.
10. Integración con Tauri.
11. Notas sobre Real-ESRGAN.
12. Troubleshooting.
13. Limpieza de storage.
14. Convenciones de errores.
15. Estado del MVP.

---

# Estructura de documentación final

Crear o actualizar:

```text
docs/
├── context.md
├── frontend-integration.md
├── backend-api-contract.md
├── http/
│   └── oroya-video-api.http
└── requirements/
    └── backend/
        ├── REQ-001-backend-foundation.md
        ├── ...
        └── REQ-016-api-contract-freeze-frontend-integration-readiness.md
```

---

# backend-api-contract.md

Debe incluir:

1. Base URL.
2. API version.
3. Error envelope.
4. Pagination format.
5. Job lifecycle.
6. Project workspace contract.
7. Preview contract.
8. Export contract.
9. Settings contract.
10. Queue contract.
11. Polling recommendations.
12. Tauri integration notes.

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* La API oficial vive bajo `/api/v1`.
* Existe `/api/v1/bootstrap`.
* Existe `/api/v1/dashboard`.
* Existe `/api/v1/app-state`.
* Existe `/api/v1/settings`.
* Existe `/api/v1/queue`.
* Existe `/api/v1/projects/{project_id}/workspace`.
* Existe `/api/v1/health/full`.
* Todas las listas tienen `items`, `total`, `limit`, `offset`.
* Todos los errores usan envelope estándar.
* Todos los errores incluyen `request_id`.
* Response headers incluyen `X-Request-ID`.
* OpenAPI está limpio y organizado por tags.
* `shared/api/openapi.json` se genera correctamente.
* Existe documentación frontend integration.
* Existe colección HTTP.
* Existe contrato de progreso congelado.
* Existe contrato de queue congelado.
* Existe contrato de workspace congelado.
* CORS está preparado para Angular/Tauri.
* Settings API funciona.
* Los tests de contrato pasan.
* README final está actualizado.
* El backend queda listo para conexión con UI.

---

# Resultado esperado

Al finalizar este requerimiento, el frontend Angular/Tauri debe poder construir la app usando contratos estables:

```text
Dashboard
    → GET /api/v1/bootstrap
    → GET /api/v1/dashboard

Import Video
    → POST /api/v1/videos/probe
    → POST /api/v1/videos/import

Project Workspace
    → GET /api/v1/projects/{project_id}/workspace

Models
    → GET /api/v1/models

Jobs
    → POST /api/v1/jobs
    → POST /api/v1/jobs/{job_id}/start
    → GET /api/v1/jobs/{job_id}/progress

Preview
    → GET /api/v1/jobs/{job_id}/preview/recommended

Exports
    → GET /api/v1/exports
    → POST /api/v1/exports/{export_id}/open-folder

Settings
    → GET /api/v1/settings
    → PATCH /api/v1/settings
```

Con este requerimiento, el backend MVP queda cerrado y listo para integración frontend.

A partir de aquí, el desarrollo debería pasar a:

```text
Angular 22 + Tauri 2 + Neural Angular
```

y no seguir agregando alcance backend salvo bugs, ajustes de contrato o necesidades reales detectadas durante integración.
