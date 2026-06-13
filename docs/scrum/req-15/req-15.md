# REQ-015 - Pipeline Hardening, Recovery & Cleanup

## Proyecto

Oroya Video

## Área

Backend

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
```

El backend ya debe tener:

* Pipeline completo con `mock`.
* Pipeline completo con `realesrgan`.
* Jobs persistidos en SQLite.
* Logs de job.
* Progreso por etapas.
* Export final.
* Preview Before/After.
* Detección de sistema, FFmpeg, GPU, PyTorch y CUDA.
* Endpoints de videos, proyectos, modelos, jobs, previews y exports.

---

# Objetivo

Endurecer el pipeline completo de Oroya Video para que sea confiable durante uso real.

Este requerimiento debe mejorar:

1. Recuperación de jobs tras reiniciar el backend.
2. Limpieza segura de temporales.
3. Manejo consistente de errores.
4. Validaciones antes de procesar.
5. Control de storage.
6. Control de procesos externos.
7. Auditoría de logs.
8. Reintentos controlados.
9. Diagnóstico de jobs fallidos.
10. Estado global del pipeline.

El objetivo no es agregar nuevas features visuales, sino hacer que el backend sea robusto antes de conectarlo formalmente al frontend Angular/Tauri.

---

# Contexto

Hasta REQ-014, Oroya Video ya tiene un pipeline funcional:

```text
Import Video
    ↓
Create Project
    ↓
Create Job
    ↓
Extract Frames
    ↓
Enhance Frames
    ↓
Encode Video
    ↓
Mux Audio
    ↓
Final Export
    ↓
Preview Before/After
```

Pero un pipeline real puede fallar por muchas razones:

* La app se cierra durante procesamiento.
* FFmpeg queda corriendo.
* PyTorch falla por VRAM.
* El usuario borra el video original.
* Se llena el disco.
* El job queda en `running` tras reiniciar.
* Hay temporales enormes.
* Un export queda incompleto.
* Un proceso externo no termina.
* La UI necesita saber qué se puede reparar, limpiar o reintentar.

Este requerimiento prepara el backend para esos casos.

---

# Alcance de este requerimiento

Implementar:

1. Recuperación de jobs al iniciar backend.
2. Detección de jobs huérfanos.
3. Estado `interrupted`.
4. Reintento controlado de jobs fallidos/interrumpidos.
5. Limpieza de temporales por job.
6. Limpieza global de temporales antiguos.
7. Validación completa antes de iniciar job.
8. Preflight check por job.
9. Resumen de storage usado.
10. Resumen de pipeline por job.
11. Diagnóstico de fallos.
12. Control de procesos externos activos.
13. Normalización de errores.
14. Logs de auditoría.
15. Tests.
16. README actualizado.

No implementar:

* Batch processing.
* Procesamiento distribuido.
* Multi-GPU avanzado.
* UI.
* WebSocket.
* Marketplace.
* Descarga automática de modelos.
* Edición avanzada de video.
* Reintentos automáticos infinitos.

---

# Nuevos estados de job

Actualizar estados permitidos de `ProcessingJob`.

Estados existentes:

```text
pending
queued
running
paused
completed
failed
cancelled
```

Agregar:

```text
interrupted
retrying
cleaning
```

## Descripción

```text
interrupted  El backend se cerró o reinició mientras el job estaba queued/running.
retrying     El job está siendo preparado para un nuevo intento.
cleaning     El backend está limpiando recursos temporales del job.
```

---

# Nuevas etapas del pipeline

Etapas existentes:

```text
idle
queued
extracting_frames
enhancing_frames
encoding_video
muxing_audio
exporting
completed
failed
cancelled
```

Agregar:

```text
preflight
recovering
cleaning
interrupted
retrying
```

---

# Nuevos campos en ProcessingJob

Actualizar:

```text
app/db/models.py
```

Agregar a `ProcessingJob`:

```text
retry_count
max_retries
last_retry_at
interrupted_at
recovered_at
cleanup_started_at
cleanup_completed_at
cleanup_error_code
cleanup_error_message
preflight_started_at
preflight_completed_at
preflight_error_code
preflight_error_message
last_known_stage
last_known_progress_percent
worker_id
process_id
process_kind
process_started_at
process_ended_at
temp_size_bytes
original_frames_size_bytes
enhanced_frames_size_bytes
encoded_size_bytes
muxed_size_bytes
exports_size_bytes
```

Tipos sugeridos:

```text
retry_count                       Integer not null default 0
max_retries                       Integer not null default 1
last_retry_at                     DateTime nullable
interrupted_at                    DateTime nullable
recovered_at                      DateTime nullable

