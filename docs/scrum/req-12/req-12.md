# REQ-012 - Preview & Before/After Frame API

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
* Extracción de frames originales.
* Generación de frames enhanced.
* Encoding de video silent.
* Mux de audio.
* Export final.
* Job progress completo.

---

# Objetivo

Implementar la API de previews para que el frontend pueda mostrar comparación visual entre frames originales y frames mejorados.

El backend debe permitir:

1. Consultar información de preview de un job.
2. Obtener un frame original por índice.
3. Obtener un frame enhanced por índice.
4. Obtener metadata de comparación original/enhanced.
5. Obtener rutas o URLs de preview para la UI.
6. Validar existencia de frames.
7. Servir imágenes PNG de forma segura.
8. Preparar la base para el slider Before / After de Oroya Video.

Este requerimiento no debe implementar edición visual ni generación de imágenes comparativas compuestas.
La UI será la responsable de mostrar el slider, split view o side-by-side usando los frames servidos por el backend.

---

# Contexto

Hasta ahora, el pipeline completo genera:

```text
storage/temp/jobs/{job_id}/frames/original/
├── frame_00000000.png
├── frame_00000001.png
└── ...

storage/temp/jobs/{job_id}/frames/enhanced/
├── frame_00000000.png
├── frame_00000001.png
└── ...
```

La UI de Oroya Video necesita consumir esos frames para mostrar:

```text
Original Frame  |  Enhanced Frame
```

y permitir modos visuales como:

```text
split
slider
side_by_side
```

El backend debe exponer endpoints seguros y estables para esta función.

---

# Decisión MVP

El backend servirá frames individuales como archivos PNG usando `FileResponse`.

La UI podrá usar directamente URLs como:

```text
/api/jobs/{job_id}/preview/original/0
/api/jobs/{job_id}/preview/enhanced/0
```

Esto permite que Angular/Tauri renderice las imágenes en elementos `<img>`.

No se devolverán imágenes en Base64 por defecto.

Motivo:

* Menor uso de memoria.
* Mejor rendimiento.
* Más simple para el frontend.
* Compatible con caching futuro.
* Más cercano al uso real de imágenes en una app desktop/web.

---

# Alcance de este requerimiento

Implementar:

1. Servicio de preview.
2. Endpoints para obtener frames originales.
3. Endpoints para obtener frames enhanced.
4. Endpoint para metadata de preview.
5. Endpoint para comparación de un frame.
6. Endpoint para frame recomendado de preview.
7. Validación de índices de frame.
8. Validación de existencia de frames.
9. Respuestas JSON con URLs relativas.
10. Serving seguro de PNGs con `FileResponse`.
11. Tests con mocks.
12. Actualización del README.

No implementar todavía:

* Slider visual.
* Composición de imagen before/after en backend.
* Generación de thumbnails persistentes.
* WebSocket.
* Streaming de video.
* Preview de video completo.
* Cache avanzado.
* Transformaciones reales de imagen.
* OCR.
* OpenCV.
* Real-ESRGAN real.

---

# Conceptos nuevos

## Preview Frame

Representa un frame disponible para visualización.

Puede ser:

```text
original
enhanced
```

Cada preview frame debe tener:

* Índice.
* Nombre de archivo.
* Ruta interna.
* URL API.
* Existencia.
* Tamaño en bytes.

---

## Compare Frame

Representa un par de frames:

```text
original frame + enhanced frame
```

Ambos deben compartir el mismo índice.

Ejemplo:

```text
frame_00000480.png original
frame_00000480.png enhanced
```

---

# Convención de nombres de frames

La convención existente se mantiene:

```text
frame_%08d.png
```

Ejemplos:

```text
frame_00000000.png
frame_00000001.png
frame_00000480.png
frame_00003079.png
```

El backend debe convertir un índice entero en nombre de archivo.

Ejemplo:

```text
index = 480
file_name = frame_00000480.png
```

---

# Estructura a modificar

