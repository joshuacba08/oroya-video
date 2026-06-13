# REQ-007 - Processing Jobs CRUD & Queue Skeleton

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
```

El backend ya debe tener:

* FastAPI funcional.
* SQLite inicializado.
* Sistema de logging.
* Sistema de paths.
* CRUD de videos.
* CRUD de proyectos.
* Registro local de modelos IA.
* Validación básica de modelos en proyectos.
* Configuración de mejora y exportación guardada en proyectos.

---

# Objetivo

Implementar la estructura inicial de jobs de procesamiento para Oroya Video.

Un `ProcessingJob` representa una tarea de mejora de video asociada a un proyecto.

Este requerimiento debe permitir crear, listar, consultar, iniciar, pausar, reanudar, cancelar y registrar progreso de jobs.

No debe implementar todavía procesamiento real de video, extracción de frames, FFmpeg, Real-ESRGAN ni exportación final.

El objetivo es crear la base de control, estados, progreso y cola interna para que el siguiente requerimiento pueda conectar el pipeline real.

---

# Contexto

Oroya Video procesará videos mediante un pipeline pesado:

```text
Video
  ↓
Probe Metadata
  ↓
Extract Frames
  ↓
AI Enhancement
  ↓
Encode Video
  ↓
Mux Audio
  ↓
Export
```

Antes de implementar ese pipeline, el backend necesita una entidad persistente que represente cada ejecución.

Un proyecto puede tener varios jobs a lo largo del tiempo, por ejemplo:

```text
Test Real-ESRGAN x2
Test Real-ESRGAN x4
Final Export 4K
```

Cada job debe guardar:

* Proyecto asociado.
* Video asociado.
* Modelo seleccionado.
* Configuración usada.
* Estado actual.
* Progreso.
* Etapa actual.
* Frames totales.
* Frames procesados.
* Tiempo estimado.
* Logs.
* Error, si existe.
* Ruta de salida futura.

---

# Decisión MVP

La cola inicial será simple y local.

No usar todavía:

```text
Celery
Redis
RQ
RabbitMQ
```

Para el MVP se usará una estructura interna basada en:

```text
asyncio.Queue
worker interno
estado persistido en SQLite
```

En este requerimiento, el worker no ejecutará procesamiento real.

Solo debe simular la entrada a cola y preparar la arquitectura para que futuros pipelines puedan conectarse.

---

# Alcance de este requerimiento

Implementar:

1. Modelo ORM `ProcessingJob`.
2. Modelo ORM opcional `JobLog`.
3. Repositorio de jobs.
4. Servicio de jobs.
5. Cola interna básica.
6. Worker skeleton.
7. Endpoints CRUD/control de jobs.
8. Estados de job.
9. Progreso persistente.
10. Logs básicos de job.
11. Endpoint de progreso.
12. Validación de proyecto y modelo.
13. Tests.
14. Actualización de README.

No implementar todavía:

* Extracción real de frames.
* Procesamiento con FFmpeg.
* Procesamiento con PyTorch.
* Real-ESRGAN real.
* Exportación de video.
* WebSocket.
* Server-Sent Events.
* Batch processing.
* Reintentos automáticos complejos.
* Procesamiento paralelo real.

---

# Conceptos nuevos

## ProcessingJob

Representa una ejecución de procesamiento.

Un job pertenece a un proyecto y usa:

* Un video asset.
* Un modelo IA.
* Una configuración de mejora.
* Una configuración de exportación.

---

## JobLog

Representa eventos internos de un job.

Ejemplos:

```text
Job created
Job queued
Job started
Job paused
Job cancelled
Job failed
```

---

## Job Progress

Representa el avance actual del job.

Debe incluir:

```text
progress_percent
current_stage
frames_total
frames_processed
estimated_time_seconds
elapsed_time_seconds
```

---

# Estados del Job

Estados permitidos:

```text
pending
queued
running
paused
completed
failed
cancelled
```

Descripción:

```text
pending     El job fue creado pero aún no ha entrado a la cola.
queued      El job fue enviado a la cola.
running     El worker tomó el job.
paused      El job fue pausado.
completed   El job terminó correctamente.
failed      El job falló.
cancelled   El usuario canceló el job.
```

---

# Etapas del Pipeline

Aunque todavía no se ejecuten, se deben preparar las etapas:

```text
idle
probing
extracting_frames
enhancing_frames
encoding_video
muxing_audio
exporting
completed
failed
cancelled
```

En este requerimiento, la etapa normalmente será:

```text
idle
```

o durante simulación:

```text
queued
running
```

---

# Modelo ORM

Actualizar:

```text
app/db/models.py
```

Agregar:

```python
class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
```

Campos requeridos:

```text
id
project_id
video_asset_id
ai_model_id
ai_model_slug
status
current_stage
progress_percent
frames_total
frames_processed
estimated_time_seconds
elapsed_time_seconds
enhancement_config_json
export_config_json
output_path
error_code
error_message
created_at
updated_at
started_at
completed_at
cancelled_at
```

Tipos sugeridos:

```text
id                         String primary key UUID
project_id                  String ForeignKey projects.id not null
video_asset_id              String ForeignKey video_assets.id not null
ai_model_id                 String ForeignKey ai_models.id nullable
ai_model_slug               String not null
status                     String not null
current_stage              String not null
progress_percent            Float not null default 0
frames_total                Integer nullable
frames_processed            Integer not null default 0
estimated_time_seconds      Integer nullable
elapsed_time_seconds        Integer nullable
enhancement_config_json     Text not null
export_config_json          Text not null
output_path                 String nullable
error_code                  String nullable
error_message               Text nullable
created_at                  DateTime not null
updated_at                  DateTime not null
started_at                  DateTime nullable
completed_at                DateTime nullable
cancelled_at                DateTime nullable
```

Relaciones sugeridas:

```python
project = relationship("Project")
video_asset = relationship("VideoAsset")
ai_model = relationship("AIModel")
logs = relationship("JobLog", cascade="all, delete-orphan")
```

---

# Modelo ORM JobLog

Agregar:

```python
class JobLog(Base):
    __tablename__ = "job_logs"