cleanup_started_at                DateTime nullable
cleanup_completed_at              DateTime nullable
cleanup_error_code                String nullable
cleanup_error_message             Text nullable

preflight_started_at              DateTime nullable
preflight_completed_at            DateTime nullable
preflight_error_code              String nullable
preflight_error_message           Text nullable

last_known_stage                  String nullable
last_known_progress_percent       Float nullable

worker_id                         String nullable
process_id                        Integer nullable
process_kind                      String nullable
process_started_at                DateTime nullable
process_ended_at                  DateTime nullable

temp_size_bytes                   Integer nullable
original_frames_size_bytes        Integer nullable
enhanced_frames_size_bytes        Integer nullable
encoded_size_bytes                Integer nullable
muxed_size_bytes                  Integer nullable
exports_size_bytes                Integer nullable
```

---

# Configuración nueva

Actualizar:

```text
app/core/config.py
```

Agregar:

```python
job_recovery_enabled: bool = True
mark_running_jobs_interrupted_on_startup: bool = True
cleanup_temp_on_success: bool = False
cleanup_temp_older_than_hours: int = 72
max_job_retries: int = 1
process_shutdown_timeout_seconds: int = 5
preflight_min_free_disk_gb: float = 10.0
audit_log_enabled: bool = True
```

Variables `.env`:

```env
JOB_RECOVERY_ENABLED=true
MARK_RUNNING_JOBS_INTERRUPTED_ON_STARTUP=true
CLEANUP_TEMP_ON_SUCCESS=false
CLEANUP_TEMP_OLDER_THAN_HOURS=72
MAX_JOB_RETRIES=1
PROCESS_SHUTDOWN_TIMEOUT_SECONDS=5
PREFLIGHT_MIN_FREE_DISK_GB=10
AUDIT_LOG_ENABLED=true
```

---

# Recuperación al iniciar backend

Crear servicio:

```text
app/services/job_recovery_service.py
```

Responsabilidades:

1. Buscar jobs en estados no finales.
2. Detectar jobs que quedaron `running` o `queued`.
3. Marcarlos como `interrupted`.
4. Guardar `interrupted_at`.
5. Guardar `last_known_stage`.
6. Guardar `last_known_progress_percent`.
7. Crear logs de job.
8. Exponer endpoint de recuperación.

Estados afectados al iniciar:

```text
queued
running
retrying
cleaning
```

Regla MVP:

```text
Todo job queued/running al iniciar backend se marca como interrupted.
```

No intentar continuar automáticamente todavía.

Motivo:

* Continuar un pipeline interrumpido requiere validar archivos parciales.
* Es más seguro pedir acción explícita del usuario.

---

# Servicio de recuperación

Funciones sugeridas:

```python
def recover_interrupted_jobs_on_startup(db: Session) -> int:
    ...


def mark_job_as_interrupted(db: Session, job: ProcessingJob) -> ProcessingJob:
    ...


def list_interrupted_jobs(db: Session) -> JobListResponse:
    ...


def recover_job_for_retry(db: Session, job_id: str) -> JobControlResponse:
    ...
