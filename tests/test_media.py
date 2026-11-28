"""Тесты «живых книг»: трейлеры, манга, переводы поверх страниц, ИИ.

ИИ (Claude) в тестах не вызывается: проверяем, что без ключа функции
честно сообщают «ИИ не настроен», и разбор ответа модели.
"""

import json
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


def test_manga_page_files_listed_for_deletion(db, author, manga):
    service.add_manga_page(db, author, manga, "p1.png", 800, 1200)
    service.add_manga_page(db, author, manga, "p2.png", 800, 1200)
    assert sorted(service.book_files(db, manga)) == ["p1.png", "p2.png"]


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
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert ai.is_configured() is False and ai.provider() == ""
    with pytest.raises(service.AIUnavailableError):
        ai.generate_trailer({"title": "Т", "author": "А"}, "")
    with pytest.raises(service.AIUnavailableError):
        ai.translate_page(b"x", "image/png", "ru")


class _FakeResponse:
    """Ответ «Gemini» без сети: тест не тратит бесплатный лимит."""

    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_gemini(monkeypatch, answer, seen):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def urlopen(request, timeout=0):
        seen.append(request)
        return _FakeResponse({"candidates": [{"content": {"parts": [
            {"text": json.dumps(answer, ensure_ascii=False)}]}}]})
    monkeypatch.setattr(ai.urllib.request, "urlopen", urlopen)


def test_gemini_translation_boxes(monkeypatch):
    seen = []
    _fake_gemini(monkeypatch, {"boxes": [
        {"box_2d": [100, 200, 300, 500], "shape": "oval",
         "src": "やあ", "text": "Привет"}]}, seen)
    assert ai.provider() == "gemini"
    boxes = ai.translate_page(b"\x89PNG", "image/png", "ru")
    assert boxes == [{"x": 20.0, "y": 10.0, "w": 30.0, "h": 20.0,
                      "text": "Привет", "shape": "oval", "src": "やあ"}]
    # Ключ передаётся заголовком, а не в адресе запроса.
    assert seen[0].get_header("X-goog-api-key") == "test-key"
    assert "key=" not in seen[0].full_url
    body = json.loads(seen[0].data)
    assert body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == \
        "image/png"


def test_gemini_answer_variants(monkeypatch):
    # Список вместо объекта, поле bbox вместо box_2d, original/translation
    # вместо src/text, рамка без координат — пропускается, а не роняет всё.
    seen = []
    _fake_gemini(monkeypatch, [
        {"bbox": [0, 0, 500, 500], "original": "やあ", "translation": "Сәлем"},
        {"shape": "oval", "translation": "без рамки"},
    ], seen)
    boxes = ai.translate_page(b"\x89PNG", "image/png", "kk")
    assert [(b["text"], b["src"], b["w"]) for b in boxes] == \
        [("Сәлем", "やあ", 50.0)]
    # Язык назван и по-английски, и самоназванием.
    prompt = json.loads(seen[0].data)["contents"][0]["parts"][1]["text"]
    assert "Kazakh" in prompt and "қазақ тілі" in prompt


BROKEN_GEMINI = """[
  {
    "box_2d": [
      78, 137, 252, 264],
      "shape": "oval",
      "original": "ね、猫が\\nしゃべった",
      "translation": "Мышык\\nсүйлөдү!?"
    }
  },
  {
    "box_2d": [484, 558, 600, 694], "shape": "rect",
      "original": "ごらん。", "translation": "Ачып көр."
    }
  }
]"""


def test_broken_gemini_json_is_salvaged():
    # Настоящий ответ Gemini Flash-Lite с лишними скобками «}».
    boxes = ai._json(BROKEN_GEMINI)["boxes"]
    assert [(b["translation"], b["shape"]) for b in boxes] == [
        ("Мышык\nсүйлөдү!?", "oval"), ("Ачып көр.", "rect")]
    assert boxes[0]["box_2d"] == [78.0, 137.0, 252.0, 264.0]


def test_gemini_gets_response_schema(monkeypatch):
    seen = []
    _fake_gemini(monkeypatch, {"boxes": []}, seen)
    ai.translate_page(b"x", "image/png", "ky")
    config = json.loads(seen[0].data)["generationConfig"]
    assert config["responseSchema"]["properties"]["boxes"]["type"] == "ARRAY"


def test_gemini_answer_without_any_box(monkeypatch):
    _fake_gemini(monkeypatch, {"boxes": [{"text": "нет рамки"}]}, [])
    with pytest.raises(service.AIUnavailableError):
        ai.translate_page(b"x", "image/png", "ru")


def test_gemini_trailer_is_cleaned(monkeypatch):
    long = "Очень длинная подпись " * 20
    _fake_gemini(monkeypatch, {"scenes": [
        {"scene": "rider", "text": long}, {"scene": "ship", "text": "Море"},
        {"scene": "storm", "text": "Буря"}]}, [])
    scenes = ai.generate_trailer({"title": "Т", "author": "А"}, "")
    assert len(scenes) == 3 and len(scenes[0]["text"]) <= 160


def test_gemini_quota_exhausted(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def urlopen(request, timeout=0):
        raise ai.urllib.error.HTTPError(request.full_url, 429, "quota", {},
                                        None)
    monkeypatch.setattr(ai.urllib.request, "urlopen", urlopen)
    with pytest.raises(service.AIUnavailableError, match="лимит"):
        ai.translate_page(b"x", "image/png", "kk")


# --- Рисунки ИИ: очистка SVG ------------------------------------------------
GOOD_SVG = ('<svg viewBox="0 0 320 200" width="900"><rect width="320" '
            'height="200" fill="#123"/><circle cx="50" cy="50" r="9">'
            '<animate attributeName="r" values="9;12;9" dur="2s" '
            'repeatCount="indefinite"/></circle></svg>')


def test_svg_keeps_drawing_and_animation():
    from app.svg_safe import sanitize_svg
    svg = sanitize_svg("```svg\n" + GOOD_SVG + "\n```")
    assert svg.startswith("<svg") and "<animate" in svg
    assert 'width="900"' not in svg and 'viewBox="0 0 320 200"' in svg


@pytest.mark.parametrize("evil", [
    '<script>alert(1)</script>',
    '<foreignObject><div>x</div></foreignObject>',
    '<image href="https://evil.example/a.png"/>',
    '<a href="javascript:alert(1)"><rect width="1" height="1"/></a>',
])
def test_svg_dangerous_parts_removed(evil):
    from app.svg_safe import sanitize_svg
    svg = sanitize_svg(GOOD_SVG.replace("</svg>", evil + "</svg>"))
    assert svg and "script" not in svg and "foreignObject" not in svg
    assert "evil.example" not in svg and "javascript" not in svg


def test_svg_dangerous_attributes_removed():
    from app.svg_safe import sanitize_svg
    svg = sanitize_svg(
        '<svg viewBox="0 0 10 10"><rect width="5" height="5" '
        'onclick="alert(1)" fill="url(https://evil.example/x)" '
        'style="background:url(https://evil.example)"/>'
        '<style>@import url(https://evil.example/a.css); rect{fill:red}'
        '</style><use href="https://evil.example/#a"/></svg>')
    assert "onclick" not in svg and "evil.example" not in svg


@pytest.mark.parametrize("bad", [
    None, 42, "просто текст", "<svg><rect", "<html></html>",
    '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg/>',
    '<svg viewBox="0 0 10 10"><g/></svg>',               # без фигур
    "<svg>" + "<rect width='1' height='1'/>" * 3000 + "</svg>",  # огромный
])
def test_svg_rejected(bad):
    from app.svg_safe import sanitize_svg
    assert sanitize_svg(bad) is None


def test_trailer_keeps_clean_ai_drawing(db, author, book):
    scenes = [{**SCENES[0], "svg": GOOD_SVG}, {**SCENES[1], "svg": "мусор"},
              SCENES[2]]
    saved = service.set_trailer(db, author, book, scenes)["scenes"]
    assert "svg" in saved[0] and "svg" not in saved[1]
    assert saved[0]["scene"] == "rider"        # запасная сцена остаётся


def test_draw_scenes_by_index(monkeypatch):
    _fake_gemini(monkeypatch, {"scenes": [
        {"index": 2, "svg": GOOD_SVG}, {"index": 1, "svg": "<svg>сломан"}]},
        [])
    drawings = ai.draw_scenes({"title": "Т", "author": "А"}, SCENES)
    assert drawings[0] is None and drawings[1].startswith("<svg")
    assert drawings[2] is None


def test_drawn_trailer_survives_failed_drawing(monkeypatch):
    calls = []

    def fake_ask(parts, system, max_tokens, schema=None, model=None):
        calls.append(model)
        if system == ai.DRAW_SYSTEM:
            raise service.AIUnavailableError("лимит")
        return json.dumps({"scenes": SCENES})
    monkeypatch.setattr(ai, "_ask", fake_ask)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    scenes = ai.generate_drawn_trailer({"title": "Т", "author": "А"}, "")
    assert len(scenes) == 3 and not any("svg" in s for s in scenes)


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
