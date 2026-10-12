from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.version import __version__

# Raíz del backend: el .env se lee desde aquí, no desde el directorio de trabajo.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_STORAGE_PATH = "storage"
DEFAULT_DATABASE_URL = "sqlite:///storage/db/oroya-video.sqlite"


class Settings(BaseSettings):
    app_name: str = "Oroya Video Backend"
    api_version: str = "v1"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True
    oroya_data_dir: str | None = None
    # Lo genera la app de escritorio en cada arranque: identifica a su backend (health) y
    # autoriza el apagado ordenado. Sin él (desarrollo) /system/shutdown no está disponible.
    oroya_instance_id: str | None = None
    storage_path: str = DEFAULT_STORAGE_PATH
    database_url: str = DEFAULT_DATABASE_URL
    ai_extra_site_dir: str | None = None
    cors_origins: str = (
        "http://localhost:4200,http://127.0.0.1:4200,"
        "tauri://localhost,http://tauri.localhost,https://tauri.localhost"
    )
    frame_enhancer_engine: str = "mock"
    ai_device: str = "auto"
    ai_allow_cpu: bool = True
    ai_half_precision: bool = True
    realesrgan_tile_size: int = 0
    realesrgan_tile_pad: int = 10
    realesrgan_pre_pad: int = 0
    realesrgan_max_failed_frames: int = 0
    realesrgan_clear_cuda_cache: bool = True
    job_recovery_enabled: bool = True
    mark_running_jobs_interrupted_on_startup: bool = True
    cleanup_temp_on_success: bool = True
    cleanup_keep_preview_frames: int = 24
    cleanup_temp_older_than_hours: int = 72
    max_job_retries: int = 3
    process_shutdown_timeout_seconds: int = 5
    # ffmpeg sin emitir progreso durante este tiempo se considera colgado.
    ffmpeg_stall_timeout_seconds: int = 180
    preflight_min_free_disk_gb: float = 10.0
    audit_log_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def app_version(self) -> str:
        # No configurable por .env: la versión la define el código (app/version.py).
        return __version__

    @model_validator(mode="after")
    def _apply_data_dir_defaults(self) -> "Settings":
        if not self.oroya_data_dir:
            return self

        data_dir = Path(self.oroya_data_dir)
        if self.storage_path == DEFAULT_STORAGE_PATH:
            self.storage_path = str(data_dir / "storage")
        if self.database_url == DEFAULT_DATABASE_URL:
            db_path = Path(self.storage_path) / "db" / "oroya-video.sqlite"
            self.database_url = f"sqlite:///{db_path.as_posix()}"
        if self.ai_extra_site_dir is None:
            self.ai_extra_site_dir = str(data_dir / "ai-env")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
