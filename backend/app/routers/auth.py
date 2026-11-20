from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import (
    LoginRateLimiter,
    LoginRateLimitExceeded,
    RateLimitUnavailable,
    get_client_ip,
    get_login_limiter,
)
from app.core.security import create_access_token
from app.routers.deps import CurrentUser, DbSession
from app.schemas.token import Token
from app.schemas.user import UserLogin, UserRead, UserRegister
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["认证"])
logger = get_logger(__name__)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: DbSession) -> UserRead:
    user = user_service.register_user(db, payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
def login(
    payload: UserLogin,
    request: Request,
    db: DbSession,
    limiter: Annotated[LoginRateLimiter, Depends(get_login_limiter)],
) -> Token:
    client_ip = get_client_ip(request)

    try:
        limiter.check(client_ip, payload.email)
    except LoginRateLimitExceeded as exc:
        logger.warning("登录触发限流 ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后再试",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except RateLimitUnavailable as exc:
        logger.exception("登录限流依赖 Redis 不可用")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="登录服务暂时不可用，请稍后重试",
        ) from exc

    user = user_service.authenticate_user(db, payload.email, payload.password)
    if user is None:
        try:
            limiter.record_failure(client_ip, payload.email)
        except RateLimitUnavailable as exc:
            logger.exception("记录登录失败次数时 Redis 不可用")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="登录服务暂时不可用，请稍后重试",
            ) from exc

        # 不区分“用户不存在”与“密码错误”，避免账号枚举
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 登录成功只清除邮箱维度，IP 维度的失败记录保留到窗口过期
    try:
        limiter.reset_email(payload.email)
    except RateLimitUnavailable:
        logger.warning("登录成功，但清理邮箱限流计数失败 ip=%s", client_ip)

    token = create_access_token(str(user.id))
    return Token(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
