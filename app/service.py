"""Бизнес-логика библиотеки (не зависит от веб-фреймворка).

Это файл ``service.py`` из структуры методички (раздел 5.3) — «бизнес-логика
без интерфейса». Все функции принимают уже открытое соединение с базой данных
(:func:`app.db.connect`) и ничего не знают про HTTP, FastAPI или шаблоны.
Благодаря этому логику можно:

* полностью покрыть автотестами без запуска сервера (раздел 5.5);
* подключить к любому интерфейсу — веб, настольному или мобильному.

Ключевые идеи безопасности (раздел 5.4): запросы параметризованы, пароли
хранятся только в виде хэша (см. :mod:`app.security`), входные данные
проверяются, а права доступа реализованы по **принципу наименьших
привилегий**.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from app import security
from app.db import DATETIME_FMT

# ---------------------------------------------------------------------------
# Константы (вынесены, чтобы не было «магических чисел» — раздел 5.2)
# ---------------------------------------------------------------------------
MIN_PASSWORD_LEN = 8
MAX_COMMENT_LEN = 2000
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
USERNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_ROLES = ("owner", "editor", "author", "moderator", "student", "user", "guest")
SHELF_STATUSES = ("reading", "want", "dropped", "read")


# ---------------------------------------------------------------------------
# Иерархия исключений. Интерфейс перехватывает их и показывает понятное
# сообщение вместо аварийного завершения (та же идея, что BookingError).
# ---------------------------------------------------------------------------
class ServiceError(Exception):
    """Базовая ошибка бизнес-логики."""


class ValidationError(ServiceError):
    """Некорректные входные данные."""


class NotFoundError(ServiceError):
    """Запрошенный объект не найден."""


class AuthError(ServiceError):
    """Неверный логин или пароль."""


class AccountLocked(ServiceError):
    """Аккаунт временно заблокирован из-за подбора пароля."""


class Banned(ServiceError):
    """Пользователь забанен."""


class PermissionDenied(ServiceError):
    """Недостаточно прав для действия."""


class Conflict(ServiceError):
    """Конфликт данных (например, дубликат)."""


# ---------------------------------------------------------------------------
# Права доступа: принцип наименьших привилегий (пункт 23 ТЗ пользователя)
# ---------------------------------------------------------------------------
# Каждому действию соответствует строка-право. Роли получают минимально
# необходимый набор прав. Роль owner имеет все права (проверяется отдельно).
PERMISSIONS: dict[str, set[str]] = {
    "guest": {"book.read_free"},
    "user": {
        "book.read_free", "comment.write", "comment.delete_own",
        "shelf.manage", "progress.save",
    },
    "student": {
        "book.read_free", "book.read_paid", "comment.write",
        "comment.delete_own", "shelf.manage", "progress.save",
    },
    "author": {
        "book.read_free", "book.add", "comment.write", "comment.delete_own",
        "shelf.manage", "progress.save",
    },
    "moderator": {
        "book.read_free", "comment.write", "comment.delete_own",
        "comment.delete_any", "shelf.manage", "progress.save",
        "user.ban", "user.verify_student", "log.read", "unban.manage",
    },
    "editor": {
        "book.read_free", "book.read_paid", "book.add", "book.edit",
        "book.delete", "comment.write", "comment.delete_own",
        "comment.delete_any", "shelf.manage", "progress.save",
    },
    # owner получает все права динамически (см. has_permission).
    "owner": set(),
}

# Приписка к комментарию в зависимости от роли (пункты 71–75 ТЗ пользователя).
ROLE_BADGE = {
    "owner": "Главный разработчик",
    "editor": "Редактор",
    "author": "Автор",
    "moderator": "Модератор",
}


def has_permission(role: str, permission: str) -> bool:
    """Проверить, есть ли у роли указанное право."""
    if role == "owner":
        return True
    return permission in PERMISSIONS.get(role, set())


def require_permission(role: str, permission: str) -> None:
    """Выбросить :class:`PermissionDenied`, если у роли нет права."""
    if not has_permission(role, permission):
        raise PermissionDenied(f"Недостаточно прав для действия: {permission}")


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_str() -> str:
    return _now().strftime(DATETIME_FMT)


def _parse(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FMT).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Журнал действий пользователей с временными метками (УСЛОЖНЕНИЕ варианта 11)
# ---------------------------------------------------------------------------
def log_action(db: sqlite3.Connection, user_id: Optional[int], action: str,
               details: str = "", ip: str = "") -> int:
    """Записать действие пользователя в журнал с временной меткой."""
    cur = db.execute(
        "INSERT INTO action_log(user_id, action, details, ip, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, action, details, ip, _now_str()),
    )
    db.commit()
    return cur.lastrowid


def list_log(db: sqlite3.Connection, limit: int = 100,
             user_id: Optional[int] = None) -> list[sqlite3.Row]:
    """Вернуть последние записи журнала (при необходимости — по пользователю)."""
    limit = max(1, min(int(limit), 1000))
    if user_id is None:
        rows = db.execute(
            "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM action_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return rows


# ---------------------------------------------------------------------------
# Пользователи и аутентификация
# ---------------------------------------------------------------------------
def register_user(db: sqlite3.Connection, username: str, email: str,
                  password: str, role: str = "user",
                  language: str = "ru", display_name: str = "") -> int:
    """Зарегистрировать нового пользователя.

    Проверяет корректность логина, почты и длины пароля; пароль сохраняется
    только в виде хэша. Дубликат логина или почты даёт :class:`Conflict`.
    """
    username = (username or "").strip()
    email = (email or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValidationError(
            "Логин: 3–32 символа, буквы/цифры/._- без пробелов"
        )
    if not EMAIL_RE.match(email):
        raise ValidationError("Некорректный адрес электронной почты")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValidationError(
            f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов"
        )
    if role not in VALID_ROLES or role == "guest":
        raise ValidationError("Недопустимая роль")
    try:
        cur = db.execute(
            "INSERT INTO users(username, email, password_hash, role, language, "
            "display_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, email, security.hash_password(password), role,
             language, display_name or username, _now_str()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise Conflict("Пользователь с таким логином или почтой уже существует")
    return cur.lastrowid


def get_user(db: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    """Вернуть пользователя по идентификатору или выбросить :class:`NotFoundError`."""
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFoundError("Пользователь не найден")
    return row


def get_user_by_username(db: sqlite3.Connection,
                         username: str) -> Optional[sqlite3.Row]:
    """Вернуть пользователя по логину или ``None``."""
    return db.execute(
        "SELECT * FROM users WHERE username = ?", ((username or "").strip(),)
    ).fetchone()


def authenticate(db: sqlite3.Connection, username: str,
                 password: str) -> sqlite3.Row:
    """Проверить логин и пароль с защитой от подбора (брутфорса).

    После :data:`security.MAX_FAILED_ATTEMPTS` неудач подряд аккаунт
    блокируется на :data:`security.LOCKOUT_MINUTES` минут. Успешный вход
    сбрасывает счётчик. Забаненный пользователь войти не может.
    """
    user = get_user_by_username(db, username)
    if user is None:
        raise AuthError("Неверный логин или пароль")

    # Проверка активной блокировки за брутфорс.
    if user["locked_until"]:
        if _parse(user["locked_until"]) > _now():
            raise AccountLocked(
                "Слишком много попыток. Повторите позже."
            )

    if not security.verify_password(password, user["password_hash"]):
        attempts = user["failed_attempts"] + 1
        locked_until = None
        if attempts >= security.MAX_FAILED_ATTEMPTS:
            locked_until = (
                _now() + timedelta(minutes=security.LOCKOUT_MINUTES)
            ).strftime(DATETIME_FMT)
            attempts = 0  # сбрасываем счётчик, фиксируем факт блокировки
        db.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (attempts, locked_until, user["id"]),
        )
        db.commit()
        if locked_until:
            raise AccountLocked("Слишком много попыток. Повторите позже.")
        raise AuthError("Неверный логин или пароль")

    # Успех: сбрасываем счётчик и снимаем блокировку.
    db.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
        (user["id"],),
    )
    db.commit()

    if is_banned(db, user["id"]):
        raise Banned("Аккаунт заблокирован (бан)")
    return get_user(db, user["id"])


def assign_role(db: sqlite3.Connection, actor_role: str, target_id: int,
                new_role: str) -> None:
    """Назначить пользователю роль (требует права ``user.assign_role``)."""
    if actor_role != "owner":
        raise PermissionDenied("Выдавать роли может только главный разработчик")
    if new_role not in VALID_ROLES or new_role == "guest":
        raise ValidationError("Недопустимая роль")
    get_user(db, target_id)
    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, target_id))
    db.commit()


def verify_student(db: sqlite3.Connection, actor_role: str,
                   target_id: int) -> None:
    """Подтвердить статус студента (модератор/владелец)."""
    require_permission(actor_role, "user.verify_student")
    get_user(db, target_id)
    db.execute("UPDATE users SET is_student = 1 WHERE id = ?", (target_id,))
    db.commit()


def set_language(db: sqlite3.Connection, user_id: int, language: str) -> None:
    """Сохранить выбранный язык интерфейса пользователя."""
    if language not in ("ru", "kk", "en"):
        raise ValidationError("Поддерживаются языки ru, kk, en")
    get_user(db, user_id)
    db.execute("UPDATE users SET language = ? WHERE id = ?", (language, user_id))
    db.commit()


# ---------------------------------------------------------------------------
# Книги: добавление, редактирование, удаление, поиск с пагинацией
# ---------------------------------------------------------------------------
def add_book(db: sqlite3.Connection, actor_role: str, title: str, author: str,
             *, year: Optional[int] = None, language: str = "ru",
             genre: str = "", description: str = "", content: str = "",
             cover_color: str = "#4f46e5", is_paid: bool = False,
             paid_days: Optional[int] = None,
             added_by: Optional[int] = None) -> int:
    """Добавить книгу (требует право ``book.add``).

    Платная книга становится бесплатной после ``paid_days`` дней
    (пункт 73 ТЗ пользователя: «платное всегда на время, со временем
    становится бесплатным»).
    """
    require_permission(actor_role, "book.add")
    title = (title or "").strip()
    author = (author or "").strip()
    if not title:
        raise ValidationError("Название книги не должно быть пустым")
    if not author:
        raise ValidationError("Укажите автора книги")
    if year is not None and not (0 <= int(year) <= 2100):
        raise ValidationError("Год должен быть в диапазоне 0–2100")
    if language not in ("ru", "kk", "en"):
        raise ValidationError("Язык книги: ru, kk или en")
    paid_until = None
    if is_paid and paid_days:
        paid_until = (_now() + timedelta(days=int(paid_days))).strftime(DATETIME_FMT)
    cur = db.execute(
        "INSERT INTO books(title, author, year, language, genre, description, "
        "content, cover_color, is_paid, paid_until, added_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, author, year, language, genre, description, content,
         cover_color, 1 if is_paid else 0, paid_until, added_by, _now_str()),
    )
    db.commit()
    return cur.lastrowid


def get_book(db: sqlite3.Connection, book_id: int) -> sqlite3.Row:
    """Вернуть книгу по идентификатору или выбросить :class:`NotFoundError`."""
    row = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise NotFoundError("Книга не найдена")
    return row


def edit_book(db: sqlite3.Connection, actor_role: str, book_id: int,
              **fields: Any) -> None:
    """Изменить поля книги (требует право ``book.edit``)."""
    require_permission(actor_role, "book.edit")
    get_book(db, book_id)
    allowed = {"title", "author", "year", "language", "genre",
               "description", "content", "cover_color"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        raise ValidationError("Нет полей для обновления")
    cols = ", ".join(f"{k} = ?" for k in updates)
    db.execute(f"UPDATE books SET {cols} WHERE id = ?",
               (*updates.values(), book_id))
    db.commit()


def delete_book(db: sqlite3.Connection, actor_role: str, book_id: int) -> None:
    """Удалить книгу (требует право ``book.delete``)."""
    require_permission(actor_role, "book.delete")
    cur = db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()
    if cur.rowcount == 0:
        raise NotFoundError("Книга не найдена")


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    """Нормализовать номер страницы и размер страницы для пагинации."""
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    return page, page_size


def search_books(db: sqlite3.Connection, *, query: str = "",
                 author: str = "", year: Optional[int] = None,
                 genre: str = "", language: str = "",
                 sort: str = "title", order: str = "asc",
                 page: int = 1,
                 page_size: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    """Найти книги с поиском, фильтрацией, сортировкой и пагинацией.

    * ``query`` ищется по названию **и** автору (регистронезависимо);
    * ``author``, ``year``, ``genre``, ``language`` — дополнительные фильтры;
    * ``sort`` — одно из ``title``, ``author``, ``year``, ``created_at``;
    * постраничный вывод (обязательная функция варианта 11).

    :returns: словарь с ключами ``items``, ``total``, ``page``, ``page_size``,
        ``pages``.
    """
    page, page_size = _clamp_page(page, page_size)

    where: list[str] = []
    args: list[Any] = []
    if query:
        where.append("(LOWER(title) LIKE ? OR LOWER(author) LIKE ?)")
        pattern = f"%{query.strip().lower()}%"
        args += [pattern, pattern]
    if author:
        where.append("LOWER(author) LIKE ?")
        args.append(f"%{author.strip().lower()}%")
    if year is not None:
        where.append("year = ?")
        args.append(int(year))
    if genre:
        where.append("LOWER(genre) = ?")
        args.append(genre.strip().lower())
    if language:
        where.append("language = ?")
        args.append(language)

    clause = (" WHERE " + " AND ".join(where)) if where else ""

    # Белый список полей сортировки защищает от инъекции через имя столбца.
    sort_col = sort if sort in ("title", "author", "year", "created_at") else "title"
    sort_dir = "DESC" if str(order).lower() == "desc" else "ASC"

    total = db.execute(
        f"SELECT COUNT(*) AS n FROM books{clause}", args
    ).fetchone()["n"]

    offset = (page - 1) * page_size
    items = db.execute(
        f"SELECT * FROM books{clause} ORDER BY {sort_col} {sort_dir} "
        f"LIMIT ? OFFSET ?",
        (*args, page_size, offset),
    ).fetchall()

    pages = (total + page_size - 1) // page_size
    return {"items": items, "total": total, "page": page,
            "page_size": page_size, "pages": pages}


def can_read_book(user: Optional[sqlite3.Row], book: sqlite3.Row) -> bool:
    """Определить, может ли пользователь читать книгу.

    Бесплатную книгу читают все. Платную — пока не истёк срок ``paid_until`` —
    читают владелец/редактор, проверенные студенты, а также автор, добавивший
    книгу. После истечения срока книга становится бесплатной для всех.
    """
    if not book["is_paid"]:
        return True
    if book["paid_until"] and _parse(book["paid_until"]) <= _now():
        return True  # срок платности истёк — книга бесплатна
    if user is None:
        return False
    if user["role"] in ("owner", "editor"):
        return True
    if user["is_student"]:
        return True
    if book["added_by"] is not None and user["id"] == book["added_by"]:
        return True
    return False


# ---------------------------------------------------------------------------
# Комментарии и цензура нецензурной лексики
# ---------------------------------------------------------------------------
# Небольшой список корней бранных слов (ru/kk/en). Полный список вынесен бы
# в отдельный файл; здесь — демонстрация механизма маскирования.
_PROFANITY = ("дур", "идиот", "fool", "stupid", "ақымақ")


def censor_profanity(text: str) -> str:
    """Замаскировать бранные слова звёздочками, сохранив первую букву."""
    def mask(match: re.Match) -> str:
        word = match.group(0)
        return word[0] + "*" * (len(word) - 1)

    result = text
    for root in _PROFANITY:
        result = re.sub(rf"\b{root}\w*", mask, result, flags=re.IGNORECASE)
    return result


def add_comment(db: sqlite3.Connection, user: sqlite3.Row, book_id: int,
                text: str) -> int:
    """Добавить комментарий к книге (требует право ``comment.write``).

    Текст проходит цензуру, а приписка (badge) выставляется по роли автора.
    """
    require_permission(user["role"], "comment.write")
    text = (text or "").strip()
    if not text:
        raise ValidationError("Комментарий не должен быть пустым")
    if len(text) > MAX_COMMENT_LEN:
        raise ValidationError(
            f"Комментарий не длиннее {MAX_COMMENT_LEN} символов"
        )
    get_book(db, book_id)
    badge = ROLE_BADGE.get(user["role"], "")
    cur = db.execute(
        "INSERT INTO comments(book_id, user_id, text, badge, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (book_id, user["id"], censor_profanity(text), badge, _now_str()),
    )
    db.commit()
    return cur.lastrowid


def delete_comment(db: sqlite3.Connection, user: sqlite3.Row,
                   comment_id: int) -> None:
    """Удалить комментарий: свой (``comment.delete_own``) или любой
    (``comment.delete_any``)."""
    row = db.execute(
        "SELECT * FROM comments WHERE id = ? AND is_deleted = 0", (comment_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError("Комментарий не найден")
    is_own = row["user_id"] == user["id"]
    if is_own:
        require_permission(user["role"], "comment.delete_own")
    else:
        require_permission(user["role"], "comment.delete_any")
    db.execute("UPDATE comments SET is_deleted = 1 WHERE id = ?", (comment_id,))
    db.commit()


def list_comments(db: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
    """Вернуть неудалённые комментарии книги в хронологическом порядке."""
    return db.execute(
        "SELECT c.*, u.username FROM comments c JOIN users u ON u.id = c.user_id "
        "WHERE c.book_id = ? AND c.is_deleted = 0 ORDER BY c.created_at",
        (book_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Книжная полка и прогресс чтения (удобство, как в MangaLib)
# ---------------------------------------------------------------------------
def set_shelf_status(db: sqlite3.Connection, user_id: int, book_id: int,
                     status: str) -> None:
    """Добавить книгу на полку со статусом reading/want/dropped/read."""
    if status not in SHELF_STATUSES:
        raise ValidationError("Недопустимый статус полки")
    get_book(db, book_id)
    db.execute(
        "INSERT INTO shelf(user_id, book_id, status, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, book_id) DO UPDATE SET status = ?, updated_at = ?",
        (user_id, book_id, status, _now_str(), status, _now_str()),
    )
    db.commit()


def get_shelf(db: sqlite3.Connection, user_id: int,
              status: Optional[str] = None) -> list[sqlite3.Row]:
    """Вернуть книги на полке пользователя (при необходимости — по статусу)."""
    if status is not None and status not in SHELF_STATUSES:
        raise ValidationError("Недопустимый статус полки")
    sql = ("SELECT s.status, s.updated_at, b.* FROM shelf s "
           "JOIN books b ON b.id = s.book_id WHERE s.user_id = ?")
    args: list[Any] = [user_id]
    if status:
        sql += " AND s.status = ?"
        args.append(status)
    return db.execute(sql + " ORDER BY s.updated_at DESC", args).fetchall()


def save_progress(db: sqlite3.Connection, user_id: int, book_id: int,
                  position: int) -> None:
    """Сохранить позицию чтения, чтобы продолжить с того же места."""
    position = int(position)
    if position < 0:
        raise ValidationError("Позиция не может быть отрицательной")
    get_book(db, book_id)
    db.execute(
        "INSERT INTO reading_progress(user_id, book_id, position, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, book_id) DO UPDATE SET position = ?, updated_at = ?",
        (user_id, book_id, position, _now_str(), position, _now_str()),
    )
    db.commit()


def get_progress(db: sqlite3.Connection, user_id: int,
                 book_id: int) -> int:
    """Вернуть сохранённую позицию чтения (0, если ещё не читал)."""
    row = db.execute(
        "SELECT position FROM reading_progress WHERE user_id = ? AND book_id = ?",
        (user_id, book_id),
    ).fetchone()
    return row["position"] if row else 0


# ---------------------------------------------------------------------------
# Баны и заявки на разбан
# ---------------------------------------------------------------------------
def is_banned(db: sqlite3.Connection, user_id: int) -> bool:
    """Проверить, действует ли на пользователя активный бан."""
    row = db.execute(
        "SELECT until FROM bans WHERE user_id = ? AND is_active = 1 "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        return False
    if row["until"] is None:
        return True  # бан навсегда
    if _parse(row["until"]) > _now():
        return True
    # Срок бана истёк — снимаем его.
    db.execute(
        "UPDATE bans SET is_active = 0 WHERE user_id = ? AND is_active = 1",
        (user_id,),
    )
    db.commit()
    return False


def ban_user(db: sqlite3.Connection, actor: sqlite3.Row, target_id: int,
             reason: str, minutes: Optional[int] = None) -> int:
    """Забанить пользователя (требует право ``user.ban``).

    ``minutes=None`` — бан навсегда. Причина обязательна (пункт 74 ТЗ).
    """
    require_permission(actor["role"], "user.ban")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Укажите причину бана")
    target = get_user(db, target_id)
    if target["role"] == "owner":
        raise PermissionDenied("Нельзя забанить главного разработчика")
    until = None
    if minutes is not None:
        if int(minutes) <= 0:
            raise ValidationError("Срок бана должен быть положительным")
        until = (_now() + timedelta(minutes=int(minutes))).strftime(DATETIME_FMT)
    cur = db.execute(
        "INSERT INTO bans(user_id, reason, banned_by, until, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (target_id, reason, actor["id"], until, _now_str()),
    )
    db.commit()
    return cur.lastrowid


def unban_user(db: sqlite3.Connection, actor: sqlite3.Row,
               target_id: int) -> None:
    """Снять все активные баны с пользователя (требует право ``user.ban``)."""
    require_permission(actor["role"], "user.ban")
    db.execute(
        "UPDATE bans SET is_active = 0 WHERE user_id = ? AND is_active = 1",
        (target_id,),
    )
    db.commit()


def create_unban_request(db: sqlite3.Connection, user_id: int,
                         text: str) -> int:
    """Создать заявку на разбан от забаненного пользователя."""
    text = (text or "").strip()
    if not text:
        raise ValidationError("Опишите причину разбана")
    if not is_banned(db, user_id):
        raise Conflict("Пользователь не забанен")
    cur = db.execute(
        "INSERT INTO unban_requests(user_id, text, created_at) VALUES (?, ?, ?)",
        (user_id, text, _now_str()),
    )
    db.commit()
    return cur.lastrowid


def resolve_unban_request(db: sqlite3.Connection, actor: sqlite3.Row,
                          request_id: int, approve: bool) -> None:
    """Одобрить или отклонить заявку на разбан (требует право ``unban.manage``)."""
    require_permission(actor["role"], "unban.manage")
    row = db.execute(
        "SELECT * FROM unban_requests WHERE id = ?", (request_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError("Заявка не найдена")
    status = "approved" if approve else "rejected"
    db.execute("UPDATE unban_requests SET status = ? WHERE id = ?",
               (status, request_id))
    if approve:
        db.execute(
            "UPDATE bans SET is_active = 0 WHERE user_id = ? AND is_active = 1",
            (row["user_id"],),
        )
    db.commit()


# ---------------------------------------------------------------------------
# Статистика чтения (пункт 24 ТЗ пользователя)
# ---------------------------------------------------------------------------
def reading_stats(db: sqlite3.Connection) -> dict[str, Any]:
    """Собрать статистику прочитанного по всем пользователям.

    Лидер списка — пользователь с ролью ``owner`` (главный разработчик):
    ему засчитывается символический «рекорд» прочитанного.
    """
    total_read = db.execute(
        "SELECT COUNT(*) AS n FROM shelf WHERE status = 'read'"
    ).fetchone()["n"]
    per_user = db.execute(
        "SELECT u.username, u.role, COUNT(s.book_id) AS read_count "
        "FROM users u LEFT JOIN shelf s "
        "ON s.user_id = u.id AND s.status = 'read' "
        "GROUP BY u.id ORDER BY read_count DESC"
    ).fetchall()
    leaderboard = [
        {"username": r["username"], "role": r["role"],
         "read_count": r["read_count"]}
        for r in per_user
    ]
    # Символический рекорд главного разработчика (∞).
    for entry in leaderboard:
        if entry["role"] == "owner":
            entry["read_count"] = "∞"
            entry["badge"] = "главный разработчик"
    return {"total_read": total_read, "leaderboard": leaderboard}


# ---------------------------------------------------------------------------
# Теги
# ---------------------------------------------------------------------------
def add_tag(db: sqlite3.Connection, name: str) -> int:
    """Создать тег (или вернуть id существующего)."""
    name = (name or "").strip().lower()
    if not name:
        raise ValidationError("Имя тега не должно быть пустым")
    row = db.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = db.execute("INSERT INTO tags(name) VALUES (?)", (name,))
    db.commit()
    return cur.lastrowid


def tag_book(db: sqlite3.Connection, book_id: int, tag_name: str) -> None:
    """Присвоить книге тег."""
    get_book(db, book_id)
    tag_id = add_tag(db, tag_name)
    db.execute(
        "INSERT OR IGNORE INTO book_tags(book_id, tag_id) VALUES (?, ?)",
        (book_id, tag_id),
    )
    db.commit()


def book_tags(db: sqlite3.Connection, book_id: int) -> list[str]:
    """Вернуть список тегов книги."""
    rows = db.execute(
        "SELECT t.name FROM tags t JOIN book_tags bt ON bt.tag_id = t.id "
        "WHERE bt.book_id = ? ORDER BY t.name",
        (book_id,),
    ).fetchall()
    return [r["name"] for r in rows]
