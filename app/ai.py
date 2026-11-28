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
from typing import Any, Optional

from app import service, svg_safe

GEMINI_MODEL = os.environ.get("OQU_GEMINI_MODEL", "gemini-flash-lite-latest")
# Рисует сцены трейлеров модель посильнее (у неё меньше бесплатных запросов
# в день, но рисунок нужен один раз на книгу). Не вышло — берём основную.
GEMINI_DRAW_MODEL = os.environ.get("OQU_GEMINI_DRAW_MODEL",
                                   "gemini-flash-latest")
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


def _ask(parts: list[Part], system: str, max_tokens: int,
         schema: dict | None = None, model: str | None = None) -> str:
    """Один запрос к ИИ; возвращает текст ответа (в нём JSON).

    ``schema`` — схема ответа для Gemini (structured output): с ней модель
    не может прислать сломанный JSON. ``model`` — другая модель Gemini."""
    which = provider()
    if which == "gemini":
        return _ask_gemini(parts, system, max_tokens, schema, model)
    if which == "claude":
        return _ask_claude(parts, system, max_tokens)
    raise service.AIUnavailableError(
        "ИИ не настроен: на сервере не задан GEMINI_API_KEY "
        "(бесплатный ключ Google AI Studio)")


# --- Google Gemini (бесплатный тариф) ----------------------------------------
def _ask_gemini(parts: list[Part], system: str, max_tokens: int,
                schema: dict | None = None,
                model: str | None = None) -> str:
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
    if schema:
        body["generationConfig"]["responseSchema"] = schema
    request = urllib.request.Request(
        GEMINI_URL.format(model=model or GEMINI_MODEL),
        data=json.dumps(body).encode("utf-8"), method="POST",
        # Ключ — в заголовке, а не в адресе: адреса попадают в логи.
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    try:
        # Рисование (большой ответ) идёт минуты; оно работает в фоне.
        wait = 300 if max_tokens > 20000 else 90
        with urllib.request.urlopen(request, timeout=wait) as response:
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
            # Без стриминга SDK не разрешает очень большой max_tokens.
            model=CLAUDE_MODEL, max_tokens=min(max_tokens, 16000),
            system=system,
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
        salvaged = _salvage_boxes(text)
        if salvaged:
            return {"boxes": salvaged}
        raise service.AIUnavailableError(
            "ИИ вернул ответ не в том формате") from None


_STR = r'"((?:[^"\\]|\\.)*)"'
_BOX_RE = re.compile(
    r'"(?:box_2d|bbox|box)"\s*:\s*\[([^\]]*)\]'
    r'(?:(?!"(?:box_2d|bbox|box)")[\s\S])*?"original"\s*:\s*' + _STR +
    r'(?:(?!"(?:box_2d|bbox|box)")[\s\S])*?"translation"\s*:\s*' + _STR)
_SHAPE_RE = re.compile(r'"shape"\s*:\s*"(oval|rect)"')


def _salvage_boxes(text: str) -> list[dict]:
    """Запасной разбор, если модель прислала сломанный JSON (лишняя
    скобка и т. п.): вытаскиваем рамки и реплики регулярным выражением."""
    result = []
    for m in _BOX_RE.finditer(text):
        try:
            coords = [float(v) for v in m.group(1).split(",")]
            original = json.loads(f'"{m.group(2)}"')
            translation = json.loads(f'"{m.group(3)}"')
        except ValueError:
            continue
        shape = _SHAPE_RE.search(m.group(0))
        result.append({"box_2d": coords, "original": original,
                       "translation": translation,
                       "shape": shape.group(1) if shape else "rect"})
    return result


# Схемы ответов для Gemini (structured output, формат OpenAPI).
_BOXES_SCHEMA = {
    "type": "OBJECT", "required": ["boxes"],
    "properties": {"boxes": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "required": ["box_2d", "shape", "original", "translation"],
        "properties": {
            "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            "shape": {"type": "STRING", "enum": ["oval", "rect"]},
            "original": {"type": "STRING"},
            "translation": {"type": "STRING"}}}}}}


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
    schema = {"type": "OBJECT", "required": ["scenes"], "properties": {
        "scenes": {"type": "ARRAY", "items": {
            "type": "OBJECT", "required": ["scene", "text"],
            "properties": {
                "scene": {"type": "STRING", "enum": list(SCENE_HINTS)},
                "text": {"type": "STRING"}}}}}}
    data = _json(_ask([("text", prompt)], TRAILER_SYSTEM, 4000, schema))
    scenes = data.get("scenes") if isinstance(data, dict) else data
    if isinstance(scenes, list):
        # Модель могла написать подпись чуть длиннее лимита — подрежем.
        scenes = [{**s, "text": str(s.get("text", ""))[
            :service.MAX_SCENE_TEXT]} if isinstance(s, dict) else s
            for s in scenes[:service.MAX_TRAILER_SCENES]]
    return service.clean_trailer(scenes)


# --- ИИ рисует сцены трейлера (анимированный SVG) --------------------------
DRAW_SYSTEM = (
    "You are an illustrator and motion designer who draws with SVG code. "
    "You make small looping animated illustrations for book trailers seen "
    "by teenagers: flat vector style, bold readable shapes, a clear focal "
    "subject, a mood that matches the caption, rich but harmonious colors. "
    "Reply with JSON only.")

