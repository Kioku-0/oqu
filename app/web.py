"""Веб-интерфейс и REST API библиотеки «Оқу» на FastAPI (вариант 11).

Это файл ``web.py`` из структуры методички — интерфейсный слой. Он принимает
HTTP-запросы, проверяет права, вызывает бизнес-логику :mod:`app.service` и
возвращает JSON. Обязательные функции варианта 11:

* **FastAPI** с автодокументацией OpenAPI: Swagger UI (``/docs``) и ReDoc
  (``/redoc``);
* **аутентификация JWT** — токены доступа и обновления (:mod:`app.security`);
* **постраничный вывод** — книги, комментарии, пользователи, журнал.

Усложнение — **журнал действий пользователей с временными метками**:
значимые действия пишутся в таблицу ``action_log`` (их видно в админ-панели),
а все запросы — в файл ``instance/logs/oqu.log`` с ротацией (это журнал
сервера, который на хостинге смотрит администратор).
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import Optional

from fastapi import (Depends, FastAPI, File, HTTPException, Path, Query,
                     Request, UploadFile, status)
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               Response)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from app import __version__, ai, i18n, schemas, security, service
from app.db import connect

# --- Конфигурация (всё, что зависит от сервера, — через окружение) ---------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.environ.get("OQU_INSTANCE", os.path.join(BASE_DIR,
                                                           "instance"))
DB_PATH = os.environ.get("LIBRARY_DB", os.path.join(INSTANCE_DIR,
                                                    "library.sqlite"))
UPLOAD_DIR = os.path.join(INSTANCE_DIR, "uploads")
LOG_DIR = os.path.join(INSTANCE_DIR, "logs")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

MAX_PDF_BYTES = 40 * 1024 * 1024        # скан книги — до 40 МБ
MAX_IMAGE_BYTES = 5 * 1024 * 1024       # фото студбилета — до 5 МБ
LOGIN_RATE_LIMIT = 10                   # попыток входа с одного IP...
LOGIN_RATE_WINDOW = 60                  # ...за столько секунд
# Публичный режим (сайт открыт в интернет через туннель): скрыть подсказку
# с демо-аккаунтами и паролем, доверять заголовку с IP от туннеля.
PUBLIC_MODE = os.environ.get("OQU_PUBLIC") == "1"
TRUST_PROXY = os.environ.get("OQU_TRUST_PROXY") == "1"

for _folder in (UPLOAD_DIR, os.path.join(UPLOAD_DIR, "books"),
                os.path.join(UPLOAD_DIR, "students"),
                os.path.join(UPLOAD_DIR, "images"), LOG_DIR):
    os.makedirs(_folder, exist_ok=True)

# --- Файловый журнал сервера с ротацией ---------------------------------
logger = logging.getLogger("oqu")
if not logger.handlers:
    _handler = RotatingFileHandler(os.path.join(LOG_DIR, "oqu.log"),
                                   maxBytes=2 * 1024 * 1024, backupCount=5,
                                   encoding="utf-8")
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

OPENAPI_TAGS = [
    {"name": "Аутентификация", "description": "Регистрация, вход, JWT."},
    {"name": "Профиль", "description": "Данные пользователя, пароль, "
                                       "удаление аккаунта."},
    {"name": "Книги", "description": "Каталог, поиск, пагинация, чтение, "
                                     "сканы PDF, покупка, оценки."},
    {"name": "Комментарии", "description": "Отзывы к книгам."},
    {"name": "Полка", "description": "Списки, прогресс, закладки."},
    {"name": "Статистика", "description": "Статистика прочитанного."},
    {"name": "Модерация", "description": "Пользователи, баны, заявки, "
                                         "студенты."},
    {"name": "Журнал", "description": "Журнал действий (усложнение)."},
    {"name": "Игра", "description": "Мини-игра «Парақ»: прогресс и рекорды."},
    {"name": "Трейлеры", "description": "Анимированные трейлеры книг, "
                                        "лента, генерация ИИ."},
    {"name": "Манга", "description": "Страницы манги и ИИ-перевод "
                                     "с любого языка."},
    {"name": "Новости", "description": "Обновления, конкурсы, марафоны."},
    {"name": "Презентация", "description": "Пульт живой презентации "
                                           "(только владелец)."},
    {"name": "Интерфейс", "description": "Переводы и служебное."},
]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """При запуске: подготовить базу и удалить устаревшие записи журнала."""
    db = connect(DB_PATH)
    try:
        removed = service.purge_old_log(db)
        if removed:
            logger.info("Удалено устаревших записей журнала: %d", removed)
    finally:
        db.close()
    logger.info("Оқу %s запущен, база: %s", __version__, DB_PATH)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Оқу — REST API электронной библиотеки",
    description=(
        "REST API электронной библиотеки **«Оқу»** с документацией OpenAPI."
        "\n\nВариант 11: FastAPI, аутентификация JWT, постраничный вывод, "
        "журнал действий пользователей с временными метками.\n\n"
        "Как авторизоваться здесь: выполните `POST /api/auth/login`, "
        "скопируйте `access_token`, нажмите **Authorize** и вставьте его."
        "\n\nКызылординский университет имени Коркыт Ата, 2026."
    ),
    version=__version__,
    openapi_tags=OPENAPI_TAGS,
    contact={"name": "Мұхан Надирхалиф, Жоробекова Хадизат"},
)
app.add_middleware(GZipMiddleware, minimum_size=500)

bearer_scheme = HTTPBearer(auto_error=False)


# --- Зависимости -----------------------------------------------------------
def get_db():
    """Открыть соединение с БД на время запроса и закрыть после."""
    db = connect(DB_PATH)
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    """IP-адрес посетителя (для журнала и лимита попыток входа).

    За туннелем Cloudflare все запросы приходят с 127.0.0.1, поэтому при
    ``OQU_TRUST_PROXY=1`` берём настоящий адрес из заголовка, который
    добавляет Cloudflare. Заголовку верим только от локального туннеля:
    снаружи его можно подделать.
    """
    host = request.client.host if request.client else ""
    if TRUST_PROXY and host in ("127.0.0.1", "::1"):
        real = (request.headers.get("cf-connecting-ip")
                or request.headers.get("x-forwarded-for", "").split(",")[0])
        if real.strip():
            return real.strip()[:45]
    return host


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: sqlite3.Connection = Depends(get_db),
) -> Optional[sqlite3.Row]:
    """Пользователь по JWT-токену доступа или ``None`` (гость)."""
    if creds is None:
        return None
    try:
        payload = security.decode_token(creds.credentials)
        if payload.get("type") != "access":
            return None
        return service.get_user(db, int(payload["sub"]))
    except Exception:
        return None


def require_user(
    user: Optional[sqlite3.Row] = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    """Требовать вошедшего и не забаненного пользователя."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Требуется авторизация")
    if service.is_banned(db, user["id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован")
    return user


def require_perm(permission: str):
    """Фабрика зависимостей: требовать конкретное право."""
    def dependency(user: sqlite3.Row = Depends(require_user)) -> sqlite3.Row:
        service.require_permission(user["role"], permission)
        return user
    return dependency


def audit(db: sqlite3.Connection, request: Request,
          user_id: Optional[int], action: str, details: str = "") -> None:
    """Записать значимое действие в журнал (БД) с временной меткой."""
    service.log_action(db, user_id, action, details, client_ip(request))


# --- Ошибки бизнес-логики -> HTTP ------------------------------------------
_ERROR_STATUS = (
    (service.ValidationError, status.HTTP_400_BAD_REQUEST, "validation"),
    (service.AuthError, status.HTTP_401_UNAUTHORIZED, "auth"),
    (service.AccountLockedError, status.HTTP_429_TOO_MANY_REQUESTS, "locked"),
    (service.BannedError, status.HTTP_403_FORBIDDEN, "banned"),
    (service.PermissionDeniedError, status.HTTP_403_FORBIDDEN, "forbidden"),
    (service.NotFoundError, status.HTTP_404_NOT_FOUND, "not_found"),
    (service.ConflictError, status.HTTP_409_CONFLICT, "conflict"),
    (service.AIUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE, "ai"),
)


@app.exception_handler(service.ServiceError)
async def service_error_handler(request: Request, exc: service.ServiceError):
    """Ошибка бизнес-логики -> понятный JSON с кодом для интерфейса."""
    code, kind = status.HTTP_400_BAD_REQUEST, "error"
    for exc_type, http_code, name in _ERROR_STATUS:
        if isinstance(exc, exc_type):
            code, kind = http_code, name
            break
    body = {"detail": str(exc), "code": kind}
    headers = None
    if isinstance(exc, service.BannedError):
        body.update(reason=exc.reason, until=exc.until)
    if isinstance(exc, service.AccountLockedError) and exc.retry_after:
        body["retry_after"] = exc.retry_after
        headers = {"Retry-After": str(exc.retry_after)}
    return JSONResponse(status_code=code, content=body, headers=headers)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    """Непредвиденная ошибка: пишем в лог, наружу — без подробностей."""
    logger.exception("Необработанная ошибка: %s %s", request.method,
                     request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "Внутренняя ошибка сервера",
                                 "code": "server"})