```

Campos:

```text
id
job_id
level
message
stage
created_at
```

Tipos:

```text
id          String primary key UUID
job_id      String ForeignKey processing_jobs.id not null
level       String not null
message     Text not null
stage       String nullable
created_at  DateTime not null
```

Niveles permitidos:

```text
debug
info
warning
error
```

---

# Schemas

Crear:

```text
app/schemas/job_schema.py
```

## JobCreateRequest

```python
class JobCreateRequest(BaseModel):
    project_id: str
    model_id: str | None = None
    enhancement_config: dict[str, Any] | None = None
    export_config: dict[str, Any] | None = None
```

Reglas:

* Si `model_id` no se envía, usar `project.enhancement_config.model_id`.
* Si `enhancement_config` no se envía, usar la configuración del proyecto.
* Si `export_config` no se envía, usar la configuración del proyecto.

---

## JobResponse

```python
class JobResponse(BaseModel):
    id: str
    project_id: str
    video_asset_id: str
    ai_model_id: str | None
    ai_model_slug: str
    status: str
    current_stage: str
    progress_percent: float
    frames_total: int | None
    frames_processed: int
    estimated_time_seconds: int | None
    elapsed_time_seconds: int | None
    enhancement_config: dict[str, Any]
    export_config: dict[str, Any]
    output_path: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
```

---

## JobDetailResponse

```python
class JobDetailResponse(BaseModel):
    job: JobResponse
    project: ProjectResponse
    video: VideoAssetResponse
    model: AIModelResponse | None
```

---

## JobListResponse

```python
class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
```

---

## JobProgressResponse

```python
class JobProgressResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    progress_percent: float
    frames_total: int | None
    frames_processed: int
    estimated_time_seconds: int | None
    elapsed_time_seconds: int | None
    error_code: str | None
    error_message: str | None
