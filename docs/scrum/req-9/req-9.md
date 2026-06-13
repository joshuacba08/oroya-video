# REQ-009 - AI Frame Enhancement Pipeline

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
```

El backend ya debe tener:

* FastAPI funcional.
* SQLite inicializado.
* Sistema de paths.
* Logging.
* Detección de FFmpeg y FFprobe.
* Importación lógica de videos.
* CRUD de proyectos.
* Registro local de modelos IA.
* CRUD/control de jobs.
* Worker real para extracción de frames.
* Carpeta de frames originales por job.
* Carpeta de frames mejorados preparada.
* Progreso real durante extracción de frames.

---

# Objetivo

Implementar la segunda etapa real del pipeline de procesamiento de Oroya Video: mejora de frames mediante un sistema de enhancement extensible.

En este requerimiento se debe crear la arquitectura para procesar frames extraídos y generar frames mejorados en la carpeta `enhanced`.

Para mantener el avance seguro y testeable, la implementación inicial debe incluir un `MockFrameEnhancer`, que copia los frames originales hacia la carpeta de frames mejorados y simula el procesamiento IA actualizando progreso, estados y logs.

No se debe implementar todavía inferencia real con PyTorch ni Real-ESRGAN.
El objetivo es dejar lista la arquitectura para conectar Real-ESRGAN en el siguiente requerimiento sin rediseñar el pipeline.

---

# Contexto

Oroya Video procesará videos con este pipeline:

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

REQ-008 ya implementó:

```text
Video original
    ↓
Extract Frames
```

REQ-009 debe implementar:

```text
Original Frames
    ↓
Frame Enhancement
    ↓
Enhanced Frames
```

La salida esperada será:

```text
storage/temp/jobs/{job_id}/frames/enhanced/
├── frame_00000000.png
├── frame_00000001.png
├── frame_00000002.png
└── ...
```

---

# Decisión MVP

La primera implementación del enhancement será:

```text
mock
```

Esto significa:

* No altera visualmente los frames.
* Copia los frames originales a `enhanced`.
* Simula el tiempo de procesamiento.
* Actualiza progreso real por frame.
* Valida rutas, estados, cancelación y logs.
* Permite que el siguiente paso pueda reconstruir video usando `enhanced`.

El backend debe quedar preparado para futuros engines:

```text
mock
realesrgan
opencv
custom
```

---

# Alcance de este requerimiento

Implementar:

1. Interfaz base para frame enhancers.
2. `MockFrameEnhancer`.
3. Servicio de enhancement de frames.
4. Integración del enhancement dentro del worker.
5. Validación de frames originales existentes.
6. Generación de frames enhanced.
7. Progreso durante enhancement.
8. Cancelación durante enhancement.
9. Limpieza de frames enhanced.
10. Listado de frames enhanced.
11. Resumen de enhancement.
12. Logs del job durante enhancement.
13. Nuevos campos en `ProcessingJob`.
14. Tests con mocks.
15. Actualización del README.

No implementar todavía:

* PyTorch.
* Real-ESRGAN real.
* CUDA real.
* ONNX Runtime.
* OpenCV enhancement real.
* Reconstrucción de video.
* Mux de audio.
* Exportación final.
* Preview thumbnails.
* WebSocket.
* Server-Sent Events.
* Batch processing.

---

# Cambios conceptuales

## Antes

REQ-008 terminaba el job cuando la extracción de frames finalizaba:

```text
queued
  ↓
running
  ↓
extracting_frames
  ↓
