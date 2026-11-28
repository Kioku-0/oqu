"""ИИ-функции «Оқу»: трейлеры книг и перевод манги.

* :func:`generate_trailer` — сценарий трейлера книги: 5–6 сцен из готового
  каталога анимаций и интригующие подписи без спойлеров концовки;
* :func:`translate_page` — перевод страницы манги/комикса с любого языка:
  модель находит на картинке реплики (облачка, подписи, звуки) и возвращает
  их рамки и перевод; сайт рисует перевод поверх картинки.

Провайдеры (выбираются по тому, какой ключ задан в окружении):

1. **Google Gemini — бесплатный тариф** (``GEMINI_API_KEY``, ключ бесплатно
   выдаёт Google AI Studio, банковская карта не нужна). Основной вариант:
   запросы идут через стандартный ``urllib``, лишних пакетов не нужно.
   Модель — ``OQU_GEMINI_MODEL``, по умолчанию облегчённая Flash-Lite:
   у неё самый большой бесплатный дневной лимит.
2. **Claude (Anthropic)** — платный, запасной вариант
   (``ANTHROPIC_API_KEY`` + пакет ``anthropic``).

Ключей в коде нет. Если ни одного ключа нет, функции выбрасывают
:class:`app.service.AIUnavailableError` — сайт работает дальше, а готовые
(демо и ранее сделанные) трейлеры и переводы показываются как обычно.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from app import service

GEMINI_MODEL = os.environ.get("OQU_GEMINI_MODEL", "gemini-flash-lite-latest")
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent")
CLAUDE_MODEL = os.environ.get("OQU_AI_MODEL", "claude-opus-5-5")
LANG_NAMES = {"ru": "Russian", "kk": "Kazakh", "ky": "Kyrgyz",
              "en": "English"}
# Самоназвание языка: без него облегчённые модели иногда переводят
# «на казахский» по-английски.
LANG_NATIVE = {"ru": "русский язык", "kk": "қазақ тілі (кириллица)",
               "ky": "кыргыз тили (кириллица)", "en": "English"}

# Часть «запроса»: текст или картинка — одинаково для всех провайдеров.
Part = tuple  # ("text", str) | ("image", bytes, media_type)


def provider() -> str:
    """Какой ИИ будет работать: ``gemini``, ``claude`` или ``""``."""
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return ""
        return "claude"
    return ""


def is_configured() -> bool:
    return bool(provider())


def model_name() -> str:
    return {"gemini": GEMINI_MODEL, "claude": CLAUDE_MODEL}.get(provider(),
                                                               "")


def _ask(parts: list[Part], system: str, max_tokens: int) -> str:
    """Один запрос к ИИ; возвращает текст ответа (в нём JSON)."""
    which = provider()
    if which == "gemini":
        return _ask_gemini(parts, system, max_tokens)
    if which == "claude":
        return _ask_claude(parts, system, max_tokens)
    raise service.AIUnavailableError(
        "ИИ не настроен: на сервере не задан GEMINI_API_KEY "
        "(бесплатный ключ Google AI Studio)")


# --- Google Gemini (бесплатный тариф) ----------------------------------------
def _ask_gemini(parts: list[Part], system: str, max_tokens: int) -> str:
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [
            {"text": p[1]} if p[0] == "text" else
            {"inline_data": {"mime_type": p[2], "data": base64.b64encode(
                p[1]).decode("ascii")}} for p in parts]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "maxOutputTokens": max_tokens,
                             "temperature": 0.5},
    }
    request = urllib.request.Request(
        GEMINI_URL.format(model=GEMINI_MODEL),
        data=json.dumps(body).encode("utf-8"), method="POST",
        # Ключ — в заголовке, а не в адресе: адреса попадают в логи.
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise service.AIUnavailableError(
                "Бесплатный лимит ИИ на сегодня исчерпан, попробуйте "
                "завтра или через минуту") from None
        raise service.AIUnavailableError(
            f"ИИ временно недоступен (код {exc.code})") from None
    except (urllib.error.URLError, TimeoutError):
        raise service.AIUnavailableError("Нет связи с сервисом ИИ") from None
    candidates = data.get("candidates") or []
    if not candidates:
        raise service.AIUnavailableError("ИИ отказался обработать запрос")
    content = candidates[0].get("content") or {}
    return "".join(p.get("text", "") for p in content.get("parts", []))


# --- Claude (платный, запасной) ----------------------------------------------
def _ask_claude(parts: list[Part], system: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(timeout=120.0, max_retries=2)
    content = [{"type": "text", "text": p[1]} if p[0] == "text" else
               {"type": "image", "source": {
                   "type": "base64", "media_type": p[2],
                   "data": base64.standard_b64encode(p[1]).decode("ascii")}}
               for p in parts]
    try:
        # fallbacks="default": если основная модель откажет по правилам
        # безопасности, сервер Anthropic сам повторит запрос на запасной.
        response = client.beta.messages.create(
            model=CLAUDE_MODEL, max_tokens=max_tokens, system=system,
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
    data = _json(_ask([("text", prompt)], TRAILER_SYSTEM, 4000))
    scenes = data.get("scenes") if isinstance(data, dict) else data
    if isinstance(scenes, list):
        # Модель могла написать подпись чуть длиннее лимита — подрежем.
        scenes = [{**s, "text": str(s.get("text", ""))[
            :service.MAX_SCENE_TEXT]} if isinstance(s, dict) else s
            for s in scenes[:service.MAX_TRAILER_SCENES]]
    return service.clean_trailer(scenes)


# --- Перевод страницы манги -----------------------------------------------
TRANSLATE_SYSTEM = (
    "You are a professional manga and comics translator and letterer. You "
    "find every piece of text on a page (speech balloons, thought bubbles, "
    "captions, signs, sound effects) and translate it naturally, keeping "
    "the tone of each character. Reply with JSON only.")


def _box_from_gemini(b: dict) -> dict | None:
    """Gemini отдаёт рамку как box_2d = [ymin, xmin, ymax, xmax] в долях
    0–1000 — переводим в проценты x, y, w, h. Модель называет поле
    по-разному (box_2d, bbox, box), принимаем любое; без рамки — None."""
    raw = next((b[k] for k in ("box_2d", "bbox", "box", "bounding_box")
                if k in b), None)
    try:
        y0, x0, y1, x1 = (float(v) / 10 for v in raw)
    except (TypeError, ValueError):
        return None
    return {**b, "x": min(x0, x1), "y": min(y0, y1), "w": abs(x1 - x0),
            "h": abs(y1 - y0)}


def _normalize_box(b: dict, gemini: bool) -> dict | None:
    """Привести ответ модели к виду ``{x, y, w, h, shape, src, text}``."""
    if not isinstance(b, dict):
        return None
    if gemini:
        b = _box_from_gemini(b)
        if b is None:
            return None
    text = b.get("translation", b.get("text", ""))
    src = b.get("original", b.get("src", ""))
    if not all(isinstance(b.get(k), (int, float)) for k in "xywh"):
        return None          # рамку без координат пропускаем, а не падаем
    return {**b, "text": text, "src": src}


def translate_page(image: bytes, media_type: str, lang: str) -> list[dict]:
    """Найти реплики на странице и перевести их на язык ``lang``.

    Возвращает рамки ``{"x", "y", "w", "h", "shape", "src", "text"}``:
    координаты левого верхнего угла, ширина и высота в процентах.
    """
    if lang not in LANG_NAMES:
        raise service.ValidationError("Перевод возможен на ru, kk, ky, en")
    gemini = provider() == "gemini"
    box_format = (
        'give its bounding box as "box_2d": [ymin, xmin, ymax, xmax] '
        "normalized to 0-1000" if gemini else
        "give its bounding box as percentages of the image width and height "
        "(x and y of the top-left corner, w, h)")
    example = ('"box_2d": [0, 0, 0, 0]' if gemini
               else '"x": 0, "y": 0, "w": 0, "h": 0')
    target = f"{LANG_NAMES[lang]} ({LANG_NATIVE[lang]})"
    prompt = (
        f"TARGET LANGUAGE: {target}.\n"
        f"Translate all text on this page into {target}. Every "
        f'"translation" value MUST be written in {LANG_NAMES[lang]}'
        + ("" if lang == "en" else ", not in English") + ". "
        f"For each text region {box_format}, covering the whole balloon "
        "interior so the translation can be drawn over the original. Use "
        'shape "oval" for round speech balloons and "rect" for captions, '
        "signs and sound effects. Keep reading order. Return exactly: "
        f'{{"boxes": [{{{example}, "shape": "oval", '
        '"original": "<original text>", '
        f'"translation": "<text in {LANG_NAMES[lang]}>"}}]}}')
    data = _json(_ask([("image", image, media_type), ("text", prompt)],
                      TRANSLATE_SYSTEM, 8000))
    boxes = data.get("boxes") if isinstance(data, dict) else data
    if not isinstance(boxes, list):
        raise service.AIUnavailableError("ИИ вернул ответ не в том формате")
    clean = [b for b in (_normalize_box(x, gemini) for x in boxes) if b]
    if boxes and not clean:
        raise service.AIUnavailableError(
            "ИИ не смог разметить реплики, попробуйте ещё раз")
    return service.clean_boxes(clean)
