# REQ-008 - FFmpeg Frame Extraction Pipeline

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
```

El backend ya debe tener:

* FastAPI funcional.
* SQLite inicializado.
* Sistema de paths.
* Logging.
* Detección de FFmpeg y FFprobe.
* Importación lógica de videos.
* CRUD de proyectos.
* Registro de modelos IA.
* CRUD/control de jobs.
* Cola interna básica.
* Worker skeleton.
* Logs de job.
* Progreso básico de job.

---

# Objetivo

Implementar la primera etapa real del pipeline de procesamiento de Oroya Video: extracción de frames usando FFmpeg.

Cuando un job sea iniciado, el worker debe tomar el video asociado al proyecto, crear una carpeta temporal para el job, extraer los frames del video original y actualizar el progreso en la base de datos.

Este requerimiento no debe implementar todavía procesamiento IA, Real-ESRGAN, reconstrucción de video ni exportación final.

---

# Contexto

Oroya Video procesará videos usando este pipeline general:

```text
Video original
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
Export Result
```

Hasta ahora los jobs existen, pero no ejecutan procesamiento real.

Con este requerimiento, el job empezará a hacer trabajo tangible:

```text
Job queued
    ↓
Worker starts job
    ↓
Create job workspace
    ↓
Extract original frames with FFmpeg
    ↓
Update progress
    ↓
Mark frame extraction as completed
```

---

# Decisión MVP

La extracción de frames se hará usando FFmpeg hacia archivos PNG.

Formato inicial:

```text
PNG
```

Motivo:

* Es simple.
* Es compatible con pipelines de IA.
* Evita pérdidas adicionales antes del modelo.
* Facilita inspección manual durante desarrollo.

Estructura esperada por job:

```text
storage/temp/jobs/{job_id}/
├── frames/
│   ├── original/
│   │   ├── frame_00000000.png
│   │   ├── frame_00000001.png
│   │   ├── frame_00000002.png
│   │   └── ...
│   │
│   └── enhanced/
│
├── logs/
└── metadata.json
```

La carpeta `enhanced` se crea desde ahora, pero todavía no se usa.

---

# Alcance de este requerimiento

Implementar:

1. Pipeline de extracción de frames con FFmpeg.
2. Servicio para preparar workspace del job.
3. Servicio para construir comando FFmpeg.
4. Ejecución de FFmpeg sin `shell=True`.
5. Parseo de progreso de FFmpeg.
6. Actualización real de `frames_total`.
7. Actualización real de `frames_processed`.
8. Actualización real de `progress_percent`.
9. Logs del job durante extracción.
10. Cancelación básica de extracción.
11. Limpieza opcional de frames.
12. Endpoint para listar frames extraídos.
13. Endpoint para obtener resumen de extracción.
14. Tests con mocks.
15. Actualización del README.

No implementar todavía:

* Procesamiento con IA.
* Real-ESRGAN.
* OpenCV.
* PyTorch.
* Reconstrucción de video.
* Mux de audio.
* Exportación final.
* Preview thumbnails.
* WebSocket.
* Server-Sent Events.
* Batch processing.
* Reintentos avanzados.

---

# Cambios conceptuales

## Antes

En REQ-007, el worker era un skeleton:

```text
queued -> running -> completed
```

## Ahora

El worker debe ejecutar una etapa real:

```text
queued
  ↓
running
  ↓
extracting_frames
  ↓
