import json
import secrets
from datetime import datetime, timedelta
from math import ceil

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.models.notification import Notification
from app.models.ticket import (
    Ticket,
    TicketComment,
    TicketHistory,
    TicketNotificationEvent,
)
from app.models.user import User, UserRole
from app.schemas.ticket import (
    AssigneeStat,
    TicketCategory,
    TicketCommentCreate,
    TicketCommentRead,
    TicketCreate,
    TicketHistoryRead,
    TicketPage,
    TicketPriority,
    TicketRead,
    TicketStats,
    TicketStatus,
    TicketUpdate,
)
from app.schemas.user import UserDirectoryRead
from app.services import notification_service, sla_service, ticket_notification_service

logger = get_logger(__name__)

OPEN_STATUSES = {
    TicketStatus.PENDING.value,
    TicketStatus.IN_PROGRESS.value,
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    TicketStatus.PENDING.value: {
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
    },
    TicketStatus.IN_PROGRESS.value: {TicketStatus.RESOLVED.value},
    TicketStatus.RESOLVED.value: {
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.CLOSED.value: set(),
}

EMPLOYEE_EDITABLE_FIELDS = {"title", "description", "category"}
SUPPORT_EDITABLE_FIELDS = {
    "title",
    "description",
    "category",
    "priority",
    "due_at",
}


def _new_ticket_no(now: datetime) -> str:
    return f"TK-{now.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"


def _ticket_query():
    return (
        select(Ticket)
        .where(Ticket.deleted_at.is_(None))
        .options(
            joinedload(Ticket.creator),
            joinedload(Ticket.assignee),
        )
    )


def _is_support(user: User) -> bool:
    return user.role == UserRole.IT_SUPPORT.value


def get_accessible_ticket(db: Session, user: User, ticket_id: int) -> Ticket:
    ticket = db.scalar(_ticket_query().where(Ticket.id == ticket_id))
    if ticket is None:
        raise NotFoundError("工单不存在")
    if not _is_support(user) and ticket.user_id != user.id:
        raise NotFoundError("工单不存在")
    return ticket


def get_accessible_ticket_for_update(
    db: Session, user: User, ticket_id: int
) -> Ticket:
    """锁定工单行，串行化状态/分配/删除等关键修改。"""
    ticket = db.scalar(
        select(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.deleted_at.is_(None),
        )
        .with_for_update(of=Ticket)
    )
    if ticket is None:
        raise NotFoundError("工单不存在")
    if not _is_support(user) and ticket.user_id != user.id:
        raise NotFoundError("工单不存在")
    return ticket


def _history(
    db: Session,
    *,
    ticket: Ticket,
    actor: User,
    action: str,
    old_value: str | None = None,
    new_value: str | None = None,
) -> TicketHistory:
    item = TicketHistory(
        ticket_id=ticket.id,
        actor_id=actor.id,
        action=action,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(item)
    db.flush()
    return item


def _serialize(ticket: Ticket, now: datetime | None = None) -> TicketRead:
    now = now or sla_service.utcnow()
    creator = UserDirectoryRead.model_validate(ticket.creator)
    assignee = (
        UserDirectoryRead.model_validate(ticket.assignee)
        if ticket.assignee
        else None
    )
    return TicketRead(
        id=ticket.id,
        ticket_no=ticket.ticket_no,
        creator=creator,
        assignee=assignee,
        title=ticket.title,
        description=ticket.description,
        category=TicketCategory(ticket.category),
        priority=TicketPriority(ticket.priority),
        status=TicketStatus(ticket.status),
        due_at=ticket.due_at,
        is_overdue=sla_service.is_overdue(ticket.status, ticket.due_at, now),
        sla_remaining_seconds=sla_service.sla_remaining_seconds(
            ticket.due_at, now
        ),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
    )


def create_ticket(
    db: Session,
    user: User,
    data: TicketCreate,
    *,
    now: datetime | None = None,
) -> TicketRead:
    now = sla_service.ensure_utc(now or sla_service.utcnow())
    ticket = Ticket(
        ticket_no=_new_ticket_no(now),
        user_id=user.id,
        title=data.title,
        description=data.description,
        category=data.category.value,
        priority=data.priority.value,
        status=TicketStatus.PENDING.value,
        due_at=sla_service.calculate_due_at(data.priority.value, now),
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()

    _history(
        db,
        ticket=ticket,
        actor=user,
        action="created",
        new_value=TicketStatus.PENDING.value,
    )
    notification = ticket_notification_service.notify_ticket_event(
        db,
        ticket=ticket,
        event_key=f"ticket:{ticket.id}:created",
        event_type="ticket_created",
        recipient_user_id=ticket.user_id,
        title="工单已创建",
        content=(
            f"工单 {ticket.ticket_no}「{ticket.title}」已创建，"
            f"优先级 {ticket.priority}，状态 pending。"
        ),
        actor=user,
    )
    db.commit()
    db.refresh(ticket)
    if notification is not None:
        notification_service.dispatch_notifications(db, [notification.id])
        db.refresh(ticket)
    return _serialize(ticket, now)


def list_tickets(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    assignee_id: int | None = None,
    keyword: str = "",
) -> TicketPage:
    filters = [Ticket.deleted_at.is_(None)]
    if not _is_support(user):
        filters.append(Ticket.user_id == user.id)
    if status is not None:
        filters.append(Ticket.status == status.value)
    if priority is not None:
        filters.append(Ticket.priority == priority.value)
    if category is not None:
        filters.append(Ticket.category == category.value)
    if assignee_id is not None:
        filters.append(Ticket.assignee_id == assignee_id)
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        filters.append(
            or_(
                Ticket.title.ilike(pattern),
                Ticket.description.ilike(pattern),
                Ticket.ticket_no.ilike(pattern),
            )
        )

    total = db.scalar(
        select(func.count()).select_from(Ticket).where(*filters)
    ) or 0
    items = list(
        db.scalars(
            _ticket_query()
            .where(*filters)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    now = sla_service.utcnow()
    return TicketPage(
        items=[_serialize(item, now) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


def get_ticket(db: Session, user: User, ticket_id: int) -> TicketRead:
    return _serialize(get_accessible_ticket(db, user, ticket_id))


def update_ticket(
    db: Session,
    user: User,
    ticket_id: int,
    data: TicketUpdate,
) -> TicketRead:
    ticket = get_accessible_ticket_for_update(db, user, ticket_id)
    if ticket.status == TicketStatus.CLOSED.value:
        raise ConflictError("已关闭工单不能修改")

    changes = data.model_dump(exclude_unset=True)
    allowed = SUPPORT_EDITABLE_FIELDS if _is_support(user) else EMPLOYEE_EDITABLE_FIELDS
    forbidden = set(changes) - allowed
    if forbidden:
        raise ForbiddenError("当前角色不能修改这些工单字段")

    old_priority = ticket.priority
    old_due_at = ticket.due_at
    old_values: dict[str, str] = {}
    new_values: dict[str, str] = {}

    if "title" in changes:
        old_values["title"] = ticket.title
        new_values["title"] = changes["title"]
        ticket.title = changes["title"]
    if "description" in changes:
        old_values["description"] = ticket.description
        new_values["description"] = changes["description"]
        ticket.description = changes["description"]
    if "category" in changes:
        old_values["category"] = ticket.category
        new_values["category"] = changes["category"].value
        ticket.category = changes["category"].value
    if "priority" in changes:
        ticket.priority = changes["priority"].value
        if not ticket.sla_manually_adjusted:
            ticket.due_at = sla_service.calculate_due_at(
                ticket.priority, ticket.created_at
            )
    if "due_at" in changes:
        if not _is_support(user):
            raise ForbiddenError("只有 IT 支持人员可以调整截止时间")
        new_due_at = sla_service.ensure_utc(changes["due_at"])
        if new_due_at != old_due_at:
            ticket.due_at = new_due_at
            ticket.sla_manually_adjusted = True

    if new_values:
        _history(
            db,
            ticket=ticket,
            actor=user,
            action="updated",
            old_value=json.dumps(old_values, ensure_ascii=False),
            new_value=json.dumps(new_values, ensure_ascii=False),
        )
    if ticket.priority != old_priority:
        _history(
            db,
            ticket=ticket,
            actor=user,
            action="priority_changed",
            old_value=old_priority,
            new_value=ticket.priority,
        )
    if ticket.due_at != old_due_at:
        _history(
            db,
            ticket=ticket,
            actor=user,
            action="due_date_changed",
            old_value=old_due_at.isoformat() if old_due_at else None,
            new_value=ticket.due_at.isoformat() if ticket.due_at else None,
        )

    db.commit()
    db.refresh(ticket)
    return _serialize(ticket)


def delete_ticket(db: Session, user: User, ticket_id: int) -> None:
    ticket = get_accessible_ticket_for_update(db, user, ticket_id)
    if ticket.status != TicketStatus.PENDING.value or ticket.assignee_id is not None:
        raise ConflictError("只有未分配且待处理的工单可以删除")
    ticket.deleted_at = sla_service.utcnow()
    _history(
        db,
        ticket=ticket,
        actor=user,
        action="deleted",
        old_value=None,
        new_value="soft-deleted",
    )
    db.commit()


def assign_ticket(
    db: Session,
    user: User,
    ticket_id: int,
    assignee_id: int,
) -> TicketRead:
    if not _is_support(user):
        raise ForbiddenError("只有 IT 支持人员可以分配工单")
    ticket = get_accessible_ticket_for_update(db, user, ticket_id)
    if ticket.status == TicketStatus.CLOSED.value:
        raise ConflictError("已关闭工单不能分配")

    assignee = db.get(User, assignee_id)
    if assignee is None or assignee.role != UserRole.IT_SUPPORT.value:
        raise ConflictError("只能分配给有效的 IT 支持人员")
    if ticket.assignee_id == assignee.id:
        raise ConflictError("工单已经分配给该处理人")

    old_assignee_id = ticket.assignee_id
    ticket.assignee_id = assignee.id
    history = _history(
        db,
        ticket=ticket,
        actor=user,
        action="reassigned" if old_assignee_id else "assigned",
        old_value=str(old_assignee_id) if old_assignee_id else None,
        new_value=str(assignee.id),
    )
    notification = ticket_notification_service.notify_ticket_event(
        db,
        ticket=ticket,
        event_key=f"ticket:{ticket.id}:assigned:{history.id}",
        event_type="ticket_assigned",
        recipient_user_id=ticket.user_id,
        title="工单已分配",
        content=(
            f"工单 {ticket.ticket_no}「{ticket.title}」"
            f"已分配给 {assignee.username}。"
        ),
        actor=user,
    )
    db.commit()
    db.refresh(ticket)
    if notification is not None:
        notification_service.dispatch_notifications(db, [notification.id])
        db.refresh(ticket)
    return _serialize(ticket)


def change_status(
    db: Session,
    user: User,
    ticket_id: int,
    new_status: TicketStatus,
) -> TicketRead:
    if not _is_support(user):
        raise ForbiddenError("只有 IT 支持人员可以变更工单状态")
    ticket = get_accessible_ticket_for_update(db, user, ticket_id)
    old_status = ticket.status
    target = new_status.value
    if target not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise ConflictError(f"不允许的状态转换：{old_status} -> {target}")

    now = sla_service.utcnow()
    ticket.status = target
    if target == TicketStatus.RESOLVED.value:
        ticket.resolved_at = now
    elif target == TicketStatus.IN_PROGRESS.value and old_status == TicketStatus.RESOLVED.value:
        ticket.resolved_at = None
    elif target == TicketStatus.CLOSED.value:
        ticket.closed_at = now

    action = {
        TicketStatus.RESOLVED.value: "resolved",
        TicketStatus.CLOSED.value: "closed",
    }.get(target, "status_changed")
    history = _history(
        db,
        ticket=ticket,
        actor=user,
        action=action,
        old_value=old_status,
        new_value=target,
    )
    notification = ticket_notification_service.notify_ticket_event(
        db,
        ticket=ticket,
        event_key=f"ticket:{ticket.id}:status:{history.id}",
        event_type="ticket_status_changed",
        recipient_user_id=ticket.user_id,
        title="工单状态已更新",
        content=(
            f"工单 {ticket.ticket_no}「{ticket.title}」状态已从 "
            f"{old_status} 变为 {target}。"
        ),
        actor=user,
    )
    db.commit()
    db.refresh(ticket)
    if notification is not None:
        notification_service.dispatch_notifications(db, [notification.id])
        db.refresh(ticket)
    return _serialize(ticket)


def add_comment(
    db: Session,
    user: User,
    ticket_id: int,
    data: TicketCommentCreate,
) -> TicketCommentRead:
    if not _is_support(user):
        raise ForbiddenError("只有 IT 支持人员可以添加处理备注")
    ticket = get_accessible_ticket_for_update(db, user, ticket_id)
    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=user.id,
        content=data.content,
    )
    db.add(comment)
    db.flush()
    notification = ticket_notification_service.notify_ticket_event(
        db,
        ticket=ticket,
        event_key=f"ticket:{ticket.id}:comment:{comment.id}",
        event_type="ticket_comment_added",
        recipient_user_id=ticket.user_id,
        title="工单有新的处理备注",
        content=(
            f"工单 {ticket.ticket_no}「{ticket.title}」新增处理备注："
            f"{comment.content[:500]}"
        ),
        actor=user,
    )
    db.commit()
    db.refresh(comment)
    if notification is not None:
        notification_service.dispatch_notifications(db, [notification.id])
        db.refresh(comment)
    return TicketCommentRead.model_validate(comment)


def list_history(
    db: Session, user: User, ticket_id: int
) -> list[TicketHistoryRead]:
    get_accessible_ticket(db, user, ticket_id)
    items = db.scalars(
        select(TicketHistory)
        .options(joinedload(TicketHistory.actor))
        .where(TicketHistory.ticket_id == ticket_id)
        .order_by(TicketHistory.created_at.asc(), TicketHistory.id.asc())
    ).all()
    return [TicketHistoryRead.model_validate(item) for item in items]


def list_comments(
    db: Session, user: User, ticket_id: int
) -> list[TicketCommentRead]:
    get_accessible_ticket(db, user, ticket_id)
    items = db.scalars(
        select(TicketComment)
        .options(joinedload(TicketComment.author))
        .where(TicketComment.ticket_id == ticket_id)
        .order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
    ).all()
    return [TicketCommentRead.model_validate(item) for item in items]


def list_assignees(db: Session) -> list[UserDirectoryRead]:
    users = db.scalars(
        select(User)
        .where(User.role == UserRole.IT_SUPPORT.value)
        .order_by(User.username.asc(), User.id.asc())
    ).all()
    return [UserDirectoryRead.model_validate(user) for user in users]


def get_stats(
    db: Session,
    user: User,
    *,
    now: datetime | None = None,
) -> TicketStats:
    now = sla_service.ensure_utc(now or sla_service.utcnow())
    filters = [Ticket.deleted_at.is_(None)]
    if not _is_support(user):
        filters.append(Ticket.user_id == user.id)

    status_counts = dict(
        db.execute(
            select(Ticket.status, func.count())
            .where(*filters)
            .group_by(Ticket.status)
        ).all()
    )
    priority_counts = dict(
        db.execute(
            select(Ticket.priority, func.count())
            .where(*filters)
            .group_by(Ticket.priority)
        ).all()
    )
    total = db.scalar(
        select(func.count()).select_from(Ticket).where(*filters)
    ) or 0
    overdue = db.scalar(
        select(func.count())
        .select_from(Ticket)
        .where(
            *filters,
            Ticket.status.in_(OPEN_STATUSES),
            Ticket.due_at.isnot(None),
            Ticket.due_at < now,
        )
    ) or 0
    unassigned = db.scalar(
        select(func.count())
        .select_from(Ticket)
        .where(
            *filters,
            Ticket.status.in_(OPEN_STATUSES),
            Ticket.assignee_id.is_(None),
        )
    ) or 0

    assignees: list[AssigneeStat] = []
    if _is_support(user):
        rows = db.execute(
            select(
                Ticket.assignee_id,
                User.username,
                func.count(Ticket.id),
                func.sum(
                    case((Ticket.status.in_(OPEN_STATUSES), 1), else_=0)
                ),
            )
            .join(User, Ticket.assignee_id == User.id)
            .where(
                Ticket.assignee_id.isnot(None),
                Ticket.deleted_at.is_(None),
            )
            .group_by(Ticket.assignee_id, User.username)
            .order_by(User.username.asc())
        ).all()
        assignees = [
            AssigneeStat(
                assignee_id=row[0],
                username=row[1],
                total=row[2],
                open=int(row[3] or 0),
            )
            for row in rows
        ]

    return TicketStats(
        total=total,
        pending=status_counts.get(TicketStatus.PENDING.value, 0),
        in_progress=status_counts.get(TicketStatus.IN_PROGRESS.value, 0),
        resolved=status_counts.get(TicketStatus.RESOLVED.value, 0),
        closed=status_counts.get(TicketStatus.CLOSED.value, 0),
        overdue=overdue,
        unassigned=unassigned,
        priorities={
            priority.value: priority_counts.get(priority.value, 0)
            for priority in TicketPriority
        },
        assignees=assignees,
    )


def send_ticket_message(
    db: Session,
    user: User,
    ticket_id: int,
    title: str,
    content: str,
) -> Notification:
    if not _is_support(user):
        raise ForbiddenError("只有 IT 支持人员可以向工单相关员工发送通知")
    ticket = get_accessible_ticket_for_update(db, user, ticket_id)
    notification = ticket_notification_service.notify_ticket_event(
        db,
        ticket=ticket,
        event_key=f"ticket:{ticket.id}:manual:{secrets.token_hex(8)}",
        event_type="ticket_manual_message",
        recipient_user_id=ticket.user_id,
        title=title,
        content=content,
        actor=user,
    )
    if notification is None:
        raise ConflictError("通知发送失败")
    db.commit()
    db.refresh(notification)
    notification_service.dispatch_notifications(db, [notification.id])
    db.refresh(notification)
    return notification


def _sla_event_exists(key_expression):
    return (
        select(TicketNotificationEvent.id)
        .where(
            TicketNotificationEvent.ticket_id == Ticket.id,
            TicketNotificationEvent.event_key == key_expression,
        )
        .exists()
    )


def _process_sla_event(
    db: Session,
    *,
    ticket_id: int,
    now: datetime,
    window_end: datetime,
    event_type: str,
) -> Notification | None:
    """锁定并再次确认工单状态后创建 SLA 通知。"""
    ticket = db.scalar(
        select(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.deleted_at.is_(None),
        )
        .with_for_update(of=Ticket)
    )
    if ticket is None or ticket.status not in OPEN_STATUSES or ticket.due_at is None:
        db.rollback()
        return None

    due_at = sla_service.ensure_utc(ticket.due_at)
    if event_type == "sla_overdue":
        if due_at > now:
            db.rollback()
            return None
        event_key = f"ticket:{ticket.id}:sla_overdue"
        title = "工单已超时"
        content = f"工单 {ticket.ticket_no}「{ticket.title}」已超过 SLA 截止时间。"
    else:
        if not (now < due_at <= window_end):
            db.rollback()
            return None
        event_key = f"ticket:{ticket.id}:sla_due_soon"
        title = "工单即将到期"
        content = (
            f"工单 {ticket.ticket_no}「{ticket.title}」将在 "
            f"{max(int((due_at - now).total_seconds() // 60), 0)} 分钟内到期。"
        )

    notification = ticket_notification_service.notify_ticket_event(
        db,
        ticket=ticket,
        event_key=event_key,
        event_type=event_type,
        recipient_user_id=ticket.user_id,
        title=title,
        content=content,
    )
    if notification is None:
        db.rollback()
        return None

    db.commit()
    notification_service.dispatch_notifications(db, [notification.id])
    return notification


def check_ticket_sla(
    db: Session,
    *,
    now: datetime | None = None,
    window_minutes: int = 30,
) -> dict[str, int]:
    now = sla_service.ensure_utc(now or sla_service.utcnow())
    window_end = now + timedelta(minutes=window_minutes)
    base_filters = [
        Ticket.deleted_at.is_(None),
        Ticket.status.in_(OPEN_STATUSES),
        Ticket.due_at.isnot(None),
    ]

    # 计数保持原有语义：统计当前窗口内的工单，而不是只统计本次新发通知。
    due_soon_count = (
        db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(
                *base_filters,
                Ticket.due_at > now,
                Ticket.due_at <= window_end,
            )
        )
        or 0
    )
    overdue_count = (
        db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(
                *base_filters,
                Ticket.due_at <= now,
            )
        )
        or 0
    )

    due_soon_key = func.concat(
        "ticket:", cast(Ticket.id, String), ":sla_due_soon"
    )
    overdue_key = func.concat(
        "ticket:", cast(Ticket.id, String), ":sla_overdue"
    )

    due_soon_ids = db.scalars(
        select(Ticket.id)
        .where(
            *base_filters,
            Ticket.due_at > now,
            Ticket.due_at <= window_end,
            ~_sla_event_exists(due_soon_key),
        )
        .order_by(Ticket.due_at.asc(), Ticket.id.asc())
        .limit(200)
    ).all()
    overdue_ids = db.scalars(
        select(Ticket.id)
        .where(
            *base_filters,
            Ticket.due_at <= now,
            ~_sla_event_exists(overdue_key),
        )
        .order_by(Ticket.due_at.asc(), Ticket.id.asc())
        .limit(200)
    ).all()

    processed = 0
    for ticket_id in due_soon_ids:
        if _process_sla_event(
            db,
            ticket_id=ticket_id,
            now=now,
            window_end=window_end,
            event_type="sla_due_soon",
        ):
            processed += 1
    for ticket_id in overdue_ids:
        if _process_sla_event(
            db,
            ticket_id=ticket_id,
            now=now,
            window_end=window_end,
            event_type="sla_overdue",
        ):
            processed += 1

    logger.info(
        "SLA 检查完成 due_soon=%s overdue=%s processed=%s",
        due_soon_count,
        overdue_count,
        processed,
    )
    return {
        "due_soon": due_soon_count,
        "overdue": overdue_count,
        "scanned": due_soon_count + overdue_count,
    }