```

---

# Reintento de jobs

Agregar endpoint para retry.

## POST /api/jobs/{job_id}/retry

Permite reintentar jobs en estados:

```text
failed
interrupted
cancelled
```

Reglas:

1. No permitir retry de `running`.
2. No permitir retry de `completed`.
3. Incrementar `retry_count`.
4. Validar que `retry_count < max_retries`.
5. Limpiar outputs parciales según estrategia.
6. Volver estado a `pending`.
7. Resetear progreso.
8. Mantener configuración original del job.
9. Crear log `Job prepared for retry`.

Request opcional:

```json
{
  "cleanup_before_retry": true,
  "reset_progress": true
}
```

Response:

```json
{
  "job": {
    "id": "job-id",
    "status": "pending",
    "current_stage": "idle",
    "retry_count": 1,
    "progress_percent": 0
  },
  "message": "Job prepared for retry."
}
```

---

# Estrategia de limpieza antes de retry

Si `cleanup_before_retry = true`:

Eliminar temporales del job:

```text
storage/temp/jobs/{job_id}/frames/original
storage/temp/jobs/{job_id}/frames/enhanced
storage/temp/jobs/{job_id}/encoded
storage/temp/jobs/{job_id}/muxed
```

No eliminar:

```text
storage/exports
video original
video importado
project
video asset
export records antiguos
```

---

# Preflight check por job

Crear servicio:

```text
app/services/job_preflight_service.py
```

El preflight valida si el job está listo antes de iniciar.

Debe revisar:

1. Project existe.
2. VideoAsset existe.
3. Archivo original existe.
4. FFmpeg disponible.
5. FFprobe disponible.
6. Modelo IA existe.
7. Modelo IA habilitado.
8. Si engine es `realesrgan`, modelo instalado.
9. Si engine es `realesrgan`, runtime IA disponible.
10. Si `AI_DEVICE=cuda`, CUDA disponible.
11. Storage temporal disponible.
12. Storage export disponible.
13. Permisos de escritura en storage.
14. El job no está en estado final.
15. El job no tiene otro proceso activo.

---

# Endpoint preflight

## GET /api/jobs/{job_id}/preflight

Response:

```json
{
  "job_id": "job-id",
  "ready": true,
  "checks": {
    "project_exists": true,
    "video_asset_exists": true,
    "video_file_exists": true,
    "ffmpeg_available": true,
    "ffprobe_available": true,
    "model_exists": true,
    "model_enabled": true,
    "model_installed": true,
    "ai_runtime_available": true,
    "storage_temp_writable": true,
    "storage_exports_writable": true,
    "free_disk_space_ok": true
  },
  "warnings": [],
  "errors": []
}
```

Si no está listo:

```json
{
  "job_id": "job-id",
  "ready": false,
  "checks": {
    "video_file_exists": false,
    "model_installed": false
  },
  "warnings": [
    "Selected model is not installed."
  ],
  "errors": [
    "Video file associated with this job is missing."
  ]
}
```

---

# Integración del preflight en start

Actualizar:

```text
POST /api/jobs/{job_id}/start
```

Antes de encolar:

1. Ejecutar preflight.
2. Si `ready = false`, responder `409`.
3. Guardar resultado de preflight en logs del job.
4. Si pasa, continuar con `queued`.

Error:

```json
{
  "error": "job_preflight_failed",
  "message": "Job preflight checks failed."
}
```

---

# Limpieza de temporales por job

Crear servicio:

```text
app/services/cleanup_service.py
```

Funciones sugeridas:

```python
def calculate_job_temp_size(job_id: str) -> JobStorageSummary:
    ...


def cleanup_job_temp_files(
    db: Session,
    job_id: str,
    include_original_frames: bool = True,
    include_enhanced_frames: bool = True,
    include_encoded: bool = True,
    include_muxed: bool = True,
) -> CleanupResponse:
    ...


def cleanup_old_temp_files(db: Session, older_than_hours: int) -> CleanupBatchResponse:
    ...


def cleanup_all_safe_temp_files(db: Session) -> CleanupBatchResponse:
    ...
