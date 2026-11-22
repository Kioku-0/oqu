"""Слой работы с базой данных (SQLite).

Модуль отвечает только за подключение к базе данных, создание схемы и её
автоматическое обновление (миграции). Вся бизнес-логика вынесена в
:mod:`app.service` и получает уже открытое соединение.

Соответствие методичке (раздел 5.3): это файл ``db.py`` — «работа с базой
данных». Все запросы в проекте параметризованы (знаки ``?``), что защищает
от SQL-инъекций (раздел 5.4).
"""

from __future__ import annotations

import re
import sqlite3

# Формат хранения дат и времени (UTC). Строки в этом формате сравниваются в том
# же порядке, что и сами даты, поэтому сортировать и фильтровать по времени
# можно прямо средствами SQL (та же идея, что в примере LabBooking).
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

SCHEMA = """
-- Пользователи ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    email           TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'user',
    language        TEXT    NOT NULL DEFAULT 'ru',
    is_student      INTEGER NOT NULL DEFAULT 0,   -- подтверждён ли студбилет
    display_name    TEXT    NOT NULL DEFAULT '',
    failed_attempts INTEGER NOT NULL DEFAULT 0,   -- неудачных входов подряд
    locked_until    TEXT,                         -- блок за подбор пароля
    agreed_at       TEXT,                         -- когда принято соглашение
    agreement_ver   TEXT    NOT NULL DEFAULT '',  -- редакция соглашения
    created_at      TEXT    NOT NULL,
    CHECK (role IN ('owner', 'editor', 'author', 'moderator',
                    'student', 'user', 'guest')),
    CHECK (language IN ('ru', 'kk', 'en'))
);

-- Книги ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS books (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    author        TEXT    NOT NULL,
    year          INTEGER,
    language      TEXT    NOT NULL DEFAULT 'ru',
    genre         TEXT    NOT NULL DEFAULT '',
    description   TEXT    NOT NULL DEFAULT '',
    content       TEXT    NOT NULL DEFAULT '',     -- текст книги
    file_path     TEXT,                            -- PDF-скан (имя файла)
    external_url  TEXT    NOT NULL DEFAULT '',     -- ссылка на МегаПро и т.п.
    cover_color   TEXT    NOT NULL DEFAULT '#1f5f4a',
    cover_pattern TEXT    NOT NULL DEFAULT 'auto',   -- узор обложки
    is_paid       INTEGER NOT NULL DEFAULT 0,
    price         INTEGER NOT NULL DEFAULT 0,      -- цена в тенге (учебная)
    paid_until    TEXT,                            -- потом книга бесплатна
    added_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at    TEXT    NOT NULL,
    CHECK (year IS NULL OR (year >= 0 AND year <= 2100)),
    CHECK (is_paid IN (0, 1)),
    CHECK (price >= 0),
    CHECK (language IN ('ru', 'kk', 'en'))
);

-- Комментарии ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    badge       TEXT    NOT NULL DEFAULT '',  -- код приписки: owner, editor...
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    edited_at   TEXT,
    created_at  TEXT    NOT NULL,
    CHECK (is_deleted IN (0, 1))
);

-- Теги («многие ко многим» с книгами) ----------------------------------------
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS book_tags (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (book_id, tag_id)
);

-- Полка: читаю / буду читать / прочитано / брошено ---------------------------
CREATE TABLE IF NOT EXISTS shelf (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    status     TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, book_id),
    CHECK (status IN ('reading', 'want', 'dropped', 'read'))
);

-- Прогресс чтения: текст — промилле (0..1000), PDF — номер страницы ----------
CREATE TABLE IF NOT EXISTS reading_progress (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, book_id),
    CHECK (position >= 0)
);

-- Закладки с заметками («оставил заметку на странице») -----------------------
CREATE TABLE IF NOT EXISTS bookmarks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    note       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    CHECK (position >= 0)
);

-- Оценки книг 1..5 -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS ratings (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    value      INTEGER NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, book_id),
    CHECK (value BETWEEN 1 AND 5)
);

-- Покупки платных книг (учебная имитация оплаты) -----------------------------
CREATE TABLE IF NOT EXISTS purchases (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    price      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, book_id)
);

-- Заявки на подтверждение статуса студента (фото студбилета) -----------------
CREATE TABLE IF NOT EXISTS student_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_path   TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL,
    CHECK (status IN ('pending', 'approved', 'rejected'))
);

-- Журнал действий с временными метками (УСЛОЖНЕНИЕ варианта 11) --------------
CREATE TABLE IF NOT EXISTS action_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action     TEXT    NOT NULL,
    details    TEXT    NOT NULL DEFAULT '',
    ip         TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);

-- Баны -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason     TEXT    NOT NULL,
    banned_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    until      TEXT,                               -- NULL = навсегда
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL,
    CHECK (is_active IN (0, 1))
);

-- Заявки на разбан -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS unban_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL,
    CHECK (status IN ('pending', 'approved', 'rejected'))
);

-- Иллюстрации внутри текста книги (картинки, схемы). В тексте на них
-- ссылается строка вида ![подпись](img:<имя файла>) --------------------------
CREATE TABLE IF NOT EXISTS book_images (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    file_name  TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL
);

-- Мини-игра «Парақ» (кликер): сохранение прогресса и таблица рекордов ------
CREATE TABLE IF NOT EXISTS game_saves (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    pages       REAL    NOT NULL DEFAULT 0,    -- сколько страниц сейчас
    pages_total REAL    NOT NULL DEFAULT 0,    -- собрано за всё время
    clicks      INTEGER NOT NULL DEFAULT 0,
    upgrades    TEXT    NOT NULL DEFAULT '{}', -- купленные улучшения (JSON)
    updated_at  TEXT    NOT NULL,
    CHECK (pages >= 0 AND pages_total >= pages AND clicks >= 0)
);

-- Индексы для частых запросов (поиск, сортировка, пагинация) -----------------
CREATE INDEX IF NOT EXISTS idx_books_author  ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_title   ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_year    ON books(year);
CREATE INDEX IF NOT EXISTS idx_books_genre   ON books(genre);
CREATE INDEX IF NOT EXISTS idx_comments_book ON comments(book_id);
CREATE INDEX IF NOT EXISTS idx_log_created   ON action_log(created_at);
CREATE INDEX IF NOT EXISTS idx_log_user      ON action_log(user_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks     ON bookmarks(user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_book_images   ON book_images(book_id);
CREATE INDEX IF NOT EXISTS idx_game_total    ON game_saves(pages_total);
"""

