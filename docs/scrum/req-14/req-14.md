# REQ-014 - Real-ESRGAN Batch Frame Enhancement

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
```

El backend ya debe tener:

* Pipeline completo usando `mock` enhancer.
* Registro local de modelos IA.
* Diagnóstico IA.
* Validación de PyTorch/CUDA.
* Validación de modelos Real-ESRGAN.
* Adapter preparado para Real-ESRGAN.
* Dry-run de Real-ESRGAN preparado o parcialmente funcional.
* Preview Before/After usando frames original/enhanced.
* Export final MP4 con audio.

---

# Objetivo

Implementar el procesamiento real de frames usando Real-ESRGAN.

Este requerimiento debe reemplazar el comportamiento mock cuando el engine seleccionado sea:

```text
realesrgan
```

El backend debe tomar los frames originales extraídos en:

```text
storage/temp/jobs/{job_id}/frames/original/
```

procesarlos con el modelo Real-ESRGAN seleccionado y guardar los resultados en:

```text
storage/temp/jobs/{job_id}/frames/enhanced/
```

El resto del pipeline debe continuar igual:

```text
Extract Frames
    ↓
Real-ESRGAN Enhancement
    ↓
Encode Video
    ↓
Mux Audio
    ↓
Final Export
```

---

# Contexto

Hasta ahora Oroya Video puede ejecutar un pipeline completo usando `MockFrameEnhancer`.

Ese pipeline valida:

* Extracción de frames.
* Generación de frames enhanced.
* Encoding de video.
* Mux de audio.
* Export final.
* Preview before/after.

Pero visualmente los frames enhanced son iguales a los originales porque el mock solo copia archivos.

Este requerimiento introduce la mejora real con IA.

---

# Decisión MVP

El procesamiento Real-ESRGAN será:

```text
secuencial
1 frame a la vez
1 modelo cargado por job
GPU si está disponible
CPU como fallback opcional
```

No implementar todavía:

* Batch inference complejo.
* Procesamiento paralelo multi-GPU.
* TensorRT.
* ONNX Runtime.
* Cola distribuida.
* Optimización avanzada de VRAM.
* Comparación simultánea de varios modelos.
* Marketplace de modelos.

La prioridad es estabilidad, no velocidad extrema.

---

# Engines soportados

El backend debe soportar:

```text
mock
realesrgan
```

Configuración:

```env
FRAME_ENHANCER_ENGINE=realesrgan
```

Reglas:

* Si `FRAME_ENHANCER_ENGINE=mock`, el pipeline debe seguir usando el mock.
* Si `FRAME_ENHANCER_ENGINE=realesrgan`, el pipeline debe usar Real-ESRGAN.
* Si Real-ESRGAN falla por entorno, modelo o CUDA, el job debe fallar con error controlado.
* No hacer fallback silencioso a mock durante un job real.
* Si se desea fallback a mock, debe ser configuración explícita futura.

---

# Alcance de este requerimiento

Implementar:

1. Procesamiento real de frames con Real-ESRGAN.
2. Carga de modelo por job.
3. Selección de modelo según `model_id` del job.
4. Selección de device `cuda` o `cpu`.
5. Procesamiento frame por frame.
6. Guardado de frames enhanced.
7. Progreso real durante enhancement.
8. Cancelación durante enhancement.
9. Manejo de errores CUDA/VRAM.
10. Manejo de errores por modelo faltante.
11. Manejo de errores por frame corrupto.
12. Logs técnicos por job.
13. Métricas básicas de rendimiento.
14. Endpoint de resumen Real-ESRGAN por job.
15. Tests con mocks.
16. Actualización del README.

No implementar todavía:

* Descarga automática de modelos.
* Entrenamiento personalizado.
* RIFE.
* GFPGAN.
* CodeFormer.
* BasicVSR++.
* Multi-model comparison.
* Benchmark visual.
* Optimización multi-GPU.
* Postprocesado avanzado.
* Corrección de color.
* Deblur.
* Face enhancement.

---

# Modelos soportados en MVP

Modelos esperados desde el registry:

```text
realesrgan-x2
realesrgan-x4
realesrgan-general
```

Mapeo esperado:

```text
realesrgan-x2       scale_factor = 2
realesrgan-x4       scale_factor = 4
realesrgan-general  restoration/general
```

Los archivos del modelo deben estar en:

```text
storage/models/realesrgan/
```

Ejemplo:

```text
storage/models/realesrgan/realesrgan-x2.pth
storage/models/realesrgan/realesrgan-x4.pth
storage/models/realesrgan/realesrgan-general.pth
```

---

# Cambios conceptuales

## Antes

El pipeline enhanced hacía esto:

```text
original frame
    ↓
