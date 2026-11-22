from typing import Annotated

from fastapi import APIRouter, Query, status

from app.routers.deps import CurrentUser, DbSession
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationCreate,
    NotificationPage,
    NotificationRead,
    NotificationStatus,
    UnreadCount,
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
    unread_only: bool = False,
) -> NotificationPage:
    items, total = notification_service.list_notifications(
        db, current_user.id, page, page_size, status, unread_only
    )
    return NotificationPage(
        **notification_service.build_page(items, total, page, page_size)
    )


@router.get("/unread-count", response_model=UnreadCount)
def get_unread_count(db: DbSession, current_user: CurrentUser) -> UnreadCount:
    return UnreadCount(
        unread_count=notification_service.unread_count(db, current_user.id)
    )


@router.post("/read-all", response_model=MarkAllReadResponse)
def read_all_notifications(
    db: DbSession, current_user: CurrentUser
) -> MarkAllReadResponse:
    return MarkAllReadResponse(
        updated=notification_service.mark_all_read(db, current_user.id)
    )


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(
    notification_id: int, db: DbSession, current_user: CurrentUser
) -> NotificationRead:
    notification = notification_service.get_owned_notification(
        db, current_user.id, notification_id
    )
    return NotificationRead.model_validate(notification)


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: int, db: DbSession, current_user: CurrentUser
) -> NotificationRead:
    notification = notification_service.mark_read(
        db, current_user.id, notification_id
    )
    return NotificationRead.model_validate(notification)