completed
```

## Ahora

REQ-009 debe extender el worker:

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

Importante:

En este requerimiento, `completed` significa:

```text
La extracción de frames y el enhancement mock terminaron correctamente.
```

No significa todavía que exista un video final exportado.

El log del job debe dejar esto claro:

```text
Frame enhancement completed using mock enhancer. Video encoding and export are not implemented yet.
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
enhancing_frames
completed
failed
cancelled
```

Durante enhancement:

```text
status = running
current_stage = enhancing_frames
```

Al terminar correctamente:

```text
status = completed
current_stage = completed
progress_percent = 100
```

---

# Progreso global del job

Desde este requerimiento, el progreso del job debe considerar dos etapas:

```text
extracting_frames = 0% - 50%
enhancing_frames  = 50% - 100%
```

Reglas:

* Durante extracción de frames, el progreso máximo será `50`.
* Durante enhancement, el progreso irá de `50` a `100`.
* Si solo existe una etapa ejecutada, igual se debe respetar el progreso global.
* Al terminar enhancement, `progress_percent = 100`.

Ejemplo:

```text
Extracción 100% completada      → progress_percent = 50
Enhancement 50% completado      → progress_percent = 75
Enhancement 100% completado     → progress_percent = 100
```

---

# Nuevos campos en ProcessingJob

Actualizar modelo ORM:

```text
app/db/models.py
```

Agregar a `ProcessingJob`:

```text
enhancer_engine
enhanced_frames
enhancement_started_at
enhancement_completed_at
enhancement_error_code
enhancement_error_message
```

Tipos sugeridos:

```text
enhancer_engine                  String nullable default "mock"
enhanced_frames                  Integer not null default 0
enhancement_started_at           DateTime nullable
enhancement_completed_at         DateTime nullable
enhancement_error_code           String nullable
enhancement_error_message        Text nullable
```

---

# Paths

Ya deben existir desde REQ-008:

```text
storage/temp/jobs/{job_id}/frames/original
storage/temp/jobs/{job_id}/frames/enhanced
```

Confirmar o actualizar:

```text
app/core/paths.py
```

Funciones requeridas:

```python
def get_job_original_frames_path(job_id: str) -> Path:
    ...


def get_job_enhanced_frames_path(job_id: str) -> Path:
    ...


def ensure_job_directories(job_id: str) -> dict[str, Path]:
    ...
```

---

# Nuevos módulos

Agregar:

```text
app/enhancers/
├── __init__.py
├── base.py
├── mock_enhancer.py
└── registry.py
```

Agregar:

```text
app/services/frame_enhancement_service.py
```

---

# Enhancer base

Crear:

```text
app/enhancers/base.py
```

Definir una interfaz base:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[[int, int], None]


class FrameEnhancer(ABC):
    name: str
    engine: str

    @abstractmethod
    def enhance_frames(
        self,
        input_dir: Path,
        output_dir: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> int:
        ...
```

Reglas:

* `input_dir` contiene frames originales.
* `output_dir` recibirá frames mejorados.
* Debe devolver cantidad de frames procesados.
* `progress_callback(processed, total)` actualiza progreso.
* `cancel_callback()` permite detener procesamiento.

---

# MockFrameEnhancer

Crear:

```text
app/enhancers/mock_enhancer.py
```

Responsabilidad:

* Leer frames `.png` de `input_dir`.
* Copiarlos a `output_dir`.
* Mantener mismo nombre de archivo.
* Actualizar progreso por frame.
* Soportar cancelación.
* No modificar visualmente el frame.

Implementación esperada:

```python
class MockFrameEnhancer(FrameEnhancer):
    name = "Mock Frame Enhancer"
    engine = "mock"

    def enhance_frames(...):
        ...
```

Reglas:

* Usar `shutil.copy2`.
* Ordenar frames por nombre.
* Crear `output_dir` si no existe.
* Si el frame destino ya existe, puede sobrescribirse.
* No borrar frames originales.
* Si `cancel_callback()` retorna `True`, detener procesamiento.
* Si no hay frames originales, lanzar error controlado.

---

# Enhancer Registry

Crear:

```text
app/enhancers/registry.py
```

Responsabilidad:

* Resolver qué enhancer usar según engine.
* Por ahora solo soporta `mock`.
* Dejar preparado para `realesrgan`.

Funciones sugeridas:

