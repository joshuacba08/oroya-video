from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Oroya Video Backend"
    app_version: str = "0.1.0"
    api_version: str = "v1"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True
    storage_path: str = "storage"
    database_url: str = "sqlite:///storage/db/oroya-video.sqlite"
    cors_origins: str = (
        "http://localhost:4200,http://127.0.0.1:4200,"
        "tauri://localhost,https://tauri.localhost"
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
    cleanup_temp_on_success: bool = False
    cleanup_temp_older_than_hours: int = 72
    max_job_retries: int = 1
    process_shutdown_timeout_seconds: int = 5
    preflight_min_free_disk_gb: float = 10.0
    audit_log_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
