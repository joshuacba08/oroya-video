from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import DownloadSourceNotConfiguredError
from app.core.logging import get_logger
from app.core.paths import get_model_path
from app.db import database
from app.schemas.ai_model_schema import (
    AIModelDownloadProgressResponse,
    AIModelDownloadStartResponse,
)
from app.services import ai_model_service
from app.services.audit_log_service import record_audit_event
from app.services.download_service import get_download_state, start_download

logger = get_logger(__name__)

# Fuentes oficiales (releases de github.com/xinntao/Real-ESRGAN). Los SHA256
# están verificados contra los archivos publicados.
MODEL_DOWNLOAD_SOURCES: dict[str, dict[str, str]] = {
    "realesrgan-x2": {
        "url": (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.2.1/RealESRGAN_x2plus.pth"
        ),
        "sha256": "49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb",
    },
    "realesrgan-x4": {
        "url": (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.1.0/RealESRGAN_x4plus.pth"
        ),
        "sha256": "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1",
    },
    "realesrgan-general": {
        "url": (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.3.0/realesr-general-x4v3.pth"
        ),
        "sha256": "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292",
    },
}


def _download_key(slug: str) -> str:
    return f"model:{slug}"


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def start_model_download(
    db: Session,
    model_id_or_slug: str,
    settings: Settings | None = None,
) -> AIModelDownloadStartResponse:
    active_settings = _get_active_settings(settings)
    model = ai_model_service._get_model_or_raise(db, model_id_or_slug)

    # El flag de la DB puede estar desfasado (archivo borrado a mano): se comprueba el disco.
    installed_file_exists = bool(model.relative_path) and get_model_path(
        model.relative_path, active_settings
    ).is_file()
    if model.is_installed and installed_file_exists:
        return AIModelDownloadStartResponse(
            slug=model.slug,
            status="completed",
            already_installed=True,
        )

    source = MODEL_DOWNLOAD_SOURCES.get(model.slug)
    if source is None or not model.relative_path:
        raise DownloadSourceNotConfiguredError()

    dest_path = get_model_path(model.relative_path, active_settings)
    model_id = model.id
    model_slug = model.slug

    def on_complete() -> None:
        _refresh_after_download(model_id, model_slug, active_settings)

    state = start_download(
        _download_key(model.slug),
        source["url"],
        dest_path,
        sha256=source["sha256"],
        on_complete=on_complete,
    )
    logger.info("Model download started: %s", model.slug)
    return AIModelDownloadStartResponse(
        slug=model.slug,
        status=state.status,
        already_installed=False,
    )


def _refresh_after_download(
    model_id: str,
    model_slug: str,
    settings: Settings,
) -> None:
    if database.SessionLocal is None:
        return
    db = database.SessionLocal()
    try:
        ai_model_service.refresh_models(db, settings)
        record_audit_event(
            "model_downloaded",
            "model",
            model_id,
            f"Model weights downloaded: {model_slug}",
            settings=settings,
        )
    except Exception:
        logger.exception("Post-download model refresh failed: %s", model_slug)
    finally:
        db.close()


def get_model_download_progress(
    db: Session,
    model_id_or_slug: str,
) -> AIModelDownloadProgressResponse:
    model = ai_model_service._get_model_or_raise(db, model_id_or_slug)
    state = get_download_state(_download_key(model.slug))
    status = state.status
    if status == "idle" and model.is_installed:
        status = "completed"
    return AIModelDownloadProgressResponse(
        slug=model.slug,
        status=status,
        bytes_done=state.bytes_done,
        bytes_total=state.bytes_total,
        percent=state.percent if status != "completed" else 100.0,
        error_code=state.error_code,
        error_message=state.error_message,
    )


__all__ = [
    "MODEL_DOWNLOAD_SOURCES",
    "get_model_download_progress",
    "start_model_download",
]
