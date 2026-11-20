from typing import Annotated

from fastapi import APIRouter, Query, status

from app.routers.deps import CurrentUser, DbSession
from app.schemas.notification import (
    NotificationCreate,
    NotificationPage,
    NotificationRead,
    NotificationStatus,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["通知"])


@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationCreate, db: DbSession, current_user: CurrentUser
) -> NotificationRead:
    notification = notification_service.create_notification(
        db, current_user, payload
    )
    return NotificationRead.model_validate(notification)


@router.get("", response_model=NotificationPage)
def list_notifications(
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: NotificationStatus | None = None,
) -> NotificationPage:
    items, total = notification_service.list_notifications(
        db, current_user.id, page, page_size, status
    )
    return NotificationPage(
        **notification_service.build_page(items, total, page, page_size)
    )


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(
    notification_id: int, db: DbSession, current_user: CurrentUser
) -> NotificationRead:
    notification = notification_service.get_owned_notification(
        db, current_user.id, notification_id
    )
    return NotificationRead.model_validate(notification)
