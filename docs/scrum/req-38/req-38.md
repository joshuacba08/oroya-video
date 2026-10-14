# REQ-038 - Color fiel y filtros en su sitio

## Proyecto

Oroya Video

## Área

Backend

## Objetivo

Que los colores de la exportación coincidan con los del original en cualquier reproductor, y
que la limpieza de compresión y la reducción de ruido no emborronen el detalle que crea la IA.

## Problema

- **Color:** el codificador convertía RGB→YUV con la matriz BT.601 y dejaba la salida sin
  etiquetar. Los reproductores de Windows y los navegadores interpretan una salida HD como
  BT.709, así que los tonos se desviaban: piel (200,140,110) → (205,142,107).
- **Orden de los filtros:** `deblock` y `hqdn3d` se aplicaban al codificar, después de la IA.

## Implementación

- **`app/utils/color.py`:**
  - El decodificador convierte YUV→RGB con la matriz y el rango de la fuente
    (`scale=in_color_matrix=…:in_range=…`). Sin etiqueta: BT.601 en SD y BT.709 en HD.
  - El codificador convierte RGB→YUV con BT.709 en rango limitado y etiqueta la salida:
    `setparams` en los fotogramas, porque el FFmpeg reciente toma de ellos los primarios y la
    transferencia, y además `-colorspace`/`-color_*`. Las etiquetas sobreviven al `concat` y
    al mux.
- **Datos de la fuente:** la matriz y el rango se guardan al importar (`VideoAsset.color_space`
  y `color_range`, del mismo ffprobe del import).
  - Para videos importados antes, el streaming los sondea al empezar.
  - El pipeline clásico usa los valores SD/HD.
- **Filtros:**
  - `build_pre_ai_filters` (limpieza de compresión y reducción de ruido) va en el
    decodificador, antes de la IA y a la resolución de origen.
  - `build_post_ai_filters` (nitidez) va en el codificador.
  - La vista previa con filtros aplica solo los posteriores.
  - El pipeline clásico aplica los previos al extraer los fotogramas.

## Verificación

- Un clip de barras de color (piel, rojo, verde) con etiquetas BT.709 pasa por el pipeline. La
  exportación sale etiquetada `tv/bt709/bt709/bt709` y, decodificada como un reproductor
  BT.709, queda a ≤3 niveles de la fuente (antes la piel se desviaba ~5).
- Tests del mapeo de etiquetas, de los comandos y del orden de los filtros, en los dos
  pipelines y en la vista previa.
