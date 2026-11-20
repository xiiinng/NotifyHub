from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=10000)

    @model_validator(mode="after")
    def reject_explicit_null(self) -> "TemplateUpdate":
        # 字段"未提供"不会进入 model_fields_set；只有显式传 null 才会
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"模板字段 {field} 不能为 null")
        return self


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str
    content: str
    created_at: datetime
