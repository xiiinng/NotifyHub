from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.user import UserRegister


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def register_user(db: Session, data: UserRegister) -> User:
    if get_user_by_email(db, data.email) is not None:
        raise ConflictError("该邮箱已被注册")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 并发注册时唯一约束兜底
        db.rollback()
        raise ConflictError("该邮箱已被注册")
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


def create_it_support_user(
    db: Session,
    *,
    email: str,
    username: str,
    password: str | None = None,
) -> tuple[User, bool]:
    """创建或提升 IT 支持账号。

    返回 (user, created)。已有用户只提升角色，不重置密码。
    该函数只应通过管理 CLI 调用，不暴露为公开 API。
    """
    existing = get_user_by_email(db, email)
    if existing is not None:
        created = False
        if existing.role != UserRole.IT_SUPPORT.value:
            existing.role = UserRole.IT_SUPPORT.value
            db.commit()
            db.refresh(existing)
        return existing, created

    if not password:
        raise ValueError("创建新的 IT 支持账号必须提供密码")

    user = User(
        username=username,
        email=email.lower(),
        hashed_password=hash_password(password),
        role=UserRole.IT_SUPPORT.value,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("该邮箱已被注册")
    db.refresh(user)
    return user, True