```

---

# Endpoint de limpieza por job

## DELETE /api/jobs/{job_id}/temp

Request/query params:

```text
include_original_frames=true
include_enhanced_frames=true
include_encoded=true
include_muxed=true
```

Reglas:

* No permitir si job está `running`.
* No eliminar export final.
* No eliminar video original.
* No eliminar VideoAsset.
* No eliminar Project.
* Actualizar campos de tamaño.
* Crear log.

Response:

```json
{
  "deleted": true,
  "job_id": "job-id",
  "freed_bytes": 123456789,
  "deleted_paths": [
    "storage/temp/jobs/job-id/frames/original",
    "storage/temp/jobs/job-id/frames/enhanced",
    "storage/temp/jobs/job-id/encoded",
    "storage/temp/jobs/job-id/muxed"
  ],
  "warnings": []
}
```

---

# Limpieza global

## POST /api/system/cleanup/temp

Request:

```json
{
  "older_than_hours": 72,
  "dry_run": false
}
```

Response:

```json
{
  "dry_run": false,
  "deleted": true,
  "jobs_scanned": 10,
  "jobs_cleaned": 4,
  "freed_bytes": 987654321,
  "items": [
    {
      "job_id": "job-id",
      "freed_bytes": 123456789,
      "deleted_paths": []
    }
  ],
  "warnings": []
}
```

Si `dry_run = true`, no borra nada, solo reporta.

---

# Resumen de storage

Agregar endpoint:

## GET /api/system/storage/usage

Debe devolver:

```json
{
  "storage_path": "storage",
  "total_bytes": 512000000000,
  "free_bytes": 200000000000,
  "used_by_oroya_bytes": 12000000000,
  "breakdown": {
    "db_bytes": 2000000,
    "temp_bytes": 9000000000,
    "imports_bytes": 1000000000,
    "exports_bytes": 2000000000,
    "models_bytes": 500000000
  }
}
```

---

# Resumen de pipeline por job

Agregar endpoint:

## GET /api/jobs/{job_id}/pipeline

Response:

```json
{
  "job_id": "job-id",
  "status": "completed",
  "current_stage": "completed",
  "progress_percent": 100,
  "stages": [
    {
      "name": "preflight",
      "status": "completed",
      "started_at": "2026-06-13T12:00:00",
      "completed_at": "2026-06-13T12:00:02",
      "error_code": null
    },
    {
      "name": "extracting_frames",
      "status": "completed",
      "started_at": "2026-06-13T12:00:02",
      "completed_at": "2026-06-13T12:02:00",
      "error_code": null
    },
    {
      "name": "enhancing_frames",
      "status": "completed",
      "started_at": "2026-06-13T12:02:00",
      "completed_at": "2026-06-13T12:20:00",
      "error_code": null
    },
    {
      "name": "encoding_video",
      "status": "completed",
      "started_at": "2026-06-13T12:20:00",
      "completed_at": "2026-06-13T12:22:00",
      "error_code": null
    },
    {
      "name": "muxing_audio",
      "status": "completed",
      "started_at": "2026-06-13T12:22:00",
      "completed_at": "2026-06-13T12:22:30",
      "error_code": null
    },
    {
      "name": "exporting",
      "status": "completed",
      "started_at": "2026-06-13T12:22:30",
      "completed_at": "2026-06-13T12:23:00",
      "error_code": null
    }
  ],
  "output": {
    "export_id": "export-id",
    "final_export_path": "storage/exports/project/job/file.mp4"
  }
}
```

---

# Diagnóstico de fallo

Agregar endpoint:

## GET /api/jobs/{job_id}/diagnostics

Response:

```json
{
  "job_id": "job-id",
  "status": "failed",
  "current_stage": "enhancing_frames",
  "error_code": "cuda_out_of_memory",
  "error_message": "CUDA ran out of memory while processing frames.",
  "likely_causes": [
    "The selected model requires more VRAM than available.",
    "Tile size may be too large.",
    "Another application may be using GPU memory."
  ],
  "suggested_actions": [
    "Try using Real-ESRGAN x2 instead of x4.",
    "Enable tile processing.",
    "Close other GPU-heavy applications.",
    "Retry with CPU only if processing time is acceptable."
  ],
  "can_retry": true,
  "can_cleanup": true,
  "related_logs_url": "/api/jobs/job-id/logs"
}
```

---

# Normalización de errores

Crear catálogo central:

```text
app/core/error_codes.py
```

Debe incluir códigos estándar:

```text
video_file_missing
ffmpeg_not_available
ffprobe_not_available
ai_runtime_not_available
model_not_installed
cuda_not_available
cuda_out_of_memory
insufficient_temp_storage
insufficient_export_storage
frame_extraction_failed
frame_enhancement_failed
video_encoding_failed
audio_mux_failed
final_export_failed
job_cancelled
job_interrupted
job_preflight_failed
unknown_error
```

Cada error debe tener:

```text
code
message
http_status
category
recoverable
suggested_actions
```

Categorías:

```text
system
storage
video
ai
job
export
unknown
```

---

# Auditoría

Crear servicio:

```text
app/services/audit_log_service.py
```

Modelo opcional:

```text
AuditLog
```

Campos:

```text
id
event_type
entity_type
entity_id
message
metadata_json
created_at
```

Eventos mínimos:

```text
job_started
job_cancelled
job_failed
job_completed
job_retried
job_interrupted
job_cleaned
export_created
export_deleted
model_enabled
model_disabled
```

Si se decide no crear tabla, al menos registrar en `storage/logs/audit.log`.

Recomendación MVP:

```text
Crear archivo audit.log primero.
Tabla AuditLog puede quedar para futuro.
```

---

# Control de procesos externos

Crear módulo:

```text
app/services/process_registry_service.py
```

Objetivo:

* Registrar procesos FFmpeg activos.
* Registrar tipo de proceso.
* Asociar PID a job.
* Permitir cancelación más limpia.
* Limpiar referencias al terminar.

Funciones:

```python
def register_process(job_id: str, process_id: int, process_kind: str) -> None:
    ...


