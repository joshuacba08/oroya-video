# REQ-004 - Local Video Import & Storage Registration

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
```

El backend ya debe tener:

* FastAPI funcional.
* Configuración centralizada.
* Sistema de paths.
* Logging.
* Detección de FFmpeg / FFprobe.
* Endpoint de análisis de video `POST /api/videos/probe`.
* Servicio `video_probe_service.py`.
* Schemas de metadata de video.
* Manejo de errores controlados para video probe.

---

# Objetivo

Implementar la importación lógica de videos dentro de Oroya Video.

En este requerimiento, “importar” significa registrar un archivo de video local dentro del sistema, guardar su metadata en SQLite y dejarlo disponible para futuros proyectos, jobs y procesamiento.

El backend debe permitir:

1. Recibir una ruta local de video.
2. Validar el archivo usando el sistema de probe existente.
3. Registrar el video en base de datos.
4. Guardar metadata técnica.
5. Opcionalmente copiar el archivo a una carpeta interna de storage.
6. Listar videos importados.
7. Consultar un video importado.
8. Eliminar el registro de un video importado.

Este requerimiento no debe crear proyectos todavía.

---

# Contexto

Hasta el requerimiento anterior, Oroya Video puede analizar un video con `ffprobe`, pero esa información no queda guardada.

Ahora se necesita crear la primera entidad persistente real del backend: `VideoAsset`.

Un `VideoAsset` representa un video que Oroya Video conoce y puede usar en futuros proyectos.

La app desktop podrá usar este flujo así:

```text
User selects file with Tauri
        ↓
Frontend sends local path to backend
        ↓
Backend probes video metadata
        ↓
Backend registers video asset
        ↓
Frontend receives video_asset_id
        ↓
Video becomes available for project creation
```

---

# Decisión importante del MVP

Oroya Video no debe copiar videos grandes por defecto.

Muchos videos pueden pesar varios GB, así que el comportamiento inicial será:

```text
source_mode = reference
```

Esto significa que el backend guarda la ruta original del archivo y su metadata, pero no copia el video.

También se debe soportar opcionalmente:

```text
source_mode = copy
```

En ese caso, el backend copiará el video a una carpeta interna:

```text
storage/imports/{video_asset_id}/original.{ext}
```

---

# Stack adicional requerido

Agregar soporte de base de datos con SQLAlchemy.

Dependencias nuevas:

```text
sqlalchemy
```

Opcional pero recomendado:

```text
alembic
```

Para este requerimiento, Alembic puede quedar preparado, pero no es obligatorio implementar migraciones completas todavía.

---

# Alcance de este requerimiento

Implementar:

1. Base de datos SQLite real.
2. Modelo ORM `VideoAsset`.
3. Repositorio para videos.
4. Servicio de importación de videos.
5. Endpoint `POST /api/videos/import`.
6. Endpoint `GET /api/videos`.
7. Endpoint `GET /api/videos/{video_id}`.
8. Endpoint `DELETE /api/videos/{video_id}`.
9. Registro de metadata técnica del video.
10. Manejo de modo `reference` y modo `copy`.
11. Carpeta `storage/imports`.
12. Tests con mocks.
13. Actualización del README.

No implementar todavía:

* Proyectos.
* Jobs.
* Cola de procesamiento.
* Extracción de frames.
* Thumbnails.
* Previews.
* Procesamiento IA.
* Exportación.
* Batch import.
* Watch folders.

---

# Estructura a modificar

Agregar o actualizar:

```text
backend/
├── app/
│   ├── api/
│   │   ├── router.py
│   │   └── routes_videos.py
│   │
│   ├── core/
│   │   ├── paths.py
│   │   └── errors.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── models.py
│   │   └── repositories/
│   │       ├── __init__.py
│   │       └── video_repository.py
│   │
│   ├── schemas/
│   │   └── video_schema.py
│   │
│   └── services/
│       ├── video_probe_service.py
│       └── video_import_service.py
│
├── storage/
│   ├── db/
│   ├── imports/
│   └── temp/
│
├── tests/
│   └── test_video_import.py
│
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

# Base de datos

Crear o actualizar:

```text
app/db/database.py
```

Debe exponer:

```python
engine
SessionLocal
Base
get_db()
init_db()
```

Reglas:

* Usar SQLite.
* Usar la ruta configurada en `database_url`.
* Crear tablas automáticamente en desarrollo usando `Base.metadata.create_all`.
* `get_db()` debe ser compatible con dependencias de FastAPI.
* La conexión SQLite debe usar `check_same_thread=False`.

Ejemplo conceptual:

```python
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
```

---

# Inicialización de DB

Actualizar `app/main.py`.

Al iniciar la aplicación debe:

1. Crear carpetas de storage.
2. Configurar logging.
3. Inicializar base de datos.
4. Registrar routers.

En desarrollo, debe crear automáticamente las tablas necesarias.

---

# Paths locales

Actualizar:

```text
app/core/paths.py
```

Agregar:

```python
get_imports_path()
get_video_import_path(video_asset_id: str)
```

También actualizar:

```python
ensure_storage_directories()
```

Para crear:

```text
storage/imports
```

---

# Modelo ORM

Crear o actualizar:

```text
app/db/models.py
```

Agregar modelo:

```python
class VideoAsset(Base):
    __tablename__ = "video_assets"
```

Campos requeridos:

```text
id
source_path
stored_path
source_mode
file_name
file_extension
file_size_bytes
file_size_mb
format_name
duration_seconds
duration_label
bit_rate
video_codec
video_codec_long_name
width
height
resolution_label
fps
pix_fmt
video_profile
video_bit_rate
has_audio
audio_codec
audio_codec_long_name
audio_sample_rate
audio_channels
audio_channel_layout
audio_bit_rate
streams_json
warnings_json
fingerprint
created_at
updated_at
```

Tipos sugeridos:

```text
id                  String primary key UUID
source_path          String not null
stored_path          String nullable
source_mode          String not null
file_name            String not null
file_extension       String not null
file_size_bytes      Integer not null
file_size_mb         Float not null
duration_seconds     Float nullable
fps                  Float nullable
streams_json         Text not null
warnings_json        Text not null
fingerprint          String nullable
created_at           DateTime
updated_at           DateTime
```

---

# Fingerprint inicial

No calcular hash completo del archivo en este requerimiento.

Los videos pueden ser demasiado grandes.

Crear un fingerprint ligero basado en:

```text
resolved file path
file size
last modified timestamp
```

Ejemplo:

```text
sha256("{path}:{size}:{mtime}")
```

Este fingerprint sirve para detectar si el mismo archivo ya fue registrado.

---

# Reglas de duplicados

Si se intenta importar el mismo video otra vez:

* Detectar por `fingerprint`.
* No crear un duplicado.
* Devolver el registro existente.
* Incluir un campo `already_imported: true` en la respuesta.

Si es una importación nueva:

```json
{
  "already_imported": false
}
```

---

# Schemas

Actualizar:

```text
app/schemas/video_schema.py
```

Agregar:

```python
class VideoImportRequest(BaseModel):
    file_path: str = Field(..., min_length=1)
    source_mode: Literal["reference", "copy"] = "reference"


class VideoAssetResponse(BaseModel):
    id: str
    source_path: str
    stored_path: str | None
    source_mode: str
    file_name: str
    file_extension: str
    file_size_bytes: int
    file_size_mb: float
    format_name: str | None
    duration_seconds: float | None
    duration_label: str | None
    bit_rate: int | None
    video_codec: str | None
    video_codec_long_name: str | None
    width: int | None
    height: int | None
    resolution_label: str | None
    fps: float | None
    pix_fmt: str | None
    video_profile: str | None
    video_bit_rate: int | None
    has_audio: bool
    audio_codec: str | None
    audio_codec_long_name: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    audio_channel_layout: str | None
    audio_bit_rate: int | None
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class VideoImportResponse(BaseModel):
    video: VideoAssetResponse
    already_imported: bool


class VideoListResponse(BaseModel):
    items: list[VideoAssetResponse]
    total: int
```

