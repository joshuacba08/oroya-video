# REQ-011 - Audio Mux & Final Export

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
* Encoding de video silent desde frames enhanced.
* Archivo temporal `video_silent.mp4`.

---

# Objetivo

Implementar la etapa final del pipeline MVP de Oroya Video: mux de audio original y exportación final.

El backend debe tomar el video silent generado en:

```text
storage/temp/jobs/{job_id}/encoded/video_silent.mp4
```

y combinarlo con el audio del video original, generando un archivo final exportado en:

```text
storage/exports/{project_id}/{job_id}/
```

El resultado final debe ser un archivo MP4 H264 listo para que el usuario lo abra desde la UI.

---

# Contexto

Hasta este punto, el pipeline puede hacer:

```text
Video original
    ↓
Extract Frames
    ↓
Mock Frame Enhancement
    ↓
Enhanced Frames
    ↓
Encode Silent MP4
```

Este requerimiento agrega:

```text
Silent MP4
    ↓
Mux Original Audio
    ↓
Final Export
```

Pipeline completo esperado:

```text
Video original
    ↓
Probe Metadata
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
```

---

# Decisión MVP

El export final será:

```text
Formato: MP4
Video codec: H264
Audio: mantener audio original cuando sea compatible
```

Regla de audio:

```text
1. Si el video original tiene audio compatible con MP4, usar copy.
2. Si el copy falla por incompatibilidad, hacer fallback a AAC.
3. Si el video original no tiene audio, exportar video final sin audio.
```

Esto permite cumplir el objetivo de mantener audio original, pero sin romper el flujo cuando el input venga de MKV/MOV con codecs de audio problemáticos para MP4.

---

# Alcance de este requerimiento

Implementar:

1. Servicio de mux de audio.
2. Servicio de export final.
3. Carpeta final `storage/exports/{project_id}/{job_id}`.
4. Modelo ORM `ExportAsset`.
5. Repositorio de exports.
6. Registro del export final en SQLite.
7. Integración del mux/export dentro del worker.
8. Progreso durante mux/export.
9. Logs de job durante mux/export.
10. Cancelación durante mux/export.
11. Endpoints para consultar exports.
12. Endpoint para consultar export de un job.
13. Endpoint para eliminar export.
14. Endpoint para abrir carpeta de export, preparado para integración desktop.
15. Nuevos campos en `ProcessingJob`.
16. Tests con mocks.
17. Actualización del README.

No implementar todavía:

* H265.
* Batch exports.
* Export presets avanzados.
* Selección manual de bitrate.
* Exportación ProRes.
* Streaming.
* Upload a cloud.
* Real-ESRGAN real.
* Limpieza automática avanzada.
* Apertura real de archivos con APIs Tauri.

---

# Cambios conceptuales

## Antes

REQ-010 terminaba en:

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

## Ahora

REQ-011 debe cerrar el pipeline completo:

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
muxing_audio
  ↓
exporting
  ↓
completed
```

En este requerimiento, `completed` significa:

```text
El archivo final exportado fue generado y registrado correctamente.
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
muxing_audio
exporting
completed
failed
cancelled
```

Durante mux:

```text
status = running
current_stage = muxing_audio
```

Durante registro/copia final:

```text
status = running
current_stage = exporting
```

Al terminar correctamente:

```text
status = completed
current_stage = completed
progress_percent = 100
```

---

# Progreso global del job

Desde este requerimiento, el progreso global será:

```text
extracting_frames = 0% - 25%
enhancing_frames  = 25% - 60%
encoding_video    = 60% - 85%
muxing_audio      = 85% - 97%
exporting         = 97% - 100%
```

Reglas:

* Al terminar extracción: `progress_percent = 25`
* Al terminar enhancement: `progress_percent = 60`
* Al terminar encoding: `progress_percent = 85`
* Al terminar mux: `progress_percent = 97`
* Al registrar export: `progress_percent = 100`

---

# Nuevos campos en ProcessingJob

Actualizar:

```text
app/db/models.py
```

Agregar a `ProcessingJob`:

```text
muxed_video_path
muxed_video_file_name
muxed_video_size_bytes
audio_strategy
audio_codec
audio_mux_started_at
audio_mux_completed_at
audio_mux_error_code
audio_mux_error_message
export_id
final_export_path
final_export_file_name
final_export_size_bytes
export_started_at
export_completed_at
export_error_code
export_error_message
```

Tipos sugeridos:

```text
muxed_video_path             String nullable
muxed_video_file_name        String nullable
muxed_video_size_bytes       Integer nullable
audio_strategy               String nullable
audio_codec                  String nullable
audio_mux_started_at         DateTime nullable
audio_mux_completed_at       DateTime nullable
audio_mux_error_code         String nullable
audio_mux_error_message      Text nullable

