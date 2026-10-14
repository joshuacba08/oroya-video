# REQ-040 - Calidad de codificación

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Decidir cómo se codifica la exportación: códec, calidad, GPU y 10 bits. Hasta ahora era fijo
(H.264, CRF 18 en streaming y 23 en el pipeline clásico, siempre en la CPU).

## Implementación

- **Configuración:** `export_config.encoding = {codec, quality, hardware, ten_bit}`.
  - `codec`: `h264` (se reproduce en todas partes) o `h265` (archivos más pequeños).
  - `quality`: `high`, `balanced` o `small`.
  - El `codec` de primer nivel admite también `h265`.
- **`app/services/encoding_options.py`:** `build_video_codec_args` construye los argumentos que
  comparten los tramos del streaming (idénticos en todos, así que `concat -c copy` sigue
  sirviendo) y el codificador clásico.
  - CPU: libx264/libx265 con CRF 16 / 20 / 24.
  - GPU: NVENC `-preset p5 -tune hq -rc vbr`, con CQ 18 / 22 / 26.
  - H.265 lleva la etiqueta `hvc1` (la que esperan Windows y Apple) y conserva las etiquetas
    de color de REQ-038. 10 bits solo en H.265 (Main 10).
- **NVENC disponible:** una codificación de prueba de 1 fotograma por códec, cacheada.
  - Estar en la lista de codificadores no basta (sin GPU NVIDIA, driver antiguo…).
  - Por debajo de 256×144 se usa la CPU: NVENC rechaza fotogramas pequeños.
  - Si no se puede usar la GPU, se codifica en la CPU y el job lo registra.
  - `GET /system/encoders` informa a la UI.
- **UI:** en la exportación del Workspace se eligen códec, calidad, "Codificar con la GPU"
  (deshabilitado con su motivo si no hay NVENC) y "10 bits" (solo H.265). El aviso de salida
  exigente usa el límite del nivel 5.1 de cada códec.
- El `encoding_codec` del job y el resumen del mux reflejan el códec real.

## Verificación

- Tests de argumentos por combinación, retorno a la CPU, 10 bits solo en H.265, validación y
  endpoint.
- Con ffmpeg real: una exportación H.265 de 10 bits sale `hevc / Main 10 / yuv420p10le / hvc1`.
  Con NVENC (este equipo) una exportación por GPU se completa sin volver a la CPU; en CI se
  salta.
- Un hallazgo de la propia prueba: NVENC falla con fotogramas pequeños. De ahí el mínimo
  de 256×144.