# --- Промежуточные слои: заголовки, кэш, файловый лог ------------------------
_CSP = ("default-src 'self'; img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "frame-src 'self' blob:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'self'")
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_and_logging(request: Request, call_next):
    """Заголовки безопасности, политика кэша и запись в файл журнала."""
    started = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=()"
    if not path.startswith(_DOCS_PATHS):
        # Swagger грузит свои скрипты с CDN, поэтому для /docs CSP не ставим.
        response.headers["Content-Security-Policy"] = _CSP
    if path.startswith("/static/"):
        # Файлы подключаются с ?v=<версия>, поэтому их можно кэшировать
        # надолго: при обновлении сайта меняется адрес.
        response.headers["Cache-Control"] = "public, max-age=31536000, " \
                                            "immutable"
    elif path.startswith("/api/i18n/"):
        response.headers["Cache-Control"] = "public, max-age=3600"
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elapsed = (time.perf_counter() - started) * 1000
    if path == "/api/present/state" and response.status_code == 200:
        return response    # опрос пульта раз в секунду — в лог не пишем
    logger.info("%s %s %s %d %.1fms", client_ip(request), request.method,
                path, response.status_code, elapsed)
    return response


# --- Ограничение частоты входа по IP (вторая линия защиты от брутфорса) ----
_login_hits: dict[str, deque] = defaultdict(deque)


def _check_login_rate(ip: str) -> None:
    now = time.monotonic()
    hits = _login_hits[ip]
    while hits and now - hits[0] > LOGIN_RATE_WINDOW:
        hits.popleft()
    if len(hits) >= LOGIN_RATE_LIMIT:
        # Через столько секунд самая старая попытка «выпадет» из окна.
        wait = int(LOGIN_RATE_WINDOW - (now - hits[0])) + 1
        raise service.AccountLockedError(
            "Слишком много попыток входа с этого адреса. Подождите минуту.",
            retry_after=wait)
    hits.append(now)


# --- Загрузка файлов ---------------------------------------------------------
_IMAGE_SIGNATURES = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"),
                     (b"RIFF", ".webp"))


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """Прочитать файл, не превышая лимит (защита от огромных загрузок)."""
    data = bytearray()
    while chunk := await upload.read(1024 * 256):
        data += chunk
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"Файл больше {limit // 1024 // 1024} МБ")
    return bytes(data)


def _save_upload(folder: str, data: bytes, ext: str) -> str:
    """Сохранить файл под случайным именем (имя от пользователя не берём)."""
    name = secrets.token_hex(16) + ext
    with open(os.path.join(UPLOAD_DIR, folder, name), "wb") as fh:
        fh.write(data)
    return name


