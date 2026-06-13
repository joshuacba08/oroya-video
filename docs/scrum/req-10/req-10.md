# REQ-010 - Video Encoding from Enhanced Frames

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
```

El backend ya debe tener:

* FastAPI funcional.
* SQLite inicializado.
* Sistema de paths.
* Logging.
* Importación lógica de videos.
* CRUD de proyectos.
* Registro local de modelos IA.
* CRUD/control de jobs.
* Worker real.
* Extracción de frames originales con FFmpeg.
* Mock enhancement de frames.
* Carpeta `frames/enhanced` con imágenes PNG.
* Progreso real durante extracción y enhancement.

---

# Objetivo

Implementar la tercera etapa real del pipeline de Oroya Video: reconstrucción de video a partir de los frames mejorados.

El backend debe tomar los frames ubicados en:

```text
storage/temp/jobs/{job_id}/frames/enhanced/
```

y generar un archivo de video MP4 H264 temporal sin audio.

Este requerimiento no debe hacer todavía mux del audio original.
El audio se implementará en el siguiente requerimiento.

---

# Contexto

Hasta este punto, el pipeline ya puede hacer:

```text
Video original
    ↓
Extract Frames
    ↓
Mock Frame Enhancement
    ↓
Enhanced Frames
```

Este requerimiento agrega:

```text
Enhanced Frames
    ↓
Encode Video
    ↓
Silent MP4
```

Resultado esperado:

```text
storage/temp/jobs/{job_id}/encoded/
└── video_silent.mp4
```

El archivo generado será usado luego por el requerimiento de mux de audio y exportación final.

---

# Decisión MVP

La reconstrucción inicial será:

```text
MP4
H264
sin audio
```

Esto permite validar:

* Orden correcto de frames.
* FPS original.
* Resolución resultante.
* Codec H264.
* Progreso de encoding.
* Rutas de output.
* Integración con el worker.

El audio original se mantendrá para una fase posterior:

```text
REQ-011 - Audio Mux & Final Export
```

---

# Alcance de este requerimiento

Implementar:

1. Servicio de encoding de video.
2. Creación de carpeta `encoded`.
3. Construcción de comando FFmpeg para generar MP4 H264.
4. Uso de FPS original del video.
5. Uso de frames enhanced como input.
6. Generación de `video_silent.mp4`.
7. Actualización del worker.
8. Progreso durante encoding.
9. Logs de job durante encoding.
10. Cancelación durante encoding.
11. Endpoint para consultar resumen de encoding.
12. Endpoint para consultar archivo encoded.
13. Endpoint para eliminar encoded temporal.
14. Nuevos campos en `ProcessingJob`.
15. Tests con mocks.
16. Actualización del README.

No implementar todavía:

* Mux de audio.
* Export final con audio.
* Copia a `storage/exports`.
* Export registry.
* H265.
* Presets avanzados.
* Bitrate configurable complejo.
* Exportación batch.
* Preview thumbnails.
* Real-ESRGAN real.

---

# Cambios conceptuales

## Antes

REQ-009 terminaba en:

```text
queued
  ↓
running
  ↓
extracting_frames
  ↓
enhancing_frames
  ↓
completed
```

## Ahora

REQ-010 debe extender el pipeline:

```text
queued
  ↓
running
  ↓
extracting_frames
  ↓
enhancing_frames
  ↓
encoding_video
  ↓
completed
```

Importante:

En este requerimiento, `completed` significa:

```text
Frames extraídos, frames enhanced generados y video silent codificado correctamente.
```

No significa todavía exportación final con audio.

El log debe dejarlo claro:

```text
Video encoding completed. Audio mux and final export are not implemented yet.
```

---

# Estados usados

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

Etapas usadas:

```text
idle
queued
extracting_frames
enhancing_frames
encoding_video
completed
failed
cancelled
```

Durante encoding:

```text
status = running
current_stage = encoding_video
```

Al terminar correctamente:

```text
status = completed
current_stage = completed
progress_percent = 100
```

---

# Progreso global del job

Desde este requerimiento, el progreso global tendrá tres etapas:

```text
extracting_frames = 0% - 35%
enhancing_frames  = 35% - 75%
encoding_video    = 75% - 100%
```

Reglas:

* Al terminar extracción: `progress_percent = 35`
* Al terminar enhancement: `progress_percent = 75`
* Durante encoding: `75 + stage_progress * 25`
* Al terminar encoding: `progress_percent = 100`

Ejemplo:

```text
Extracción completa          → 35%
Enhancement completo         → 75%
Encoding al 50%              → 87.5%
Encoding completo            → 100%
```

---

# Nuevos campos en ProcessingJob

Actualizar:

```text
app/db/models.py
```

Agregar a `ProcessingJob`:

```text
encoded_dir
encoded_video_path
encoded_video_file_name
encoded_video_size_bytes
encoding_fps
encoding_codec
encoding_format
encoding_started_at
encoding_completed_at
encoding_error_code
encoding_error_message
```

Tipos sugeridos:

```text
encoded_dir                  String nullable
encoded_video_path            String nullable
encoded_video_file_name       String nullable
encoded_video_size_bytes      Integer nullable
encoding_fps                  Float nullable
encoding_codec                String nullable default "h264"
encoding_format               String nullable default "mp4"
encoding_started_at           DateTime nullable
encoding_completed_at         DateTime nullable
encoding_error_code           String nullable
encoding_error_message        Text nullable
```

---

# Paths

Actualizar:

```text
app/core/paths.py
```

Agregar funciones:

```python
def get_job_encoded_path(job_id: str) -> Path:
    ...