```python
def get_frame_enhancer(engine: str) -> FrameEnhancer:
    ...
```

Comportamiento:

```text
engine = "mock"       → MockFrameEnhancer
engine = "realesrgan" → no implementado todavía
```

Si el engine no existe:

```json
{
  "error": "frame_enhancer_not_found",
  "message": "Frame enhancer was not found."
}
```

---

# Servicio de enhancement

Crear:

```text
app/services/frame_enhancement_service.py
```

Responsabilidades:

1. Cargar job.
2. Validar que el job tenga frames originales.
3. Validar que exista carpeta `original`.
4. Validar que exista carpeta `enhanced`.
5. Seleccionar engine.
6. Ejecutar enhancer.
7. Actualizar progreso.
8. Actualizar `enhanced_frames`.
9. Actualizar timestamps.
10. Registrar logs.
11. Manejar cancelación.
12. Manejar errores.

Funciones sugeridas:

```python
def enhance_frames_for_job(
    db: Session,
    job_id: str,
    engine: str = "mock",
) -> ProcessingJob:
    ...


def count_enhanced_frames(frames_dir: Path) -> int:
    ...


def list_enhanced_frames(
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    ...


def clean_enhanced_frames(job_id: str) -> None:
    ...
```

---

# Cálculo de progreso durante enhancement

El enhancement debe calcular progreso global:

```python
stage_progress = processed / total
global_progress = 50 + (stage_progress * 50)
```

Ejemplo:

```text
processed = 50
total = 100
stage_progress = 0.5
global_progress = 75
```

Actualizar job:

```text
frames_processed = processed
enhanced_frames = processed
progress_percent = global_progress
current_stage = enhancing_frames
```

Nota:

`frames_processed` puede representar el conteo de la etapa actual.
`extracted_frames` mantiene el total extraído.
`enhanced_frames` mantiene el total mejorado.

---

# Worker

Actualizar:

```text
app/workers/job_runner.py
```

Flujo esperado:

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
set completed
```

Más detallado:

```text
queued
  ↓
running / extracting_frames
  ↓
running / enhancing_frames
  ↓
completed
```

El worker debe llamar:

```python
extract_frames_for_job(db, job_id)
enhance_frames_for_job(db, job_id, engine="mock")
```

Por ahora, aunque el proyecto tenga `model_id = realesrgan-x2`, el engine real será:

```text
mock
```

Pero el log debe registrar:

```text
Requested model: realesrgan-x2
Enhancer engine: mock
```

---

# Configuración del engine

Agregar a configuración:

```text
app/core/config.py
```

Campo:

```python
frame_enhancer_engine: str = "mock"
```

Debe poder leerse desde `.env`:

```text
FRAME_ENHANCER_ENGINE=mock
```

Valores iniciales permitidos:

```text
mock
```

Preparar, pero no habilitar todavía:

```text
realesrgan
```

---

# Validaciones

Antes de iniciar enhancement:

1. El job existe.
2. El job no está cancelado.
3. `original_frames_dir` existe.
4. Hay frames `.png` en `original_frames_dir`.
5. `enhanced_frames_dir` existe o puede crearse.
6. El engine existe.
7. Hay espacio libre suficiente para copiar frames.

---

# Control de espacio en disco

Antes de copiar frames a `enhanced`, verificar espacio libre.

Regla inicial:

```text
free_space_bytes >= size_of_original_frames_dir
```

Implementar función utilitaria:

```python
def get_directory_size_bytes(path: Path) -> int:
    ...
