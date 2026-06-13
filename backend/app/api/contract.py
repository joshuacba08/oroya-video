from fastapi import APIRouter

from app.api.routes_ai_runtime import router as ai_runtime_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_exports import router as exports_router
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_models import router as models_router
from app.api.routes_preview import router as preview_router
from app.api.routes_projects import router as projects_router
from app.api.routes_settings import router as settings_router
from app.api.routes_system import router as system_router
from app.api.routes_videos import router as videos_router


def include_contract_routes(router: APIRouter) -> APIRouter:
    router.include_router(health_router, tags=["Health"])
    router.include_router(dashboard_router, tags=["Dashboard"])
    router.include_router(system_router, prefix="/system", tags=["System"])
    router.include_router(settings_router, prefix="/settings", tags=["Settings"])
    router.include_router(videos_router, prefix="/videos", tags=["Videos"])
    router.include_router(projects_router, prefix="/projects", tags=["Projects"])
    router.include_router(models_router, prefix="/models", tags=["Models"])
    router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
    router.include_router(preview_router, tags=["Preview"])
    router.include_router(exports_router, prefix="/exports", tags=["Exports"])
    router.include_router(ai_runtime_router, prefix="/ai", tags=["AI Runtime"])
    return router
