# REQ-002 - System Info & Environment Detection

## Proyecto

Oroya Video

## Área

Backend

## Dependencia previa

Este requerimiento asume que ya existe y funciona:

```text
REQ-001 - Backend Foundation
```

La base FastAPI ya debe tener:

* Aplicación FastAPI funcional.
* Configuración centralizada.
* Sistema de paths.
* Logging.
* Endpoints `/api/health` y `/api/version`.
* Estructura modular inicial.
* Tests básicos.

---

# Objetivo

Implementar endpoints y servicios para detectar el entorno local donde se ejecuta Oroya Video.

El backend debe poder reportar información básica del sistema, disponibilidad de herramientas multimedia, rutas internas, espacio en disco y estado inicial de GPU NVIDIA si está disponible.

Este requerimiento prepara la base para futuros módulos de procesamiento de video, detección de FFmpeg, validación de requisitos y selección de recursos.

---

# Contexto

Oroya Video ejecutará procesamiento pesado de video e IA localmente.

Antes de permitir importar, procesar o exportar videos, la aplicación necesita saber si el entorno del usuario tiene las herramientas necesarias.

El backend debe poder responder preguntas como:

* ¿Qué sistema operativo está usando el usuario?
* ¿Qué versión de Python está ejecutando el backend?
* ¿Está FFmpeg instalado?
* ¿Está FFprobe disponible?
* ¿Hay GPU NVIDIA disponible?
* ¿Está disponible `nvidia-smi`?
* ¿Cuánta memoria RAM tiene el sistema?
* ¿Cuánto espacio libre hay en storage?
* ¿Qué rutas internas está usando Oroya Video?

---

# Stack adicional requerido

Agregar la siguiente dependencia:

```text
psutil
```

No instalar todavía:

* PyTorch
* OpenCV
* Real-ESRGAN
* CUDA Toolkit como dependencia Python

La detección de GPU en este requerimiento debe hacerse de forma ligera usando comandos del sistema, principalmente `nvidia-smi` cuando esté disponible.

---

# Alcance de este requerimiento

Implementar:

1. Endpoint de información general del sistema.
2. Endpoint de detección de herramientas multimedia.
3. Endpoint de detección básica de GPU.
4. Endpoint de información de almacenamiento.
5. Servicios internos para detectar binarios del sistema.
6. Schemas Pydantic para respuestas.
7. Logging de detección.
8. Tests unitarios básicos.

No implementar todavía:

* Video probe real de archivos.
* Importación de videos.
* Procesamiento con FFmpeg.
* OpenCV.
* PyTorch.
* CUDA desde Python.
* Jobs.
* Workers.
* Real-ESRGAN.
* Descarga de modelos.

---

# Estructura a modificar

Partiendo de la estructura existente, agregar o actualizar:

```text
backend/
├── app/
│   ├── api/
│   │   ├── router.py
│   │   └── routes_system.py
│   │
│   ├── schemas/
│   │   └── system_schema.py
│   │
│   ├── services/
│   │   ├── system_service.py
│   │   ├── tool_detection_service.py
│   │   └── gpu_detection_service.py
│   │
│   └── core/
│       └── paths.py
│
├── tests/
│   └── test_system.py
│
├── requirements.txt
└── pyproject.toml
```

---

# Endpoints requeridos

## GET /api/system/info

Debe devolver información general del entorno.

Respuesta esperada:

```json
{
  "app_name": "Oroya Video Backend",
  "app_version": "0.1.0",
  "environment": "development",
  "os": {
    "system": "Windows",
    "release": "10",
    "version": "10.0.19045",
    "machine": "AMD64"
  },
  "python": {
    "version": "3.13.0",
    "implementation": "CPython"
  },
  "memory": {
    "total_gb": 32.0,
    "available_gb": 18.5,
    "used_percent": 42.1
  }
}
```

---

## GET /api/system/tools

Debe detectar herramientas externas necesarias para el backend.

Herramientas a detectar:

```text
ffmpeg
ffprobe
nvidia-smi
```

Respuesta esperada:

```json
{
  "ffmpeg": {
    "available": true,
    "path": "C:\\ffmpeg\\bin\\ffmpeg.exe",
    "version": "ffmpeg version 7.1 ..."
  },
  "ffprobe": {
    "available": true,
    "path": "C:\\ffmpeg\\bin\\ffprobe.exe",
    "version": "ffprobe version 7.1 ..."
  },
  "nvidia_smi": {
    "available": true,
    "path": "C:\\Windows\\System32\\nvidia-smi.exe",
    "version": "NVIDIA-SMI 560.94 ..."
  }
}
```

Si una herramienta no está disponible:

```json
{
  "available": false,
  "path": null,
  "version": null
}
```

---

## GET /api/system/gpu

Debe detectar GPU NVIDIA de forma básica.

Para el MVP de este requerimiento usar:

```text
nvidia-smi
```

Si `nvidia-smi` está disponible, ejecutar consulta para obtener:

