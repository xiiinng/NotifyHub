from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.notification_template import NotificationTemplate
from app.schemas.template import TemplateCreate, TemplateUpdate

_NAME_CONSTRAINT = "uq_user_template_name"


def _is_template_name_conflict(exc: IntegrityError) -> bool:
    """仅当违反 (user_id, name) 唯一约束时返回 True。"""
    orig = exc.orig
    if not isinstance(orig, UniqueViolation):
        return False
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) if diag else None
    return constraint == _NAME_CONSTRAINT


def list_templates(db: Session, user_id: int) -> list[NotificationTemplate]:
    stmt = (
        select(NotificationTemplate)
        .where(NotificationTemplate.user_id == user_id)
        .order_by(NotificationTemplate.created_at.desc(), NotificationTemplate.id.desc())
    )
    return list(db.scalars(stmt).all())


def get_owned_template(
    db: Session, user_id: int, template_id: int
) -> NotificationTemplate:
    """按 id + user_id 查询，越权访问统一表现为 404，不泄露资源是否存在。"""
    template = db.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.id == template_id,
            NotificationTemplate.user_id == user_id,
        )
    )
    if template is None:
        raise NotFoundError("模板不存在")
    return template


def create_template(
    db: Session, user_id: int, data: TemplateCreate
) -> NotificationTemplate:
    template = NotificationTemplate(user_id=user_id, **data.model_dump())
    db.add(template)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_template_name_conflict(exc):
            raise ConflictError("模板名称已存在")
        raise
    db.refresh(template)
    return template


def update_template(
    db: Session, user_id: int, template_id: int, data: TemplateUpdate
) -> NotificationTemplate:
    template = get_owned_template(db, user_id, template_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(template, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_template_name_conflict(exc):
            raise ConflictError("模板名称已存在")
        raise
    db.refresh(template)
    return template


def delete_template(db: Session, user_id: int, template_id: int) -> None:
    template = get_owned_template(db, user_id, template_id)
    db.delete(template)
    db.commit()
