# REQ-003 - Video Probe & Metadata Extraction

## Proyecto

Oroya Video

## Área

Backend

## Dependencia previa

Este requerimiento asume que ya existen y funcionan:

```text
REQ-001 - Backend Foundation
REQ-002 - System Info & Environment Detection
```

El backend ya debe tener:

* FastAPI funcional.
* Configuración centralizada.
* Logging.
* Sistema de paths.
* Detección de herramientas del sistema.
* Detección básica de FFmpeg, FFprobe y GPU.
* Endpoints `/api/system/*`.

---

# Objetivo

Implementar la capacidad de analizar archivos de video locales usando `ffprobe`.

El backend debe recibir una ruta local de video, validar que el archivo exista, ejecutar `ffprobe`, parsear la metadata y devolver una respuesta estructurada para que el frontend pueda mostrar información técnica del archivo antes de importarlo o procesarlo.

Este requerimiento no debe copiar, mover ni importar el video todavía.

Solo debe analizar metadata.

---

# Contexto

Oroya Video necesita mostrar información clara del video antes de crear un proyecto o iniciar procesamiento.

La UI necesita saber:

* Nombre del archivo.
* Ruta local.
* Extensión.
* Tamaño.
* Duración.
* Resolución.
* FPS.
* Codec de video.
* Codec de audio.
* Bitrate.
* Streams disponibles.
* Si el archivo parece válido para el MVP.

Esto permitirá que la pantalla de importación y el workspace puedan mostrar una ficha técnica del video.

---

# Stack requerido

Usar herramientas ya contempladas:

```text
ffprobe
FastAPI
Pydantic
Python pathlib
subprocess
```

No agregar todavía:

* OpenCV.
* PyTorch.
* Real-ESRGAN.
* Jobs.
* Importación persistente.
* Base de datos.
* Extracción de frames.
* Generación de thumbnails.

---

# Alcance de este requerimiento

Implementar:

1. Endpoint para analizar metadata de video.
2. Validación básica de archivo local.
3. Validación de formato permitido.
4. Servicio para ejecutar `ffprobe`.
5. Parseo seguro de respuesta JSON de `ffprobe`.
6. Schemas Pydantic para request y response.
7. Manejo de errores específicos de video.
8. Tests con mocks para no depender de videos reales.
9. Actualización de README.

No implementar todavía:

* Copia del video a storage.
* Creación de proyectos.
* Persistencia en SQLite.
* Extracción de frames.
* Preview thumbnail.
* Jobs de procesamiento.
* Exportación.
* Uso de FFmpeg para encoding.

---

# Formatos soportados MVP

Inicialmente aceptar solo:

```text
.mp4
.mov
.mkv
```

Si el archivo tiene otra extensión, responder error controlado.

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
│   ├── schemas/
│   │   └── video_schema.py
│   │
│   ├── services/
│   │   └── video_probe_service.py
│   │
│   └── core/
│       └── errors.py
│
├── tests/
│   └── test_video_probe.py
│
└── README.md
```

---

# Endpoint requerido

## POST /api/videos/probe

Analiza un archivo de video local usando `ffprobe`.

### Request

```json
{
  "file_path": "C:\\Users\\user\\Videos\\sample.mp4"
}
```

También debe funcionar con rutas Unix/macOS:

```json
{
  "file_path": "/Users/user/Videos/sample.mp4"
}
```

---

# Respuesta exitosa

```json
{
  "valid": true,
  "file": {
    "path": "C:\\Users\\user\\Videos\\sample.mp4",
    "name": "sample.mp4",
    "extension": ".mp4",
    "size_bytes": 524288000,
    "size_mb": 500.0
  },
  "format": {
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "duration_seconds": 128.45,
    "duration_label": "00:02:08",
    "bit_rate": 8000000
  },
  "video": {
    "codec": "h264",
    "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
    "width": 1920,
    "height": 1080,
    "resolution_label": "1920x1080",
    "fps": 23.976,
    "pix_fmt": "yuv420p",
    "profile": "High",
    "bit_rate": 7500000
  },
  "audio": {
    "available": true,
    "codec": "aac",
    "codec_long_name": "AAC (Advanced Audio Coding)",
    "sample_rate": 48000,
    "channels": 2,
    "channel_layout": "stereo",
    "bit_rate": 320000
  },
  "streams": [
    {
      "index": 0,
      "type": "video",
      "codec": "h264",
      "width": 1920,
      "height": 1080
    },
    {
      "index": 1,
      "type": "audio",
      "codec": "aac"
    }
  ],
  "warnings": []
}
```

---

# Respuesta para video sin audio

Si el video no contiene audio:

```json
{
  "valid": true,
  "audio": {
    "available": false,
    "codec": null,
    "codec_long_name": null,
    "sample_rate": null,
    "channels": null,
    "channel_layout": null,
    "bit_rate": null
  },
  "warnings": [
    "No audio stream detected."
  ]
}
```

---

# Errores esperados

## Archivo no encontrado

Status HTTP:

```text
404
```

Respuesta:

```json
{
  "error": "video_file_not_found",
  "message": "Video file was not found."
}
```

---

## Formato no soportado

Status HTTP:

```text
400
```

Respuesta:

```json
{
  "error": "unsupported_video_format",
  "message": "Only MP4, MOV and MKV files are supported in the MVP."
}
```

---

## FFprobe no disponible

Status HTTP:

```text
503
```

Respuesta:

```json
{
  "error": "ffprobe_not_available",
  "message": "FFprobe is required to analyze video files."
}
```

---

## FFprobe falla al analizar el video

Status HTTP:

```text
422
```

Respuesta:

```json
{
  "error": "video_probe_failed",
  "message": "The video metadata could not be analyzed."
}
```

---

## No se detecta stream de video

Status HTTP:

```text
422
```

Respuesta:

```json
{
  "error": "video_stream_not_found",
  "message": "No video stream was detected in the selected file."
}
```

---

# Router

Actualizar:

```text
app/api/router.py
```

Debe incluir el router de videos bajo:

```text
/api/videos
```

Endpoint final:

```text
POST /api/videos/probe
```

---

# Schemas

Crear:

```text
app/schemas/video_schema.py
```

Modelos sugeridos:

```python
from pydantic import BaseModel, Field