---

# Repository

Crear:

```text
app/db/repositories/video_repository.py
```

Responsabilidades:

* Crear video asset.
* Buscar por ID.
* Buscar por fingerprint.
* Listar videos.
* Eliminar video asset.
* Convertir ORM a schema o dict.

Funciones sugeridas:

```python
def create_video_asset(db: Session, data: dict) -> VideoAsset:
    ...


def get_video_asset_by_id(db: Session, video_id: str) -> VideoAsset | None:
    ...


def get_video_asset_by_fingerprint(db: Session, fingerprint: str) -> VideoAsset | None:
    ...


def list_video_assets(db: Session, limit: int = 50, offset: int = 0) -> list[VideoAsset]:
    ...


def count_video_assets(db: Session) -> int:
    ...


def delete_video_asset(db: Session, video: VideoAsset) -> None:
    ...
```

---

# Servicio de importación

Crear:

```text
app/services/video_import_service.py
```

Responsabilidades:

1. Recibir `file_path`.
2. Ejecutar `probe_video(file_path)` usando `video_probe_service`.
3. Calcular fingerprint.
4. Revisar si ya existe el video en DB.
5. Si existe, devolverlo con `already_imported: true`.
6. Si no existe, crear registro.
7. Si `source_mode = copy`, copiar archivo a storage.
8. Devolver `VideoImportResponse`.

Funciones sugeridas:

```python
def import_video(
    db: Session,
    file_path: str,
    source_mode: str = "reference",
) -> VideoImportResponse:
    ...


def copy_video_to_storage(
    source_path: Path,
    video_asset_id: str,
) -> Path:
    ...


def calculate_file_fingerprint(path: Path) -> str:
    ...
```

---

# Modo reference

Si `source_mode = reference`:

* No copiar archivo.
* Guardar `source_path`.
* Guardar `stored_path = null`.
* El backend usará la ruta original para futuros procesos.

Respuesta:

```json
{
  "video": {
    "source_mode": "reference",
    "source_path": "C:\\Users\\user\\Videos\\sample.mp4",
    "stored_path": null
  },
  "already_imported": false
}
```

---

# Modo copy

Si `source_mode = copy`:

* Crear carpeta:

```text
storage/imports/{video_asset_id}/
```

* Copiar archivo como:

```text
storage/imports/{video_asset_id}/original.mp4
```

* Guardar `source_path` original.
* Guardar `stored_path` interno.

Respuesta:

```json
{
  "video": {
    "source_mode": "copy",
    "source_path": "C:\\Users\\user\\Videos\\sample.mp4",
    "stored_path": "storage/imports/{video_asset_id}/original.mp4"
  },
  "already_imported": false
}
```

Reglas:

* Usar `shutil.copy2`.
* No borrar el archivo original.
* Si falla la copia, no dejar registro corrupto en DB.
* Si se crea una carpeta parcial y falla, registrar warning y limpiar si es seguro.

---

# Endpoints requeridos

## POST /api/videos/import

Importa o registra un video local.

### Request

```json
{
  "file_path": "C:\\Users\\user\\Videos\\sample.mp4",
  "source_mode": "reference"
}
```

### Response 201

```json
{
  "video": {
    "id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001",
    "source_path": "C:\\Users\\user\\Videos\\sample.mp4",
    "stored_path": null,
    "source_mode": "reference",
    "file_name": "sample.mp4",
    "file_extension": ".mp4",
    "file_size_bytes": 524288000,
    "file_size_mb": 500.0,
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "duration_seconds": 128.45,
    "duration_label": "00:02:08",
    "bit_rate": 8000000,
    "video_codec": "h264",
    "video_codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
    "width": 1920,
    "height": 1080,
    "resolution_label": "1920x1080",
    "fps": 23.976,
    "pix_fmt": "yuv420p",
    "video_profile": "High",
    "video_bit_rate": 7500000,
    "has_audio": true,
    "audio_codec": "aac",
    "audio_codec_long_name": "AAC (Advanced Audio Coding)",
    "audio_sample_rate": 48000,
    "audio_channels": 2,
    "audio_channel_layout": "stereo",
    "audio_bit_rate": 320000,
    "warnings": [],
    "created_at": "2026-06-13T12:00:00",
    "updated_at": "2026-06-13T12:00:00"
  },
  "already_imported": false
}
```

