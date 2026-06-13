# REQ-001 - Backend Foundation

## Proyecto

Oroya Video

## Área

Backend

## Objetivo

Crear la base inicial del backend local de Oroya Video usando Python, FastAPI y una estructura modular preparada para crecer hacia procesamiento de video, gestión de proyectos, modelos IA y cola de jobs.

Este primer requerimiento no debe implementar todavía procesamiento real de video, FFmpeg, Real-ESRGAN ni lógica de IA.
El objetivo es dejar lista una base profesional, mantenible y fácil de extender.

---

# Contexto

Oroya Video es una aplicación desktop local para mejora y restauración de video mediante inteligencia artificial.

El frontend estará construido con Angular 22, Tauri 2 y Neural Angular.

El backend será un servicio local ejecutado en la misma máquina del usuario. Su responsabilidad futura será:

* Analizar videos.
* Gestionar proyectos.
* Gestionar modelos IA.
* Ejecutar jobs.
* Procesar frames.
* Exportar videos.
* Reportar progreso a la UI.

En esta primera tarea solo se debe construir la base técnica del backend.

---

# Stack requerido

* Python 3.13+
* FastAPI
* Uvicorn
* Pydantic
* SQLite preparado para siguientes fases
* Pytest para pruebas
* Ruff para linting/formato
* python-dotenv o pydantic-settings para configuración

---

# Alcance de este requerimiento

Implementar:

1. Estructura inicial del backend.
2. Aplicación FastAPI funcional.
3. Endpoint de health check.
4. Endpoint de versión.
5. Sistema centralizado de configuración.
6. Sistema básico de paths locales.
7. Sistema básico de logging.
8. Manejo estándar de errores.
9. Archivo `pyproject.toml`.
10. README inicial del backend.
11. Pruebas mínimas para validar que la API arranca.

No implementar todavía:

* CRUD de proyectos.
* Base de datos real.
* FFmpeg.
* OpenCV.
* PyTorch.
* Real-ESRGAN.
* Cola de jobs.
* Procesamiento de video.
* WebSockets.
* Integración con Tauri.

---

# Estructura esperada

Crear la siguiente estructura:

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── routes_health.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── paths.py
│   │   ├── logging.py
│   │   └── errors.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── health_schema.py
│   │
│   └── services/
│       ├── __init__.py
│       └── system_service.py
│
├── storage/
│   ├── db/
│   ├── temp/
│   ├── exports/
│   ├── models/
│   └── logs/
│
├── tests/
│   ├── __init__.py
│   └── test_health.py
│
├── .env.example
├── pyproject.toml
├── README.md
└── requirements.txt
```

---

# Configuración

Crear un módulo de configuración en:

```text
app/core/config.py
```

Debe exponer una clase `Settings`.

Campos mínimos:

```python
app_name: str = "Oroya Video Backend"
app_version: str = "0.1.0"
environment: str = "development"
host: str = "127.0.0.1"
port: int = 8000
debug: bool = True
storage_path: str = "storage"
database_url: str = "sqlite:///storage/db/oroya-video.sqlite"
```

También debe existir una función:

```python
get_settings() -> Settings
```

La configuración debe poder leerse desde variables de entorno.

---

# Paths locales

Crear un módulo:

```text
app/core/paths.py
```

Debe definir funciones para resolver y crear carpetas necesarias:

```python
get_storage_path()
get_db_path()
get_temp_path()
get_exports_path()
get_models_path()
get_logs_path()
ensure_storage_directories()
```

Al iniciar la aplicación, deben crearse automáticamente estas carpetas si no existen:

```text
storage/db
storage/temp
storage/exports
storage/models
storage/logs
```

---

# Logging

Crear un módulo:

```text
app/core/logging.py
```

Debe configurar logging básico para:

* Consola.
* Archivo `storage/logs/backend.log`.

Formato sugerido:

```text
timestamp | level | module | message
```

El backend debe registrar al iniciar:

```text
Oroya Video Backend started
Environment: development
Storage path: ...
```

---

# Manejo de errores

Crear un módulo:

```text
app/core/errors.py
```

Debe incluir una excepción base:

```python
class OroyaVideoError(Exception):
    pass
```

Y preparar una estructura simple para errores futuros.

También configurar en `main.py` un handler general para errores inesperados, devolviendo JSON:

```json
{
  "error": "internal_server_error",
  "message": "Unexpected server error"
}
```

---

# FastAPI App

Crear la app en:

```text
app/main.py
```

Debe:

1. Crear instancia de FastAPI.
2. Usar título `Oroya Video Backend`.
3. Usar versión desde configuración.
4. Registrar router principal.
5. Crear carpetas de storage al iniciar.
6. Configurar logging.
7. Registrar handlers de error.
8. Permitir CORS local para desarrollo.

CORS inicial permitido:

```text
http://localhost:4200
http://127.0.0.1:4200
tauri://localhost
```

---

# Router principal

Crear:

```text
app/api/router.py
```

Debe incluir el router de health:

```text
/api/health
/api/version
```

---

# Endpoints requeridos

## GET /api/health

Debe devolver:

```json
{
  "status": "ok",
  "service": "Oroya Video Backend"
}
```

## GET /api/version

Debe devolver:

```json
{
  "name": "Oroya Video Backend",
  "version": "0.1.0",
  "environment": "development"
}
```

---

# Schemas

Crear:

```text
app/schemas/health_schema.py
```

Con modelos Pydantic:

```python
class HealthResponse(BaseModel):
    status: str
    service: str

class VersionResponse(BaseModel):
    name: str
    version: str
    environment: str
```

---

# Tests

Crear pruebas con pytest.

Archivo:

```text
tests/test_health.py
```

Debe probar:

1. `GET /api/health` responde `200`.
2. `GET /api/health` devuelve `status: ok`.
3. `GET /api/version` responde `200`.
4. `GET /api/version` devuelve la versión configurada.

---

# pyproject.toml

Crear un `pyproject.toml` con configuración mínima para:

* Proyecto Python.
* Dependencias principales.
* Dependencias de desarrollo.
* Ruff.
* Pytest.

Dependencias mínimas:

```text
fastapi
uvicorn[standard]
pydantic
pydantic-settings
python-dotenv
pytest
httpx
ruff
```

---

# requirements.txt

Además del `pyproject.toml`, generar un `requirements.txt` inicial con las dependencias necesarias para instalación simple.

---

# README inicial

Crear:

```text
backend/README.md
```

Debe incluir:

1. Descripción breve del backend.
2. Requisitos.
3. Instalación.
4. Cómo ejecutar en desarrollo.
5. Cómo correr tests.
6. Endpoints disponibles.

Comandos esperados:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

pytest
```

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* La carpeta `backend/` existe con la estructura indicada.
* La API inicia correctamente con Uvicorn.
* Swagger UI está disponible en `/docs`.
* `GET /api/health` responde correctamente.
* `GET /api/version` responde correctamente.
* Las carpetas de storage se crean automáticamente.
* El archivo de log se genera en `storage/logs/backend.log`.
* Los tests pasan correctamente.
* El código está organizado por módulos.
* No hay lógica de video ni IA todavía.
* El backend queda preparado para el siguiente requerimiento: system info y detección de FFmpeg/GPU.

---

# Resultado esperado

Al finalizar esta tarea, debe ser posible ejecutar:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Y luego abrir:

```text
http://127.0.0.1:8000/docs
```

También debe funcionar:

```text
GET http://127.0.0.1:8000/api/health
GET http://127.0.0.1:8000/api/version
```

Este será el punto de partida técnico para construir el motor local de Oroya Video.
