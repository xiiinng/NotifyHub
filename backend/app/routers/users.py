from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.models.user import User
from app.routers.deps import CurrentUser, DbSession
from app.schemas.user import UserDirectoryRead

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/directory", response_model=list[UserDirectoryRead])
def list_user_directory(
    db: DbSession,
    current_user: CurrentUser,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[UserDirectoryRead]:
    """供站内通知选择接收人；不返回密码等敏感字段。"""
    stmt = select(User).where(User.id != current_user.id)
    keyword = q.strip()
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    stmt = stmt.order_by(User.username.asc(), User.id.asc()).limit(limit)
    return [
        UserDirectoryRead.model_validate(user)
        for user in db.scalars(stmt).all()
    ]