export_id                    String nullable
final_export_path            String nullable
final_export_file_name       String nullable
final_export_size_bytes      Integer nullable
export_started_at            DateTime nullable
export_completed_at          DateTime nullable
export_error_code            String nullable
export_error_message         Text nullable
```

---

# Nuevo modelo ORM ExportAsset

Actualizar:

```text
app/db/models.py
```

Agregar:

```python
class ExportAsset(Base):
    __tablename__ = "export_assets"
```

Campos requeridos:

```text
id
project_id
job_id
video_asset_id
file_path
file_name
file_extension
file_size_bytes
file_size_mb
format
video_codec
audio_codec
has_audio
audio_strategy
resolution_label
width
height
fps
duration_seconds
duration_label
created_at
updated_at
```

Tipos sugeridos:

```text
id                 String primary key UUID
project_id          String ForeignKey projects.id not null
job_id              String ForeignKey processing_jobs.id not null
video_asset_id      String ForeignKey video_assets.id not null
file_path           String not null
file_name           String not null
file_extension      String not null
file_size_bytes     Integer not null
file_size_mb        Float not null
format              String not null
video_codec         String nullable
audio_codec         String nullable
has_audio           Boolean not null
audio_strategy      String nullable
resolution_label    String nullable
width               Integer nullable
height              Integer nullable
fps                 Float nullable
duration_seconds    Float nullable
duration_label      String nullable
created_at          DateTime not null
updated_at          DateTime not null
```

Relaciones sugeridas:

```python
project = relationship("Project")
job = relationship("ProcessingJob")
video_asset = relationship("VideoAsset")
```

---

# Paths

Actualizar:

```text
app/core/paths.py
```

Agregar funciones:

```python
def get_exports_path() -> Path:
    ...


def get_project_exports_path(project_id: str) -> Path:
    ...


def get_job_export_path(project_id: str, job_id: str) -> Path:
    ...


def get_job_muxed_video_path(job_id: str) -> Path:
    ...


def get_final_export_video_path(project_id: str, job_id: str, file_name: str) -> Path:
    ...


def ensure_job_export_directory(project_id: str, job_id: str) -> Path:
    ...
```

Estructura esperada:

```text
storage/
├── temp/
│   └── jobs/
│       └── {job_id}/
│           ├── frames/
│           ├── encoded/
│           │   └── video_silent.mp4
│           └── muxed/
│               └── video_with_audio.mp4
│
└── exports/
    └── {project_id}/
        └── {job_id}/
            └── oroya_export.mp4
```

---

# Nuevos servicios

Crear:

```text
app/services/audio_mux_service.py
app/services/export_service.py
```

---

# audio_mux_service.py

Responsabilidades:

1. Cargar job.
2. Validar que existe `video_silent.mp4`.
3. Resolver video original.
4. Detectar si el video original tiene audio.
5. Construir comando FFmpeg para mux.
6. Ejecutar mux con audio copy.
7. Si falla por codec incompatible, reintentar con AAC.
8. Si no hay audio, copiar silent MP4 como muxed.
9. Actualizar job.
10. Registrar logs.
11. Manejar cancelación.
12. Manejar errores.

Funciones sugeridas:

```python
def mux_audio_for_job(
    db: Session,
    job_id: str,
) -> ProcessingJob:
    ...


def resolve_original_video_path(job: ProcessingJob) -> Path:
    ...


def build_audio_copy_mux_command(
    silent_video_path: Path,
    original_video_path: Path,
    output_path: Path,
) -> list[str]:
    ...


def build_audio_aac_mux_command(
    silent_video_path: Path,
    original_video_path: Path,
    output_path: Path,
) -> list[str]:
    ...


