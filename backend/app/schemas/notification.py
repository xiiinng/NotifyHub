from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NotificationStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class NotificationCreate(BaseModel):
    template_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    # 不传时保持旧行为：发给自己；传入时必须是其他有效用户。
    recipient_user_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_source(self) -> "NotificationCreate":
        if self.template_id is not None:
            if self.title is not None or self.content is not None:
                raise ValueError("使用模板创建通知时不能再传入 title 或 content")
            return self
        if not self.title or not self.content:
            raise ValueError("必须提供 template_id，或者同时提供 title 和 content")
        return self


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    sender_id: int | None
    template_id: int | None
    title: str
    content: str
    status: NotificationStatus
    retry_count: int
    error_message: str | None
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    total: int
    page: int
    page_size: int
    pages: int


class UnreadCount(BaseModel):
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated: int