DRAW_RULES = (
    "Quality bar: like a polished flat-design illustration from a "
    "children's encyclopedia, not a doodle. First plan the picture in the "
    '"plan" field (setting, main subject, colors, what moves), then draw.\n'
    "Rules for every SVG:\n"
    '- root: <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200">'
    ";\n"
    "- layered depth: a sky or wall with a <linearGradient>, a far layer "
    "(mountains, city skyline, horizon), a middle layer, a foreground "
    "(ground, grass, floor, waves);\n"
    "- the main subject from the caption is large (about a third of the "
    "frame), built from 8 or more shapes so it is clearly recognisable: "
    "a horse has a head, ears, mane, four legs and a tail and a rider sits "
    "on it; a person has a head, hair, body, arms, legs and clothes; a "
    "ship has a hull, masts and sails; a fortress has walls, towers and a "
    "gate. Use <path> curves, not only circles and rectangles;\n"
    "- light and shade: a darker shade on one side of objects, a glow "
    "for lamps, fire, the moon or the sun;\n"
    "- 2 to 4 smooth looping animations made with <animate>, "
    "<animateTransform> or CSS @keyframes in a <style> element (the horse "
    "gallops, snow falls, waves roll, a flag waves, a candle flickers, "
    "stars twinkle), dur 1-6s, infinite;\n"
    "- the audience is schoolchildren: show danger and drama through "
    "weather, light, distance and posture, NEVER through violence: no "
    "blood, wounds, corpses, skulls, gallows, nooses, executions, "
    "weapons pointed at a person, no frightening faces; swords may only "
    "be held up or crossed;\n"
    "- NO text or letters, NO <script>, NO <image>, NO <foreignObject>, "
    "NO external links or fonts;\n"
    "- 2500 to 6000 characters per SVG.")


def draw_scenes(book: dict[str, Any],
                scenes: list[dict]) -> list[Optional[str]]:
    """Нарисовать анимированный SVG для каждой сцены трейлера.

    Возвращает список той же длины: очищенный SVG или ``None`` (тогда
    останется сцена из каталога). Один запрос к ИИ на весь трейлер."""
    captions = "\n".join(f"{i + 1}. {s['text']}"
                         for i, s in enumerate(scenes))
    prompt = (
        f"Book: «{book['title']}» by {book['author']}.\n"
        f"Description: {book.get('description') or '-'}\n\n"
        f"Trailer pages (captions):\n{captions}\n\n"
        "Draw one animated SVG illustration for each page, in the same "
        f"order ({len(scenes)} in total). Each picture must show what its "
        "caption is about, in the setting of this book.\n\n"
        f"{DRAW_RULES}\n\n"
        'Return exactly: {"scenes": [{"index": 1, "plan": "<composition>", '
        '"svg": "<svg ...>"}]}')
    # «plan» перед «svg»: модель сначала продумывает композицию, а потом
    # рисует — так рисунки заметно лучше. Сам план нигде не сохраняется.
    schema = {"type": "OBJECT", "required": ["scenes"], "properties": {
        "scenes": {"type": "ARRAY", "items": {
            "type": "OBJECT", "required": ["index", "plan", "svg"],
            "propertyOrdering": ["index", "plan", "svg"],
            "properties": {"index": {"type": "INTEGER"},
                           "plan": {"type": "STRING"},
                           "svg": {"type": "STRING"}}}}}}
    parts = [("text", prompt)]
    try:
        raw = _ask(parts, DRAW_SYSTEM, 60000, schema, GEMINI_DRAW_MODEL)
    except service.AIUnavailableError:
        if provider() != "gemini" or GEMINI_DRAW_MODEL == GEMINI_MODEL:
            raise
        raw = _ask(parts, DRAW_SYSTEM, 60000, schema)   # запасная модель
    data = _json(raw)
    items = data.get("scenes") if isinstance(data, dict) else data
    result: list[Optional[str]] = [None] * len(scenes)
    for k, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("index", k + 1)) - 1
        except (TypeError, ValueError):
            i = k
        if 0 <= i < len(scenes):
            result[i] = svg_safe.sanitize_svg(item.get("svg"))
    return result


def generate_drawn_trailer(book: dict[str, Any], sample: str) -> list[dict]:
    """Полный трейлер от ИИ: сначала подписи, потом рисунки к ним.

    Если рисование не удалось (лимит, ошибка), трейлер всё равно
    получается — со сценами из каталога."""
    scenes = generate_trailer(book, sample)
    try:
        drawings = draw_scenes(book, scenes)
    except service.AIUnavailableError:
        return scenes
    return [{**s, "svg": svg} if svg else s
            for s, svg in zip(scenes, drawings)]


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
                      TRANSLATE_SYSTEM, 8000,
                      _BOXES_SCHEMA if gemini else None))
    boxes = data.get("boxes") if isinstance(data, dict) else data
    if not isinstance(boxes, list):
        raise service.AIUnavailableError("ИИ вернул ответ не в том формате")
    clean = [b for b in (_normalize_box(x, gemini) for x in boxes) if b]
    if boxes and not clean:
        raise service.AIUnavailableError(
            "ИИ не смог разметить реплики, попробуйте ещё раз")
    return service.clean_boxes(clean)