def build_no_audio_mux_command(
    silent_video_path: Path,
    output_path: Path,
) -> list[str]:
    ...


def has_audio_stream(video_asset: VideoAsset) -> bool:
    ...


def get_muxed_video_summary(
    db: Session,
    job_id: str,
) -> AudioMuxSummaryResponse:
    ...


def delete_muxed_video(
    db: Session,
    job_id: str,
) -> DeleteMuxedVideoResponse:
    ...
```

---

# Comando FFmpeg - audio copy

Input 0:

```text
video_silent.mp4
```

Input 1:

```text
video original
```

Output:

```text
video_with_audio.mp4
```

Comando base:

```bash
ffmpeg \
  -hide_banner \
  -y \
  -i video_silent.mp4 \
  -i original.mp4 \
  -map 0:v:0 \
  -map 1:a:0? \
  -c:v copy \
  -c:a copy \
  -shortest \
  -movflags +faststart \
  -progress pipe:1 \
  -nostats \
  video_with_audio.mp4
```

En Python:

```python
[
    "ffmpeg",
    "-hide_banner",
    "-y",
    "-i",
    str(silent_video_path),
    "-i",
    str(original_video_path),
    "-map",
    "0:v:0",
    "-map",
    "1:a:0?",
    "-c:v",
    "copy",
    "-c:a",
    "copy",
    "-shortest",
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
* Leer progreso.
* Si falla, evaluar fallback AAC.
* Registrar stderr en logs internos, no completo al frontend.

---

# Comando FFmpeg - fallback AAC

Si falla audio copy, reintentar:

```bash
ffmpeg \
  -hide_banner \
  -y \
  -i video_silent.mp4 \
  -i original.mkv \
  -map 0:v:0 \
  -map 1:a:0? \
  -c:v copy \
  -c:a aac \
  -b:a 320k \
  -shortest \
  -movflags +faststart \
  -progress pipe:1 \
  -nostats \
  video_with_audio.mp4
```

En Python:

```python
[
    "ffmpeg",
    "-hide_banner",
    "-y",
    "-i",
    str(silent_video_path),
    "-i",
    str(original_video_path),
    "-map",
    "0:v:0",
    "-map",
    "1:a:0?",
    "-c:v",
    "copy",
    "-c:a",
    "aac",
    "-b:a",
    "320k",
    "-shortest",
    "-movflags",
    "+faststart",
    "-progress",
    "pipe:1",
    "-nostats",
    str(output_path),
]
```

Al usar fallback:

```text
audio_strategy = transcode_aac
audio_codec = aac
```

---

# Comando FFmpeg - sin audio

Si el video original no tiene audio:

```bash
ffmpeg \
  -hide_banner \
  -y \
  -i video_silent.mp4 \
  -map 0:v:0 \
  -c:v copy \
  -movflags +faststart \
  -progress pipe:1 \
  -nostats \
  video_with_audio.mp4
```

En este caso:

```text
audio_strategy = none
audio_codec = null
```

---

# export_service.py

Responsabilidades:

1. Cargar job.
2. Validar que existe video muxed.
3. Crear carpeta final de export.
4. Generar nombre final seguro.
5. Copiar o mover archivo muxed a exports.
6. Crear registro `ExportAsset`.
7. Actualizar job con `export_id` y rutas finales.
8. Actualizar estado del proyecto si aplica.
9. Consultar exports.
10. Eliminar exports.
11. Preparar endpoints para abrir archivo/carpeta.

Funciones sugeridas:

```python
def create_final_export_for_job(
    db: Session,
    job_id: str,
) -> ExportAsset:
    ...


def build_export_file_name(project: Project, job: ProcessingJob) -> str:
    ...


def copy_muxed_video_to_exports(
    muxed_video_path: Path,
    destination_path: Path,
) -> Path:
    ...


def get_export_by_id(
    db: Session,
    export_id: str,
) -> ExportAssetResponse:
    ...


def list_exports(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    project_id: str | None = None,
    job_id: str | None = None,
) -> ExportListResponse:
    ...


def get_export_for_job(
    db: Session,
    job_id: str,
) -> ExportAssetResponse:
    ...


def delete_export(
    db: Session,
    export_id: str,
    delete_file: bool = False,
) -> ExportDeleteResponse:
    ...
```

---

# Nombre del export final

Nombre recomendado:

```text
{project_name}_oroya_export.mp4
```

Reglas:

* Convertir a slug seguro.
* Evitar caracteres inválidos en Windows/macOS/Linux.
* Si ya existe, agregar sufijo incremental.

Ejemplos:

```text
anime_episode_01_oroya_export.mp4
anime_episode_01_oroya_export_2.mp4
anime_episode_01_oroya_export_3.mp4
```

---

# Copia vs mover

Para el MVP:

```text
Copiar muxed video a storage/exports
```

No mover.

Motivo:

* Mantener temporal para debugging.
* Evitar pérdida si falla el registro final.
* Facilitar re-export.

Usar:

```python
shutil.copy2(...)
```

---

# Validaciones antes de mux

Antes de mux:

1. El job existe.
2. El job no está cancelado.
3. FFmpeg está disponible.
4. Existe `encoded_video_path`.
5. Existe `video_silent.mp4`.
6. Existe video original si se requiere audio.
7. La carpeta `muxed` puede crearse.
8. Hay espacio suficiente en `storage/temp`.

---

# Validaciones antes de export final

Antes de export:

1. El job existe.
2. Existe muxed video.
3. El archivo muxed es un archivo válido.
4. Existe proyecto.
5. Existe video asset.
6. Existe carpeta `storage/exports`.
7. Hay espacio suficiente en `storage/exports`.
8. Si ya existe un export para el job, puede reemplazarse o crear uno nuevo según regla MVP.

Regla MVP:

```text
Un job puede tener un export principal.
Si se exporta de nuevo, crear nuevo archivo con sufijo incremental y actualizar export_id del job al último export.
```

---

# Control de espacio en disco

## Antes de mux

Regla:

```text
free_space_bytes >= encoded_video_size_bytes * 1.5
```

## Antes de export final

Regla:

```text
free_space_bytes >= muxed_video_size_bytes
```

Si no hay espacio:

```text
status = failed
current_stage = failed
error_code = insufficient_export_storage
error_message = Not enough storage space to create final export.
```

---

# Cancelación durante mux/export

Si el job está:

```text
running
current_stage = muxing_audio
```

o:

```text
running
current_stage = exporting
```

Entonces:

1. `POST /api/jobs/{job_id}/cancel` marca `cancel_requested = true`.
2. El servicio detecta cancelación.
3. Si FFmpeg está corriendo, terminar proceso.
4. Si está copiando export, abortar si es posible.
5. Marcar:

```text
status = cancelled
current_stage = cancelled
cancelled_at = now
```

6. Agregar log:

```text
Final export cancelled by user.
```

No borrar automáticamente archivos parciales en este requerimiento.

---

# Pausa

Pausar mux/export no será obligatorio.

Regla MVP:

* Si el job está `queued`, se puede pausar.
* Si está `running` en cualquier etapa pesada, responder `409`.

Mensaje:

```json
{
  "error": "job_pause_not_supported",
  "message": "Pausing during processing is not supported yet. Cancel the job instead."
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
enhance frames
    ↓
encode video
    ↓
mux audio
    ↓
create final export
    ↓
set completed
```

Llamadas esperadas:

```python
extract_frames_for_job(db, job_id)
enhance_frames_for_job(db, job_id, engine=settings.frame_enhancer_engine)
encode_video_for_job(db, job_id)
mux_audio_for_job(db, job_id)
create_final_export_for_job(db, job_id)
```

Al completar:

```text
status = completed
current_stage = completed
progress_percent = 100
completed_at = now
```

También actualizar proyecto:

```text
project.status = completed
project.updated_at = now
```

---

# Repository

Crear:

```text
app/db/repositories/export_repository.py
```

Funciones sugeridas:

```python
def create_export_asset(db: Session, data: dict) -> ExportAsset:
    ...


def get_export_by_id(db: Session, export_id: str) -> ExportAsset | None:
    ...


def get_exports_by_job_id(db: Session, job_id: str) -> list[ExportAsset]:
    ...


def list_exports(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    project_id: str | None = None,
    job_id: str | None = None,
) -> list[ExportAsset]:
    ...


def count_exports(
    db: Session,
    project_id: str | None = None,
    job_id: str | None = None,
) -> int:
    ...


def delete_export_asset(db: Session, export_asset: ExportAsset) -> None:
    ...
```

Reglas:

* Ordenar exports por `created_at DESC`.
* No eliminar job al eliminar export.
* No eliminar proyecto al eliminar export.
* `delete_file=false` por defecto para evitar borrar accidentalmente.

---

# Schemas nuevos

Crear o actualizar:

```text
app/schemas/export_schema.py
```

## ExportAssetResponse

```python
class ExportAssetResponse(BaseModel):
    id: str
    project_id: str
    job_id: str
    video_asset_id: str
    file_path: str
    file_name: str
    file_extension: str
    file_size_bytes: int
    file_size_mb: float
    format: str
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool
    audio_strategy: str | None
    resolution_label: str | None
    width: int | None
    height: int | None
    fps: float | None
    duration_seconds: float | None
    duration_label: str | None
    created_at: datetime
    updated_at: datetime
```

## ExportListResponse

```python
class ExportListResponse(BaseModel):
    items: list[ExportAssetResponse]
    total: int
```

## ExportDeleteResponse

```python
class ExportDeleteResponse(BaseModel):
    deleted: bool
    export_id: str
    file_deleted: bool
```

## ExportOpenResponse

```python
class ExportOpenResponse(BaseModel):
    export_id: str
    path: str
    available: bool
    message: str
```

---

# Schemas de job a actualizar

Actualizar:

```text
app/schemas/job_schema.py
```

Agregar:

```python
class AudioMuxSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    muxed_video_path: str | None
    muxed_video_file_name: str | None
    muxed_video_size_bytes: int | None
    audio_strategy: str | None
    audio_codec: str | None
    audio_mux_started_at: datetime | None
    audio_mux_completed_at: datetime | None
    audio_mux_error_code: str | None
    audio_mux_error_message: str | None


class FinalExportSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    export_id: str | None
    final_export_path: str | None
    final_export_file_name: str | None
    final_export_size_bytes: int | None
    export_started_at: datetime | None
    export_completed_at: datetime | None
    export_error_code: str | None
    export_error_message: str | None


class MuxedVideoResponse(BaseModel):
    job_id: str
    available: bool
    path: str | None
    file_name: str | None
    size_bytes: int | None
    format: str
    video_codec: str
    audio_codec: str | None
    has_audio: bool
    audio_strategy: str | None


class DeleteMuxedVideoResponse(BaseModel):
    deleted: bool
    job_id: str
```

Actualizar `JobResponse` y `JobProgressResponse` para incluir:

```python
muxed_video_path: str | None
muxed_video_file_name: str | None
muxed_video_size_bytes: int | None
audio_strategy: str | None
audio_codec: str | None
audio_mux_started_at: datetime | None
audio_mux_completed_at: datetime | None
audio_mux_error_code: str | None
audio_mux_error_message: str | None
export_id: str | None
final_export_path: str | None
final_export_file_name: str | None
final_export_size_bytes: int | None
export_started_at: datetime | None
export_completed_at: datetime | None
export_error_code: str | None
export_error_message: str | None
```

---

# Endpoints nuevos o modificados

## Jobs

Agregar bajo:

```text
/api/jobs
```

Rutas nuevas:

```text
GET    /api/jobs/{job_id}/audio-mux
GET    /api/jobs/{job_id}/muxed-video
DELETE /api/jobs/{job_id}/muxed-video
GET    /api/jobs/{job_id}/final-export
```

---

## GET /api/jobs/{job_id}/audio-mux

Devuelve resumen del mux de audio.

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "completed",
  "current_stage": "completed",
  "muxed_video_path": "storage/temp/jobs/{job_id}/muxed/video_with_audio.mp4",
  "muxed_video_file_name": "video_with_audio.mp4",
  "muxed_video_size_bytes": 90200000,
  "audio_strategy": "copy",
  "audio_codec": "aac",
  "audio_mux_started_at": "2026-06-13T12:15:00",
  "audio_mux_completed_at": "2026-06-13T12:16:00",
  "audio_mux_error_code": null,
  "audio_mux_error_message": null
}
```

---

## GET /api/jobs/{job_id}/muxed-video

Devuelve metadata del video muxed temporal.

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "available": true,
  "path": "storage/temp/jobs/{job_id}/muxed/video_with_audio.mp4",
  "file_name": "video_with_audio.mp4",
  "size_bytes": 90200000,
  "format": "mp4",
  "video_codec": "h264",
  "audio_codec": "aac",
  "has_audio": true,
  "audio_strategy": "copy"
}
```

