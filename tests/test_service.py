"""Автотесты бизнес-логики (pytest).

Покрываются обычные, граничные и ошибочные случаи (раздел 5.5 методички).
Каждый тест получает новую базу данных в памяти через фикстуру ``db``,
поэтому тесты независимы друг от друга.

Запуск из корня проекта::

    python -m pytest -q
"""

import os
import sys

import pytest

# Позволяем запускать тесты из корня проекта без установки пакета.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import security, service
from app.db import connect


@pytest.fixture()
def db():
    """Новая пустая база данных в памяти для каждого теста."""
    connection = connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture()
def owner(db):
    """Пользователь-владелец (главный разработчик)."""
    uid = service.register_user(db, "owner1", "owner@ex.kz", "password123",
                                role="owner")
    return service.get_user(db, uid)


@pytest.fixture()
def reader(db):
    """Обычный зарегистрированный пользователь."""
    uid = service.register_user(db, "reader1", "reader@ex.kz", "password123")
    return service.get_user(db, uid)


# --- Пароли и JWT (модуль security) ---------------------------------------
def test_password_hash_roundtrip():
    h = security.hash_password("MyS3cret!")
    assert h != "MyS3cret!"                      # хранится не в открытом виде
    assert security.verify_password("MyS3cret!", h)
    assert not security.verify_password("wrong", h)


def test_password_hash_is_salted():
    # Один и тот же пароль даёт разные хэши (случайная соль).
    assert security.hash_password("same") != security.hash_password("same")


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        security.hash_password("")


def test_jwt_access_token_roundtrip():
    token = security.create_access_token(42, "student")
    payload = security.decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "student"
    assert payload["type"] == "access"


def test_jwt_invalid_token_rejected():
    import jwt as pyjwt
    with pytest.raises(pyjwt.InvalidTokenError):
        security.decode_token("not.a.valid.token")


# --- Регистрация и валидация ----------------------------------------------
def test_register_ok(db):
    uid = service.register_user(db, "alice", "alice@ex.kz", "password123")
    assert uid == 1
    assert service.get_user(db, uid)["username"] == "alice"


def test_register_duplicate_username(db):
    service.register_user(db, "bob", "bob@ex.kz", "password123")
    with pytest.raises(service.Conflict):
        service.register_user(db, "bob", "other@ex.kz", "password123")


@pytest.mark.parametrize("username,email,password", [
    ("ab", "a@ex.kz", "password123"),        # слишком короткий логин
    ("bad user", "a@ex.kz", "password123"),  # пробел в логине
    ("good", "not-an-email", "password123"),  # плохая почта
    ("good", "g@ex.kz", "short"),             # короткий пароль
])
def test_register_invalid(db, username, email, password):
    with pytest.raises(service.ValidationError):
        service.register_user(db, username, email, password)


def test_get_missing_user_raises(db):
    with pytest.raises(service.NotFoundError):
        service.get_user(db, 999)


# --- Аутентификация и защита от брутфорса ---------------------------------
def test_authenticate_ok(db, reader):
    user = service.authenticate(db, "reader1", "password123")
    assert user["id"] == reader["id"]


def test_authenticate_wrong_password(db, reader):
    with pytest.raises(service.AuthError):
        service.authenticate(db, "reader1", "WRONG")


def test_authenticate_unknown_user(db):
    with pytest.raises(service.AuthError):
        service.authenticate(db, "ghost", "password123")


