import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.database import engine
from app.routers import auth, notifications, templates, tickets, users

setup_logging()
logger = logging.getLogger(__name__)

# JWT 密钥、ENVIRONMENT 合法性由 Settings 在导入时统一校验，缺失或不安全会直接启动失败

app = FastAPI(
    title=settings.app_name,
    description="基于 FastAPI + Celery 的企业 IT 工单管理与异步通知平台",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(templates.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(tickets.router, prefix=settings.api_prefix)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("数据库异常 path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "数据库操作失败，请稍后重试"},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常 path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


@app.get("/", tags=["系统"])
def root() -> dict:
    return {"message": "Welcome to NotifyHub"}


@app.get("/health", tags=["系统"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db", tags=["系统"])
def database_health() -> JSONResponse:
    try:
        with engine.connect() as connection:
            value = connection.execute(text("SELECT 1")).scalar()
    except SQLAlchemyError:
        logger.exception("数据库健康检查失败")
        return JSONResponse(
            status_code=503,
            content={"database": "unavailable"},
        )

    return JSONResponse(
        status_code=200,
        content={"database": "connected", "result": value},
    )
