"""Слой работы с базой данных (SQLite).

Модуль отвечает только за подключение к базе данных и создание схемы.
Вся бизнес-логика вынесена в :mod:`app.service` и не зависит от этого
модуля напрямую — функции логики получают уже открытое соединение.

Соответствие методичке (раздел 5.3): это файл ``db.py`` — «работа с базой
данных». Все запросы в проекте параметризованы (знаки ``?``), что защищает
от SQL-инъекций (раздел 5.4).
"""

from __future__ import annotations

import sqlite3

# Формат хранения дат и времени. Строки в этом формате сравниваются в том же
# порядке, что и сами даты, поэтому сортировку и фильтрацию по времени можно
# выполнять прямо средствами SQL (та же идея, что в примере LabBooking).
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

# Схема базы данных. Выполняется при каждом подключении через
# ``CREATE TABLE IF NOT EXISTS`` — повторный запуск безопасен (идемпотентность).
SCHEMA = """
-- Пользователи системы ----------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    email           TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'user',
    language        TEXT    NOT NULL DEFAULT 'ru',
    is_student      INTEGER NOT NULL DEFAULT 0,   -- верифицирован ли студ. билет
    display_name    TEXT    NOT NULL DEFAULT '',
    failed_attempts INTEGER NOT NULL DEFAULT 0,   -- подряд неудачных входов
    locked_until    TEXT,                         -- блокировка (защита от брутфорса)
    created_at      TEXT    NOT NULL,
    CHECK (role IN ('owner', 'editor', 'author', 'moderator',
                    'student', 'user', 'guest')),
    CHECK (language IN ('ru', 'kk', 'en'))
);

-- Книги --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS books (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    author        TEXT    NOT NULL,
    year          INTEGER,
    language      TEXT    NOT NULL DEFAULT 'ru',
    genre         TEXT    NOT NULL DEFAULT '',
    description   TEXT    NOT NULL DEFAULT '',
    content       TEXT    NOT NULL DEFAULT '',     -- текст книги
    cover_color   TEXT    NOT NULL DEFAULT '#4f46e5',
    is_paid       INTEGER NOT NULL DEFAULT 0,      -- платная ли книга
    paid_until    TEXT,                            -- до этой даты платная, потом бесплатная
    added_by      INTEGER REFERENCES users(id),
    created_at    TEXT    NOT NULL,
    CHECK (year IS NULL OR (year >= 0 AND year <= 2100)),
    CHECK (is_paid IN (0, 1)),
    CHECK (language IN ('ru', 'kk', 'en'))
);

-- Комментарии к книгам -----------------------------------------------------
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    badge       TEXT    NOT NULL DEFAULT '',       -- приписка: «разработчик», «автор» и т.п.
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    CHECK (is_deleted IN (0, 1))
);

-- Теги и связь «многие ко многим» с книгами --------------------------------
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS book_tags (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (book_id, tag_id)
);

-- Книжная полка пользователя (как в MangaLib: читаю / буду / бросил / прочитал)
CREATE TABLE IF NOT EXISTS shelf (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    status     TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, book_id),
    CHECK (status IN ('reading', 'want', 'dropped', 'read'))
);

-- Прогресс чтения («продолжить с места, где остановился») -------------------
CREATE TABLE IF NOT EXISTS reading_progress (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,         -- смещение в тексте (символ/страница)
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, book_id),
    CHECK (position >= 0)
);

-- Журнал действий пользователей с временными метками (УСЛОЖНЕНИЕ варианта 11)
CREATE TABLE IF NOT EXISTS action_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action     TEXT    NOT NULL,                   -- тип действия (login, add_book, ...)
    details    TEXT    NOT NULL DEFAULT '',        -- подробности
    ip         TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL                    -- временная метка
);

-- Баны пользователей -------------------------------------------------------
CREATE TABLE IF NOT EXISTS bans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason     TEXT    NOT NULL,
    banned_by  INTEGER REFERENCES users(id),
    until      TEXT,                               -- NULL = навсегда
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL,
    CHECK (is_active IN (0, 1))
);

-- Заявки на разбан ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS unban_requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text       TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'pending',
    created_at TEXT    NOT NULL,
    CHECK (status IN ('pending', 'approved', 'rejected'))
);

-- Индексы для ускорения частых запросов (поиск, сортировка, пагинация) ------
CREATE INDEX IF NOT EXISTS idx_books_author  ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_title   ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_year    ON books(year);
CREATE INDEX IF NOT EXISTS idx_comments_book ON comments(book_id);
CREATE INDEX IF NOT EXISTS idx_log_created   ON action_log(created_at);
CREATE INDEX IF NOT EXISTS idx_log_user      ON action_log(user_id);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Открыть соединение с базой данных и подготовить схему.

    :param path: путь к файлу базы данных; ``":memory:"`` — база в памяти
        (используется в тестах, чтобы они не влияли друг на друга).
    :returns: открытое соединение :class:`sqlite3.Connection`.

    Включается проверка внешних ключей (в SQLite она по умолчанию выключена),
    а ``row_factory`` позволяет обращаться к полям строки по имени.
    """
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    # Встроенные LOWER()/UPPER() в SQLite обрабатывают только латиницу, из-за
    # чего регистронезависимый поиск по кириллице и казахским буквам не работал
    # бы. Заменяем их Unicode-функциями Python (str.lower/str.upper).
    db.create_function(
        "lower", 1, lambda s: s.lower() if isinstance(s, str) else s,
        deterministic=True,
    )
    db.create_function(
        "upper", 1, lambda s: s.upper() if isinstance(s, str) else s,
        deterministic=True,
    )
    db.executescript(SCHEMA)
    return db
