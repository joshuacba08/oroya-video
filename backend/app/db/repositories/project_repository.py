import json

from sqlalchemy.orm import Session

from app.db.models import Project
from app.schemas.project_schema import ProjectResponse


def create_project(db: Session, data: dict) -> Project:
    project = Project(**data)
    db.add(project)
    db.flush()
    db.refresh(project)
    return project


def get_project_by_id(db: Session, project_id: str) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


def list_projects(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> list[Project]:
    query = db.query(Project)
    if status:
        query = query.filter(Project.status == status)
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))

    return (
        query.order_by(Project.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_projects(
    db: Session,
    status: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(Project)
    if status:
        query = query.filter(Project.status == status)
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))

    return query.count()


def update_project(db: Session, project: Project, data: dict) -> Project:
    for key, value in data.items():
        setattr(project, key, value)
    db.flush()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.flush()


def to_project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        video_asset_id=project.video_asset_id,
        status=project.status,
        enhancement_config=_deserialize_json_object(project.enhancement_config_json),
        export_config=_deserialize_json_object(project.export_config_json),
        workspace_state=_deserialize_json_object(project.workspace_state_json),
        created_at=project.created_at,
        updated_at=project.updated_at,
        last_opened_at=project.last_opened_at,
    )


def _deserialize_json_object(raw_value: str | None) -> dict:
    if not raw_value:
        return {}

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    return value if isinstance(value, dict) else {}
