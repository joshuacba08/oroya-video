from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import Settings, get_settings
from app.core.paths import BACKEND_ROOT

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
    nullable_sql = "" if column.nullable else " NOT NULL"
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


def init_db(settings: Settings | None = None) -> None:
    global engine, SessionLocal, _current_database_url

    active_settings = settings or get_settings()
    resolved_database_url = _resolve_database_url(active_settings.database_url)

    if engine is not None and _current_database_url != resolved_database_url:
        engine.dispose()
        engine = None
        SessionLocal = None

    if engine is None:
        engine = create_engine(
            resolved_database_url,
            connect_args={"check_same_thread": False},
        )
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
        _current_database_url = resolved_database_url

    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema(engine)


def get_db() -> Generator[Session]:
    global SessionLocal

    if SessionLocal is None:
        init_db()

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
