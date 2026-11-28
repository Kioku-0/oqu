"""Тесты новостей на главной и пульта живой презентации.

Обычные, граничные и ошибочные случаи: права, проверка ссылок и сроков,
пагинация, переключение слайдов за края, пауза таймера.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import service
from app.db import connect


@pytest.fixture()
def db():
    connection = connect(":memory:")
    yield connection
    connection.close()


def _user(db, name, role):
    uid = service.register_user(db, name, f"{name}@ex.kz", "password123",
                                role=role)
    return service.get_user(db, uid)


@pytest.fixture()
def owner(db):
    return _user(db, "owner1", "owner")


@pytest.fixture()
def editor(db):
    return _user(db, "editor1", "editor")


@pytest.fixture()
def reader(db):
    return _user(db, "reader1", "user")


# --- Новости ----------------------------------------------------------------
def test_editor_publishes_news_and_it_is_listed(db, editor):
    nid = service.add_news(db, editor, kind="contest", title="Конкурс",
                           body="Текст", prize="10 000 ₸",
                           ends_at="2026-12-20 18:59:59", link="#/game")
    page = service.list_news(db)
    assert page["total"] == 1
    item = page["items"][0]
    assert item["id"] == nid and item["kind"] == "contest"
    assert item["prize"] == "10 000 ₸" and item["link"] == "#/game"


@pytest.mark.parametrize("role", ["user", "student", "author", "moderator"])
def test_other_roles_cannot_publish_news(db, role):
    actor = _user(db, "u_" + role, role)
    with pytest.raises(service.PermissionDeniedError):
        service.add_news(db, actor, kind="update", title="Нельзя")


def test_owner_can_publish_news(db, owner):
    assert service.add_news(db, owner, kind="event", title="Защита") > 0


@pytest.mark.parametrize("link", ["https://evil.example", "javascript:x",
                                  "//evil.example", "#/a b"])
def test_news_link_must_stay_inside_site(db, editor, link):
    with pytest.raises(service.ValidationError):
        service.add_news(db, editor, kind="update", title="Т", link=link)


@pytest.mark.parametrize("bad", [
    {"kind": "spam", "title": "Т"},
    {"kind": "update", "title": "   "},
    {"kind": "update", "title": "x" * 121},
    {"kind": "update", "title": "Т", "ends_at": "20-12-2026"},
])
def test_news_validation(db, editor, bad):
    with pytest.raises(service.ValidationError):
        service.add_news(db, editor, **bad)


def test_news_title_is_censored(db, editor):
    service.add_news(db, editor, kind="update", title="Ну ты блять")
    assert "блять" not in service.list_news(db)["items"][0]["title"]


def test_pinned_news_first_and_pagination(db, editor):
    for i in range(7):
        service.add_news(db, editor, kind="update", title=f"Новость {i}")
    service.add_news(db, editor, kind="marathon", title="Главная",
                     pinned=True)
    first = service.list_news(db, page=1, page_size=3)
    assert first["items"][0]["title"] == "Главная"
    assert first["total"] == 8 and first["pages"] == 3
    last = service.list_news(db, page=3, page_size=3)
    assert len(last["items"]) == 2


def test_news_filter_by_kind(db, editor):
    service.add_news(db, editor, kind="contest", title="К")
    service.add_news(db, editor, kind="update", title="О")
    assert [n["title"] for n in
            service.list_news(db, kind="contest")["items"]] == ["К"]
    with pytest.raises(service.ValidationError):
        service.list_news(db, kind="spam")


def test_delete_news(db, editor, reader):
    nid = service.add_news(db, editor, kind="update", title="Т")
    with pytest.raises(service.PermissionDeniedError):
        service.delete_news(db, reader, nid)
    service.delete_news(db, editor, nid)
    assert service.list_news(db)["total"] == 0
    with pytest.raises(service.NotFoundError):
        service.delete_news(db, editor, nid)


def test_demo_news_added_once(db, editor):
    from app.seed import add_demo_news
    assert add_demo_news(db, editor) > 0
    assert add_demo_news(db, editor) == 0


# --- Пульт презентации -------------------------------------------------------
def test_present_state_before_start(db):
    s = service.get_present_state(db, now=100.0)
    assert s["slide"] == 0 and not s["started"] and s["elapsed"] == 0


def test_only_owner_controls_presentation(db, editor):
    with pytest.raises(service.PermissionDeniedError):
        service.control_present(db, editor, "next")
    assert "present.control" not in service.permissions_of("editor")
    assert "present.control" in service.permissions_of("owner")


def test_timer_start_pause_resume(db, owner):
    service.control_present(db, owner, "start", now=1000.0)
    assert service.get_present_state(db, now=1060.0)["elapsed"] == 60
    service.control_present(db, owner, "pause", now=1060.0)
    # Во время паузы время не идёт.
    paused = service.get_present_state(db, now=1500.0)
    assert paused["elapsed"] == 60 and not paused["running"]
    service.control_present(db, owner, "resume", now=1500.0)
    assert service.get_present_state(db, now=1530.0)["elapsed"] == 90


def test_slides_do_not_go_past_edges(db, owner):
    service.control_present(db, owner, "prev")
    assert service.get_present_state(db)["slide"] == 0
    for _ in range(service.PRESENT_SLIDES + 3):
        service.control_present(db, owner, "next")
    assert service.get_present_state(db)["slide"] == \
        service.PRESENT_SLIDES - 1


@pytest.mark.parametrize("slide", [None, -1, service.PRESENT_SLIDES])
def test_goto_wrong_slide(db, owner, slide):
    with pytest.raises(service.ValidationError):
        service.control_present(db, owner, "goto", slide)


def test_start_and_reset_return_to_first_slide(db, owner):
    service.control_present(db, owner, "goto", 5)
    service.control_present(db, owner, "start", now=10.0)
    assert service.get_present_state(db, now=11.0)["slide"] == 0
    service.control_present(db, owner, "goto", 3)
    s = service.control_present(db, owner, "reset")
    assert s["slide"] == 0 and not s["started"]


def test_every_command_changes_revision(db, owner):
    revs = [service.control_present(db, owner, a)["rev"]
            for a in ("start", "next", "prev", "pause")]
    assert revs == sorted(set(revs))


def test_unknown_command(db, owner):
    with pytest.raises(service.ValidationError):
        service.control_present(db, owner, "explode")


def test_slides_file_matches_timer():
    # Слайдов столько же, сколько знает сервер; доклад укладывается в 8 мин.
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "present", "slides.json")
    with open(path, encoding="utf-8") as fh:
        deck = json.load(fh)
    assert len(deck["slides"]) == service.PRESENT_SLIDES
    assert sum(s["time"] for s in deck["slides"]) == deck["talk"] == 480
    assert deck["total"] == 600
    assert all(s["who"] in deck["people"] and s["notes"] for s in
               deck["slides"])
