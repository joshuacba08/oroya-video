# Oroya Video Backend API Contract

## Base URL

- Oficial: `/api/v1`
- Legacy temporal: `/api`

## Principios

- IDs son UUID string.
- Fechas se serializan en ISO 8601 UTC.
- Paths de archivos se devuelven como strings.
- Las listas incluyen `items`, `total`, `limit`, `offset`.
- Los errores usan envelope estable.

## Error Envelope

```json
{
  "error": "error_code",
  "message": "Human readable message.",
  "details": {},
  "request_id": "req_abc123",
  "timestamp": "2026-06-13T12:00:00Z"
}
```

## Pagination Format

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

## Core Endpoints

- `GET /api/v1/health`
- `GET /api/v1/health/full`
- `GET /api/v1/bootstrap`
- `GET /api/v1/dashboard`
- `GET /api/v1/app-state`
- `GET /api/v1/queue`
- `GET /api/v1/settings`
- `PATCH /api/v1/settings`
- `POST /api/v1/videos/probe`
- `POST /api/v1/videos/import`
- `GET /api/v1/projects/{project_id}/workspace`
- `POST /api/v1/jobs`
- `POST /api/v1/jobs/{job_id}/start`
- `GET /api/v1/jobs/{job_id}/progress`
- `GET /api/v1/jobs/{job_id}/preview/recommended`
- `GET /api/v1/exports`

## Job Lifecycle

Estados:

- `pending`
- `queued`
- `running`
- `paused`
- `completed`
- `failed`
- `cancelled`
- `interrupted`
- `retrying`
- `cleaning`

Etapas:

- `idle`
- `preflight`
- `queued`
- `extracting_frames`
- `enhancing_frames`
- `encoding_video`
- `muxing_audio`
- `exporting`
- `recovering`
- `retrying`
- `cleaning`
- `interrupted`
- `completed`
- `failed`
- `cancelled`

## Progress Contract

`GET /api/v1/jobs/{job_id}/progress` siempre incluye:

- `job_id`
- `project_id`
- `status`
- `current_stage`
- `progress_percent`
- `stage_progress_percent`
- `stage_label`
- `can_cancel`
- `can_pause`
- `can_retry`
- `can_cleanup`
- `preview_available`
- `export_available`
- `updated_at`

## Queue Contract

`GET /api/v1/queue` devuelve:

- `items`
- `total`
- `running`
- `queued`
- `pending`
- `interrupted`
- `limit`
- `offset`

## Workspace Contract

`GET /api/v1/projects/{project_id}/workspace` devuelve:

- `project`
- `video`
- `latest_job`
- `latest_export`
- `models.selected`
- `models.available`
- `preview.available`
- `preview.recommended`
- `actions`

## Preview Contract

- `GET /api/v1/jobs/{job_id}/preview`
- `GET /api/v1/jobs/{job_id}/preview/original/{frame_index}`
- `GET /api/v1/jobs/{job_id}/preview/enhanced/{frame_index}`
- `GET /api/v1/jobs/{job_id}/preview/compare/{frame_index}`
- `GET /api/v1/jobs/{job_id}/preview/recommended`
- `GET /api/v1/jobs/{job_id}/preview/frames`

Las URLs de preview devueltas por la API son relativas y apuntan a `/api/v1/...`.

## Export Contract

- `GET /api/v1/exports`
- `GET /api/v1/exports/{export_id}`
- `POST /api/v1/exports/{export_id}/open`
- `POST /api/v1/exports/{export_id}/open-folder`
- `DELETE /api/v1/exports/{export_id}`

## Settings Contract

`GET /api/v1/settings` expone:

- `general`
- `processing`
- `storage`
- `cleanup`

`PATCH /api/v1/settings` persiste la configuración local en `storage/settings.json`.

## Hardening Contract

- `GET /api/v1/jobs/interrupted`
- `GET /api/v1/jobs/{job_id}/preflight`
- `POST /api/v1/jobs/{job_id}/retry`
- `GET /api/v1/jobs/{job_id}/pipeline`
- `GET /api/v1/jobs/{job_id}/diagnostics`
- `DELETE /api/v1/jobs/{job_id}/temp`
- `GET /api/v1/system/storage/usage`
- `POST /api/v1/system/cleanup/temp`

## Polling Recommendations

- Job `running`: cada 1s en `/api/v1/jobs/{job_id}/progress`
- Job `queued`: cada 2s
- Dashboard con jobs activos: cada 10s
- Estado global del sistema: cada 30s

## Tauri Integration Notes

- Tauri abre el file picker y envía la ruta absoluta al backend.
- El backend no abre diálogos de sistema.
- El frontend debe propagar `X-Request-ID` cuando quiera correlación end-to-end.