completed
```

Importante:

En este requerimiento, `completed` significa:

```text
La extracción de frames terminó correctamente.
```

No significa que el video final haya sido exportado.

El log del job debe dejar esto claro:

```text
Frame extraction completed. AI enhancement and video export are not implemented yet.
```

---

# Estados usados

Estados de job existentes:

```text
pending
queued
running
paused
completed
failed
cancelled
```

Etapas usadas en este requerimiento:

```text
idle
queued
extracting_frames
completed
failed
cancelled
```

Durante extracción:

```text
status = running
current_stage = extracting_frames
```

Al terminar correctamente:

```text
status = completed
current_stage = completed
progress_percent = 100
```

---

# Nuevos campos en ProcessingJob

Actualizar modelo ORM:

```text
app/db/models.py
```

Agregar a `ProcessingJob`:

```text
working_dir
original_frames_dir
enhanced_frames_dir
frame_file_pattern
frame_format
extracted_frames
extraction_started_at
extraction_completed_at
pause_requested
cancel_requested
```

Tipos sugeridos:

```text
working_dir                 String nullable
original_frames_dir          String nullable
enhanced_frames_dir          String nullable
frame_file_pattern           String nullable
frame_format                 String nullable default "png"
extracted_frames             Integer not null default 0
extraction_started_at        DateTime nullable
extraction_completed_at      DateTime nullable
pause_requested              Boolean not null default false
cancel_requested             Boolean not null default false
```

---

# Paths

Actualizar:

```text
app/core/paths.py
```

Agregar funciones:

```python
def get_jobs_temp_path() -> Path:
    ...


def get_job_working_path(job_id: str) -> Path:
    ...


def get_job_original_frames_path(job_id: str) -> Path:
    ...


def get_job_enhanced_frames_path(job_id: str) -> Path:
    ...


def get_job_logs_path(job_id: str) -> Path:
    ...


def ensure_job_directories(job_id: str) -> dict[str, Path]:
    ...
```

Estructura generada:

```text
storage/temp/jobs/{job_id}/
storage/temp/jobs/{job_id}/frames/original
storage/temp/jobs/{job_id}/frames/enhanced
storage/temp/jobs/{job_id}/logs
```

---

# Nuevos servicios

Agregar:

```text
app/services/frame_extraction_service.py
app/services/job_workspace_service.py
```

---

# job_workspace_service.py

Responsabilidades:

1. Crear carpetas temporales del job.
2. Resolver rutas de frames originales.
3. Resolver rutas de frames enhanced.
4. Crear archivo metadata inicial.
5. Verificar si la carpeta ya existe.
6. Limpiar carpetas si se solicita.

Funciones sugeridas:

```python
def prepare_job_workspace(job_id: str) -> dict[str, Path]:
    ...


def get_job_workspace_summary(job_id: str) -> dict:
    ...


def clean_job_workspace(job_id: str) -> None:
    ...
```

---

# frame_extraction_service.py

Responsabilidades:

1. Resolver el video input.
2. Validar disponibilidad de FFmpeg.
3. Calcular número estimado de frames.
4. Crear comando FFmpeg.
5. Ejecutar FFmpeg.
6. Parsear progreso.
7. Actualizar job en DB.
8. Registrar logs.
9. Soportar cancelación básica.
10. Contar frames generados al final.

Funciones sugeridas:

```python
def resolve_job_input_video(job: ProcessingJob) -> Path:
    ...


def estimate_total_frames(job: ProcessingJob) -> int | None:
    ...


def build_frame_extraction_command(
    input_path: Path,
    output_dir: Path,
    frame_pattern: str = "frame_%08d.png",
) -> list[str]:
    ...


def extract_frames_for_job(
    db: Session,
    job_id: str,
) -> ProcessingJob:
    ...


def parse_ffmpeg_progress_line(line: str) -> dict[str, str]:
    ...


def count_extracted_frames(frames_dir: Path) -> int:
    ...
```

---

# Resolución del video input

Para obtener el archivo de video a procesar:

```text
if video.source_mode == "copy":
    usar video.stored_path
else:
    usar video.source_path
```

Reglas:

* Resolver path con `Path(...).expanduser().resolve()`.
* Validar que existe.
* Validar que es archivo.
* Si no existe, marcar job como `failed`.
* Registrar log de error.
* Responder error controlado si se consulta el job.

---

# Comando FFmpeg

Comando base:

```bash
ffmpeg \
  -hide_banner \
  -y \
  -i input.mp4 \
  -map 0:v:0 \
  -vsync 0 \
  -start_number 0 \
  -progress pipe:1 \
  -nostats \
  storage/temp/jobs/{job_id}/frames/original/frame_%08d.png
