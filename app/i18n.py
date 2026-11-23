"""Переводы интерфейса: русский (ru), казахский (kk), кыргызский (ky),
английский (en).

Основной язык проекта — русский. Словари лежат в ``static/i18n/<язык>.json``:
браузер загружает их напрямую (они кэшируются), а для API и для будущих
настольной и мобильной версий они доступны через ``GET /api/i18n/{lang}``.
Если в словаре нет ключа, используется русский вариант.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

SUPPORTED = ("ru", "kk", "ky", "en")
DEFAULT = "ru"
_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "static", "i18n")


@lru_cache(maxsize=len(SUPPORTED))
def _load(lang: str) -> dict[str, str]:
    with open(os.path.join(_DIR, f"{lang}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def get(lang: str) -> dict[str, str]:
    """Словарь переводов языка, дополненный русскими строками."""
    if lang not in SUPPORTED:
        lang = DEFAULT
    if lang == DEFAULT:
        return _load(DEFAULT)
    return {**_load(DEFAULT), **_load(lang)}


def missing_keys(lang: str) -> set[str]:
    """Ключи, которые есть в русском словаре, но не переведены."""
    return set(_load(DEFAULT)) - set(_load(lang))
