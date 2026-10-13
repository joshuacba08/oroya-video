# REQ-024 - Datos y persistencia robustos

## Proyecto

Oroya Video

## Área

Backend / Base de datos

## Objetivo

Que una actualización de la app nunca deje la base de datos inutilizable y que un bloqueo
momentáneo de SQLite no haga fallar un job de horas.

## Implementación

- **Migraciones versionadas** (`app/db/migrations.py`): tabla `schema_version` y lista
  ordenada de pasos. Las bases sin tabla de versión (v0.3.0) se marcan como v1. Antes de
  aplicar pasos pendientes se copia la base con la API de backup de SQLite a `db/backups/`
  (se conservan 3); si un paso falla se restaura la copia y se lanza
  `database_migration_failed`. Una base recién creada no necesita copia. Una base de una
  versión más nueva de la app se acepta con un aviso en el log.
- **v2**: índices para la cola y el dashboard.
- **`ADD COLUMN` seguro**: una columna `NOT NULL` sin default SQL se añade nullable en vez de
  impedir el arranque (SQLite rechaza `NOT NULL` sin default en tablas con filas).
- **SQLite**: `journal_mode=WAL`, `busy_timeout=30000`, `synchronous=NORMAL` en cada conexión.
- **`commit_progress`**: las escrituras de progreso de todas las etapas toleran un
  "database is locked" (rollback y seguir); los cambios de estado siguen con `commit`.
  Los logs de progreso por frame pasan a DEBUG.
- **`settings.json`**: escritura atómica (temporal + `os.replace`) bajo un lock compartido por
  peticiones e instalación de IA; un archivo ilegible se aparta como `.corrupt-<fecha>` y se
  avisa en los warnings del sistema; los valores guardados se validan contra los tipos de
  `Settings` y los inválidos se ignoran.
- **Tests aislados**: `conftest.py` fija `STORAGE_PATH` a una carpeta temporal antes de
  importar la app; antes, `test_health` arrancaba sobre `backend/storage` del desarrollador.

## Verificación

- `tests/test_persistence.py`: baseline + migración con copia, sin copia si ya está al día,
  restauración ante un paso fallido, columna NOT NULL, `commit_progress`, settings corrupto,
  valores inválidos y escritura atómica.
- Migración sobre una copia de la base real de desarrollo (v0.3.0): v1 → v2, WAL activo.
