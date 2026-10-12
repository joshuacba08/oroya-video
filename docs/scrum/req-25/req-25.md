# REQ-025 - Robustez del pipeline

## Proyecto

Oroya Video

## Área

Backend pipeline / Frontend

## Objetivo

Que un ffmpeg colgado, un disco lleno o un frame defectuoso no dejen un job bloqueado para
siempre ni un video cortado sin aviso.

## Implementación

- **Watchdog de ffmpeg** (`watch_process_output`): la salida se lee en un hilo; cada segundo
  sin salida se comprueba la cancelación y, tras `ffmpeg_stall_timeout_seconds` (180 s) sin
  progreso, se detiene ffmpeg y el job falla con `ffmpeg_stalled`. Extracción, codificación
  y mux.
- **Espacio en disco**:
  - Extracción: estimación por resolución × frames (PNG ≈ 1,5 B/píxel) + 512 MB de margen;
    el mensaje dice cuántos GB hacen falta.
  - Real-ESRGAN: antes de empezar, frames pendientes × tamaño medio del original × escala²;
    si no cabe, falla al inicio en lugar de tras horas.
  - Durante la mejora, si quedan menos de 1,5 GB libres el job **se pausa** con
    `insufficient_disk_space`; al liberar espacio, reanudar continúa donde quedó.
  - "No space left on device" de ffmpeg se traduce a `insufficient_disk_space`.
- **Sin huecos**: un frame fallido tolerado (`realesrgan_max_failed_frames > 0`) se sustituye
  por el original reescalado; el encode ya no se corta en el hueco.
- **Procesos**: los estados de fallo limpian `process_id`/`process_kind`.
- **Frontend**: timeout de 120 s para analizar/importar, reintentar, limpiar, borrar y
  refrescar modelos; códigos de error nuevos traducidos.

## Verificación

- Tests: lector con ticks y detección de bloqueo, ffmpeg colgado de extremo a extremo (job
  `ffmpeg_stalled`, proceso matado), detección de disco lleno, estimación de extracción,
  pausa por disco lleno, fallo temprano por espacio insuficiente y frame de reemplazo.
