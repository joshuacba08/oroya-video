# REQ-013 - Real-ESRGAN Integration Preparation

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
```

El backend ya debe tener:

* Pipeline completo con mock enhancement.
* Registro local de modelos IA.
* Carpeta `storage/models`.
* Sistema de jobs.
* Worker real.
* Extracción de frames.
* Frames enhanced generados por mock.
* Export final MP4.
* Preview before/after por API.

---

# Objetivo

Preparar la integración real de Real-ESRGAN dentro del backend de Oroya Video.

Este requerimiento no debe implementar todavía procesamiento completo de todos los frames con Real-ESRGAN en producción.

El objetivo es crear la base técnica necesaria para que el siguiente requerimiento pueda reemplazar el `MockFrameEnhancer` por un `RealESRGANFrameEnhancer` real de forma segura, testeable y reversible.

Se debe implementar:

1. Detección de dependencias IA.
2. Detección de PyTorch.
3. Detección de CUDA desde Python.
4. Validación de modelos Real-ESRGAN instalados.
5. Configuración del engine `realesrgan`.
6. Adapter base para Real-ESRGAN.
7. Dry-run sobre un frame individual.
8. Endpoints de diagnóstico IA.
9. Errores controlados.
10. Tests sin depender de GPU real.

---

# Contexto

Oroya Video ya tiene un pipeline funcional:

```text
Video original
    ↓
Extract Frames
    ↓
Mock Enhancement
    ↓
Encode Video
    ↓
Mux Audio
    ↓
Final Export
```

Ahora se necesita preparar el cambio hacia:

```text
Video original
    ↓
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

Antes de procesar miles de frames con IA real, el backend debe ser capaz de responder preguntas como:

* ¿Está PyTorch instalado?
* ¿Está CUDA disponible?
* ¿Qué dispositivo se usará?
* ¿Existe el archivo `.pth` del modelo?
* ¿El modelo seleccionado está instalado?
* ¿Puede cargarse el modelo?
* ¿Puede procesarse un frame de prueba?
* ¿Qué error ocurrió si no puede ejecutarse?

---

# Decisión MVP

El engine por defecto seguirá siendo:

```text
mock
```

El engine `realesrgan` quedará preparado, pero no será el default todavía.

Configuración:

```env
FRAME_ENHANCER_ENGINE=mock
```

Para pruebas manuales:

```env
FRAME_ENHANCER_ENGINE=realesrgan
```

En este requerimiento, `realesrgan` solo debe soportar:

* Validación de entorno.
* Validación de modelo.
* Carga controlada.
* Dry-run sobre un frame individual.
* Preparación del adapter.

El procesamiento masivo de todos los frames se implementará en el siguiente requerimiento.

---

# Alcance de este requerimiento

Implementar:

1. Servicio de diagnóstico IA.
2. Detección de PyTorch.
3. Detección de CUDA.
4. Detección de dispositivo disponible.
5. Validación de archivos `.pth`.
6. Adapter inicial `RealESRGANFrameEnhancer`.
7. Registro del engine `realesrgan`.
8. Endpoint de health IA.
9. Endpoint para validar modelo.
10. Endpoint para dry-run de un frame.
11. Configuración para seleccionar device.
12. Manejo de errores IA.
13. Logs técnicos.
14. Tests con mocks.
15. Actualización del README.

No implementar todavía:

* Procesamiento completo de todos los frames con Real-ESRGAN.
* Optimización de tiles.
* Batch inference.
* Procesamiento paralelo GPU.
* Descarga automática de modelos.
* Marketplace.
* ONNX Runtime.
* TensorRT.
* Half precision obligatorio.
* Benchmark completo.
* Gestión avanzada de VRAM.

---

# Estructura a modificar

Agregar o actualizar:

```text
backend/
├── app/
│   ├── api/
│   │   ├── router.py
│   │   └── routes_ai_runtime.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   └── errors.py
│   │
│   ├── enhancers/
│   │   ├── base.py
│   │   ├── mock_enhancer.py
│   │   ├── realesrgan_enhancer.py
│   │   └── registry.py
│   │
│   ├── schemas/
│   │   └── ai_runtime_schema.py
│   │
│   ├── services/
│   │   ├── ai_runtime_service.py
│   │   ├── ai_model_service.py
│   │   └── realesrgan_service.py
│   │
│   └── utils/
│       └── image_utils.py
│
├── tests/
│   └── test_realesrgan_preparation.py
│
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

# Dependencias opcionales

Este requerimiento debe preparar dependencias IA, pero sin romper instalaciones donde no exista GPU.

Agregar dependencias como opcionales o documentadas.

Dependencias base sugeridas para modo IA:

```text
torch
torchvision
numpy
Pillow
```

Dependencias Real-ESRGAN futuras:

```text
realesrgan
basicsr
```

Importante:

* El backend debe poder arrancar aunque estas dependencias no estén instaladas.
* Si faltan dependencias IA, los endpoints deben responder estado `available: false`.
* No debe fallar `/api/health`.
* No debe fallar `/api/system/info`.
* No debe fallar el pipeline mock.

---

# Configuración

Actualizar:

```text
app/core/config.py
```

Agregar settings:

```python
frame_enhancer_engine: str = "mock"
ai_device: str = "auto"
ai_allow_cpu: bool = True
ai_half_precision: bool = True
realesrgan_tile_size: int = 0
realesrgan_tile_pad: int = 10
realesrgan_pre_pad: int = 0
```

Variables `.env`:

```env
FRAME_ENHANCER_ENGINE=mock
AI_DEVICE=auto
AI_ALLOW_CPU=true
AI_HALF_PRECISION=true
REALESRGAN_TILE_SIZE=0
REALESRGAN_TILE_PAD=10
REALESRGAN_PRE_PAD=0
```

Valores permitidos para `AI_DEVICE`:

```text
auto
cpu
cuda
```

Reglas:

* `auto`: usar CUDA si está disponible, si no CPU.
* `cuda`: exigir CUDA disponible.
* `cpu`: usar CPU.
* Si `AI_ALLOW_CPU=false` y CUDA no está disponible, Real-ESRGAN no debe ejecutarse.
* Si `FRAME_ENHANCER_ENGINE=mock`, no se debe exigir PyTorch.

---

# AI Runtime Service

Crear:

```text
app/services/ai_runtime_service.py
```

Responsabilidades:

1. Detectar PyTorch.
2. Detectar versión de PyTorch si está disponible.
3. Detectar CUDA desde PyTorch.
4. Detectar número de GPUs desde PyTorch.
5. Detectar nombre de GPU si es posible.
6. Resolver device final.
7. Reportar si el runtime IA está listo.
8. No romper si PyTorch no está instalado.

Funciones sugeridas:

```python
def get_ai_runtime_status() -> AIRuntimeStatusResponse:
    ...


def is_torch_available() -> bool:
    ...


def get_torch_version() -> str | None:
    ...


def is_cuda_available() -> bool:
    ...


def get_cuda_device_count() -> int:
    ...


def get_cuda_devices() -> list[AICudaDeviceInfo]:
    ...


def resolve_ai_device(preferred_device: str = "auto") -> str:
    ...
```

---

# Reglas de imports IA

Los imports de PyTorch deben hacerse de forma lazy.

No hacer esto globalmente:

```python
import torch
```

Preferir:

```python
try:
    import torch
except ImportError:
    torch = None
```

o dentro de funciones.

Objetivo:

```text
El backend debe iniciar aunque torch no esté instalado.
```

---

# Schemas

Crear:

```text
app/schemas/ai_runtime_schema.py
```

## AICudaDeviceInfo

```python
class AICudaDeviceInfo(BaseModel):
    index: int
    name: str | None
    memory_total_mb: int | None = None
```

## AIRuntimeStatusResponse

```python
class AIRuntimeStatusResponse(BaseModel):
    available: bool
    torch_available: bool
    torch_version: str | None
    cuda_available: bool
    cuda_device_count: int
    cuda_devices: list[AICudaDeviceInfo]
    selected_device: str | None
    allow_cpu: bool
    half_precision: bool
    warnings: list[str]
```

## AIModelValidationResponse

```python
class AIModelValidationResponse(BaseModel):
    model_slug: str
    exists_in_registry: bool
    is_enabled: bool
    is_installed: bool
    file_path: str | None
    file_exists: bool
    file_size_bytes: int | None
    estimated_vram_mb: int | None
    runtime_available: bool
    can_run: bool
    device: str | None
    warnings: list[str]
```

## RealESRGANDryRunRequest

```python
class RealESRGANDryRunRequest(BaseModel):
    model_slug: str
    input_frame_path: str | None = None
    job_id: str | None = None
    frame_index: int | None = None
```

Reglas:

* Se puede enviar `input_frame_path` directamente para pruebas locales.
* O se puede enviar `job_id + frame_index` para usar un frame original extraído.
* Si se envían ambos, priorizar `input_frame_path`.
* Si no se envía ninguno, responder error controlado.

## RealESRGANDryRunResponse

```python
class RealESRGANDryRunResponse(BaseModel):
    success: bool
    model_slug: str
    engine: str
    device: str | None
    input_frame_path: str
    output_frame_path: str | None
    elapsed_time_ms: int | None
    message: str
    warnings: list[str]
```

---

# RealESRGAN Service

Crear:

```text
app/services/realesrgan_service.py
```

Responsabilidades:

1. Validar modelo Real-ESRGAN.
2. Resolver path del modelo.
3. Resolver device.
4. Preparar carpeta de prueba.
5. Ejecutar dry-run sobre un frame.
6. Manejar errores de dependencias.
7. Manejar errores de CUDA.
8. Manejar errores de modelo faltante.
9. No procesar frames masivamente todavía.

Funciones sugeridas:

```python
def validate_realesrgan_model(
    db: Session,
    model_slug: str,
) -> AIModelValidationResponse:
    ...


def resolve_realesrgan_model_path(
    db: Session,
    model_slug: str,
) -> Path:
    ...


def run_realesrgan_dry_run(
    db: Session,
    request: RealESRGANDryRunRequest,
) -> RealESRGANDryRunResponse:
    ...


def resolve_dry_run_input_frame(
    db: Session,
    request: RealESRGANDryRunRequest,
) -> Path:
    ...
```

---

# RealESRGANFrameEnhancer Adapter

Crear:

```text
app/enhancers/realesrgan_enhancer.py
```

Debe implementar la interfaz base:

```python
class RealESRGANFrameEnhancer(FrameEnhancer):
    name = "Real-ESRGAN Frame Enhancer"
    engine = "realesrgan"

    def enhance_frames(...):
        ...
```

En este requerimiento, `enhance_frames` no debe ejecutar todavía todos los frames.

Debe hacer una de estas dos opciones aceptadas:

## Opción A - no implementado controlado

```python
raise RealESRGANEnhancementNotImplementedError(...)
```

## Opción B - dry-run only

Permitir procesar un solo frame si se llama desde dry-run, pero no desde el pipeline masivo.

Recomendación MVP:

```text
Implementar adapter con método interno `enhance_single_frame`, pero dejar `enhance_frames` bloqueado para procesamiento masivo hasta REQ-014.
```

Funciones sugeridas:

```python
def enhance_single_frame(
    self,
    input_path: Path,
    output_path: Path,
    model_path: Path,
    device: str,
) -> Path:
    ...
