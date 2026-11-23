"""Бизнес-логика библиотеки «Оқу» (не зависит от веб-фреймворка).

Это файл ``service.py`` из структуры методички (раздел 5.3) — «бизнес-логика
без интерфейса». Все функции принимают уже открытое соединение с базой данных
(:func:`app.db.connect`) и ничего не знают про HTTP, FastAPI или шаблоны.
Поэтому логику можно:

* полностью покрыть автотестами без запуска сервера (раздел 5.5);
* подключить к любому интерфейсу — веб, настольному или мобильному.

Безопасность (раздел 5.4): запросы параметризованы, пароли хранятся только
в виде хэша (:mod:`app.security`), входные данные проверяются, права доступа
построены по **принципу наименьших привилегий**.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app import profanity, security
from app.db import DATETIME_FMT

# ---------------------------------------------------------------------------
# Константы (без «магических чисел» — раздел 5.2)
# ---------------------------------------------------------------------------
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128
MAX_COMMENT_LEN = 2000
MAX_NOTE_LEN = 500
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_TAGS_PER_BOOK = 10
USERNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LANGUAGES = ("ru", "kk", "ky", "en")

AGREEMENT_VERSION = "1.0 от 20.11.2026"

VALID_ROLES = ("owner", "editor", "author", "moderator", "student", "user",
               "guest")
ASSIGNABLE_ROLES = ("editor", "author", "moderator", "student", "user")
SHELF_STATUSES = ("reading", "want", "dropped", "read")
BOOK_SORTS = ("title", "author", "year", "created_at", "rating", "popular")


# ---------------------------------------------------------------------------
# Исключения. Интерфейс перехватывает их и показывает понятное сообщение
# вместо аварийного завершения (та же идея, что BookingError в методичке).
# ---------------------------------------------------------------------------
class ServiceError(Exception):
    """Базовая ошибка бизнес-логики."""


class ValidationError(ServiceError):
    """Некорректные входные данные."""


class NotFoundError(ServiceError):
    """Запрошенный объект не найден."""


class AuthError(ServiceError):
    """Неверный логин или пароль."""


class AccountLockedError(ServiceError):
    """Аккаунт временно заблокирован из-за подбора пароля.

    ``retry_after`` — сколько секунд осталось до снятия блокировки
    (интерфейс показывает по нему обратный отсчёт).
    """

    def __init__(self, message: str, retry_after: int = 0) -> None:
        super().__init__(message)
        self.retry_after = max(0, int(retry_after))


class BannedError(ServiceError):
    """Пользователь забанен. Хранит причину и срок бана."""

    def __init__(self, message: str, reason: str = "",
                 until: Optional[str] = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.until = until


class PermissionDeniedError(ServiceError):
    """Недостаточно прав для действия."""


class ConflictError(ServiceError):
    """Конфликт данных (например, дубликат)."""


# ---------------------------------------------------------------------------
# Права доступа: принцип наименьших привилегий
# ---------------------------------------------------------------------------
_READER = {"book.read_free", "comment.write", "comment.edit_own",
           "comment.delete_own", "shelf.manage", "progress.save",
           "rating.set", "book.buy", "student.apply"}

PERMISSIONS: dict[str, set[str]] = {
    # Гость (без входа) только читает бесплатные книги.
    "guest": {"book.read_free"},
    "user": set(_READER),
    "student": (_READER - {"student.apply"}) | {"book.read_paid"},
    # Автор добавляет книги и управляет только своими.
    "author": _READER | {"book.add", "book.edit_own", "book.delete_own"},
    # Модератор работает с людьми и комментариями, но не с книгами.
    "moderator": _READER | {"comment.delete_any", "user.list", "user.ban",
                            "user.verify_student", "log.read",
                            "unban.manage"},
    # Редактор работает с книгами и комментариями к ним.
    "editor": _READER | {"book.read_paid", "book.add", "book.edit",
                         "book.delete", "comment.delete_any"},
    # Главный разработчик получает все права (см. has_permission).
    "owner": set(),
}

# Приписка к комментарию хранится кодом, а текст подставляет интерфейс на
# выбранном языке. "author_own" — автор пишет под своей книгой.
ROLE_BADGE = {"owner": "owner", "editor": "editor", "author": "author",
              "moderator": "moderator"}


def has_permission(role: str, permission: str) -> bool:
    """Проверить, есть ли у роли указанное право."""
    if role == "owner":
        return True
    return permission in PERMISSIONS.get(role, set())


def require_permission(role: str, permission: str) -> None:
    """Выбросить :class:`PermissionDeniedError`, если у роли нет права."""
    if not has_permission(role, permission):
        raise PermissionDeniedError(f"Недостаточно прав: {permission}")


def permissions_of(role: str) -> list[str]:
    """Список прав роли (интерфейс по нему показывает или прячет кнопки)."""
    if role == "owner":
        every: set[str] = set()
        for perms in PERMISSIONS.values():
            every |= perms
        return sorted(every | {"user.assign_role", "user.delete"})
    return sorted(PERMISSIONS.get(role, set()))


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_str() -> str:
    return _now().strftime(DATETIME_FMT)


def _parse(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FMT).replace(tzinfo=timezone.utc)


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    """Нормализовать номер и размер страницы для постраничного вывода."""
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    return page, page_size


def _paginate(db: sqlite3.Connection, select_sql: str, count_sql: str,
              args: list[Any], page: int, page_size: int) -> dict[str, Any]:
    """Выполнить запрос постранично и вернуть стандартный словарь страницы."""
    page, page_size = _clamp_page(page, page_size)
    total = db.execute(count_sql, args).fetchone()[0]
    rows = db.execute(select_sql + " LIMIT ? OFFSET ?",
                      (*args, page_size, (page - 1) * page_size)).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


# ---------------------------------------------------------------------------
# Журнал действий с временными метками (УСЛОЖНЕНИЕ варианта 11)
# ---------------------------------------------------------------------------
def log_action(db: sqlite3.Connection, user_id: Optional[int], action: str,
               details: str = "", ip: str = "") -> int:
    """Записать действие пользователя в журнал с временной меткой (UTC)."""
    cur = db.execute(
        "INSERT INTO action_log(user_id, action, details, ip, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, action[:100], details[:500], ip[:64], _now_str()),
    )
    db.commit()
    return cur.lastrowid


LOG_RETENTION_DAYS = 365


def purge_old_log(db: sqlite3.Connection,
                  days: int = LOG_RETENTION_DAYS) -> int:
    """Удалить записи журнала старше ``days`` дней (срок хранения из
    Политики конфиденциальности). Возвращает число удалённых записей."""
    border = (_now() - timedelta(days=int(days))).strftime(DATETIME_FMT)
    cur = db.execute("DELETE FROM action_log WHERE created_at < ?", (border,))
    db.commit()
    return cur.rowcount


def list_log(db: sqlite3.Connection, *, page: int = 1, page_size: int = 50,
             user_id: Optional[int] = None, action: str = "",
             date_from: str = "", date_to: str = "") -> dict[str, Any]:
    """Вернуть журнал постранично, с фильтрами по пользователю, типу и дате.

    ``date_from``/``date_to`` — строки ``ГГГГ-ММ-ДД`` (включительно).
    """
    where, args = [], []
    if user_id is not None:
        where.append("l.user_id = ?")
        args.append(int(user_id))
    if action:
        where.append("LOWER(l.action) LIKE ?")
        args.append(f"%{action.strip().lower()}%")
    if date_from:
        where.append("l.created_at >= ?")
        args.append(f"{date_from} 00:00:00")
    if date_to:
        where.append("l.created_at <= ?")
        args.append(f"{date_to} 23:59:59")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    return _paginate(
        db,
        "SELECT l.*, u.username FROM action_log l "
        f"LEFT JOIN users u ON u.id = l.user_id{clause} ORDER BY l.id DESC",
        f"SELECT COUNT(*) FROM action_log l{clause}",
        args, page, page_size)


# ---------------------------------------------------------------------------
# Пользователи и аутентификация
# ---------------------------------------------------------------------------
def _check_password(password: str) -> None:
    if not isinstance(password, str) or \
            not MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN:
        raise ValidationError(
            f"Пароль: от {MIN_PASSWORD_LEN} до {MAX_PASSWORD_LEN} символов")
    if not (re.search(r"[^\W\d_]", password) and re.search(r"\d", password)):
        raise ValidationError("Пароль должен содержать буквы и цифры")


def register_user(db: sqlite3.Connection, username: str, email: str,
                  password: str, role: str = "user", language: str = "ru",
                  display_name: str = "",
                  accept_terms: bool = True) -> int:
    """Зарегистрировать пользователя.

    Регистрация возможна только с согласием с пользовательским соглашением
    (``accept_terms``): дата и редакция соглашения сохраняются — так согласие
    можно подтвердить (Закон РК «О персональных данных и их защите»).
    """
    if not accept_terms:
        raise ValidationError("Необходимо принять пользовательское соглашение")
    username = (username or "").strip()
    email = (email or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValidationError(
            "Логин: 3–32 символа — буквы, цифры, точка, _ или -")
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise ValidationError("Некорректный адрес электронной почты")
    _check_password(password)
    if role not in VALID_ROLES or role == "guest":
        raise ValidationError("Недопустимая роль")
    if language not in LANGUAGES:
        raise ValidationError("Поддерживаются языки ru, kk, ky, en")
    display_name = (display_name or username).strip()[:64]
    try:
        cur = db.execute(
            "INSERT INTO users(username, email, password_hash, role, language,"
            " display_name, agreed_at, agreement_ver, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (username, email, security.hash_password(password), role,
             language, display_name, _now_str(), AGREEMENT_VERSION,
             _now_str()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise ConflictError("Пользователь с таким логином или почтой уже есть")
    return cur.lastrowid


def get_user(db: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    """Вернуть пользователя по id или выбросить :class:`NotFoundError`."""
    row = db.execute("SELECT * FROM users WHERE id = ?",
                     (user_id,)).fetchone()
    if row is None:
        raise NotFoundError("Пользователь не найден")
    return row


def get_user_by_username(db: sqlite3.Connection,
                         username: str) -> Optional[sqlite3.Row]:
    """Вернуть пользователя по логину (без учёта регистра) или ``None``."""
    return db.execute(
        "SELECT * FROM users WHERE LOWER(username) = ?",
        ((username or "").strip().lower(),)).fetchone()


def _check_credentials(db: sqlite3.Connection, username: str,
                       password: str) -> sqlite3.Row:
    """Проверить логин и пароль с защитой от подбора (брутфорса).

    После :data:`security.MAX_FAILED_ATTEMPTS` неудач подряд вход
    блокируется на :data:`security.LOCKOUT_SECONDS` секунд.
    """
    user = get_user_by_username(db, username)
    if user is None:
        # Хэшируем «впустую», чтобы по времени ответа нельзя было узнать,
        # существует ли такой логин (защита от перебора логинов).
        security.verify_password(password or "", security.DUMMY_HASH)
        raise AuthError("Неверный логин или пароль")

    if user["locked_until"] and _parse(user["locked_until"]) > _now():
        left = (_parse(user["locked_until"]) - _now()).total_seconds()
        raise AccountLockedError("Слишком много попыток. Повторите позже.",
                                 retry_after=int(left) + 1)

    if not security.verify_password(password or "", user["password_hash"]):
        attempts = user["failed_attempts"] + 1
        locked_until = None
        if attempts >= security.MAX_FAILED_ATTEMPTS:
            locked_until = (_now() + timedelta(
                seconds=security.LOCKOUT_SECONDS)).strftime(DATETIME_FMT)
            attempts = 0
        db.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? "
            "WHERE id = ?", (attempts, locked_until, user["id"]))
        db.commit()
        if locked_until:
            raise AccountLockedError(
                "Слишком много попыток. Повторите позже.",
                retry_after=security.LOCKOUT_SECONDS)
        raise AuthError("Неверный логин или пароль")

    db.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL "
               "WHERE id = ?", (user["id"],))
    db.commit()
    return get_user(db, user["id"])


def authenticate(db: sqlite3.Connection, username: str,
                 password: str) -> sqlite3.Row:
    """Войти: проверить пароль и отсутствие активного бана."""
    user = _check_credentials(db, username, password)
    ban = active_ban(db, user["id"])
    if ban is not None:
        raise BannedError("Аккаунт заблокирован", ban["reason"], ban["until"])
    return user


def change_password(db: sqlite3.Connection, user_id: int, old: str,
                    new: str) -> None:
    """Сменить пароль, подтвердив старый."""
    user = get_user(db, user_id)
    if not security.verify_password(old or "", user["password_hash"]):
        raise AuthError("Текущий пароль указан неверно")
    _check_password(new)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (security.hash_password(new), user_id))
    db.commit()


def update_profile(db: sqlite3.Connection, user_id: int,
                   display_name: str) -> None:
    """Изменить отображаемое имя."""
    display_name = (display_name or "").strip()
    if not 1 <= len(display_name) <= 64:
        raise ValidationError("Имя: от 1 до 64 символов")
    get_user(db, user_id)
    db.execute("UPDATE users SET display_name = ? WHERE id = ?",
               (display_name, user_id))
    db.commit()


def delete_account(db: sqlite3.Connection, user_id: int,
                   password: str) -> None:
    """Удалить собственный аккаунт (с подтверждением паролем).

    Удаляются профиль, полки, прогресс, оценки и комментарии пользователя
    (каскадно). Главного разработчика удалить нельзя — иначе система
    останется без администратора.
    """
    user = get_user(db, user_id)
    if not security.verify_password(password or "", user["password_hash"]):
        raise AuthError("Пароль указан неверно")
    if user["role"] == "owner":
        raise PermissionDeniedError(
            "Аккаунт главного разработчика удалить нельзя")
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


def admin_delete_user(db: sqlite3.Connection, actor: sqlite3.Row,
                      target_id: int) -> None:
    """Удалить чужой аккаунт (только главный разработчик)."""
    if actor["role"] != "owner":
        raise PermissionDeniedError("Удалять аккаунты может только владелец")
    target = get_user(db, target_id)
    if target["role"] == "owner":
        raise PermissionDeniedError("Нельзя удалить главного разработчика")
    db.execute("DELETE FROM users WHERE id = ?", (target_id,))
    db.commit()


def assign_role(db: sqlite3.Connection, actor_role: str, target_id: int,
                new_role: str) -> None:
    """Назначить роль (только главный разработчик)."""
    if actor_role != "owner":
        raise PermissionDeniedError(
            "Выдавать роли может только главный разработчик")
    if new_role not in ASSIGNABLE_ROLES:
        raise ValidationError("Недопустимая роль")
    target = get_user(db, target_id)
    if target["role"] == "owner":
        raise PermissionDeniedError("Роль главного разработчика не меняется")
    is_student = 1 if new_role == "student" else target["is_student"]
    db.execute("UPDATE users SET role = ?, is_student = ? WHERE id = ?",
               (new_role, is_student, target_id))
    db.commit()


def verify_student(db: sqlite3.Connection, actor_role: str,
                   target_id: int) -> None:
    """Подтвердить статус студента (пользователь становится студентом)."""
    require_permission(actor_role, "user.verify_student")
    target = get_user(db, target_id)
    role = "student" if target["role"] == "user" else target["role"]
    db.execute("UPDATE users SET is_student = 1, role = ? WHERE id = ?",
               (role, target_id))
    db.commit()


def set_language(db: sqlite3.Connection, user_id: int, language: str) -> None:
    """Сохранить язык интерфейса пользователя."""
    if language not in LANGUAGES:
        raise ValidationError("Поддерживаются языки ru, kk, ky, en")
    get_user(db, user_id)
    db.execute("UPDATE users SET language = ? WHERE id = ?",
               (language, user_id))
    db.commit()


def list_users(db: sqlite3.Connection, *, query: str = "", page: int = 1,
               page_size: int = 20) -> dict[str, Any]:
    """Список пользователей с поиском и пагинацией (для модерации)."""
    where, args = "", []
    if query:
        where = (" WHERE LOWER(username) LIKE ? OR LOWER(display_name) "
                 "LIKE ? OR LOWER(email) LIKE ?")
        pattern = f"%{query.strip().lower()}%"
        args = [pattern, pattern, pattern]
    result = _paginate(
        db,
        "SELECT id, username, display_name, email, role, is_student, "
        f"created_at FROM users{where} ORDER BY id",
        f"SELECT COUNT(*) FROM users{where}", args, page, page_size)
    for item in result["items"]:
        ban = active_ban(db, item["id"])
        item["banned"] = ban is not None
        item["ban_reason"] = ban["reason"] if ban else ""
        item["ban_until"] = ban["until"] if ban else None
    return result


# ---------------------------------------------------------------------------
# Книги
# ---------------------------------------------------------------------------
# Узоры обложек. "auto" — интерфейс подбирает узор сам по номеру книги.
COVER_PATTERNS = ("auto", "plain", "stripes", "diagonal", "dots", "grid",
                  "waves", "ornament", "frame", "band", "sun")


def _validate_book(title: str, author: str, year: Optional[int],
                   language: str, cover_color: str, price: int,
                   cover_pattern: str = "auto") -> None:
    if cover_pattern not in COVER_PATTERNS:
        raise ValidationError("Неизвестный узор обложки")
    if not (title or "").strip():
        raise ValidationError("Название книги не должно быть пустым")
    if not (author or "").strip():
        raise ValidationError("Укажите автора книги")
    if year is not None and not 0 <= int(year) <= 2100:
        raise ValidationError("Год должен быть в диапазоне 0–2100")
    if language not in LANGUAGES:
        raise ValidationError("Язык книги: ru, kk, ky или en")
    if not COLOR_RE.match(cover_color or ""):
        raise ValidationError("Цвет обложки в формате #RRGGBB")
    if int(price) < 0:
        raise ValidationError("Цена не может быть отрицательной")


def add_book(db: sqlite3.Connection, actor_role: str, title: str, author: str,
             *, year: Optional[int] = None, language: str = "ru",
             genre: str = "", description: str = "", content: str = "",
             cover_color: str = "#1f5f4a", cover_pattern: str = "auto",
             is_paid: bool = False, price: int = 0,
             paid_days: Optional[int] = None, external_url: str = "",
             tags: Optional[list[str]] = None,
             added_by: Optional[int] = None) -> int:
    """Добавить книгу (право ``book.add``).

    Платная книга становится бесплатной через ``paid_days`` дней —
    «платное всегда на время».
    """
    require_permission(actor_role, "book.add")
    _validate_book(title, author, year, language, cover_color, price,
                   cover_pattern)
    if is_paid and not paid_days:
        raise ValidationError("Для платной книги укажите срок платности")
    if external_url and not external_url.startswith(("https://", "http://")):
        raise ValidationError("Ссылка должна начинаться с http(s)://")
    paid_until = None
    if is_paid:
        paid_until = (_now() + timedelta(days=int(paid_days))
                      ).strftime(DATETIME_FMT)
    cur = db.execute(
        "INSERT INTO books(title, author, year, language, genre, description,"
        " content, external_url, cover_color, cover_pattern, is_paid, price,"
        " paid_until, added_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title.strip(), author.strip(), year, language,
         (genre or "").strip().lower(), description or "", content or "",
         external_url or "", cover_color, cover_pattern, 1 if is_paid else 0,
         int(price) if is_paid else 0, paid_until, added_by, _now_str()),
    )
    db.commit()
    if tags:
        set_book_tags(db, cur.lastrowid, tags)
    return cur.lastrowid


def get_book(db: sqlite3.Connection, book_id: int) -> sqlite3.Row:
    """Вернуть книгу по id или выбросить :class:`NotFoundError`."""
    row = db.execute("SELECT * FROM books WHERE id = ?",
                     (book_id,)).fetchone()
    if row is None:
        raise NotFoundError("Книга не найдена")
    return row


def require_book_rights(actor: sqlite3.Row | str, book: sqlite3.Row,
                        any_perm: str, own_perm: str) -> None:
    """Разрешить действие над любой книгой или только над своей."""
    role = actor if isinstance(actor, str) else actor["role"]
    if has_permission(role, any_perm):
        return
    if not isinstance(actor, str) and has_permission(role, own_perm) \
            and book["added_by"] == actor["id"]:
        return
    raise PermissionDeniedError(f"Недостаточно прав: {any_perm}")


def edit_book(db: sqlite3.Connection, actor: sqlite3.Row | str, book_id: int,
              **fields: Any) -> None:
    """Изменить книгу: редактор — любую, автор — только свою.

    ``actor`` — строка с ролью или строка пользователя из БД.
    """
    book = get_book(db, book_id)
    require_book_rights(actor, book, "book.edit", "book.edit_own")
    allowed = {"title", "author", "year", "language", "genre",
               "description", "content", "cover_color", "cover_pattern",
               "external_url"}
    updates = {k: v for k, v in fields.items()
               if k in allowed and v is not None}
    tags = fields.get("tags")
    if not updates and tags is None:
        raise ValidationError("Нет полей для обновления")
    merged = {**dict(book), **updates}
    _validate_book(merged["title"], merged["author"], merged["year"],
                   merged["language"], merged["cover_color"], book["price"],
                   merged["cover_pattern"] or "auto")
    if "genre" in updates:
        updates["genre"] = updates["genre"].strip().lower()
    if updates:
        # Имена столбцов берутся только из белого списка allowed.
        cols = ", ".join(f"{k} = ?" for k in updates)
        db.execute(f"UPDATE books SET {cols} WHERE id = ?",
                   (*updates.values(), book_id))
        db.commit()
    if tags is not None:
        set_book_tags(db, book_id, tags)


def set_book_file(db: sqlite3.Connection, book_id: int,
                  file_path: Optional[str]) -> None:
    """Привязать к книге PDF-скан (имя файла в хранилище) или отвязать."""
    get_book(db, book_id)
    db.execute("UPDATE books SET file_path = ? WHERE id = ?",
               (file_path, book_id))
    db.commit()


def set_book_cover(db: sqlite3.Connection, book_id: int,
                   file_name: Optional[str]) -> Optional[str]:
    """Поставить картинку обложки (или убрать). Возвращает имя старой."""
    book = get_book(db, book_id)
    db.execute("UPDATE books SET cover_image = ? WHERE id = ?",
               (file_name, book_id))
    db.commit()
    return book["cover_image"]


MAX_IMAGES_PER_BOOK = 60


def add_book_image(db: sqlite3.Connection, book_id: int,
                   file_name: str) -> str:
    """Зарегистрировать иллюстрацию книги. Возвращает разметку для текста.

    В тексте книги иллюстрация вставляется отдельной строкой
    ``![подпись](img:<имя>)`` — читалка показывает её картинкой.
    """
    get_book(db, book_id)
    count = db.execute("SELECT COUNT(*) FROM book_images WHERE book_id = ?",
                       (book_id,)).fetchone()[0]
    if count >= MAX_IMAGES_PER_BOOK:
        raise ValidationError(f"Не больше {MAX_IMAGES_PER_BOOK} иллюстраций "
                              "в одной книге")
    db.execute("INSERT INTO book_images(book_id, file_name, created_at) "
               "VALUES (?, ?, ?)", (book_id, file_name, _now_str()))
    db.commit()
    return f"![](img:{file_name})"


def book_files(db: sqlite3.Connection, book_id: int) -> list[str]:
    """Все картинки книги (обложка и иллюстрации) — чтобы удалить файлы."""
    names = [r[0] for r in db.execute(
        "SELECT file_name FROM book_images WHERE book_id = ?", (book_id,))]
    cover = db.execute("SELECT cover_image FROM books WHERE id = ?",
                       (book_id,)).fetchone()
    if cover and cover[0]:
        names.append(cover[0])
    return names


def delete_book(db: sqlite3.Connection, actor: sqlite3.Row | str,
                book_id: int) -> Optional[str]:
    """Удалить книгу. Возвращает имя PDF-файла, чтобы удалить и его."""
    book = get_book(db, book_id)
    require_book_rights(actor, book, "book.delete", "book.delete_own")
    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()
    return book["file_path"]


# Поля книги для списков: без полного текста, чтобы ответы были лёгкими.
_LIST_COLUMNS = (
    "b.id, b.title, b.author, b.year, b.language, b.genre, b.description, "
    "b.cover_color, b.cover_pattern, b.cover_image, b.is_paid, b.price, "
    "b.paid_until, b.added_by, "
    "b.external_url, b.created_at, "
    "(b.file_path IS NOT NULL) AS has_file, (b.content <> '') AS has_text, "
    "(SELECT ROUND(AVG(r.value), 1) FROM ratings r WHERE r.book_id = b.id)"
    " AS rating, "
    "(SELECT COUNT(*) FROM ratings r WHERE r.book_id = b.id) AS rating_count,"
    " (SELECT COUNT(*) FROM shelf s WHERE s.book_id = b.id"
    " AND s.status = 'read') AS reads"
)

_SORT_SQL = {
    "title": "natural_key(b.title)", "author": "b.author", "year": "b.year",
    "created_at": "b.created_at", "rating": "rating", "popular": "reads",
}


def search_books(db: sqlite3.Connection, *, query: str = "",
                 author: str = "", year: Optional[int] = None,
                 year_from: Optional[int] = None,
                 year_to: Optional[int] = None, genre: str = "",
                 language: str = "", tag: str = "", access: str = "",
                 sort: str = "title", order: str = "asc", page: int = 1,
                 page_size: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    """Найти книги с поиском, фильтрами, сортировкой и пагинацией.

    * ``query`` ищется по названию, автору и описанию (без учёта регистра);
    * фильтры: автор, год или диапазон лет, жанр, язык, тег,
      доступ (``free``/``paid``);
    * ``sort`` — одно из :data:`BOOK_SORTS`; имя столбца берётся только из
      белого списка, что исключает SQL-инъекцию через сортировку;
    * постраничный вывод — обязательная функция варианта 11.
    """
    where: list[str] = []
    args: list[Any] = []
    if query:
        where.append("(LOWER(b.title) LIKE ? OR LOWER(b.author) LIKE ? "
                     "OR LOWER(b.description) LIKE ?)")
        pattern = f"%{query.strip().lower()}%"
        args += [pattern, pattern, pattern]
    if author:
        where.append("LOWER(b.author) LIKE ?")
        args.append(f"%{author.strip().lower()}%")
    if year is not None:
        where.append("b.year = ?")
        args.append(int(year))
    if year_from is not None:
        where.append("b.year >= ?")
        args.append(int(year_from))
    if year_to is not None:
        where.append("b.year <= ?")
        args.append(int(year_to))
    if genre:
        where.append("b.genre = ?")
        args.append(genre.strip().lower())
    if language:
        where.append("b.language = ?")
        args.append(language)
    if tag:
        where.append("b.id IN (SELECT bt.book_id FROM book_tags bt JOIN tags t"
                     " ON t.id = bt.tag_id WHERE t.name = ?)")
        args.append(tag.strip().lower())
    if access in ("free", "paid"):
        # Платная книга с истёкшим сроком считается бесплатной.
        paid_now = "(b.is_paid = 1 AND (b.paid_until IS NULL OR " \
                   "b.paid_until > ?))"
        where.append(paid_now if access == "paid" else f"NOT {paid_now}")
        args.append(_now_str())

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sort_col = _SORT_SQL.get(sort, "b.title")
    sort_dir = "DESC" if str(order).lower() == "desc" else "ASC"
    result = _paginate(
        db,
        f"SELECT {_LIST_COLUMNS} FROM books b{clause} "
        f"ORDER BY {sort_col} IS NULL, {sort_col} {sort_dir}, b.id",
        f"SELECT COUNT(*) FROM books b{clause}", args, page, page_size)
    for item in result["items"]:
        item["is_paid"] = is_paid_now(item)
    return result


def get_book_details(db: sqlite3.Connection, book_id: int) -> dict[str, Any]:
    """Карточка книги: поля без текста + рейтинг, теги, прочтения."""
    row = db.execute(f"SELECT {_LIST_COLUMNS} FROM books b WHERE b.id = ?",
                     (book_id,)).fetchone()
    if row is None:
        raise NotFoundError("Книга не найдена")
    data = dict(row)
    data["is_paid"] = is_paid_now(data)
    data["tags"] = book_tags(db, book_id)
    return data


def random_books(db: sqlite3.Connection, genre: str = "",
                 limit: int = 24) -> list[dict[str, Any]]:
    """Случайные книги для «режима книжного шкафа» (при желании по жанру)."""
    limit = max(1, min(int(limit), 60))
    args: list[Any] = []
    clause = ""
    if genre:
        clause = " WHERE b.genre = ?"
        args.append(genre.strip().lower())
    rows = db.execute(f"SELECT {_LIST_COLUMNS} FROM books b{clause} "
                      "ORDER BY RANDOM() LIMIT ?", (*args, limit)).fetchall()
    return [dict(r) for r in rows]


def list_genres(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """Жанры с количеством книг."""
    rows = db.execute("SELECT genre AS name, COUNT(*) AS count FROM books "
                      "WHERE genre <> '' GROUP BY genre ORDER BY count DESC, "
                      "genre").fetchall()
    return [dict(r) for r in rows]


def is_paid_now(book: sqlite3.Row | dict) -> bool:
    """Платная ли книга прямо сейчас (после ``paid_until`` — бесплатна)."""
    if not book["is_paid"]:
        return False
    return not (book["paid_until"] and _parse(book["paid_until"]) <= _now())


def can_read_book(user: Optional[sqlite3.Row], book: sqlite3.Row,
                  purchased: bool = False) -> bool:
    """Может ли пользователь читать книгу.

    Бесплатную книгу читают все, включая гостей. Платную (пока не истёк
    срок) — владелец и редактор, подтверждённые студенты, автор книги и
    тот, кто её купил.
    """
    if not is_paid_now(book):
        return True
    if user is None:
        return False
    if purchased or user["role"] in ("owner", "editor"):
        return True
    if user["is_student"] and has_permission(user["role"], "book.read_paid"):
        return True
    return book["added_by"] is not None and user["id"] == book["added_by"]


def has_purchased(db: sqlite3.Connection, user_id: int, book_id: int) -> bool:
    """Купил ли пользователь книгу."""
    return db.execute("SELECT 1 FROM purchases WHERE user_id = ? AND "
                      "book_id = ?", (user_id, book_id)).fetchone() is not None


def user_can_read(db: sqlite3.Connection, user: Optional[sqlite3.Row],
                  book: sqlite3.Row) -> bool:
    """Обёртка над :func:`can_read_book`, учитывающая покупки."""
    bought = user is not None and has_purchased(db, user["id"], book["id"])
    return can_read_book(user, book, purchased=bought)


def buy_book(db: sqlite3.Connection, user: sqlite3.Row, book_id: int) -> int:
    """Купить платную книгу (учебная имитация: деньги не списываются).

    :returns: цена в тенге, зафиксированная в покупке.
    """
    require_permission(user["role"], "book.buy")
    book = get_book(db, book_id)
    if not is_paid_now(book):
        raise ConflictError("Книга бесплатная — покупать не нужно")
    if user_can_read(db, user, book):
        raise ConflictError("У вас уже есть доступ к этой книге")
    db.execute("INSERT INTO purchases(user_id, book_id, price, created_at) "
               "VALUES (?, ?, ?, ?)",
               (user["id"], book_id, book["price"], _now_str()))
    db.commit()
    return book["price"]


# ---------------------------------------------------------------------------
# Комментарии и цензура
# ---------------------------------------------------------------------------
def censor_profanity(text: str) -> str:
    """Замаскировать бранные слова звёздочками, оставив первую букву.

    Словарь и правила поиска — в модуле :mod:`app.profanity`. Цензура
    действует для всех ролей, включая главного разработчика.
    """
    return profanity.censor(text)


def _clean_comment(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValidationError("Комментарий не должен быть пустым")
    if len(text) > MAX_COMMENT_LEN:
        raise ValidationError(f"Комментарий не длиннее {MAX_COMMENT_LEN} "
                              "символов")
    return censor_profanity(text)


def add_comment(db: sqlite3.Connection, user: sqlite3.Row, book_id: int,
                text: str) -> int:
    """Добавить комментарий (право ``comment.write``).

    Текст проходит цензуру; приписка ставится по роли. Автор под своей
    книгой получает приписку «автор этой книги».
    """
    require_permission(user["role"], "comment.write")
    clean = _clean_comment(text)
    book = get_book(db, book_id)
    badge = ROLE_BADGE.get(user["role"], "")
    if book["added_by"] == user["id"] and user["role"] == "author":
        badge = "author_own"
    cur = db.execute(
        "INSERT INTO comments(book_id, user_id, text, badge, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (book_id, user["id"], clean, badge, _now_str()))
    db.commit()
    return cur.lastrowid


def _get_comment(db: sqlite3.Connection, comment_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM comments WHERE id = ? AND is_deleted = 0",
                     (comment_id,)).fetchone()
    if row is None:
        raise NotFoundError("Комментарий не найден")
    return row


def edit_comment(db: sqlite3.Connection, user: sqlite3.Row, comment_id: int,
                 text: str) -> None:
    """Отредактировать свой комментарий (чужие редактировать нельзя)."""
    row = _get_comment(db, comment_id)
    if row["user_id"] != user["id"]:
        raise PermissionDeniedError(
            "Редактировать можно только свой комментарий")
    require_permission(user["role"], "comment.edit_own")
    db.execute("UPDATE comments SET text = ?, edited_at = ? WHERE id = ?",
               (_clean_comment(text), _now_str(), comment_id))
    db.commit()


def delete_comment(db: sqlite3.Connection, user: sqlite3.Row,
                   comment_id: int) -> None:
    """Удалить комментарий: свой или любой (модератор/редактор)."""
    row = _get_comment(db, comment_id)
    perm = ("comment.delete_own" if row["user_id"] == user["id"]
            else "comment.delete_any")
    require_permission(user["role"], perm)
    db.execute("UPDATE comments SET is_deleted = 1 WHERE id = ?",
               (comment_id,))
    db.commit()


def list_comments(db: sqlite3.Connection, book_id: int, page: int = 1,
                  page_size: int = 20) -> dict[str, Any]:
    """Комментарии книги постранично, новые сверху."""
    return _paginate(
        db,
        "SELECT c.id, c.book_id, c.user_id, c.text, c.badge, c.edited_at, "
        "c.created_at, u.username, u.display_name FROM comments c "
        "JOIN users u ON u.id = c.user_id WHERE c.book_id = ? AND "
        "c.is_deleted = 0 ORDER BY c.id DESC",
        "SELECT COUNT(*) FROM comments WHERE book_id = ? AND is_deleted = 0",
        [book_id], page, page_size)


# ---------------------------------------------------------------------------
# Оценки
# ---------------------------------------------------------------------------
def rate_book(db: sqlite3.Connection, user: sqlite3.Row, book_id: int,
              value: int) -> None:
    """Поставить книге оценку 1–5 (повторная оценка заменяет прежнюю)."""
    require_permission(user["role"], "rating.set")
    value = int(value)
    if not 1 <= value <= 5:
        raise ValidationError("Оценка — от 1 до 5")
    get_book(db, book_id)
    db.execute("INSERT INTO ratings(user_id, book_id, value, updated_at) "
               "VALUES (?, ?, ?, ?) ON CONFLICT(user_id, book_id) DO UPDATE "
               "SET value = excluded.value, updated_at = excluded.updated_at",
               (user["id"], book_id, value, _now_str()))
    db.commit()


def user_rating(db: sqlite3.Connection, user_id: int,
                book_id: int) -> Optional[int]:
    """Оценка, которую пользователь поставил книге (или ``None``)."""
    row = db.execute("SELECT value FROM ratings WHERE user_id = ? AND "
                     "book_id = ?", (user_id, book_id)).fetchone()
    return row["value"] if row else None


# ---------------------------------------------------------------------------
# Полка, прогресс чтения и закладки
# ---------------------------------------------------------------------------
def set_shelf_status(db: sqlite3.Connection, user_id: int, book_id: int,
                     status: Optional[str]) -> None:
    """Поставить статус книги на полке; ``None`` — убрать с полки."""
    get_book(db, book_id)
    if status is None:
        db.execute("DELETE FROM shelf WHERE user_id = ? AND book_id = ?",
                   (user_id, book_id))
        db.commit()
        return
    if status not in SHELF_STATUSES:
        raise ValidationError("Недопустимый статус полки")
    db.execute(
        "INSERT INTO shelf(user_id, book_id, status, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(user_id, book_id) DO UPDATE "
        "SET status = excluded.status, updated_at = excluded.updated_at",
        (user_id, book_id, status, _now_str()))
    db.commit()


def shelf_status(db: sqlite3.Connection, user_id: int,
                 book_id: int) -> Optional[str]:
    """Статус книги на полке пользователя (или ``None``)."""
    row = db.execute("SELECT status FROM shelf WHERE user_id = ? AND "
                     "book_id = ?", (user_id, book_id)).fetchone()
    return row["status"] if row else None


def get_shelf(db: sqlite3.Connection, user_id: int,
              status: Optional[str] = None) -> list[dict[str, Any]]:
    """Книги на полке пользователя (при необходимости — по статусу)."""
    if status is not None and status not in SHELF_STATUSES:
        raise ValidationError("Недопустимый статус полки")
    sql = (f"SELECT s.status, s.updated_at AS shelved_at, {_LIST_COLUMNS}, "
           "p.position FROM shelf s JOIN books b ON b.id = s.book_id "
           "LEFT JOIN reading_progress p ON p.user_id = s.user_id AND "
           "p.book_id = s.book_id WHERE s.user_id = ?")
    args: list[Any] = [user_id]
    if status:
        sql += " AND s.status = ?"
        args.append(status)
    rows = db.execute(sql + " ORDER BY s.updated_at DESC", args).fetchall()
    return [dict(r) for r in rows]


def shelf_counts(db: sqlite3.Connection, user_id: int) -> dict[str, int]:
    """Сколько книг в каждом списке полки."""
    counts = {s: 0 for s in SHELF_STATUSES}
    for row in db.execute("SELECT status, COUNT(*) AS n FROM shelf WHERE "
                          "user_id = ? GROUP BY status", (user_id,)):
        counts[row["status"]] = row["n"]
    return counts


def save_progress(db: sqlite3.Connection, user_id: int, book_id: int,
                  position: int) -> None:
    """Сохранить место чтения. Книга сама попадает в список «Читаю»."""
    position = int(position)
    if position < 0:
        raise ValidationError("Позиция не может быть отрицательной")
    get_book(db, book_id)
    db.execute(
        "INSERT INTO reading_progress(user_id, book_id, position, updated_at)"
        " VALUES (?, ?, ?, ?) ON CONFLICT(user_id, book_id) DO UPDATE "
        "SET position = excluded.position, updated_at = excluded.updated_at",
        (user_id, book_id, position, _now_str()))
    # Начал читать книгу из списка «Буду читать» (или вне полки) —
    # она переходит в «Читаю» и появляется в «Продолжить чтение».
    if shelf_status(db, user_id, book_id) in (None, "want"):
        db.execute(
            "INSERT INTO shelf(user_id, book_id, status, updated_at) "
            "VALUES (?, ?, 'reading', ?) ON CONFLICT(user_id, book_id) "
            "DO UPDATE SET status = 'reading', "
            "updated_at = excluded.updated_at",
            (user_id, book_id, _now_str()))
    db.commit()


def get_progress(db: sqlite3.Connection, user_id: int, book_id: int) -> int:
    """Сохранённое место чтения (0, если ещё не читал)."""
    row = db.execute("SELECT position FROM reading_progress WHERE user_id = ?"
                     " AND book_id = ?", (user_id, book_id)).fetchone()
    return row["position"] if row else 0


def continue_reading(db: sqlite3.Connection, user_id: int,
                     limit: int = 6) -> list[dict[str, Any]]:
    """Книги «продолжить чтение»: недочитанные, последние сверху."""
    rows = db.execute(
        f"SELECT p.position, p.updated_at AS read_at, {_LIST_COLUMNS} "
        "FROM reading_progress p JOIN books b ON b.id = p.book_id "
        "LEFT JOIN shelf s ON s.user_id = p.user_id AND s.book_id = p.book_id"
        " WHERE p.user_id = ? AND COALESCE(s.status, 'reading') = 'reading' "
        "ORDER BY p.updated_at DESC LIMIT ?",
        (user_id, max(1, min(int(limit), 50)))).fetchall()
    return [dict(r) for r in rows]


def add_bookmark(db: sqlite3.Connection, user_id: int, book_id: int,
                 position: int, note: str = "") -> int:
    """Добавить закладку с заметкой на месте чтения."""
    position = int(position)
    if position < 0:
        raise ValidationError("Позиция не может быть отрицательной")
    note = (note or "").strip()
    if len(note) > MAX_NOTE_LEN:
        raise ValidationError(f"Заметка не длиннее {MAX_NOTE_LEN} символов")
    get_book(db, book_id)
    cur = db.execute("INSERT INTO bookmarks(user_id, book_id, position, note,"
                     " created_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, book_id, position, note, _now_str()))
    db.commit()
    return cur.lastrowid


def list_bookmarks(db: sqlite3.Connection, user_id: int,
                   book_id: Optional[int] = None) -> list[dict[str, Any]]:
    """Закладки пользователя (все или по одной книге)."""
    sql = ("SELECT m.*, b.title FROM bookmarks m JOIN books b ON "
           "b.id = m.book_id WHERE m.user_id = ?")
    args: list[Any] = [user_id]
    if book_id is not None:
        sql += " AND m.book_id = ?"
        args.append(book_id)
    return [dict(r) for r in
            db.execute(sql + " ORDER BY m.id DESC", args).fetchall()]


def delete_bookmark(db: sqlite3.Connection, user_id: int,
                    bookmark_id: int) -> None:
    """Удалить свою закладку."""
    cur = db.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?",
                     (bookmark_id, user_id))
    db.commit()
    if cur.rowcount == 0:
        raise NotFoundError("Закладка не найдена")


# ---------------------------------------------------------------------------
# Подтверждение статуса студента
# ---------------------------------------------------------------------------
def submit_student_request(db: sqlite3.Connection, user: sqlite3.Row,
                           file_path: str) -> int:
    """Подать заявку на статус студента с фото студенческого билета."""
    require_permission(user["role"], "student.apply")
    if user["is_student"]:
        raise ConflictError("Статус студента уже подтверждён")
    pending = db.execute("SELECT 1 FROM student_requests WHERE user_id = ? "
                         "AND status = 'pending'", (user["id"],)).fetchone()
    if pending:
        raise ConflictError("Заявка уже на рассмотрении")
    cur = db.execute("INSERT INTO student_requests(user_id, file_path, "
                     "created_at) VALUES (?, ?, ?)",
                     (user["id"], file_path, _now_str()))
    db.commit()
    return cur.lastrowid


def student_request_status(db: sqlite3.Connection,
                           user_id: int) -> Optional[str]:
    """Статус последней заявки пользователя на статус студента."""
    row = db.execute("SELECT status FROM student_requests WHERE user_id = ? "
                     "ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    return row["status"] if row else None


def list_student_requests(db: sqlite3.Connection,
                          actor_role: str) -> list[dict[str, Any]]:
    """Заявки, ожидающие проверки (модератор)."""
    require_permission(actor_role, "user.verify_student")
    rows = db.execute("SELECT r.id, r.user_id, r.created_at, u.username, "
                      "u.display_name FROM student_requests r JOIN users u "
                      "ON u.id = r.user_id WHERE r.status = 'pending' "
                      "ORDER BY r.id").fetchall()
    return [dict(r) for r in rows]


def get_student_request(db: sqlite3.Connection,
                        request_id: int) -> sqlite3.Row:
    """Заявка на статус студента по id."""
    row = db.execute("SELECT * FROM student_requests WHERE id = ?",
                     (request_id,)).fetchone()
    if row is None:
        raise NotFoundError("Заявка не найдена")
    return row


def review_student_request(db: sqlite3.Connection, actor: sqlite3.Row,
                           request_id: int, approve: bool) -> None:
    """Одобрить (пользователь становится студентом) или отклонить заявку."""
    require_permission(actor["role"], "user.verify_student")
    row = get_student_request(db, request_id)
    if row["status"] != "pending":
        raise ConflictError("Заявка уже рассмотрена")
    db.execute("UPDATE student_requests SET status = ?, reviewed_by = ? "
               "WHERE id = ?",
               ("approved" if approve else "rejected", actor["id"],
                request_id))
    db.commit()
    if approve:
        verify_student(db, actor["role"], row["user_id"])


# ---------------------------------------------------------------------------
# Баны и заявки на разбан
# ---------------------------------------------------------------------------
def active_ban(db: sqlite3.Connection,
               user_id: int) -> Optional[sqlite3.Row]:
    """Действующий бан пользователя или ``None``; истёкший снимается."""
    row = db.execute("SELECT * FROM bans WHERE user_id = ? AND is_active = 1 "
                     "ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    if row is None:
        return None
    if row["until"] is None or _parse(row["until"]) > _now():
        return row
    db.execute("UPDATE bans SET is_active = 0 WHERE user_id = ? AND "
               "is_active = 1", (user_id,))
    db.commit()
    return None


def is_banned(db: sqlite3.Connection, user_id: int) -> bool:
    """Действует ли на пользователя бан."""
    return active_ban(db, user_id) is not None


def ban_user(db: sqlite3.Connection, actor: sqlite3.Row, target_id: int,
             reason: str, seconds: Optional[int] = None) -> int:
    """Забанить пользователя (право ``user.ban``) с причиной и сроком.

    ``seconds=None`` — навсегда. Модератор не может забанить персонал с
    равными или большими правами — только главный разработчик.
    """
    require_permission(actor["role"], "user.ban")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Укажите причину бана")
    if len(reason) > 500:
        raise ValidationError("Причина не длиннее 500 символов")
    target = get_user(db, target_id)
    if target["role"] == "owner":
        raise PermissionDeniedError("Нельзя забанить главного разработчика")
    if target["id"] == actor["id"]:
        raise ValidationError("Нельзя забанить самого себя")
    if actor["role"] != "owner" and target["role"] in ("moderator", "editor"):
        raise PermissionDeniedError("Банить персонал может только владелец")
    until = None
    if seconds is not None:
        if int(seconds) <= 0:
            raise ValidationError("Срок бана должен быть положительным")
        until = (_now() + timedelta(seconds=int(seconds))
                 ).strftime(DATETIME_FMT)
    db.execute("UPDATE bans SET is_active = 0 WHERE user_id = ?",
               (target_id,))
    cur = db.execute("INSERT INTO bans(user_id, reason, banned_by, until, "
                     "created_at) VALUES (?, ?, ?, ?, ?)",
                     (target_id, reason, actor["id"], until, _now_str()))
    db.commit()
    return cur.lastrowid


def unban_user(db: sqlite3.Connection, actor: sqlite3.Row,
               target_id: int) -> None:
    """Снять активные баны (право ``user.ban``)."""
    require_permission(actor["role"], "user.ban")
    get_user(db, target_id)
    db.execute("UPDATE bans SET is_active = 0 WHERE user_id = ? AND "
               "is_active = 1", (target_id,))
    db.commit()


def create_unban_request(db: sqlite3.Connection, user_id: int,
                         text: str) -> int:
    """Создать заявку на разбан от забаненного пользователя."""
    text = (text or "").strip()
    if not text:
        raise ValidationError("Опишите, почему вас стоит разбанить")
    if len(text) > 1000:
        raise ValidationError("Текст заявки не длиннее 1000 символов")
    if not is_banned(db, user_id):
        raise ConflictError("Пользователь не забанен")
    if db.execute("SELECT 1 FROM unban_requests WHERE user_id = ? AND "
                  "status = 'pending'", (user_id,)).fetchone():
        raise ConflictError("Заявка уже на рассмотрении")
    cur = db.execute("INSERT INTO unban_requests(user_id, text, created_at) "
                     "VALUES (?, ?, ?)", (user_id, text, _now_str()))
    db.commit()
    return cur.lastrowid


def unban_request_by_credentials(db: sqlite3.Connection, username: str,
                                 password: str, text: str) -> int:
    """Заявка на разбан без входа: забаненный не может получить токен,
    поэтому подтверждает личность логином и паролем."""
    user = _check_credentials(db, username, password)
    return create_unban_request(db, user["id"], text)


def list_unban_requests(db: sqlite3.Connection,
                        actor_role: str) -> list[dict[str, Any]]:
    """Ожидающие заявки на разбан вместе с причиной бана."""
    require_permission(actor_role, "unban.manage")
    rows = db.execute(
        "SELECT r.id, r.user_id, r.text, r.created_at, u.username, "
        "(SELECT reason FROM bans b WHERE b.user_id = r.user_id ORDER BY "
        "b.id DESC LIMIT 1) AS ban_reason FROM unban_requests r JOIN users u"
        " ON u.id = r.user_id WHERE r.status = 'pending' ORDER BY r.id"
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_unban_request(db: sqlite3.Connection, actor: sqlite3.Row,
                          request_id: int, approve: bool) -> None:
    """Одобрить (бан снимается) или отклонить заявку на разбан."""
    require_permission(actor["role"], "unban.manage")
    row = db.execute("SELECT * FROM unban_requests WHERE id = ?",
                     (request_id,)).fetchone()
    if row is None:
        raise NotFoundError("Заявка не найдена")
    if row["status"] != "pending":
        raise ConflictError("Заявка уже рассмотрена")
    db.execute("UPDATE unban_requests SET status = ?, reviewed_by = ? "
               "WHERE id = ?",
               ("approved" if approve else "rejected", actor["id"],
                request_id))
    if approve:
        db.execute("UPDATE bans SET is_active = 0 WHERE user_id = ? AND "
                   "is_active = 1", (row["user_id"],))
    db.commit()


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------
def reading_stats(db: sqlite3.Connection) -> dict[str, Any]:
    """Общая статистика прочитанного по всем пользователям.

    Главный разработчик стоит на «нулевом» месте с символическим «∞» —
    вне конкурса, а за первое место соревнуются остальные читатели.
    Читатели с одинаковым числом книг делят одно место.
    """
    def count(sql: str) -> int:
        return db.execute(sql).fetchone()[0]

    rows = [dict(r) for r in db.execute(
        "SELECT u.username, u.display_name, u.role, COUNT(s.book_id) "
        "AS read_count FROM users u LEFT JOIN shelf s ON s.user_id = u.id"
        " AND s.status = 'read' GROUP BY u.id "
        "ORDER BY (u.role = 'owner') DESC, read_count DESC, u.id")]
    leaderboard = []
    place, previous = 0, None
    for index, entry in enumerate(
            (e for e in rows if e["role"] != "owner"), start=1):
        if entry["read_count"] != previous:
            place, previous = index, entry["read_count"]
        entry["place"] = place
        leaderboard.append(entry)
    leaderboard = leaderboard[:10]
    owners = [e for e in rows if e["role"] == "owner"]
    for entry in owners:
        entry.update(place=0, read_count="∞")
    leaderboard = owners + leaderboard

    top_books = [dict(r) for r in db.execute(
        "SELECT b.id, b.title, b.author, b.cover_color, COUNT(*) AS reads "
        "FROM shelf s JOIN books b ON b.id = s.book_id WHERE s.status = 'read'"
        " GROUP BY b.id ORDER BY reads DESC, b.title LIMIT 5")]

    return {
        "total_read": count("SELECT COUNT(*) FROM shelf WHERE "
                            "status = 'read'"),
        "total_books": count("SELECT COUNT(*) FROM books"),
        "total_users": count("SELECT COUNT(*) FROM users"),
        "total_comments": count("SELECT COUNT(*) FROM comments WHERE "
                                "is_deleted = 0"),
        "reading_now": count("SELECT COUNT(*) FROM shelf WHERE "
                             "status = 'reading'"),
        "leaderboard": leaderboard,
        "top_books": top_books,
        "genres": list_genres(db),
    }


# ---------------------------------------------------------------------------
# Мини-игра «Парақ» (кликер в духе Cookie Clicker)
# ---------------------------------------------------------------------------
# Игрок собирает «страницы»: кликом по книге и с помощью улучшений, которые
# приносят страницы сами каждую секунду. Цена каждого следующего улучшения
# того же вида растёт в GAME_COST_GROWTH раз. Таблица общая для сервера и
# интерфейса (отдаётся через /api/game/config), поэтому сервер может
# проверить, что присланный прогресс вообще мог быть получен честно.
GAME_COST_GROWTH = 1.15
GAME_MAX_CPS = 20            # больше 20 кликов в секунду человек не делает
GAME_FIRST_SAVE_SECONDS = 120
GAME_UPGRADES: dict[str, dict[str, Any]] = {
    # обычные — можно покупать много раз
    "bookmark": {"cost": 15, "click": 1},       # закладка: +1 к клику
    "student": {"cost": 60, "rate": 0.5},       # студент-читатель
    "lamp": {"cost": 300, "rate": 3},           # настольная лампа
    "shelf": {"cost": 1500, "rate": 12},        # книжная полка (маскот!)
    "hall": {"cost": 8000, "rate": 50},         # читальный зал
    "press": {"cost": 40000, "rate": 220},      # типография
    "library": {"cost": 200000, "rate": 1000},  # библиотека «Оқу»
    # разовые — пасхалки с одногруппниками, покупаются один раз
    "edige": {"cost": 600, "once": True, "autoclick": 2},
    "altynbek": {"cost": 4000, "once": True, "click_mult": 2},
    "temirlan": {"cost": 25000, "once": True, "rate_mult": 2},
    "muhan": {"cost": 300000, "once": True, "rate_mult": 3},
}


def game_cost(kind: str, owned: int) -> float:
    """Цена следующего улучшения ``kind``, если уже куплено ``owned``."""
    return GAME_UPGRADES[kind]["cost"] * GAME_COST_GROWTH ** owned


def game_spent(upgrades: dict[str, int]) -> float:
    """Сколько страниц потрачено на все купленные улучшения."""
    return sum(game_cost(kind, i) for kind, n in upgrades.items()
               for i in range(n))


def game_click_power(upgrades: dict[str, int]) -> float:
    """Сколько страниц даёт один клик."""
    base = 1 + sum(GAME_UPGRADES[k].get("click", 0) * n
                   for k, n in upgrades.items())
    mult = 1
    for k, n in upgrades.items():
        if n:
            mult *= GAME_UPGRADES[k].get("click_mult", 1)
    return base * mult


def game_rate(upgrades: dict[str, int]) -> float:
    """Сколько страниц в секунду приносят улучшения без кликов."""
    rate = sum(GAME_UPGRADES[k].get("rate", 0) * n
               for k, n in upgrades.items())
    mult = 1
    for k, n in upgrades.items():
        if n:
            mult *= GAME_UPGRADES[k].get("rate_mult", 1)
    auto = sum(GAME_UPGRADES[k].get("autoclick", 0) * n
               for k, n in upgrades.items())
    return rate * mult + auto * game_click_power(upgrades)


def _game_upgrades(raw: dict[str, Any]) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValidationError("Неверный формат улучшений")
    result: dict[str, int] = {}
    for kind, count in raw.items():
        if kind not in GAME_UPGRADES:
            raise ValidationError(f"Неизвестное улучшение: {kind}")
        if not isinstance(count, int) or isinstance(count, bool) \
                or not 0 <= count <= 500:
            raise ValidationError("Количество улучшений — от 0 до 500")
        if GAME_UPGRADES[kind].get("once") and count > 1:
            raise ValidationError("Разовое улучшение покупается один раз")
        if count:
            result[kind] = count
    return result


def get_game(db: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    """Сохранённый прогресс игрока (или пустой, если он ещё не играл)."""
    row = db.execute("SELECT * FROM game_saves WHERE user_id = ?",
                     (user_id,)).fetchone()
    if row is None:
        return {"pages": 0, "pages_total": 0, "clicks": 0, "upgrades": {},
                "updated_at": None}
    data = dict(row)
    data["upgrades"] = json.loads(data["upgrades"] or "{}")
    data.pop("user_id", None)
    return data


def save_game(db: sqlite3.Connection, user_id: int, pages: float,
              pages_total: float, clicks: int,
              upgrades: dict[str, Any]) -> dict[str, Any]:
    """Сохранить прогресс игры с защитой от накрутки.

    Проверяется: числа неотрицательные; на купленные улучшения хватило бы
    собранных страниц; число кликов растёт не быстрее GAME_MAX_CPS в секунду;
    страниц прибавилось не больше, чем могли дать клики и улучшения за
    прошедшее с прошлого сохранения время (с запасом в 1,5 раза).
    """
    for value in (pages, pages_total, clicks):
        if not isinstance(value, (int, float)) or isinstance(value, bool) \
                or value != value or value < 0 or value > 1e15:
            raise ValidationError("Неверные числа в сохранении")
    if pages > pages_total + 1e-6:
        raise ValidationError("Страниц сейчас не может быть больше, "
                              "чем собрано всего")
    owned = _game_upgrades(upgrades)
    if game_spent(owned) > pages_total - pages + 1:
        raise ValidationError("На такие улучшения не хватило бы страниц")

    prev = get_game(db, user_id)
    if prev["updated_at"]:
        elapsed = max(1.0, (_now() - _parse(prev["updated_at"]))
                      .total_seconds())
    else:
        elapsed = float(GAME_FIRST_SAVE_SECONDS)
    new_clicks = clicks - prev["clicks"]
    gained = pages_total - prev["pages_total"]
    if new_clicks < 0 or gained < -1e-6:
        raise ValidationError("Прогресс не может уменьшаться — для начала "
                              "заново сбросьте игру")
    if new_clicks > GAME_MAX_CPS * elapsed + GAME_MAX_CPS:
        raise ValidationError("Слишком много кликов за это время")
    allowed = (game_rate(owned) * elapsed
               + game_click_power(owned) * new_clicks) * 1.5 + 100
    if gained > allowed:
        raise ValidationError("Слишком быстрый рост — сохранение отклонено")

    db.execute(
        "INSERT INTO game_saves(user_id, pages, pages_total, clicks, upgrades,"
        " updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO "
        "UPDATE SET pages = excluded.pages, "
        "pages_total = excluded.pages_total, "
        "clicks = excluded.clicks, upgrades = excluded.upgrades, "
        "updated_at = excluded.updated_at",
        (user_id, float(pages), float(pages_total), int(clicks),
         json.dumps(owned, sort_keys=True), _now_str()))
    db.commit()
    return get_game(db, user_id)


def reset_game(db: sqlite3.Connection, user_id: int) -> None:
    """Начать игру заново (удалить сохранение)."""
    db.execute("DELETE FROM game_saves WHERE user_id = ?", (user_id,))
    db.commit()


def game_leaderboard(db: sqlite3.Connection,
                     limit: int = 10) -> list[dict[str, Any]]:
    """Рекорды «Парақ»: все игроки на равных (без особого места владельца).

    Игроки с одинаковым числом собранных страниц делят одно место.
    """
    rows = db.execute(
        "SELECT u.username, u.display_name, u.role, g.pages_total, g.clicks,"
        " g.upgrades FROM game_saves g JOIN users u ON u.id = g.user_id "
        "WHERE g.pages_total > 0 ORDER BY g.pages_total DESC, g.updated_at "
        "LIMIT ?", (max(1, min(int(limit), 50)),)).fetchall()
    result, place, previous = [], 0, None
    for index, row in enumerate(rows, start=1):
        entry = dict(row)
        owned = json.loads(entry.pop("upgrades") or "{}")
        entry["rate"] = round(game_rate(owned), 1)
        entry["pages_total"] = int(entry["pages_total"])
        if entry["pages_total"] != previous:
            place, previous = index, entry["pages_total"]
        entry["place"] = place
        result.append(entry)
    return result


def game_config() -> dict[str, Any]:
    """Таблица улучшений и константы — для интерфейса игры."""
    return {"upgrades": GAME_UPGRADES, "cost_growth": GAME_COST_GROWTH,
            "max_cps": GAME_MAX_CPS}


# ---------------------------------------------------------------------------
# Теги
# ---------------------------------------------------------------------------
def add_tag(db: sqlite3.Connection, name: str) -> int:
    """Создать тег (или вернуть id существующего)."""
    name = (name or "").strip().lower().lstrip("#")
    if not name:
        raise ValidationError("Имя тега не должно быть пустым")
    if len(name) > 40:
        raise ValidationError("Тег не длиннее 40 символов")
    row = db.execute("SELECT id FROM tags WHERE name = ?",
                     (name,)).fetchone()
    if row:
        return row["id"]
    cur = db.execute("INSERT INTO tags(name) VALUES (?)", (name,))
    db.commit()
    return cur.lastrowid


def tag_book(db: sqlite3.Connection, book_id: int, tag_name: str) -> None:
    """Присвоить книге тег."""
    get_book(db, book_id)
    tag_id = add_tag(db, tag_name)
    db.execute("INSERT OR IGNORE INTO book_tags(book_id, tag_id) "
               "VALUES (?, ?)", (book_id, tag_id))
    db.commit()


def set_book_tags(db: sqlite3.Connection, book_id: int,
                  names: list[str]) -> None:
    """Заменить теги книги на переданный список."""
    clean = []
    for name in names:
        name = (name or "").strip().lower().lstrip("#")
        if name and name not in clean:
            clean.append(name)
    if len(clean) > MAX_TAGS_PER_BOOK:
        raise ValidationError(f"Не больше {MAX_TAGS_PER_BOOK} тегов")
    get_book(db, book_id)
    db.execute("DELETE FROM book_tags WHERE book_id = ?", (book_id,))
    db.commit()
    for name in clean:
        tag_book(db, book_id, name)


def book_tags(db: sqlite3.Connection, book_id: int) -> list[str]:
    """Теги книги по алфавиту."""
    rows = db.execute("SELECT t.name FROM tags t JOIN book_tags bt ON "
                      "bt.tag_id = t.id WHERE bt.book_id = ? ORDER BY t.name",
                      (book_id,)).fetchall()
    return [r["name"] for r in rows]


def popular_tags(db: sqlite3.Connection,
                 limit: int = 20) -> list[dict[str, Any]]:
    """Самые используемые теги."""
    rows = db.execute("SELECT t.name, COUNT(*) AS count FROM tags t JOIN "
                      "book_tags bt ON bt.tag_id = t.id GROUP BY t.id "
                      "ORDER BY count DESC, t.name LIMIT ?",
                      (limit,)).fetchall()
    return [dict(r) for r in rows]
