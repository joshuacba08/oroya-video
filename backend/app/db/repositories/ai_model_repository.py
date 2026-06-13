import json

from sqlalchemy.orm import Session

from app.db.models import AIModel
from app.schemas.ai_model_schema import AIModelResponse


def create_ai_model(db: Session, data: dict) -> AIModel:
    ai_model = AIModel(**data)
    db.add(ai_model)
    db.flush()
    db.refresh(ai_model)
    return ai_model


def get_ai_model_by_id(db: Session, model_id: str) -> AIModel | None:
    return db.query(AIModel).filter(AIModel.id == model_id).first()


def get_ai_model_by_slug(db: Session, slug: str) -> AIModel | None:
    return db.query(AIModel).filter(AIModel.slug == slug).first()


def list_ai_models(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
    status: str | None = None,
    installed: bool | None = None,
    enabled: bool | None = None,
) -> list[AIModel]:
    query = db.query(AIModel)
    if category:
        query = query.filter(AIModel.category == category)
    if status:
        query = query.filter(AIModel.status == status)
    if installed is not None:
        query = query.filter(AIModel.is_installed == installed)
    if enabled is not None:
        query = query.filter(AIModel.is_enabled == enabled)

    return (
        query.order_by(AIModel.category.asc(), AIModel.name.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_ai_models(
    db: Session,
    category: str | None = None,
    status: str | None = None,
    installed: bool | None = None,
    enabled: bool | None = None,
) -> int:
    query = db.query(AIModel)
    if category:
        query = query.filter(AIModel.category == category)
    if status:
        query = query.filter(AIModel.status == status)
    if installed is not None:
        query = query.filter(AIModel.is_installed == installed)
    if enabled is not None:
        query = query.filter(AIModel.is_enabled == enabled)

    return query.count()


def update_ai_model(db: Session, model: AIModel, data: dict) -> AIModel:
    for key, value in data.items():
        setattr(model, key, value)
    db.flush()
    db.refresh(model)
    return model


def delete_ai_model(db: Session, model: AIModel) -> None:
    db.delete(model)
    db.flush()


def to_ai_model_response(model: AIModel) -> AIModelResponse:
    return AIModelResponse(
        id=model.id,
        name=model.name,
        slug=model.slug,
        description=model.description,
        provider=model.provider,
        category=model.category,
        model_type=model.model_type,
        scale_factor=model.scale_factor,
        version=model.version,
        status=model.status,
        is_enabled=model.is_enabled,
        is_installed=model.is_installed,
        file_name=model.file_name,
        relative_path=model.relative_path,
        absolute_path=model.absolute_path,
        file_size_bytes=model.file_size_bytes,
        estimated_vram_mb=model.estimated_vram_mb,
        supports_gpu=model.supports_gpu,
        supports_cpu=model.supports_cpu,
        capabilities=_deserialize_json_object(model.capabilities_json),
        metadata=_deserialize_json_object(model.metadata_json),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _deserialize_json_object(raw_value: str | None) -> dict:
    if not raw_value:
        return {}

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    return value if isinstance(value, dict) else {}
