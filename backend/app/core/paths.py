import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.core.config import BACKEND_ROOT, Settings, get_settings


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def resolve_path(raw_path: str, settings: Settings | None = None) -> Path:
    base_path = Path(raw_path)
    if base_path.is_absolute():
        return base_path

    return (BACKEND_ROOT / base_path).resolve()


def get_storage_path(settings: Settings | None = None) -> Path:
    active_settings = _get_active_settings(settings)
    return resolve_path(active_settings.storage_path, active_settings)


def get_db_path(settings: Settings | None = None) -> Path:
    return get_storage_path(settings) / "db"


def get_temp_path(settings: Settings | None = None) -> Path:
    return get_storage_path(settings) / "temp"


def get_ai_dry_runs_path(settings: Settings | None = None) -> Path:
    return get_temp_path(settings) / "ai-dry-runs"


def get_jobs_temp_path(settings: Settings | None = None) -> Path:
    return get_temp_path(settings) / "jobs"


def get_exports_path(settings: Settings | None = None) -> Path:
    return get_storage_path(settings) / "exports"


def get_imports_path(settings: Settings | None = None) -> Path:
    return get_storage_path(settings) / "imports"


def get_models_path(settings: Settings | None = None) -> Path:
    return get_storage_path(settings) / "models"


def get_ai_models_path(settings: Settings | None = None) -> Path:
    return get_models_path(settings)


def get_realesrgan_models_path(settings: Settings | None = None) -> Path:
    return get_ai_models_path(settings) / "realesrgan"


def get_model_path(relative_path: str, settings: Settings | None = None) -> Path:
    base_path = Path(relative_path)
    if base_path.is_absolute():
        return base_path

    return (get_ai_models_path(settings) / base_path).resolve()


def get_logs_path(settings: Settings | None = None) -> Path:
    return get_storage_path(settings) / "logs"


def get_settings_file_path(settings: Settings | None = None) -> Path:
    return get_storage_path(settings) / "settings.json"


def get_audit_log_path(settings: Settings | None = None) -> Path:
    return get_logs_path(settings) / "audit.log"


def get_video_import_path(
    video_asset_id: str,
    settings: Settings | None = None,
) -> Path:
    return get_imports_path(settings) / video_asset_id


def get_job_working_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_jobs_temp_path(settings) / job_id


def get_job_original_frames_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_working_path(job_id, settings) / "frames" / "original"


def get_job_enhanced_frames_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_working_path(job_id, settings) / "frames" / "enhanced"


def get_job_filtered_frames_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_working_path(job_id, settings) / "frames" / "filtered"


def get_data_bin_path(settings: Settings | None = None) -> Path:
    active_settings = settings or get_settings()
    if active_settings.oroya_data_dir:
        return Path(active_settings.oroya_data_dir) / "bin"
    return BACKEND_ROOT / "bin"


def get_job_logs_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_working_path(job_id, settings) / "logs"


def get_job_encoded_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_working_path(job_id, settings) / "encoded"


def get_job_muxed_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_working_path(job_id, settings) / "muxed"


def get_job_silent_video_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_encoded_path(job_id, settings) / "video_silent.mp4"


def get_job_muxed_video_path(job_id: str, settings: Settings | None = None) -> Path:
    return get_job_muxed_path(job_id, settings) / "video_with_audio.mp4"


def get_project_exports_path(project_id: str, settings: Settings | None = None) -> Path:
    return get_exports_path(settings) / project_id


def get_job_export_path(
    project_id: str,
    job_id: str,
    settings: Settings | None = None,
) -> Path:
    return get_project_exports_path(project_id, settings) / job_id


def get_final_export_video_path(
    project_id: str,
    job_id: str,
    file_name: str,
    settings: Settings | None = None,
) -> Path:
    return get_job_export_path(project_id, job_id, settings) / file_name


def build_frame_file_name(index: int) -> str:
    return f"frame_{index:08d}.png"


def ensure_job_directories(job_id: str, settings: Settings | None = None) -> dict[str, Path]:
    working_dir = get_job_working_path(job_id, settings)
    original_frames_dir = get_job_original_frames_path(job_id, settings)
    enhanced_frames_dir = get_job_enhanced_frames_path(job_id, settings)
    logs_dir = get_job_logs_path(job_id, settings)
    encoded_dir = get_job_encoded_path(job_id, settings)
    muxed_dir = get_job_muxed_path(job_id, settings)

    for directory in (
        working_dir,
        original_frames_dir,
        enhanced_frames_dir,
        logs_dir,
        encoded_dir,
        muxed_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    return {
        "working_dir": working_dir,
        "original_frames_dir": original_frames_dir,
        "enhanced_frames_dir": enhanced_frames_dir,
        "logs_dir": logs_dir,
        "encoded_dir": encoded_dir,
        "muxed_dir": muxed_dir,
    }


def ensure_job_encoded_directory(job_id: str, settings: Settings | None = None) -> Path:
    encoded_dir = get_job_encoded_path(job_id, settings)
    encoded_dir.mkdir(parents=True, exist_ok=True)
    return encoded_dir


def ensure_job_muxed_directory(job_id: str, settings: Settings | None = None) -> Path:
    muxed_dir = get_job_muxed_path(job_id, settings)
    muxed_dir.mkdir(parents=True, exist_ok=True)
    return muxed_dir


def ensure_job_export_directory(
    project_id: str,
    job_id: str,
    settings: Settings | None = None,
) -> Path:
    export_dir = get_job_export_path(project_id, job_id, settings)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


def ensure_ai_dry_runs_directory(settings: Settings | None = None) -> Path:
    dry_runs_dir = get_ai_dry_runs_path(settings)
    dry_runs_dir.mkdir(parents=True, exist_ok=True)
    return dry_runs_dir


def get_storage_path_strings(settings: Settings | None = None) -> dict[str, str]:
    active_settings = _get_active_settings(settings)
    storage_root = Path(active_settings.storage_path)
    return {
        "storage": storage_root.as_posix(),
        "db": (storage_root / "db").as_posix(),
        "temp": (storage_root / "temp").as_posix(),
        "exports": (storage_root / "exports").as_posix(),
        "models": (storage_root / "models").as_posix(),
        "logs": (storage_root / "logs").as_posix(),
    }


def ensure_storage_directories(settings: Settings | None = None) -> None:
    directories = (
        get_storage_path(settings),
        get_db_path(settings),
        get_temp_path(settings),
        get_ai_dry_runs_path(settings),
        get_jobs_temp_path(settings),
        get_exports_path(settings),
        get_imports_path(settings),
        get_models_path(settings),
        get_realesrgan_models_path(settings),
        get_logs_path(settings),
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def is_storage_writable(settings: Settings | None = None) -> bool:
    storage_path = get_storage_path(settings)
    ensure_storage_directories(settings)

    try:
        with NamedTemporaryFile(dir=storage_path, prefix=".oroya-write-test-", delete=True):
            return True
    except OSError:
        return False


def delete_job_frames_directories(job_id: str, settings: Settings | None = None) -> None:
    for directory in (
        get_job_original_frames_path(job_id, settings),
        get_job_enhanced_frames_path(job_id, settings),
    ):
        if directory.exists():
            shutil.rmtree(directory)


def get_directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        # Otra limpieza (o el pipeline) puede borrar archivos mientras se recorre la carpeta.
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def to_client_path(path: Path, settings: Settings | None = None) -> str:
    # Absolute: the client (Tauri opener, UI) cannot resolve paths relative to storage.
    return str(path.resolve())
