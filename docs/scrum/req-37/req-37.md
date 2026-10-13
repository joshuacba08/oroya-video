# REQ-037 - Interpolación de fotogramas con RIFE

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Subir los fps del video (2× o 48/50/60) con fotogramas intermedios generados por RIFE 4.25,
para un movimiento más fluido, dentro del pipeline por streaming.

## Implementación

- **Modelo**: `rife-4.25` (categoría `frame_interpolation`, MIT) en el registro y descargable
  desde Modelos: `flownet_v4.25.pkl` de HolyWu/vs-rife, 24,6 MB, con SHA-256 fijado
  (`6615790e…eb6de2`, calculado al descargarlo porque el release no publica digest).
- **Arquitectura incluida en el repo** (`app/enhancers/rife/`): `IFNet_HDv3_v4_25.py` y
  `warplayer.py` sin modificar, con el aviso MIT. Licencias en `THIRD_PARTY_NOTICES.md`.
- **`RIFEInterpolator`**:
  - carga con `torch.load(weights_only=True)`, de modo que el `.pkl` no puede ejecutar código;
  - fp16 en CUDA y CPU como respaldo;
  - relleno a múltiplo de 64 y `scale=0.5` desde 4K;
  - reutiliza el último fotograma codificado para el par siguiente.
- **Calendario** (`InterpolationSchedule`): el fotograma de salida n cae en la posición
  n·fps_in/fps_out de la fuente. Se interpola entre `floor` y `floor+1`, o se copia la fuente
  cuando t = 0. Las tasas NTSC se tratan como fracciones exactas (24000/1001…), así que
  24→60 produce exactamente 2,5 fotogramas por cada uno.
- **Cambios de escena**: si la diferencia media en gris y a tamaño pequeño supera 0,15, se
  repite el fotograma anterior en vez de mezclar dos planos.
- **En el streaming** (`InterpolationStage`): va tras la mejora y las caras. Los
  intermedios de i→i+1 se generan al llegar i+1. Cada tramo cuenta fotogramas de origen
  *completos*, así que pausar y reanudar no pierde ni repite fotogramas, y un fotograma que
  esperaba a su siguiente se vuelve a decodificar. El codificador usa los fps de salida y
  la exportación se llama, p. ej., `clip (Oroya 2x 60fps).mp4`.
- **Configuración**: `enhancement_config.interpolation = {enabled, target_fps}`, con
  `target_fps` en `"2x"`, 48, 50 o 60. Un objetivo fijo debe superar los fps del video.
- **Preflight**: exige el pipeline por streaming, el modelo RIFE instalado y el runtime de IA.
- **UI**: interruptor "Interpolar fotogramas" y selector de fps en el Workspace (2× muestra
  los fps resultantes; solo se ofrecen objetivos por encima de los del video) y en el
  diálogo de lote. RIFE no aparece entre los modelos de escalado.
- **Últimos ajustes usados**: iniciar un video suelto también los guarda (antes solo el
  lote). La carpeta de salida, como el nombre y el recorte, es propia de cada proyecto.

## Verificación

- Tests: calendario 24→60 y 2×, fracciones NTSC, etapa con interpolador simulado (orden,
  último fotograma, cambios de escena), detección de escena, validación por API, etiqueta
  de exportación, fallo claro sin modelo. Con ffmpeg real: 10→20 fps produce exactamente
  60 fotogramas en 3 s, también tras pausar y reanudar. Con torch y los pesos (variable
  `OROYA_RIFE_WEIGHTS`): un cuadro que se desplaza 16 px queda a mitad de camino en t = 0,5.
- GPU real (RTX 5060 Ti): ver abajo.