Si el video ya estaba registrado:

### Response 200

```json
{
  "video": {
    "id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001"
  },
  "already_imported": true
}
```

---

## GET /api/videos

Lista videos importados.

Query params:

```text
limit: int = 50
offset: int = 0
```

Response:

```json
{
  "items": [],
  "total": 0
}
```

---

## GET /api/videos/{video_id}

Devuelve un video importado por ID.

Si no existe:

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

## DELETE /api/videos/{video_id}

Elimina el registro del video.

Reglas:

* Si `source_mode = reference`, eliminar solo el registro de DB.
* Si `source_mode = copy`, eliminar registro y carpeta interna `storage/imports/{video_id}`.
* Nunca borrar el archivo original indicado en `source_path`.

Response:

```json
{
  "deleted": true,
  "video_id": "a6f6ad38-7e1f-4db9-91d8-92b764b1c001"
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
class VideoAssetNotFoundError(OroyaVideoError):
    pass


class VideoImportFailedError(OroyaVideoError):
    pass


class VideoCopyFailedError(OroyaVideoError):
    pass
```

Errores esperados:

## Video asset no encontrado

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

## Fallo de importación

Status:

```text
500
```

Response:

```json
{
  "error": "video_import_failed",
  "message": "Video could not be imported."
}
```

## Fallo al copiar archivo

Status:

```text
500
```

Response:

```json
{
  "error": "video_copy_failed",
  "message": "Video could not be copied to internal storage."
}
```

---

# Router

Actualizar:

```text
app/api/router.py
```

Debe mantener:

```text
POST /api/videos/probe
```

Y agregar:

```text
POST   /api/videos/import
GET    /api/videos
GET    /api/videos/{video_id}
DELETE /api/videos/{video_id}
```

Todos bajo:

```text
/api/videos
```

---

# Logging

Registrar eventos:

```text
Video import requested
Video already imported
Video asset created
Video asset copied to storage
Video asset listed
Video asset requested
Video asset deleted
Video import failed
Video copy failed
```

No enviar rutas completas en errores al frontend.

En logs internos sí se puede registrar la ruta completa.

---

# Seguridad de archivos

Reglas:

* Resolver rutas con `Path(file_path).expanduser().resolve()`.
* No usar `shell=True`.
* No borrar archivos originales.
* No modificar archivos originales.
* No copiar si `source_mode = reference`.
* Si `source_mode = copy`, usar `shutil.copy2`.
* Validar espacio disponible antes de copiar.
* Si no hay espacio suficiente, responder error controlado.

---

# Validación de espacio para modo copy

Antes de copiar, verificar:

```text
free_disk_space > file_size_bytes
```

Si no hay espacio suficiente:

Status:

```text
400
```

Response:

```json
{
  "error": "insufficient_storage_space",
  "message": "Not enough storage space to copy the video."
}
```

Agregar excepción:

```python
class InsufficientStorageSpaceError(OroyaVideoError):
    pass
```

---

# Serialización de streams y warnings

Como SQLite no tendrá JSON nativo confiable en esta fase, guardar como texto JSON:

```text
streams_json
warnings_json
```

Al responder al frontend:

* Convertir `streams_json` a lista si se necesita más adelante.
* Exponer `warnings` como `list[str]`.
* No es obligatorio exponer `streams` completos en `VideoAssetResponse` en este requerimiento, pero sí deben quedar guardados.

---

# Tests

Crear:

```text
tests/test_video_import.py
```

Los tests no deben depender de videos reales ni de FFprobe real.