---

## DELETE /api/jobs/{job_id}/muxed-video

Elimina solo el video muxed temporal.

Reglas:

* No permitir si job está `running`.
* No eliminar encoded silent video.
* No eliminar frames.
* No eliminar export final.
* Limpiar campos de mux en DB.

Response:

```json
{
  "deleted": true,
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003"
}
```

---

## GET /api/jobs/{job_id}/final-export

Devuelve resumen del export final asociado al job.

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "completed",
  "current_stage": "completed",
  "export_id": "a6d65572-9b21-41e5-8887-8cbaf2b3166a",
  "final_export_path": "storage/exports/{project_id}/{job_id}/anime_episode_01_oroya_export.mp4",
  "final_export_file_name": "anime_episode_01_oroya_export.mp4",
  "final_export_size_bytes": 90200000,
  "export_started_at": "2026-06-13T12:16:00",
  "export_completed_at": "2026-06-13T12:17:00",
  "export_error_code": null,
  "export_error_message": null
}
```

---

# Export endpoints

Crear:

```text
app/api/routes_exports.py
```

Rutas bajo:

```text
/api/exports
```

Endpoints:

```text
GET    /api/exports
GET    /api/exports/{export_id}
DELETE /api/exports/{export_id}
POST   /api/exports/{export_id}/open
POST   /api/exports/{export_id}/open-folder
```

---

## GET /api/exports

Lista exports.

Query params:

```text
limit: int = 50
offset: int = 0
project_id: str | None = None
job_id: str | None = None
```

Response:

```json
{
  "items": [],
  "total": 0
}
```

---

## GET /api/exports/{export_id}

Devuelve detalle de export.

Response:

```json
{
  "id": "a6d65572-9b21-41e5-8887-8cbaf2b3166a",
  "project_id": "f42109c4-33cb-48de-81db-d45f53238221",
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "video_asset_id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
  "file_path": "storage/exports/{project_id}/{job_id}/anime_episode_01_oroya_export.mp4",
  "file_name": "anime_episode_01_oroya_export.mp4",
  "file_extension": ".mp4",
  "file_size_bytes": 90200000,
  "file_size_mb": 86.02,
  "format": "mp4",
  "video_codec": "h264",
  "audio_codec": "aac",
  "has_audio": true,
  "audio_strategy": "copy",
  "resolution_label": "3840x2160",
  "width": 3840,
  "height": 2160,
  "fps": 23.976,
  "duration_seconds": 128.45,
  "duration_label": "00:02:08",
  "created_at": "2026-06-13T12:17:00",
  "updated_at": "2026-06-13T12:17:00"
}
```

---

## DELETE /api/exports/{export_id}

Elimina registro de export.

Query param:

```text
delete_file: bool = false
```

Reglas:

* Si `delete_file = false`, eliminar solo registro DB.
* Si `delete_file = true`, eliminar también archivo físico.
* No eliminar job.
* No eliminar proyecto.
* No eliminar video original.

Response:

```json
{
  "deleted": true,
  "export_id": "a6d65572-9b21-41e5-8887-8cbaf2b3166a",
  "file_deleted": false
}
```

---

## POST /api/exports/{export_id}/open

Preparado para integración desktop.

En este requerimiento no es obligatorio abrir el archivo realmente.

Debe validar que el archivo exista y devolver:

```json
{
  "export_id": "a6d65572-9b21-41e5-8887-8cbaf2b3166a",
  "path": "storage/exports/{project_id}/{job_id}/anime_episode_01_oroya_export.mp4",
  "available": true,
  "message": "Export file is available. Desktop open integration will be handled by Tauri."
}
```

---

## POST /api/exports/{export_id}/open-folder

Preparado para integración desktop.

Debe validar carpeta contenedora y devolver:

```json
{
  "export_id": "a6d65572-9b21-41e5-8887-8cbaf2b3166a",
  "path": "storage/exports/{project_id}/{job_id}",
  "available": true,
  "message": "Export folder is available. Desktop open integration will be handled by Tauri."
}
```

---

# Router

Actualizar:

```text
app/api/router.py
```

Debe incluir:

```text
/api/exports
```

Y las nuevas rutas de jobs:

```text
/api/jobs/{job_id}/audio-mux
/api/jobs/{job_id}/muxed-video
/api/jobs/{job_id}/final-export
```

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class AudioMuxFailedError(OroyaVideoError):
    pass


class MuxedVideoNotFoundError(OroyaVideoError):
    pass


class FinalExportFailedError(OroyaVideoError):
    pass


class ExportAssetNotFoundError(OroyaVideoError):
    pass


class InsufficientExportStorageError(OroyaVideoError):
    pass
```

