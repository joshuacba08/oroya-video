from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ExportAsset
from app.schemas.export_schema import ExportAssetResponse


def create_export_asset(db: Session, data: dict) -> ExportAsset:
    export_asset = ExportAsset(**data)
    db.add(export_asset)
    db.flush()
    db.refresh(export_asset)
    return export_asset


def get_export_by_id(db: Session, export_id: str) -> ExportAsset | None:
    return db.query(ExportAsset).filter(ExportAsset.id == export_id).first()


def get_exports_by_job_id(db: Session, job_id: str) -> list[ExportAsset]:
    return (
        db.query(ExportAsset)
        .filter(ExportAsset.job_id == job_id)
        .order_by(ExportAsset.created_at.desc())
        .all()
    )


def list_exports(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    project_id: str | None = None,
    job_id: str | None = None,
) -> list[ExportAsset]:
    query = db.query(ExportAsset)
    if project_id:
        query = query.filter(ExportAsset.project_id == project_id)
    if job_id:
        query = query.filter(ExportAsset.job_id == job_id)
    return (
        query.order_by(ExportAsset.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_exports(
    db: Session,
    project_id: str | None = None,
    job_id: str | None = None,
) -> int:
    query = db.query(ExportAsset)
    if project_id:
        query = query.filter(ExportAsset.project_id == project_id)
    if job_id:
        query = query.filter(ExportAsset.job_id == job_id)
    return query.count()


def delete_export_asset(db: Session, export_asset: ExportAsset) -> None:
    db.delete(export_asset)
    db.flush()


def to_export_asset_response(export_asset: ExportAsset) -> ExportAssetResponse:
    return ExportAssetResponse(
        id=export_asset.id,
        project_id=export_asset.project_id,
        job_id=export_asset.job_id,
        video_asset_id=export_asset.video_asset_id,
        file_path=export_asset.file_path,
        file_name=export_asset.file_name,
        file_extension=export_asset.file_extension,
        file_size_bytes=export_asset.file_size_bytes,
        file_size_mb=export_asset.file_size_mb,
        format=export_asset.format,
        video_codec=export_asset.video_codec,
        audio_codec=export_asset.audio_codec,
        has_audio=export_asset.has_audio,
        audio_strategy=export_asset.audio_strategy,
        resolution_label=export_asset.resolution_label,
        width=export_asset.width,
        height=export_asset.height,
        fps=export_asset.fps,
        duration_seconds=export_asset.duration_seconds,
        duration_label=export_asset.duration_label,
        created_at=export_asset.created_at,
        updated_at=export_asset.updated_at,
    )
