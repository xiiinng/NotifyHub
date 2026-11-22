from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: DbSession,
) -> User:
    """当前用户只从 JWT 解析，绝不信任请求参数中的 user_id。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _unauthorized()

    subject = payload.get("sub")
    if payload.get("type") != "access" or not subject or not str(subject).isdigit():
        raise _unauthorized()

    user = db.get(User, int(subject))
    if user is None:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_it_support(current_user: CurrentUser) -> User:
    if current_user.role != UserRole.IT_SUPPORT.value:
        raise ForbiddenError("需要 IT 支持人员权限")
    return current_user


ItSupportUser = Annotated[User, Depends(require_it_support)]