---

## Audio mux fallido

Status:

```text
422
```

Response:

```json
{
  "error": "audio_mux_failed",
  "message": "Audio could not be muxed into the encoded video."
}
```

---

## Muxed video no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "muxed_video_not_found",
  "message": "Muxed video was not found for this job."
}
```

---

## Export fallido

Status:

```text
422
```

Response:

```json
{
  "error": "final_export_failed",
  "message": "Final export could not be created."
}
```

---

## Export no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "export_asset_not_found",
  "message": "Export asset was not found."
}
```

---

## Espacio insuficiente para export

Status:

```text
400
```

Response:

```json
{
  "error": "insufficient_export_storage",
  "message": "Not enough storage space to create final export."
}
```

---

# Logging

Registrar en backend:

```text
Audio mux requested
Audio stream detected
No audio stream detected
Audio copy mux started
Audio copy mux failed
AAC fallback mux started
AAC fallback mux completed
Audio mux completed
Audio mux cancelled
Final export requested
Final export directory prepared
Final export copied
Export asset created
Final export completed
Export listed
Export requested
Export deleted
Export open requested
Export folder open requested
```

Registrar en logs del job:

```text
Audio mux started.
Audio strategy: copy.
Audio copy failed. Retrying with AAC fallback.
Audio strategy: transcode_aac.
No audio stream detected. Exporting video without audio.
Audio mux completed.
Final export started.
Final export path: {path}
Final export completed.
Job completed successfully.
```

