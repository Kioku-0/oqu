"""Веб-интерфейс и REST API на FastAPI (вариант 11).

Это файл ``web.py`` из структуры методички — интерфейсный слой. Он только
принимает HTTP-запросы, вызывает бизнес-логику из :mod:`app.service` и
возвращает результат. Здесь реализованы три обязательные функции варианта 11:

* **FastAPI** как фреймворк REST API с автодокументацией OpenAPI/Swagger
  (``/docs``) и ReDoc (``/redoc``);
* **аутентификация JWT** (токены доступа и обновления, см. :mod:`app.security`);
* **постраничный вывод** (пагинация) списков книг, комментариев и журнала.

Усложнение варианта 11 — **журнал действий пользователей с временными
метками** — реализовано двумя способами: промежуточным слоем (middleware),
который фиксирует все изменяющие запросы, и явными записями для входа и чтения.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from fastapi import (Depends, FastAPI, HTTPException, Path, Query, Request,
                     status)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from app import i18n, schemas, security, service
from app.db import connect

# --- Конфигурация ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("LIBRARY_DB", os.path.join(BASE_DIR, "instance",
                                                    "library.sqlite"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

OPENAPI_TAGS = [
    {"name": "Аутентификация", "description": "Регистрация, вход, JWT-токены."},
    {"name": "Книги", "description": "Каталог, поиск, пагинация, чтение."},
    {"name": "Комментарии", "description": "Отзывы к книгам."},
    {"name": "Полка", "description": "Списки и прогресс чтения пользователя."},
    {"name": "Статистика", "description": "Статистика прочитанного."},
    {"name": "Администрирование", "description": "Роли, баны, журнал действий."},
    {"name": "Интерфейс", "description": "Переводы и страницы сайта."},
]

app = FastAPI(
    title="Электронная библиотека — REST API",
    description=(
        "REST API электронной библиотеки с документацией OpenAPI.\n\n"
        "Вариант 11: FastAPI, аутентификация JWT, постраничный вывод, "
        "журнал действий пользователей с временными метками.\n\n"
        "Университет имени Коркыт Ата, 2026."
    ),
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS,
    contact={"name": "Мұхан Надирхалиф, Хадизат", "email": "team@ex.kz"},
)

bearer_scheme = HTTPBearer(auto_error=False)


# --- Зависимости -----------------------------------------------------------
def get_db():
    """Открыть соединение с базой данных на время запроса и закрыть после."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = connect(DB_PATH)
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: sqlite3.Connection = Depends(get_db),
) -> Optional[sqlite3.Row]:
    """Определить пользователя по JWT-токену доступа (или ``None`` для гостя)."""
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
    """Требовать авторизованного и не забаненного пользователя."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Требуется авторизация")
    if service.is_banned(db, user["id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован")
    return user


def require_perm(permission: str):
    """Фабрика зависимостей: требовать у пользователя конкретное право."""
    def dependency(user: sqlite3.Row = Depends(require_user)) -> sqlite3.Row:
        service.require_permission(user["role"], permission)
        return user
    return dependency


# --- Обработка ошибок бизнес-логики ---------------------------------------
_ERROR_STATUS = {
    service.ValidationError: status.HTTP_400_BAD_REQUEST,
    service.AuthError: status.HTTP_401_UNAUTHORIZED,
    service.AccountLocked: status.HTTP_429_TOO_MANY_REQUESTS,
    service.Banned: status.HTTP_403_FORBIDDEN,
    service.PermissionDenied: status.HTTP_403_FORBIDDEN,
    service.NotFoundError: status.HTTP_404_NOT_FOUND,
    service.Conflict: status.HTTP_409_CONFLICT,
}


@app.exception_handler(service.ServiceError)
async def service_error_handler(request: Request, exc: service.ServiceError):
    """Преобразовать исключение бизнес-логики в корректный HTTP-ответ."""
    code = status.HTTP_400_BAD_REQUEST
    for exc_type, http_code in _ERROR_STATUS.items():
        if isinstance(exc, exc_type):
            code = http_code
            break
    return JSONResponse(status_code=code, content={"detail": str(exc)})


# --- Журнал действий: middleware (усложнение варианта 11) ------------------
@app.middleware("http")
async def action_log_middleware(request: Request, call_next):
    """Фиксировать все изменяющие запросы в журнале с временной меткой."""
    response = await call_next(request)
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and \
            request.url.path.startswith("/api") and response.status_code < 400:
        user_id = None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = security.decode_token(auth[7:])
                user_id = int(payload["sub"])
            except Exception:
                user_id = None
        ip = request.client.host if request.client else ""
        log_db = connect(DB_PATH)
        try:
            service.log_action(
                log_db, user_id, f"{request.method} {request.url.path}",
                details=f"status={response.status_code}", ip=ip,
            )
        finally:
            log_db.close()
    return response


# --- Вспомогательные функции -----------------------------------------------
def _book_out(row: sqlite3.Row) -> dict:
    return dict(row)


# ===========================================================================
# Аутентификация
# ===========================================================================
@app.post("/api/auth/register", response_model=schemas.UserOut,
          status_code=201, tags=["Аутентификация"],
          summary="Регистрация нового пользователя")
def register(data: schemas.RegisterIn, db: sqlite3.Connection = Depends(get_db)):
    uid = service.register_user(db, data.username, data.email, data.password,
                                language=data.language)
    return dict(service.get_user(db, uid))


@app.post("/api/auth/login", response_model=schemas.TokenOut,
          tags=["Аутентификация"], summary="Вход и получение JWT-токенов")
def login(data: schemas.LoginIn, request: Request,
          db: sqlite3.Connection = Depends(get_db)):
    user = service.authenticate(db, data.username, data.password)
    ip = request.client.host if request.client else ""
    service.log_action(db, user["id"], "login", "успешный вход", ip)
    return schemas.TokenOut(
        access_token=security.create_access_token(user["id"], user["role"]),
        refresh_token=security.create_refresh_token(user["id"]),
    )


@app.post("/api/auth/refresh", response_model=schemas.TokenOut,
          tags=["Аутентификация"], summary="Обновление токена доступа")
def refresh(data: schemas.RefreshIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        payload = security.decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError
        user = service.get_user(db, int(payload["sub"]))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Недействительный refresh-токен")
    return schemas.TokenOut(
        access_token=security.create_access_token(user["id"], user["role"]),
        refresh_token=security.create_refresh_token(user["id"]),
    )


@app.get("/api/auth/me", response_model=schemas.UserOut,
         tags=["Аутентификация"], summary="Текущий пользователь")
def me(user: sqlite3.Row = Depends(require_user)):
    return dict(user)


# ===========================================================================
# Книги
# ===========================================================================
@app.get("/api/books", response_model=schemas.Page[schemas.BookOut],
         tags=["Книги"], summary="Каталог книг с поиском и пагинацией")
def list_books(
    db: sqlite3.Connection = Depends(get_db),
    query: str = Query("", description="Поиск по названию или автору"),
    author: str = Query("", description="Фильтр по автору"),
    year: Optional[int] = Query(None, description="Фильтр по году"),
    genre: str = Query("", description="Фильтр по жанру"),
    language: str = Query("", description="Язык книги (ru/kk/en)"),
    sort: str = Query("title", pattern="^(title|author|year|created_at)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(service.DEFAULT_PAGE_SIZE, ge=1,
                           le=service.MAX_PAGE_SIZE),
):
    result = service.search_books(
        db, query=query, author=author, year=year, genre=genre,
        language=language, sort=sort, order=order, page=page,
        page_size=page_size)
    result["items"] = [_book_out(r) for r in result["items"]]
    return result


@app.get("/api/books/{book_id}", response_model=schemas.BookOut,
         tags=["Книги"], summary="Карточка книги")
def get_book(book_id: int = Path(..., ge=1),
             db: sqlite3.Connection = Depends(get_db)):
    return _book_out(service.get_book(db, book_id))


@app.get("/api/books/{book_id}/read", response_model=schemas.BookContentOut,
         tags=["Книги"], summary="Читать книгу (с учётом прав доступа)")
def read_book(book_id: int, request: Request,
              user: Optional[sqlite3.Row] = Depends(get_current_user),
              db: sqlite3.Connection = Depends(get_db)):
    book = service.get_book(db, book_id)
    if not service.can_read_book(user, book):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Эта книга доступна только по подписке/верификации")
    position = 0
    if user is not None:
        position = service.get_progress(db, user["id"], book_id)
        ip = request.client.host if request.client else ""
        service.log_action(db, user["id"], "read_book",
                           f"книга #{book_id}", ip)
    data = dict(book)
    data["position"] = position
    return data


@app.post("/api/books", response_model=schemas.BookOut, status_code=201,
          tags=["Книги"], summary="Добавить книгу (редактор/автор/владелец)")
def create_book(data: schemas.BookIn,
                user: sqlite3.Row = Depends(require_perm("book.add")),
                db: sqlite3.Connection = Depends(get_db)):
    bid = service.add_book(
        db, user["role"], data.title, data.author, year=data.year,
        language=data.language, genre=data.genre, description=data.description,
        content=data.content, cover_color=data.cover_color,
        is_paid=data.is_paid, paid_days=data.paid_days, added_by=user["id"])
    return _book_out(service.get_book(db, bid))


@app.patch("/api/books/{book_id}", response_model=schemas.BookOut,
           tags=["Книги"], summary="Изменить книгу (редактор/владелец)")
def update_book(book_id: int, data: schemas.BookPatch,
                user: sqlite3.Row = Depends(require_perm("book.edit")),
                db: sqlite3.Connection = Depends(get_db)):
    fields = {k: v for k, v in data.model_dump().items() if v is not None}
    service.edit_book(db, user["role"], book_id, **fields)
    return _book_out(service.get_book(db, book_id))


@app.delete("/api/books/{book_id}", response_model=schemas.Message,
            tags=["Книги"], summary="Удалить книгу (редактор/владелец)")
def remove_book(book_id: int,
                user: sqlite3.Row = Depends(require_perm("book.delete")),
                db: sqlite3.Connection = Depends(get_db)):
    service.delete_book(db, user["role"], book_id)
    return {"detail": "Книга удалена"}


# ===========================================================================
# Комментарии
# ===========================================================================
@app.get("/api/books/{book_id}/comments",
         response_model=list[schemas.CommentOut],
         tags=["Комментарии"], summary="Комментарии книги")
def get_comments(book_id: int, db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in service.list_comments(db, book_id)]


@app.post("/api/books/{book_id}/comments", response_model=schemas.CommentOut,
          status_code=201, tags=["Комментарии"], summary="Оставить комментарий")
def post_comment(book_id: int, data: schemas.CommentIn,
                 user: sqlite3.Row = Depends(require_user),
                 db: sqlite3.Connection = Depends(get_db)):
    cid = service.add_comment(db, user, book_id, data.text)
    row = db.execute(
        "SELECT c.*, u.username FROM comments c JOIN users u ON u.id = c.user_id "
        "WHERE c.id = ?", (cid,)).fetchone()
    return dict(row)


@app.delete("/api/comments/{comment_id}", response_model=schemas.Message,
            tags=["Комментарии"], summary="Удалить комментарий")
def remove_comment(comment_id: int,
                   user: sqlite3.Row = Depends(require_user),
                   db: sqlite3.Connection = Depends(get_db)):
    service.delete_comment(db, user, comment_id)
    return {"detail": "Комментарий удалён"}


# ===========================================================================
# Полка и прогресс чтения
# ===========================================================================
@app.get("/api/me/shelf", response_model=list[dict], tags=["Полка"],
         summary="Книги на полке пользователя")
def my_shelf(status_filter: str = Query("", alias="status"),
             user: sqlite3.Row = Depends(require_user),
             db: sqlite3.Connection = Depends(get_db)):
    rows = service.get_shelf(db, user["id"], status_filter or None)
    return [dict(r) for r in rows]


@app.put("/api/me/shelf/{book_id}", response_model=schemas.Message,
         tags=["Полка"], summary="Поставить статус книги на полке")
def set_shelf(book_id: int, data: schemas.ShelfIn,
              user: sqlite3.Row = Depends(require_perm("shelf.manage")),
              db: sqlite3.Connection = Depends(get_db)):
    service.set_shelf_status(db, user["id"], book_id, data.status)
    return {"detail": "Статус обновлён"}


@app.put("/api/me/progress/{book_id}", response_model=schemas.Message,
         tags=["Полка"], summary="Сохранить позицию чтения")
def set_progress(book_id: int, data: schemas.ProgressIn,
                 user: sqlite3.Row = Depends(require_perm("progress.save")),
                 db: sqlite3.Connection = Depends(get_db)):
    service.save_progress(db, user["id"], book_id, data.position)
    return {"detail": "Прогресс сохранён"}


# ===========================================================================
# Статистика
# ===========================================================================
@app.get("/api/stats/reading", tags=["Статистика"],
         summary="Статистика прочитанного по всем пользователям")
def stats_reading(db: sqlite3.Connection = Depends(get_db)):
    return service.reading_stats(db)


# ===========================================================================
# Администрирование и модерация
# ===========================================================================
@app.get("/api/admin/users", response_model=list[dict],
         tags=["Администрирование"], summary="Список пользователей")
def admin_users(user: sqlite3.Row = Depends(require_perm("user.ban")),
                db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT id, username, display_name, email, role, is_student, "
        "created_at FROM users ORDER BY id").fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["banned"] = service.is_banned(db, r["id"])
        result.append(item)
    return result


@app.post("/api/admin/users/{user_id}/role", response_model=schemas.Message,
          tags=["Администрирование"], summary="Назначить роль (владелец)")
def admin_set_role(user_id: int, data: schemas.RoleIn,
                   user: sqlite3.Row = Depends(require_user),
                   db: sqlite3.Connection = Depends(get_db)):
    service.assign_role(db, user["role"], user_id, data.role)
    return {"detail": "Роль назначена"}


@app.post("/api/admin/users/{user_id}/verify-student",
          response_model=schemas.Message, tags=["Администрирование"],
          summary="Подтвердить статус студента")
def admin_verify_student(
        user_id: int,
        user: sqlite3.Row = Depends(require_perm("user.verify_student")),
        db: sqlite3.Connection = Depends(get_db)):
    service.verify_student(db, user["role"], user_id)
    return {"detail": "Студент верифицирован"}


@app.post("/api/admin/users/{user_id}/ban", response_model=schemas.Message,
          tags=["Администрирование"], summary="Забанить пользователя")
def admin_ban(user_id: int, data: schemas.BanIn,
              user: sqlite3.Row = Depends(require_perm("user.ban")),
              db: sqlite3.Connection = Depends(get_db)):
    service.ban_user(db, user, user_id, data.reason, data.minutes)
    return {"detail": "Пользователь забанен"}


@app.post("/api/admin/users/{user_id}/unban", response_model=schemas.Message,
          tags=["Администрирование"], summary="Разбанить пользователя")
def admin_unban(user_id: int,
                user: sqlite3.Row = Depends(require_perm("user.ban")),
                db: sqlite3.Connection = Depends(get_db)):
    service.unban_user(db, user, user_id)
    return {"detail": "Пользователь разбанен"}


@app.get("/api/admin/log", response_model=schemas.Page[schemas.LogOut],
         tags=["Администрирование"],
         summary="Журнал действий пользователей (усложнение)")
def admin_log(user: sqlite3.Row = Depends(require_perm("log.read")),
              db: sqlite3.Connection = Depends(get_db),
              page: int = Query(1, ge=1),
              page_size: int = Query(50, ge=1, le=service.MAX_PAGE_SIZE)):
    total = db.execute("SELECT COUNT(*) AS n FROM action_log").fetchone()["n"]
    offset = (page - 1) * page_size
    rows = db.execute(
        "SELECT * FROM action_log ORDER BY id DESC LIMIT ? OFFSET ?",
        (page_size, offset)).fetchall()
    pages = (total + page_size - 1) // page_size
    return {"items": [dict(r) for r in rows], "total": total, "page": page,
            "page_size": page_size, "pages": pages}


@app.post("/api/unban-request", response_model=schemas.Message,
          tags=["Администрирование"], summary="Подать заявку на разбан")
def unban_request(data: schemas.UnbanRequestIn,
                  user: Optional[sqlite3.Row] = Depends(get_current_user),
                  db: sqlite3.Connection = Depends(get_db)):
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется авторизация")
    service.create_unban_request(db, user["id"], data.text)
    return {"detail": "Заявка отправлена"}


@app.get("/api/admin/unban-requests", response_model=list[dict],
         tags=["Администрирование"], summary="Список заявок на разбан")
def list_unban(user: sqlite3.Row = Depends(require_perm("unban.manage")),
               db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT r.*, u.username FROM unban_requests r "
        "JOIN users u ON u.id = r.user_id WHERE r.status = 'pending' "
        "ORDER BY r.id DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/unban-requests/{request_id}/resolve",
          response_model=schemas.Message, tags=["Администрирование"],
          summary="Одобрить/отклонить заявку на разбан")
def resolve_unban(request_id: int, data: schemas.ResolveIn,
                  user: sqlite3.Row = Depends(require_perm("unban.manage")),
                  db: sqlite3.Connection = Depends(get_db)):
    service.resolve_unban_request(db, user, request_id, data.approve)
    return {"detail": "Заявка обработана"}


# ===========================================================================
# Интерфейс: переводы, язык, страницы
# ===========================================================================
@app.get("/api/i18n/{lang}", tags=["Интерфейс"], summary="Словарь переводов")
def get_translations(lang: str):
    return i18n.get(lang)


@app.put("/api/me/language", response_model=schemas.Message, tags=["Интерфейс"],
         summary="Сохранить язык интерфейса")
def set_user_language(data: schemas.LanguageIn,
                      user: sqlite3.Row = Depends(require_user),
                      db: sqlite3.Connection = Depends(get_db)):
    service.set_language(db, user["id"], data.language)
    return {"detail": "Язык сохранён"}


# --- Статические файлы и главная страница ----------------------------------
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    """Отдать одностраничный веб-интерфейс библиотеки."""
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse({"detail": "Интерфейс не найден. См. /docs"},
                        status_code=200)