```

---

## JobLogResponse

```python
class JobLogResponse(BaseModel):
    id: str
    job_id: str
    level: str
    message: str
    stage: str | None
    created_at: datetime
```

---

## JobLogsResponse

```python
class JobLogsResponse(BaseModel):
    items: list[JobLogResponse]
    total: int
```

---

## JobControlResponse

```python
class JobControlResponse(BaseModel):
    job: JobResponse
    message: str
```

---

# Repository

Crear:

```text
app/db/repositories/job_repository.py
```

Funciones sugeridas:

```python
def create_job(db: Session, data: dict) -> ProcessingJob:
    ...


def get_job_by_id(db: Session, job_id: str) -> ProcessingJob | None:
    ...


def list_jobs(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    project_id: str | None = None,
) -> list[ProcessingJob]:
    ...


def count_jobs(
    db: Session,
    status: str | None = None,
    project_id: str | None = None,
) -> int:
    ...


def update_job(db: Session, job: ProcessingJob, data: dict) -> ProcessingJob:
    ...


def delete_job(db: Session, job: ProcessingJob) -> None:
    ...


def create_job_log(
    db: Session,
    job_id: str,
    level: str,
    message: str,
    stage: str | None = None,
) -> JobLog:
    ...


def list_job_logs(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[JobLog]:
    ...
```

Reglas:

* Ordenar jobs por `created_at DESC`.
* Ordenar logs por `created_at ASC`.
* No eliminar proyecto ni video al eliminar un job.
* Eliminar logs asociados al eliminar un job.

---

# Servicio

Crear:

```text
app/services/job_service.py
```

Responsabilidades:

1. Crear jobs desde proyectos.
2. Validar que el proyecto exista.
3. Validar que el video asociado exista.
4. Validar que el archivo de video siga disponible.
5. Validar que el modelo exista y esté habilitado.
6. Crear job con configuración congelada.
7. Listar jobs.
8. Obtener detalle de job.
9. Iniciar job.
10. Pausar job.
11. Reanudar job.
12. Cancelar job.
13. Eliminar job.
14. Obtener progreso.
15. Obtener logs.

Funciones sugeridas:

```python
def create_processing_job(
    db: Session,
    request: JobCreateRequest,
) -> JobDetailResponse:
    ...


def list_processing_jobs(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    project_id: str | None = None,
) -> JobListResponse:
    ...


def get_processing_job_detail(
    db: Session,
    job_id: str,
) -> JobDetailResponse:
    ...


def start_processing_job(
    db: Session,
    job_id: str,
) -> JobControlResponse:
    ...


def pause_processing_job(
    db: Session,
    job_id: str,
) -> JobControlResponse:
    ...


def resume_processing_job(
    db: Session,
    job_id: str,
) -> JobControlResponse:
    ...


def cancel_processing_job(
    db: Session,
    job_id: str,
) -> JobControlResponse:
    ...


def delete_processing_job(
    db: Session,
    job_id: str,
) -> dict:
    ...


def get_job_progress(
    db: Session,
    job_id: str,
) -> JobProgressResponse:
    ...


def get_job_logs(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> JobLogsResponse:
    ...
```

---

# Cola interna

Crear:

```text
app/workers/queue.py
```

Debe implementar una cola simple.

Funciones sugeridas:

```python
class JobQueue:
    async def enqueue(self, job_id: str) -> None:
        ...

    async def dequeue(self) -> str:
        ...

    def size(self) -> int:
        ...


job_queue = JobQueue()
```

Para este requerimiento:

* La cola puede almacenar IDs de jobs.
* No necesita procesamiento paralelo.
* No necesita persistir en memoria después de reiniciar.
* El estado persistente real está en SQLite.

---

# Worker skeleton

Crear:

```text
app/workers/job_runner.py
```

Debe preparar una función skeleton:

```python
async def run_job_worker() -> None:
    ...
```

Y una función:

```python
async def process_job_skeleton(job_id: str) -> None:
    ...
```

En este requerimiento, el worker puede hacer una simulación mínima:

```text
queued -> running -> completed
```

Pero preferiblemente debe quedar configurable.

Recomendación para el MVP:

* `POST /jobs/{id}/start` cambia a `queued`.
* Encola el job.
* El worker skeleton cambia a `running`.
* Luego marca `completed` después de una simulación corta solo en entorno `development`.

Para evitar falsa confianza, el log debe decir:

```text
Processing pipeline is not implemented yet. Job completed by skeleton runner.
```

Si se prefiere no simular completion, también es aceptable que quede en `queued`, pero la arquitectura debe estar lista para que el worker tome el job en el siguiente requerimiento.

---

# Startup del worker

Actualizar:

```text
app/main.py
```

En startup:

* Inicializar DB.
* Seed de modelos.
* Crear storage.
* Inicializar worker skeleton.

Usar lifecycle de FastAPI.

Reglas:

* El worker no debe bloquear el arranque de la API.
* Si el worker falla, registrar error.
* No debe romper los endpoints básicos.

---

# Endpoints requeridos

Todos bajo:

```text
/api/jobs
```

---

## POST /api/jobs

Crea un job desde un proyecto.

### Request

```json
{
  "project_id": "f42109c4-33cb-48de-81db-d45f53238221"
}
```

También puede sobreescribir configuración:

```json
{
  "project_id": "f42109c4-33cb-48de-81db-d45f53238221",
  "model_id": "realesrgan-x4",
  "enhancement_config": {
    "model_id": "realesrgan-x4",
    "scale": "4x",
    "denoise": 10,
    "sharpen": 15,
    "compression_cleanup": true
  },
  "export_config": {
    "format": "mp4",
    "codec": "h264",
    "keep_audio": true,
    "output_resolution": "4x"
  }
}
```

### Response 201

```json
{
  "job": {
    "id": "b1dd73d0-ea57-4039-970d-597c7158a003",
    "project_id": "f42109c4-33cb-48de-81db-d45f53238221",
    "video_asset_id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
    "ai_model_id": "6fcff276-a744-46ef-b81d-92aa5094f322",
    "ai_model_slug": "realesrgan-x4",
    "status": "pending",
    "current_stage": "idle",
    "progress_percent": 0,
    "frames_total": null,
    "frames_processed": 0,
    "estimated_time_seconds": null,
    "elapsed_time_seconds": null,
    "enhancement_config": {
      "model_id": "realesrgan-x4",
      "scale": "4x",
      "denoise": 10,
      "sharpen": 15,
      "compression_cleanup": true
    },
    "export_config": {
      "format": "mp4",
      "codec": "h264",
      "keep_audio": true,
      "output_resolution": "4x"
    },
    "output_path": null,
    "error_code": null,
    "error_message": null,
    "created_at": "2026-06-13T12:00:00",
    "updated_at": "2026-06-13T12:00:00",
    "started_at": null,
    "completed_at": null,
    "cancelled_at": null
  },
  "project": {},
  "video": {},
  "model": {}
}
```

---

## GET /api/jobs

Lista jobs.

Query params:

```text
limit: int = 50
offset: int = 0
status: str | None = None
project_id: str | None = None
```

---

## GET /api/jobs/{job_id}

Devuelve detalle completo de un job.

---

## POST /api/jobs/{job_id}/start

Inicia o encola un job.

Reglas:

* Solo puede iniciar jobs en estado `pending` o `paused`.
* Cambiar estado a `queued`.
* Agregar log `Job queued`.
* Enviar job a la cola interna.
* Responder con el estado actualizado.

### Response 200

```json
{
  "job": {
    "id": "b1dd73d0-ea57-4039-970d-597c7158a003",
    "status": "queued",
    "current_stage": "idle",
    "progress_percent": 0
  },
  "message": "Job queued."
}
```

---

## POST /api/jobs/{job_id}/pause

Pausa un job.

Reglas:

* Solo permitir pausar jobs `queued` o `running`.
* Cambiar estado a `paused`.
* Agregar log `Job paused`.
* En este requerimiento, la pausa es lógica.
* El worker real respetará esta pausa en requerimientos futuros.

---

## POST /api/jobs/{job_id}/resume

Reanuda un job pausado.

Reglas:

* Solo permitir si está en `paused`.
* Cambiar estado a `queued`.
* Agregar log `Job resumed`.
* Encolar nuevamente.

---

## POST /api/jobs/{job_id}/cancel

Cancela un job.

Reglas:

* Permitir cancelar jobs `pending`, `queued`, `running` o `paused`.
* Cambiar estado a `cancelled`.
* Cambiar etapa a `cancelled`.
* Setear `cancelled_at`.
* Agregar log `Job cancelled`.
* No borrar archivos todavía.

---

## DELETE /api/jobs/{job_id}

Elimina un job.

Reglas:

* No permitir eliminar jobs `running`.
* Eliminar logs asociados.
* No eliminar proyecto.
* No eliminar video.
* No eliminar modelo.
* No borrar archivos de salida todavía.

---

## GET /api/jobs/{job_id}/progress

Devuelve progreso resumido del job.

---

## GET /api/jobs/{job_id}/logs

Devuelve logs del job.

Query params:

```text
limit: int = 100
offset: int = 0
```

---

# Validaciones

## Crear job

Validar:

1. El proyecto existe.
2. El video asociado existe.
3. El archivo de video sigue existiendo.
4. El modelo existe.
5. El modelo está habilitado.
6. La configuración de exportación es válida.
7. La configuración de mejora es válida.

No exigir todavía que el modelo esté instalado.

Eso se hará cuando se implemente el pipeline real.

---

## Iniciar job

Validar:

1. El job existe.
2. El estado permite iniciar.
3. El proyecto existe.
4. El video existe.
5. El archivo de video sigue disponible.
6. El modelo sigue habilitado.

---

# Transiciones permitidas

```text
pending -> queued
queued -> running
running -> completed
running -> failed
queued -> paused
running -> paused
paused -> queued
pending -> cancelled
queued -> cancelled
running -> cancelled
paused -> cancelled
```

No permitir:

```text
completed -> running
completed -> queued
cancelled -> running
failed -> running
```

En el futuro se podrá implementar retry usando un nuevo endpoint.

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class JobNotFoundError(OroyaVideoError):
    pass


class JobInvalidStateError(OroyaVideoError):
    pass


class JobCreateFailedError(OroyaVideoError):
    pass


class JobStartFailedError(OroyaVideoError):
    pass


class JobCancelFailedError(OroyaVideoError):
    pass


class JobDeleteFailedError(OroyaVideoError):
    pass
```

---

## Job no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "job_not_found",
  "message": "Processing job was not found."
}
```

---

## Estado inválido

Status:

```text
409
```

Response:

```json
{
  "error": "job_invalid_state",
  "message": "The job cannot perform this action in its current state."
}
```

---

## Fallo creando job

Status:

```text
500
```

Response:

```json
{
  "error": "job_create_failed",
  "message": "Processing job could not be created."
}
```

---

# Logging del backend

Registrar eventos:

```text
Job create requested
Job created
Job list requested
Job detail requested
Job queued
Job started by worker
Job paused
Job resumed
Job cancelled
Job deleted
Job progress requested
Job logs requested
Job invalid state transition
Job not found
```

---

# Logs del job

Cada acción relevante debe crear un `JobLog`.

Ejemplos:

```text
Job created.
Job queued.
Job started.
Job paused.
Job resumed.
Job cancelled.
Job completed by skeleton runner.
Processing pipeline is not implemented yet.
```

---

# Tests

Crear:

```text
tests/test_jobs.py
```

Los tests deben usar SQLite temporal o en memoria.

Pruebas mínimas:

1. `POST /api/jobs` crea un job con proyecto válido.
2. `POST /api/jobs` usa configuración del proyecto si no se envía override.
3. `POST /api/jobs` permite override de `model_id`.
4. `POST /api/jobs` responde `404` si el proyecto no existe.
5. `POST /api/jobs` responde `404` si el modelo no existe.
6. `POST /api/jobs` responde `409` si el modelo está deshabilitado.
7. `POST /api/jobs` responde `409` si el archivo de video no existe.
8. `GET /api/jobs` lista jobs.
9. `GET /api/jobs` filtra por `status`.
10. `GET /api/jobs` filtra por `project_id`.
11. `GET /api/jobs/{job_id}` devuelve detalle.
12. `GET /api/jobs/{job_id}` responde `404` si no existe.
13. `POST /api/jobs/{job_id}/start` cambia estado a `queued`.
14. `POST /api/jobs/{job_id}/start` crea log `Job queued`.
15. `POST /api/jobs/{job_id}/pause` cambia estado a `paused`.
16. `POST /api/jobs/{job_id}/resume` cambia estado a `queued`.
17. `POST /api/jobs/{job_id}/cancel` cambia estado a `cancelled`.
18. `POST /api/jobs/{job_id}/cancel` setea `cancelled_at`.
19. `DELETE /api/jobs/{job_id}` elimina job no running.
20. `DELETE /api/jobs/{job_id}` no permite eliminar job running.
21. `GET /api/jobs/{job_id}/progress` devuelve progreso.
22. `GET /api/jobs/{job_id}/logs` devuelve logs.
23. No se permite iniciar un job `completed`.
24. No se permite reanudar un job que no esté `paused`.

---

# Actualizar README

Agregar sección:

```text
Processing jobs endpoints
```

Documentar:

```text
POST   /api/jobs
GET    /api/jobs
GET    /api/jobs/{job_id}
POST   /api/jobs/{job_id}/start
POST   /api/jobs/{job_id}/pause
POST   /api/jobs/{job_id}/resume
POST   /api/jobs/{job_id}/cancel
DELETE /api/jobs/{job_id}
GET    /api/jobs/{job_id}/progress
GET    /api/jobs/{job_id}/logs
```

Ejemplo crear job:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\": \"f42109c4-33cb-48de-81db-d45f53238221\"}"
```

Ejemplo iniciar job:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/{job_id}/start"
```

Agregar nota:

```text
In this requirement, jobs are controlled and queued, but the real video processing pipeline is not implemented yet.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe modelo ORM `ProcessingJob`.
* Existe modelo ORM `JobLog`.
* Existe repositorio de jobs.
* Existe servicio de jobs.
* Existe router `routes_jobs.py`.
* Existe cola interna básica.
* Existe worker skeleton.
* El router principal incluye `/api/jobs`.
* `POST /api/jobs` crea jobs.
* `GET /api/jobs` lista jobs.
* `GET /api/jobs/{job_id}` devuelve detalle.
* `POST /api/jobs/{job_id}/start` encola jobs.
* `POST /api/jobs/{job_id}/pause` pausa jobs.
* `POST /api/jobs/{job_id}/resume` reanuda jobs.
* `POST /api/jobs/{job_id}/cancel` cancela jobs.
* `DELETE /api/jobs/{job_id}` elimina jobs no activos.
* `GET /api/jobs/{job_id}/progress` devuelve progreso.
* `GET /api/jobs/{job_id}/logs` devuelve logs.
* Los jobs validan proyecto, video y modelo.
* Los jobs congelan configuración de enhancement/export.
* Los logs de job se guardan en SQLite.
* Las transiciones inválidas devuelven error controlado.
* Los tests pasan.
* README documenta los endpoints.
* No se implementa todavía procesamiento real de video.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Importar un video.
2. Crear un proyecto.
3. Crear un job desde ese proyecto.
4. Iniciar el job.
5. Ver su estado como `queued`.
6. Consultar progreso.
7. Consultar logs.
8. Pausar, reanudar o cancelar el job.

Ejemplo de flujo:

```text
POST /api/videos/import
POST /api/projects
POST /api/jobs
POST /api/jobs/{job_id}/start
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/logs
```

Este requerimiento deja preparado el backend para el siguiente paso: implementación real de extracción de frames usando FFmpeg.
