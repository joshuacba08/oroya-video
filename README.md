# Oroya Video - Contexto Inicial del Proyecto

## 1. Descripción General

**Oroya Video** es una aplicación desktop local para mejora, restauración y escalado de video mediante inteligencia artificial.

La aplicación permitirá importar videos, analizarlos, aplicar modelos de IA open source, comparar el resultado antes/después y exportar un video final mejorado, manteniendo todo el procesamiento dentro de la máquina del usuario.

El objetivo inicial no es competir directamente con herramientas comerciales avanzadas, sino construir una base sólida, privada, extensible y técnicamente controlable para procesamiento de video asistido por IA.

---

## 2. Visión del Producto

Oroya Video debe sentirse como una herramienta profesional moderna para creadores, desarrolladores y usuarios avanzados.

La experiencia debe combinar:

* Interfaz limpia y oscura.
* Flujo de trabajo simple.
* Control técnico suficiente.
* Procesamiento local.
* Feedback visual en tiempo real.
* Integración clara entre video, IA, GPU y exportación.

El usuario ideal debe poder abrir la app, importar un video, seleccionar un modelo, previsualizar la mejora, lanzar el procesamiento y exportar el resultado sin tener que tocar la terminal.

---

## 3. Principios del Producto

### 3.1 Local First

Todo ocurre localmente.

Oroya Video no debe depender de servicios externos para:

* Procesar video.
* Ejecutar modelos IA.
* Exportar archivos.
* Guardar proyectos.
* Gestionar historial local.

La privacidad y el control del usuario son parte central del producto.

---

### 3.2 AI Native

Oroya Video no es un editor de video tradicional.

La aplicación está construida alrededor de pipelines de IA:

```text
Video original
    ↓
Análisis
    ↓
Extracción de frames
    ↓
Procesamiento IA
    ↓
Reconstrucción
    ↓
Exportación
```

La IA no es una función secundaria, sino el núcleo del flujo de trabajo.

---

### 3.3 Performance First

El procesamiento de video es pesado por naturaleza.

La aplicación debe diseñarse desde el inicio pensando en:

* GPU NVIDIA.
* CUDA.
* VRAM disponible.
* Procesamiento por lotes de frames.
* Control de trabajos en cola.
* Carpetas temporales optimizadas.
* Cancelación segura de procesos.
* Logs técnicos claros.

---

### 3.4 Offline by Default

La aplicación debe poder funcionar sin conexión a internet una vez instalados los modelos necesarios.

Internet puede ser necesario para futuras funciones como descarga de modelos, actualizaciones o marketplace, pero no para procesar videos.

---

### 3.5 Extensible desde el inicio

Aunque el MVP será pequeño, la arquitectura debe permitir añadir más adelante:

* Nuevos modelos IA.
* Interpolación de frames.
* Restauración facial.
* Batch processing.
* Plugins.
* Presets inteligentes.
* Comparación entre modelos.
* Exportación avanzada.

---

## 4. Nombre del Producto

### Aplicación

```text
Oroya Video
```

### Descripción corta

```text
AI video enhancement desktop app.
```

### Descripción técnica

```text
Aplicación desktop local para mejora de video mediante modelos open source de inteligencia artificial.
```

---

## 5. Framework UI

La interfaz de Oroya Video será construida usando un framework interno llamado:

```text
Neural Angular
```

Neural Angular es un framework visual propio construido sobre:

* Angular 22.
* Angular Material.
* Angular CDK.
* GSAP.
* Design tokens propios.
* Sistema de motion.
* Componentes profesionales para apps AI-native.

Angular Material y CDK funcionan como base técnica, pero no definen la identidad visual final.

La identidad visual pertenece a Neural Angular.

---

## 6. Stack General

### Frontend Desktop

```text
Angular 22
Tauri 2
TypeScript
Neural Angular
Angular Material
Angular CDK
GSAP
```

### Backend Local

```text
Python 3.13+
FastAPI
Uvicorn
Pydantic
SQLite
```

### Procesamiento Multimedia

```text
FFmpeg
OpenCV
```

### Inteligencia Artificial

```text
PyTorch
Real-ESRGAN
CUDA
```

### Modelos MVP

```text
Real-ESRGAN x2
Real-ESRGAN x4
Real-ESRGAN General
```

### Modelos futuros

```text
GFPGAN
CodeFormer
RIFE
BasicVSR++
```

---

## 7. Arquitectura General

Oroya Video tendrá una arquitectura dividida en tres capas principales:

```text
Desktop App
Angular + Tauri + Neural Angular
        ↓
Local API
FastAPI
        ↓
Processing Engine
FFmpeg + OpenCV + PyTorch + AI Models
```

El frontend no procesa video directamente.

El frontend se comunica con el backend local mediante una API interna.

El backend es el responsable de:

* Analizar videos.
* Gestionar proyectos.
* Gestionar modelos.
* Crear jobs.
* Ejecutar pipelines.
* Reportar progreso.
* Exportar resultados.
* Mantener logs.
* Persistir información local.

---

## 8. Rol del Backend

El backend de Oroya Video debe entenderse como un motor local de procesamiento.

No es una API pública tradicional.

Es un servicio local que vive junto a la aplicación desktop y se encarga de las operaciones pesadas.

Sus responsabilidades principales son:

* Recibir instrucciones del frontend.
* Validar archivos de video.
* Extraer metadata.
* Crear proyectos.
* Gestionar configuraciones.
* Ejecutar pipelines de video.
* Controlar la cola de procesamiento.
* Monitorear estado del sistema.
* Detectar GPU y recursos.
* Gestionar modelos IA.
* Generar previews.
* Exportar archivos finales.

---

## 9. Backend First

La primera etapa del desarrollo se enfocará en construir el backend.

Antes de completar la interfaz final, el backend debe poder funcionar de manera independiente.

Esto significa que debe poder probarse mediante:

* Swagger UI de FastAPI.
* Requests HTTP locales.
* Scripts de prueba.
* Archivos de video de ejemplo.
* Logs de ejecución.

El objetivo es validar primero el motor de procesamiento antes de conectarlo completamente con la UI.

---

## 10. Conceptos Principales del Dominio

### 10.1 Project

Un proyecto representa una unidad de trabajo dentro de Oroya Video.

Contiene:

* Nombre del proyecto.
* Video original.
* Metadata del video.
* Configuración de procesamiento.
* Modelo seleccionado.
* Estado actual.
* Jobs asociados.
* Exports generados.
* Fecha de creación.
* Fecha de actualización.

---

### 10.2 Video Asset

Representa un archivo de video importado.

Contiene:

* Ruta local.
* Nombre de archivo.
* Formato.
* Duración.
* Resolución.
* FPS.
* Codec de video.
* Codec de audio.
* Tamaño.
* Información de streams.
* Thumbnail o preview frame.

Formatos MVP soportados:

```text
MP4
MOV
MKV
```

---

### 10.3 AI Model

Representa un modelo de IA disponible para procesamiento.

Contiene:

* ID del modelo.
* Nombre.
* Versión.
* Tipo.
* Descripción.
* Estado de instalación.
* Ruta local.
* Tamaño.
* Requisito estimado de VRAM.
* Factor de escala.
* Capacidades.

Tipos iniciales:

```text
upscaling
restoration
```

---

### 10.4 Job

Un job representa una tarea de procesamiento.

Cada job pertenece a un proyecto.

Un job contiene:

* ID.
* Project ID.
* Video Asset ID.
* Modelo seleccionado.
* Configuración de procesamiento.
* Estado actual.
* Progreso.
* Etapa actual del pipeline.
* Frames totales.
* Frames procesados.
* Tiempo estimado.
* Ruta de salida.
* Logs.
* Error, si existe.

---

### 10.5 Export

Representa un resultado final generado.

Contiene:

* ID.
* Project ID.
* Job ID.
* Ruta del archivo exportado.
* Formato.
* Codec.
* Resolución.
* Tamaño.
* Duración.
* Fecha de creación.

---

## 11. Estados de Job

Los estados principales de un job serán:

```text
pending
probing
extracting_frames
enhancing_frames
encoding_video
muxing_audio
completed
failed
cancelled
paused
```

Descripción:

```text
pending            El job fue creado pero aún no inicia.
probing            El backend está analizando el video.
extracting_frames  FFmpeg está extrayendo frames.
enhancing_frames   El modelo IA está procesando frames.
encoding_video     FFmpeg está reconstruyendo el video.
muxing_audio       Se está copiando o sincronizando el audio original.
completed          El resultado fue generado correctamente.
failed             El proceso falló.
cancelled          El usuario canceló el job.
paused             El job fue pausado.
```

---

## 12. Pipeline Principal de Procesamiento

El pipeline MVP será:

```text
1. Importar video
2. Analizar metadata con FFmpeg
3. Crear estructura temporal del proyecto
4. Extraer frames
5. Procesar frames con modelo IA
6. Reconstruir video
7. Mantener audio original
8. Generar archivo exportado
9. Limpiar temporales opcionalmente
10. Registrar resultado
```

Pipeline visual:

```text
Video
  ↓
Probe Metadata
  ↓
Extract Frames
  ↓
AI Enhance
  ↓
Encode Video
  ↓
Mux Audio
  ↓
Export
```

---

## 13. Funcionalidades MVP del Backend

### 13.1 Health Check

Permitir saber si el backend está vivo.

Endpoints esperados:

```text
GET /health
GET /version
```

---

### 13.2 System Info

Permitir consultar información del sistema.

Debe devolver:

* Sistema operativo.
* Versión de Python.
* Versión de FFmpeg.
* GPU disponible.
* CUDA disponible.
* VRAM disponible.
* Carpeta temporal.
* Carpeta de modelos.
* Carpeta de exports.

Endpoints esperados:

```text
GET /system/info
GET /system/gpu
```

---

### 13.3 Projects

Permitir crear, listar, leer y eliminar proyectos.

Endpoints esperados:

```text
POST   /projects
GET    /projects
GET    /projects/{project_id}
PATCH  /projects/{project_id}
DELETE /projects/{project_id}
```

---

### 13.4 Videos

Permitir importar y analizar videos.

Endpoints esperados:

```text
POST /videos/probe
POST /videos/import
GET  /videos/{video_id}
```

---

### 13.5 Models

Permitir listar y gestionar modelos IA.

Endpoints esperados:

```text
GET    /models
GET    /models/{model_id}
POST   /models/install
DELETE /models/{model_id}
```

En el MVP, la instalación puede ser simulada o manual si todavía no existe descarga automática de modelos.

---

### 13.6 Jobs

Permitir crear y controlar trabajos de procesamiento.

Endpoints esperados:

```text
POST /jobs
GET  /jobs
GET  /jobs/{job_id}
POST /jobs/{job_id}/start
POST /jobs/{job_id}/pause
POST /jobs/{job_id}/resume
POST /jobs/{job_id}/cancel
```

---

### 13.7 Progress Updates

El frontend necesita recibir progreso en tiempo real.

Opciones posibles:

```text
WebSocket
Server-Sent Events
Polling
```

Para el MVP se puede comenzar con polling simple.

Luego se puede migrar a WebSocket o SSE.

Endpoint inicial:

```text
GET /jobs/{job_id}/progress
```

---

### 13.8 Exports

Permitir listar y consultar exportaciones.

Endpoints esperados:

```text
GET /exports
GET /exports/{export_id}
POST /exports/{export_id}/open
POST /exports/{export_id}/open-folder
```

---

## 14. Persistencia Local

La base de datos inicial será SQLite.

SQLite almacenará:

* Proyectos.
* Videos importados.
* Modelos registrados.
* Jobs.
* Exports.
* Configuración local.
* Historial.
* Logs resumidos.

Los archivos pesados no se guardan dentro de la base de datos.

La base de datos solamente guarda metadata y rutas locales.

---

## 15. Almacenamiento Local

Estructura inicial recomendada:

```text
storage/
├── db/
│   └── oroya-video.sqlite
│
├── temp/
│   └── jobs/
│
├── frames/
│   └── {job_id}/
│
├── exports/
│   └── {project_id}/
│
├── models/
│   └── realesrgan/
│
└── logs/
    └── backend.log
```

---

## 16. Estructura Inicial del Backend

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── routes_health.py
│   │   ├── routes_system.py
│   │   ├── routes_projects.py
│   │   ├── routes_videos.py
│   │   ├── routes_models.py
│   │   ├── routes_jobs.py
│   │   └── routes_exports.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── paths.py
│   │   ├── logging.py
│   │   └── errors.py
│   │
│   ├── db/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── repositories/
│   │
│   ├── schemas/
│   │   ├── project_schema.py
│   │   ├── video_schema.py
│   │   ├── model_schema.py
│   │   ├── job_schema.py
│   │   ├── export_schema.py
│   │   └── system_schema.py
│   │
│   ├── services/
│   │   ├── project_service.py
│   │   ├── video_probe_service.py
│   │   ├── video_import_service.py
│   │   ├── model_service.py
│   │   ├── job_service.py
│   │   ├── export_service.py
│   │   └── system_service.py
│   │
│   ├── workers/
│   │   ├── queue.py
│   │   ├── job_runner.py
│   │   └── job_events.py
│   │
│   └── pipelines/
│       ├── video_pipeline.py
│       ├── extract_frames.py
│       ├── enhance_frames.py
│       ├── encode_video.py
│       └── mux_audio.py
│
├── storage/
├── tests/
├── pyproject.toml
└── README.md
```

---

## 17. Decisiones Técnicas Iniciales

### 17.1 Cola de trabajos

Para el MVP se evitará Celery.

La cola inicial puede ser implementada con:

```text
asyncio.Queue
worker interno
estado persistido en SQLite
```

Más adelante se puede migrar a:

```text
RQ
Celery
Redis
```

---

### 17.2 Comunicación frontend-backend

La app desktop usará Tauri para lanzar o conectarse con el backend local.

El backend correrá localmente, probablemente en:

```text
127.0.0.1
```

El puerto puede ser configurable o asignado automáticamente.

---

### 17.3 Procesamiento pesado

El procesamiento pesado no debe bloquear la API.

FastAPI debe recibir la solicitud, crear el job y delegar el procesamiento a un worker.

El frontend consultará progreso mientras el job avanza.

---

### 17.4 Logs

Cada job debe tener logs consultables.

Tipos de logs:

```text
info
warning
error
debug
```

Los logs deben ayudar a diagnosticar:

* Errores de FFmpeg.
* Errores de CUDA.
* Falta de modelos.
* Falta de espacio en disco.
* Videos corruptos.
* Fallos de codificación.

---

## 18. Configuración de Procesamiento MVP

Configuraciones iniciales:

```text
resolution: original | 2x | 4x
model: realesrgan-x2 | realesrgan-x4 | realesrgan-general
denoise: 0 - 100
sharpen: 0 - 100
compression_cleanup: true | false
output_format: mp4
output_codec: h264
keep_audio: true
```

---

## 19. No Objetivos del MVP

No se incluirá inicialmente:

* Editor de video completo.
* Timeline avanzado.
* Corrección de color.
* Estabilización.
* Detección automática de escenas.
* Interpolación de frames con RIFE.
* Restauración facial avanzada.
* Batch processing.
* Procesamiento distribuido.
* Marketplace real de modelos.
* Plugins.
* Login.
* Cloud sync.
* Colaboración multiusuario.

---

## 20. Métricas de Éxito del MVP

### Técnicas

* El backend inicia correctamente desde la app desktop.
* El backend detecta FFmpeg.
* El backend detecta GPU NVIDIA cuando esté disponible.
* El backend puede analizar metadata de videos.
* El backend puede extraer frames.
* El backend puede procesar frames con Real-ESRGAN.
* El backend puede reconstruir video.
* El backend mantiene el audio original sincronizado.
* El backend puede exportar MP4 H264.
* El backend no bloquea la UI durante procesamiento.

---

### Usuario

* El usuario puede importar un video sin usar terminal.
* El usuario puede configurar una mejora en menos de un minuto.
* El usuario puede ver el progreso del procesamiento.
* El usuario puede cancelar un job.
* El usuario puede exportar un resultado usable.
* El usuario puede encontrar el archivo exportado fácilmente.

---

## 21. Riesgos Técnicos

Riesgos principales:

* Videos muy grandes pueden generar demasiados frames temporales.
* La VRAM puede no ser suficiente para algunos modelos.
* FFmpeg puede fallar con codecs raros.
* Mantener audio sincronizado puede requerir cuidado.
* Real-ESRGAN puede ser lento sin GPU.
* El empaquetado de Python dentro de Tauri puede requerir ajustes.
* Los modelos IA pueden ocupar mucho espacio.
* Diferentes sistemas operativos pueden necesitar binarios distintos.

---

## 22. Prioridad Inicial de Desarrollo

Orden recomendado:

```text
1. Crear backend FastAPI base.
2. Crear health check.
3. Crear sistema de configuración y paths.
4. Detectar FFmpeg.
5. Detectar GPU/CUDA.
6. Implementar video probe.
7. Crear modelos de base de datos.
8. Crear CRUD de proyectos.
9. Crear importación de videos.
10. Crear cola de jobs.
11. Implementar extracción de frames.
12. Implementar procesamiento con Real-ESRGAN.
13. Implementar reconstrucción de video.
14. Implementar exportación.
15. Exponer progreso a la UI.
```

---

## 23. Resultado Esperado de la Primera Fase

Al terminar la primera fase backend, debería ser posible:

1. Levantar FastAPI localmente.
2. Abrir Swagger UI.
3. Crear un proyecto.
4. Importar un video.
5. Obtener metadata real del video.
6. Crear un job.
7. Ejecutar el pipeline.
8. Ver progreso.
9. Exportar un MP4 mejorado.
10. Consultar logs del proceso.

La UI de Angular/Tauri podrá conectarse encima de esta base sin que el backend dependa de decisiones visuales.

---

## 24. Instalador de Windows

El proyecto genera un instalador NSIS autocontenido:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1
```

El script empaqueta un runtime CPython portable (python-build-standalone 3.12) con el
backend y sus dependencias core dentro de la app Tauri. Al instalar:

- La app arranca el backend automáticamente (sidecar) y lo detiene al cerrar.
- Todos los datos de usuario viven en `%LOCALAPPDATA%\dev.oroya.video\`:
  - `storage/` — base de datos, imports, exports, temporales y modelos.
  - `bin/` — FFmpeg/FFprobe descargados por el asistente.
  - `ai-env/` — stack de IA (PyTorch) instalado bajo demanda.
- En la primera ejecución, el asistente (`/setup`) descarga FFmpeg y los modelos
  Real-ESRGAN (con verificación SHA256 desde los releases oficiales), y guía la
  instalación opcional de PyTorch CUDA para la mejora con IA.
- Sin IA instalada, la app funciona en modo básico (motor mock).

En desarrollo nada cambia: el backend se corre manualmente con uvicorn y la app
con `pnpm tauri dev` (el sidecar solo se activa en builds de release con el
backend empaquetado presente).

## 25. Licencia

Oroya Video se publica bajo licencia MIT. Consulta [LICENSE](LICENSE) para el texto completo.
