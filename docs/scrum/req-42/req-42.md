# REQ-042 - Procesamiento más rápido

## Proyecto

Oroya Video

## Área

Backend

## Objetivo

Procesar más rápido midiendo antes dónde se va el tiempo.

## Medición

- El bucle del streaming registra el tiempo por fotograma de cada parte (decodificar, IA,
  codificar y muestras de vista previa) en el log del job: `Time per frame (ms): …`.
- Línea base en una RTX 5060 Ti (`natsumi` 640×480 → 1280×960, x264):
  - RealPLKSR 2x: IA 433 ms; decodificar 1 ms; codificar 1 ms.
  - Configuración completa: IA 1397 ms.
- Decodificar y codificar ya van en paralelo (procesos ffmpeg aparte). Un hilo escritor no
  aportaría nada, así que no se hizo.
- La IA tardaba 433 ms dentro del pipeline frente a 305 ms aislada. La causa: x264 con todos
  los núcleos dejaba sin CPU al lanzador de los cientos de kernels pequeños de la red. Con NVENC
  bajaba a 302 ms, lo que confirmó la causa.

## Cambios

- **Hilos de x264/x265 limitados** a un cuarto de los núcleos (mínimo 2). El codificador sigue
  muy por delante de la IA, y la IA recupera su velocidad.
- **`channels_last` automático por modelo:** se mide con el primer fotograma real y se queda
  el formato más rápido. RealPLKSR fp16 −13 %, SPAN −23 % y DeH264 fp32 +11 % (en ese caso se
  descarta).
- **PNG de las muestras con OpenCV** cuando está el runtime de IA.
- **Descartado tras medir:**
  - inferencia por lotes (0-11 %: la GPU ya va llena a 640×480);
  - CUDA Graphs (sin ganancia en modelos grandes y no compatible con dysample);
  - TF32 (sin efecto).
- La codificación por GPU (REQ-040) libera la CPU por completo.

## Resultado (mismo clip, x264)

| Configuración | Antes | Después |
|---|---|---|
| RealPLKSR 2x | 465 ms/fotograma | 336 ms (1,38×) |
| DeH264 + RealPLKSR + GFPGAN + estabilidad | 1437 ms | 1098 ms (1,31×) |

Con NVENC, RealPLKSR 2x baja a 321 ms (1,45×). El objetivo de 1,5-2× se alcanza solo en
parte: el resto es tiempo de GPU de la propia red.
