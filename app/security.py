"""Модуль безопасности: хэширование паролей, JWT-токены, политики защиты.

Здесь собрана вся «криптографическая» часть проекта, отделённая от бизнес-логики:

* хэширование паролей алгоритмом **PBKDF2-HMAC-SHA256** (стандартная библиотека
  :mod:`hashlib`, внешние зависимости не требуются; пароль никогда не хранится
  в открытом виде — раздел 5.4 методички);
* выпуск и проверка **JWT**-токенов доступа и обновления (обязательная функция
  варианта 11 — «аутентификация JWT»);
* константы политики защиты от **подбора пароля (брутфорса)**.

SECRET_KEY берётся из переменной окружения и никогда не хранится в коде
в боевом режиме (значение по умолчанию ``"dev-only-change-me"`` допустимо
только для локальной разработки).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT

# --- Общие настройки ------------------------------------------------------
SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MIN = 30          # срок жизни токена доступа, минут
REFRESH_TOKEN_TTL_DAYS = 7         # срок жизни токена обновления, дней

# --- Политика защиты от брутфорса ----------------------------------------
MAX_FAILED_ATTEMPTS = 5            # после скольких неудач блокируем вход
LOCKOUT_MINUTES = 15              # на сколько минут блокируем

# --- Параметры PBKDF2 -----------------------------------------------------
_PBKDF2_ROUNDS = 240_000
_PBKDF2_HASH = "sha256"
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Вернуть безопасный хэш пароля в формате ``pbkdf2_sha256$rounds$salt$hash``.

    Соль генерируется случайно для каждого пароля, поэтому одинаковые пароли
    дают разные хэши. Сам пароль восстановить из хэша нельзя.
    """
    if not isinstance(password, str) or password == "":
        raise ValueError("Пароль не должен быть пустым")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH, password.encode("utf-8"), salt, _PBKDF2_ROUNDS
    )
    return f"pbkdf2_{_PBKDF2_HASH}${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Проверить пароль против сохранённого хэша.

    Сравнение выполняется функцией :func:`hmac.compare_digest`, устойчивой к
    атакам по времени (timing attack).
    """
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        rounds = int(rounds)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH, (password or "").encode("utf-8"), salt, rounds
    )
    return hmac.compare_digest(digest, expected)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, role: str) -> str:
    """Создать краткоживущий JWT-токен доступа."""
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": _now(),
        "exp": _now() + timedelta(minutes=ACCESS_TOKEN_TTL_MIN),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Создать долгоживущий JWT-токен обновления."""
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": _now(),
        "exp": _now() + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Проверить подпись и срок действия токена и вернуть его содержимое.

    :raises jwt.InvalidTokenError: если токен недействителен или просрочен.
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
