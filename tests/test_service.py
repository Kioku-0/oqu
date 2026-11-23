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
    with pytest.raises(service.ConflictError):
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
    with pytest.raises(service.AccountLockedError) as first:
        service.authenticate(db, "reader1", "WRONG")
    # Сервер сообщает, сколько секунд ждать (для таймера в окне входа).
    assert first.value.retry_after == security.LOCKOUT_SECONDS
    # Теперь даже правильный пароль не проходит, пока действует блокировка.
    with pytest.raises(service.AccountLockedError) as again:
        service.authenticate(db, "reader1", "password123")
    assert 0 < again.value.retry_after <= security.LOCKOUT_SECONDS + 1


# --- Права доступа (принцип наименьших привилегий) ------------------------
def test_permissions_matrix():
    assert service.has_permission("owner", "book.delete")  # может всё
    assert service.has_permission("editor", "book.add")
    assert not service.has_permission("student", "book.add")
    assert not service.has_permission("guest", "comment.write")
    assert service.has_permission("student", "book.read_paid")


def test_student_cannot_add_book(db):
    service.register_user(db, "stud", "s@ex.kz", "password123",
                                role="student")
    with pytest.raises(service.PermissionDeniedError):
        service.add_book(db, "student", "Книга", "Автор")


# --- Книги: добавление, поиск, пагинация ----------------------------------
def test_add_and_get_book(db):
    bid = service.add_book(db, "owner", "Абай жолы", "Мұхтар Әуезов",
                           year=1942)
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
    assert service.can_read_book(None, book) is False  # гость не может
    student = {"id": 1, "role": "student", "is_student": 1, "added_by": None}
    assert service.can_read_book(student, book) is True         # студент может


def test_free_book_readable_by_guest(db):
    bid = service.add_book(db, "owner", "Бесплатная", "Автор")
    assert service.can_read_book(None, service.get_book(db, bid)) is True


# --- Комментарии и цензура -------------------------------------------------
def test_comment_with_badge(db, owner):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    service.add_comment(db, owner, bid, "Отличная книга")
    comments = service.list_comments(db, bid)
    assert comments["items"][0]["badge"] == "owner"   # код приписки


