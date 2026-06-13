# REQ-006 - AI Models Registry

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
```

El backend ya debe tener:

* FastAPI funcional.
* SQLite inicializado.
* Sistema de paths.
* Logging.
* CRUD de videos importados.
* CRUD de proyectos.
* Configuración de mejora guardada en proyectos.
* Campo `model_id` dentro de `enhancement_config`.

---

# Objetivo

Implementar un registro local de modelos de inteligencia artificial disponibles para Oroya Video.

Este requerimiento debe permitir que el backend conozca qué modelos existen, cuáles están instalados, dónde están almacenados, qué capacidades tienen y qué requisitos aproximados de hardware necesitan.

No se debe implementar todavía inferencia real ni procesamiento con IA.

---

# Contexto

Oroya Video necesita seleccionar modelos IA antes de crear jobs de procesamiento.

En el MVP los modelos principales serán:

```text
Real-ESRGAN x2
Real-ESRGAN x4
Real-ESRGAN General
```

La UI necesita mostrar estos modelos como tarjetas seleccionables, incluyendo:

* Nombre.
* Descripción.
* Tipo.
* Estado de instalación.
* Factor de escala.
* Requisito estimado de VRAM.
* Si está disponible para usar.
* Ruta local del modelo si está instalado.

---

# Concepto principal

## AIModel

Un `AIModel` representa un modelo de IA registrado dentro de Oroya Video.

Puede estar:

* Disponible conceptualmente, pero no instalado.
* Instalado manualmente.
* Pendiente de descarga futura.
* Deshabilitado.
* No compatible con el sistema actual.

En este requerimiento, los modelos pueden registrarse y marcarse como instalados si existe su archivo local.

---

# Decisión MVP

Para este requerimiento no se descargan modelos automáticamente.

La instalación inicial puede ser:

```text
manual
```

Esto significa que el usuario o desarrollador coloca los archivos del modelo en:

```text
storage/models/
```

Y el backend detecta si existen.

Más adelante se podrá implementar descarga automática, marketplace o instalación desde URL.

---

# Alcance de este requerimiento

Implementar:

1. Modelo ORM `AIModel`.
2. Registro inicial de modelos conocidos.
3. Repositorio de modelos.
4. Servicio de modelos.
5. Endpoints para listar modelos.
6. Endpoint para consultar un modelo.
7. Endpoint para registrar un modelo manualmente.
8. Endpoint para refrescar estado de instalación.
9. Endpoint para habilitar o deshabilitar modelos.
10. Validación de modelo dentro de configuración de proyecto.
11. Tests.
12. Actualización del README.

No implementar todavía:

* Descarga automática de modelos.
* PyTorch.
* Real-ESRGAN real.
* Inferencia.
* Procesamiento de frames.
* Jobs.
* Benchmark de rendimiento.
* Marketplace.
* Plugins.

---

# Estructura a modificar

Agregar o actualizar:

```text
backend/
├── app/
│   ├── api/
│   │   ├── router.py
│   │   └── routes_models.py
│   │
│   ├── core/
│   │   ├── errors.py
│   │   └── paths.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   └── repositories/
│   │       └── ai_model_repository.py
│   │
│   ├── schemas/
│   │   └── ai_model_schema.py
│   │
│   └── services/
│       └── ai_model_service.py
│
├── storage/
│   └── models/
│       └── realesrgan/
│
├── tests/
│   └── test_ai_models.py
│
└── README.md
```

---

# Paths

Actualizar:

```text
app/core/paths.py
```

Agregar funciones:

```python
get_ai_models_path()
get_realesrgan_models_path()
get_model_path(relative_path: str)
```

La estructura inicial esperada será:

```text
storage/models/
└── realesrgan/
    ├── realesrgan-x2.pth
    ├── realesrgan-x4.pth
    └── realesrgan-general.pth
```

Los nombres exactos pueden cambiar en el futuro, pero para el MVP se usarán estos identificadores internos.

---

# Modelo ORM

Actualizar:

```text
app/db/models.py
```

Agregar:

```python
class AIModel(Base):
    __tablename__ = "ai_models"
```

Campos requeridos:

```text
id
name
slug
description
provider
category
model_type
scale_factor
version
status
is_enabled
is_installed
file_name
relative_path
absolute_path
file_size_bytes
estimated_vram_mb
supports_gpu
supports_cpu
capabilities_json
metadata_json
created_at
updated_at
```

Tipos sugeridos:

```text
id                    String primary key UUID
name                  String not null
slug                  String unique not null
description           Text nullable
provider              String not null
category              String not null
model_type            String not null
scale_factor           Integer nullable
version               String nullable
status                String not null
is_enabled             Boolean not null
is_installed           Boolean not null
file_name              String nullable
relative_path          String nullable
absolute_path          String nullable
file_size_bytes        Integer nullable
estimated_vram_mb      Integer nullable
supports_gpu           Boolean not null
supports_cpu           Boolean not null
capabilities_json      Text not null
metadata_json          Text not null
created_at             DateTime not null
updated_at             DateTime not null
```

---

# Estados del modelo

Estados permitidos:

```text
available
installed
missing
disabled
incompatible
error
```

Descripción:

```text
available      El modelo está registrado, pero no necesariamente instalado.
installed      El archivo del modelo existe y puede usarse.
missing        El archivo esperado no existe.
disabled       El modelo fue deshabilitado por el usuario o sistema.
incompatible   El modelo no es compatible con el entorno actual.
error          Hubo un problema validando el modelo.
```

---

# Categorías

Categorías iniciales:

```text
upscaling
restoration
interpolation
face_enhancement
experimental
```

Para el MVP se usarán principalmente:

```text
upscaling
restoration
```

---

# Modelos seed iniciales

Al inicializar la base de datos, el backend debe poder registrar estos modelos si no existen.

## Real-ESRGAN x2

```json
{
  "name": "Real-ESRGAN x2",
  "slug": "realesrgan-x2",
  "description": "General purpose 2x video frame upscaling model.",
  "provider": "Real-ESRGAN",
  "category": "upscaling",
  "model_type": "realesrgan",
  "scale_factor": 2,
  "version": "mvp",
  "status": "missing",
  "is_enabled": true,
  "is_installed": false,
  "file_name": "realesrgan-x2.pth",
  "relative_path": "realesrgan/realesrgan-x2.pth",
  "estimated_vram_mb": 4096,
  "supports_gpu": true,
  "supports_cpu": true,
  "capabilities": {
    "upscale": true,
    "restore": false,
    "frame_interpolation": false,
    "face_enhancement": false
  }
}
```

## Real-ESRGAN x4

```json
{
  "name": "Real-ESRGAN x4",
  "slug": "realesrgan-x4",
  "description": "High quality 4x video frame upscaling model.",
  "provider": "Real-ESRGAN",
  "category": "upscaling",
  "model_type": "realesrgan",
  "scale_factor": 4,
  "version": "mvp",
  "status": "missing",
  "is_enabled": true,
  "is_installed": false,
  "file_name": "realesrgan-x4.pth",
  "relative_path": "realesrgan/realesrgan-x4.pth",
  "estimated_vram_mb": 8192,
  "supports_gpu": true,
  "supports_cpu": true,
  "capabilities": {
    "upscale": true,
    "restore": false,
    "frame_interpolation": false,
    "face_enhancement": false
  }
}
```

## Real-ESRGAN General

```json
{
  "name": "Real-ESRGAN General",
  "slug": "realesrgan-general",
  "description": "General restoration model for improving compressed or degraded frames.",
  "provider": "Real-ESRGAN",
  "category": "restoration",
  "model_type": "realesrgan",
  "scale_factor": null,
  "version": "mvp",
  "status": "missing",
  "is_enabled": true,
  "is_installed": false,
  "file_name": "realesrgan-general.pth",
  "relative_path": "realesrgan/realesrgan-general.pth",
  "estimated_vram_mb": 4096,
  "supports_gpu": true,
  "supports_cpu": true,
  "capabilities": {
    "upscale": false,
    "restore": true,
    "frame_interpolation": false,
    "face_enhancement": false
  }
}
```

---

# Inicialización de modelos

Crear en el servicio:

```python
def seed_default_models(db: Session) -> None:
    ...
