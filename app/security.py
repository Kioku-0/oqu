"""Модуль безопасности: хэширование паролей, JWT-токены, политики защиты.

Здесь собрана «криптографическая» часть проекта, отделённая от логики:

* хэширование паролей алгоритмом **PBKDF2-HMAC-SHA256** (стандартная библиотека
  :mod:`hashlib`, внешние зависимости не требуются; пароль никогда не хранится
  в открытом виде — раздел 5.4 методички);
* выпуск и проверка **JWT**-токенов доступа и обновления (обязательная функция
  варианта 11 — «аутентификация JWT»);
* константы политики защиты от **подбора пароля (брутфорса)**.

SECRET_KEY берётся из переменной окружения ``SECRET_KEY``. Если её нет
(локальный запуск), ключ один раз генерируется случайно и сохраняется в
``instance/secret.key``, который не попадает в Git. В коде ключа нет.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEY_FILE = os.path.join(_BASE_DIR, "instance", "secret.key")


def _load_secret_key() -> str:
    """Взять ключ из окружения или из локального файла (создав его)."""
    env_key = os.environ.get("SECRET_KEY", "")
    if env_key:
        return env_key
    try:
        with open(_KEY_FILE, encoding="utf-8") as fh:
            key = fh.read().strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(48)
    try:
        os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
        with open(_KEY_FILE, "w", encoding="utf-8") as fh:
            fh.write(key)
    except OSError:
        pass  # только для этого запуска (например, папка только для чтения)
    return key


# --- Общие настройки ------------------------------------------------------
SECRET_KEY: str = _load_secret_key()
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
    """Вернуть хэш пароля в формате ``pbkdf2_sha256$rounds$salt$hash``.

    Соль генерируется случайно для каждого пароля, поэтому одинаковые пароли
    дают разные хэши. Сам пароль восстановить из хэша нельзя.
    """
    if not isinstance(password, str) or password == "":
        raise ValueError("Пароль не должен быть пустым")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH, password.encode("utf-8"), salt, _PBKDF2_ROUNDS
    )
    return (f"pbkdf2_{_PBKDF2_HASH}${_PBKDF2_ROUNDS}$"
            f"{salt.hex()}${digest.hex()}")


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


# Хэш случайного пароля: проверяется при входе под несуществующим логином,
# чтобы время ответа не выдавало, есть ли такой пользователь.
DUMMY_HASH = hash_password(secrets.token_hex(16))


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