Agregar o actualizar:

```text
backend/
├── app/
│   ├── api/
│   │   ├── router.py
│   │   └── routes_preview.py
│   │
│   ├── schemas/
│   │   └── preview_schema.py
│   │
│   ├── services/
│   │   └── preview_service.py
│   │
│   └── core/
│       └── errors.py
│
├── tests/
│   └── test_preview.py
│
└── README.md
```

---

# Paths

Usar las funciones existentes de REQ-008 y REQ-009:

```python
get_job_original_frames_path(job_id: str) -> Path
get_job_enhanced_frames_path(job_id: str) -> Path
```

Agregar si aún no existe:

```python
def build_frame_file_name(index: int) -> str:
    ...
```

Ejemplo:

```python
build_frame_file_name(0) == "frame_00000000.png"
build_frame_file_name(480) == "frame_00000480.png"
```

---

# Servicio de preview

Crear:

```text
app/services/preview_service.py
```

Responsabilidades:

1. Cargar job.
2. Validar que el job exista.
3. Validar que existan frames originales.
4. Validar que existan frames enhanced cuando se pidan.
5. Resolver frame por índice.
6. Validar índice no negativo.
7. Calcular total de frames disponibles.
8. Construir URLs relativas para frontend.
9. Devolver metadata de comparación.
10. Seleccionar frame recomendado para preview.

Funciones sugeridas:

```python
def get_preview_info(
    db: Session,
    job_id: str,
) -> PreviewInfoResponse:
    ...


def get_original_frame_path(
    db: Session,
    job_id: str,
    frame_index: int,
) -> Path:
    ...


def get_enhanced_frame_path(
    db: Session,
    job_id: str,
    frame_index: int,
) -> Path:
    ...


def get_compare_frame_info(
    db: Session,
    job_id: str,
    frame_index: int,
) -> CompareFrameResponse:
    ...


def get_recommended_preview_frame_index(
    db: Session,
    job_id: str,
) -> int:
    ...


def list_preview_frames(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> PreviewFrameListResponse:
    ...
```

---

# Frame recomendado

El backend debe poder sugerir un frame inicial para preview.

Regla MVP:

```text
Si hay frames totales:
    recommended_index = min(total_frames // 2, total_frames - 1)
Si no hay frames:
    error
```

Ejemplo:

```text
total_frames = 3080
recommended_index = 1540
```

Motivo:

* El primer frame puede ser negro.
* Un frame central suele representar mejor el contenido.
* La UI puede abrir una comparación útil por defecto.

---

# Schemas

Crear:

```text
app/schemas/preview_schema.py
```

## PreviewFrameResponse

```python
class PreviewFrameResponse(BaseModel):
    job_id: str
    frame_index: int
    frame_type: Literal["original", "enhanced"]
    file_name: str
    path: str
    url: str
    available: bool
    size_bytes: int | None = None
```

---

## PreviewInfoResponse

```python
class PreviewInfoResponse(BaseModel):
    job_id: str
    project_id: str
    status: str
    current_stage: str
    original_frames_available: bool
    enhanced_frames_available: bool
    original_frames_count: int
    enhanced_frames_count: int
    comparable_frames_count: int
    recommended_frame_index: int | None
    frame_pattern: str
    frame_format: str
    original_frames_dir: str | None
    enhanced_frames_dir: str | None
```

---

## CompareFrameResponse

```python
class CompareFrameResponse(BaseModel):
    job_id: str
    frame_index: int
    original: PreviewFrameResponse
    enhanced: PreviewFrameResponse
    compare_modes: list[str]
```

---

## PreviewFrameListItem

```python
class PreviewFrameListItem(BaseModel):
    index: int
    file_name: str
    original_available: bool
    enhanced_available: bool
    original_url: str | None
    enhanced_url: str | None
```

---

## PreviewFrameListResponse

```python
class PreviewFrameListResponse(BaseModel):
    job_id: str
    items: list[PreviewFrameListItem]
    total: int
    limit: int
    offset: int
```

---

# Endpoints requeridos

Crear:

```text
app/api/routes_preview.py
```

Todos los endpoints irán bajo:

```text
/api/jobs/{job_id}/preview
```

---

## GET /api/jobs/{job_id}/preview

Devuelve metadata general de preview.

### Response 200

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "project_id": "f42109c4-33cb-48de-81db-d45f53238221",
  "status": "completed",
  "current_stage": "completed",
  "original_frames_available": true,
  "enhanced_frames_available": true,
  "original_frames_count": 3080,
  "enhanced_frames_count": 3080,
  "comparable_frames_count": 3080,
  "recommended_frame_index": 1540,
  "frame_pattern": "frame_%08d.png",
  "frame_format": "png",
  "original_frames_dir": "storage/temp/jobs/{job_id}/frames/original",
  "enhanced_frames_dir": "storage/temp/jobs/{job_id}/frames/enhanced"
}
```

---

## GET /api/jobs/{job_id}/preview/original/{frame_index}

Devuelve el PNG original correspondiente al índice solicitado.

Ejemplo:

```text
GET /api/jobs/{job_id}/preview/original/480
```

Debe devolver:

```text
Content-Type: image/png
```

Usar:

```python
FileResponse(path, media_type="image/png")
```

---

## GET /api/jobs/{job_id}/preview/enhanced/{frame_index}

Devuelve el PNG enhanced correspondiente al índice solicitado.

Ejemplo:

```text
GET /api/jobs/{job_id}/preview/enhanced/480
```

Debe devolver:

```text
Content-Type: image/png
```

Usar:

```python
FileResponse(path, media_type="image/png")
```

---

## GET /api/jobs/{job_id}/preview/compare/{frame_index}

Devuelve metadata JSON con URLs para comparar original y enhanced.

### Response 200

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "frame_index": 480,
  "original": {
    "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
    "frame_index": 480,
    "frame_type": "original",
    "file_name": "frame_00000480.png",
    "path": "storage/temp/jobs/{job_id}/frames/original/frame_00000480.png",
    "url": "/api/jobs/{job_id}/preview/original/480",
    "available": true,
    "size_bytes": 2450000
  },
  "enhanced": {
    "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
    "frame_index": 480,
    "frame_type": "enhanced",
    "file_name": "frame_00000480.png",
    "path": "storage/temp/jobs/{job_id}/frames/enhanced/frame_00000480.png",
    "url": "/api/jobs/{job_id}/preview/enhanced/480",
    "available": true,
    "size_bytes": 2451000
  },
  "compare_modes": [
    "split",
    "slider",
    "side_by_side"
  ]
}
```

---

## GET /api/jobs/{job_id}/preview/recommended

Devuelve metadata del frame recomendado para comparación.

Debe ser equivalente a:

```text
GET /api/jobs/{job_id}/preview/compare/{recommended_frame_index}
```