def unregister_process(job_id: str) -> None:
    ...


def get_process_for_job(job_id: str) -> ProcessInfo | None:
    ...


def terminate_process_for_job(job_id: str) -> bool:
    ...
```

Tipos de proceso:

```text
ffmpeg_extract
ffmpeg_encode
ffmpeg_mux
realesrgan
file_copy
```

---

# Endpoints nuevos

Agregar:

```text
GET    /api/jobs/interrupted
POST   /api/jobs/{job_id}/retry
GET    /api/jobs/{job_id}/preflight
GET    /api/jobs/{job_id}/pipeline
GET    /api/jobs/{job_id}/diagnostics
DELETE /api/jobs/{job_id}/temp
GET    /api/system/storage/usage
POST   /api/system/cleanup/temp
```

---

# Schemas nuevos

Crear:

```text
app/schemas/hardening_schema.py
```

Schemas mínimos:

```python
class JobPreflightResponse(BaseModel):
    job_id: str
    ready: bool
    checks: dict[str, bool]
    warnings: list[str]
    errors: list[str]


class JobRetryRequest(BaseModel):
    cleanup_before_retry: bool = True
    reset_progress: bool = True


class CleanupResponse(BaseModel):
    deleted: bool
    job_id: str
    freed_bytes: int
    deleted_paths: list[str]
    warnings: list[str]


class CleanupBatchRequest(BaseModel):
    older_than_hours: int = 72
    dry_run: bool = False


class CleanupBatchResponse(BaseModel):
    dry_run: bool
    deleted: bool
    jobs_scanned: int
    jobs_cleaned: int
    freed_bytes: int
    items: list[dict]
    warnings: list[str]


class StorageUsageResponse(BaseModel):
    storage_path: str
    total_bytes: int
    free_bytes: int
    used_by_oroya_bytes: int
    breakdown: dict[str, int]


class JobPipelineStage(BaseModel):
    name: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None


class JobPipelineResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    progress_percent: float
    stages: list[JobPipelineStage]
    output: dict[str, Any]


class JobDiagnosticsResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    error_code: str | None
    error_message: str | None
    likely_causes: list[str]
    suggested_actions: list[str]
    can_retry: bool
    can_cleanup: bool
    related_logs_url: str
