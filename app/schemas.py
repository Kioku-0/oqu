"""Модели запросов и ответов REST API (Pydantic v2).

Эти модели задают контракт API: FastAPI по ним проверяет входные данные и
автоматически строит документацию OpenAPI/Swagger (тема варианта 11 —
«REST API с документацией OpenAPI»).
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_LANG_PATTERN = "^(ru|kk|en)$"
_COLOR_PATTERN = "^#[0-9a-fA-F]{6}$"
_COVER_PATTERN = ("^(auto|plain|stripes|diagonal|dots|grid|waves|ornament|"
                  "frame|band|sun)$")

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Обёртка постраничного вывода (обязательная функция варианта 11)."""
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class Message(BaseModel):
    detail: str


# --- Аутентификация и профиль ------------------------------------------------
class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32,
                          examples=["student01"])
    email: str = Field(..., max_length=254, pattern=_EMAIL_PATTERN,
                       examples=["student@ex.kz"])
    password: str = Field(..., min_length=8, max_length=128,
                          examples=["Str0ngPass"])
    display_name: str = Field("", max_length=64)
    language: str = Field("ru", pattern=_LANG_PATTERN)
    accept_terms: bool = Field(
        False, description="Согласие с пользовательским соглашением")


class LoginIn(BaseModel):
    username: str = Field(..., max_length=64, examples=["student01"])
    password: str = Field(..., max_length=128, examples=["Str0ngPass"])


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
    created_at: str
    permissions: list[str] = []


class ProfileIn(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=64)


class PasswordChangeIn(BaseModel):
    old_password: str = Field(..., max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class DeleteAccountIn(BaseModel):
    password: str = Field(..., max_length=128)


class LanguageIn(BaseModel):
    language: str = Field(..., pattern=_LANG_PATTERN)


# --- Книги -------------------------------------------------------------------
class BookIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    author: str = Field(..., min_length=1, max_length=200)
    year: Optional[int] = Field(None, ge=0, le=2100)
    language: str = Field("ru", pattern=_LANG_PATTERN)
    genre: str = Field("", max_length=60)
    description: str = Field("", max_length=5000)
    content: str = Field("", max_length=5_000_000)
    external_url: str = Field("", max_length=500)
    cover_color: str = Field("#1f5f4a", pattern=_COLOR_PATTERN)
    cover_pattern: str = Field("auto", pattern=_COVER_PATTERN)
    is_paid: bool = False
    price: int = Field(0, ge=0, le=1_000_000)
    paid_days: Optional[int] = Field(None, ge=1, le=3650)
    tags: list[str] = Field(default_factory=list, max_length=10)


class BookPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    author: Optional[str] = Field(None, min_length=1, max_length=200)
    year: Optional[int] = Field(None, ge=0, le=2100)
    language: Optional[str] = Field(None, pattern=_LANG_PATTERN)
    genre: Optional[str] = Field(None, max_length=60)
    description: Optional[str] = Field(None, max_length=5000)
    content: Optional[str] = Field(None, max_length=5_000_000)
    external_url: Optional[str] = Field(None, max_length=500)
    cover_color: Optional[str] = Field(None, pattern=_COLOR_PATTERN)
    cover_pattern: Optional[str] = Field(None, pattern=_COVER_PATTERN)
    tags: Optional[list[str]] = Field(None, max_length=10)


class BookOut(BaseModel):
    id: int
    title: str
    author: str
    year: Optional[int]
    language: str
    genre: str
    description: str
    cover_color: str
    cover_pattern: str = "auto"
    cover_image: Optional[str] = None
    is_paid: bool
    price: int = 0
    paid_until: Optional[str] = None
    added_by: Optional[int] = None
    external_url: str = ""
    has_file: bool = False
    has_text: bool = False
    rating: Optional[float] = None
    rating_count: int = 0
    reads: int = 0
    created_at: str


class BookDetailOut(BookOut):
    tags: list[str] = []
    can_read: bool = False
    can_edit: bool = False
    can_delete: bool = False
    shelf_status: Optional[str] = None
    my_rating: Optional[int] = None
    position: int = 0


class BookContentOut(BaseModel):
    id: int
    title: str
    author: str
    content: str
    has_file: bool
    position: int = 0


class ImageOut(BaseModel):
    """Загруженная иллюстрация: имя файла и строка для вставки в текст."""
    name: str
    url: str
    markup: str


class GameSaveIn(BaseModel):
    """Прогресс мини-игры «Парақ» (проверяется в service.save_game)."""
    pages: float = Field(..., ge=0, le=1e15)
    pages_total: float = Field(..., ge=0, le=1e15)
    clicks: int = Field(..., ge=0, le=10 ** 12)
    upgrades: dict[str, int] = Field(default_factory=dict, max_length=30)


class GenreOut(BaseModel):
    name: str
    count: int


# --- Комментарии и оценки ----------------------------------------------------
class CommentIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    book_id: int
    user_id: int
    username: str
    display_name: str
    text: str
    badge: str
    edited_at: Optional[str] = None
    created_at: str


class RatingIn(BaseModel):
    value: int = Field(..., ge=1, le=5)


# --- Полка, прогресс, закладки -----------------------------------------------
class ShelfIn(BaseModel):
    status: Optional[str] = Field(
        ..., pattern="^(reading|want|dropped|read)$",
        description="null — убрать книгу с полки")


class ProgressIn(BaseModel):
    position: int = Field(..., ge=0, le=1_000_000)


class BookmarkIn(BaseModel):
    position: int = Field(..., ge=0, le=1_000_000)
    note: str = Field("", max_length=500)


class BookmarkOut(BaseModel):
    id: int
    book_id: int
    title: str
    position: int
    note: str
    created_at: str


# --- Модерация и администрирование -------------------------------------------
class RoleIn(BaseModel):
    role: str = Field(..., pattern="^(editor|author|moderator|student|user)$")


class BanIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    seconds: Optional[int] = Field(
        None, ge=1, le=10 * 365 * 24 * 3600,
        description="Срок бана в секундах; пусто — навсегда")


class UnbanRequestIn(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=128)
    text: str = Field(..., min_length=1, max_length=1000)


class ResolveIn(BaseModel):
    approve: bool


class LogOut(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str] = None
    action: str
    details: str
    ip: str
    created_at: str