* Nombre de GPU.
* Driver version.
* VRAM total.
* VRAM usada.
* VRAM libre.
* Uso de GPU.
* Temperatura, si está disponible.

Comando sugerido:

```bash
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv,noheader,nounits
```

Respuesta esperada cuando hay GPU:

```json
{
  "available": true,
  "provider": "nvidia",
  "gpus": [
    {
      "name": "NVIDIA GeForce RTX 4070",
      "driver_version": "560.94",
      "memory_total_mb": 12288,
      "memory_used_mb": 1024,
      "memory_free_mb": 11264,
      "utilization_percent": 12,
      "temperature_celsius": 48
    }
  ]
}
```

Respuesta esperada cuando no hay GPU NVIDIA:

```json
{
  "available": false,
  "provider": null,
  "gpus": []
}
```

---

## GET /api/system/storage

Debe devolver información de rutas internas y espacio disponible.

Respuesta esperada:

```json
{
  "storage_path": "storage",
  "paths": {
    "db": "storage/db",
    "temp": "storage/temp",
    "exports": "storage/exports",
    "models": "storage/models",
    "logs": "storage/logs"
  },
  "disk": {
    "total_gb": 512.0,
    "used_gb": 240.5,
    "free_gb": 271.5,
    "used_percent": 47.0
  }
}
```

---

## GET /api/system/requirements

Debe devolver un resumen de si el entorno está listo para futuras funciones del MVP.

La lógica inicial será simple:

Requisitos mínimos:

```text
ffmpeg available
ffprobe available
storage writable
```

Requisitos recomendados:

```text
nvidia-smi available
gpu available
free disk space > 10GB
```

Respuesta esperada:

```json
{
  "ready": true,
  "minimum": {
    "ffmpeg": true,
    "ffprobe": true,
    "storage_writable": true
  },
  "recommended": {
    "nvidia_gpu": true,
    "free_disk_space": true
  },
  "warnings": []
}
```

Ejemplo con advertencias:

```json
{
  "ready": true,
  "minimum": {
    "ffmpeg": true,
    "ffprobe": true,
    "storage_writable": true
  },
  "recommended": {
    "nvidia_gpu": false,
    "free_disk_space": true
  },
  "warnings": [
    "NVIDIA GPU was not detected. Processing may be very slow in future AI tasks."
  ]
}
```

Si falta un requisito mínimo:

```json
{
  "ready": false,
  "minimum": {
    "ffmpeg": false,
    "ffprobe": true,
    "storage_writable": true
  },
  "recommended": {
    "nvidia_gpu": false,
    "free_disk_space": true
  },
  "warnings": [
    "FFmpeg was not detected. Video processing will not be available."
  ]
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
/api/system/info
/api/system/tools
/api/system/gpu
/api/system/storage
/api/system/requirements
```

Todos los endpoints deben estar agrupados bajo:

```text
/api/system
```

---

# Schemas

Crear:

```text
app/schemas/system_schema.py
```

Modelos sugeridos:

```python
class OSInfo(BaseModel):
    system: str
    release: str
    version: str
    machine: str


class PythonInfo(BaseModel):
    version: str
    implementation: str


class MemoryInfo(BaseModel):
    total_gb: float
    available_gb: float
    used_percent: float


class SystemInfoResponse(BaseModel):
    app_name: str
    app_version: str
    environment: str
    os: OSInfo
    python: PythonInfo
    memory: MemoryInfo


class ToolInfo(BaseModel):
    available: bool
    path: str | None = None
    version: str | None = None


class ToolsResponse(BaseModel):
    ffmpeg: ToolInfo
    ffprobe: ToolInfo
    nvidia_smi: ToolInfo


class GPUInfo(BaseModel):
    name: str
    driver_version: str | None = None
    memory_total_mb: int | None = None
    memory_used_mb: int | None = None
    memory_free_mb: int | None = None
    utilization_percent: int | None = None
    temperature_celsius: int | None = None


class GPUResponse(BaseModel):
    available: bool
    provider: str | None = None
    gpus: list[GPUInfo]


class StoragePaths(BaseModel):
    db: str
    temp: str
    exports: str
    models: str
    logs: str


class DiskInfo(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    used_percent: float


class StorageResponse(BaseModel):
    storage_path: str
    paths: StoragePaths
    disk: DiskInfo


class RequirementsMinimum(BaseModel):
    ffmpeg: bool
    ffprobe: bool
    storage_writable: bool


class RequirementsRecommended(BaseModel):
    nvidia_gpu: bool
    free_disk_space: bool


class RequirementsResponse(BaseModel):
    ready: bool
    minimum: RequirementsMinimum
    recommended: RequirementsRecommended
    warnings: list[str]
```

---

# Servicios

## system_service.py

Responsabilidades:

* Obtener información de OS.
* Obtener información de Python.
* Obtener memoria RAM.
* Obtener información de storage.
* Construir resumen de requisitos.