```

---

# Errores nuevos

Agregar:

```python
class JobPreflightFailedError(OroyaVideoError):
    pass


class JobRetryNotAllowedError(OroyaVideoError):
    pass


class JobRecoveryFailedError(OroyaVideoError):
    pass


class JobCleanupFailedError(OroyaVideoError):
    pass


class ProcessTerminationFailedError(OroyaVideoError):
    pass
```

---

# Tests

Crear:

```text
tests/test_pipeline_hardening.py
```

Pruebas mínimas:

1. Al iniciar backend, jobs `running` se marcan como `interrupted`.
2. Jobs `queued` se marcan como `interrupted`.
3. Jobs `completed` no cambian.
4. Jobs `failed` no cambian.
5. `GET /api/jobs/interrupted` lista jobs interrumpidos.
6. `GET /api/jobs/{job_id}/preflight` devuelve ready true si todo está correcto.
7. Preflight falla si falta video original.
8. Preflight falla si falta FFmpeg.
9. Preflight falla si falta modelo Real-ESRGAN en engine realesrgan.
10. `POST /api/jobs/{job_id}/start` no encola si preflight falla.
11. `POST /api/jobs/{job_id}/retry` permite retry de failed.
12. Retry incrementa `retry_count`.
13. Retry no permite superar `max_retries`.
14. Retry no permite jobs running.
15. Retry no permite jobs completed.
16. Cleanup por job borra temporales indicados.
17. Cleanup por job no borra export final.
18. Cleanup por job no borra video original.
19. Cleanup global en dry_run no borra archivos.
20. Cleanup global real borra temporales antiguos.
21. Storage usage calcula breakdown.
22. Pipeline summary devuelve etapas.
23. Diagnostics devuelve acciones para `cuda_out_of_memory`.
24. Diagnostics devuelve acciones para `ffmpeg_not_available`.
25. Process registry registra proceso.
26. Process registry cancela proceso.
27. Job cancel usa process registry si existe proceso activo.
28. Audit log registra job_started.
29. Audit log registra job_completed.
30. Audit log registra job_failed.

---

# Actualizar README

Agregar sección:

```text
Pipeline hardening and cleanup
```

Documentar:

```text
GET    /api/jobs/interrupted
POST   /api/jobs/{job_id}/retry
GET    /api/jobs/{job_id}/preflight
GET    /api/jobs/{job_id}/pipeline
GET    /api/jobs/{job_id}/diagnostics
DELETE /api/jobs/{job_id}/temp
GET    /api/system/storage/usage
POST   /api/system/cleanup/temp
```

Agregar explicación:

```text
REQ-015 makes the pipeline safer for real desktop usage by detecting interrupted jobs, validating jobs before start, cleaning temporary files, and exposing diagnostics for failures.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Jobs running/queued se marcan como interrupted al iniciar backend.
* Existe preflight por job.
* `POST /api/jobs/{job_id}/start` ejecuta preflight antes de encolar.
* Existe retry controlado.
* Existe limpieza por job.
* Existe limpieza global de temporales.
* Existe storage usage.
* Existe pipeline summary.
* Existe diagnostics endpoint.
* Existe catálogo central de error codes.
* Existen suggested actions para errores comunes.
* Existe process registry.
* Cancelación usa process registry cuando aplica.
* Se registran logs de auditoría.
* Los exports finales nunca se borran por limpieza temporal.
* Los videos originales nunca se borran por limpieza temporal.
* Los tests pasan.
* README documenta los nuevos endpoints.

---

# Resultado esperado

Al finalizar este requerimiento, el backend debe ser capaz de:

1. Detectar jobs interrumpidos.
2. Evitar iniciar jobs inválidos.
3. Explicar por qué un job no puede ejecutarse.
4. Reintentar jobs fallidos de forma controlada.
5. Limpiar temporales pesados.
6. Reportar storage usado.
7. Diagnosticar errores frecuentes.
8. Cancelar procesos externos con mayor seguridad.
9. Mantener logs útiles para debugging.

Este requerimiento convierte el pipeline funcional en un pipeline más confiable para uso real.