```

Si las dependencias no están instaladas:

```text
Responder error controlado.
```

---

# Enhancer Registry

Actualizar:

```text
app/enhancers/registry.py
```

Debe soportar:

```text
mock
realesrgan
```

Comportamiento:

```python
get_frame_enhancer("mock")       -> MockFrameEnhancer
get_frame_enhancer("realesrgan") -> RealESRGANFrameEnhancer
```

Pero:

* Si faltan dependencias IA, el enhancer puede construirse, pero debe fallar de forma controlada al ejecutarse.
* El pipeline no debe usar `realesrgan` por defecto todavía.

---

# Validación de modelo Real-ESRGAN

Usar el registro de modelos existente:

Modelos esperados:

```text
realesrgan-x2
realesrgan-x4
realesrgan-general
```

Validar:

1. Existe en DB.
2. Está habilitado.
3. Está marcado como instalado.
4. Tiene `relative_path`.
5. El archivo existe físicamente.
6. El archivo no está vacío.
7. El runtime IA está disponible.
8. Se puede resolver device.

No validar todavía calidad del modelo ni compatibilidad exacta del state dict.

---

# Dry-run

Endpoint de dry-run debe:

1. Validar runtime IA.
2. Validar modelo.
3. Resolver input frame.
4. Crear carpeta temporal:

```text
storage/temp/ai-dry-runs/
```

5. Generar output:

```text
storage/temp/ai-dry-runs/{model_slug}_{timestamp}.png
```

6. Intentar procesar un solo frame.
7. Medir tiempo.
8. Devolver resultado.

Si todavía no se implementa inferencia real, el dry-run puede tener dos modos:

## Modo preparation

Verifica todo excepto inferencia real:

```text
success = true
message = "Real-ESRGAN dry-run preparation completed. Real inference will be implemented in REQ-014."
```

## Modo inference

Si el adapter ya permite un frame:

```text
success = true
message = "Real-ESRGAN dry-run completed successfully."
```

Para este requerimiento se acepta modo preparation.

---

# Endpoints requeridos

Crear:

```text
app/api/routes_ai_runtime.py
```

Todos bajo:

```text
/api/ai
```

---

## GET /api/ai/runtime

Devuelve estado del runtime IA.

### Response 200

```json
{
  "available": true,
  "torch_available": true,
  "torch_version": "2.x.x",
  "cuda_available": true,
  "cuda_device_count": 1,
  "cuda_devices": [
    {
      "index": 0,
      "name": "NVIDIA GeForce RTX 4070",
      "memory_total_mb": 12288
    }
  ],
  "selected_device": "cuda",
  "allow_cpu": true,
  "half_precision": true,
  "warnings": []
}
```

Si PyTorch no está instalado:

```json
{
  "available": false,
  "torch_available": false,
  "torch_version": null,
  "cuda_available": false,
  "cuda_device_count": 0,
  "cuda_devices": [],
  "selected_device": null,
  "allow_cpu": true,
  "half_precision": true,
  "warnings": [
    "PyTorch is not installed. Real-ESRGAN cannot run yet."
  ]
}
```

---

## GET /api/ai/models/{model_slug}/validate

Valida si un modelo puede ejecutarse.

### Response 200

```json
{
  "model_slug": "realesrgan-x4",
  "exists_in_registry": true,
  "is_enabled": true,
  "is_installed": true,
  "file_path": "storage/models/realesrgan/realesrgan-x4.pth",
  "file_exists": true,
  "file_size_bytes": 67000000,
  "estimated_vram_mb": 8192,
  "runtime_available": true,
  "can_run": true,
  "device": "cuda",
  "warnings": []
}
```

Si falta el archivo:

```json
{
  "model_slug": "realesrgan-x4",
  "exists_in_registry": true,
  "is_enabled": true,
  "is_installed": false,
  "file_path": "storage/models/realesrgan/realesrgan-x4.pth",
  "file_exists": false,
  "file_size_bytes": null,
  "estimated_vram_mb": 8192,
  "runtime_available": true,
  "can_run": false,
  "device": "cuda",
  "warnings": [
    "Model file does not exist."
  ]
}
```

---

## POST /api/ai/realesrgan/dry-run

Ejecuta validación/dry-run sobre un frame.

### Request usando ruta directa

```json
{
  "model_slug": "realesrgan-x2",
  "input_frame_path": "storage/temp/jobs/{job_id}/frames/original/frame_00000000.png"
}
```

### Request usando job + frame

```json
{
  "model_slug": "realesrgan-x2",
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "frame_index": 0
}
```

### Response 200

```json
{
  "success": true,
  "model_slug": "realesrgan-x2",
  "engine": "realesrgan",
  "device": "cuda",
  "input_frame_path": "storage/temp/jobs/{job_id}/frames/original/frame_00000000.png",
  "output_frame_path": "storage/temp/ai-dry-runs/realesrgan-x2_20260613_120000.png",
  "elapsed_time_ms": 850,
  "message": "Real-ESRGAN dry-run preparation completed. Real inference will be implemented in REQ-014.",
  "warnings": []
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
/api/ai/runtime
/api/ai/models/{model_slug}/validate
/api/ai/realesrgan/dry-run
```

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class AIRuntimeNotAvailableError(OroyaVideoError):
    pass


class TorchNotAvailableError(OroyaVideoError):
    pass


class CUDANotAvailableError(OroyaVideoError):
    pass


class AIModelFileNotFoundError(OroyaVideoError):
    pass


class RealESRGANNotAvailableError(OroyaVideoError):
    pass


class RealESRGANDryRunFailedError(OroyaVideoError):
    pass


class RealESRGANEnhancementNotImplementedError(OroyaVideoError):
    pass
```

---

## Runtime IA no disponible

Status:

```text
503
```

Response:

```json
{
  "error": "ai_runtime_not_available",
  "message": "AI runtime is not available."
}
```

---

## PyTorch no disponible

Status:

```text
503
```

Response:

```json
{
  "error": "torch_not_available",
  "message": "PyTorch is required to run Real-ESRGAN."
}
```

---

## CUDA no disponible

Status:

```text
503
```

Response:

```json
{
  "error": "cuda_not_available",
  "message": "CUDA device was requested but is not available."
}
```

---

## Archivo de modelo no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "ai_model_file_not_found",
  "message": "AI model file was not found."
}
```

---

## Dry-run fallido

Status:

```text
422
```

Response:

```json
{
  "error": "realesrgan_dry_run_failed",
  "message": "Real-ESRGAN dry-run failed."
}
```

---

# Seguridad de archivos

Reglas:

* Para `dry-run` con `input_frame_path`, resolver path con `.resolve()`.
* Permitir únicamente archivos `.png`, `.jpg`, `.jpeg`, `.webp`.
* No permitir directorios.
* No sobrescribir el input.
* Escribir outputs solo dentro de:

```text
storage/temp/ai-dry-runs/
```

* No permitir path traversal.
* No devolver tracebacks completos al frontend.
* Registrar detalles técnicos solo en logs locales.

---

# Logs

Registrar en backend:

```text
AI runtime requested
PyTorch detected
PyTorch not available
CUDA detected
CUDA not available
AI device resolved
Real-ESRGAN model validation requested
Real-ESRGAN model validation completed
Real-ESRGAN dry-run requested
Real-ESRGAN dry-run preparation completed
Real-ESRGAN dry-run failed
Real-ESRGAN dependencies missing
```

Registrar warnings cuando:

```text
PyTorch is not installed
CUDA requested but not available
Model file is missing
CPU fallback selected
Real inference is not implemented yet
```

---

# Tests

Crear:

```text
tests/test_realesrgan_preparation.py
```

Los tests no deben depender de PyTorch real, CUDA real ni modelos reales.

Usar mocks para:

* import de torch
* `torch.cuda.is_available`
* `torch.cuda.device_count`
* `torch.cuda.get_device_name`
* `Path.exists`
* `Path.stat`
* DB/repository de modelos
* dry-run input frames

Pruebas mínimas:

1. `/api/ai/runtime` responde 200 aunque PyTorch no esté instalado.
2. Runtime devuelve `torch_available=false` si falla import.
3. Runtime devuelve `cuda_available=false` si torch existe pero CUDA no.
4. Runtime resuelve `selected_device=cpu` cuando `AI_DEVICE=auto` y no hay CUDA.
5. Runtime resuelve `selected_device=cuda` cuando CUDA está disponible.
6. Runtime responde warning si `AI_DEVICE=cuda` pero CUDA no está disponible.
7. `GET /api/ai/models/{slug}/validate` responde modelo válido si existe archivo.
8. Validate responde `can_run=false` si modelo no está instalado.
9. Validate responde `can_run=false` si runtime IA no está disponible.
10. Validate responde `404` si modelo no existe.
11. `get_frame_enhancer("realesrgan")` devuelve adapter RealESRGAN.
12. `get_frame_enhancer("mock")` sigue funcionando.
13. `POST /api/ai/realesrgan/dry-run` acepta `input_frame_path`.
14. `POST /api/ai/realesrgan/dry-run` acepta `job_id + frame_index`.
15. Dry-run rechaza input inexistente.
16. Dry-run rechaza extensión no permitida.
17. Dry-run escribe o prepara output dentro de `storage/temp/ai-dry-runs`.
18. Dry-run no modifica input.
19. El backend arranca sin PyTorch.
20. El pipeline mock sigue funcionando con `FRAME_ENHANCER_ENGINE=mock`.

---

# Actualizar README

Agregar sección:

```text
Real-ESRGAN preparation
```

Documentar endpoints:

```text
GET  /api/ai/runtime
GET  /api/ai/models/{model_slug}/validate
POST /api/ai/realesrgan/dry-run
```

Agregar explicación:

```text
Real-ESRGAN is prepared as an optional AI engine.
The default enhancer remains mock until full inference is implemented.
```

Agregar ejemplo:

```bash
curl "http://127.0.0.1:8000/api/ai/runtime"
```

Validar modelo:

```bash
curl "http://127.0.0.1:8000/api/ai/models/realesrgan-x2/validate"
```

Dry-run:

```bash
curl -X POST "http://127.0.0.1:8000/api/ai/realesrgan/dry-run" \
  -H "Content-Type: application/json" \
  -d "{\"model_slug\": \"realesrgan-x2\", \"job_id\": \"JOB_ID\", \"frame_index\": 0}"