class VideoProbeRequest(BaseModel):
    file_path: str = Field(..., min_length=1)


class VideoFileInfo(BaseModel):
    path: str
    name: str
    extension: str
    size_bytes: int
    size_mb: float


class VideoFormatInfo(BaseModel):
    format_name: str | None = None
    duration_seconds: float | None = None
    duration_label: str | None = None
    bit_rate: int | None = None


class VideoStreamInfo(BaseModel):
    codec: str | None = None
    codec_long_name: str | None = None
    width: int | None = None
    height: int | None = None
    resolution_label: str | None = None
    fps: float | None = None
    pix_fmt: str | None = None
    profile: str | None = None
    bit_rate: int | None = None


class AudioStreamInfo(BaseModel):
    available: bool
    codec: str | None = None
    codec_long_name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    bit_rate: int | None = None


class StreamSummary(BaseModel):
    index: int
    type: str
    codec: str | None = None
    width: int | None = None
    height: int | None = None


class VideoProbeResponse(BaseModel):
    valid: bool
    file: VideoFileInfo
    format: VideoFormatInfo
    video: VideoStreamInfo
    audio: AudioStreamInfo
    streams: list[StreamSummary]
    warnings: list[str]
```

---

# Servicio principal

Crear:

```text
app/services/video_probe_service.py
```

Responsabilidades:

* Validar que la ruta exista.
* Validar que sea un archivo.
* Validar extensión permitida.
* Verificar que `ffprobe` esté disponible.
* Ejecutar `ffprobe`.
* Parsear la respuesta JSON.
* Extraer stream de video principal.
* Extraer stream de audio principal si existe.
* Calcular duración legible.
* Calcular FPS.
* Generar warnings si falta audio o metadata secundaria.

---

# Comando FFprobe

Usar este comando base:

```bash
ffprobe -v error -print_format json -show_format -show_streams "video.mp4"
```

En Python:

```python
subprocess.run(
    [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ],
    capture_output=True,
    text=True,
    timeout=15,
)
```

Reglas:

* Usar timeout máximo de 15 segundos.
* Capturar `stdout`.
* Capturar `stderr`.
* No usar `shell=True`.
* Si el comando retorna código diferente de 0, lanzar error controlado.
* Si `stdout` no es JSON válido, lanzar error controlado.

---

# Parseo de FPS

`ffprobe` puede devolver FPS como fracción:

```text
24000/1001
```

Crear función utilitaria interna:

```python
def parse_fps(value: str | None) -> float | None:
    ...
```

Debe soportar:

```text
24000/1001 -> 23.976
30000/1001 -> 29.97
25/1       -> 25.0
30         -> 30.0
0/0        -> None
None       -> None
```

Redondear a 3 decimales.

---

# Parseo de duración

Crear función:

```python
def format_duration(seconds: float | None) -> str | None:
    ...
```

Ejemplos:

```text
65.3    -> 00:01:05
128.45  -> 00:02:08
3661.0  -> 01:01:01
None    -> None
```

---

# Parseo de bitrate

`ffprobe` puede devolver números como strings.

Crear función segura:

```python
def parse_int(value: str | int | None) -> int | None:
    ...
```

Debe devolver `None` si el valor no es válido.

---

# Errores personalizados

Actualizar:

```text
app/core/errors.py
```

Agregar excepciones:

```python
class VideoFileNotFoundError(OroyaVideoError):
    pass


class UnsupportedVideoFormatError(OroyaVideoError):
    pass


class FFprobeNotAvailableError(OroyaVideoError):
    pass