```

En Python:

```python
[
    "ffmpeg",
    "-hide_banner",
    "-y",
    "-i",
    str(input_path),
    "-map",
    "0:v:0",
    "-vsync",
    "0",
    "-start_number",
    "0",
    "-progress",
    "pipe:1",
    "-nostats",
    str(output_dir / "frame_%08d.png"),
]
```

Reglas:

* No usar `shell=True`.
* Usar `subprocess.Popen` para leer progreso en tiempo real.
* Capturar `stdout`.
* Capturar `stderr`.
* Registrar errores de FFmpeg.
* Si FFmpeg termina con código distinto de `0`, marcar job como `failed`.
* Si el usuario cancela, terminar el proceso y marcar `cancelled`.

---

# Progreso de FFmpeg

FFmpeg con `-progress pipe:1` emite líneas como:

```text
frame=120
fps=32.5
stream_0_0_q=-0.0
bitrate=N/A
total_size=N/A
out_time_us=5000000
out_time_ms=5000000
out_time=00:00:05.000000
dup_frames=0
drop_frames=0
speed=1.25x
progress=continue
```

El backend debe leer especialmente:

```text
frame
progress
```

Cuando detecte:

```text
frame=120
```

Actualizar:

```text
frames_processed = 120
progress_percent = frames_processed / frames_total * 100
```

Si `frames_total` es `None`, se puede calcular progreso aproximado usando `out_time` y duración del video.

---

# Cálculo de frames_total

Primera opción:

```text
video.duration_seconds * video.fps
```

Ejemplo:

```text
128.45 * 23.976 = 3079 frames aproximadamente
```

Reglas:

* Redondear al entero más cercano.
* Si falta duración o FPS, dejar `frames_total = None`.
* Si `frames_total` es `None`, el progreso puede quedarse en `0` durante ejecución y actualizarse a `100` al final.
* Al terminar, contar archivos PNG generados y guardar el valor real en `extracted_frames`.

---

# Control de espacio en disco

Antes de extraer frames, verificar espacio libre en `storage/temp`.

Regla inicial:

```text
free_space_bytes >= video.file_size_bytes * 3
```

Si no hay espacio suficiente:

```text
status = failed
current_stage = failed
error_code = insufficient_temp_storage
error_message = Not enough temporary storage space to extract frames.
```

Respuesta esperada al consultar progreso:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "failed",
  "current_stage": "failed",
  "progress_percent": 0,
  "error_code": "insufficient_temp_storage",
  "error_message": "Not enough temporary storage space to extract frames."
}
```

---

# Cancelación

La cancelación debe funcionar si el job está:

```text
queued
running
paused
```

Si el job está en `running` y `current_stage = extracting_frames`:

1. Marcar `cancel_requested = true`.
2. El worker debe detectar esto.
3. Terminar el proceso FFmpeg con `process.terminate()`.
4. Si no termina en pocos segundos, usar `process.kill()`.
5. Marcar:

```text
status = cancelled
current_stage = cancelled
cancelled_at = now
```

6. Agregar log:

```text
Frame extraction cancelled by user.
```

No borrar automáticamente los frames parciales en este requerimiento.

---

# Pausa

Pausar extracción real de FFmpeg de forma multiplataforma no será obligatorio en este requerimiento.

Regla MVP:

* Si el job está `queued`, se puede pausar.
* Si el job está `running` y `extracting_frames`, responder `409` indicando que la pausa real durante extracción no está soportada todavía.
* La cancelación sí debe estar soportada.

Respuesta:

```json
{
  "error": "job_pause_not_supported",
  "message": "Pausing during FFmpeg frame extraction is not supported yet. Cancel the job instead."
}
```

Agregar excepción:

