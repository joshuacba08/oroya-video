from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import get_audit_log_path

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _serialize_entry(
    event_type: str,
    entity_type: str,
    entity_id: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "message": message,
            "metadata": metadata or {},
            "created_at": _utcnow().isoformat(),
        }
    )


def get_audit_log_file_path(settings: Settings | None = None) -> Path:
    audit_path = get_audit_log_path(settings)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    return audit_path


def record_audit_event(
    event_type: str,
    entity_type: str,
    entity_id: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    if not active_settings.audit_log_enabled:
        return

    audit_log_path = get_audit_log_file_path(active_settings)
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    audit_log_path.write_text("", encoding="utf-8") if not audit_log_path.exists() else None
    with audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(_serialize_entry(event_type, entity_type, entity_id, message, metadata) + "\n")
    logger.info("Audit event recorded: %s %s", event_type, entity_id)