---

# Tests

Crear:

```text
tests/test_audio_mux_export.py
```

Los tests no deben depender de FFmpeg real ni videos reales.

Usar mocks para:

* `subprocess.Popen`
* `shutil.which`
* `Path.exists`
* `Path.stat`
* `shutil.disk_usage`
* `shutil.copy2`
* servicios de DB cuando sea necesario

Pruebas mínimas:

1. `build_audio_copy_mux_command` genera comando con dos inputs.
2. El comando usa `-map 0:v:0`.
3. El comando usa `-map 1:a:0?`.
4. El comando usa `-c:v copy`.
5. El comando usa `-c:a copy`.
6. El comando incluye `-shortest`.
7. El comando incluye `-movflags +faststart`.
8. El comando no usa `shell=True`.
9. `build_audio_aac_mux_command` usa `-c:a aac`.
10. `build_no_audio_mux_command` no mapea audio.
11. `mux_audio_for_job` falla si no existe `encoded_video_path`.
12. `mux_audio_for_job` usa audio copy si hay audio.
13. `mux_audio_for_job` usa fallback AAC si audio copy falla.
14. `mux_audio_for_job` genera muxed sin audio si el original no tiene audio.
15. `mux_audio_for_job` actualiza `current_stage = muxing_audio`.
16. `mux_audio_for_job` actualiza `audio_strategy`.
17. `mux_audio_for_job` guarda `muxed_video_path`.
18. `create_final_export_for_job` crea carpeta de export.
19. `create_final_export_for_job` copia muxed video a exports.
20. `create_final_export_for_job` crea registro `ExportAsset`.
21. `create_final_export_for_job` actualiza `job.export_id`.
22. Worker ejecuta extracción, enhancement, encoding, mux y export.
23. Worker marca job `completed`.
24. Worker actualiza proyecto a `completed`.
25. Cancelación durante mux marca `cancelled`.
26. Cancelación durante export marca `cancelled`.
27. `GET /api/jobs/{job_id}/audio-mux` devuelve resumen.
28. `GET /api/jobs/{job_id}/muxed-video` devuelve metadata.
29. `GET /api/jobs/{job_id}/final-export` devuelve resumen.
30. `GET /api/exports` lista exports.
31. `GET /api/exports/{export_id}` devuelve export.
32. `DELETE /api/exports/{export_id}` elimina registro sin borrar archivo por defecto.
33. `DELETE /api/exports/{export_id}?delete_file=true` elimina archivo si existe.
34. `POST /api/exports/{export_id}/open` valida existencia.
35. `POST /api/exports/{export_id}/open-folder` valida carpeta.

