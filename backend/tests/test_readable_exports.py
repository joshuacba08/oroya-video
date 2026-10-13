import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.paths import project_display_name, remove_empty_export_dirs, safe_folder_name
from app.main import create_app
from app.services.export_service import (
    _build_unique_export_destination,
    build_export_file_name,
    get_export_directory,
)
from app.services.job_workspace_service import delete_job_files
from tests.test_projects import _create_project, _import_video


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'exports.sqlite').as_posix()}",
        exports_dir=str(tmp_path / "Videos" / "Oroya Video"),
    )


def _job(enhancement: dict | None = None, export: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        enhancement_config_json=json.dumps(enhancement or {"scale": "2x"}),
        export_config_json=json.dumps(export or {}),
    )


def test_names_are_readable_and_safe_for_windows() -> None:
    assert project_display_name("Vacaciones en la playa.MOV") == "Vacaciones en la playa"
    assert safe_folder_name("Mi viaje: día 1/2") == "Mi viaje día 1 2"
    assert safe_folder_name("CON") == "CON_"
    assert safe_folder_name("  ..  ") == "Oroya Video"
    assert len(safe_folder_name("x" * 300)) == 80


def test_export_goes_to_a_folder_named_after_the_project(tmp_path) -> None:
    settings = _settings(tmp_path)
    project = SimpleNamespace(name="Boda de Ana.mp4")
    job = _job({"scale": "4x", "interpolation": {"enabled": True, "target_fps": 60}})

    assert build_export_file_name(project, job) == "Boda de Ana (Oroya 4x 60fps).mp4"
    assert get_export_directory(project, job, settings) == (
        tmp_path / "Videos" / "Oroya Video" / "Boda de Ana"
    )


def test_custom_file_name_and_folder_come_from_the_job_snapshot(tmp_path) -> None:
    settings = _settings(tmp_path)
    project = SimpleNamespace(name="clip.mp4")
    chosen = tmp_path / "Escritorio"
    job = _job(export={"file_name": "Versión final", "output_dir": str(chosen)})

    assert build_export_file_name(project, job) == "Versión final.mp4"
    assert get_export_directory(project, job, settings) == chosen


def test_existing_exports_are_never_overwritten(tmp_path) -> None:
    (tmp_path / "clip (Oroya 2x).mp4").write_bytes(b"1")
    (tmp_path / "clip (Oroya 2x) (2).mp4").write_bytes(b"2")

    destination = _build_unique_export_destination(tmp_path, "clip (Oroya 2x).mp4")

    assert destination.name == "clip (Oroya 2x) (3).mp4"


def test_deleting_a_job_only_removes_its_own_export_files(tmp_path) -> None:
    settings = _settings(tmp_path)
    folder = tmp_path / "Videos" / "Oroya Video" / "clip"
    folder.mkdir(parents=True)
    own = folder / "clip (Oroya 2x).mp4"
    other = folder / "clip (Oroya 2x) (2).mp4"  # otro proyecto con el mismo nombre
    own.write_bytes(b"mine")
    other.write_bytes(b"theirs")

    delete_job_files("job-1", "project-1", settings, [str(own)])

    assert not own.exists()
    assert other.exists()

    delete_job_files("job-2", "project-2", settings, [str(other)])

    assert not folder.exists()
    # La carpeta raíz de exportación nunca se borra.
    assert (tmp_path / "Videos" / "Oroya Video").is_dir()


def test_a_folder_chosen_by_the_user_is_never_removed(tmp_path) -> None:
    settings = _settings(tmp_path)
    chosen = tmp_path / "Escritorio"
    chosen.mkdir()
    export = chosen / "clip.mp4"
    export.write_bytes(b"x")
    export.unlink()

    remove_empty_export_dirs(export, settings)

    assert chosen.is_dir()


def test_export_settings_are_validated(tmp_path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake-video-content")
    with TestClient(create_app(_settings(tmp_path))) as client:
        project_id = _create_project(client, _import_video(client, source)["id"])["project"]["id"]
        relative = client.patch(
            f"/api/v1/projects/{project_id}",
            json={"export_config": {"output_dir": "relative/folder"}},
        )
        too_long = client.patch(
            f"/api/v1/projects/{project_id}", json={"export_config": {"file_name": "x" * 200}}
        )
        valid = client.patch(
            f"/api/v1/projects/{project_id}",
            json={"export_config": {"file_name": "Final", "output_dir": str(tmp_path / "out")}},
        )

    assert relative.status_code == 400
    assert too_long.status_code == 400
    assert valid.status_code == 200
    assert valid.json()["project"]["export_config"]["file_name"] == "Final"