```

Si no hay espacio:

```text
status = failed
current_stage = failed
error_code = insufficient_temp_storage
enhancement_error_code = insufficient_temp_storage
error_message = Not enough temporary storage space to enhance frames.
enhancement_error_message = Not enough temporary storage space to enhance frames.
```

---

# Cancelación

La cancelación debe funcionar durante enhancement.

Si el job está:

```text
running
current_stage = enhancing_frames
```

Entonces:

1. `POST /api/jobs/{job_id}/cancel` marca `cancel_requested = true`.
2. El enhancer revisa `cancel_callback`.
3. Se detiene el procesamiento.
4. Se marca:

```text
status = cancelled
current_stage = cancelled
cancelled_at = now
```

5. Se agrega log:

```text
Frame enhancement cancelled by user.
```

No borrar automáticamente los frames enhanced parciales.

---

# Pausa

Pausar enhancement real no será obligatorio en este requerimiento.

Regla MVP:

* Si el job está `queued`, se puede pausar.
* Si está `running` y `current_stage` es `extracting_frames` o `enhancing_frames`, responder `409`.

Respuesta:

```json
{
  "error": "job_pause_not_supported",
  "message": "Pausing during frame extraction or enhancement is not supported yet. Cancel the job instead."
}
```

---

# Endpoints nuevos o modificados

Los endpoints de jobs existentes se mantienen.

Actualizar comportamiento de:

```text
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/logs
POST /api/jobs/{job_id}/cancel
POST /api/jobs/{job_id}/pause
```

Agregar:

```text
GET    /api/jobs/{job_id}/enhanced-frames
GET    /api/jobs/{job_id}/frame-enhancement
DELETE /api/jobs/{job_id}/enhanced-frames
```

---

## GET /api/jobs/{job_id}/progress

Actualizar response para incluir:

```text
enhancer_engine
enhanced_frames
enhanced_frames_dir
enhancement_started_at
enhancement_completed_at
```

Ejemplo:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "running",
  "current_stage": "enhancing_frames",
  "progress_percent": 74.5,
  "frames_total": 3080,
  "frames_processed": 1509,
  "extracted_frames": 3080,
  "enhanced_frames": 1509,
  "enhancer_engine": "mock",
  "working_dir": "storage/temp/jobs/{job_id}",
  "original_frames_dir": "storage/temp/jobs/{job_id}/frames/original",
  "enhanced_frames_dir": "storage/temp/jobs/{job_id}/frames/enhanced",
  "error_code": null,
  "error_message": null
}
```

---

## GET /api/jobs/{job_id}/enhanced-frames

Lista frames mejorados para un job.

Query params:

```text
limit: int = 100
offset: int = 0
```

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "frames_dir": "storage/temp/jobs/b1dd73d0-ea57-4039-970d-597c7158a003/frames/enhanced",
  "items": [
    {
      "index": 0,
      "file_name": "frame_00000000.png",
      "path": "storage/temp/jobs/{job_id}/frames/enhanced/frame_00000000.png"
    },
    {
      "index": 1,
      "file_name": "frame_00000001.png",
      "path": "storage/temp/jobs/{job_id}/frames/enhanced/frame_00000001.png"
    }
  ],
  "total": 3080
}
```

---

## GET /api/jobs/{job_id}/frame-enhancement

Devuelve resumen de enhancement.

Response:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "completed",
  "current_stage": "completed",
  "enhancer_engine": "mock",
  "original_frames_dir": "storage/temp/jobs/{job_id}/frames/original",
  "enhanced_frames_dir": "storage/temp/jobs/{job_id}/frames/enhanced",
  "extracted_frames": 3080,
  "enhanced_frames": 3080,
  "enhancement_started_at": "2026-06-13T12:05:00",
  "enhancement_completed_at": "2026-06-13T12:10:00",
  "enhancement_error_code": null,
  "enhancement_error_message": null
}
```

---

## DELETE /api/jobs/{job_id}/enhanced-frames

Elimina solo frames enhanced.

Reglas:

* No permitir si el job está `running`.
* Eliminar únicamente:

```text
storage/temp/jobs/{job_id}/frames/enhanced
```

* Recrear carpeta vacía después de eliminarla.
* No eliminar frames originales.
* No eliminar video original.
* No eliminar exports.
* Marcar:

