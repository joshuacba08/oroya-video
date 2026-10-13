# REQ-034 - Procesamiento por lotes

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Importar varios videos de una vez y procesarlos con los mismos ajustes, uno tras otro, sin
tener que entrar en cada proyecto.

## Implementación

- **Importar varios**: `DesktopService.pickVideos()` (selector múltiple); en el navegador de
  desarrollo, la importación manual acepta varias rutas (una por línea, Mayús+Enter).
  `ImportService` sustituye las tres copias de la importación (shell, Inicio, Proyectos):
  importa de uno en uno, avisa de los que fallan sin cancelar el resto; un video abre su
  Workspace, varios abren el diálogo de lote.
- **Diálogo "Procesar en lote"** (`ov-batch-dialog` + `BatchService`): modelo, resolución,
  restaurar rostros y conservar audio, prellenados con los ajustes del primer proyecto.
  También desde Proyectos, seleccionando varias tarjetas.
- **`POST /jobs/batch`**: crea y encola un job por proyecto en orden (sin duplicados); los que
  no se pueden encolar (proyecto inexistente, preflight fallido…) se omiten con su motivo.
- **Últimos ajustes usados**: el lote guarda sus ajustes en `settings.json` (`defaults`, sin
  nombre de archivo ni recorte); los proyectos nuevos parten de ellos si siguen siendo válidos.
- **Cola**: orden real de proceso (en marcha, en cola por `queued_at`, resto), "#N en la cola"
  y "Reanudar todo".
- **Reinicio**: los jobs que esperaban en la cola se vuelven a encolar en el mismo orden al
  arrancar; solo el que estaba en marcha pasa a "interrumpido".

## Verificación

- Tests: orden y ajustes del lote, omitidos, últimos ajustes en proyectos nuevos, cola tras
  reinicio; vitest de `ImportService` (rutas, un video, fallo parcial).
- E2E: tres videos importados a la vez, encolados y exportados con nombre legible.
