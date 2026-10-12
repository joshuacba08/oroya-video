# REQ-023 - Ciclo de vida del backend en escritorio

## Proyecto

Oroya Video

## Área

Escritorio (Tauri / Rust) / Frontend / Backend

## Objetivo

Que el backend local arranque, se recupere y se detenga de forma fiable sin intervención del
usuario: sin backends huérfanos, sin dos instancias sobre la misma base de datos y sin
depender de que el puerto 8001 esté libre.

## Implementación

- **Instancia única** (`tauri-plugin-single-instance`): una segunda ejecución enfoca la
  ventana existente y termina sin arrancar otro backend.
- **Puerto e identidad**: 8001 si está libre; si no, uno asignado por el sistema. Cada arranque
  genera `OROYA_INSTANCE_ID`; el backend lo devuelve en `/health` y la app solo lo considera
  listo cuando coincide (un huérfano o una versión antigua en el puerto no cuenta).
- **Frontend**: `backend_info` y el evento `backend-status` (`starting`, `ready`, `exited`,
  `failed`) actualizan la URL base de la API (`core/api/api-base-url.ts`); la CSP admite
  `http://127.0.0.1:*`. Pantalla "Iniciando el motor…" y pantalla de fallo con "Reintentar"
  (`restart_backend`) y "Abrir carpeta de logs".
- **Arranque no bloqueante** en un hilo supervisor; stdout/stderr del backend a
  `storage/logs/backend-process.log` (rotado a 5 MB) para ver errores de import o de bind.
- **Apagado ordenado**: al cerrar, `POST /system/shutdown` con `X-Oroya-Instance` (el
  backend pausa la mejora y termina ffmpeg en su lifespan); `kill` solo si no termina en 10 s.
- **Sin huérfanos**: el backend corre en un Job Object con kill-on-close; ffmpeg y pip lo
  heredan. Además, la recuperación al arrancar termina el ffmpeg cuyo PID guardaba un job.
- **Supervisión**: si el backend muere, se reinicia (2 veces como máximo, con espera); la UI
  vuelve a cargar el estado cuando queda listo.

## Verificación

- Tests: `instance_id` en health, shutdown con instancia correcta/incorrecta/ausente,
  terminación de huérfanos solo si el proceso es ffmpeg.
- Manual con la build de release: arranque normal; segunda instancia (1 app, 1 backend);
  cierre normal (shutdown ordenado en ~1 s); 8001 ocupado (arranca en otro puerto y la UI lo
  usa); backend matado a mano (se reinicia y la UI recarga); app matada a la fuerza (el
  backend muere con ella).
