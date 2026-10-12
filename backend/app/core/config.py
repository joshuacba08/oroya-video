import sys
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
    # Carpeta de los videos exportados. En escritorio, por defecto la de Vídeos del usuario:
    # fuera de AppData, desinstalar con "borrar datos" no se lleva los videos.
    exports_dir: str | None = None
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
    # Solo para pruebas: ralentiza el motor mock (ms por frame).
    mock_enhancer_frame_delay_ms: int = 0
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
            # Con otro STORAGE_PATH (tests, E2E) la base va dentro de ese almacenamiento,
            # aunque un .env repita DATABASE_URL con el valor por defecto: antes la base
            # seguía siendo la de backend/storage y los tests tocaban los datos de desarrollo.
            if (
                self.database_url == DEFAULT_DATABASE_URL
                and self.storage_path != DEFAULT_STORAGE_PATH
            ):
                db_path = Path(self.storage_path) / "db" / "oroya-video.sqlite"
                self.database_url = f"sqlite:///{db_path.as_posix()}"
            return self

        data_dir = Path(self.oroya_data_dir)
        if self.storage_path == DEFAULT_STORAGE_PATH:
            self.storage_path = str(data_dir / "storage")
        if self.database_url == DEFAULT_DATABASE_URL:
            db_path = Path(self.storage_path) / "db" / "oroya-video.sqlite"
            self.database_url = f"sqlite:///{db_path.as_posix()}"
        if self.ai_extra_site_dir is None:
            self.ai_extra_site_dir = str(data_dir / "ai-env")
        if self.exports_dir is None:
            self.exports_dir = str(default_videos_dir() / "Oroya Video")
        return self


def default_videos_dir() -> Path:
    """The user's Videos folder (Windows known folder, also when redirected to OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            # FOLDERID_Videos {18989B1D-99B5-455B-841C-AB7C74E4DDFC}
            folder_id = GUID(
                0x18989B1D,
                0x99B5,
                0x455B,
                (ctypes.c_ubyte * 8)(0x84, 0x1C, 0xAB, 0x7C, 0x74, 0xE4, 0xDD, 0xFC),
            )
            path_pointer = ctypes.c_wchar_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(path_pointer)
            )
            if result == 0 and path_pointer.value:
                folder = Path(path_pointer.value)
                ctypes.windll.ole32.CoTaskMemFree(path_pointer)
                return folder
        except (AttributeError, OSError):
            pass
    return Path.home() / "Videos"


@lru_cache
def get_settings() -> Settings:
    return Settings()
