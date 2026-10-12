import logging
import sys
import threading
from contextvars import ContextVar
from logging.config import dictConfig
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.paths import ensure_storage_directories, get_logs_path

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
# Rotación: 5 archivos de 5 MB (antes un solo archivo crecía sin límite).
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5


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
    # En la app de escritorio stdout ya va a backend-process.log: ahí solo avisos y errores,
    # para no duplicar todo backend.log.
    console_level = "WARNING" if active_settings.environment == "production" else log_level

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
                    "level": console_level,
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                    "filters": ["request_id"],
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": log_level,
                    "formatter": "standard",
                    "filename": str(log_file_path),
                    "maxBytes": LOG_MAX_BYTES,
                    "backupCount": LOG_BACKUP_COUNT,
                    "encoding": "utf-8",
                    "delay": True,
                    "filters": ["request_id"],
                },
            },
            "loggers": {
                "oroya_video": {
                    "level": log_level,
                    "handlers": ["console", "file"],
                    "propagate": False,
                },
                # Errores de uvicorn (p. ej. no poder abrir el puerto) también en backend.log;
                # su log de accesos sobra: AccessLogMiddleware ya registra cada petición.
                "uvicorn.error": {"level": "INFO", "handlers": ["file"], "propagate": True},
                "uvicorn.access": {"level": "WARNING"},
            },
            "root": {
                "level": log_level,
                "handlers": ["console", "file"],
            },
        }
    )


def install_exception_hooks() -> None:
    """Uncaught exceptions (main thread or worker threads) go to backend.log too."""
    logger = logging.getLogger("oroya_video.crash")

    def log_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    def log_thread_exception(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        logger.critical(
            "Uncaught exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_exception
    threading.excepthook = log_thread_exception


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger("oroya_video")

    return logging.getLogger(f"oroya_video.{name}")


def set_request_id(request_id: str) -> object:
    return request_id_context.set(request_id)


def reset_request_id(token: object) -> None:
    request_id_context.reset(token)