```

Reglas:

* Si un modelo con el mismo `slug` ya existe, no duplicarlo.
* Si no existe, crearlo.
* Después de crearlo, validar si su archivo existe en `storage/models`.
* Actualizar `status`, `is_installed`, `absolute_path` y `file_size_bytes`.

Este seed debe ejecutarse al iniciar la app después de inicializar la DB.

---

# Schemas

Crear:

```text
app/schemas/ai_model_schema.py
```

## AIModelResponse

```python
class AIModelResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    provider: str
    category: str
    model_type: str
    scale_factor: int | None
    version: str | None
    status: str
    is_enabled: bool
    is_installed: bool
    file_name: str | None
    relative_path: str | None
    absolute_path: str | None
    file_size_bytes: int | None
    estimated_vram_mb: int | None
    supports_gpu: bool
    supports_cpu: bool
    capabilities: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
```

## AIModelListResponse

```python
class AIModelListResponse(BaseModel):
    items: list[AIModelResponse]
    total: int
```

## AIModelCreateRequest

```python
class AIModelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    slug: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    provider: str = "custom"
    category: str
    model_type: str
    scale_factor: int | None = None
    version: str | None = None
    file_name: str | None = None
    relative_path: str | None = None
    estimated_vram_mb: int | None = None
    supports_gpu: bool = true
    supports_cpu: bool = true
    capabilities: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
```

## AIModelUpdateRequest

```python
class AIModelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: str | None = None
    is_enabled: bool | None = None
    relative_path: str | None = None
    estimated_vram_mb: int | None = None
    capabilities: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
```

## AIModelRefreshResponse

```python
class AIModelRefreshResponse(BaseModel):
    refreshed: bool
    items: list[AIModelResponse]
    total: int
```

---

# Repository

Crear:

```text
app/db/repositories/ai_model_repository.py
```

Funciones sugeridas:

```python
def create_ai_model(db: Session, data: dict) -> AIModel:
    ...


def get_ai_model_by_id(db: Session, model_id: str) -> AIModel | None:
    ...


def get_ai_model_by_slug(db: Session, slug: str) -> AIModel | None:
    ...


def list_ai_models(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
    status: str | None = None,
    installed: bool | None = None,
    enabled: bool | None = None,
) -> list[AIModel]:
    ...


def count_ai_models(
    db: Session,
    category: str | None = None,
    status: str | None = None,
    installed: bool | None = None,
    enabled: bool | None = None,
) -> int:
    ...


def update_ai_model(db: Session, model: AIModel, data: dict) -> AIModel:
    ...


def delete_ai_model(db: Session, model: AIModel) -> None:
    ...
```

Reglas:

* Ordenar por `category`, luego por `name`.
* `slug` debe ser único.
* No borrar archivos físicos al eliminar un modelo.
* No permitir duplicados por `slug`.

---

# Servicio

Crear:

```text
app/services/ai_model_service.py
```

Responsabilidades:

1. Registrar modelos por defecto.
2. Listar modelos.
3. Consultar modelo por ID o slug.
4. Crear modelos personalizados.
5. Actualizar metadata de modelos.
6. Refrescar estado de instalación.
7. Habilitar/deshabilitar modelos.
8. Validar si un modelo está disponible para procesamiento futuro.

Funciones sugeridas:

```python
def seed_default_models(db: Session) -> None:
    ...


def list_models(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
    status: str | None = None,
    installed: bool | None = None,
    enabled: bool | None = None,
) -> AIModelListResponse:
    ...


def get_model(
    db: Session,
    model_id_or_slug: str,
) -> AIModelResponse:
    ...


def create_model(
    db: Session,
    request: AIModelCreateRequest,
) -> AIModelResponse:
    ...


def update_model(
    db: Session,
    model_id_or_slug: str,
    request: AIModelUpdateRequest,
) -> AIModelResponse:
    ...


def refresh_models(
    db: Session,
) -> AIModelRefreshResponse:
    ...


def validate_model_available(
    db: Session,
    model_slug: str,
) -> AIModelResponse:
    ...