### Response 200

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "frame_index": 1540,
  "original": {
    "url": "/api/jobs/{job_id}/preview/original/1540"
  },
  "enhanced": {
    "url": "/api/jobs/{job_id}/preview/enhanced/1540"
  },
  "compare_modes": [
    "split",
    "slider",
    "side_by_side"
  ]
}
```

---

## GET /api/jobs/{job_id}/preview/frames

Lista frames disponibles para preview.

Query params:

```text
limit: int = 100
offset: int = 0
```

### Response 200

```json
{
  "job_id": "b1dd73d0-ea57-4039-970d-597c7158a003",
  "items": [
    {
      "index": 0,
      "file_name": "frame_00000000.png",
      "original_available": true,
      "enhanced_available": true,
      "original_url": "/api/jobs/{job_id}/preview/original/0",
      "enhanced_url": "/api/jobs/{job_id}/preview/enhanced/0"
    },
    {
      "index": 1,
      "file_name": "frame_00000001.png",
      "original_available": true,
      "enhanced_available": true,
      "original_url": "/api/jobs/{job_id}/preview/original/1",
      "enhanced_url": "/api/jobs/{job_id}/preview/enhanced/1"
    }
  ],
  "total": 3080,
  "limit": 100,
  "offset": 0
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
/api/jobs/{job_id}/preview
```

Recomendación:

Aunque los endpoints viven bajo `/api/jobs`, pueden estar en un archivo separado:

```text
routes_preview.py
```

para mantener limpio `routes_jobs.py`.

---

# Validaciones

## Validar job

Para cualquier endpoint:

1. El job debe existir.
2. El job debe tener `original_frames_dir` o `enhanced_frames_dir` según endpoint.
3. La ruta debe estar dentro de `storage/temp/jobs/{job_id}`.
4. No se debe permitir path traversal.
5. No aceptar índices negativos.

---

## Validar frame original

Para original:

```text
storage/temp/jobs/{job_id}/frames/original/frame_{index}.png
```

Debe existir y ser archivo.

---

## Validar frame enhanced

Para enhanced:

```text
storage/temp/jobs/{job_id}/frames/enhanced/frame_{index}.png
```

Debe existir y ser archivo.

---

## Validar comparación

Para compare:

* Debe existir frame original.
* Debe existir frame enhanced.
* Ambos deben compartir el mismo índice.
* Si falta uno, devolver error controlado.

---

# Seguridad de archivos

Reglas:

* Nunca recibir rutas directamente desde el usuario en estos endpoints.
* El usuario solo envía `job_id` y `frame_index`.
* El backend construye la ruta internamente.
* Resolver rutas con `.resolve()`.
* Validar que la ruta resuelta está dentro del directorio esperado.
* Servir únicamente archivos `.png`.
* No servir archivos fuera de `storage/temp/jobs/{job_id}`.
* No exponer rutas absolutas si no es necesario.

En las respuestas JSON, preferir rutas relativas.

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class PreviewNotAvailableError(OroyaVideoError):
    pass


class PreviewFrameNotFoundError(OroyaVideoError):
    pass


class InvalidFrameIndexError(OroyaVideoError):
    pass


class PreviewFrameAccessDeniedError(OroyaVideoError):
    pass
```

---

## Preview no disponible

Status:

```text
404
```

Response:

```json
{
  "error": "preview_not_available",
  "message": "Preview frames are not available for this job."
}
```

---

## Frame no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "preview_frame_not_found",
  "message": "Preview frame was not found."
}
```

---

## Índice inválido

Status:

```text
400
```

Response:

```json
{
  "error": "invalid_frame_index",
  "message": "Frame index must be greater than or equal to zero."
}
```

---

## Acceso denegado a frame

Status:

```text
403
```

Response:

```json
{
  "error": "preview_frame_access_denied",
  "message": "Preview frame path is outside the allowed job directory."
}
```

---

# Logging

Registrar en backend:

```text
Preview info requested
Original preview frame requested
Enhanced preview frame requested
Compare preview requested
Recommended preview requested
Preview frame list requested
Preview frame not found
Preview not available
Invalid preview frame index
Preview frame access denied
```

No registrar cada solicitud de imagen con demasiado detalle si genera ruido.

Recomendación:

* Log nivel `debug` para frames individuales.
* Log nivel `info` para metadata general.
* Log nivel `warning` para errores controlados.

---

# Tests

Crear:

```text
tests/test_preview.py
```

Los tests no deben depender de imágenes reales pesadas.

Usar archivos PNG dummy pequeños creados con bytes mínimos o mocks de `Path`.

Pruebas mínimas:

1. `build_frame_file_name(0)` devuelve `frame_00000000.png`.
2. `build_frame_file_name(480)` devuelve `frame_00000480.png`.
3. `GET /api/jobs/{job_id}/preview` devuelve metadata.
4. `GET /api/jobs/{job_id}/preview` responde `404` si no hay frames.
5. `GET /api/jobs/{job_id}/preview/original/0` devuelve `image/png`.
6. `GET /api/jobs/{job_id}/preview/enhanced/0` devuelve `image/png`.
7. `GET /api/jobs/{job_id}/preview/original/-1` responde `400`.
8. `GET /api/jobs/{job_id}/preview/enhanced/-1` responde `400`.
9. `GET /api/jobs/{job_id}/preview/original/999999` responde `404` si no existe.
10. `GET /api/jobs/{job_id}/preview/enhanced/999999` responde `404` si no existe.
11. `GET /api/jobs/{job_id}/preview/compare/0` devuelve URLs original/enhanced.
12. `GET /api/jobs/{job_id}/preview/compare/0` responde `404` si falta enhanced.
13. `GET /api/jobs/{job_id}/preview/recommended` usa frame central.
14. `GET /api/jobs/{job_id}/preview/frames` lista frames paginados.
15. `GET /api/jobs/{job_id}/preview/frames?limit=10&offset=10` aplica paginación.
16. El servicio no permite servir rutas fuera de `storage/temp/jobs/{job_id}`.
17. El servicio solo sirve archivos `.png`.
18. Si el job no existe, responde `404`.

---

# Actualizar README

Agregar sección:

```text
Preview and before/after API
```

Documentar:

```text
GET /api/jobs/{job_id}/preview
GET /api/jobs/{job_id}/preview/original/{frame_index}
GET /api/jobs/{job_id}/preview/enhanced/{frame_index}
GET /api/jobs/{job_id}/preview/compare/{frame_index}
GET /api/jobs/{job_id}/preview/recommended
GET /api/jobs/{job_id}/preview/frames
```

Ejemplo:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/preview"
```

