from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.routers.deps import CurrentUser, DbSession, ItSupportUser
from app.schemas.notification import NotificationRead
from app.schemas.ticket import (
    TicketAssign,
    TicketCategory,
    TicketCommentCreate,
    TicketCommentRead,
    TicketCreate,
    TicketHistoryRead,
    TicketNotificationSend,
    TicketPage,
    TicketPriority,
    TicketRead,
    TicketStats,
    TicketStatus,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.schemas.user import UserDirectoryRead
from app.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["工单"])


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> TicketRead:
    return ticket_service.create_ticket(db, current_user, payload)


@router.get("", response_model=TicketPage)
def list_tickets(
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    assignee_id: Annotated[int | None, Query(gt=0)] = None,
    q: Annotated[str, Query(max_length=200)] = "",
) -> TicketPage:
    return ticket_service.list_tickets(
        db,
        current_user,
        page=page,
        page_size=page_size,
        status=status_filter,
        priority=priority,
        category=category,
        assignee_id=assignee_id,
        keyword=q,
    )


@router.get("/stats", response_model=TicketStats)
def ticket_stats(db: DbSession, current_user: CurrentUser) -> TicketStats:
    return ticket_service.get_stats(db, current_user)


@router.get("/assignees", response_model=list[UserDirectoryRead])
def ticket_assignees(
    db: DbSession,
    _: ItSupportUser,
) -> list[UserDirectoryRead]:
    return ticket_service.list_assignees(db)


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket(
    ticket_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> TicketRead:
    return ticket_service.get_ticket(db, current_user, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> TicketRead:
    return ticket_service.update_ticket(db, current_user, ticket_id, payload)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    ticket_service.delete_ticket(db, current_user, ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{ticket_id}/assign", response_model=TicketRead)
def assign_ticket(
    ticket_id: int,
    payload: TicketAssign,
    db: DbSession,
    current_user: ItSupportUser,
) -> TicketRead:
    return ticket_service.assign_ticket(
        db, current_user, ticket_id, payload.assignee_id
    )


@router.patch("/{ticket_id}/status", response_model=TicketRead)
def change_ticket_status(
    ticket_id: int,
    payload: TicketStatusUpdate,
    db: DbSession,
    current_user: ItSupportUser,
) -> TicketRead:
    return ticket_service.change_status(
        db, current_user, ticket_id, payload.status
    )


@router.get("/{ticket_id}/history", response_model=list[TicketHistoryRead])
def ticket_history(
    ticket_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> list[TicketHistoryRead]:
    return ticket_service.list_history(db, current_user, ticket_id)


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentRead])
def ticket_comments(
    ticket_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> list[TicketCommentRead]:
    return ticket_service.list_comments(db, current_user, ticket_id)


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_ticket_comment(
    ticket_id: int,
    payload: TicketCommentCreate,
    db: DbSession,
    current_user: ItSupportUser,
) -> TicketCommentRead:
    return ticket_service.add_comment(db, current_user, ticket_id, payload)


@router.post("/{ticket_id}/notify", response_model=NotificationRead)
def notify_ticket_creator(
    ticket_id: int,
    payload: TicketNotificationSend,
    db: DbSession,
    current_user: ItSupportUser,
) -> NotificationRead:
    notification = ticket_service.send_ticket_message(
        db,
        current_user,
        ticket_id,
        payload.title,
        payload.content,
    )
    return NotificationRead.model_validate(notification)
