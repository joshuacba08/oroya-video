# REQ-005 - Projects CRUD & Workspace State

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
```

El backend ya debe tener:

* FastAPI funcional.
* Configuración centralizada.
* Sistema de paths.
* Logging.
* SQLite inicializado.
* Modelo ORM `VideoAsset`.
* Repositorio de videos.
* Servicio de importación de videos.
* Endpoint `POST /api/videos/import`.
* Endpoint `GET /api/videos`.
* Endpoint `GET /api/videos/{video_id}`.
* Endpoint `DELETE /api/videos/{video_id}`.

---

# Objetivo

Implementar la gestión de proyectos de Oroya Video.

Un proyecto será la unidad principal de trabajo dentro de la aplicación. Cada proyecto estará asociado a un video importado y contendrá la configuración inicial de mejora, exportación y estado del workspace.

Este requerimiento debe permitir:

1. Crear proyectos a partir de un `video_asset_id`.
2. Listar proyectos.
3. Consultar un proyecto.
4. Actualizar datos básicos del proyecto.
5. Actualizar configuración de mejora.
6. Actualizar estado visual del workspace.
7. Eliminar proyectos.
8. Preparar la estructura para futuros jobs y exports.

Este requerimiento no debe implementar todavía procesamiento de video ni jobs reales.

---

# Contexto

Hasta ahora Oroya Video puede analizar e importar videos.

Pero la app necesita una entidad superior para organizar el trabajo del usuario.

Flujo esperado:

```text
User imports video
        ↓
Backend creates VideoAsset
        ↓
User creates project from VideoAsset
        ↓
Project stores enhancement settings
        ↓
Project becomes workspace for preview, processing and export
```

La UI principal de Oroya Video girará alrededor de proyectos.

Un proyecto representa algo como:

```text
"Anime Episode 01 - 1080p to 4K"
"Old Family Video Restoration"
"Clip Enhancement Test"
```

---

# Conceptos nuevos

## Project

Un `Project` representa una unidad de trabajo editable.

Contiene:

* Nombre.
* Descripción opcional.
* Video asociado.
* Configuración de mejora.
* Configuración de exportación.
* Estado del workspace.
* Estado general del proyecto.
* Fecha de creación.
* Fecha de actualización.
* Fecha de último acceso.

---

## Workspace State

El `workspace_state` guarda información útil para restaurar la UI cuando el usuario vuelve a abrir un proyecto.

Ejemplos:

* Frame seleccionado.
* Modo de comparación.
* Nivel de zoom.
* Panel activo.
* Si el inspector está abierto.
* Última posición del timeline.

No es lógica crítica de procesamiento.

Es estado útil para experiencia de usuario.

---

## Enhancement Config

Representa la configuración inicial para mejorar el video.

Ejemplo:

```json
{
  "model_id": "realesrgan-x2",
  "scale": "2x",
  "denoise": 0,
  "sharpen": 0,
  "compression_cleanup": false
}
```

---

## Export Config

Representa la configuración inicial de exportación.

Ejemplo:

```json
{
  "format": "mp4",
  "codec": "h264",
  "keep_audio": true,
  "output_resolution": "2x"
}
```

---

# Decisiones del MVP

## Un proyecto tendrá un video principal

Para el MVP:

```text
1 Project = 1 VideoAsset principal
```

No implementar todavía:

* Múltiples videos por proyecto.
* Batch processing.
* Timeline multipista.
* Secuencias.
* Carpetas internas por escena.

---

## Configuración como JSON

Para mantener flexibilidad, las configuraciones iniciales se guardarán como texto JSON en SQLite:

```text
enhancement_config_json
export_config_json
workspace_state_json
```

Más adelante se podrán normalizar si hace falta.

---

# Alcance de este requerimiento

Implementar:

1. Modelo ORM `Project`.
2. Relación entre `Project` y `VideoAsset`.
3. Repositorio de proyectos.
4. Servicio de proyectos.
5. Endpoints CRUD de proyectos.
6. Endpoint para obtener estado completo del workspace.
7. Validación de existencia de `VideoAsset`.
8. Configuración inicial por defecto.
9. Actualización parcial de proyecto.
10. Eliminación de proyecto.
11. Tests.
12. Actualización del README.

No implementar todavía:

* Jobs.
* Workers.
* Cola de procesamiento.
* Modelos IA reales.
* Preview frames.
* Exports reales.
* Historial de jobs.
* Timeline avanzado.
* Procesamiento de video.

---

# Estructura a modificar

Agregar o actualizar:

```text
backend/
├── app/
│   ├── api/
│   │   ├── router.py
│   │   └── routes_projects.py
│   │
│   ├── core/
│   │   └── errors.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   └── repositories/
│   │       └── project_repository.py
│   │
│   ├── schemas/
│   │   └── project_schema.py
│   │
│   └── services/
│       └── project_service.py
│
├── tests/
│   └── test_projects.py
│
└── README.md
```

---

# Modelo ORM

Actualizar:

```text
app/db/models.py
```

Agregar modelo:

```python
class Project(Base):
    __tablename__ = "projects"
