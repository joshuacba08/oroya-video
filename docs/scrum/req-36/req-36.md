# REQ-036 - Pipeline por streaming

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Dejar de extraer todos los fotogramas a PNG: un video largo ocupaba decenas de GB en
temporales (originales más mejorados a escala²). El nuevo pipeline decodifica, mejora y
codifica en memoria, por tramos, con disco acotado y reanudación.

## Implementación

- **Decodificador**: un único `ffmpeg` con el recorte (`-ss/-t`), `-vf fps=<fps>` (ritmo
  constante; el audio queda sincronizado también con fuentes VFR) y salida `rawvideo rgb24`
  por una tubería. Un hilo lee fotogramas completos a una cola corta: el bucle comprueba
  pausa y cancelación mientras espera y detecta un decodificador colgado.
- **Proceso en memoria** (`app/enhancers/stream.py`): motor mock sin dependencias;
  Real-ESRGAN (`enhance_image`, misma escalera de tiles ante OOM y mismo respaldo para los
  fotogramas que fallan) y GFPGAN (`restore_image`) sobre imágenes numpy. El modelo cargado
  se reutiliza entre jobs como antes.
- **Codificador por tramo**: `libx264 -crf 18 -preset medium` desde `stdin`, con los
  filtros de mejora y el escalado de salida en `-vf`. Cada tramo (240 fotogramas por
  defecto) se escribe como `.part.mp4` y se renombra al terminar,
  `seg_<n>_<primer fotograma>_<fotogramas>.mp4`. Al acabar, `concat -c copy` produce
  `video_silent.mp4`; el audio y la exportación siguen igual que antes.
- **Pausar, reanudar y cancelar**: se puede pausar en cualquier momento. Pausar, o apagar la
  app, cierra el tramo en curso (no se pierde trabajo) y reanudar busca el primer
  fotograma pendiente. Cancelar descarta el tramo a medias. Si el disco baja de 1,5 GB, el
  job se pausa entre tramos. El registro de procesos admite varios por job (decodificador,
  codificador, concat) y cancelar los termina todos.
- **Vista previa**: se guardan 24 pares original/mejorado repartidos por el video, con su
  índice real, más el último procesado para la vista en vivo (`preview_frame_index`). La
  muestra en vivo se limita a ~10 % del tiempo de proceso. El fotograma recomendado ya no
  supone índices contiguos.
- **Progreso**: una sola etapa `processing` (0-85 %), con ETA a partir del ms/fotograma
  medido. El job guarda `pipeline_mode`, `segments_completed` y `segments_total`.
- **Transición**: el pipeline clásico sigue como respaldo oculto (`processing.pipeline_mode`:
  `"legacy"` en `settings.json`, o `PIPELINE_MODE`). Cada job conserva el pipeline con el
  que empezó; los jobs de la 0.4 con fotogramas ya extraídos siguen con el clásico.
- **CI**: el job de backend instala ffmpeg para ejecutar los tests de streaming y de
  recorte.

## Verificación

- Tests con ffmpeg real: tramos y concat (audio sincronizado), pausa a mitad y reanudación
  desde el tramo siguiente, cancelación sin restos, recorte en streaming. También tests
  unitarios de tramos contiguos, muestras de vista previa, el comando del decodificador, el
  PNG y la terminación de varios procesos.
- E2E: todo el flujo (pausar y reanudar, lote, recorte) ya corre sobre el streaming.
- GPU real (RTX 5060 Ti): un clip de 720p de 8 s (192 fotogramas) con Real-ESRGAN x2 y
  GFPGAN. Streaming: 172 s y un pico de 79 MB de temporales. Clásico: 186 s y 635 MB. Las
  dos exportaciones salen a 2560×1440, duran 8,000 s y llevan audio.
