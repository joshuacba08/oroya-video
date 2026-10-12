import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.errors import DatabaseMigrationFailedError
from app.db import database, migrations
from app.services import settings_service


def _settings(tmp_path: Path) -> Settings:
    storage = tmp_path / "storage"
    return Settings(
        storage_path=str(storage),
        database_url=f"sqlite:///{(storage / 'db' / 'oroya-video.sqlite').as_posix()}",
    )


def _db_file(settings: Settings) -> Path:
    return Path(settings.database_url.removeprefix("sqlite:///"))


@pytest.fixture
def isolated_db(tmp_path: Path):
    settings = _settings(tmp_path)
    yield settings
    if database.engine is not None:
        database.engine.dispose()


def test_existing_database_gets_baseline_version_and_pending_migrations(isolated_db) -> None:
    db_file = _db_file(isolated_db)
    db_file.parent.mkdir(parents=True)
    # Base "v0.3.0": tablas creadas pero sin tabla de versión.
    database.init_db(isolated_db)
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE schema_version")
    database.engine.dispose()

    database.init_db(isolated_db)

    connection = sqlite3.connect(db_file)
    try:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_version")]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()
    assert versions == [migrations.BASELINE_SCHEMA_VERSION, migrations.CURRENT_SCHEMA_VERSION]
    assert journal_mode == "wal"
    backups = list((db_file.parent / "backups").glob("*.sqlite"))
    assert len(backups) == 1


def test_up_to_date_database_is_not_migrated_or_backed_up_again(isolated_db) -> None:
    database.init_db(isolated_db)
    database.engine.dispose()
    database.init_db(isolated_db)

    assert migrations.get_schema_version(database.engine) == migrations.CURRENT_SCHEMA_VERSION
    assert not (_db_file(isolated_db).parent / "backups").exists()


def test_failed_migration_restores_the_backup(isolated_db, monkeypatch) -> None:
    database.init_db(isolated_db)
    engine = database.engine
    db_file = _db_file(isolated_db)
    version_before = migrations.CURRENT_SCHEMA_VERSION

    def broken_step(connection) -> None:
        connection.exec_driver_sql("CREATE TABLE half_done (id INTEGER)")
        raise RuntimeError("boom")

    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (*migrations.MIGRATIONS, migrations.Migration(99, "Broken", broken_step)),
    )
    monkeypatch.setattr(migrations, "CURRENT_SCHEMA_VERSION", 99)

    with pytest.raises(DatabaseMigrationFailedError):
        migrations.run_migrations(engine, db_file)

    connection = sqlite3.connect(db_file)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        version = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    finally:
        connection.close()
    assert "half_done" not in tables
    assert version == version_before


def test_not_null_column_without_sql_default_is_added_as_nullable() -> None:
    engine = create_engine("sqlite://")
    table = Table(
        "items",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("created_by", String, nullable=False, default=lambda: "app"),
        Column("kind", String, nullable=False, default="video"),
    )

    computed_default_sql = database._build_add_column_sql(engine, "items", table.c.created_by)
    scalar_default_sql = database._build_add_column_sql(engine, "items", table.c.kind)

    assert "NOT NULL" not in computed_default_sql
    assert scalar_default_sql.endswith("DEFAULT 'video' NOT NULL")


def test_commit_progress_skips_a_locked_database_but_not_other_errors() -> None:
    locked = MagicMock()
    locked.commit.side_effect = OperationalError("UPDATE", {}, Exception("database is locked"))
    broken = MagicMock()
    broken.commit.side_effect = OperationalError("UPDATE", {}, Exception("no such table"))

    assert database.commit_progress(locked) is False
    locked.rollback.assert_called_once()
    with pytest.raises(OperationalError):
        database.commit_progress(broken)


def test_corrupt_settings_file_is_kept_aside_and_defaults_are_used(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(settings_service, "corrupt_settings_backup", None)
    settings_file = settings_service._get_settings_file(settings)
    settings_file.write_text("{ not json", encoding="utf-8")

    loaded = settings_service._load_ui_settings(settings)

    assert loaded == settings_service.DEFAULT_SETTINGS_FILE
    assert not settings_file.exists()
    backup = settings_service.corrupt_settings_backup
    assert backup is not None and backup.read_text(encoding="utf-8") == "{ not json"


def test_invalid_saved_values_are_ignored(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings_service._get_settings_file(settings).write_text(
        json.dumps({"processing": {"realesrgan_tile_size": "abc", "ai_allow_cpu": False}}),
        encoding="utf-8",
    )
    default_tile = settings.realesrgan_tile_size

    settings_service.apply_persisted_settings(settings)

    assert settings.realesrgan_tile_size == default_tile
    assert settings.ai_allow_cpu is False


def test_settings_are_saved_atomically(tmp_path) -> None:
    settings = _settings(tmp_path)

    settings_service.set_frame_enhancer_engine("mock", settings)

    settings_file = settings_service._get_settings_file(settings)
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["processing"]["frame_enhancer_engine"] == "mock"
    assert not settings_file.with_name(f"{settings_file.name}.tmp").exists()
