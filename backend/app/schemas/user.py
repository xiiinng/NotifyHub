import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_一-龥-]+$")


class UserRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value: object) -> object:
        # 先 strip，后续 Field 的 min_length/max_length 才会作用于最终值
        return value.strip() if isinstance(value, str) else value

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        # 显式再次校验最终长度，避免任何校验顺序造成的绕过
        if len(value) < 3:
            raise ValueError("用户名至少需要 3 个字符")
        if len(value) > 50:
            raise ValueError("用户名最多 50 个字符")
        if not _USERNAME_PATTERN.match(value):
            raise ValueError("用户名只能包含字母、数字、下划线、中文或连字符")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value):
            raise ValueError("密码必须包含至少一个字母")
        if not re.search(r"\d", value):
            raise ValueError("密码必须包含至少一个数字")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: UserRole
    created_at: datetime


class UserDirectoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: UserRole
