from fastapi import APIRouter, Response, status

from app.routers.deps import CurrentUser, DbSession
from app.schemas.template import TemplateCreate, TemplateRead, TemplateUpdate
from app.services import template_service

router = APIRouter(prefix="/templates", tags=["通知模板"])


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateCreate, db: DbSession, current_user: CurrentUser
) -> TemplateRead:
    template = template_service.create_template(db, current_user.id, payload)
    return TemplateRead.model_validate(template)


@router.get("", response_model=list[TemplateRead])
def list_templates(db: DbSession, current_user: CurrentUser) -> list[TemplateRead]:
    templates = template_service.list_templates(db, current_user.id)
    return [TemplateRead.model_validate(item) for item in templates]


@router.get("/{template_id}", response_model=TemplateRead)
def get_template(
    template_id: int, db: DbSession, current_user: CurrentUser
) -> TemplateRead:
    template = template_service.get_owned_template(db, current_user.id, template_id)
    return TemplateRead.model_validate(template)


@router.put("/{template_id}", response_model=TemplateRead)
def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> TemplateRead:
    template = template_service.update_template(
        db, current_user.id, template_id, payload
    )
    return TemplateRead.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int, db: DbSession, current_user: CurrentUser
) -> Response:
    template_service.delete_template(db, current_user.id, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