copy
    ↓
enhanced frame
```

## Ahora

Con engine `realesrgan` hará esto:

```text
original frame
    ↓
load image
    ↓
Real-ESRGAN inference
    ↓
save enhanced PNG
```

El nombre del archivo debe conservarse.

Ejemplo:

```text
original/frame_00000480.png
enhanced/frame_00000480.png
```

---

# Progreso global

Se mantiene el progreso global definido en REQ-011:

```text
extracting_frames = 0% - 25%
enhancing_frames  = 25% - 60%
encoding_video    = 60% - 85%
muxing_audio      = 85% - 97%
exporting         = 97% - 100%
```

Durante Real-ESRGAN:

```text
stage_progress = enhanced_frames / extracted_frames
global_progress = 25 + stage_progress * 35
```

Ejemplo:

```text
0% de enhancement   → progress_percent = 25
50% de enhancement  → progress_percent = 42.5
100% enhancement    → progress_percent = 60
```

---

# Nuevos campos en ProcessingJob

Actualizar:

```text
app/db/models.py
```

Agregar a `ProcessingJob`:

```text
realesrgan_model_slug
realesrgan_model_path
realesrgan_device
realesrgan_scale
realesrgan_tile_size
realesrgan_tile_pad
realesrgan_pre_pad
realesrgan_half_precision
realesrgan_frames_total
realesrgan_frames_processed
realesrgan_failed_frames
realesrgan_average_frame_time_ms
realesrgan_started_at
realesrgan_completed_at
realesrgan_error_code
realesrgan_error_message
```

Tipos sugeridos:

```text
realesrgan_model_slug              String nullable
realesrgan_model_path              String nullable
realesrgan_device                  String nullable
realesrgan_scale                   Integer nullable
realesrgan_tile_size               Integer nullable
realesrgan_tile_pad                Integer nullable
realesrgan_pre_pad                 Integer nullable
realesrgan_half_precision          Boolean nullable
realesrgan_frames_total            Integer nullable
realesrgan_frames_processed        Integer not null default 0
realesrgan_failed_frames           Integer not null default 0
realesrgan_average_frame_time_ms   Integer nullable
realesrgan_started_at              DateTime nullable
realesrgan_completed_at            DateTime nullable
realesrgan_error_code              String nullable
realesrgan_error_message           Text nullable
```

---

# Configuración

Actualizar:

```text
app/core/config.py
```

Agregar o confirmar:

```python
frame_enhancer_engine: str = "mock"
ai_device: str = "auto"
ai_allow_cpu: bool = True
ai_half_precision: bool = True
realesrgan_tile_size: int = 0
realesrgan_tile_pad: int = 10
realesrgan_pre_pad: int = 0
realesrgan_max_failed_frames: int = 0
realesrgan_clear_cuda_cache: bool = True
```

Variables `.env`:

```env
FRAME_ENHANCER_ENGINE=realesrgan
AI_DEVICE=auto
AI_ALLOW_CPU=true
AI_HALF_PRECISION=true
REALESRGAN_TILE_SIZE=0
REALESRGAN_TILE_PAD=10
REALESRGAN_PRE_PAD=0
REALESRGAN_MAX_FAILED_FRAMES=0
REALESRGAN_CLEAR_CUDA_CACHE=true
```

---

# Reglas de device

Valores permitidos:

```text
auto
cuda
cpu
```

## auto

```text
Usar CUDA si está disponible.
Si CUDA no está disponible y AI_ALLOW_CPU=true, usar CPU.
Si CUDA no está disponible y AI_ALLOW_CPU=false, fallar.
```

## cuda

```text
Exigir CUDA.
Si CUDA no está disponible, fallar.
```

## cpu

```text
Usar CPU.
Advertir que el procesamiento será lento.
```

---

# Módulos a modificar

Actualizar:

```text
app/enhancers/realesrgan_enhancer.py
app/enhancers/registry.py
app/services/frame_enhancement_service.py
app/services/realesrgan_service.py
app/workers/job_runner.py
app/api/routes_ai_runtime.py
app/api/routes_jobs.py
app/schemas/job_schema.py
```

Crear si hace falta:

```text
app/utils/image_utils.py
app/utils/performance_utils.py
```

---

# RealESRGANFrameEnhancer

Actualizar:

```text
app/enhancers/realesrgan_enhancer.py
```

Debe implementar procesamiento real de múltiples frames.

Interfaz esperada:

```python
class RealESRGANFrameEnhancer(FrameEnhancer):
    name = "Real-ESRGAN Frame Enhancer"
    engine = "realesrgan"

    def enhance_frames(
        self,
        input_dir: Path,
        output_dir: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> int:
        ...
```

Pero además debe aceptar configuración de modelo y runtime.

Opción recomendada:

```python
class RealESRGANFrameEnhancer(FrameEnhancer):
    def __init__(
        self,
        model_path: Path,
        model_slug: str,
        device: str,
        scale: int | None,
        tile_size: int,
        tile_pad: int,
        pre_pad: int,
        half_precision: bool,
    ):
        ...
```

---

# Carga del modelo

Reglas:

1. Cargar modelo una sola vez por job.
2. No cargar el modelo por cada frame.
3. Validar que el archivo `.pth` exista antes de cargar.
4. Registrar tiempo de carga.
5. Si falla carga, marcar job como `failed`.

Errores posibles:

```text
model_file_not_found
model_load_failed
torch_not_available
cuda_not_available
cuda_out_of_memory
```

---

# Procesamiento por frame

Reglas:

1. Leer frames `.png` desde `input_dir`.
2. Ordenar por nombre.
3. Procesar uno por uno.
4. Guardar resultado en `output_dir`.
5. Mantener el mismo nombre de archivo.
6. No modificar frames originales.
7. Sobrescribir enhanced frame si ya existe.
8. Actualizar progreso después de cada frame.
9. Verificar cancelación entre frames.
10. Medir tiempo por frame.
11. Actualizar promedio de tiempo por frame.

---

# Manejo de errores por frame

Configuración:

```env
REALESRGAN_MAX_FAILED_FRAMES=0
```

Regla MVP:

```text
Por defecto, cualquier frame fallido detiene el job.
```

Si en el futuro se permite tolerancia:

```text
Permitir hasta N frames fallidos.
Registrar warnings.
Continuar.
```

Para este requerimiento:

* Implementar el campo y la lógica básica.
* Default `0`.
* Si un frame falla y `max_failed_frames = 0`, el job falla.
* Si `max_failed_frames > 0`, continuar hasta superar el límite.

---

# Manejo de VRAM

Durante procesamiento CUDA:

* Capturar errores de out of memory.
* Marcar error controlado.
* Registrar recomendación en logs.
* Si `realesrgan_clear_cuda_cache=true`, llamar limpieza de cache entre frames o al fallar.

Error esperado:

```json
{
  "error": "cuda_out_of_memory",
  "message": "CUDA ran out of memory while processing frames."
}
```

No hacer fallback automático a CPU si CUDA falla por VRAM en medio del job.

Motivo:

* Sería extremadamente lento.
* El resultado sería impredecible.
* El usuario debe decidir.

---

# Limpieza de memoria

Implementar función segura:

```python
def clear_cuda_cache_if_available() -> None:
    ...
```

Reglas:

* No fallar si torch no está instalado.
* No fallar si CUDA no está disponible.
* Usar solo si `realesrgan_clear_cuda_cache=true`.

---

# RealESRGAN Service

Actualizar:

```text
app/services/realesrgan_service.py
```

Funciones sugeridas:

```python
def prepare_realesrgan_context(
    db: Session,
    job: ProcessingJob,
) -> RealESRGANContext:
    ...


def process_realesrgan_frames_for_job(
    db: Session,
    job_id: str,
) -> ProcessingJob:
    ...


def get_realesrgan_job_summary(
    db: Session,
    job_id: str,
) -> RealESRGANJobSummaryResponse:
    ...


def validate_realesrgan_job_requirements(
    db: Session,
    job: ProcessingJob,
) -> None:
    ...
```

---

# RealESRGANContext

Crear schema interno o dataclass:

```python
@dataclass
class RealESRGANContext:
    model_slug: str
    model_path: Path
    device: str
    scale: int | None
    tile_size: int
    tile_pad: int
    pre_pad: int
    half_precision: bool
    input_dir: Path
    output_dir: Path
    total_frames: int
```

---

# Selección del modelo

El job tiene configuración congelada:

```json
{
  "model_id": "realesrgan-x4",
  "scale": "4x"
}
```

Reglas:

1. Leer `model_id` desde `job.enhancement_config`.
2. Validar que exista en `AIModel`.
3. Validar que esté habilitado.
4. Validar que esté instalado.
5. Validar archivo físico.
6. Resolver `scale_factor`.
7. Guardar campos Real-ESRGAN en job.

---

# Relación con frame_enhancement_service

Actualizar:

```text
app/services/frame_enhancement_service.py
```

Comportamiento:

```text
engine = mock
    usar MockFrameEnhancer

engine = realesrgan
    usar process_realesrgan_frames_for_job
```

El servicio debe seguir siendo el punto de entrada único para enhancement.

No duplicar lógica de estado en varios lugares.

---

# Worker

Actualizar:

```text
app/workers/job_runner.py
```

Debe seguir usando:

```python
enhance_frames_for_job(
    db,
    job_id,
    engine=settings.frame_enhancer_engine,
)
```

Cuando engine sea `realesrgan`, el worker debe:

1. Cambiar stage a `enhancing_frames`.
2. Ejecutar Real-ESRGAN.
3. Continuar con encoding.
4. Continuar con mux.
5. Continuar con final export.

Flujo completo:

```text
queued
  ↓
running / extracting_frames
  ↓
running / enhancing_frames
  ↓
running / encoding_video
  ↓
running / muxing_audio
  ↓
running / exporting
  ↓
completed
```

---

# Cancelación

Debe funcionar durante Real-ESRGAN.

Reglas:

1. `POST /api/jobs/{job_id}/cancel` marca `cancel_requested = true`.
2. El procesamiento revisa cancelación entre frames.
3. Si se detecta, detener antes del siguiente frame.
4. Marcar:

```text
status = cancelled
current_stage = cancelled
cancelled_at = now
```

5. Registrar log:

```text
Real-ESRGAN enhancement cancelled by user.
```

No eliminar automáticamente frames ya procesados.

---

# Pausa

Pausar Real-ESRGAN no será obligatorio.

Regla:

* Si el job está `running` y `current_stage = enhancing_frames`, responder `409`.

Mensaje:

```json
{
  "error": "job_pause_not_supported",
  "message": "Pausing during Real-ESRGAN enhancement is not supported yet. Cancel the job instead."
}
```

---

# Endpoints nuevos

Agregar bajo:

```text
/api/jobs/{job_id}
```

---

## GET /api/jobs/{job_id}/realesrgan

Devuelve resumen Real-ESRGAN del job.

### Response 200

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "status": "completed",
  "current_stage": "completed",
  "model_slug": "realesrgan-x4",
  "model_path": "storage/models/realesrgan/realesrgan-x4.pth",
  "device": "cuda",
  "scale": 4,
  "tile_size": 0,
  "tile_pad": 10,
  "pre_pad": 0,
  "half_precision": true,
  "frames_total": 3080,
  "frames_processed": 3080,
  "failed_frames": 0,
  "average_frame_time_ms": 185,
  "started_at": "2026-06-13T12:05:00",
  "completed_at": "2026-06-13T12:20:00",
  "error_code": null,
  "error_message": null
}
```

---

## POST /api/jobs/{job_id}/realesrgan/validate

Valida si un job está listo para ejecutar Real-ESRGAN.

### Response 200

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "ready": true,
  "model_slug": "realesrgan-x4",
  "model_installed": true,
  "input_frames_available": true,
  "device": "cuda",
  "estimated_vram_mb": 8192,
  "warnings": []
}
```

Si no está listo:

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "ready": false,
  "model_slug": "realesrgan-x4",
  "model_installed": false,
  "input_frames_available": true,
  "device": "cuda",
  "estimated_vram_mb": 8192,
  "warnings": [
    "Selected Real-ESRGAN model is not installed."
  ]
}
```

---

# Schemas nuevos

Actualizar o crear:

```text
app/schemas/realesrgan_schema.py
```

## RealESRGANJobSummaryResponse

```python
class RealESRGANJobSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    model_slug: str | None
    model_path: str | None
    device: str | None
    scale: int | None
    tile_size: int | None
    tile_pad: int | None
    pre_pad: int | None
    half_precision: bool | None
    frames_total: int | None
    frames_processed: int
    failed_frames: int
    average_frame_time_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
```

## RealESRGANJobValidationResponse

```python
class RealESRGANJobValidationResponse(BaseModel):
    job_id: str
    ready: bool
    model_slug: str | None
    model_installed: bool
    input_frames_available: bool
    device: str | None
    estimated_vram_mb: int | None
    warnings: list[str]
```

Actualizar `JobResponse` y `JobProgressResponse` para incluir:

```python
realesrgan_model_slug: str | None
realesrgan_device: str | None
realesrgan_frames_total: int | None
realesrgan_frames_processed: int
realesrgan_failed_frames: int
realesrgan_average_frame_time_ms: int | None
realesrgan_error_code: str | None
realesrgan_error_message: str | None
```

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class RealESRGANModelLoadFailedError(OroyaVideoError):
    pass


class RealESRGANFrameProcessingFailedError(OroyaVideoError):
    pass