def get_job_silent_video_path(job_id: str) -> Path:
    ...


def ensure_job_encoded_directory(job_id: str) -> Path:
    ...
```

Estructura esperada:

```text
storage/temp/jobs/{job_id}/
├── frames/
│   ├── original/
│   └── enhanced/
│
└── encoded/
    └── video_silent.mp4
```

---

# Nuevo servicio

Crear:

```text
app/services/video_encoding_service.py
```

Responsabilidades:

1. Cargar job.
2. Validar que existan frames enhanced.
3. Validar FFmpeg disponible.
4. Resolver FPS original.
5. Crear carpeta `encoded`.
6. Construir comando FFmpeg.
7. Ejecutar encoding.
8. Parsear progreso.
9. Actualizar job.
10. Registrar logs.
11. Manejar cancelación.
12. Manejar errores.

Funciones sugeridas:

```python
def encode_video_for_job(
    db: Session,
    job_id: str,
) -> ProcessingJob:
    ...


def build_video_encoding_command(
    input_pattern: Path,
    output_path: Path,
    fps: float,
    codec: str = "libx264",
    pix_fmt: str = "yuv420p",
) -> list[str]:
    ...


def resolve_encoding_fps(job: ProcessingJob) -> float:
    ...


def parse_ffmpeg_encoding_progress_line(line: str) -> dict[str, str]:
    ...


def get_encoded_video_summary(
    db: Session,
    job_id: str,
) -> VideoEncodingSummaryResponse:
    ...


def delete_encoded_video(
    db: Session,
    job_id: str,
) -> DeleteEncodedVideoResponse:
    ...
```

---

# Resolución de FPS

El video encoded debe usar el FPS del video original.

Orden recomendado:

```text
1. video_asset.fps
2. job export_config.fps, si existiera en el futuro
3. fallback = 30.0
```

Reglas:

* Si `video_asset.fps` existe, usarlo.
* Si no existe, usar `30.0`.
* Guardar FPS usado en `encoding_fps`.
* Registrar warning si se usa fallback.

---

# Comando FFmpeg

Input esperado:

```text
storage/temp/jobs/{job_id}/frames/enhanced/frame_%08d.png
```

Output esperado:

```text
storage/temp/jobs/{job_id}/encoded/video_silent.mp4
```

Comando base:

```bash
ffmpeg \
  -hide_banner \
  -y \
  -framerate 23.976 \
  -start_number 0 \
  -i storage/temp/jobs/{job_id}/frames/enhanced/frame_%08d.png \
  -c:v libx264 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  -progress pipe:1 \
  -nostats \
  storage/temp/jobs/{job_id}/encoded/video_silent.mp4
