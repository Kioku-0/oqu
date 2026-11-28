"""Тесты «живых книг»: трейлеры, манга, переводы поверх страниц, ИИ.

ИИ (Claude) в тестах не вызывается: проверяем, что без ключа функции
честно сообщают «ИИ не настроен», и разбор ответа модели.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import ai, seed, service
from app.db import connect

SCENES = [{"scene": "rider", "text": "Буран в степи."},
          {"scene": "castle", "text": "Крепость на краю империи."},
          {"scene": "duel", "text": "Дуэль из-за девушки."}]


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
def author(db):
    return _user(db, "author1", "author")


@pytest.fixture()
def book(db, author):
    return service.add_book(db, "author", "Книга", "Автор", content="текст",
                            added_by=author["id"])


@pytest.fixture()
def manga(db, author):
    return service.add_book(db, "author", "Манга", "Автор", kind="manga",
                            added_by=author["id"])


# --- Трейлеры ----------------------------------------------------------------
def test_author_saves_and_reads_trailer(db, author, book):
    service.set_trailer(db, author, book, SCENES)
    data = service.get_trailer(db, book)
    assert data["source"] == "author" and len(data["scenes"]) == 3
    assert service.get_book_details(db, book)["has_trailer"] == 1


def test_other_author_cannot_edit_trailer(db, book):
    stranger = _user(db, "author2", "author")
    with pytest.raises(service.PermissionDeniedError):
        service.set_trailer(db, stranger, book, SCENES)


@pytest.mark.parametrize("scenes", [
    SCENES[:2],                                           # меньше 3 сцен
    SCENES * 3,                                           # больше 8
    [*SCENES[:2], {"scene": "ufo", "text": "Т"}],         # нет такой сцены
    [*SCENES[:2], {"scene": "ship", "text": "   "}],      # пустая подпись
    [*SCENES[:2], {"scene": "ship", "text": "x" * 161}],  # длинная подпись
    "не список",
])
def test_trailer_validation(db, author, book, scenes):
    with pytest.raises(service.ValidationError):
        service.set_trailer(db, author, book, scenes)


def test_trailer_text_is_censored(db, author, book):
    bad = [*SCENES[:2], {"scene": "ship", "text": "Капитан блять"}]
    service.set_trailer(db, author, book, bad)
    assert "блять" not in service.get_trailer(db, book)["scenes"][2]["text"]


def test_delete_trailer_and_feed(db, author, book):
    assert service.trailer_feed(db)["total"] == 0
    service.set_trailer(db, author, book, SCENES)
    feed = service.trailer_feed(db)
    assert feed["total"] == 1 and feed["items"][0]["trailer"]["scenes"]
    service.delete_trailer(db, author, book)
    with pytest.raises(service.NotFoundError):
        service.get_trailer(db, book)


# --- Манга -------------------------------------------------------------------
def test_kind_is_validated(db):
    with pytest.raises(service.ValidationError):
        service.add_book(db, "editor", "Т", "А", kind="comics")
    assert service.get_book_details(db, service.add_book(
        db, "editor", "Т", "А"))["kind"] == "book"


def test_pages_only_for_manga(db, author, book):
    with pytest.raises(service.ValidationError):
        service.add_manga_page(db, author, book, "a.png", 800, 1200)


def test_pages_are_numbered_and_renumbered(db, author, manga):
    ids = [service.add_manga_page(db, author, manga, f"{i}.png", 800, 1200)
           for i in range(4)]
    service.delete_manga_page(db, author, ids[1])
    pages = service.list_manga_pages(db, manga)
    assert [p["idx"] for p in pages] == [1, 2, 3]
    assert [p["file_name"] for p in pages] == ["0.png", "2.png", "3.png"]
    assert service.get_book_details(db, manga)["pages"] == 3


def test_page_needs_size_and_rights(db, author, manga):
    with pytest.raises(service.ValidationError):
        service.add_manga_page(db, author, manga, "a.png", 0, 100)
    reader = _user(db, "reader1", "user")
    with pytest.raises(service.PermissionDeniedError):
        service.add_manga_page(db, reader, manga, "a.png", 10, 10)


def test_translation_boxes_are_clipped(db, author, manga):
    pid = service.add_manga_page(db, author, manga, "a.png", 800, 1200)
    boxes = service.set_page_translation(db, pid, "ru", [
        {"x": -5, "y": 95, "w": 30, "h": 20, "text": "Привет", "src": "やあ"},
        {"x": 10, "y": 10, "w": 10, "h": 10, "text": "   "},       # пустая
    ])
    assert boxes == [{"x": 0.0, "y": 95.0, "w": 30.0, "h": 5.0,
                      "text": "Привет", "shape": "rect", "src": "やあ"}]
    assert service.list_manga_pages(db, manga)[0]["langs"] == ["ru"]
    assert service.book_translations(db, manga, "ru") == {pid: boxes}
    assert service.get_page_translation(db, pid, "en") is None


@pytest.mark.parametrize("bad", ["не список", [{"x": 1}], [{"x": "a", "y": 1,
                                                         "w": 1, "h": 1}]])
def test_translation_validation(db, author, manga, bad):
    pid = service.add_manga_page(db, author, manga, "a.png", 800, 1200)
    with pytest.raises(service.ValidationError):
        service.set_page_translation(db, pid, "ru", bad)
    with pytest.raises(service.ValidationError):
        service.set_page_translation(db, pid, "de", [])


def test_demo_media_added_once(db, tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "DB_PATH", str(tmp_path / "x.sqlite"))
    editor = _user(db, "editor1", "editor")
    service.add_book(db, "editor", "Капитанская дочка", "Пушкин")
    first = seed.add_demo_media(db, editor)
    assert first["manga"] == 1 and first["trailers"] == 1
    manga_id = db.execute("SELECT id FROM books WHERE kind = 'manga'"
                          ).fetchone()[0]
    pages = service.list_manga_pages(db, manga_id)
    assert len(pages) == 4 and all(p["langs"] == ["en", "kk", "ru"]
                                   for p in pages)
    assert len(os.listdir(tmp_path / "uploads" / "images")) == 4
    assert seed.DEMO_TAG in service.book_tags(db, manga_id)
    assert seed.add_demo_media(db, editor) == {"trailers": 0, "manga": 0,
                                               "tagged": 0}


# --- ИИ без ключа и разбор ответа --------------------------------------------
def test_ai_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai.is_configured() is False
    with pytest.raises(service.AIUnavailableError):
        ai.generate_trailer({"title": "Т", "author": "А"}, "")
    with pytest.raises(service.AIUnavailableError):
        ai.translate_page(b"x", "image/png", "ru")


def test_ai_rejects_unknown_language():
    with pytest.raises(service.ValidationError):
        ai.translate_page(b"x", "image/png", "de")


def test_ai_json_parsing():
    assert ai._json('```json\n{"boxes": []}\n```') == {"boxes": []}
    assert ai._json('Вот: {"scenes": [1]} готово') == {"scenes": [1]}
    with pytest.raises(service.AIUnavailableError):
        ai._json("без json")


def test_image_size_parser():
    from app.web import _image_size
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
           + (900).to_bytes(4, "big") + (1350).to_bytes(4, "big"))
    assert _image_size(png) == (900, 1350)
    jpeg = (b"\xff\xd8\xff\xe0\x00\x10" + b"\x00" * 14
            + b"\xff\xc0\x00\x11\x08" + (600).to_bytes(2, "big")
            + (400).to_bytes(2, "big") + b"\x03")
    assert _image_size(jpeg) == (400, 600)
    assert _image_size(b"nothing") == (0, 0)
