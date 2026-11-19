"""Модели данных запросов и ответов (Pydantic v2).

Эти модели задают контракт REST API: FastAPI по ним автоматически проверяет
входные данные и строит документацию OpenAPI/Swagger (тема варианта 11 —
«REST API с документацией OpenAPI»).
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

# Простая проверка формата e-mail без внешней зависимости email-validator.
# Полную валидацию почты выполняет также бизнес-логика (service.register_user).
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

T = TypeVar("T")


# --- Аутентификация --------------------------------------------------------
class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32,
                          examples=["student01"])
    email: str = Field(..., pattern=_EMAIL_PATTERN, examples=["student@ex.kz"])
    password: str = Field(..., min_length=8, examples=["Str0ngPass!"])
    language: str = Field("ru", pattern="^(ru|kk|en)$")


class LoginIn(BaseModel):
    username: str = Field(..., examples=["student01"])
    password: str = Field(..., examples=["Str0ngPass!"])


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    language: str
    is_student: bool
    display_name: str


# --- Книги -----------------------------------------------------------------
class BookIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    author: str = Field(..., min_length=1, max_length=200)
    year: Optional[int] = Field(None, ge=0, le=2100)
    language: str = Field("ru", pattern="^(ru|kk|en)$")
    genre: str = ""
    description: str = ""
    content: str = ""
    cover_color: str = "#4f46e5"
    is_paid: bool = False
    paid_days: Optional[int] = Field(None, ge=1, le=3650)


class BookPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    author: Optional[str] = Field(None, min_length=1, max_length=200)
    year: Optional[int] = Field(None, ge=0, le=2100)
    language: Optional[str] = Field(None, pattern="^(ru|kk|en)$")
    genre: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    cover_color: Optional[str] = None


class BookOut(BaseModel):
    id: int
    title: str
    author: str
    year: Optional[int]
    language: str
    genre: str
    description: str
    cover_color: str
    is_paid: bool
    created_at: str


class BookContentOut(BookOut):
    content: str
    position: int = 0  # сохранённая позиция чтения текущего пользователя


class Page(BaseModel, Generic[T]):
    """Обёртка постраничного вывода (обязательная функция варианта 11)."""
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# --- Комментарии -----------------------------------------------------------
class CommentIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    book_id: int
    username: str
    text: str
    badge: str
    created_at: str


# --- Полка и прогресс ------------------------------------------------------
class ShelfIn(BaseModel):
    status: str = Field(..., pattern="^(reading|want|dropped|read)$")


class ProgressIn(BaseModel):
    position: int = Field(..., ge=0)


# --- Администрирование и модерация ----------------------------------------
class RoleIn(BaseModel):
    role: str = Field(..., pattern="^(editor|author|moderator|student|user)$")


class BanIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    minutes: Optional[int] = Field(None, ge=1,
                                   description="Срок бана; пусто = навсегда")


class UnbanRequestIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class ResolveIn(BaseModel):
    approve: bool


class LanguageIn(BaseModel):
    language: str = Field(..., pattern="^(ru|kk|en)$")


class LogOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    details: str
    ip: str
    created_at: str


class Message(BaseModel):
    detail: str