---

# Actualizar README

Agregar sección:

```text
Audio mux and final export
```

Documentar:

```text
GET    /api/jobs/{job_id}/audio-mux
GET    /api/jobs/{job_id}/muxed-video
DELETE /api/jobs/{job_id}/muxed-video
GET    /api/jobs/{job_id}/final-export
GET    /api/exports
GET    /api/exports/{export_id}
DELETE /api/exports/{export_id}
POST   /api/exports/{export_id}/open
POST   /api/exports/{export_id}/open-folder
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
4. Audio mux
5. Final export
```

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/{job_id}/start"
```

Consultar export final:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/final-export"
```

Listar exports:

```bash
curl "http://127.0.0.1:8000/api/exports"
```

Agregar nota:

```text
In this requirement, Oroya Video generates a final MP4 export. The visual enhancement still uses the mock enhancer until Real-ESRGAN is implemented.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe `audio_mux_service.py`.
* Existe `export_service.py`.
* Existe modelo ORM `ExportAsset`.
* Existe repositorio de exports.
* Existe router `routes_exports.py`.
* El worker ejecuta extracción, enhancement, encoding, mux y export.
* El job usa `current_stage = muxing_audio` durante mux.
* El job usa `current_stage = exporting` durante export final.
* Se genera `video_with_audio.mp4` temporal.
* Se genera archivo final en `storage/exports/{project_id}/{job_id}`.
* Si el video original tiene audio compatible, se usa `audio_strategy = copy`.
* Si audio copy falla, se usa `audio_strategy = transcode_aac`.
* Si no hay audio, se usa `audio_strategy = none`.
* Se crea registro `ExportAsset`.
* El job guarda `export_id`.
* El job guarda `final_export_path`.
* El proyecto se marca como `completed`.
* El progreso global llega a `100`.
* La cancelación durante mux/export está soportada.
* La pausa durante mux/export responde error controlado.
* `GET /api/jobs/{job_id}/audio-mux` funciona.
* `GET /api/jobs/{job_id}/muxed-video` funciona.
* `GET /api/jobs/{job_id}/final-export` funciona.
* `GET /api/exports` lista exports.
* `GET /api/exports/{export_id}` devuelve detalle.
* `DELETE /api/exports/{export_id}` elimina registro.
* `POST /api/exports/{export_id}/open` prepara integración desktop.
* `POST /api/exports/{export_id}/open-folder` prepara integración desktop.
* Los logs de job reflejan mux y export.
* Los tests pasan.
* README documenta el flujo.
* No se implementa todavía Real-ESRGAN real.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Importar un video.
2. Crear un proyecto.
3. Crear un job.
4. Iniciar el job.
5. Extraer frames.
6. Generar frames enhanced con mock enhancer.
7. Codificar video silent.
8. Hacer mux con audio original.
9. Crear export final.
10. Consultar el export desde la API.
11. Ver el archivo final en:

```text
storage/exports/{project_id}/{job_id}/
```

Flujo esperado:

```text
POST /api/videos/import
POST /api/projects
POST /api/jobs
POST /api/jobs/{job_id}/start
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/final-export
GET  /api/exports
GET  /api/exports/{export_id}
```

Con este requerimiento, el backend tiene por primera vez un pipeline MVP completo de extremo a extremo, aunque el enhancement visual todavía sea mock.
