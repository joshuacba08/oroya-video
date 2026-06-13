import logging
from contextvars import ContextVar
from logging.config import dictConfig
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.paths import ensure_storage_directories, get_logs_path

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


def _get_log_file_path(settings: Settings | None = None) -> Path:
    return get_logs_path(settings) / "backend.log"


def configure_logging(settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    ensure_storage_directories(active_settings)
    log_file_path = _get_log_file_path(active_settings)
    log_level = "DEBUG" if active_settings.debug else "INFO"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": LOG_FORMAT,
                    "datefmt": LOG_DATE_FORMAT,
                }
            },
            "filters": {
                "request_id": {
                    "()": RequestIdFilter,
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": log_level,
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                    "filters": ["request_id"],
                },
                "file": {
                    "class": "logging.FileHandler",
                    "level": log_level,
                    "formatter": "standard",
                    "filename": str(log_file_path),
                    "encoding": "utf-8",
                    "filters": ["request_id"],
                },
            },
            "loggers": {
                "oroya_video": {
                    "level": log_level,
                    "handlers": ["console", "file"],
                    "propagate": False,
                }
            },
            "root": {
                "level": log_level,
                "handlers": ["console", "file"],
            },
        }
    )


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger("oroya_video")

    return logging.getLogger(f"oroya_video.{name}")


def set_request_id(request_id: str) -> object:
    return request_id_context.set(request_id)


def reset_request_id(token: object) -> None:
    request_id_context.reset(token)