```

Campos requeridos:

```text
id
name
description
video_asset_id
status
enhancement_config_json
export_config_json
workspace_state_json
created_at
updated_at
last_opened_at
```

Tipos sugeridos:

```text
id                        String primary key UUID
name                      String not null
description               Text nullable
video_asset_id             String ForeignKey video_assets.id not null
status                    String not null
enhancement_config_json    Text not null
export_config_json         Text not null
workspace_state_json       Text not null
created_at                DateTime not null
updated_at                DateTime not null
last_opened_at             DateTime nullable
```

Relación:

```python
video_asset = relationship("VideoAsset")
```

---

# Estados del proyecto

Estados permitidos:

```text
draft
ready
processing
completed
failed
archived
```

Descripción:

```text
draft       Proyecto creado pero todavía sin procesamiento.
ready       Proyecto configurado y listo para crear un job.
processing  Hay un job activo asociado en el futuro.
completed   El proyecto tiene al menos un export terminado en el futuro.
failed      El último procesamiento falló en el futuro.
archived    Proyecto oculto o archivado.
```

En este requerimiento, los estados más usados serán:

```text
draft
ready
archived
```

---

# Configuración por defecto

Si el frontend no envía configuración, el backend debe crear valores por defecto.

## Enhancement Config default

```json
{
  "model_id": "realesrgan-x2",
  "scale": "2x",
  "denoise": 0,
  "sharpen": 0,
  "compression_cleanup": false
}
```

## Export Config default

```json
{
  "format": "mp4",
  "codec": "h264",
  "keep_audio": true,
  "output_resolution": "2x"
}
```

## Workspace State default

```json
{
  "selected_frame": 0,
  "compare_mode": "split",
  "zoom": "fit",
  "active_panel": "inspector",
  "timeline_position": 0,
  "inspector_open": true
}
```

---

# Schemas

Crear:

```text
app/schemas/project_schema.py
```

## ProjectCreateRequest

```python
class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = None
    video_asset_id: str
    enhancement_config: dict[str, Any] | None = None
    export_config: dict[str, Any] | None = None
    workspace_state: dict[str, Any] | None = None
```

## ProjectUpdateRequest

```python
class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: Literal[
        "draft",
        "ready",
        "processing",
        "completed",
        "failed",
        "archived",
    ] | None = None
    enhancement_config: dict[str, Any] | None = None
    export_config: dict[str, Any] | None = None
    workspace_state: dict[str, Any] | None = None
```

## ProjectResponse

```python
class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    video_asset_id: str
    status: str
    enhancement_config: dict[str, Any]
    export_config: dict[str, Any]
    workspace_state: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None