def _image_ext(data: bytes) -> str:
    """Расширение картинки по её первым байтам (а не по имени файла)."""
    ext = next((e for sig, e in _IMAGE_SIGNATURES if data.startswith(sig)),
               None)
    if ext is None or (ext == ".webp" and data[8:12] != b"WEBP"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Нужна картинка: JPG, PNG или WebP")
    return ext


def _remove_upload(folder: str, name: Optional[str]) -> None:
    if name:
        try:
            os.remove(os.path.join(UPLOAD_DIR, folder,
                                   os.path.basename(name)))
        except OSError:
            pass


def _user_out(user: sqlite3.Row) -> dict:
    data = dict(user)
    data["permissions"] = service.permissions_of(user["role"])
    return data


# ===========================================================================
# Аутентификация
# ===========================================================================
@app.post("/api/auth/register", response_model=schemas.UserOut,
          status_code=201, tags=["Аутентификация"],
          summary="Регистрация (нужно согласие с соглашением)")
def register(data: schemas.RegisterIn, request: Request,
             db: sqlite3.Connection = Depends(get_db)):
    uid = service.register_user(
        db, data.username, data.email, data.password, language=data.language,
        display_name=data.display_name, accept_terms=data.accept_terms)
    audit(db, request, uid, "register",
          f"соглашение {service.AGREEMENT_VERSION}")
    return _user_out(service.get_user(db, uid))


@app.post("/api/auth/login", response_model=schemas.TokenOut,
          tags=["Аутентификация"], summary="Вход и получение JWT-токенов")
def login(data: schemas.LoginIn, request: Request,
          db: sqlite3.Connection = Depends(get_db)):
    ip = client_ip(request)
    _check_login_rate(ip)
    try:
        user = service.authenticate(db, data.username, data.password)
    except (service.AuthError, service.AccountLockedError) as exc:
        target = service.get_user_by_username(db, data.username)
        audit(db, request, target["id"] if target else None, "login_failed",
              f"логин «{data.username[:32]}»: {exc}")
        raise
    audit(db, request, user["id"], "login", "успешный вход")
    return schemas.TokenOut(
        access_token=security.create_access_token(user["id"], user["role"]),
        refresh_token=security.create_refresh_token(user["id"]))


@app.post("/api/auth/refresh", response_model=schemas.TokenOut,
          tags=["Аутентификация"], summary="Обновить токен доступа")
def refresh(data: schemas.RefreshIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        payload = security.decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("not a refresh token")
        user = service.get_user(db, int(payload["sub"]))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Недействительный refresh-токен")
    if service.is_banned(db, user["id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован")
    return schemas.TokenOut(
        access_token=security.create_access_token(user["id"], user["role"]),
        refresh_token=security.create_refresh_token(user["id"]))


@app.post("/api/unban-request", response_model=schemas.Message,
          tags=["Аутентификация"],
          summary="Заявка на разбан (без входа, по логину и паролю)")
def unban_request(data: schemas.UnbanRequestIn, request: Request,
                  db: sqlite3.Connection = Depends(get_db)):
    _check_login_rate(client_ip(request))
    rid = service.unban_request_by_credentials(db, data.username,
                                               data.password, data.text)
    user = service.get_user_by_username(db, data.username)
    audit(db, request, user["id"], "unban_request", f"заявка #{rid}")
    return {"detail": "Заявка отправлена"}


# ===========================================================================
# Профиль
# ===========================================================================
@app.get("/api/me", response_model=schemas.UserOut, tags=["Профиль"],
         summary="Текущий пользователь и его права")
def me(user: sqlite3.Row = Depends(require_user)):
    return _user_out(user)


@app.get("/api/me/summary", tags=["Профиль"],
         summary="Профиль: полки, продолжить чтение, закладки")
def me_summary(user: sqlite3.Row = Depends(require_user),
               db: sqlite3.Connection = Depends(get_db)):
    return {
        "user": _user_out(user),
        "shelf_counts": service.shelf_counts(db, user["id"]),
        "continue": service.continue_reading(db, user["id"]),
        "bookmarks": service.list_bookmarks(db, user["id"])[:10],
        "student_request": service.student_request_status(db, user["id"]),
    }


@app.patch("/api/me", response_model=schemas.UserOut, tags=["Профиль"],
           summary="Изменить имя")
def update_me(data: schemas.ProfileIn, request: Request,
              user: sqlite3.Row = Depends(require_user),
              db: sqlite3.Connection = Depends(get_db)):
    service.update_profile(db, user["id"], data.display_name)
    audit(db, request, user["id"], "profile_update")
    return _user_out(service.get_user(db, user["id"]))


@app.post("/api/me/password", response_model=schemas.Message,
          tags=["Профиль"], summary="Сменить пароль")
def change_password(data: schemas.PasswordChangeIn, request: Request,
                    user: sqlite3.Row = Depends(require_user),
                    db: sqlite3.Connection = Depends(get_db)):
    service.change_password(db, user["id"], data.old_password,
                            data.new_password)
    audit(db, request, user["id"], "password_change")
    return {"detail": "Пароль изменён"}


@app.delete("/api/me", response_model=schemas.Message, tags=["Профиль"],
            summary="Удалить свой аккаунт (подтверждение паролем)")
def delete_me(data: schemas.DeleteAccountIn, request: Request,
              user: sqlite3.Row = Depends(require_user),
              db: sqlite3.Connection = Depends(get_db)):
    service.delete_account(db, user["id"], data.password)
    # Логин в журнал не пишем: после удаления запись остаётся обезличенной.
    audit(db, request, None, "account_delete", f"id {user['id']}")
    return {"detail": "Аккаунт удалён"}


@app.put("/api/me/language", response_model=schemas.Message,
         tags=["Профиль"], summary="Сохранить язык интерфейса")
def set_user_language(data: schemas.LanguageIn,
                      user: sqlite3.Row = Depends(require_user),
                      db: sqlite3.Connection = Depends(get_db)):
    service.set_language(db, user["id"], data.language)
    return {"detail": "Язык сохранён"}


@app.post("/api/me/student-request", response_model=schemas.Message,
          tags=["Профиль"],
          summary="Загрузить фото студбилета (JPG/PNG/WebP до 5 МБ)")
async def student_request(request: Request, file: UploadFile = File(...),
                          user: sqlite3.Row = Depends(
                              require_perm("student.apply")),
                          db: sqlite3.Connection = Depends(get_db)):
    data = await _read_limited(file, MAX_IMAGE_BYTES)
    name = _save_upload("students", data, _image_ext(data))
    try:
        rid = service.submit_student_request(db, user, name)
    except service.ServiceError:
        _remove_upload("students", name)
        raise
    audit(db, request, user["id"], "student_request", f"заявка #{rid}")
    return {"detail": "Заявка отправлена на проверку"}


# ===========================================================================
# Книги
# ===========================================================================
@app.get("/api/books", response_model=schemas.Page[schemas.BookOut],
         tags=["Книги"], summary="Каталог: поиск, фильтры, пагинация")
def list_books(
    db: sqlite3.Connection = Depends(get_db),
    query: str = Query("", max_length=100,
                       description="Поиск по названию, автору, описанию"),
    author: str = Query("", max_length=100),
    year: Optional[int] = Query(None, ge=0, le=2100),
    year_from: Optional[int] = Query(None, ge=0, le=2100),
    year_to: Optional[int] = Query(None, ge=0, le=2100),
    genre: str = Query("", max_length=60),
    language: str = Query("", pattern="^(|ru|kk|ky|en)$"),
    tag: str = Query("", max_length=40),
    access: str = Query("", pattern="^(|free|paid)$"),
    sort: str = Query("title", pattern="^(" + "|".join(service.BOOK_SORTS)
                      + ")$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(service.DEFAULT_PAGE_SIZE, ge=1,
                           le=service.MAX_PAGE_SIZE),
):
    return service.search_books(
        db, query=query, author=author, year=year, year_from=year_from,
        year_to=year_to, genre=genre, language=language, tag=tag,
        access=access, sort=sort, order=order, page=page,
        page_size=page_size)


@app.get("/api/books/random", response_model=list[schemas.BookOut],
         tags=["Книги"], summary="Случайные книги для режима «Шкаф»")
def random_books(genre: str = Query("", max_length=60),
                 limit: int = Query(24, ge=1, le=60),
                 db: sqlite3.Connection = Depends(get_db)):
    return service.random_books(db, genre, limit)


@app.get("/api/genres", response_model=list[schemas.GenreOut],
         tags=["Книги"], summary="Жанры с количеством книг")
def genres(db: sqlite3.Connection = Depends(get_db)):
    return service.list_genres(db)


@app.get("/api/tags", tags=["Книги"], summary="Популярные теги")
def tags(db: sqlite3.Connection = Depends(get_db)):
    return service.popular_tags(db)


@app.get("/api/books/{book_id}", response_model=schemas.BookDetailOut,
         tags=["Книги"], summary="Карточка книги (с учётом пользователя)")
def get_book(book_id: int = Path(..., ge=1),
             user: Optional[sqlite3.Row] = Depends(get_current_user),
             db: sqlite3.Connection = Depends(get_db)):
    data = service.get_book_details(db, book_id)
    book = service.get_book(db, book_id)
    data["can_read"] = service.user_can_read(db, user, book)
    if user is not None:
        role, own = user["role"], book["added_by"] == user["id"]
        data["can_edit"] = service.has_permission(role, "book.edit") or (
            own and service.has_permission(role, "book.edit_own"))
        data["can_delete"] = service.has_permission(role, "book.delete") or (
            own and service.has_permission(role, "book.delete_own"))
        data["shelf_status"] = service.shelf_status(db, user["id"], book_id)
        data["my_rating"] = service.user_rating(db, user["id"], book_id)
        data["position"] = service.get_progress(db, user["id"], book_id)
    return data


def _readable_book(db, user, book_id) -> sqlite3.Row:
    book = service.get_book(db, book_id)
    if not service.user_can_read(db, user, book):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Книга платная: купите её или подтвердите "
                            "статус студента")
    return book


@app.get("/api/books/{book_id}/read", response_model=schemas.BookContentOut,
         tags=["Книги"], summary="Текст книги (с учётом прав доступа)")
def read_book(book_id: int, request: Request,
              user: Optional[sqlite3.Row] = Depends(get_current_user),
              db: sqlite3.Connection = Depends(get_db)):
    book = _readable_book(db, user, book_id)
    position = 0
    if user is not None:
        position = service.get_progress(db, user["id"], book_id)
        audit(db, request, user["id"], "read_book", f"книга #{book_id}")
    return {"id": book["id"], "title": book["title"],
            "author": book["author"], "content": book["content"],
            "has_file": book["file_path"] is not None, "position": position}


@app.get("/api/books/{book_id}/file", tags=["Книги"],
         summary="PDF-скан книги (с учётом прав доступа)",
         response_class=FileResponse)
def book_file(book_id: int,
              user: Optional[sqlite3.Row] = Depends(get_current_user),
              db: sqlite3.Connection = Depends(get_db)):
    book = _readable_book(db, user, book_id)
    if not book["file_path"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "У книги нет скана")
    path = os.path.join(UPLOAD_DIR, "books",
                        os.path.basename(book["file_path"]))
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/books", response_model=schemas.BookOut, status_code=201,
          tags=["Книги"], summary="Добавить книгу (редактор, автор)")
def create_book(data: schemas.BookIn, request: Request,
                user: sqlite3.Row = Depends(require_perm("book.add")),
                db: sqlite3.Connection = Depends(get_db)):
    bid = service.add_book(
        db, user["role"], data.title, data.author, year=data.year,
        language=data.language, genre=data.genre,
        description=data.description, content=data.content,
        external_url=data.external_url, cover_color=data.cover_color,
        cover_pattern=data.cover_pattern,
        is_paid=data.is_paid, price=data.price, paid_days=data.paid_days,
        tags=data.tags, added_by=user["id"], kind=data.kind)
    audit(db, request, user["id"], "book_add", f"#{bid} «{data.title}»")
    return service.get_book_details(db, bid)


@app.patch("/api/books/{book_id}", response_model=schemas.BookOut,
           tags=["Книги"], summary="Изменить книгу (редактор или её автор)")
def update_book(book_id: int, data: schemas.BookPatch, request: Request,
                user: sqlite3.Row = Depends(require_user),
                db: sqlite3.Connection = Depends(get_db)):
    service.edit_book(db, user, book_id, **data.model_dump())
    audit(db, request, user["id"], "book_edit", f"#{book_id}")
    return service.get_book_details(db, book_id)


@app.delete("/api/books/{book_id}", response_model=schemas.Message,
            tags=["Книги"], summary="Удалить книгу (редактор или её автор)")
def remove_book(book_id: int, request: Request,
                user: sqlite3.Row = Depends(require_user),
                db: sqlite3.Connection = Depends(get_db)):
    title = service.get_book(db, book_id)["title"]
    images = service.book_files(db, book_id)
    _remove_upload("books", service.delete_book(db, user, book_id))
    for name in images:
        _remove_upload("images", name)
    audit(db, request, user["id"], "book_delete", f"#{book_id} «{title}»")
    return {"detail": "Книга удалена"}


@app.post("/api/books/{book_id}/file", response_model=schemas.Message,
          tags=["Книги"], summary="Загрузить PDF-скан книги (до 40 МБ)")
async def upload_book_file(book_id: int, request: Request,
                           file: UploadFile = File(...),
                           user: sqlite3.Row = Depends(require_user),
                           db: sqlite3.Connection = Depends(get_db)):
    book = service.get_book(db, book_id)
    service.require_book_rights(user, book, "book.edit", "book.edit_own")
    data = await _read_limited(file, MAX_PDF_BYTES)
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нужен файл PDF")
    name = _save_upload("books", data, ".pdf")
    _remove_upload("books", book["file_path"])
    service.set_book_file(db, book_id, name)
    audit(db, request, user["id"], "book_file", f"#{book_id} PDF "
          f"{len(data) // 1024} КБ")
    return {"detail": "Скан загружен"}


@app.delete("/api/books/{book_id}/file", response_model=schemas.Message,
            tags=["Книги"], summary="Удалить PDF-скан книги")
def delete_book_file(book_id: int, request: Request,
                     user: sqlite3.Row = Depends(require_user),
                     db: sqlite3.Connection = Depends(get_db)):
    book = service.get_book(db, book_id)
    service.require_book_rights(user, book, "book.edit", "book.edit_own")
    _remove_upload("books", book["file_path"])
    service.set_book_file(db, book_id, None)
    audit(db, request, user["id"], "book_file_delete", f"#{book_id}")
    return {"detail": "Скан удалён"}


@app.post("/api/books/{book_id}/cover", response_model=schemas.Message,
          tags=["Книги"], summary="Картинка обложки (JPG/PNG/WebP до 5 МБ)")
async def upload_cover(book_id: int, request: Request,
                       file: UploadFile = File(...),
                       user: sqlite3.Row = Depends(require_user),
                       db: sqlite3.Connection = Depends(get_db)):
    book = service.get_book(db, book_id)
    service.require_book_rights(user, book, "book.edit", "book.edit_own")
    data = await _read_limited(file, MAX_IMAGE_BYTES)
    name = _save_upload("images", data, _image_ext(data))
    _remove_upload("images", service.set_book_cover(db, book_id, name))
    audit(db, request, user["id"], "book_cover", f"#{book_id}")
    return {"detail": "Обложка загружена"}


@app.delete("/api/books/{book_id}/cover", response_model=schemas.Message,
            tags=["Книги"], summary="Убрать картинку обложки")
def delete_cover(book_id: int, request: Request,
                 user: sqlite3.Row = Depends(require_user),
                 db: sqlite3.Connection = Depends(get_db)):
    book = service.get_book(db, book_id)
    service.require_book_rights(user, book, "book.edit", "book.edit_own")
    _remove_upload("images", service.set_book_cover(db, book_id, None))
    audit(db, request, user["id"], "book_cover_delete", f"#{book_id}")
    return {"detail": "Обложка убрана"}


@app.post("/api/books/{book_id}/images", response_model=schemas.ImageOut,
          tags=["Книги"],
          summary="Иллюстрация для текста книги (JPG/PNG/WebP до 5 МБ)")
async def upload_book_image(book_id: int, request: Request,
                            file: UploadFile = File(...),
                            user: sqlite3.Row = Depends(require_user),
                            db: sqlite3.Connection = Depends(get_db)):
    book = service.get_book(db, book_id)
    service.require_book_rights(user, book, "book.edit", "book.edit_own")
    data = await _read_limited(file, MAX_IMAGE_BYTES)
    name = _save_upload("images", data, _image_ext(data))
    try:
        markup = service.add_book_image(db, book_id, name)
    except service.ServiceError:
        _remove_upload("images", name)
        raise
    audit(db, request, user["id"], "book_image", f"#{book_id}")
    return {"name": name, "url": f"/media/{name}", "markup": markup}


_MEDIA_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")


@app.get("/media/{name}", include_in_schema=False)
def media(name: str):
    """Картинки обложек и иллюстраций. Имена случайные (32 hex-символа),
    угадать чужой файл нельзя; путь проверяется регулярным выражением."""
    if not _MEDIA_NAME.match(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Нет такого файла")
    path = os.path.join(UPLOAD_DIR, "images", name)
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Нет такого файла")
    return FileResponse(path, headers={
        "Cache-Control": "public, max-age=31536000, immutable"})


@app.post("/api/books/{book_id}/buy", response_model=schemas.Message,
          tags=["Книги"], summary="Купить платную книгу (учебная имитация)")
def buy_book(book_id: int, request: Request,
             user: sqlite3.Row = Depends(require_user),
             db: sqlite3.Connection = Depends(get_db)):
    price = service.buy_book(db, user, book_id)
    audit(db, request, user["id"], "purchase", f"#{book_id}, {price} ₸")
    return {"detail": "Книга куплена"}


@app.put("/api/books/{book_id}/rating", response_model=schemas.Message,
         tags=["Книги"], summary="Оценить книгу от 1 до 5")
def rate_book(book_id: int, data: schemas.RatingIn,
              user: sqlite3.Row = Depends(require_user),
              db: sqlite3.Connection = Depends(get_db)):
    service.rate_book(db, user, book_id, data.value)
    return {"detail": "Оценка сохранена"}


# ===========================================================================
# Комментарии
# ===========================================================================
@app.get("/api/books/{book_id}/comments",
         response_model=schemas.Page[schemas.CommentOut],
         tags=["Комментарии"], summary="Комментарии книги (постранично)")
def get_comments(book_id: int, page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100),
                 db: sqlite3.Connection = Depends(get_db)):
    service.get_book(db, book_id)
    return service.list_comments(db, book_id, page, page_size)


@app.post("/api/books/{book_id}/comments", response_model=schemas.Message,
          status_code=201, tags=["Комментарии"],
          summary="Оставить комментарий")
def post_comment(book_id: int, data: schemas.CommentIn, request: Request,
                 user: sqlite3.Row = Depends(require_user),
                 db: sqlite3.Connection = Depends(get_db)):
    cid = service.add_comment(db, user, book_id, data.text)
    audit(db, request, user["id"], "comment_add",
          f"комментарий #{cid} к книге #{book_id}")
    return {"detail": "Комментарий добавлен"}


@app.patch("/api/comments/{comment_id}", response_model=schemas.Message,
           tags=["Комментарии"], summary="Изменить свой комментарий")
def edit_comment(comment_id: int, data: schemas.CommentIn, request: Request,
                 user: sqlite3.Row = Depends(require_user),
                 db: sqlite3.Connection = Depends(get_db)):
    service.edit_comment(db, user, comment_id, data.text)
    audit(db, request, user["id"], "comment_edit", f"#{comment_id}")
    return {"detail": "Комментарий изменён"}


@app.delete("/api/comments/{comment_id}", response_model=schemas.Message,
            tags=["Комментарии"], summary="Удалить комментарий")
def remove_comment(comment_id: int, request: Request,
                   user: sqlite3.Row = Depends(require_user),
                   db: sqlite3.Connection = Depends(get_db)):
    service.delete_comment(db, user, comment_id)
    audit(db, request, user["id"], "comment_delete", f"#{comment_id}")
    return {"detail": "Комментарий удалён"}


# ===========================================================================
# Полка, прогресс, закладки
# ===========================================================================
@app.get("/api/me/shelf", response_model=list[dict], tags=["Полка"],
         summary="Книги на полке")
def my_shelf(status_filter: str = Query(
        "", alias="status", pattern="^(|reading|want|dropped|read)$"),
        user: sqlite3.Row = Depends(require_user),
        db: sqlite3.Connection = Depends(get_db)):
    return service.get_shelf(db, user["id"], status_filter or None)


@app.put("/api/me/shelf/{book_id}", response_model=schemas.Message,
         tags=["Полка"], summary="Статус книги на полке (null — убрать)")
def set_shelf(book_id: int, data: schemas.ShelfIn,
              user: sqlite3.Row = Depends(require_perm("shelf.manage")),
              db: sqlite3.Connection = Depends(get_db)):
    service.set_shelf_status(db, user["id"], book_id, data.status)
    return {"detail": "Статус обновлён"}


@app.put("/api/me/progress/{book_id}", response_model=schemas.Message,
         tags=["Полка"], summary="Сохранить место чтения")
def set_progress(book_id: int, data: schemas.ProgressIn,
                 user: sqlite3.Row = Depends(require_perm("progress.save")),
                 db: sqlite3.Connection = Depends(get_db)):
    service.save_progress(db, user["id"], book_id, data.position)
    return {"detail": "Прогресс сохранён"}


@app.get("/api/me/bookmarks", response_model=list[schemas.BookmarkOut],
         tags=["Полка"], summary="Мои закладки")
def bookmarks(book_id: Optional[int] = Query(None, ge=1),
              user: sqlite3.Row = Depends(require_user),
              db: sqlite3.Connection = Depends(get_db)):
    return service.list_bookmarks(db, user["id"], book_id)


@app.post("/api/me/bookmarks/{book_id}", response_model=schemas.Message,
          status_code=201, tags=["Полка"], summary="Добавить закладку")
def add_bookmark(book_id: int, data: schemas.BookmarkIn,
                 user: sqlite3.Row = Depends(require_perm("progress.save")),
                 db: sqlite3.Connection = Depends(get_db)):
    service.add_bookmark(db, user["id"], book_id, data.position, data.note)
    return {"detail": "Закладка добавлена"}


@app.delete("/api/me/bookmarks/{bookmark_id}",
            response_model=schemas.Message, tags=["Полка"],
            summary="Удалить закладку")
def delete_bookmark(bookmark_id: int,
                    user: sqlite3.Row = Depends(require_user),
                    db: sqlite3.Connection = Depends(get_db)):
    service.delete_bookmark(db, user["id"], bookmark_id)
    return {"detail": "Закладка удалена"}


# ===========================================================================
# Статистика
# ===========================================================================
@app.get("/api/stats", tags=["Статистика"],
         summary="Статистика прочитанного по всем пользователям")
def stats(db: sqlite3.Connection = Depends(get_db)):
    return service.reading_stats(db)


# ===========================================================================
# Мини-игра «Парақ»
# ===========================================================================
@app.get("/api/game/config", tags=["Игра"],
         summary="Улучшения и константы мини-игры")
def game_config():
    return service.game_config()


@app.get("/api/game/me", tags=["Игра"], summary="Мой прогресс в игре")
def game_me(user: sqlite3.Row = Depends(require_user),
            db: sqlite3.Connection = Depends(get_db)):
    return service.get_game(db, user["id"])


@app.put("/api/game/me", tags=["Игра"],
         summary="Сохранить прогресс (с проверкой на накрутку)")
def game_save(data: schemas.GameSaveIn,
              user: sqlite3.Row = Depends(require_user),
              db: sqlite3.Connection = Depends(get_db)):
    return service.save_game(db, user["id"], data.pages, data.pages_total,
                             data.clicks, data.upgrades)


@app.delete("/api/game/me", response_model=schemas.Message, tags=["Игра"],
            summary="Начать игру заново")
def game_reset(request: Request, user: sqlite3.Row = Depends(require_user),
               db: sqlite3.Connection = Depends(get_db)):
    service.reset_game(db, user["id"])
    audit(db, request, user["id"], "game_reset", "прогресс игры сброшен")
    return {"detail": "Игра начата заново"}


@app.get("/api/game/leaderboard", tags=["Игра"],
         summary="Рекорды игры (все игроки на равных)")
def game_top(db: sqlite3.Connection = Depends(get_db)):
    return service.game_leaderboard(db)


# ===========================================================================
# Трейлеры книг: анимированная «книга-история» при открытии + лента
# ===========================================================================
@app.get("/api/trailers", tags=["Трейлеры"],
         summary="Лента трейлеров (книжный TikTok), пагинация")
def trailers_feed(page: int = Query(1, ge=1),
                  page_size: int = Query(10, ge=1, le=30),
                  db: sqlite3.Connection = Depends(get_db)):
    return service.trailer_feed(db, page=page, page_size=page_size)


@app.get("/api/books/{book_id}/trailer", response_model=schemas.TrailerOut,
         tags=["Трейлеры"], summary="Трейлер книги")
def book_trailer(book_id: int, db: sqlite3.Connection = Depends(get_db)):
    return service.get_trailer(db, book_id)


@app.put("/api/books/{book_id}/trailer", response_model=schemas.TrailerOut,
         tags=["Трейлеры"], summary="Сохранить трейлер (автор, редактор)")
def save_trailer(book_id: int, data: schemas.TrailerIn, request: Request,
                 user: sqlite3.Row = Depends(require_user),
                 db: sqlite3.Connection = Depends(get_db)):
    result = service.set_trailer(db, user, book_id,
                                 [s.model_dump() for s in data.scenes])
    audit(db, request, user["id"], "trailer_save", f"#{book_id}")
    return result


@app.delete("/api/books/{book_id}/trailer", response_model=schemas.Message,
            tags=["Трейлеры"], summary="Удалить трейлер")
def remove_trailer(book_id: int, request: Request,
                   user: sqlite3.Row = Depends(require_user),
                   db: sqlite3.Connection = Depends(get_db)):
    service.delete_trailer(db, user, book_id)
    audit(db, request, user["id"], "trailer_delete", f"#{book_id}")
    return {"detail": "Трейлер удалён"}


# Рисование трейлера ИИ идёт 1–3 минуты — дольше, чем прокси ждёт ответа
# (120 с). Поэтому работа запускается в фоне, а страница раз в несколько
# секунд спрашивает её состояние: GET /api/books/{id}/trailer/job.
_trailer_jobs: dict[int, dict] = {}
_jobs_lock = threading.Lock()


def _run_trailer_job(book_id: int, user_id: int, mode: str, ip: str) -> None:
    db = connect(DB_PATH)
    try:
        user = service.get_user(db, user_id)
        book = service.get_book(db, book_id)
        if mode == "generate":
            scenes = ai.generate_drawn_trailer(dict(book),
                                               book["content"] or "")
            source = "ai"
        else:
            current = service.get_trailer(db, book_id)
            drawings = ai.draw_scenes(dict(book), current["scenes"])
            if not any(drawings):
                raise service.AIUnavailableError(
                    "ИИ не смог нарисовать сцены, попробуйте ещё раз")
            scenes = [{**s, "svg": svg or s.get("svg")}
                      for s, svg in zip(current["scenes"], drawings)]
            source = current.get("source", "author")
        service.set_trailer(db, user, book_id, scenes, source=source)
        service.log_action(db, user_id, f"trailer_{mode}", f"#{book_id}", ip)
        state = {"state": "done"}
    except service.ServiceError as exc:
        state = {"state": "error", "error": str(exc)}
    except Exception:                       # noqa: BLE001 — в лог, наружу кратко
        logger.exception("Фоновая генерация трейлера #%d", book_id)
        state = {"state": "error", "error": "Внутренняя ошибка сервера"}
    finally:
        db.close()
    with _jobs_lock:
        _trailer_jobs[book_id] = {**state, "mode": mode,
                                  "finished": time.time()}


def _start_trailer_job(book_id: int, request: Request, user: sqlite3.Row,
                       db: sqlite3.Connection, mode: str) -> dict:
    book = service.get_book(db, book_id)
    service.require_book_rights(user, book, "book.edit", "book.edit_own")
    if mode == "draw":
        service.get_trailer(db, book_id)        # рисовать есть к чему?
    if not ai.is_configured():
        raise service.AIUnavailableError(
            "ИИ не настроен: на сервере не задан GEMINI_API_KEY")
    with _jobs_lock:
        job = _trailer_jobs.get(book_id)
        if job and job["state"] == "working":
            return job                           # уже идёт — не дублируем
        _check_ai_rate(user["id"])
        job = {"state": "working", "mode": mode, "started": time.time()}
        _trailer_jobs[book_id] = job
    threading.Thread(target=_run_trailer_job, daemon=True,
                     args=(book_id, user["id"], mode,
                           client_ip(request))).start()
    return job


@app.post("/api/books/{book_id}/trailer/generate", status_code=202,
          tags=["Трейлеры"],
          summary="ИИ (Gemini) пишет подписи и рисует сцены (в фоне)")
def generate_trailer(book_id: int, request: Request,
                     user: sqlite3.Row = Depends(require_user),
                     db: sqlite3.Connection = Depends(get_db)):
    return _start_trailer_job(book_id, request, user, db, "generate")


@app.post("/api/books/{book_id}/trailer/draw", status_code=202,
          tags=["Трейлеры"],
          summary="ИИ заново рисует сцены к подписям трейлера (в фоне)")
def draw_trailer(book_id: int, request: Request,
                 user: sqlite3.Row = Depends(require_user),
                 db: sqlite3.Connection = Depends(get_db)):
    return _start_trailer_job(book_id, request, user, db, "draw")


@app.get("/api/books/{book_id}/trailer/job", tags=["Трейлеры"],
         summary="Состояние фоновой работы ИИ над трейлером")
def trailer_job(book_id: int, user: sqlite3.Row = Depends(require_user),
                db: sqlite3.Connection = Depends(get_db)):
    service.require_book_rights(user, service.get_book(db, book_id),
                                "book.edit", "book.edit_own")
    with _jobs_lock:
        return _trailer_jobs.get(book_id, {"state": "none"})


@app.get("/api/ai/status", tags=["Трейлеры"],
         summary="Включены ли ИИ-функции на сервере")
def ai_status():
    return {"enabled": ai.is_configured(), "provider": ai.provider(),
            "model": ai.model_name()}


# ===========================================================================
# Манга и комиксы: страницы-картинки и автоперевод с любого языка
# ===========================================================================
MAX_MANGA_PAGE_BYTES = 8 * 1024 * 1024
AI_RATE_LIMIT, AI_RATE_WINDOW = 40, 3600     # запросов к ИИ в час на человека
_ai_hits: dict[int, deque] = defaultdict(deque)


def _check_ai_rate(user_id: int) -> None:
    """ИИ стоит денег: не больше AI_RATE_LIMIT запросов в час от одного
    пользователя (готовые переводы отдаются без запроса к ИИ)."""
    now = time.monotonic()
    hits = _ai_hits[user_id]
    while hits and now - hits[0] > AI_RATE_WINDOW:
        hits.popleft()
    if len(hits) >= AI_RATE_LIMIT:
        raise service.AccountLockedError(
            "Слишком много запросов к ИИ, попробуйте позже",
            retry_after=int(AI_RATE_WINDOW - (now - hits[0])) + 1)
    hits.append(now)


def _image_size(data: bytes) -> tuple[int, int]:
    """Ширина и высота PNG/JPEG/WebP по заголовку файла (без Pillow)."""
    if data.startswith(b"\x89PNG"):
        return (int.from_bytes(data[16:20], "big"),
                int.from_bytes(data[20:24], "big"))
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1,
                    int.from_bytes(data[27:30], "little") + 1)
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8 ":
            return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                    int.from_bytes(data[28:30], "little") & 0x3FFF)
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            length = int.from_bytes(data[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9,
                          0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                return (int.from_bytes(data[i + 7:i + 9], "big"),
                        int.from_bytes(data[i + 5:i + 7], "big"))
            i += 2 + length
    return 0, 0


def _page_out(page: dict) -> dict:
    return {**page, "url": f"/media/{page['file_name']}"}


@app.get("/api/books/{book_id}/pages", response_model=list[
         schemas.MangaPageOut], tags=["Манга"],
         summary="Страницы манги (с учётом прав доступа)")
def manga_pages(book_id: int,
                user: Optional[sqlite3.Row] = Depends(get_current_user),
                db: sqlite3.Connection = Depends(get_db)):
    _readable_book(db, user, book_id)
    return [_page_out(p) for p in service.list_manga_pages(db, book_id)]


@app.post("/api/books/{book_id}/pages", response_model=schemas.MangaPageOut,
          status_code=201, tags=["Манга"],
          summary="Загрузить страницу манги (в конец)")
async def upload_manga_page(book_id: int, request: Request,
                            file: UploadFile = File(...),
                            user: sqlite3.Row = Depends(require_user),
                            db: sqlite3.Connection = Depends(get_db)):
    book = service.get_book(db, book_id)
    service.require_book_rights(user, book, "book.edit", "book.edit_own")
    data = await _read_limited(file, MAX_MANGA_PAGE_BYTES)
    ext = _image_ext(data)
    width, height = _image_size(data)
    name = _save_upload("images", data, ext)
    try:
        page_id = service.add_manga_page(db, user, book_id, name, width,
                                         height)
    except service.ServiceError:
        _remove_upload("images", name)
        raise
    audit(db, request, user["id"], "manga_page", f"#{book_id}")
    page = next(p for p in service.list_manga_pages(db, book_id)
                if p["id"] == page_id)
    return _page_out(page)


@app.delete("/api/manga/pages/{page_id}", response_model=schemas.Message,
            tags=["Манга"], summary="Удалить страницу манги")
def delete_manga_page(page_id: int, request: Request,
                      user: sqlite3.Row = Depends(require_user),
                      db: sqlite3.Connection = Depends(get_db)):
    name = service.delete_manga_page(db, user, page_id)
    _remove_upload("images", name)
    audit(db, request, user["id"], "manga_page_delete", f"#{page_id}")
    return {"detail": "Страница удалена"}


@app.get("/api/books/{book_id}/translations", tags=["Манга"],
         summary="Готовые переводы всех страниц на язык")
def manga_translations(book_id: int,
                       lang: str = Query(..., pattern="^(ru|kk|ky|en)$"),
                       user: Optional[sqlite3.Row] = Depends(
                           get_current_user),
                       db: sqlite3.Connection = Depends(get_db)):
    _readable_book(db, user, book_id)
    return {str(k): v for k, v in
            service.book_translations(db, book_id, lang).items()}


@app.post("/api/manga/pages/{page_id}/translate",
          response_model=list[schemas.TranslationBox], tags=["Манга"],
          summary="Перевести страницу ИИ (Gemini) с любого языка")
def translate_manga_page(page_id: int, data: schemas.TranslateIn,
                         request: Request,
                         user: sqlite3.Row = Depends(require_user),
                         db: sqlite3.Connection = Depends(get_db)):
    page = service.get_manga_page(db, page_id)
    _readable_book(db, user, page["book_id"])
    ready = service.get_page_translation(db, page_id, data.lang)
    if ready is not None:
        return ready            # перевод уже есть — ИИ не нужен
    _check_ai_rate(user["id"])
    path = os.path.join(UPLOAD_DIR, "images",
                        os.path.basename(page["file_name"]))
    with open(path, "rb") as fh:
        image = fh.read()
    media_type = {".jpg": "image/jpeg", ".png": "image/png",
                  ".webp": "image/webp"}[_image_ext(image)]
    boxes = ai.translate_page(image, media_type, data.lang)
    result = service.set_page_translation(db, page_id, data.lang, boxes)
    audit(db, request, user["id"], "manga_translate",
          f"страница #{page_id} -> {data.lang}")
    return result


# ===========================================================================
# Новости: обновления, конкурсы, марафоны (блок на главной)
# ===========================================================================
@app.get("/api/news", response_model=schemas.Page[schemas.NewsOut],
         tags=["Новости"], summary="Новости и конкурсы (пагинация)")
def news_list(page: int = Query(1, ge=1),
              page_size: int = Query(6, ge=1, le=50),
              kind: str = Query("", pattern="^(|update|contest|marathon|"
                                            "event)$"),
              db: sqlite3.Connection = Depends(get_db)):
    return service.list_news(db, page=page, page_size=page_size, kind=kind)


@app.post("/api/news", response_model=schemas.Message, status_code=201,
          tags=["Новости"], summary="Опубликовать новость (редактор)")
def news_add(data: schemas.NewsIn, request: Request,
             user: sqlite3.Row = Depends(require_perm("news.manage")),
             db: sqlite3.Connection = Depends(get_db)):
    news_id = service.add_news(db, user, **data.model_dump())
    audit(db, request, user["id"], "news_add", f"#{news_id}: {data.title}")
    return {"detail": "Новость опубликована"}


@app.delete("/api/news/{news_id}", response_model=schemas.Message,
            tags=["Новости"], summary="Удалить новость")
def news_delete(news_id: int, request: Request,
                user: sqlite3.Row = Depends(require_perm("news.manage")),
                db: sqlite3.Connection = Depends(get_db)):
    service.delete_news(db, user, news_id)
    audit(db, request, user["id"], "news_delete", f"#{news_id}")
    return {"detail": "Новость удалена"}


# ===========================================================================
# Живая презентация для защиты (только владелец): ноутбук у доски
# показывает слайды и сайт, телефон работает пультом. Оба экрана раз в
# ~0,7 с спрашивают /api/present/state, поэтому переключаются вместе.
# ===========================================================================
PRESENT_FILE = os.path.join(BASE_DIR, "app", "present", "slides.json")


@app.get("/api/present/slides", tags=["Презентация"],
         summary="Слайды и речь (только владелец)")
def present_slides(user: sqlite3.Row = Depends(
        require_perm("present.control"))):
    with open(PRESENT_FILE, encoding="utf-8") as fh:
        return Response(fh.read(), media_type="application/json")


@app.get("/api/present/state", response_model=schemas.PresentOut,
         tags=["Презентация"], summary="Текущий слайд и таймер")
def present_state(user: sqlite3.Row = Depends(
        require_perm("present.control")),
        db: sqlite3.Connection = Depends(get_db)):
    return service.get_present_state(db)


@app.post("/api/present/control", response_model=schemas.PresentOut,
          tags=["Презентация"], summary="Пульт: слайд, старт/пауза таймера")
def present_control(data: schemas.PresentIn, request: Request,
                    user: sqlite3.Row = Depends(
                        require_perm("present.control")),
                    db: sqlite3.Connection = Depends(get_db)):
    state = service.control_present(db, user, data.action, data.slide)
    if data.action in ("start", "reset"):
        audit(db, request, user["id"], "present_" + data.action)
    return state


@app.get("/present", include_in_schema=False, response_class=HTMLResponse)
def present_page():
    """Страница презентации. Сама по себе пустая: слайды она получает по
    API только с токеном владельца."""
    with open(os.path.join(TEMPLATES_DIR, "present.html"),
              encoding="utf-8") as fh:
        html = fh.read().replace("{{v}}", _asset_version())
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


# ===========================================================================
# Модерация и администрирование
# ===========================================================================
@app.get("/api/admin/users", tags=["Модерация"],
         summary="Пользователи (поиск, пагинация)")
def admin_users(query: str = Query("", max_length=64),
                page: int = Query(1, ge=1),
                page_size: int = Query(20, ge=1, le=100),
                user: sqlite3.Row = Depends(require_perm("user.list")),
                db: sqlite3.Connection = Depends(get_db)):
    return service.list_users(db, query=query, page=page,
                              page_size=page_size)


@app.post("/api/admin/users/{user_id}/role", response_model=schemas.Message,
          tags=["Модерация"], summary="Назначить роль (только владелец)")
def admin_set_role(user_id: int, data: schemas.RoleIn, request: Request,
                   user: sqlite3.Row = Depends(require_user),
                   db: sqlite3.Connection = Depends(get_db)):
    service.assign_role(db, user["role"], user_id, data.role)
    audit(db, request, user["id"], "role_change",
          f"пользователь #{user_id} -> {data.role}")
    return {"detail": "Роль назначена"}


@app.post("/api/admin/users/{user_id}/ban", response_model=schemas.Message,
          tags=["Модерация"], summary="Забанить (причина и срок)")
def admin_ban(user_id: int, data: schemas.BanIn, request: Request,
              user: sqlite3.Row = Depends(require_perm("user.ban")),
              db: sqlite3.Connection = Depends(get_db)):
    service.ban_user(db, user, user_id, data.reason, data.seconds)
    term = f"{data.seconds} с" if data.seconds else "навсегда"
    audit(db, request, user["id"], "ban",
          f"пользователь #{user_id}, {term}: {data.reason}")
    return {"detail": "Пользователь забанен"}


@app.post("/api/admin/users/{user_id}/unban", response_model=schemas.Message,
          tags=["Модерация"], summary="Разбанить")
def admin_unban(user_id: int, request: Request,
                user: sqlite3.Row = Depends(require_perm("user.ban")),
                db: sqlite3.Connection = Depends(get_db)):
    service.unban_user(db, user, user_id)
    audit(db, request, user["id"], "unban", f"пользователь #{user_id}")
    return {"detail": "Пользователь разбанен"}


@app.post("/api/admin/users/{user_id}/verify-student",
          response_model=schemas.Message, tags=["Модерация"],
          summary="Подтвердить статус студента вручную")
def admin_verify_student(user_id: int, request: Request,
                         user: sqlite3.Row = Depends(
                             require_perm("user.verify_student")),
                         db: sqlite3.Connection = Depends(get_db)):
    service.verify_student(db, user["role"], user_id)
    audit(db, request, user["id"], "student_verify",
          f"пользователь #{user_id}")
    return {"detail": "Студент подтверждён"}


@app.delete("/api/admin/users/{user_id}", response_model=schemas.Message,
            tags=["Модерация"], summary="Удалить аккаунт (только владелец)")
def admin_delete_user(user_id: int, request: Request,
                      user: sqlite3.Row = Depends(require_user),
                      db: sqlite3.Connection = Depends(get_db)):
    service.admin_delete_user(db, user, user_id)
    audit(db, request, user["id"], "user_delete", f"id {user_id}")
    return {"detail": "Аккаунт удалён"}


@app.get("/api/admin/unban-requests", tags=["Модерация"],
         summary="Заявки на разбан")
def list_unban(user: sqlite3.Row = Depends(require_perm("unban.manage")),
               db: sqlite3.Connection = Depends(get_db)):
    return service.list_unban_requests(db, user["role"])


@app.post("/api/admin/unban-requests/{request_id}/resolve",
          response_model=schemas.Message, tags=["Модерация"],
          summary="Одобрить или отклонить заявку на разбан")
def resolve_unban(request_id: int, data: schemas.ResolveIn, request: Request,
                  user: sqlite3.Row = Depends(require_perm("unban.manage")),
                  db: sqlite3.Connection = Depends(get_db)):
    service.resolve_unban_request(db, user, request_id, data.approve)
    audit(db, request, user["id"], "unban_resolve",
          f"заявка #{request_id}: {'одобрена' if data.approve else 'отказ'}")
    return {"detail": "Заявка обработана"}


@app.get("/api/admin/student-requests", tags=["Модерация"],
         summary="Заявки на статус студента")
def list_student_requests(user: sqlite3.Row = Depends(
        require_perm("user.verify_student")),
        db: sqlite3.Connection = Depends(get_db)):
    return service.list_student_requests(db, user["role"])


@app.get("/api/admin/student-requests/{request_id}/image",
         tags=["Модерация"], summary="Фото студбилета из заявки",
         response_class=FileResponse)
def student_request_image(request_id: int, user: sqlite3.Row = Depends(
        require_perm("user.verify_student")),
        db: sqlite3.Connection = Depends(get_db)):
    row = service.get_student_request(db, request_id)
    path = os.path.join(UPLOAD_DIR, "students",
                        os.path.basename(row["file_path"]))
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.post("/api/admin/student-requests/{request_id}/resolve",
          response_model=schemas.Message, tags=["Модерация"],
          summary="Одобрить или отклонить заявку студента")
def resolve_student(request_id: int, data: schemas.ResolveIn,
                    request: Request, user: sqlite3.Row = Depends(
                        require_perm("user.verify_student")),
                    db: sqlite3.Connection = Depends(get_db)):
    row = service.get_student_request(db, request_id)
    service.review_student_request(db, user, request_id, data.approve)
    # Фото студбилета больше не нужно — удаляем его (минимизация данных).
    _remove_upload("students", row["file_path"])
    audit(db, request, user["id"], "student_review",
          f"заявка #{request_id}: {'одобрена' if data.approve else 'отказ'}")
    return {"detail": "Заявка обработана"}


# ===========================================================================
# Журнал действий (усложнение варианта 11)
# ===========================================================================
@app.get("/api/admin/log", response_model=schemas.Page[schemas.LogOut],
         tags=["Журнал"], summary="Журнал действий с фильтрами")
def admin_log(user_id: Optional[int] = Query(None, ge=1),
              action: str = Query("", max_length=50),
              date_from: str = Query("", pattern=r"^(|\d{4}-\d{2}-\d{2})$"),
              date_to: str = Query("", pattern=r"^(|\d{4}-\d{2}-\d{2})$"),
              page: int = Query(1, ge=1),
              page_size: int = Query(50, ge=1, le=service.MAX_PAGE_SIZE),
              user: sqlite3.Row = Depends(require_perm("log.read")),
              db: sqlite3.Connection = Depends(get_db)):
    return service.list_log(db, page=page, page_size=page_size,
                            user_id=user_id, action=action,
                            date_from=date_from, date_to=date_to)


@app.get("/api/admin/log.csv", tags=["Журнал"],
         summary="Выгрузить журнал в CSV (до 10 000 записей)")
def admin_log_csv(request: Request,
                  user: sqlite3.Row = Depends(require_perm("log.read")),
                  db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT l.id, l.created_at, l.user_id, u.username, l.action, "
        "l.details, l.ip FROM action_log l LEFT JOIN users u ON "
        "u.id = l.user_id ORDER BY l.id DESC LIMIT 10000").fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "время (UTC)", "user_id", "логин", "действие",
                     "подробности", "ip"])
    writer.writerows([tuple(r) for r in rows])
    audit(db, request, user["id"], "log_export", f"{len(rows)} записей")
    # BOM нужен, чтобы Excel открыл кириллицу без «кракозябр».
    return Response("﻿" + buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=oqu-log.csv"})


# ===========================================================================
# Интерфейс
# ===========================================================================
@app.get("/api/i18n/{lang}", tags=["Интерфейс"], summary="Словарь переводов")
def get_translations(lang: str = Path(..., pattern="^(ru|kk|ky|en)$")):
    return i18n.get(lang)


@app.get("/api/health", tags=["Интерфейс"],
         summary="Проверка работоспособности (для хостинга)")
def health():
    return {"status": "ok", "version": __version__}


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _asset_version() -> str:
    """Короткий хэш файлов фронтенда: меняется при каждом их изменении."""
    digest = hashlib.sha1(__version__.encode())
    for root, _dirs, files in os.walk(STATIC_DIR):
        for name in sorted(files):
            digest.update(str(os.path.getmtime(os.path.join(root, name)))
                          .encode())
    return digest.hexdigest()[:10]


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def index():
    """Одностраничный интерфейс. Адреса файлов получают ?v=<версия>."""
    with open(os.path.join(TEMPLATES_DIR, "index.html"),
              encoding="utf-8") as fh:
        html = fh.read().replace("{{v}}", _asset_version())
    if PUBLIC_MODE:
        html = html.replace("<html ", '<html data-public="1" ', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