```text
enhanced_frames = 0
enhancement_started_at = null
enhancement_completed_at = null
enhancement_error_code = null
enhancement_error_message = null
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

Agregar o actualizar:

```python
class JobEnhancedFrameItem(BaseModel):
    index: int
    file_name: str
    path: str


class JobEnhancedFramesResponse(BaseModel):
    job_id: str
    frames_dir: str | None
    items: list[JobEnhancedFrameItem]
    total: int


class FrameEnhancementSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    enhancer_engine: str | None
    original_frames_dir: str | None
    enhanced_frames_dir: str | None
    extracted_frames: int
    enhanced_frames: int
    enhancement_started_at: datetime | None
    enhancement_completed_at: datetime | None
    enhancement_error_code: str | None
    enhancement_error_message: str | None


class DeleteEnhancedFramesResponse(BaseModel):
    deleted: bool
    job_id: str
```

Actualizar `JobResponse` para incluir:

```python
enhancer_engine: str | None
enhanced_frames: int
enhancement_started_at: datetime | None
enhancement_completed_at: datetime | None
enhancement_error_code: str | None
enhancement_error_message: str | None
```

Actualizar `JobProgressResponse` para incluir:

```python
enhancer_engine: str | None
enhanced_frames: int
enhanced_frames_dir: str | None
enhancement_started_at: datetime | None
enhancement_completed_at: datetime | None
```

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class FrameEnhancerNotFoundError(OroyaVideoError):
    pass


class FrameEnhancementFailedError(OroyaVideoError):
    pass


class OriginalFramesNotFoundError(OroyaVideoError):
    pass


class EnhancedFramesNotFoundError(OroyaVideoError):
    pass
```

---

## Enhancer no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "frame_enhancer_not_found",
  "message": "Frame enhancer was not found."
}
```

---

## Frames originales no encontrados

Status:

```text
404
```

Response:

```json
{
  "error": "original_frames_not_found",
  "message": "No original frames were found for this job."
}
```

---

## Enhancement fallido

Status:

```text
422
```

Response:

```json
{
  "error": "frame_enhancement_failed",
  "message": "Frames could not be enhanced."
}
```

---

## Frames enhanced no encontrados

Status:

```text
404
```

Response:

```json
{
  "error": "enhanced_frames_not_found",
  "message": "No enhanced frames were found for this job."
}
```

---

# Logging

Registrar en backend:

```text
Frame enhancement requested
Frame enhancer resolved
Mock frame enhancement started
Frame enhancement progress updated
Frame enhancement completed
Frame enhancement failed
Frame enhancement cancelled
Enhanced frames counted
Enhanced frames listed
Enhanced frames deleted
```

Registrar en logs del job:

```text
Frame enhancement started.
Requested model: {model_slug}
Enhancer engine: mock
Frame enhancement progress: {enhanced_frames}/{extracted_frames}
Frame enhancement completed using mock enhancer.
Video encoding and export are not implemented yet.
Frame enhancement failed: {reason}
Frame enhancement cancelled by user.
```

Para evitar spam:

```text
Registrar progreso cada 5% o cada 100 frames.
```

---

# Tests

Crear:

```text
tests/test_frame_enhancement.py
```

Los tests no deben depender de PyTorch, Real-ESRGAN ni videos reales.

Usar mocks para:

* `Path.exists`
* `Path.glob`
* `shutil.copy2`
* `shutil.disk_usage`
* Servicios de DB cuando sea necesario

Pruebas mínimas:

1. `get_frame_enhancer("mock")` devuelve `MockFrameEnhancer`.
2. `get_frame_enhancer("unknown")` lanza error controlado.
3. `MockFrameEnhancer` copia frames de original a enhanced.
4. `MockFrameEnhancer` mantiene nombres de archivos.
5. `MockFrameEnhancer` llama `progress_callback`.
6. `MockFrameEnhancer` se detiene si `cancel_callback` retorna `True`.
7. `enhance_frames_for_job` falla si no hay frames originales.
8. `enhance_frames_for_job` valida espacio disponible.
9. `enhance_frames_for_job` actualiza `current_stage = enhancing_frames`.
10. `enhance_frames_for_job` actualiza `enhanced_frames`.
11. `enhance_frames_for_job` actualiza `progress_percent` entre `50` y `100`.
12. `enhance_frames_for_job` marca timestamps de inicio y fin.
13. Worker ejecuta extracción y luego enhancement.
14. Worker marca `completed` después del mock enhancement.
15. Worker marca `failed` si enhancement falla.
16. `POST /api/jobs/{job_id}/cancel` cancela durante enhancement.
17. `GET /api/jobs/{job_id}/progress` incluye campos de enhancement.
18. `GET /api/jobs/{job_id}/enhanced-frames` lista frames enhanced.
19. `GET /api/jobs/{job_id}/frame-enhancement` devuelve resumen.
20. `DELETE /api/jobs/{job_id}/enhanced-frames` elimina solo enhanced.
21. `DELETE /api/jobs/{job_id}/enhanced-frames` no elimina originales.
22. `DELETE /api/jobs/{job_id}/enhanced-frames` no permite borrar si job está running.
23. `POST /api/jobs/{job_id}/pause` responde `409` si está enhancing.

---

# Actualizar README

Agregar sección:

```text
Frame enhancement pipeline
```

Documentar:

```text
GET    /api/jobs/{job_id}/enhanced-frames
GET    /api/jobs/{job_id}/frame-enhancement
DELETE /api/jobs/{job_id}/enhanced-frames
```

Actualizar la descripción de:

```text
POST /api/jobs/{job_id}/start
```

Debe explicar que ahora ejecuta:

```text
1. Frame extraction
2. Mock frame enhancement
```

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/{job_id}/start"
```

