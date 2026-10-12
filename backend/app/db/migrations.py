"""Versioned schema migrations for the local SQLite database.

`create_all` creates missing tables and `_ensure_sqlite_schema` adds missing nullable
columns; anything else (data backfills, renames, indexes) goes here as a numbered step.
Before applying pending steps the database file is backed up, and restored if a step fails,
so a broken upgrade never leaves a half-migrated database behind.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.core.errors import DatabaseMigrationFailedError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Esquema de la v0.3.0: las bases sin tabla de versión se marcan con este número.
BASELINE_SCHEMA_VERSION = 1
BACKUPS_TO_KEEP = 3


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    apply: Callable[[Connection], None]


def _add_query_indexes(connection: Connection) -> None:
    # Índices usados por la cola y el dashboard (consultas por estado y fecha).
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_processing_jobs_status_created "
            "ON processing_jobs (status, created_at)"
        )
    )
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_projects_updated_at ON projects (updated_at)")
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(2, "Indexes for queue and dashboard queries", _add_query_indexes),
)

CURRENT_SCHEMA_VERSION = max(
    [BASELINE_SCHEMA_VERSION, *(migration.version for migration in MIGRATIONS)]
)


def _ensure_version_table(connection: Connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER NOT NULL, description TEXT, applied_at TEXT NOT NULL)"
        )
    )


def get_schema_version(engine: Engine) -> int | None:
    with engine.connect() as connection:
        _ensure_version_table(connection)
        connection.commit()
        value = connection.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
    return int(value) if value is not None else None


def _record_version(connection: Connection, version: int, description: str) -> None:
    connection.execute(
        text(
            "INSERT INTO schema_version (version, description, applied_at) "
            "VALUES (:version, :description, :applied_at)"
        ),
        {
            "version": version,
            "description": description,
            "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        },
    )


def sqlite_file_from_url(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path == ":memory:":
        return None
    return Path(raw_path)


def backup_database(db_path: Path, from_version: int) -> Path:
    """Consistent copy through the SQLite backup API (safe with WAL)."""
    backups_dir = db_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = backups_dir / f"{db_path.stem}-v{from_version}-{stamp}{db_path.suffix}"
    source = sqlite3.connect(str(db_path))
    try:
        target = sqlite3.connect(str(backup_path))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    backups = sorted(backups_dir.glob(f"{db_path.stem}-v*{db_path.suffix}"))
    for old_backup in backups[:-BACKUPS_TO_KEEP]:
        old_backup.unlink(missing_ok=True)
    return backup_path


def _restore_database(engine: Engine, db_path: Path, backup_path: Path) -> None:
    engine.dispose()
    for suffix in ("-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    shutil.copy2(backup_path, db_path)


def run_migrations(engine: Engine, db_path: Path | None) -> int:
    """Apply pending migrations and return the resulting schema version."""
    current = get_schema_version(engine)
    if current is None:
        with engine.begin() as connection:
            _record_version(connection, BASELINE_SCHEMA_VERSION, "Baseline (v0.3.0 schema)")
        current = BASELINE_SCHEMA_VERSION

    if current > CURRENT_SCHEMA_VERSION:
        # Base creada por una versión más nueva de la app: se sigue (SQLite tolera columnas
        # extra), pero queda registrado por si aparece algún fallo raro.
        logger.warning(
            "Database schema v%s is newer than this app (v%s).", current, CURRENT_SCHEMA_VERSION
        )
        return current

    pending = [migration for migration in MIGRATIONS if migration.version > current]
    if not pending:
        return current

    backup_path = backup_database(db_path, current) if db_path and db_path.is_file() else None
    logger.info(
        "Migrating database schema v%s -> v%s (backup: %s)",
        current,
        pending[-1].version,
        backup_path,
    )
    try:
        for migration in pending:
            with engine.begin() as connection:
                migration.apply(connection)
                _record_version(connection, migration.version, migration.description)
            logger.info("Applied migration v%s: %s", migration.version, migration.description)
    except Exception as exc:
        logger.exception("Database migration failed")
        if backup_path is not None and db_path is not None:
            _restore_database(engine, db_path, backup_path)
            logger.error("Database restored from backup %s", backup_path)
        raise DatabaseMigrationFailedError() from exc
    return pending[-1].version