def test_comment_censorship(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    service.add_comment(db, reader, bid, "Автор дурак и идиот")
    text = service.list_comments(db, bid)["items"][0]["text"]
    assert "дурак" not in text and "идиот" not in text
    assert "*" in text


@pytest.mark.parametrize("word", [
    "блять", "Сука", "охуел", "заебал", "пиздец", "долбоёб", "нахуй",
    "xуй",          # латинская x вместо русской х
    "п0здно-пиздато",
    "FUCK", "shitty", "ақымақ", "мудак", "ебанутый",
])
def test_profanity_masked(word):
    masked = service.censor_profanity(f"Ну ты {word}!")
    assert word not in masked and "*" in masked


@pytest.mark.parametrize("word", [
    "страхует", "колебался", "ребенок", "употребляя", "хулиган",
    "педикюр", "сучки на дереве", "небо", "хлеб", "оскорблять",
    "Абай жолы", "Shakespeare", "мудрый", "застраховать",
])
def test_normal_words_untouched(word):
    assert service.censor_profanity(word) == word


def test_censorship_applies_to_owner(db, owner):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    service.add_comment(db, owner, bid, "Это пиздец")
    assert "пиздец" not in service.list_comments(db, bid)["items"][0]["text"]


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
    with pytest.raises(service.PermissionDeniedError):
        service.delete_comment(db, reader, cid)
    # Свой — может.
    own = service.add_comment(db, reader, bid, "Мой комментарий")
    service.delete_comment(db, reader, own)
    assert service.list_comments(db, bid)["total"] == 1


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
    service.ban_user(db, owner, target["id"], "спам", seconds=3600)
    assert service.is_banned(db, target["id"]) is True
    # Забаненный не может войти.
    with pytest.raises(service.BannedError):
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
    with pytest.raises(service.PermissionDeniedError):
        service.ban_user(db, owner, target["id"], "за что-то")


def test_unban_request_flow(db, owner):
    target = service.get_user(
        db, service.register_user(db, "user2", "u2@ex.kz", "password123"))
    service.ban_user(db, owner, target["id"], "нарушение", seconds=3600)
    req = service.create_unban_request(db, target["id"], "Прошу прощения")
    service.resolve_unban_request(db, owner, req, approve=True)
    assert service.is_banned(db, target["id"]) is False


def test_regular_user_cannot_ban(db, reader):
    target = service.get_user(
        db, service.register_user(db, "vuser", "v@ex.kz", "password123"))
    with pytest.raises(service.PermissionDeniedError):
        service.ban_user(db, reader, target["id"], "причина")


# --- Журнал действий (усложнение) -----------------------------------------
def test_action_log(db, reader):
    service.log_action(db, reader["id"], "login", "вход выполнен", "127.0.0.1")
    service.log_action(db, reader["id"], "read_book", "книга 1")
    log = service.list_log(db, user_id=reader["id"])["items"]
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
    with pytest.raises(service.PermissionDeniedError):
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


# ===========================================================================
# Версия 2.0: новые функции
# ===========================================================================
def _user(db, name, role="user"):
    uid = service.register_user(db, name, f"{name}@ex.kz", "password123",
                                role=role)
    return service.get_user(db, uid)


# --- Соглашение и пароль -----------------------------------------------------
def test_register_requires_terms(db):
    with pytest.raises(service.ValidationError):
        service.register_user(db, "noterms", "n@ex.kz", "password123",
                              accept_terms=False)


def test_register_saves_agreement(db, reader):
    assert reader["agreed_at"]
    assert reader["agreement_ver"] == service.AGREEMENT_VERSION


@pytest.mark.parametrize("password", ["onlyletters", "12345678", "a1" * 65])
def test_weak_or_long_password_rejected(db, password):
    with pytest.raises(service.ValidationError):
        service.register_user(db, "weak", "w@ex.kz", password)


def test_login_is_case_insensitive(db, reader):
    assert service.authenticate(db, "READER1", "password123")["id"] == \
        reader["id"]


def test_change_password(db, reader):
    with pytest.raises(service.AuthError):
        service.change_password(db, reader["id"], "wrong", "newpass123")
    service.change_password(db, reader["id"], "password123", "newpass123")
    assert service.authenticate(db, "reader1", "newpass123")


# --- Удаление аккаунта -------------------------------------------------------
def test_delete_account_needs_password(db, reader):
    with pytest.raises(service.AuthError):
        service.delete_account(db, reader["id"], "wrong")
    service.delete_account(db, reader["id"], "password123")
    with pytest.raises(service.NotFoundError):
        service.get_user(db, reader["id"])


def test_owner_cannot_delete_self(db, owner):
    with pytest.raises(service.PermissionDeniedError):
        service.delete_account(db, owner["id"], "password123")


def test_only_owner_deletes_others(db, owner, reader):
    moder = _user(db, "moder", "moderator")
    with pytest.raises(service.PermissionDeniedError):
        service.admin_delete_user(db, moder, reader["id"])
    service.admin_delete_user(db, owner, reader["id"])
    with pytest.raises(service.NotFoundError):
        service.get_user(db, reader["id"])


# --- Комментарии: редактирование и приписки ----------------------------------
def test_edit_own_comment_only(db, reader):
    other = _user(db, "other2")
    bid = service.add_book(db, "owner", "Книга", "Автор")
    cid = service.add_comment(db, reader, bid, "Было")
    with pytest.raises(service.PermissionDeniedError):
        service.edit_comment(db, other, cid, "Чужая правка")
    service.edit_comment(db, reader, cid, "Стало дурак")
    item = service.list_comments(db, bid)["items"][0]
    assert item["text"].startswith("Стало д*")       # цензура и при правке
    assert item["edited_at"]


def test_author_badge_on_own_book(db):
    author = _user(db, "writer", "author")
    bid = service.add_book(db, "author", "Моя", "Я", added_by=author["id"])
    service.add_comment(db, author, bid, "Спасибо за отзывы")
    assert service.list_comments(db, bid)["items"][0]["badge"] == "author_own"


def test_comment_too_long(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    with pytest.raises(service.ValidationError):
        service.add_comment(db, reader, bid,
                            "x" * (service.MAX_COMMENT_LEN + 1))


# --- Права на книги: автор управляет только своими ---------------------------
def test_author_edits_only_own_book(db):
    author = _user(db, "writer2", "author")
    own = service.add_book(db, "author", "Своя", "Я", added_by=author["id"])
    foreign = service.add_book(db, "owner", "Чужая", "Другой")
    service.edit_book(db, author, own, title="Своя 2")
    assert service.get_book(db, own)["title"] == "Своя 2"
    with pytest.raises(service.PermissionDeniedError):
        service.edit_book(db, author, foreign, title="Взлом")
    with pytest.raises(service.PermissionDeniedError):
        service.delete_book(db, author, foreign)


def test_moderator_cannot_touch_books():
    assert not service.has_permission("moderator", "book.add")
    assert not service.has_permission("moderator", "book.delete")
    assert service.has_permission("moderator", "user.ban")


def test_bad_cover_color(db):
    with pytest.raises(service.ValidationError):
        service.add_book(db, "owner", "Книга", "Автор", cover_color="red")


def test_paid_book_needs_term(db):
    with pytest.raises(service.ValidationError):
        service.add_book(db, "owner", "Платная", "Автор", is_paid=True)


# --- Платные книги: покупка и истечение срока --------------------------------
def test_buy_paid_book(db, reader):
    bid = service.add_book(db, "owner", "Новинка", "Автор", is_paid=True,
                           price=990, paid_days=30)
    book = service.get_book(db, bid)
    assert not service.user_can_read(db, reader, book)
    assert service.buy_book(db, reader, bid) == 990
    assert service.user_can_read(db, reader, book)
    with pytest.raises(service.ConflictError):
        service.buy_book(db, reader, bid)              # повторно не нужно


def test_buy_free_book_conflict(db, reader):
    bid = service.add_book(db, "owner", "Бесплатная", "Автор")
    with pytest.raises(service.ConflictError):
        service.buy_book(db, reader, bid)


def test_paid_book_becomes_free(db):
    bid = service.add_book(db, "owner", "Была платной", "Автор",
                           is_paid=True, paid_days=1)
    db.execute("UPDATE books SET paid_until = '2000-01-01 00:00:00' "
               "WHERE id = ?", (bid,))
    book = service.get_book(db, bid)
    assert service.is_paid_now(book) is False
    assert service.can_read_book(None, book) is True
    assert service.search_books(db, access="free")["total"] == 1


# --- Поиск: фильтры, теги, диапазон лет, сортировка --------------------------
def test_search_filters(db):
    service.add_book(db, "owner", "Абай жолы", "Әуезов", year=1942,
                     genre="Роман", tags=["классика"])
    service.add_book(db, "owner", "Python", "Айтимов", year=2026,
                     genre="учебник")
    assert service.search_books(db, tag="классика")["total"] == 1
    assert service.search_books(db, genre="роман")["total"] == 1
    assert service.search_books(db, year_from=2000,
                                year_to=2030)["total"] == 1
    assert service.search_books(db, query="ӘУЕЗОВ")["total"] == 1
    assert "content" not in service.search_books(db)["items"][0]


def test_search_injection_in_sort_is_ignored(db):
    service.add_book(db, "owner", "Книга", "Автор")
    res = service.search_books(db, sort="title; DROP TABLE books")
    assert res["total"] == 1


def test_sort_by_rating(db, reader):
    low = service.add_book(db, "owner", "Слабая", "А")
    high = service.add_book(db, "owner", "Сильная", "Б")
    service.rate_book(db, reader, low, 2)
    service.rate_book(db, reader, high, 5)
    items = service.search_books(db, sort="rating", order="desc")["items"]
    assert items[0]["id"] == high


def test_page_beyond_end_is_empty(db):
    service.add_book(db, "owner", "Книга", "Автор")
    res = service.search_books(db, page=99)
    assert res["items"] == [] and res["total"] == 1


# --- Оценки ------------------------------------------------------------------
@pytest.mark.parametrize("value", [0, 6, -1])
def test_rating_bounds(db, reader, value):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    with pytest.raises(service.ValidationError):
        service.rate_book(db, reader, bid, value)


def test_rating_upsert(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    service.rate_book(db, reader, bid, 3)
    service.rate_book(db, reader, bid, 5)
    details = service.get_book_details(db, bid)
    assert details["rating"] == 5 and details["rating_count"] == 1


# --- Продолжить чтение и закладки --------------------------------------------
def test_progress_puts_book_on_reading_shelf(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор", content="текст")
    service.save_progress(db, reader["id"], bid, 500)
    assert service.shelf_status(db, reader["id"], bid) == "reading"
    cont = service.continue_reading(db, reader["id"])
    assert cont[0]["id"] == bid and cont[0]["position"] == 500
    service.set_shelf_status(db, reader["id"], bid, "read")
    assert service.continue_reading(db, reader["id"]) == []


@pytest.mark.parametrize("lang", ["kk", "ky", "en"])
def test_translations_complete(lang):
    # В kk/ky/en нет только русских форм множественного числа (few/many).
    from app import i18n
    missing = {k for k in i18n.missing_keys(lang)
               if not k.endswith((".few", ".many"))}
    assert missing == set()


def test_kyrgyz_language_for_user_and_book(db, reader):
    service.set_language(db, reader["id"], "ky")
    assert service.get_user(db, reader["id"])["language"] == "ky"
    bid = service.add_book(db, "owner", "Манас", "Эл оозунан", language="ky")
    assert service.get_book(db, bid)["language"] == "ky"


def test_old_database_gets_kyrgyz(tmp_path):
    # База, созданная до появления кыргызского, должна принять «ky»
    # после обновления программы (миграция ограничения CHECK).
    import sqlite3
    from app import db as dbmod
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(dbmod.SCHEMA.replace(dbmod._NEW_LANG_CHECK,
                                           dbmod._OLD_LANG_CHECK))
    old.close()
    conn = connect(path)
    try:
        sql = conn.execute("SELECT sql FROM sqlite_master "
                           "WHERE name = 'users'").fetchone()[0]
        assert "'ky'" in sql
        uid = service.register_user(conn, "kyrgyz", "ky@mail.kg",
                                    "Parol2026", language="ky")
        assert service.get_user(conn, uid)["language"] == "ky"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_reading_moves_want_to_reading(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор", content="текст")
    service.set_shelf_status(db, reader["id"], bid, "want")
    service.save_progress(db, reader["id"], bid, 10)
    assert service.shelf_status(db, reader["id"], bid) == "reading"


def test_remove_from_shelf(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    service.set_shelf_status(db, reader["id"], bid, "want")
    service.set_shelf_status(db, reader["id"], bid, None)
    assert service.shelf_counts(db, reader["id"])["want"] == 0


def test_bookmarks(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    mid = service.add_bookmark(db, reader["id"], bid, 120, "Важная мысль")
    assert service.list_bookmarks(db, reader["id"], bid)[0]["note"] == \
        "Важная мысль"
    other = _user(db, "thief")
    with pytest.raises(service.NotFoundError):
        service.delete_bookmark(db, other["id"], mid)   # чужую нельзя
    service.delete_bookmark(db, reader["id"], mid)
    assert service.list_bookmarks(db, reader["id"]) == []


def test_bookmark_note_too_long(db, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    with pytest.raises(service.ValidationError):
        service.add_bookmark(db, reader["id"], bid, 0,
                             "x" * (service.MAX_NOTE_LEN + 1))


# --- Заявка на статус студента -----------------------------------------------
def test_student_request_flow(db, reader):
    moder = _user(db, "moder2", "moderator")
    rid = service.submit_student_request(db, reader, "card.jpg")
    with pytest.raises(service.ConflictError):
        service.submit_student_request(db, reader, "again.jpg")
    assert len(service.list_student_requests(db, "moderator")) == 1
    service.review_student_request(db, moder, rid, approve=True)
    user = service.get_user(db, reader["id"])
    assert user["is_student"] == 1 and user["role"] == "student"
    with pytest.raises(service.ConflictError):
        service.review_student_request(db, moder, rid, approve=False)


def test_reader_cannot_review_students(db):
    with pytest.raises(service.PermissionDeniedError):
        service.list_student_requests(db, "user")


# --- Баны: срок, персонал, заявка без входа ----------------------------------
def test_ban_expires(db, owner, reader):
    service.ban_user(db, owner, reader["id"], "тест", seconds=60)
    db.execute("UPDATE bans SET until = '2000-01-01 00:00:00'")
    assert service.is_banned(db, reader["id"]) is False


def test_banned_error_has_reason(db, owner, reader):
    service.ban_user(db, owner, reader["id"], "спам в комментариях")
    with pytest.raises(service.BannedError) as err:
        service.authenticate(db, "reader1", "password123")
    assert err.value.reason == "спам в комментариях"
    assert err.value.until is None                       # навсегда


def test_moderator_cannot_ban_staff(db):
    moder = _user(db, "moder3", "moderator")
    editor = _user(db, "editor3", "editor")
    with pytest.raises(service.PermissionDeniedError):
        service.ban_user(db, moder, editor["id"], "причина")


def test_unban_request_by_credentials(db, owner, reader):
    service.ban_user(db, owner, reader["id"], "нарушение")
    with pytest.raises(service.AuthError):
        service.unban_request_by_credentials(db, "reader1", "wrong",
                                             "прошу")
    rid = service.unban_request_by_credentials(db, "reader1", "password123",
                                               "Больше не буду")
    req = service.list_unban_requests(db, "moderator")[0]
    assert req["id"] == rid and req["ban_reason"] == "нарушение"


# --- Журнал: фильтры и пагинация ---------------------------------------------
def test_log_filters_and_pages(db, reader):
    for i in range(7):
        service.log_action(db, reader["id"],
                           "login" if i % 2 else "read_book")
    page = service.list_log(db, page=1, page_size=3)
    assert page["total"] == 7 and page["pages"] == 3
    assert service.list_log(db, action="login")["total"] == 3
    assert service.list_log(db, date_from="2000-01-01",
                            date_to="2000-01-02")["total"] == 0
    assert page["items"][0]["username"] == "reader1"


# --- Статистика --------------------------------------------------------------
def test_stats_owner_first(db, owner, reader):
    bid = service.add_book(db, "owner", "Книга", "Автор", genre="роман")
    service.set_shelf_status(db, reader["id"], bid, "read")
    stats = service.reading_stats(db)
    assert stats["leaderboard"][0]["role"] == "owner"
    assert stats["leaderboard"][0]["place"] == 0       # вне конкурса
    assert stats["leaderboard"][1]["read_count"] == 1
    assert stats["leaderboard"][1]["place"] == 1       # борьба за 1-е
    assert stats["top_books"][0]["id"] == bid
    assert stats["genres"][0] == {"name": "роман", "count": 1}


def test_list_users_search_and_ban_info(db, owner, reader):
    service.ban_user(db, owner, reader["id"], "флуд", seconds=60)
    res = service.list_users(db, query="READER", page_size=5)
    assert res["total"] == 1
    assert res["items"][0]["banned"] and res["items"][0]["ban_reason"] == \
        "флуд"
    assert "password_hash" not in res["items"][0]     # хэш не отдаём


def test_genres_tags_random(db):
    service.add_book(db, "owner", "А", "X", genre="роман", tags=["a", "b"])
    service.add_book(db, "owner", "Б", "Y", genre="роман", tags=["a"])
    service.add_book(db, "owner", "В", "Z", genre="поэзия")
    assert service.list_genres(db)[0] == {"name": "роман", "count": 2}
    assert service.popular_tags(db)[0] == {"name": "a", "count": 2}
    assert len(service.random_books(db, "поэзия")) == 1
    assert len(service.random_books(db, limit=1000)) == 3   # лимит зажат


def test_purge_old_log(db, reader):
    service.log_action(db, reader["id"], "login")
    db.execute("UPDATE action_log SET created_at = '2000-01-01 00:00:00'")
    service.log_action(db, reader["id"], "login")
    assert service.purge_old_log(db) == 1
    assert service.list_log(db)["total"] == 1


@pytest.mark.parametrize("name", ["", " ", "x" * 65])
def test_update_profile_bounds(db, reader, name):
    with pytest.raises(service.ValidationError):
        service.update_profile(db, reader["id"], name)


def test_update_profile_and_language(db, reader):
    service.update_profile(db, reader["id"], "Дана")
    service.set_language(db, reader["id"], "kk")
    user = service.get_user(db, reader["id"])
    assert user["display_name"] == "Дана" and user["language"] == "kk"
    with pytest.raises(service.ValidationError):
        service.set_language(db, reader["id"], "de")


def test_book_details_missing(db):
    with pytest.raises(service.NotFoundError):
        service.get_book_details(db, 777)


def test_owner_has_all_permissions():
    perms = service.permissions_of("owner")
    assert "user.assign_role" in perms and "book.delete" in perms
    assert service.permissions_of("guest") == ["book.read_free"]


def test_create_owner_from_env(tmp_path, monkeypatch):
    from app import seed
    monkeypatch.setattr(seed, "DB_PATH", str(tmp_path / "prod.sqlite"))
    monkeypatch.setenv("OQU_OWNER_USERNAME", "admin")
    monkeypatch.setenv("OQU_OWNER_EMAIL", "admin@ex.kz")
    monkeypatch.setenv("OQU_OWNER_PASSWORD", "Secret123")
    seed.create_owner()
    seed.create_owner()                      # второй раз — без дубликата
    db = connect(str(tmp_path / "prod.sqlite"))
    rows = db.execute("SELECT username, role FROM users").fetchall()
    db.close()
    assert [tuple(r) for r in rows] == [("admin", "owner")]


def test_set_book_tags_limit(db):
    bid = service.add_book(db, "owner", "Книга", "Автор")
    with pytest.raises(service.ValidationError):
        service.set_book_tags(db, bid, [f"t{i}" for i in range(11)])
    service.set_book_tags(db, bid, ["#Новое", "новое", "Старое"])
    assert service.book_tags(db, bid) == ["новое", "старое"]