```

## ProjectDetailResponse

Debe incluir datos del proyecto y del video asociado.

```python
class ProjectDetailResponse(BaseModel):
    project: ProjectResponse
    video: VideoAssetResponse
```

## ProjectListResponse

```python
class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
```

## ProjectDeleteResponse

```python
class ProjectDeleteResponse(BaseModel):
    deleted: bool
    project_id: str
```

---

# Repository

Crear:

```text
app/db/repositories/project_repository.py
```

Funciones sugeridas:

```python
def create_project(db: Session, data: dict) -> Project:
    ...


def get_project_by_id(db: Session, project_id: str) -> Project | None:
    ...


def list_projects(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> list[Project]:
    ...


def count_projects(
    db: Session,
    status: str | None = None,
    search: str | None = None,
) -> int:
    ...


def update_project(db: Session, project: Project, data: dict) -> Project:
    ...


def delete_project(db: Session, project: Project) -> None:
    ...
```

Reglas:

* Ordenar proyectos por `updated_at DESC`.
* Soportar búsqueda simple por nombre.
* Soportar filtro por status.
* No eliminar el `VideoAsset` al eliminar un proyecto.
* No borrar archivos de video al eliminar un proyecto.

---

# Servicio

Crear:

```text
app/services/project_service.py
```

Responsabilidades:

1. Crear proyectos.
2. Validar que `video_asset_id` exista.
3. Verificar que el archivo del video siga disponible.
4. Aplicar configuración por defecto.
5. Serializar y deserializar JSON.
6. Listar proyectos.
7. Consultar proyecto por ID.
8. Actualizar proyecto parcialmente.
9. Actualizar `last_opened_at` al abrir un proyecto.
10. Eliminar proyecto.

Funciones sugeridas:

```python
def create_project(
    db: Session,
    request: ProjectCreateRequest,
) -> ProjectDetailResponse:
    ...


def list_projects(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> ProjectListResponse:
    ...


def get_project_detail(
    db: Session,
    project_id: str,
    touch_last_opened: bool = True,
) -> ProjectDetailResponse:
    ...


def update_project(
    db: Session,
    project_id: str,
    request: ProjectUpdateRequest,
) -> ProjectDetailResponse:
    ...


def delete_project(
    db: Session,
    project_id: str,
) -> ProjectDeleteResponse:
    ...
```

---

# Validación del video asociado

Antes de crear un proyecto, verificar:

1. El `VideoAsset` existe.
2. Si `source_mode = reference`, `source_path` existe.
3. Si `source_mode = copy`, `stored_path` existe.
4. Si el archivo no existe, responder error controlado.

Esto evita crear proyectos imposibles de procesar.

---

# Endpoints requeridos

Todos bajo:

```text
/api/projects
```

---

## POST /api/projects

Crea un proyecto.

### Request

```json
{
  "name": "Anime Episode 01 - 4K Upscale",
  "description": "Test using Real-ESRGAN x2",
  "video_asset_id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
  "enhancement_config": {
    "model_id": "realesrgan-x2",
    "scale": "2x",
    "denoise": 0,
    "sharpen": 0,
    "compression_cleanup": false
  },
  "export_config": {
    "format": "mp4",
    "codec": "h264",
    "keep_audio": true,
    "output_resolution": "2x"
  }
}
```

### Response 201

```json
{
  "project": {
    "id": "f42109c4-33cb-48de-81db-d45f53238221",
    "name": "Anime Episode 01 - 4K Upscale",
    "description": "Test using Real-ESRGAN x2",
    "video_asset_id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
    "status": "draft",
    "enhancement_config": {
      "model_id": "realesrgan-x2",
      "scale": "2x",
      "denoise": 0,
      "sharpen": 0,
      "compression_cleanup": false
    },
    "export_config": {
      "format": "mp4",
      "codec": "h264",
      "keep_audio": true,
      "output_resolution": "2x"
    },
    "workspace_state": {
      "selected_frame": 0,
      "compare_mode": "split",
      "zoom": "fit",
      "active_panel": "inspector",
      "timeline_position": 0,
      "inspector_open": true
    },
    "created_at": "2026-06-13T12:00:00",
    "updated_at": "2026-06-13T12:00:00",
    "last_opened_at": null
  },
  "video": {
    "id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
    "file_name": "sample.mp4",
    "resolution_label": "1920x1080",
    "fps": 23.976,
    "duration_label": "00:02:08"
  }
}
```

---

## GET /api/projects

Lista proyectos.

Query params:

```text
limit: int = 50
offset: int = 0
status: str | None = None
search: str | None = None
```

### Response 200

```json
{
  "items": [
    {
      "id": "f42109c4-33cb-48de-81db-d45f53238221",
      "name": "Anime Episode 01 - 4K Upscale",
      "description": "Test using Real-ESRGAN x2",
      "video_asset_id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
      "status": "draft",
      "enhancement_config": {
        "model_id": "realesrgan-x2",
        "scale": "2x"
      },
      "export_config": {
        "format": "mp4",
        "codec": "h264"
      },
      "workspace_state": {
        "selected_frame": 0
      },
      "created_at": "2026-06-13T12:00:00",
      "updated_at": "2026-06-13T12:00:00",
      "last_opened_at": null
    }
  ],
  "total": 1
}
```

---

## GET /api/projects/{project_id}

Devuelve detalle completo del proyecto.

Debe actualizar `last_opened_at`.

### Response 200

```json
{
  "project": {
    "id": "f42109c4-33cb-48de-81db-d45f53238221",
    "name": "Anime Episode 01 - 4K Upscale",
    "description": "Test using Real-ESRGAN x2",
    "video_asset_id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
    "status": "draft",
    "enhancement_config": {
      "model_id": "realesrgan-x2",
      "scale": "2x",
      "denoise": 0,
      "sharpen": 0,
      "compression_cleanup": false
    },
    "export_config": {
      "format": "mp4",
      "codec": "h264",
      "keep_audio": true,
      "output_resolution": "2x"
    },
    "workspace_state": {
      "selected_frame": 0,
      "compare_mode": "split",
      "zoom": "fit",
      "active_panel": "inspector",
      "timeline_position": 0,
      "inspector_open": true
    },
    "created_at": "2026-06-13T12:00:00",
    "updated_at": "2026-06-13T12:00:00",
    "last_opened_at": "2026-06-13T12:15:00"
  },
  "video": {
    "id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
    "file_name": "sample.mp4",
    "source_path": "C:\\Users\\user\\Videos\\sample.mp4",
    "source_mode": "reference",
    "resolution_label": "1920x1080",
    "fps": 23.976,
    "duration_label": "00:02:08"
  }
}
```

---

## PATCH /api/projects/{project_id}

Actualiza parcialmente un proyecto.

### Request

```json
{
  "name": "Anime Episode 01 - Final Upscale",
  "enhancement_config": {
    "model_id": "realesrgan-x4",
    "scale": "4x",
    "denoise": 15,
    "sharpen": 20,
    "compression_cleanup": true
  },
  "workspace_state": {
    "selected_frame": 480,
    "compare_mode": "slider",
    "zoom": "100%",
    "active_panel": "settings",
    "timeline_position": 480,
    "inspector_open": true
  }
}
```

### Response 200

```json
{
  "project": {
    "id": "f42109c4-33cb-48de-81db-d45f53238221",
    "name": "Anime Episode 01 - Final Upscale",
    "status": "draft",
    "enhancement_config": {
      "model_id": "realesrgan-x4",
      "scale": "4x",
      "denoise": 15,
      "sharpen": 20,
      "compression_cleanup": true
    },
    "workspace_state": {
      "selected_frame": 480,
      "compare_mode": "slider",
      "zoom": "100%",
      "active_panel": "settings",
      "timeline_position": 480,
      "inspector_open": true
    },
    "updated_at": "2026-06-13T12:30:00"
  },
  "video": {
    "id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001"
  }
}
```

---

## DELETE /api/projects/{project_id}

Elimina un proyecto.

Reglas:

* Eliminar solo el proyecto.
* No eliminar el `VideoAsset`.
* No borrar archivo original.
* No borrar imports compartidos.
* En el futuro podrá limpiar jobs/exports asociados, pero no en este requerimiento.

### Response 200

```json
{
  "deleted": true,
  "project_id": "f42109c4-33cb-48de-81db-d45f53238221"
}
```

---

# Errores nuevos

Actualizar:

```text
app/core/errors.py
```

Agregar:

```python
class ProjectNotFoundError(OroyaVideoError):
    pass


class ProjectCreateFailedError(OroyaVideoError):
    pass


class ProjectUpdateFailedError(OroyaVideoError):
    pass


class ProjectDeleteFailedError(OroyaVideoError):
    pass


class VideoAssetFileMissingError(OroyaVideoError):
    pass
```

---

## Project no encontrado

Status:

```text
404
```

Response:

```json
{
  "error": "project_not_found",
  "message": "Project was not found."
}
```

---

## Video asset no encontrado

Reutilizar error de REQ-004:

Status:

```text
404
```

Response:

```json
{
  "error": "video_asset_not_found",
  "message": "Video asset was not found."
}
```

---

## Archivo de video faltante

Status:

```text
409
```

Response:

```json
{
  "error": "video_asset_file_missing",
  "message": "The video file associated with this asset is missing."
}
```

---

## Fallo creando proyecto

Status:

```text
500
```

Response:

```json
{
  "error": "project_create_failed",
  "message": "Project could not be created."
}
```

---

# Validación de configuración

En este requerimiento la configuración se guardará como JSON flexible.

Pero debe validarse mínimamente:

## Enhancement Config

Campos reconocidos:

```text
model_id
scale
denoise
sharpen
compression_cleanup
```

Reglas:

```text
scale: original | 2x | 4x
denoise: 0 - 100
sharpen: 0 - 100
compression_cleanup: boolean
```

## Export Config

Campos reconocidos:

```text
format
codec
keep_audio
output_resolution
```

Reglas:

```text
format: mp4
codec: h264
keep_audio: boolean
output_resolution: original | 2x | 4x
```

## Workspace State

Campos reconocidos:

```text
selected_frame
compare_mode
zoom
active_panel
timeline_position
inspector_open
```

Reglas:

```text
selected_frame: int >= 0
compare_mode: split | slider | side_by_side
zoom: fit | 50% | 100% | 200% | 400%
active_panel: inspector | settings | exports | logs
timeline_position: int >= 0
inspector_open: boolean
```

Si una configuración parcial llega en `PATCH`, debe reemplazar o fusionarse con la configuración existente.

Recomendación:

```text
PATCH debe hacer merge superficial con la configuración existente.
```

Ejemplo:

Config actual:

```json
{
  "model_id": "realesrgan-x2",
  "scale": "2x",
  "denoise": 0,
  "sharpen": 0,
  "compression_cleanup": false
}
```

Patch:

```json
{
  "denoise": 20
}
```

Resultado:

```json
{
  "model_id": "realesrgan-x2",
  "scale": "2x",
  "denoise": 20,
  "sharpen": 0,
  "compression_cleanup": false
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
/api/projects
```

Rutas finales:

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
```

---

# Logging

Registrar eventos:

```text
Project create requested
Project created
Project list requested
Project detail requested
Project updated
Project deleted
Project not found
Project creation failed
Video asset not found while creating project
Video asset file missing while creating project
```

No enviar rutas completas en errores al frontend.

En logs internos sí se puede registrar la ruta completa para diagnóstico local.

---

# Tests

Crear:

```text
tests/test_projects.py
```

Los tests deben usar SQLite temporal o en memoria.

No usar la base real:

```text
storage/db/oroya-video.sqlite
```

Usar mocks cuando sea necesario para validar existencia del archivo de video.

Pruebas mínimas:

1. `POST /api/projects` crea un proyecto con un `video_asset_id` válido.
2. `POST /api/projects` aplica configuración por defecto si no se envía.
3. `POST /api/projects` responde `404` si el `video_asset_id` no existe.
4. `POST /api/projects` responde `409` si el archivo asociado al video ya no existe.
5. `GET /api/projects` lista proyectos.
6. `GET /api/projects` soporta `limit` y `offset`.
7. `GET /api/projects` soporta filtro por `status`.
8. `GET /api/projects` soporta búsqueda por nombre.
9. `GET /api/projects/{project_id}` devuelve detalle con video asociado.
10. `GET /api/projects/{project_id}` actualiza `last_opened_at`.
11. `GET /api/projects/{project_id}` responde `404` si no existe.
12. `PATCH /api/projects/{project_id}` actualiza nombre.
13. `PATCH /api/projects/{project_id}` actualiza enhancement config con merge superficial.
14. `PATCH /api/projects/{project_id}` actualiza export config con merge superficial.
15. `PATCH /api/projects/{project_id}` actualiza workspace state con merge superficial.
16. `PATCH /api/projects/{project_id}` valida valores permitidos.
17. `DELETE /api/projects/{project_id}` elimina el proyecto.
18. `DELETE /api/projects/{project_id}` no elimina el VideoAsset.
19. `DELETE /api/projects/{project_id}` responde `404` si no existe.

---

# Actualizar README

Agregar sección:

```text
Project endpoints
```

Documentar:

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
```

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/projects" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Anime Episode 01 - 4K Upscale\", \"video_asset_id\": \"a6f6ad38-7e1f-4db9-91d8-92b764b1c001\"}"
```

Explicar que un proyecto:

* Requiere un video importado.
* No procesa video todavía.
* Guarda configuración para futuros jobs.
* Será la unidad principal del workspace de Oroya Video.

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe modelo ORM `Project`.
* Existe relación entre `Project` y `VideoAsset`.
* Existe repositorio de proyectos.
* Existe servicio de proyectos.
* Existe router `routes_projects.py`.
* El router principal incluye `/api/projects`.
* `POST /api/projects` crea proyectos.
* `GET /api/projects` lista proyectos.
* `GET /api/projects/{project_id}` devuelve detalle completo.
* `PATCH /api/projects/{project_id}` actualiza parcialmente.
* `DELETE /api/projects/{project_id}` elimina proyectos.
* Crear proyecto requiere un `video_asset_id` válido.
* El backend valida que el archivo asociado al video exista.
* El proyecto guarda `enhancement_config_json`.
* El proyecto guarda `export_config_json`.
* El proyecto guarda `workspace_state_json`.
* Se aplican configuraciones por defecto.
* `PATCH` hace merge superficial de configuraciones.
* `last_opened_at` se actualiza al abrir detalle.
* Eliminar proyecto no elimina el video asset.
* Eliminar proyecto no borra archivos originales.
* Los errores están controlados.
* Los tests pasan.
* README documenta los endpoints.
* No se implementan todavía jobs ni procesamiento real.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible ejecutar:

```bash
cd backend
uvicorn app.main:app --reload
```

Luego:

1. Importar un video con:

```text
POST /api/videos/import
```

2. Crear un proyecto con:

```text
POST /api/projects
```

3. Listar proyectos con:

```text
GET /api/projects
```

4. Abrir un proyecto con:

```text
GET /api/projects/{project_id}
```

5. Actualizar configuración con:

```text
PATCH /api/projects/{project_id}
```

6. Eliminar el proyecto con:

```text
DELETE /api/projects/{project_id}
```

Este requerimiento deja preparado el backend para el siguiente paso: gestión inicial de modelos IA disponibles para el procesamiento.
