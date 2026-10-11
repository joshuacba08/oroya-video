# REQ-021 - Performance & Live Progress

## Proyecto

Oroya Video

## Área

Backend pipeline / Frontend

## Objetivo

Tiempo restante real, progreso en vivo sin polling, menos trabajo por frame y menos disco.

## Implementación

- **Tiempo restante** (`job_contract_service.estimate_remaining_seconds`): durante la mejora,
  frames restantes × tiempo medio por frame + estimación de encode/mux; en encode/mux, se
  extrapola el progreso de la etapa; durante la extracción no se estima (falta el dato clave).
  Se expone en `estimated_time_seconds` (progreso y jobs).
- **SSE** `GET /api/v1/jobs/{id}/events`: emite el `JobProgressResponse` cuando cambia
  (consulta cada 0,5 s), keepalive cada 15 s y cierra en estado terminal o pausado. El
  frontend usa `EventSource` y vuelve al polling con backoff si falla.
- **Menos carga por frame**: el progreso se confirma en la DB y se comprueban cancelar/pausar
  como mucho cada 0,5 s (antes un commit y un SELECT por frame); la caché de CUDA se vacía
  cada 25 frames en vez de en cada uno.
- **Modelo en caché entre jobs**: el `RealESRGANFrameEnhancer` cargado se reutiliza si no
  cambian modelo ni configuración (una sola entrada; se libera al cambiar).
- **Falta de VRAM**: ante un OOM de CUDA se reintenta el frame con tiles más pequeños
  (512 → 256 → 128) y se registra el tile efectivo en el job y en los logs. No se pasa a fp32:
  usaría más memoria.
- **Disco**: al terminar la mejora se recortan los frames originales al set de vista previa
  (el encode solo lee los mejorados), si "Limpiar temporales al terminar" está activo.
- **Vista previa en vivo**: se refresca como mucho cada 2 s para no multiplicar peticiones.

## Verificación

- Tests: estimación por etapa, reintento por OOM, caché del modelo, recorte temprano, SSE.
- E2E con GPU real: estimación visible ("~0:48 restante"), SSE activo, originales recortados
  tras la mejora (9,4 MB) y segundo job reutilizando el modelo (94 ms/frame vs 100 ms).

## Fuera de alcance

- Pipeline por streaming o por tandas (pipe a ffmpeg).