```

En Python:

```python
[
    "ffmpeg",
    "-hide_banner",
    "-y",
    "-framerate",
    str(fps),
    "-start_number",
    "0",
    "-i",
    str(input_pattern),
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    "-progress",
    "pipe:1",
    "-nostats",
    str(output_path),
]
```

Reglas:

* No usar `shell=True`.
* Usar `subprocess.Popen`.
* Capturar `stdout`.
* Capturar `stderr`.
* Leer progreso en tiempo real.
* Si FFmpeg devuelve código distinto de `0`, marcar job como `failed`.
* Si el usuario cancela, terminar proceso FFmpeg.

---

# Progreso de encoding

FFmpeg con `-progress pipe:1` puede emitir:

```text
frame=120
fps=45.2
out_time=00:00:05.000000
progress=continue
```

El backend debe leer:

```text
frame
progress
```

Durante encoding:

```text
encoded_frames = frame
stage_progress = encoded_frames / enhanced_frames
global_progress = 75 + stage_progress * 25
```

Reglas:

* Si `enhanced_frames` existe, usarlo como total.
* Si no existe, contar archivos `.png` en `enhanced`.
* Si no hay total, progreso puede quedarse en `75` hasta finalizar.
* Al terminar correctamente, `progress_percent = 100`.

---

# Validación antes de encoding

Antes de ejecutar FFmpeg:

1. El job existe.
2. El job no está cancelado.
3. FFmpeg está disponible.
4. `enhanced_frames_dir` existe.
5. Hay frames `.png` enhanced.
6. Existe `frame_00000000.png`.
7. `encoding_fps` es mayor que `0`.
8. Hay espacio suficiente en `storage/temp`.
9. El job no está en estado final.

---

# Control de espacio en disco

Regla inicial:

```text
free_space_bytes >= size_of_enhanced_frames_dir * 0.25
```

Motivo:

* El MP4 codificado normalmente será bastante menor que los PNG.
* Esta regla es conservadora para el MVP.

Si no hay espacio suficiente:

```text
status = failed
current_stage = failed
error_code = insufficient_temp_storage
encoding_error_code = insufficient_temp_storage
error_message = Not enough temporary storage space to encode video.
encoding_error_message = Not enough temporary storage space to encode video.
```

---

# Cancelación durante encoding

Si el job está:

```text
running
current_stage = encoding_video
```

Entonces:

1. `POST /api/jobs/{job_id}/cancel` marca `cancel_requested = true`.
2. El servicio de encoding detecta cancelación.
3. Termina proceso FFmpeg con `process.terminate()`.
4. Si no termina, usar `process.kill()`.
5. Marcar:

```text
status = cancelled
current_stage = cancelled
cancelled_at = now
```

6. Agregar log:

```text
Video encoding cancelled by user.
```

No borrar automáticamente el MP4 parcial.

---

# Pausa

Pausar FFmpeg durante encoding no será obligatorio.

Regla MVP:

* Si el job está `queued`, se puede pausar.
* Si está `running` y `current_stage` es `extracting_frames`, `enhancing_frames` o `encoding_video`, responder `409`.

Mensaje:

```json
{
  "error": "job_pause_not_supported",
  "message": "Pausing during extraction, enhancement or encoding is not supported yet. Cancel the job instead."
}
```

---

# Worker

Actualizar:

```text
app/workers/job_runner.py
```

Nuevo flujo:

```text
dequeue job_id
    ↓
load job
    ↓
if cancelled, skip
    ↓
set status running
    ↓
extract frames
    ↓
if cancelled, stop
    ↓
enhance frames
    ↓
if cancelled, stop
    ↓
encode video
    ↓
if cancelled, stop
    ↓
set completed
```

Llamadas esperadas:

```python
extract_frames_for_job(db, job_id)
enhance_frames_for_job(db, job_id, engine=settings.frame_enhancer_engine)
encode_video_for_job(db, job_id)
```

Logs esperados:

```text
Video encoding started.
Encoding FPS: {fps}
Encoding codec: libx264
Video encoding completed.
Silent video generated: {encoded_video_path}
Audio mux and final export are not implemented yet.
```

---

# Endpoints nuevos o modificados

Endpoints existentes se mantienen.

Actualizar comportamiento de:

```text
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/logs
POST /api/jobs/{job_id}/cancel
POST /api/jobs/{job_id}/pause
```

Agregar:

```text
GET    /api/jobs/{job_id}/video-encoding
GET    /api/jobs/{job_id}/encoded-video
DELETE /api/jobs/{job_id}/encoded-video
```

---

## GET /api/jobs/{job_id}/progress

Actualizar response para incluir:

```text
encoded_dir
encoded_video_path
encoded_video_size_bytes
encoding_fps
encoding_codec
encoding_format
encoding_started_at
encoding_completed_at
```

Ejemplo:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "running",
  "current_stage": "encoding_video",
  "progress_percent": 86.4,
  "frames_total": 3080,
  "frames_processed": 1400,
  "extracted_frames": 3080,
  "enhanced_frames": 3080,
  "encoded_dir": "storage/temp/jobs/{job_id}/encoded",
  "encoded_video_path": null,
  "encoding_fps": 23.976,
  "encoding_codec": "h264",
  "encoding_format": "mp4",
  "error_code": null,
  "error_message": null
}
```

---

## GET /api/jobs/{job_id}/video-encoding