```

---

# Refresh de instalación

El servicio debe revisar si existe físicamente el archivo del modelo.

Ejemplo:

```text
storage/models/realesrgan/realesrgan-x2.pth
```

Si existe:

```text
is_installed = true
status = installed
absolute_path = resolved path
file_size_bytes = real file size
```

Si no existe:

```text
is_installed = false
status = missing
absolute_path = null
file_size_bytes = null
```

Si el modelo está deshabilitado:

```text
status = disabled
```

El refresh no debe fallar si el archivo no existe.

---

# Endpoints requeridos

Todos bajo:

```text
/api/models
```

---

## GET /api/models

Lista modelos registrados.

Query params:

```text
limit: int = 50
offset: int = 0
category: str | None = None
status: str | None = None
installed: bool | None = None
enabled: bool | None = None
```

### Response 200

```json
{
  "items": [
    {
      "id": "6fcff276-a744-46ef-b81d-92aa5094f322",
      "name": "Real-ESRGAN x2",
      "slug": "realesrgan-x2",
      "description": "General purpose 2x video frame upscaling model.",
      "provider": "Real-ESRGAN",
      "category": "upscaling",
      "model_type": "realesrgan",
      "scale_factor": 2,
      "version": "mvp",
      "status": "missing",
      "is_enabled": true,
      "is_installed": false,
      "file_name": "realesrgan-x2.pth",
      "relative_path": "realesrgan/realesrgan-x2.pth",
      "absolute_path": null,
      "file_size_bytes": null,
      "estimated_vram_mb": 4096,
      "supports_gpu": true,
      "supports_cpu": true,
      "capabilities": {
        "upscale": true,
        "restore": false
      },
      "metadata": {},
      "created_at": "2026-06-13T12:00:00",
      "updated_at": "2026-06-13T12:00:00"
    }
  ],
  "total": 3
}
```

---

## GET /api/models/{model_id_or_slug}

Devuelve un modelo por ID o slug.

Ejemplos válidos:

```text
GET /api/models/realesrgan-x2
GET /api/models/6fcff276-a744-46ef-b81d-92aa5094f322
```

---

## POST /api/models

Registra un modelo personalizado.

### Request

```json
{
  "name": "Custom Real-ESRGAN Anime",
  "slug": "custom-realesrgan-anime",
  "description": "Custom anime upscaling model.",
  "provider": "custom",
  "category": "upscaling",
  "model_type": "realesrgan",
  "scale_factor": 4,
  "file_name": "custom-anime-x4.pth",
  "relative_path": "custom/custom-anime-x4.pth",
  "estimated_vram_mb": 8192,
  "supports_gpu": true,
  "supports_cpu": true,
  "capabilities": {
    "upscale": true,
    "restore": false
  },
  "metadata": {
    "notes": "Manual model registration."
  }
}
```

### Response 201

Devuelve `AIModelResponse`.

---

## PATCH /api/models/{model_id_or_slug}

Actualiza metadata de un modelo.

### Request

```json
{
  "description": "Updated model description.",
  "is_enabled": false
}
```

### Response 200

Devuelve `AIModelResponse`.

---

## POST /api/models/refresh

Refresca el estado de instalación de todos los modelos.

### Response 200

```json
{
  "refreshed": true,
  "items": [],
  "total": 3
}
```

---

## POST /api/models/{model_id_or_slug}/enable

Habilita un modelo.

### Response 200

Devuelve `AIModelResponse`.

---

## POST /api/models/{model_id_or_slug}/disable

Deshabilita un modelo.

### Response 200

Devuelve `AIModelResponse`.

---

## DELETE /api/models/{model_id_or_slug}

Elimina el registro de un modelo.

Reglas:

* No borrar el archivo físico.
* No permitir eliminar modelos seed por defecto en esta fase.
* Sí permitir deshabilitarlos.

Si intenta borrar un modelo seed:

Status:

```text
400
```

Response:

```json
{
  "error": "default_model_cannot_be_deleted",
  "message": "Default models cannot be deleted. Disable the model instead."
}
```

---

# Validación en proyectos

Actualizar `project_service.py`.

Cuando se cree o actualice un proyecto y llegue:

```json
{
  "enhancement_config": {
    "model_id": "realesrgan-x4"
  }
}
```

El backend debe validar:

1. Que exista un modelo con ese slug.
2. Que esté habilitado.
3. No exigir todavía que esté instalado.

Si el modelo no existe:

Status:

```text
404
```

Response:

```json
{
  "error": "ai_model_not_found",
  "message": "AI model was not found."
}
```

Si el modelo está deshabilitado:

Status:

```text
409
```

Response:

```json
{
  "error": "ai_model_disabled",
  "message": "AI model is disabled."
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
class AIModelNotFoundError(OroyaVideoError):
    pass


class AIModelAlreadyExistsError(OroyaVideoError):
    pass


class AIModelDisabledError(OroyaVideoError):
    pass


class DefaultModelCannotBeDeletedError(OroyaVideoError):
    pass


class AIModelCreateFailedError(OroyaVideoError):
    pass


class AIModelUpdateFailedError(OroyaVideoError):
    pass
```

---

# Logging

Registrar eventos:

```text
AI model seed started
AI model seed completed
AI model created
AI model updated
AI model listed
AI model requested
AI model refresh started
AI model refresh completed
AI model enabled
AI model disabled
AI model not found
AI model file missing
AI model file detected
Default model delete blocked
```

---

# Tests

Crear:

```text
tests/test_ai_models.py
```

Los tests deben usar SQLite temporal o en memoria.

Pruebas mínimas:

1. Al iniciar seed, se crean los 3 modelos por defecto.
2. El seed no duplica modelos si se ejecuta dos veces.
3. `GET /api/models` devuelve lista de modelos.
4. `GET /api/models/realesrgan-x2` devuelve el modelo correcto.
5. `GET /api/models/unknown` responde `404`.
6. `POST /api/models` crea un modelo personalizado.
7. `POST /api/models` responde error si el slug ya existe.
8. `PATCH /api/models/{slug}` actualiza descripción.
9. `POST /api/models/refresh` marca modelo como `installed` si el archivo existe.
10. `POST /api/models/refresh` marca modelo como `missing` si el archivo no existe.
11. `POST /api/models/{slug}/disable` deshabilita modelo.
12. `POST /api/models/{slug}/enable` habilita modelo.
13. `DELETE /api/models/{slug}` no permite eliminar modelos seed.
14. `DELETE /api/models/{slug}` permite eliminar modelos personalizados.
15. Crear proyecto con modelo inexistente responde `404`.
16. Crear proyecto con modelo deshabilitado responde `409`.
17. Crear proyecto con modelo existente y habilitado funciona.

---

# Actualizar README

Agregar sección:

```text
AI model endpoints
```

Documentar:

```text
GET    /api/models
GET    /api/models/{model_id_or_slug}
POST   /api/models
PATCH  /api/models/{model_id_or_slug}
POST   /api/models/refresh
POST   /api/models/{model_id_or_slug}/enable
POST   /api/models/{model_id_or_slug}/disable
DELETE /api/models/{model_id_or_slug}
```

Agregar nota:

```text
In the MVP, model files are installed manually by placing them under storage/models.
Automatic model downloads are not implemented yet.
```

Ejemplo:

```bash
curl "http://127.0.0.1:8000/api/models"
```

Ejemplo refresh:

```bash
curl -X POST "http://127.0.0.1:8000/api/models/refresh"
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe modelo ORM `AIModel`.
* Existen los 3 modelos seed del MVP.
* El seed no duplica modelos.
* Existe repositorio de modelos.
* Existe servicio de modelos.
* Existe router `routes_models.py`.
* El router principal incluye `/api/models`.
* `GET /api/models` lista modelos.
* `GET /api/models/{model_id_or_slug}` obtiene modelo por ID o slug.
* `POST /api/models` permite registrar modelos personalizados.
* `PATCH /api/models/{model_id_or_slug}` actualiza modelos.
* `POST /api/models/refresh` detecta archivos existentes.
* `POST /api/models/{slug}/enable` habilita modelos.
* `POST /api/models/{slug}/disable` deshabilita modelos.
* No se pueden eliminar modelos por defecto.
* Sí se pueden eliminar modelos personalizados.
* La creación y actualización de proyectos valida `model_id`.
* No se exige que el modelo esté instalado todavía.
* Los errores están controlados.
* Los tests pasan.
* README documenta los endpoints.
* No se implementa todavía procesamiento real con IA.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible ejecutar:

```bash
cd backend
uvicorn app.main:app --reload
```

Luego consultar:

```text
GET http://127.0.0.1:8000/api/models
GET http://127.0.0.1:8000/api/models/realesrgan-x2
POST http://127.0.0.1:8000/api/models/refresh
```

Y obtener el registro local de modelos IA disponibles para Oroya Video.

Este requerimiento deja preparado el backend para el siguiente paso: creación de jobs de procesamiento sin ejecutar todavía el pipeline pesado.
