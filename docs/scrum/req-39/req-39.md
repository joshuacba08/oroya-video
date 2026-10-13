# REQ-039 - Biblioteca de modelos modernos (spandrel)

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Ir más allá de Real-ESRGAN, que en video real de baja resolución deja un aspecto "pintado". Se
cargan arquitecturas modernas a través de spandrel y se ofrecen modelos curados para video real
antiguo, animación y máximo detalle, más una limpieza de compresión con IA.

## Implementación

- **Runtime:** `spandrel==0.4.2` (MIT; solo arquitecturas con licencia permisiva), con
  `einops` y `safetensors`, en la instalación de IA.
  - Para las instalaciones anteriores, el estado del runtime informa de `missing_components`
    y Setup ofrece "Actualizar componentes de IA". pip solo instala lo que falta.
- **`SpandrelFrameEnhancer`:** misma interfaz que Real-ESRGAN.
  - fp16 si el modelo lo admite; si no, fp32. Nunca bf16: con RealPLKSR "dysample" la salida
    sale pixelada, y además era más lento (medido).
  - Tiles con solape y escalera de tiles ante falta de VRAM; reemplazo con Lanczos si falla un
    fotograma.
  - Reescala a la escala pedida si difiere de la del modelo.
  - El modelo cargado se conserva entre jobs.
- **Modelos** (Phhofm, GitHub releases, SHA-256 fijado):

  | slug | Modelo | Licencia | 640×480 en una RTX 5060 Ti |
  |---|---|---|---|
  | `realplksr-real-2x` | 2xPublic_realplksr_dysample_layernorm_real | Apache-2.0 | 305 ms (fp16) |
  | `realplksr-4x` | 4xBHI_realplksr_dysample_real | CC-BY-4.0 | 653 ms (fp32) |
  | `span-anime-2x` | 2xHFA2k_LUDVAE_SPAN | CC-BY-4.0 | 31 ms |
  | `deh264-1x` | 1xDeH264_realplksr (limpieza de compresión) | CC-BY-4.0 | 533 ms (fp32) |

  DAT2 4x, previsto en el plan, se descartó: 3,7 s por fotograma.
- **Selección:** el enhancer depende del `model_type` del modelo. Hay una limpieza de
  compresión con IA opcional (`enhancement_config.ai_cleanup`) antes de escalar.
  - Solo en el pipeline por streaming; el preflight explica qué falta (pipeline, componentes
    o modelo).
- **Preajustes recalibrados** con recortes reales del piano y de una cara:
  - *Video real antiguo* → limpieza DeH264 + RealPLKSR 2x.
  - *Animación* → SPAN 2x.
  - *Detalle máximo* → RealPLKSR 4x.
  - Si el modelo nuevo no está descargado, se usa Real-ESRGAN.
- **UI:**
  - interruptor "Limpieza de compresión con IA";
  - la limpieza no aparece como modelo de escalado;
  - los modelos nuevos aparecen en Modelos con su autor y licencia.

## Verificación

- Tests:
  - registro y descargas fijadas;
  - la inferencia por tiles coincide con la de la imagen entera;
  - reescalado a la escala pedida;
  - selección por tipo de modelo;
  - validación de `ai_cleanup`;
  - preflight con el pipeline clásico;
  - inferencia real de SPAN y DeH264, con `OROYA_SPANDREL_MODELS` (si no, se saltan).
- GPU real: un trabajo de 10 s de `natsumi` con DeH264 + RealPLKSR 2x + GFPGAN y codificación
  NVENC se completa (1280×960, BT.709). Es lento (1,5 s/fotograma), lo que motiva REQ-042.
