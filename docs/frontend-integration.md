# Frontend Integration Guide

## Startup Flow

1. Llamar `GET /api/v1/health`.
2. Llamar `GET /api/v1/bootstrap`.
3. Llamar `GET /api/v1/app-state`.
4. Llamar `GET /api/v1/settings`.
5. Si hay jobs interrumpidos, consultar `GET /api/v1/jobs/interrupted`.

## Dashboard Flow

1. `GET /api/v1/dashboard`
2. `GET /api/v1/queue`
3. Refrescar cada 10s si hay jobs activos.

## Import Video Flow

1. Tauri abre file picker.
2. Angular envía la ruta local a `POST /api/v1/videos/probe`.
3. Si la metadata es válida, llamar `POST /api/v1/videos/import`.

## Create Project Flow

1. `POST /api/v1/projects`
2. Navegar al workspace usando `GET /api/v1/projects/{project_id}/workspace`

## Workspace Load Flow

Usar una llamada principal:

1. `GET /api/v1/projects/{project_id}/workspace`

Con eso la UI obtiene proyecto, video, modelo seleccionado, preview recomendado, job reciente y acciones disponibles.

## Create And Start Job Flow

1. `POST /api/v1/jobs`
2. Opcional: `GET /api/v1/jobs/{job_id}/preflight`
3. `POST /api/v1/jobs/{job_id}/start`
4. Si falla, leer `details.checks`, `details.warnings` y `details.errors`

## Poll Progress Flow

- `running`: `GET /api/v1/jobs/{job_id}/progress` cada 1s
- `queued`: cada 2s
- `completed`, `failed`, `cancelled`: detener polling

## Preview Flow

1. `GET /api/v1/jobs/{job_id}/preview/recommended`
2. `GET /api/v1/jobs/{job_id}/preview/frames`
3. Renderizar split, slider o side-by-side en frontend

## Export Flow

1. `GET /api/v1/jobs/{job_id}/final-export`
2. `GET /api/v1/exports`
3. `POST /api/v1/exports/{export_id}/open-folder`

## Cancel And Retry Flow

1. `POST /api/v1/jobs/{job_id}/cancel`
2. Si el job queda fallido o interrumpido:
   - `GET /api/v1/jobs/{job_id}/diagnostics`
   - `POST /api/v1/jobs/{job_id}/retry`

## Cleanup Flow

1. `DELETE /api/v1/jobs/{job_id}/temp`
2. `POST /api/v1/system/cleanup/temp`
3. `GET /api/v1/system/storage/usage`

## Settings Flow

1. `GET /api/v1/settings`
2. `PATCH /api/v1/settings`
3. Refrescar bootstrap o app-state si cambian opciones de procesamiento

## Error Handling Flow

- Mostrar `message` al usuario.
- Usar `details` para UI contextual.
- Incluir `request_id` en logs del frontend.
- No asumir tracebacks ni mensajes internos.

## Polling Summary

- Dashboard: 10s con actividad
- Queue: 5-10s
- Health/full o app-state: 30s
- Progress por job: 1-2s

## Tauri Notes

- Backend local esperado en `http://127.0.0.1:8000`
- CORS listo para `http://localhost:4200`, `http://127.0.0.1:4200`, `tauri://localhost` y `https://tauri.localhost`
- El backend soporta arranque con `uvicorn app.main:app` y `python -m app`