Consultar enhanced frames:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/enhanced-frames"
```

Agregar nota:

```text
In this requirement, enhanced frames are generated using a mock enhancer that copies original frames. Real-ESRGAN inference is not implemented yet.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe módulo `app/enhancers`.
* Existe interfaz base `FrameEnhancer`.
* Existe `MockFrameEnhancer`.
* Existe enhancer registry.
* Existe `frame_enhancement_service.py`.
* El worker ejecuta extracción y luego enhancement.
* El job usa `current_stage = enhancing_frames` durante enhancement.
* El job actualiza `enhanced_frames`.
* El job actualiza progreso entre `50` y `100`.
* El job guarda timestamps de enhancement.
* Se generan frames en `storage/temp/jobs/{job_id}/frames/enhanced`.
* Los frames enhanced conservan el mismo nombre que los originales.
* La cancelación durante enhancement está soportada.
* La pausa durante enhancement responde error controlado.
* `GET /api/jobs/{job_id}/progress` incluye datos de enhancement.
* `GET /api/jobs/{job_id}/enhanced-frames` lista frames enhanced.
* `GET /api/jobs/{job_id}/frame-enhancement` devuelve resumen.
* `DELETE /api/jobs/{job_id}/enhanced-frames` limpia solo enhanced.
* Los logs de job reflejan el enhancement.
* Los tests pasan.
* README documenta el flujo.
* No se implementa todavía Real-ESRGAN real.
* No se implementa todavía reconstrucción/exportación de video.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Importar un video.
2. Crear un proyecto.
3. Crear un job.
4. Iniciar el job.
5. Extraer frames originales.
6. Ejecutar mock enhancement.
7. Generar frames enhanced.
8. Ver progreso hasta `100`.
9. Consultar frames enhanced por API.
10. Cancelar el job durante enhancement si sigue en curso.

Flujo esperado:

```text
POST /api/videos/import
POST /api/projects
POST /api/jobs
POST /api/jobs/{job_id}/start
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/frames
GET  /api/jobs/{job_id}/enhanced-frames
GET  /api/jobs/{job_id}/frame-enhancement
```

Este requerimiento deja preparado el backend para el siguiente paso: reconstrucción de video usando los frames enhanced.
