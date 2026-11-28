"""Очистка SVG-рисунков, которые нарисовал ИИ (сцены трейлеров).

ИИ присылает код картинки. Чужой код нельзя вставлять в страницу как есть:
в SVG бывают скрипты, ссылки на чужие сайты, вставки HTML. Поэтому:

1. рисунок разбирается как XML — сломанный отвергается;
2. остаются только «рисующие» элементы из белого списка (фигуры,
   градиенты, анимации); script, foreignObject, image, a и т. п. удаляются;
3. удаляются обработчики событий (on…), ссылки не на «#id», url() и
   @import на внешние адреса;
4. ограничен размер.

Вторая линия защиты — в интерфейсе: рисунок показывается через
``<img src="data:image/svg+xml,…">``. В таком режиме браузер вообще не
выполняет скрипты и не применяет стили картинки к сайту, а анимации
(CSS и SMIL) работают.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_SVG_CHARS = 16_000

ALLOWED_TAGS = {
    "svg", "g", "defs", "title", "desc", "style", "use", "symbol",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask",
    "pattern", "animate", "animateTransform", "animateMotion", "set",
    "mpath", "filter", "feGaussianBlur", "feOffset", "feMerge",
    "feMergeNode", "feFlood", "feComposite", "feColorMatrix", "feBlend",
    "feTurbulence", "feDisplacementMap",
}
_BAD_CSS = re.compile(r"@import|expression\s*\(|javascript:|behavior\s*:"
                      r"|-moz-binding", re.I)
_URL = re.compile(r"url\(\s*(['\"]?)([^)'\"]*)\1\s*\)", re.I)

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _safe_css(text: str) -> Optional[str]:
    """CSS без импорта и внешних url() (разрешены только url(#id))."""
    if _BAD_CSS.search(text):
        return None
    if any(not m.group(2).startswith("#") for m in _URL.finditer(text)):
        return None
    return text


def _clean(el: ET.Element) -> None:
    for child in list(el):
        if not isinstance(child.tag, str) or \
                _local(child.tag) not in ALLOWED_TAGS:
            el.remove(child)
            continue
        _clean(child)
    for attr in list(el.attrib):
        name, value = _local(attr).lower(), el.attrib[attr]
        low = value.strip().lower()
        if name.startswith("on") or "javascript:" in low or \
                "data:" in low:
            del el.attrib[attr]
        elif name == "href" and not value.startswith("#"):
            del el.attrib[attr]
        elif name == "style" and _safe_css(value) is None:
            del el.attrib[attr]
        elif "url(" in low and _safe_css(value) is None:
            del el.attrib[attr]
    if _local(el.tag) == "style":
        css = _safe_css(el.text or "")
        el.text = css or ""


def sanitize_svg(raw: object) -> Optional[str]:
    """Вернуть безопасный SVG-код или ``None``, если рисунок негоден."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    # Модель иногда оборачивает код в ```svg … ```.
    raw = re.sub(r"^```(?:svg|xml)?\s*|\s*```$", "", raw)
    start = raw.find("<svg")
    if start < 0 or len(raw) > MAX_SVG_CHARS * 2:
        return None
    raw = raw[start:]
    if "<!DOCTYPE" in raw or "<!ENTITY" in raw:
        return None               # защита от XML-бомб и внешних сущностей
    if "xmlns=" not in raw[:300]:
        raw = raw.replace("<svg", f'<svg xmlns="{SVG_NS}"', 1)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    if _local(root.tag) != "svg":
        return None
    _clean(root)
    # Рисунок без единой фигуры — пустой, такой не нужен.
    if not any(_local(e.tag) in {"path", "rect", "circle", "ellipse",
                                 "polygon", "polyline", "line", "use"}
               for e in root.iter()):
        return None
    root.set("viewBox", root.get("viewBox") or "0 0 320 200")
    root.set("preserveAspectRatio", "xMidYMid slice")
    for size in ("width", "height"):
        root.attrib.pop(size, None)
    text = ET.tostring(root, encoding="unicode")
    return text if len(text) <= MAX_SVG_CHARS else None