def test_bruteforce_lockout(db, reader):
    # Исчерпываем лимит неудачных попыток -> аккаунт блокируется.
    for _ in range(security.MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(service.AuthError):
            service.authenticate(db, "reader1", "WRONG")
    with pytest.raises(service.AccountLocked):
        service.authenticate(db, "reader1", "WRONG")
    # Теперь даже правильный пароль не проходит, пока действует блокировка.
    with pytest.raises(service.AccountLocked):
        service.authenticate(db, "reader1", "password123")


# --- Права доступа (принцип наименьших привилегий) ------------------------
def test_permissions_matrix():
    assert service.has_permission("owner", "book.delete")      # owner может всё
    assert service.has_permission("editor", "book.add")
    assert not service.has_permission("student", "book.add")   # студент не может
    assert not service.has_permission("guest", "comment.write")
    assert service.has_permission("student", "book.read_paid")


def test_student_cannot_add_book(db):
    uid = service.register_user(db, "stud", "s@ex.kz", "password123",
                                role="student")
    with pytest.raises(service.PermissionDenied):
        service.add_book(db, "student", "Книга", "Автор")


# --- Книги: добавление, поиск, пагинация ----------------------------------
def test_add_and_get_book(db):
    bid = service.add_book(db, "owner", "Абай жолы", "Мұхтар Әуезов", year=1942)
    book = service.get_book(db, bid)
    assert book["title"] == "Абай жолы"
    assert book["author"] == "Мұхтар Әуезов"


def test_add_book_empty_title(db):
    with pytest.raises(service.ValidationError):
        service.add_book(db, "owner", "  ", "Автор")


def test_add_book_bad_year(db):
    with pytest.raises(service.ValidationError):
        service.add_book(db, "owner", "Книга", "Автор", year=3000)


def test_search_by_author_and_title(db):
    service.add_book(db, "owner", "Война и мир", "Толстой")
    service.add_book(db, "owner", "Анна Каренина", "Толстой")
    service.add_book(db, "owner", "Преступление и наказание", "Достоевский")
    res = service.search_books(db, author="толстой")
    assert res["total"] == 2
    res2 = service.search_books(db, query="наказание")
    assert res2["total"] == 1
    assert res2["items"][0]["author"] == "Достоевский"


def test_pagination(db):
    for i in range(25):
        service.add_book(db, "owner", f"Книга {i:02d}", "Автор")
    page1 = service.search_books(db, page=1, page_size=10)
    assert page1["total"] == 25
    assert page1["pages"] == 3
    assert len(page1["items"]) == 10
    page3 = service.search_books(db, page=3, page_size=10)
    assert len(page3["items"]) == 5          # остаток на последней странице


def test_pagination_page_size_clamped(db):
    service.add_book(db, "owner", "Книга", "Автор")
    res = service.search_books(db, page_size=10_000)
    assert res["page_size"] <= service.MAX_PAGE_SIZE


def test_sort_order(db):
    service.add_book(db, "owner", "Б книга", "Автор")
    service.add_book(db, "owner", "А книга", "Автор")
    asc = service.search_books(db, sort="title", order="asc")
    desc = service.search_books(db, sort="title", order="desc")
    assert asc["items"][0]["title"].startswith("А")
    assert desc["items"][0]["title"].startswith("Б")


def test_edit_and_delete_book(db):
    bid = service.add_book(db, "owner", "Старое", "Автор")
    service.edit_book(db, "editor", bid, title="Новое")
    assert service.get_book(db, bid)["title"] == "Новое"
    service.delete_book(db, "owner", bid)
    with pytest.raises(service.NotFoundError):
        service.get_book(db, bid)


def test_delete_missing_book(db):
    with pytest.raises(service.NotFoundError):
        service.delete_book(db, "owner", 404)


# --- Платные книги и доступ -----------------------------------------------
def test_paid_book_access(db):
    bid = service.add_book(db, "owner", "Платная", "Автор",
                           is_paid=True, paid_days=30)
    book = service.get_book(db, bid)
    assert service.can_read_book(None, book) is False           # гость не может
    student = {"id": 1, "role": "student", "is_student": 1, "added_by": None}
    assert service.can_read_book(student, book) is True         # студент может


def test_free_book_readable_by_guest(db):
    bid = service.add_book(db, "owner", "Бесплатная", "Автор")
    assert service.can_read_book(None, service.get_book(db, bid)) is True


# --- Комментарии и цензура -------------------------------------------------
def test_comment_with_badge(db, owner):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    cid = service.add_comment(db, owner, bid, "Отличная книга")
    comments = service.list_comments(db, bid)
    assert comments[0]["badge"] == "Главный разработчик"


def test_comment_censorship(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    service.add_comment(db, reader, bid, "Автор дурак и идиот")
    text = service.list_comments(db, bid)[0]["text"]
    assert "дурак" not in text and "идиот" not in text
    assert "*" in text


def test_empty_comment_rejected(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    with pytest.raises(service.ValidationError):
        service.add_comment(db, reader, bid, "   ")


def test_delete_own_vs_foreign_comment(db, reader):
    other_id = service.register_user(db, "other", "o@ex.kz", "password123")
    other = service.get_user(db, other_id)
    bid = service.add_book(db, "owner", "Книга", "Автор")
    cid = service.add_comment(db, other, bid, "Чужой комментарий")
    # Обычный пользователь не может удалить чужой комментарий.
    with pytest.raises(service.PermissionDenied):
        service.delete_comment(db, reader, cid)
    # Свой — может.
    own = service.add_comment(db, reader, bid, "Мой комментарий")
    service.delete_comment(db, reader, own)
    assert len(service.list_comments(db, bid)) == 1


# --- Полка и прогресс чтения ----------------------------------------------
def test_shelf_and_progress(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор", content="x" * 100)
    service.set_shelf_status(db, reader["id"], bid, "reading")
    shelf = service.get_shelf(db, reader["id"], status="reading")
    assert len(shelf) == 1
    service.save_progress(db, reader["id"], bid, 42)
    assert service.get_progress(db, reader["id"], bid) == 42
    # Обновление статуса и позиции (upsert).
    service.set_shelf_status(db, reader["id"], bid, "read")
    assert service.get_shelf(db, reader["id"], status="read")[0]["id"] == bid


def test_shelf_bad_status(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    with pytest.raises(service.ValidationError):
        service.set_shelf_status(db, reader["id"], bid, "unknown")


def test_negative_progress_rejected(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    with pytest.raises(service.ValidationError):
        service.save_progress(db, reader["id"], bid, -5)


# --- Баны и заявки на разбан ----------------------------------------------
def test_ban_and_unban(db, owner):
    target = service.get_user(
        db, service.register_user(db, "baduser", "bad@ex.kz", "password123"))
    service.ban_user(db, owner, target["id"], "спам", minutes=60)
    assert service.is_banned(db, target["id"]) is True
    # Забаненный не может войти.
    with pytest.raises(service.Banned):
        service.authenticate(db, "baduser", "password123")
    service.unban_user(db, owner, target["id"])
    assert service.is_banned(db, target["id"]) is False


def test_ban_requires_reason(db, owner):
    target = service.get_user(
        db, service.register_user(db, "xuser", "x@ex.kz", "password123"))
    with pytest.raises(service.ValidationError):
        service.ban_user(db, owner, target["id"], "")


def test_cannot_ban_owner(db, owner):
    target = service.get_user(
        db, service.register_user(db, "owner2", "o2@ex.kz", "password123",
                                  role="owner"))
    with pytest.raises(service.PermissionDenied):
        service.ban_user(db, owner, target["id"], "за что-то")


def test_unban_request_flow(db, owner):
    target = service.get_user(
        db, service.register_user(db, "user2", "u2@ex.kz", "password123"))
    service.ban_user(db, owner, target["id"], "нарушение", minutes=60)
    req = service.create_unban_request(db, target["id"], "Прошу прощения")
    service.resolve_unban_request(db, owner, req, approve=True)
    assert service.is_banned(db, target["id"]) is False


def test_regular_user_cannot_ban(db, reader):
    target = service.get_user(
        db, service.register_user(db, "vuser", "v@ex.kz", "password123"))
    with pytest.raises(service.PermissionDenied):
        service.ban_user(db, reader, target["id"], "причина")


# --- Журнал действий (усложнение) -----------------------------------------
def test_action_log(db, reader):
    service.log_action(db, reader["id"], "login", "вход выполнен", "127.0.0.1")
    service.log_action(db, reader["id"], "read_book", "книга 1")
    log = service.list_log(db, user_id=reader["id"])
    assert len(log) == 2
    assert log[0]["action"] == "read_book"       # новые записи первыми
    assert log[0]["created_at"]                   # есть временная метка


# --- Роли и верификация студента ------------------------------------------
def test_assign_role(db, owner):
    target = service.get_user(
        db, service.register_user(db, "promote", "p@ex.kz", "password123"))
    service.assign_role(db, owner["role"], target["id"], "moderator")
    assert service.get_user(db, target["id"])["role"] == "moderator"


def test_only_owner_assigns_roles(db):
    target = service.get_user(
        db, service.register_user(db, "tuser", "t@ex.kz", "password123"))
    with pytest.raises(service.PermissionDenied):
        service.assign_role(db, "moderator", target["id"], "editor")


def test_verify_student(db, owner):
    target = service.get_user(
        db, service.register_user(db, "stud2", "s2@ex.kz", "password123",
                                  role="user"))
    service.verify_student(db, owner["role"], target["id"])
    assert service.get_user(db, target["id"])["is_student"] == 1


# --- Статистика и теги -----------------------------------------------------
def test_reading_stats_owner_infinite(db, owner):
    stats = service.reading_stats(db)
    owner_entry = [e for e in stats["leaderboard"] if e["role"] == "owner"][0]
    assert owner_entry["read_count"] == "∞"


def test_tags(db):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    service.tag_book(db, bid, "Классика")
    service.tag_book(db, bid, "Роман")
    assert set(service.book_tags(db, bid)) == {"классика", "роман"}