Usar mocks para:

* `video_probe_service.probe_video`
* `Path.exists`
* `Path.is_file`
* `Path.stat`
* `shutil.copy2`
* espacio en disco

Pruebas mínimas:

1. `POST /api/videos/import` registra un video en modo `reference`.
2. `POST /api/videos/import` devuelve `already_imported: false` en primera importación.
3. `POST /api/videos/import` devuelve `already_imported: true` al importar el mismo video otra vez.
4. `POST /api/videos/import` en modo `copy` llama a `shutil.copy2`.
5. Si falla la copia, responde error controlado.
6. Si no hay espacio suficiente, responde `400`.
7. `GET /api/videos` responde lista y total.
8. `GET /api/videos/{video_id}` responde un video existente.
9. `GET /api/videos/{video_id}` responde `404` si no existe.
10. `DELETE /api/videos/{video_id}` elimina el registro.
11. `DELETE /api/videos/{video_id}` no borra el archivo original.
12. `DELETE /api/videos/{video_id}` elimina carpeta interna solo si `source_mode = copy`.

---

# Base de datos de tests

Los tests deben usar una base SQLite temporal o en memoria.

No usar la base real:

```text
storage/db/oroya-video.sqlite
```

Opciones aceptadas:

```text
sqlite:///:memory:
```

o archivo temporal:

```text
tmp_path / "test.sqlite"
```

---

# Actualizar README

Agregar sección:

```text
Video import endpoints
```

Documentar:

```text
POST   /api/videos/import
GET    /api/videos
GET    /api/videos/{video_id}
DELETE /api/videos/{video_id}
```

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/videos/import" \
  -H "Content-Type: application/json" \
  -d "{\"file_path\": \"C:\\Users\\user\\Videos\\sample.mp4\", \"source_mode\": \"reference\"}"
```

Explicar diferencia entre:

```text
reference
copy
```

Reference:

```text
Guarda la ruta original del video. No copia el archivo.
```

Copy:

```text
Copia el video a storage/imports/{video_asset_id}/original.ext.
```

---

# Actualizar requirements.txt

Agregar:

```text
sqlalchemy
```

Si se decide preparar migraciones:

```text
alembic
```

---

# Actualizar pyproject.toml

Agregar dependencias principales:

```text
sqlalchemy
```

Opcional:

```text
alembic
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe configuración real de SQLite.
* Existe `VideoAsset` como modelo ORM.
* Existe repositorio de videos.
* Existe servicio de importación de videos.
* La app inicializa la DB al arrancar.
* `POST /api/videos/import` funciona.
* El endpoint usa internamente el probe del requerimiento anterior.
* El endpoint guarda metadata real del video en DB.
* El endpoint soporta `source_mode = reference`.
* El endpoint soporta `source_mode = copy`.
* El modo `reference` no copia archivos.
* El modo `copy` copia a `storage/imports/{video_asset_id}/original.ext`.
* Se detectan duplicados por fingerprint ligero.
* `GET /api/videos` lista videos registrados.
* `GET /api/videos/{video_id}` devuelve un video.
* `DELETE /api/videos/{video_id}` elimina un video.
* Nunca se borra el archivo original del usuario.
* Los errores están controlados.
* Los tests pasan.
* README documenta los nuevos endpoints.
* No se implementan todavía proyectos ni jobs.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible ejecutar:

```bash
cd backend
uvicorn app.main:app --reload
```

Importar un video:

```text
POST http://127.0.0.1:8000/api/videos/import
```

Con body:

```json
{
  "file_path": "C:\\Users\\user\\Videos\\sample.mp4",
  "source_mode": "reference"
}
```

Luego consultar:

```text
GET http://127.0.0.1:8000/api/videos
GET http://127.0.0.1:8000/api/videos/{video_id}
```

Y eliminar:

```text
DELETE http://127.0.0.1:8000/api/videos/{video_id}
```

Este requerimiento deja preparado el backend para el siguiente paso: creación y gestión de proyectos usando videos ya importados.