```

Agregar nota:

```text
This requirement prepares Real-ESRGAN integration. Full batch frame enhancement with Real-ESRGAN will be implemented in REQ-014.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe `ai_runtime_service.py`.
* Existe `realesrgan_service.py`.
* Existe `realesrgan_enhancer.py`.
* Existe `routes_ai_runtime.py`.
* Existe `ai_runtime_schema.py`.
* El backend arranca aunque PyTorch no esté instalado.
* `/api/ai/runtime` reporta estado IA.
* `/api/ai/models/{model_slug}/validate` valida modelos.
* `/api/ai/realesrgan/dry-run` existe y responde de forma controlada.
* El registry soporta `mock` y `realesrgan`.
* `FRAME_ENHANCER_ENGINE=mock` sigue funcionando.
* `FRAME_ENHANCER_ENGINE=realesrgan` no rompe el arranque del backend.
* Los errores IA están controlados.
* No se exponen tracebacks al frontend.
* Los tests no dependen de GPU real.
* Los tests pasan.
* README documenta diagnóstico IA y preparación Real-ESRGAN.
* No se implementa todavía procesamiento batch real de todos los frames.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Consultar estado IA:

```text
GET /api/ai/runtime
```

2. Validar modelo:

```text
GET /api/ai/models/realesrgan-x2/validate
```

3. Ejecutar dry-run preparado sobre un frame:

```text
POST /api/ai/realesrgan/dry-run
```

4. Confirmar que el backend puede convivir con dos engines:

```text
mock
realesrgan
```

5. Mantener el pipeline completo funcionando con `mock`.

Este requerimiento deja preparado el backend para REQ-014: procesamiento real de frames con Real-ESRGAN.
