from datetime import datetime, timezone

from sqlalchemy import (
    String,
    DateTime,
    Text,
    ForeignKey,
    Integer,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    __table_args__ = (
        Index(
            "ix_notifications_user_created_at",
            "user_id",
            "created_at"
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("notification_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # 保存通知内容快照，避免模板修改影响历史通知
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # pending / processing / success / failed
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )