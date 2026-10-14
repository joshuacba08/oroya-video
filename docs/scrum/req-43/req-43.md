# REQ-043 - Vista previa en movimiento

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Ver unos segundos del resultado en movimiento y con audio, junto al original, antes de procesar
el video entero. Así se ajustan modelo, intensidad, estabilidad e interpolación sin esperar
toda la exportación.

## Implementación

- **Backend:** `POST /projects/{id}/preview-clip {start_seconds, duration_seconds≤5}`.
  - Crea un job con `job_kind = "preview"` y los ajustes actuales del proyecto. Lo procesa el
    mismo pipeline por streaming, siempre en ese modo: se ve exactamente lo que dará la
    exportación.
  - Tras el audio no se exporta: se genera el mismo fragmento del original, ampliado con Lanczos
    al tamaño del mejorado, para compararlos.
  - `GET /jobs/{id}/preview-clip/{enhanced|original}` sirve los videos (con rangos, para poder
    buscar).
- **Cola con prioridad:** las vistas previas pasan por delante de los exports en espera. Si hay
  uno en marcha, esperan a que termine.
- **Efímeras:**
  - no aparecen en la cola, el panel, el historial ni como último trabajo del proyecto
    (`export_jobs_query`);
  - generar otra borra la anterior y sus archivos;
  - al arrancar se borran todas.
- **Frontend:** botón "Vista previa en movimiento" en el Workspace.
  - Procesa 3 s desde el fotograma seleccionado (o desde el inicio del recorte), con los ajustes
    que se ven en pantalla.
  - Muestra el progreso y avisa si espera tras otro trabajo.
  - Luego abre un panel con los dos videos sincronizados; el mejorado lleva los controles y el
    audio.

## Verificación

- Tests:
  - prioridad de la cola;
  - flujo completo con ffmpeg real: se procesa sin exportar, se sirven los dos videos con la
    duración pedida, no aparece en la cola ni como último trabajo, y la siguiente sustituye a la
    anterior y borra sus archivos;
  - variante desconocida → 404.
- E2E: desde un proyecto, el video de la vista previa se carga (`readyState ≥ 2`) y no aparece
  en la cola.
