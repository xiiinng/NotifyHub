from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.user import UserDirectoryRead


class TicketCategory(StrEnum):
    HARDWARE = "hardware"
    NETWORK = "network"
    SOFTWARE = "software"
    ACCOUNT = "account"
    OTHER = "other"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    category: TicketCategory
    priority: TicketPriority

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("title", "description")
    @classmethod
    def ensure_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("工单标题和描述不能为空")
        return value


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    due_at: datetime | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_update(self) -> "TicketUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待修改字段")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"工单字段 {field} 不能为 null")
        return self


class TicketAssign(BaseModel):
    assignee_id: int = Field(gt=0)


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketNotificationSend(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)


class TicketCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("content")
    @classmethod
    def ensure_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("处理备注不能为空")
        return value


class TicketRead(BaseModel):
    id: int
    ticket_no: str
    creator: UserDirectoryRead
    assignee: UserDirectoryRead | None
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    due_at: datetime | None
    is_overdue: bool
    sla_remaining_seconds: int | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class TicketPage(BaseModel):
    items: list[TicketRead]
    total: int
    page: int
    page_size: int
    pages: int


class TicketHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    actor_id: int | None
    actor: UserDirectoryRead | None
    action: str
    old_value: str | None
    new_value: str | None
    created_at: datetime


class TicketCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author_id: int | None
    author: UserDirectoryRead | None
    content: str
    created_at: datetime


class AssigneeStat(BaseModel):
    assignee_id: int
    username: str
    total: int
    open: int


class TicketStats(BaseModel):
    total: int
    pending: int
    in_progress: int
    resolved: int
    closed: int
    overdue: int
    unassigned: int
    priorities: dict[str, int]
    assignees: list[AssigneeStat]
