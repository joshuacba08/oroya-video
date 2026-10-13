# REQ-026 - Observabilidad y diagnóstico

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Que cuando algo falle en el equipo de un usuario haya información útil, acotada y fácil de
compartir, sin enviar nada a ningún servidor.

## Implementación

- **Logs**: `backend.log` con rotación (5 × 5 MB) y `audit.log` con rotación simple. El
  logging se configura al crear la app (antes del lifespan) e instala `sys.excepthook` y
  `threading.excepthook`: los errores de arranque y de hilos quedan registrados. Los errores
  de uvicorn también van al archivo.
- **Menos ruido**: el progreso por frame pasa a DEBUG; los sondeos de la UI (`/queue`,
  `/health`, `/jobs/*/progress|events`, `/system/gpu`, `/app-state`) se registran en DEBUG,
  salvo si tardan más de 1 s o fallan (WARNING/ERROR). En la app de escritorio la consola
  (que va a `backend-process.log`) solo recibe avisos y errores.
- **Errores de la UI**: `GlobalErrorHandler` los envía a `POST /system/client-log` (máximo 30
  por minuto) y muestra un aviso flotante (`ov-notifications`, propio: el toast de la
  librería requiere el compilador JIT). Si Angular no arranca, `main.ts` muestra un mensaje
  bilingüe en lugar de una ventana vacía.
- **Diagnóstico exportable** (`POST /system/diagnostics`, Ajustes → Soporte): zip en
  `storage/diagnostics` (se conservan 5) con `system.json` (versión, SO, GPU, herramientas,
  runtime de IA, espacio, versión de esquema y `PRAGMA quick_check`), `jobs.json` (20 jobs
  recientes con sus últimas 200 líneas de log), `settings.json` y los logs. La carpeta del
  usuario se sustituye por `~`. Se abre la carpeta del zip.
- **"Abrir carpeta de logs"** en Ajustes (`storage/open?target=logs`).

## Verificación

- Tests: contenido del zip y anonimización, límite de `client-log`, carpeta de logs,
  clasificación de sondeos y rotación de `audit.log`; vitest del `GlobalErrorHandler`.
- Manual: exportación desde Ajustes en el navegador de desarrollo (zip de 821 KB, sin el
  nombre de usuario de Windows).
