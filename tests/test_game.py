"""Тесты мини-игры «Парақ» и иллюстраций книг.

Проверяются формулы игры, обычное сохранение и защита от накрутки
(граничные и ошибочные случаи), таблица рекордов, а также регистрация
иллюстраций и картинки обложки.
"""

import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import service
from app.db import connect


@pytest.fixture()
def db():
    connection = connect(":memory:")
    yield connection
    connection.close()


def _user(db, name):
    uid = service.register_user(db, name, f"{name}@ex.kz", "password123")
    return service.get_user(db, uid)


def _age_save(db, user_id, seconds):
    """Сделать вид, что прошлое сохранение было ``seconds`` секунд назад."""
    past = (service._now() - timedelta(seconds=seconds)).strftime(
        service.DATETIME_FMT)
    db.execute("UPDATE game_saves SET updated_at = ? WHERE user_id = ?",
               (past, user_id))
    db.commit()


# --- Формулы ----------------------------------------------------------------
def test_game_cost_grows():
    assert service.game_cost("bookmark", 0) == 15
    assert service.game_cost("bookmark", 1) == pytest.approx(15 * 1.15)
    assert service.game_spent({"bookmark": 2}) == pytest.approx(15 + 17.25)


def test_game_click_power_and_rate():
    assert service.game_click_power({}) == 1
    assert service.game_click_power({"bookmark": 3}) == 4
    # «Алтынбек одобрил» удваивает силу клика
    assert service.game_click_power({"bookmark": 3, "altynbek": 1}) == 8
    assert service.game_rate({"student": 2, "lamp": 1}) == pytest.approx(4)
    # «Темірлан» удваивает производство, «Едіге» кликает 2 раза в секунду
    assert service.game_rate({"lamp": 1, "temirlan": 1}) == pytest.approx(6)
    assert service.game_rate({"edige": 1}) == pytest.approx(2)


# --- Сохранение -------------------------------------------------------------
def test_game_first_save_ok(db):
    user = _user(db, "player1")
    saved = service.save_game(db, user["id"], 25, 40, 40, {"bookmark": 1})
    assert saved["pages_total"] == 40
    assert saved["upgrades"] == {"bookmark": 1}
    assert service.get_game(db, user["id"])["clicks"] == 40


def test_game_new_player_is_empty(db):
    user = _user(db, "player1")
    assert service.get_game(db, user["id"])["pages_total"] == 0


@pytest.mark.parametrize("pages, total, clicks, upgrades", [
    (-1, 10, 10, {}),                  # отрицательные страницы
    (20, 10, 10, {}),                  # сейчас больше, чем собрано всего
    (0, 10, 10, {"dragon": 1}),        # неизвестное улучшение
    (0, 10, 10, {"edige": 2}),         # разовое улучшение дважды
    (0, 10, 10, {"bookmark": 1}),      # закладка стоит 15, а собрано 10
    (0, 10, 10, {"bookmark": True}),   # не число
])
def test_game_invalid_save_rejected(db, pages, total, clicks, upgrades):
    user = _user(db, "player1")
    with pytest.raises(service.ValidationError):
        service.save_game(db, user["id"], pages, total, clicks, upgrades)


def test_game_too_fast_growth_rejected(db):
    user = _user(db, "player1")
    service.save_game(db, user["id"], 10, 10, 10, {})
    _age_save(db, user["id"], 10)
    # за 10 секунд без улучшений и с 5 кликами миллион страниц не собрать
    with pytest.raises(service.ValidationError):
        service.save_game(db, user["id"], 10 ** 6, 10 ** 6, 15, {})


def test_game_too_many_clicks_rejected(db):
    user = _user(db, "player1")
    service.save_game(db, user["id"], 0, 0, 0, {})
    _age_save(db, user["id"], 5)
    with pytest.raises(service.ValidationError):
        service.save_game(db, user["id"], 0, 0, 1000, {})


def test_game_progress_cannot_decrease(db):
    user = _user(db, "player1")
    service.save_game(db, user["id"], 50, 50, 50, {})
    with pytest.raises(service.ValidationError):
        service.save_game(db, user["id"], 10, 10, 10, {})


def test_game_honest_growth_with_upgrades_ok(db):
    user = _user(db, "player1")
    service.save_game(db, user["id"], 0, 100, 100, {"student": 1})
    _age_save(db, user["id"], 60)
    # студент даёт 0,5 стр./с: за минуту ~30 страниц + 60 кликов — честно
    saved = service.save_game(db, user["id"], 90, 190, 160, {"student": 1})
    assert saved["pages_total"] == 190


def test_game_reset(db):
    user = _user(db, "player1")
    service.save_game(db, user["id"], 5, 5, 5, {})
    service.reset_game(db, user["id"])
    assert service.get_game(db, user["id"])["pages_total"] == 0


def test_game_leaderboard_equal_players(db):
    owner_id = service.register_user(db, "boss", "boss@ex.kz", "password123",
                                     role="owner")
    a, b = _user(db, "player_a"), _user(db, "player_b")
    service.save_game(db, owner_id, 10, 10, 10, {})
    service.save_game(db, a["id"], 50, 50, 50, {})
    service.save_game(db, b["id"], 50, 50, 50, {})
    top = service.game_leaderboard(db)
    # владелец не получает особого места: он просто третий
    assert [e["username"] for e in top][-1] == "boss"
    assert top[-1]["place"] == 3
    assert top[0]["place"] == top[1]["place"] == 1


def test_game_config_has_upgrades():
    config = service.game_config()
    assert "bookmark" in config["upgrades"]
    assert config["cost_growth"] == service.GAME_COST_GROWTH


# --- Иллюстрации и обложки --------------------------------------------------
def _book(db):
    return service.add_book(db, "editor", "Книга", "Автор", content="Текст")


def test_add_book_image_returns_markup(db):
    bid = _book(db)
    markup = service.add_book_image(db, bid, "a" * 32 + ".png")
    assert markup == "![](img:" + "a" * 32 + ".png)"
    assert service.book_files(db, bid) == ["a" * 32 + ".png"]


def test_book_image_limit(db, monkeypatch):
    bid = _book(db)
    monkeypatch.setattr(service, "MAX_IMAGES_PER_BOOK", 1)
    service.add_book_image(db, bid, "b" * 32 + ".png")
    with pytest.raises(service.ValidationError):
        service.add_book_image(db, bid, "c" * 32 + ".png")


def test_book_image_missing_book(db):
    with pytest.raises(service.NotFoundError):
        service.add_book_image(db, 999, "d" * 32 + ".png")


def test_set_book_cover_returns_old(db):
    bid = _book(db)
    name = "e" * 32 + ".jpg"
    assert service.set_book_cover(db, bid, name) is None
    assert service.get_book_details(db, bid)["cover_image"] == name
    assert service.set_book_cover(db, bid, None) == name
    assert name not in service.book_files(db, bid)