# Столбцы, добавленные после первой версии. Если база создана старой версией
# программы, недостающие столбцы добавляются автоматически (простая миграция),
# поэтому обновление на хостинге не требует удалять данные.
_ADDED_COLUMNS = (
    ("users", "agreed_at", "TEXT"),
    ("users", "agreement_ver", "TEXT NOT NULL DEFAULT ''"),
    ("books", "file_path", "TEXT"),
    ("books", "external_url", "TEXT NOT NULL DEFAULT ''"),
    ("books", "price", "INTEGER NOT NULL DEFAULT 0"),
    ("books", "cover_pattern", "TEXT NOT NULL DEFAULT 'auto'"),
    ("books", "cover_image", "TEXT"),          # картинка обложки (имя файла)
    ("comments", "edited_at", "TEXT"),
    ("unban_requests", "reviewed_by", "INTEGER"),
)


def _lower(value):
    return value.lower() if isinstance(value, str) else value


def _upper(value):
    return value.upper() if isinstance(value, str) else value


def natural_key(value):
    """Ключ «естественной» сортировки: числа сравниваются как числа.

    Без него «Том 10» стоял бы раньше «Том 2» (сравнение по символам).
    Каждое число дополняется нулями до 10 знаков: «том 0000000002».
    """
    if not isinstance(value, str):
        return value
    return re.sub(r"\d+", lambda m: m.group(0).zfill(10), value.lower())


def _migrate(db: sqlite3.Connection) -> None:
    """Добавить в существующие таблицы столбцы из новых версий схемы."""
    for table, column, ddl in _ADDED_COLUMNS:
        existing = {row["name"] for row in
                    db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    db.commit()


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Открыть соединение с базой данных и подготовить схему.

    :param path: путь к файлу базы; ``":memory:"`` — база в памяти (для
        тестов, чтобы они не влияли друг на друга).
    :returns: открытое соединение :class:`sqlite3.Connection`.

    Включаются внешние ключи (в SQLite по умолчанию выключены) и режим WAL,
    при котором чтение не блокируется записью. Встроенные LOWER()/UPPER()
    SQLite понимают только латиницу, поэтому заменяются Unicode-версиями
    Python — иначе поиск по кириллице и казахским буквам не работал бы.
    """
    # check_same_thread=False: FastAPI может открыть соединение в одном
    # потоке, а закрыть в другом. Это безопасно, потому что у каждого
    # запроса своё соединение и одновременно им пользуется один поток.
    db = sqlite3.connect(path, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        db.execute("PRAGMA journal_mode = WAL")
    db.create_function("lower", 1, _lower, deterministic=True)
    db.create_function("upper", 1, _upper, deterministic=True)
    db.create_function("natural_key", 1, natural_key, deterministic=True)
    db.executescript(SCHEMA)
    _migrate(db)
    return db
