import json

from sqlalchemy.orm import Session

from app.db.models import VideoAsset
from app.schemas.video_schema import VideoAssetResponse


def create_video_asset(db: Session, data: dict) -> VideoAsset:
    video_asset = VideoAsset(**data)
    db.add(video_asset)
    db.flush()
    db.refresh(video_asset)
    return video_asset


def get_video_asset_by_id(db: Session, video_id: str) -> VideoAsset | None:
    return db.query(VideoAsset).filter(VideoAsset.id == video_id).first()


def get_video_asset_by_fingerprint(db: Session, fingerprint: str) -> VideoAsset | None:
    return db.query(VideoAsset).filter(VideoAsset.fingerprint == fingerprint).first()


def list_video_assets(db: Session, limit: int = 50, offset: int = 0) -> list[VideoAsset]:
    return (
        db.query(VideoAsset)
        .order_by(VideoAsset.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_video_assets(db: Session) -> int:
    return db.query(VideoAsset).count()


def delete_video_asset(db: Session, video: VideoAsset) -> None:
    db.delete(video)
    db.flush()


def to_video_asset_response(video: VideoAsset) -> VideoAssetResponse:
    warnings = _deserialize_json_list(video.warnings_json)
    return VideoAssetResponse(
        id=video.id,
        source_path=video.source_path,
        stored_path=video.stored_path,
        source_mode=video.source_mode,
        file_name=video.file_name,
        file_extension=video.file_extension,
        file_size_bytes=video.file_size_bytes,
        file_size_mb=video.file_size_mb,
        format_name=video.format_name,
        duration_seconds=video.duration_seconds,
        duration_label=video.duration_label,
        bit_rate=video.bit_rate,
        video_codec=video.video_codec,
        video_codec_long_name=video.video_codec_long_name,
        width=video.width,
        height=video.height,
        resolution_label=video.resolution_label,
        fps=video.fps,
        pix_fmt=video.pix_fmt,
        video_profile=video.video_profile,
        video_bit_rate=video.video_bit_rate,
        has_audio=video.has_audio,
        audio_codec=video.audio_codec,
        audio_codec_long_name=video.audio_codec_long_name,
        audio_sample_rate=video.audio_sample_rate,
        audio_channels=video.audio_channels,
        audio_channel_layout=video.audio_channel_layout,
        audio_bit_rate=video.audio_bit_rate,
        warnings=warnings,
        created_at=video.created_at,
        updated_at=video.updated_at,
    )


def _deserialize_json_list(raw_value: str | None) -> list:
    if not raw_value:
        return []

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    return value if isinstance(value, list) else []