class VideoProbeFailedError(OroyaVideoError):
    pass


class VideoStreamNotFoundError(OroyaVideoError):
    pass
```

Registrar handlers en `main.py` o en módulo de errores.

Cada excepción debe devolver el status HTTP y JSON esperado.

---

# Seguridad de rutas

Validaciones mínimas:

* No aceptar `file_path` vacío.
* Resolver la ruta usando `Path(file_path).expanduser().resolve()`.
* Verificar `path.exists()`.
* Verificar `path.is_file()`.
* No modificar ni borrar el archivo.
* No copiar el archivo.
* No ejecutar comandos con `shell=True`.

Nota:

En esta fase se permite analizar cualquier ruta local válida porque la app es desktop local. En fases futuras se podrá restringir a rutas seleccionadas por Tauri.

---

# Logging

Registrar:

```text
Video probe requested: {file_path}
Video probe completed: {file_name}
Video probe failed: {reason}
Unsupported video format: {extension}
FFprobe not available
No audio stream detected
No video stream detected
```

No registrar rutas sensibles completas en errores enviados al frontend.

En logs internos sí se puede registrar la ruta completa para diagnóstico local.

---

# Tests

Crear:

```text
tests/test_video_probe.py
```

Los tests no deben depender de un video real ni de FFprobe instalado.

Usar mocks para:

* `Path.exists`
* `Path.is_file`
* `shutil.which`
* `subprocess.run`

Pruebas mínimas:

1. `POST /api/videos/probe` responde `404` si el archivo no existe.
2. Responde `400` si la extensión no está soportada.
3. Responde `503` si `ffprobe` no está disponible.
4. Responde `422` si `ffprobe` devuelve error.
5. Responde `422` si no hay stream de video.
6. Responde `200` con metadata válida cuando `ffprobe` devuelve JSON correcto.
7. Responde `200` con warning si no hay audio.
8. `parse_fps("24000/1001")` devuelve `23.976`.
9. `parse_fps("0/0")` devuelve `None`.
10. `format_duration(3661)` devuelve `"01:01:01"`.

---

# Ejemplo de JSON mock de FFprobe

Usar este mock en tests:

```json
{
  "streams": [
    {
      "index": 0,
      "codec_type": "video",
      "codec_name": "h264",
      "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
      "width": 1920,
      "height": 1080,
      "r_frame_rate": "24000/1001",
      "pix_fmt": "yuv420p",
      "profile": "High",
      "bit_rate": "7500000"
    },
    {
      "index": 1,
      "codec_type": "audio",
      "codec_name": "aac",
      "codec_long_name": "AAC (Advanced Audio Coding)",
      "sample_rate": "48000",
      "channels": 2,
      "channel_layout": "stereo",
      "bit_rate": "320000"
    }
  ],
  "format": {
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "duration": "128.45",
    "bit_rate": "8000000"
  }
}
```

---

# Actualizar README

Agregar sección:

```text
Video endpoints
```

Documentar:

```text
POST /api/videos/probe
```

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/videos/probe" \
  -H "Content-Type: application/json" \
  -d "{\"file_path\": \"C:\\Users\\user\\Videos\\sample.mp4\"}"
```

Explicar que este endpoint:

* No importa el video.
* No copia el archivo.
* No procesa frames.
* Solo analiza metadata usando `ffprobe`.

---

# Criterios de aceptación

El requerimiento se considera completo cuando:

* Existe `routes_videos.py`.
* Existe `video_schema.py`.
* Existe `video_probe_service.py`.
* El router principal incluye `/api/videos`.
* `POST /api/videos/probe` funciona.
* El endpoint valida existencia del archivo.
* El endpoint valida extensiones `.mp4`, `.mov`, `.mkv`.
* El endpoint detecta si `ffprobe` no está disponible.
* El endpoint ejecuta `ffprobe` con timeout.
* El endpoint no usa `shell=True`.
* El endpoint devuelve metadata estructurada.
* El endpoint detecta video stream principal.
* El endpoint detecta audio stream principal si existe.
* El endpoint responde con warning si no hay audio.
* El endpoint devuelve errores controlados.
* Los tests usan mocks y no dependen de videos reales.
* Los tests pasan.
* README documenta el nuevo endpoint.
* No se implementa todavía importación ni persistencia.

---

# Resultado esperado

Al finalizar este requerimiento debe ser posible ejecutar:

```bash
cd backend
uvicorn app.main:app --reload
```

Y luego probar:

```text
POST http://127.0.0.1:8000/api/videos/probe
```

Con body:

```json
{
  "file_path": "C:\\Users\\user\\Videos\\sample.mp4"
}
```

El backend debe responder con metadata real del video si:

* El archivo existe.
* La extensión es soportada.
* `ffprobe` está disponible.
* El archivo contiene al menos un stream de video.

Este requerimiento deja preparado el backend para el siguiente paso: importación local del video y creación de entidades persistentes.