```python
class JobPauseNotSupportedError(OroyaVideoError):
    pass
```

---

# Worker

Actualizar:

```text
app/workers/job_runner.py
```

El worker debe dejar de completar jobs artificialmente.

Nuevo flujo:

```text
dequeue job_id
    ↓
load job
    ↓
if job status is cancelled, skip
    ↓
set status running
    ↓
set current_stage extracting_frames
    ↓
run extract_frames_for_job
    ↓
if success, set completed
    ↓
if fail, set failed
```

El worker debe registrar logs:

```text
Job picked by worker.
Frame extraction started.
Frame extraction completed.
AI enhancement and export are not implemented yet.
```

---

# Startup

Actualizar lifecycle en:

```text
app/main.py
```

Reglas:

* El worker debe iniciar en background.
* El worker no debe bloquear la API.
* Si hay jobs `queued` al iniciar la app, pueden quedarse pendientes para futura recuperación.
* No se exige recuperación automática de jobs en este requerimiento.

---

# Endpoints nuevos o modificados

Los endpoints de jobs existentes se mantienen.

Actualizar comportamiento de:

```text
POST /api/jobs/{job_id}/start
POST /api/jobs/{job_id}/cancel
POST /api/jobs/{job_id}/pause
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/logs
```

---

## POST /api/jobs/{job_id}/start

Ahora debe:

1. Validar job.
2. Validar FFmpeg disponible.
3. Validar archivo de video.
4. Validar espacio temporal.
5. Cambiar a `queued`.
6. Encolar job.
7. Worker ejecutará extracción real.

---

## GET /api/jobs/{job_id}/progress

Debe devolver también:

```text
extracted_frames
working_dir
original_frames_dir
```

Actualizar schema `JobProgressResponse`:

```python
class JobProgressResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    progress_percent: float
    frames_total: int | None
    frames_processed: int
    extracted_frames: int
    estimated_time_seconds: int | None
    elapsed_time_seconds: int | None
    working_dir: str | None
    original_frames_dir: str | None
    error_code: str | None
    error_message: str | None
```

---

## GET /api/jobs/{job_id}/frames

Nuevo endpoint.

Lista frames extraídos para un job.

Query params:

```text
limit: int = 100
offset: int = 0
```

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "frames_dir": "storage/temp/jobs/b1dd73d0-ea57-4039-970d-597c7158a003/frames/original",
  "items": [
    {
      "index": 0,
      "file_name": "frame_00000000.png",
      "path": "storage/temp/jobs/{job_id}/frames/original/frame_00000000.png"
    },
    {
      "index": 1,
      "file_name": "frame_00000001.png",
      "path": "storage/temp/jobs/{job_id}/frames/original/frame_00000001.png"
    }
  ],
  "total": 3080
}
```

---

## GET /api/jobs/{job_id}/frame-extraction

Nuevo endpoint.

Devuelve resumen de extracción.

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "completed",
  "current_stage": "completed",
  "working_dir": "storage/temp/jobs/{job_id}",
  "original_frames_dir": "storage/temp/jobs/{job_id}/frames/original",
  "enhanced_frames_dir": "storage/temp/jobs/{job_id}/frames/enhanced",
  "frame_file_pattern": "frame_%08d.png",
  "frame_format": "png",
  "frames_total": 3080,
  "frames_processed": 3080,
  "extracted_frames": 3080,
  "extraction_started_at": "2026-06-13T12:00:00",
  "extraction_completed_at": "2026-06-13T12:05:00"
}
```

---

## DELETE /api/jobs/{job_id}/frames

Nuevo endpoint.

Elimina frames temporales del job.

Reglas:

* No permitir si job está `running`.
* Eliminar únicamente:

```text
storage/temp/jobs/{job_id}/frames/original
storage/temp/jobs/{job_id}/frames/enhanced
```

* No eliminar el video original.
* No eliminar exports.
* Marcar:

```text
extracted_frames = 0
frames_processed = 0
progress_percent = 0
original_frames_dir = null
enhanced_frames_dir = null
```