Devuelve resumen de encoding.

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "completed",
  "current_stage": "completed",
  "encoded_dir": "storage/temp/jobs/{job_id}/encoded",
  "encoded_video_path": "storage/temp/jobs/{job_id}/encoded/video_silent.mp4",
  "encoded_video_file_name": "video_silent.mp4",
  "encoded_video_size_bytes": 84500000,
  "encoding_fps": 23.976,
  "encoding_codec": "h264",
  "encoding_format": "mp4",
  "encoding_started_at": "2026-06-13T12:10:00",
  "encoding_completed_at": "2026-06-13T12:15:00",
  "encoding_error_code": null,
  "encoding_error_message": null
}
```

---

## GET /api/jobs/{job_id}/encoded-video

Devuelve metadata del archivo encoded temporal.

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "available": true,
  "path": "storage/temp/jobs/{job_id}/encoded/video_silent.mp4",
  "file_name": "video_silent.mp4",
  "size_bytes": 84500000,
  "format": "mp4",
  "codec": "h264",
  "has_audio": false
}
```

Si no existe:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "available": false,
  "path": null,
  "file_name": null,
  "size_bytes": null,
  "format": "mp4",
  "codec": "h264",
  "has_audio": false
}
```

---

## DELETE /api/jobs/{job_id}/encoded-video

Elimina el video encoded temporal.

Reglas:

* No permitir si el job está `running`.
* Eliminar únicamente:

```text
storage/temp/jobs/{job_id}/encoded/video_silent.mp4
```

* No eliminar frames originales.
* No eliminar frames enhanced.
* No eliminar video original.
* No eliminar exports futuros.
* Limpiar campos de encoding en DB.

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
class VideoEncodingSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    encoded_dir: str | None
    encoded_video_path: str | None
    encoded_video_file_name: str | None
    encoded_video_size_bytes: int | None
    encoding_fps: float | None
    encoding_codec: str | None
    encoding_format: str | None
    encoding_started_at: datetime | None
    encoding_completed_at: datetime | None
    encoding_error_code: str | None
    encoding_error_message: str | None


class EncodedVideoResponse(BaseModel):
    job_id: str
    available: bool
    path: str | None
    file_name: str | None
    size_bytes: int | None
    format: str
    codec: str
    has_audio: bool


class DeleteEncodedVideoResponse(BaseModel):
    deleted: bool
    job_id: str
```

Actualizar `JobResponse` para incluir:

```python
encoded_dir: str | None
encoded_video_path: str | None
encoded_video_file_name: str | None
encoded_video_size_bytes: int | None
encoding_fps: float | None
encoding_codec: str | None
encoding_format: str | None
encoding_started_at: datetime | None
encoding_completed_at: datetime | None
encoding_error_code: str | None
encoding_error_message: str | None
```

Actualizar `JobProgressResponse` con los mismos campos relevantes de encoding.

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class VideoEncodingFailedError(OroyaVideoError):
    pass


class EnhancedFramesRequiredError(OroyaVideoError):
    pass


class EncodedVideoNotFoundError(OroyaVideoError):
    pass
```

---

## Enhanced frames requeridos

Status:

```text
404
```

Response:

```json
{
  "error": "enhanced_frames_required",
  "message": "Enhanced frames are required before encoding video."
}
```

---

## Encoding fallido

Status:

```text
422
```

Response:

```json
{
  "error": "video_encoding_failed",
  "message": "Video could not be encoded from enhanced frames."
}
```

---

## Encoded video no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "encoded_video_not_found",
  "message": "Encoded video was not found for this job."
}
```

---

# Logging

Registrar en backend:

```text
Video encoding requested
Enhanced frames validated
Video encoding command built
Video encoding started
Video encoding progress updated
Video encoding completed
Video encoding failed
Video encoding cancelled
Encoded video summary requested
Encoded video metadata requested
Encoded video deleted
```

Registrar en logs del job:

```text
Video encoding started.
Encoding from enhanced frames.
Encoding FPS: {fps}
Encoding progress: {frame}/{enhanced_frames}
Video encoding completed.
Silent video generated.
Audio mux and final export are not implemented yet.
Video encoding failed: {reason}
Video encoding cancelled by user.
```

Para evitar spam:

```text
Registrar progreso cada 5% o cada 100 frames.
```

---

# Tests

Crear:

```text
tests/test_video_encoding.py
```

Los tests no deben depender de FFmpeg real ni videos reales.

Usar mocks para:

* `subprocess.Popen`
* `shutil.which`
* `Path.exists`
* `Path.glob`
* `Path.stat`
* `shutil.disk_usage`
* servicios de DB cuando sea necesario

Pruebas mínimas:

1. `build_video_encoding_command` genera comando con `ffmpeg`.
2. El comando incluye `-framerate`.
3. El comando incluye `-i`.
4. El comando incluye `libx264`.
5. El comando incluye `yuv420p`.
6. El comando incluye `-movflags +faststart`.
7. El comando incluye `-progress pipe:1`.
8. El comando no usa `shell=True`.
9. `resolve_encoding_fps` usa FPS del video asset.
10. `resolve_encoding_fps` usa fallback `30.0` si no existe FPS.
11. `parse_ffmpeg_encoding_progress_line("frame=120")` parsea correctamente.
12. `encode_video_for_job` falla si no hay frames enhanced.
13. `encode_video_for_job` falla si FFmpeg no existe.
14. `encode_video_for_job` valida espacio disponible.
15. `encode_video_for_job` actualiza `current_stage = encoding_video`.
16. `encode_video_for_job` actualiza `progress_percent` entre `75` y `100`.
17. `encode_video_for_job` guarda `encoded_video_path`.
18. `encode_video_for_job` marca timestamps de inicio y fin.
19. Worker ejecuta extracción, enhancement y encoding.
20. Worker marca `completed` después del encoding.
21. Worker marca `failed` si encoding falla.
22. Cancelación durante encoding marca `cancelled`.
23. `GET /api/jobs/{job_id}/video-encoding` devuelve resumen.
24. `GET /api/jobs/{job_id}/encoded-video` devuelve metadata si existe.
25. `DELETE /api/jobs/{job_id}/encoded-video` elimina solo el MP4 temporal.
26. `DELETE /api/jobs/{job_id}/encoded-video` no elimina frames.
27. `DELETE /api/jobs/{job_id}/encoded-video` no permite eliminar si job está running.
28. `POST /api/jobs/{job_id}/pause` responde `409` si está encoding.

---

# Actualizar README

Agregar sección:

```text
Video encoding pipeline
```

Documentar:

```text
GET    /api/jobs/{job_id}/video-encoding
GET    /api/jobs/{job_id}/encoded-video
DELETE /api/jobs/{job_id}/encoded-video
```

Actualizar descripción de:

```text
POST /api/jobs/{job_id}/start
```

Debe explicar que ahora ejecuta:

```text
1. Frame extraction
2. Mock frame enhancement
3. Video encoding from enhanced frames
```

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/{job_id}/start"
```

Consultar encoding:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/video-encoding"
```

Consultar video encoded:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/encoded-video"
```

Agregar nota:

```text
In this requirement, the backend generates a silent MP4 from enhanced frames. Audio mux and final export are not implemented yet.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe `video_encoding_service.py`.
* Existe carpeta `encoded` por job.
* El worker ejecuta extracción, enhancement y encoding.
* El job usa `current_stage = encoding_video` durante encoding.
* El backend usa frames de `frames/enhanced`.
* El backend genera `video_silent.mp4`.
* El video generado usa MP4.
* El video generado usa H264.
* El video generado usa `yuv420p`.
* El video generado usa FPS original o fallback controlado.
* El comando FFmpeg no usa `shell=True`.
* El progreso global llega a `100`.
* Se guardan timestamps de encoding.
* Se guardan campos de encoding en DB.
* La cancelación durante encoding está soportada.
* La pausa durante encoding responde error controlado.
* `GET /api/jobs/{job_id}/progress` incluye datos de encoding.
* `GET /api/jobs/{job_id}/video-encoding` devuelve resumen.
* `GET /api/jobs/{job_id}/encoded-video` devuelve metadata.
* `DELETE /api/jobs/{job_id}/encoded-video` limpia solo el MP4 temporal.
* Los logs de job reflejan el encoding.
* Los tests pasan.
* README documenta el flujo.
* No se implementa todavía mux de audio.
* No se implementa todavía export final a `storage/exports`.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Importar un video.
2. Crear un proyecto.
3. Crear un job.
4. Iniciar el job.
5. Extraer frames originales.
6. Generar frames enhanced con mock enhancer.
7. Codificar un MP4 silent desde frames enhanced.
8. Consultar progreso hasta `100`.
9. Consultar metadata del video encoded.
10. Encontrar el archivo en:

```text
storage/temp/jobs/{job_id}/encoded/video_silent.mp4
```

Flujo esperado:

```text
POST /api/videos/import
POST /api/projects
POST /api/jobs
POST /api/jobs/{job_id}/start
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/video-encoding
GET  /api/jobs/{job_id}/encoded-video
```

Este requerimiento deja preparado el backend para el siguiente paso: mux de audio original y exportación final.