class CUDAOutOfMemoryError(OroyaVideoError):
    pass


class RealESRGANJobNotReadyError(OroyaVideoError):
    pass


class RealESRGANUnsupportedModelError(OroyaVideoError):
    pass
```

---

## Modelo no listo

Status:

```text
409
```

Response:

```json
{
  "error": "realesrgan_job_not_ready",
  "message": "Real-ESRGAN job requirements are not satisfied."
}
```

---

## Fallo cargando modelo

Status:

```text
422
```

Response:

```json
{
  "error": "realesrgan_model_load_failed",
  "message": "Real-ESRGAN model could not be loaded."
}
```

---

## Fallo procesando frame

Status:

```text
422
```

Response:

```json
{
  "error": "realesrgan_frame_processing_failed",
  "message": "A frame could not be processed with Real-ESRGAN."
}
```

---

## CUDA out of memory

Status:

```text
507
```

Response:

```json
{
  "error": "cuda_out_of_memory",
  "message": "CUDA ran out of memory while processing frames."
}
```

---

# Logs del job

Registrar:

```text
Real-ESRGAN enhancement started.
Model: {model_slug}
Device: {device}
Scale: {scale}
Tile size: {tile_size}
Half precision: {half_precision}
Real-ESRGAN model loaded.
Real-ESRGAN progress: {processed}/{total}
Real-ESRGAN frame processed: {file_name}
Real-ESRGAN enhancement completed.
Average frame time: {average_frame_time_ms} ms
Real-ESRGAN enhancement cancelled by user.
Real-ESRGAN enhancement failed: {reason}
CUDA out of memory while processing frame: {file_name}
```

Para evitar spam:

```text
No registrar cada frame en nivel info.
Registrar cada frame en debug.
Registrar progreso cada 5% o cada 100 frames en info.
```

---

# Logs backend

Registrar:

```text
Real-ESRGAN job validation requested
Real-ESRGAN context prepared
Real-ESRGAN model file resolved
Real-ESRGAN device resolved
Real-ESRGAN model loading started
Real-ESRGAN model loading completed
Real-ESRGAN batch processing started
Real-ESRGAN batch processing completed
Real-ESRGAN batch processing failed
Real-ESRGAN CUDA cache cleared
```

---

# Tests

Crear:

```text
tests/test_realesrgan_batch.py
```

Los tests no deben depender de GPU real, PyTorch real ni modelos reales.

Usar mocks para:

* `torch`
* CUDA
* carga de modelo
* inferencia de frame
* `Path.exists`
* `Path.glob`
* `Path.stat`
* escritura de output
* DB/repositories

Pruebas mínimas:

1. `FRAME_ENHANCER_ENGINE=mock` mantiene el pipeline mock.
2. `FRAME_ENHANCER_ENGINE=realesrgan` usa RealESRGAN enhancer.
3. Valida que el modelo exista en registry.
4. Falla si el modelo no está instalado.
5. Falla si el archivo `.pth` no existe.
6. Falla si PyTorch no está disponible.
7. Falla si `AI_DEVICE=cuda` y CUDA no está disponible.
8. Usa CPU si `AI_DEVICE=auto`, CUDA no está disponible y `AI_ALLOW_CPU=true`.
9. Usa CUDA si `AI_DEVICE=auto` y CUDA está disponible.
10. Carga el modelo una sola vez por job.
11. Procesa frames en orden.
12. Mantiene nombres de archivo.
13. Guarda frames en `enhanced`.
14. Actualiza `enhanced_frames`.
15. Actualiza `realesrgan_frames_processed`.
16. Actualiza `progress_percent` entre 25 y 60.
17. Marca `realesrgan_started_at`.
18. Marca `realesrgan_completed_at`.
19. Calcula `average_frame_time_ms`.
20. Cancela entre frames si `cancel_requested=true`.
21. Marca job como `cancelled` al cancelar.
22. Marca job como `failed` si un frame falla y `max_failed_frames=0`.
23. Continúa si `max_failed_frames > 0` y no supera el límite.
24. Falla si supera `max_failed_frames`.
25. Maneja error CUDA OOM.
26. Limpia cache CUDA si está configurado.
27. `GET /api/jobs/{job_id}/realesrgan` devuelve resumen.
28. `POST /api/jobs/{job_id}/realesrgan/validate` devuelve ready true si todo está listo.
29. El worker continúa con encoding después de enhancement real.
30. El worker completa export final usando enhanced frames reales.

---

# Actualizar README

Agregar sección:

```text
Real-ESRGAN batch enhancement
```

Documentar configuración:

```env
FRAME_ENHANCER_ENGINE=realesrgan
AI_DEVICE=auto
AI_ALLOW_CPU=true
AI_HALF_PRECISION=true
REALESRGAN_TILE_SIZE=0
REALESRGAN_TILE_PAD=10
REALESRGAN_PRE_PAD=0
REALESRGAN_MAX_FAILED_FRAMES=0
REALESRGAN_CLEAR_CUDA_CACHE=true
```

Documentar endpoints:

```text
GET  /api/jobs/{job_id}/realesrgan
POST /api/jobs/{job_id}/realesrgan/validate
GET  /api/ai/runtime
GET  /api/ai/models/{model_slug}/validate
```

Agregar ejemplo:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/realesrgan"
```