Response:

```json
{
  "deleted": true,
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003"
}
```

---

# Schemas nuevos

Actualizar:

```text
app/schemas/job_schema.py
```

Agregar:

```python
class JobFrameItem(BaseModel):
    index: int
    file_name: str
    path: str


class JobFramesResponse(BaseModel):
    job_id: str
    frames_dir: str | None
    items: list[JobFrameItem]
    total: int


class FrameExtractionSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    working_dir: str | None
    original_frames_dir: str | None
    enhanced_frames_dir: str | None
    frame_file_pattern: str | None
    frame_format: str | None
    frames_total: int | None
    frames_processed: int
    extracted_frames: int
    extraction_started_at: datetime | None
    extraction_completed_at: datetime | None


class DeleteFramesResponse(BaseModel):
    deleted: bool
    job_id: str
```

Actualizar `JobResponse` para incluir:

```python
working_dir: str | None
original_frames_dir: str | None
enhanced_frames_dir: str | None
frame_file_pattern: str | None
frame_format: str | None
extracted_frames: int
extraction_started_at: datetime | None
extraction_completed_at: datetime | None
pause_requested: bool
cancel_requested: bool
```

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class FFmpegNotAvailableError(OroyaVideoError):
    pass


class FrameExtractionFailedError(OroyaVideoError):
    pass


class InsufficientTempStorageError(OroyaVideoError):
    pass


class JobFramesNotFoundError(OroyaVideoError):
    pass


class JobPauseNotSupportedError(OroyaVideoError):
    pass
```

---

## FFmpeg no disponible

Status:

```text
503
```

Response:

```json
{
  "error": "ffmpeg_not_available",
  "message": "FFmpeg is required to extract video frames."
}
```

---

## Extracción fallida

Status:

```text
422
```

Response:

```json
{
  "error": "frame_extraction_failed",
  "message": "Video frames could not be extracted."
}
```

---

## Espacio temporal insuficiente

Status:

```text
400
```

Response:

```json
{
  "error": "insufficient_temp_storage",
  "message": "Not enough temporary storage space to extract frames."
}
```

---

## Frames no encontrados

Status:

```text
404
```

Response:

```json
{
  "error": "job_frames_not_found",
  "message": "No extracted frames were found for this job."
}
```

---

# Logging

Registrar en backend:

```text
Frame extraction requested
Job workspace prepared
FFmpeg frame extraction command built
FFmpeg frame extraction started
FFmpeg progress updated
FFmpeg frame extraction completed
FFmpeg frame extraction failed
Frame extraction cancelled
Extracted frames counted
Job frames listed
Job frames deleted
```

Registrar en logs del job:

```text
Job picked by worker.
Job workspace prepared.
Frame extraction started.
Frame extraction progress: {frames_processed}/{frames_total}
Frame extraction completed.
Extracted frames: {extracted_frames}
AI enhancement and export are not implemented yet.
Frame extraction failed: {reason}
Frame extraction cancelled by user.
```

Para evitar spam, no registrar cada frame individual.

Recomendación:

```text
Registrar progreso cada 5% o cada 100 frames.
```

---

# Tests

Crear:

```text
tests/test_frame_extraction.py
```

Los tests no deben depender de FFmpeg real ni videos reales.

Usar mocks para:

* `subprocess.Popen`
* `shutil.which`
* `Path.exists`
* `Path.is_file`
* `Path.glob`
* `shutil.disk_usage`
* servicios de DB cuando sea necesario

Pruebas mínimas:

1. `build_frame_extraction_command` genera comando sin `shell=True`.
2. El comando incluye `ffmpeg`.
3. El comando incluye `-i`.
4. El comando incluye `-progress pipe:1`.
5. El comando incluye patrón `frame_%08d.png`.
6. `parse_ffmpeg_progress_line("frame=120")` devuelve `{"frame": "120"}`.
7. `count_extracted_frames` cuenta archivos `.png`.
8. `prepare_job_workspace` crea carpetas esperadas.
9. `POST /api/jobs/{job_id}/start` falla con `503` si FFmpeg no existe.
10. `POST /api/jobs/{job_id}/start` falla con `400` si no hay espacio temporal.
11. `POST /api/jobs/{job_id}/start` encola job si todo es válido.
12. Worker cambia job a `running`.
13. Worker cambia `current_stage` a `extracting_frames`.
14. Worker actualiza `frames_processed`.
15. Worker marca `completed` cuando FFmpeg termina con código `0`.
16. Worker marca `failed` cuando FFmpeg termina con código distinto de `0`.
17. `POST /api/jobs/{job_id}/cancel` marca `cancel_requested`.
18. Cancelación termina proceso FFmpeg si está corriendo.
19. `GET /api/jobs/{job_id}/progress` incluye rutas de frames.
20. `GET /api/jobs/{job_id}/frames` lista frames.
21. `GET /api/jobs/{job_id}/frame-extraction` devuelve resumen.
22. `DELETE /api/jobs/{job_id}/frames` elimina frames si job no está running.
23. `DELETE /api/jobs/{job_id}/frames` no permite eliminar si job está running.
24. `POST /api/jobs/{job_id}/pause` responde `409` si está extrayendo frames.

---

# Actualizar README

Agregar sección:

```text
Frame extraction pipeline
```

Documentar:

```text
POST   /api/jobs/{job_id}/start
GET    /api/jobs/{job_id}/progress
GET    /api/jobs/{job_id}/frames
GET    /api/jobs/{job_id}/frame-extraction
DELETE /api/jobs/{job_id}/frames
```

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/{job_id}/start"
```

