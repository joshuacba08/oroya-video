# REQ-035 - Recortar el video

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Procesar solo un fragmento del video (por ejemplo, una escena) en lugar del archivo entero:
menos tiempo, menos disco y una exportación con solo lo que interesa.

## Implementación

- **Configuración**: `export_config.trim = {start_seconds, end_seconds}` (o `null` para el
  video entero). Se valida la forma (números ≥ 0, mínimo 0,5 s) y, con el video conocido
  (crear/editar proyecto, crear job), que el inicio caiga dentro; el fin se ajusta a la
  duración. Es propio de cada proyecto: no entra en los "últimos ajustes usados" del lote.
- **Helper común** `app/utils/trim.py`: `get_job_trim(job)` lee el recorte de la instantánea
  del job y `trim_input_args()` genera `-ss INICIO -t DURACIÓN` delante de `-i`. Lo usará
  también el decodificador del pipeline por streaming (REQ-036).
- **Extracción**: solo los fotogramas del fragmento; `estimate_total_frames` y la estimación
  de disco temporal usan la duración recortada.
- **Mux**: el audio del original se corta en los mismos puntos (`-ss/-t` en la segunda
  entrada, con copia o con el respaldo AAC), así video y audio siguen sincronizados.
- **Workspace**: interruptor "Recortar video" con inicio y fin (`m:ss.s`, también segundos),
  botones "Empezar/Terminar en este fotograma" con el fotograma elegido en la vista previa, y
  la duración resultante ("Se procesan 0:12.0 de 3:42.0", también en la estimación). Los
  timecodes de la vista previa se desplazan con el inicio del recorte del último job.

## Verificación

- Tests: rango ajustado al video, argumentos `-ss/-t` antes de `-i` en extracción y mux,
  frames estimados con la duración recortada, validación por API, y ffmpeg real extrayendo
  solo el segundo pedido; vitest de `parseTrimTime`/`formatTrimTime`/`clampTrim`.
- E2E: un clip de 2 s recortado a 0,5–1,5 s se exporta con ~1 s de duración (ffprobe).
