from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import CheckConstraint, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(StrEnum):
    EMPLOYEE = "employee"
    IT_SUPPORT = "it_support"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('employee', 'it_support')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    role: Mapped[str] = mapped_column(
        String(20),
        default=UserRole.EMPLOYEE.value,
        server_default=UserRole.EMPLOYEE.value,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )