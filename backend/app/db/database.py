from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import BACKEND_ROOT

logger = get_logger(__name__)

# Espera ante un bloqueo antes de dar error (el worker escribe mientras la UI consulta).
SQLITE_BUSY_TIMEOUT_MS = 30_000

Base = declarative_base()
engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None
_current_database_url: str | None = None


def _resolve_database_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        return database_url

    relative_path = database_url.removeprefix("sqlite:///")
    if relative_path == ":memory:":
        return database_url

    db_path = Path(relative_path)
    if not db_path.is_absolute():
        db_path = (BACKEND_ROOT / db_path).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def _sql_literal(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{str(value).replace("'", "''")}'"


def _build_add_column_sql(engine: Engine, table_name: str, column) -> str:
    column_type = column.type.compile(dialect=engine.dialect)
    default_sql = ""
    if column.default is not None and getattr(column.default, "is_scalar", False):
        default_sql = f" DEFAULT {_sql_literal(column.default.arg)}"
    elif column.server_default is not None and hasattr(column.server_default, "arg"):
        default_sql = f" DEFAULT {_sql_literal(column.server_default.arg)}"
    # SQLite rechaza ADD COLUMN NOT NULL sin DEFAULT: con un default calculado en Python
    # (o sin default) la columna se añade nullable en vez de impedir que la app arranque.
    nullable_sql = "" if column.nullable or not default_sql else " NOT NULL"
    if not column.nullable and not default_sql:
        logger.warning(
            "Column %s.%s added as nullable: NOT NULL needs a SQL default on existing rows.",
            table_name,
            column.name,
        )
    return (
        f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" '
        f"{column_type}{default_sql}{nullable_sql}"
    )


def _ensure_sqlite_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in inspector.get_table_names():
                continue
            existing_columns = {
                column_info["name"] for column_info in inspector.get_columns(table.name)
            }
            for column in table.columns:
                if column.primary_key or column.name in existing_columns:
                    continue
                connection.execute(text(_build_add_column_sql(engine, table.name, column)))
                existing_columns.add(column.name)


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        # WAL: lecturas (UI, SSE) y escrituras (worker) sin bloquearse entre sí.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def commit_progress(db: Session) -> bool:
    """Commit a progress-only update; a transient lock must not fail a long job.

    Returns False when the update was dropped (the next one will carry fresher values).
    State changes (failed, completed...) keep using a plain commit.
    """
    try:
        db.commit()
        return True
    except OperationalError as exc:
        message = str(exc).lower()
        if "locked" not in message and "busy" not in message:
            raise
        db.rollback()
        logger.warning("Progress update skipped, database busy: %s", exc)
        return False


def init_db(settings: Settings | None = None) -> None:
    global engine, SessionLocal, _current_database_url

    active_settings = settings or get_settings()
    resolved_database_url = _resolve_database_url(active_settings.database_url)

    if engine is not None and _current_database_url != resolved_database_url:
        engine.dispose()
        engine = None
        SessionLocal = None

    if engine is None:
        is_sqlite = resolved_database_url.startswith("sqlite")
        engine = create_engine(
            resolved_database_url,
            connect_args=(
                {"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000}
                if is_sqlite
                else {}
            ),
        )
        if is_sqlite and ":memory:" not in resolved_database_url:
            event.listen(engine, "connect", _configure_sqlite_connection)
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
        _current_database_url = resolved_database_url

    import app.db.models  # noqa: F401

    is_new_database = not inspect(engine).get_table_names()
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema(engine)

    from app.db.migrations import run_migrations, sqlite_file_from_url

    # Una base recién creada no tiene datos que proteger: sin copia de seguridad.
    run_migrations(
        engine,
        None if is_new_database else sqlite_file_from_url(resolved_database_url),
    )


def get_db() -> Generator[Session]:
    global SessionLocal

    if SessionLocal is None:
        init_db()

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