Validar job:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/{job_id}/realesrgan/validate"
```

Ejecutar pipeline completo:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/{job_id}/start"
```

Agregar nota:

```text
Real-ESRGAN processing can be slow and memory-intensive.
For large videos, start with short clips during development.
If CUDA runs out of memory, reduce tile size or use a smaller model.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* `RealESRGANFrameEnhancer` procesa múltiples frames.
* El registry soporta `realesrgan`.
* `FRAME_ENHANCER_ENGINE=realesrgan` ejecuta enhancement real.
* El modelo se carga una sola vez por job.
* Se usa el modelo seleccionado por el proyecto/job.
* Se valida que el modelo esté instalado.
* Se valida runtime IA.
* Se resuelve device correctamente.
* Se procesan frames originales en orden.
* Se guardan frames enhanced con el mismo nombre.
* Se actualiza progreso entre 25% y 60%.
* Se actualizan métricas Real-ESRGAN en el job.
* Se soporta cancelación durante enhancement.
* Se manejan errores CUDA/VRAM.
* Se manejan errores de modelo faltante.
* Se manejan errores de frame corrupto.
* El worker continúa con encoding, mux y export final.
* El preview Before/After usa frames enhanced reales.
* Existen endpoints de resumen y validación Real-ESRGAN.
* Los tests pasan sin depender de GPU real.
* El README documenta configuración y uso.
* El pipeline mock sigue funcionando.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Instalar o colocar un modelo Real-ESRGAN en:

```text
storage/models/realesrgan/
```

2. Configurar:

```env
FRAME_ENHANCER_ENGINE=realesrgan
```

3. Importar un video.
4. Crear un proyecto usando `realesrgan-x2` o `realesrgan-x4`.
5. Crear un job.
6. Iniciar el job.
7. Extraer frames.
8. Procesar frames con Real-ESRGAN.
9. Codificar video.
10. Hacer mux de audio.
11. Crear export final.
12. Ver comparación Before/After con frames realmente mejorados.

Flujo esperado:

```text
POST /api/videos/import
POST /api/projects
POST /api/jobs
POST /api/jobs/{job_id}/realesrgan/validate
POST /api/jobs/{job_id}/start
GET  /api/jobs/{job_id}/progress
GET  /api/jobs/{job_id}/realesrgan
GET  /api/jobs/{job_id}/preview/recommended
GET  /api/jobs/{job_id}/final-export
```

Con este requerimiento, Oroya Video deja de ser un pipeline mock y pasa a tener procesamiento IA real con Real-ESRGAN.