Funciones sugeridas:

```python
def get_system_info() -> SystemInfoResponse:
    ...


def get_storage_info() -> StorageResponse:
    ...


def get_requirements_status() -> RequirementsResponse:
    ...
```

---

## tool_detection_service.py

Responsabilidades:

* Detectar binarios del sistema.
* Ejecutar comandos de versión de forma segura.
* Manejar timeouts.
* Evitar que un comando externo bloquee el backend.

Funciones sugeridas:

```python
def detect_tool(command: str, version_args: list[str] | None = None) -> ToolInfo:
    ...


def get_tools_status() -> ToolsResponse:
    ...
```

Reglas:

* Usar `shutil.which`.
* Usar `subprocess.run`.
* Definir timeout máximo de 5 segundos.
* Capturar errores.
* No lanzar excepción si la herramienta no existe.
* Retornar `available: false`.

---

## gpu_detection_service.py

Responsabilidades:

* Detectar `nvidia-smi`.
* Ejecutar consulta GPU.
* Parsear respuesta CSV.
* Soportar múltiples GPUs.
* Manejar errores sin romper el backend.

Funciones sugeridas:

```python
def get_gpu_status() -> GPUResponse:
    ...


def parse_nvidia_smi_output(output: str) -> list[GPUInfo]:
    ...
```

Reglas:

* Si `nvidia-smi` no existe, devolver `available: false`.
* Si el comando falla, devolver `available: false`.
* Si hay varias GPUs, devolver todas.
* No depender de PyTorch todavía.

---

# Logging

Registrar eventos importantes:

```text
System info requested
Tool detection completed
GPU detection completed
Storage info requested
Requirements status calculated
```

Registrar warnings cuando:

```text
FFmpeg not detected
FFprobe not detected
NVIDIA GPU not detected
Storage path is not writable
Free disk space is below recommended threshold
```

---

# Manejo de errores

Los endpoints de system no deben romperse si falta una herramienta.

Ejemplo:

* Si no existe `ffmpeg`, responder `available: false`.
* Si no existe `nvidia-smi`, responder `available: false`.
* Si falla el comando externo, responder `available: false` y registrar warning.

Solo debe responder error `500` si ocurre un problema inesperado dentro del backend.

---

# Tests

Crear:

```text
tests/test_system.py
```

Debe probar:

1. `GET /api/system/info` responde `200`.
2. La respuesta incluye `os`, `python` y `memory`.
3. `GET /api/system/tools` responde `200`.
4. La respuesta incluye `ffmpeg`, `ffprobe` y `nvidia_smi`.
5. `GET /api/system/gpu` responde `200`.
6. La respuesta incluye `available` y `gpus`.
7. `GET /api/system/storage` responde `200`.
8. La respuesta incluye `paths` y `disk`.
9. `GET /api/system/requirements` responde `200`.
10. La respuesta incluye `ready`, `minimum`, `recommended` y `warnings`.

No exigir en tests que FFmpeg o GPU existan físicamente en la máquina.

Los tests deben validar estructura, no disponibilidad real del hardware.

---

# Actualizar README

Actualizar `backend/README.md` agregando sección:

```text
System endpoints
```

Incluir:

```text
GET /api/system/info
GET /api/system/tools
GET /api/system/gpu
GET /api/system/storage
GET /api/system/requirements
```

Explicar brevemente que estos endpoints ayudan a validar si la máquina local está lista para procesamiento de video e IA.

---

# Actualizar requirements.txt

Agregar:

```text
psutil
```

---

# Actualizar pyproject.toml

Agregar `psutil` como dependencia principal.

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe `routes_system.py`.
* Existe `system_schema.py`.
* Existen servicios separados para system, tools y GPU.
* `/api/system/info` funciona.
* `/api/system/tools` funciona.
* `/api/system/gpu` funciona.
* `/api/system/storage` funciona.
* `/api/system/requirements` funciona.
* El backend no falla si FFmpeg no está instalado.
* El backend no falla si `nvidia-smi` no está disponible.
* La detección de herramientas usa `shutil.which`.
* Los comandos externos usan timeout.
* El almacenamiento reporta espacio libre.
* La respuesta de requisitos distingue entre mínimos y recomendados.
* Los tests pasan.
* El README documenta los nuevos endpoints.
* No se ha implementado todavía procesamiento real de video.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible ejecutar:

```bash
cd backend
uvicorn app.main:app --reload
```

Y consultar:

```text
http://127.0.0.1:8000/api/system/info
http://127.0.0.1:8000/api/system/tools
http://127.0.0.1:8000/api/system/gpu
http://127.0.0.1:8000/api/system/storage
http://127.0.0.1:8000/api/system/requirements
```

El backend debe responder correctamente aunque el equipo no tenga GPU NVIDIA o aunque FFmpeg todavía no esté instalado.

Este requerimiento deja preparado el backend para el siguiente paso: análisis real de videos usando FFprobe.