Consultar progreso:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/progress"
```

Listar frames:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/frames"
```

Agregar nota:

```text
In this requirement, jobs extract original video frames using FFmpeg.
AI enhancement and final video export are not implemented yet.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe `frame_extraction_service.py`.
* Existe `job_workspace_service.py`.
* El worker ejecuta extracción real de frames.
* `POST /api/jobs/{job_id}/start` valida FFmpeg.
* `POST /api/jobs/{job_id}/start` valida espacio temporal.
* `POST /api/jobs/{job_id}/start` encola el job.
* El worker crea workspace del job.
* El worker ejecuta FFmpeg sin `shell=True`.
* El worker extrae frames PNG.
* El worker actualiza `frames_total`.
* El worker actualiza `frames_processed`.
* El worker actualiza `progress_percent`.
* El worker guarda rutas de frames en DB.
* El worker guarda logs del job.
* El worker marca `completed` cuando la extracción termina.
* El worker marca `failed` si FFmpeg falla.
* La cancelación durante extracción está soportada.
* La pausa durante extracción responde error controlado.
* `GET /api/jobs/{job_id}/progress` muestra progreso real.
* `GET /api/jobs/{job_id}/frames` lista frames extraídos.
* `GET /api/jobs/{job_id}/frame-extraction` muestra resumen.
* `DELETE /api/jobs/{job_id}/frames` limpia frames temporales cuando es seguro.
* Los tests pasan.
* README documenta el flujo.
* No se implementa todavía IA ni exportación final.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Importar un video.
2. Crear un proyecto.
3. Crear un job.
4. Iniciar el job.
5. Ver el estado como `running`.
6. Ver la etapa `extracting_frames`.
7. Ver progreso basado en frames.
8. Ver frames PNG creados en:

```text
storage/temp/jobs/{job_id}/frames/original/
```

9. Consultar los frames por API.
10. Cancelar la extracción si está en curso.

Flujo esperado:

```text
POST /api/videos/import
POST /api/projects
POST /api/jobs
POST /api/jobs/{job_id}/start
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/frames
GET  /api/jobs/{job_id}/frame-extraction
```

Este requerimiento deja preparado el backend para el siguiente paso: procesamiento de frames con un modelo IA.