Ejemplo para obtener frame original:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/preview/original/480" --output original.png
```

Ejemplo para obtener frame enhanced:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/preview/enhanced/480" --output enhanced.png
```

Ejemplo para metadata comparativa:

```bash
curl "http://127.0.0.1:8000/api/jobs/{job_id}/preview/compare/480"
```

Agregar nota:

```text
The backend serves individual PNG frames. The frontend is responsible for rendering split view, slider or side-by-side comparison.
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe `preview_service.py`.
* Existe `routes_preview.py`.
* Existe `preview_schema.py`.
* El router principal incluye los endpoints de preview.
* `GET /api/jobs/{job_id}/preview` devuelve metadata.
* `GET /api/jobs/{job_id}/preview/original/{frame_index}` devuelve PNG.
* `GET /api/jobs/{job_id}/preview/enhanced/{frame_index}` devuelve PNG.
* `GET /api/jobs/{job_id}/preview/compare/{frame_index}` devuelve URLs original/enhanced.
* `GET /api/jobs/{job_id}/preview/recommended` devuelve comparación recomendada.
* `GET /api/jobs/{job_id}/preview/frames` lista frames paginados.
* El backend valida índices negativos.
* El backend valida existencia de frames.
* El backend no permite path traversal.
* El backend solo sirve PNGs de carpetas del job.
* Los errores están controlados.
* Los tests pasan.
* README documenta los endpoints.
* No se implementa composición visual del slider en backend.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible:

1. Ejecutar un job completo.
2. Tener frames originales en:

```text
storage/temp/jobs/{job_id}/frames/original/
```

3. Tener frames enhanced en:

```text
storage/temp/jobs/{job_id}/frames/enhanced/
```

4. Consultar preview metadata:

```text
GET /api/jobs/{job_id}/preview
```

5. Mostrar en la UI:

```text
Original frame
Enhanced frame
Before / After comparison
```

6. Usar URLs directas en Angular:

```html
<img src="http://127.0.0.1:8000/api/jobs/{job_id}/preview/original/480" />
<img src="http://127.0.0.1:8000/api/jobs/{job_id}/preview/enhanced/480" />
```

Este requerimiento deja preparado el backend para construir la vista visual principal de Oroya Video: Preview Before / After.
