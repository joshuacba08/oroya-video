import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import OroyaVideoError
from app.core.logging import configure_logging, get_logger, install_exception_hooks
from app.core.parent_watchdog import start_parent_watchdog
from app.core.paths import ensure_storage_directories, get_storage_path
from app.db import database
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.local_only import LocalOnlyMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.services.ai_model_service import seed_default_models
from app.services.ai_runtime_service import ensure_ai_extra_site_dir
from app.services.cleanup_service import start_startup_temp_cleanup
from app.services.job_recovery_service import (
    get_waiting_job_ids,
    recover_interrupted_jobs_on_startup,
)
from app.services.process_registry_service import clear_registry
from app.services.settings_service import (
    activate_installed_ai_runtime,
    apply_persisted_settings,
)
from app.workers.job_runner import start_job_worker, stop_job_worker
from app.workers.queue import job_queue

logger = get_logger(__name__)
OPENAPI_TAGS = [
    {"name": "Health", "description": "Basic backend health and version endpoints."},
    {"name": "System", "description": "System, storage, tools and environment endpoints."},
    {"name": "Settings", "description": "Desktop-local settings contract for the frontend."},
    {"name": "Dashboard", "description": "Bootstrap, dashboard and queue summary endpoints."},
    {"name": "Videos", "description": "Local video probe, import and registry endpoints."},
    {"name": "Projects", "description": "Project CRUD and workspace bootstrap endpoints."},
    {"name": "Models", "description": "AI model registry endpoints."},
    {"name": "Jobs", "description": "Processing job lifecycle, progress and control endpoints."},
    {"name": "Preview", "description": "Before/after preview frame endpoints."},
    {"name": "Exports", "description": "Final export listing and file actions."},
    {"name": "AI Runtime", "description": "Runtime and Real-ESRGAN readiness endpoints."},
    {"name": "Cleanup", "description": "Temporary storage cleanup endpoints."},
    {"name": "Diagnostics", "description": "Job diagnostics and failure analysis endpoints."},
]


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_cors_origins(settings: Settings) -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


def _build_error_payload(
    request: Request,
    *,
    error: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "error": error,
        "message": message,
        "details": details or {},
        "request_id": getattr(request.state, "request_id", "-"),
        "timestamp": _utcnow_iso(),
    }


def _activate_ai_runtime_quietly(settings: Settings) -> None:
    try:
        activate_installed_ai_runtime(settings)
    except Exception:  # noqa: BLE001 - una comprobación opcional nunca tumba el arranque
        logger.warning("AI runtime check at startup failed", exc_info=True)


def create_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_settings = apply_persisted_settings(settings)
        ensure_storage_directories(settings)
        configure_logging(active_settings)
        ensure_ai_extra_site_dir(active_settings)
        clear_registry()
        database.init_db(active_settings)
        app.state.settings = active_settings
        waiting_job_ids: list[str] = []
        if database.SessionLocal is not None:
            db = database.SessionLocal()
            try:
                seed_default_models(db, active_settings)
                recover_interrupted_jobs_on_startup(db, active_settings)
                waiting_job_ids = get_waiting_job_ids(db)
            finally:
                db.close()
            # Tras la recuperación: los jobs que quedaron a medias ya figuran como interrumpidos.
            start_startup_temp_cleanup(active_settings)
        # Importar torch tarda segundos: en segundo plano, sin retrasar el arranque.
        threading.Thread(
            target=_activate_ai_runtime_quietly,
            args=(active_settings,),
            daemon=True,
            name="ai-runtime-check",
        ).start()
        start_job_worker(active_settings)
        # Un lote en cola sobrevive al cierre de la app: se reanuda en el mismo orden.
        for job_id in waiting_job_ids:
            await job_queue.enqueue(job_id)
        if waiting_job_ids:
            logger.info("Requeued %s waiting jobs", len(waiting_job_ids))
        start_parent_watchdog()

        logger.info("%s started", active_settings.app_name)
        logger.info("Environment: %s", active_settings.environment)
        logger.info("Storage path: %s", get_storage_path(active_settings))
        yield
        await stop_job_worker()
        clear_registry()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = apply_persisted_settings(settings or get_settings())
    # Antes de crear la app: los errores de arranque (settings, base de datos...) quedan
    # registrados en backend.log y no solo en una consola que nadie ve.
    configure_logging(active_settings)
    install_exception_hooks()
    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        debug=active_settings.debug,
        lifespan=create_lifespan(active_settings),
        openapi_tags=OPENAPI_TAGS,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_cors_origins(active_settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    # El último añadido es el más externo: Host/Origin se comprueban antes que nada.
    app.add_middleware(LocalOnlyMiddleware, allowed_origins=_parse_cors_origins(active_settings))

    @app.exception_handler(OroyaVideoError)
    async def oroya_video_error_handler(request: Request, exc: OroyaVideoError) -> JSONResponse:
        logger.warning("Handled application error on %s: %s", request.url.path, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_payload(
                request,
                error=exc.error_code,
                message=exc.message,
                details=exc.details,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_build_error_payload(
                request,
                error="unknown_error",
                message="Unexpected server error.",
            ),
        )

    app.include_router(api_router)
    return app


app = create_app()
