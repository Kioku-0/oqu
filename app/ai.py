"""ИИ-функции «Оқу» на Claude API (Anthropic).

* :func:`generate_trailer` — сценарий трейлера книги: 5–6 сцен из готового
  каталога анимаций и интригующие подписи без спойлеров концовки;
* :func:`translate_page` — перевод страницы манги/комикса с любого языка:
  модель находит на картинке реплики (облачка, подписи, звуки) и возвращает
  их рамки в процентах и перевод; сайт рисует перевод поверх картинки.

Ключ берётся из переменной окружения ``ANTHROPIC_API_KEY`` (в коде его нет).
Если ключа или пакета ``anthropic`` нет, функции выбрасывают
:class:`app.service.AIUnavailableError` — сайт работает дальше, а готовые
(демо и ранее сделанные) трейлеры и переводы показываются как обычно.
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

from app import service

MODEL = os.environ.get("OQU_AI_MODEL", "claude-opus-5-5")
LANG_NAMES = {"ru": "Russian", "kk": "Kazakh", "ky": "Kyrgyz",
              "en": "English"}


def is_configured() -> bool:
    """Есть ли ключ API и установлен ли пакет ``anthropic``."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise service.AIUnavailableError(
            "ИИ не настроен: на сервере не задан ANTHROPIC_API_KEY")
    try:
        import anthropic
    except ImportError:
        raise service.AIUnavailableError(
            "ИИ не настроен: не установлен пакет anthropic") from None
    return anthropic, anthropic.Anthropic(timeout=120.0, max_retries=2)


def _ask(content: list[dict[str, Any]], system: str,
         max_tokens: int) -> str:
    """Один запрос к Claude; возвращает текст ответа."""
    anthropic, client = _client()
    try:
        # fallbacks="default": если основная модель откажет по правилам
        # безопасности, сервер Anthropic сам повторит запрос на запасной.
        response = client.beta.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": content}])
    except anthropic.RateLimitError:
        raise service.AIUnavailableError(
            "ИИ перегружен, попробуйте через минуту") from None
    except anthropic.APIStatusError as exc:
        raise service.AIUnavailableError(
            f"ИИ временно недоступен (код {exc.status_code})") from None
    except anthropic.APIConnectionError:
        raise service.AIUnavailableError(
            "Нет связи с сервисом ИИ") from None
    if response.stop_reason == "refusal":
        raise service.AIUnavailableError("ИИ отказался обработать запрос")
    return "".join(b.text for b in response.content if b.type == "text")


def _json(text: str) -> Any:
    """Достать JSON из ответа (модель иногда оборачивает его в ```)."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0],
                default=-1)
    if start < 0:
        raise service.AIUnavailableError("ИИ вернул ответ не в том формате")
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except json.JSONDecodeError:
        raise service.AIUnavailableError(
            "ИИ вернул ответ не в том формате") from None


# --- Трейлер книги -----------------------------------------------------------
SCENE_HINTS = {
    "rider": "a horseman galloping across the steppe",
    "ship": "a ship on a rolling sea",
    "city": "a city street at night with lit windows",
    "castle": "a castle or palace on a hill",
    "forest": "a dark forest with fireflies",
    "yurt": "a yurt in the steppe with an eagle above",
    "train": "a steam train in motion",
    "letter": "a letter and a candle on a desk (secrets, love, news)",
    "duel": "two figures facing each other (conflict, duel, argument)",
    "ball": "a ballroom with dancing couples (society, love)",
    "robot": "a robot (technology, the future)",
    "rabbit": "a white rabbit with a pocket watch (fairy tale, wonder)",
    "storm": "a storm with lightning (danger, turning point)",
    "road": "a lonely traveller on a road (journey, choice)",
    "books": "a stack of books and a lamp (knowledge, study)",
    "space": "stars and a planet (dreams, space, philosophy)",
}

TRAILER_SYSTEM = (
    "You write short animated 'book trailers' for an e-library used by "
    "school and university students in Kazakhstan. A trailer is a sequence "
    "of pages; each page shows one ready-made animated scene and a caption. "
    "Captions must make a teenager want to open the book: concrete, vivid, "
    "a question or a hook, no clichés, and never reveal the ending. "
    "Reply with JSON only.")


def generate_trailer(book: dict[str, Any], sample: str) -> list[dict]:
    """Сценарий трейлера: список ``{"scene", "text"}`` (5–6 сцен)."""
    lang = LANG_NAMES.get(book.get("language", "ru"), "Russian")
    catalog = "\n".join(f"- {k}: {v}" for k, v in SCENE_HINTS.items())
    prompt = (
        f"Book: «{book['title']}» by {book['author']}.\n"
        f"Description: {book.get('description') or '-'}\n"
        f"Opening of the text (may be empty):\n{sample[:6000]}\n\n"
        f"Available scenes (use only these ids):\n{catalog}\n\n"
        f"Write a trailer of 5 or 6 pages in {lang}. Each caption is at most "
        f"{service.MAX_SCENE_TEXT} characters. The last page invites the "
        "reader to open the book. Return exactly: "
        '{"scenes": [{"scene": "<id>", "text": "<caption>"}]}')
    data = _json(_ask([{"type": "text", "text": prompt}], TRAILER_SYSTEM,
                      4000))
    scenes = data.get("scenes") if isinstance(data, dict) else data
    return service.clean_trailer(scenes)


# --- Перевод страницы манги -----------------------------------------------
TRANSLATE_SYSTEM = (
    "You are a professional manga and comics translator and letterer. You "
    "find every piece of text on a page (speech balloons, thought bubbles, "
    "captions, signs, sound effects) and translate it naturally, keeping "
    "the tone of each character. Reply with JSON only.")


def translate_page(image: bytes, media_type: str, lang: str) -> list[dict]:
    """Найти реплики на странице и перевести их на язык ``lang``.

    Возвращает рамки ``{"x", "y", "w", "h", "src", "text"}``: координаты
    левого верхнего угла, ширина и высота в процентах от картинки.
    """
    if lang not in LANG_NAMES:
        raise service.ValidationError("Перевод возможен на ru, kk, ky, en")
    prompt = (
        f"Translate all text on this page into {LANG_NAMES[lang]}. For each "
        "text region give its bounding box as percentages of the image "
        "width and height (x and y of the top-left corner, w, h), covering "
        "the whole balloon interior so the translation can be drawn over "
        "the original. Use shape \"oval\" for round speech balloons and "
        "\"rect\" for captions, signs and sound effects. Keep reading order. "
        'Return exactly: {"boxes": [{"x": 0, "y": 0, "w": 0, "h": 0, '
        '"shape": "oval", "src": "<original text>", '
        '"text": "<translation>"}]}')
    content = [
        {"type": "image", "source": {
            "type": "base64", "media_type": media_type,
            "data": base64.standard_b64encode(image).decode("ascii")}},
        {"type": "text", "text": prompt},
    ]
    data = _json(_ask(content, TRANSLATE_SYSTEM, 8000))
    boxes = data.get("boxes") if isinstance(data, dict) else data
    return service.clean_boxes(boxes or [])
