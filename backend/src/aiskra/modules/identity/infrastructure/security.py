"""Адаптеры безопасности: хеширование паролей (scrypt из stdlib) и токены сессий (ADR-0010).

scrypt — «тяжёлая по памяти» функция (RFC 7914), есть в стандартной библиотеке: никаких внешних
зависимостей для офлайн-контура. Параметры записываются в сам хеш, поэтому их можно усилить позже,
не ломая старые пароли. Вычисление уходит в поток, чтобы не блокировать event loop (~50 мс).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets

_SCHEME = "scrypt"
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class ScryptPasswordHasher:
    """Формат хеша: `scrypt$<n>$<r>$<p>$<соль>$<ключ>` (base64url)."""

    def __init__(self, n: int = 2**14) -> None:
        if n < 2 or n & (n - 1):
            raise ValueError("Параметр scrypt n должен быть степенью двойки")
        self._n = n
        self._dummy = self._hash_sync("dummy-password", secrets.token_bytes(_SALT_BYTES), n, _R, _P)

    @staticmethod
    def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
        return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=_DKLEN, maxmem=256 * 1024 * 1024)

    def _hash_sync(self, password: str, salt: bytes, n: int, r: int, p: int) -> str:
        key = self._derive(password, salt, n, r, p)
        return f"{_SCHEME}${n}${r}${p}${_b64(salt)}${_b64(key)}"

    def _verify_sync(self, password: str, password_hash: str) -> bool:
        try:
            scheme, n, r, p, salt, key = password_hash.split("$")
            if scheme != _SCHEME:
                return False
            actual = self._derive(password, _unb64(salt), int(n), int(r), int(p))
        except ValueError:
            return False
        return hmac.compare_digest(actual, _unb64(key))

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hash_sync, password, secrets.token_bytes(_SALT_BYTES), self._n, _R, _P)

    async def verify(self, password: str, password_hash: str) -> bool:
        return await asyncio.to_thread(self._verify_sync, password, password_hash)

    async def burn(self, password: str) -> None:
        await asyncio.to_thread(self._verify_sync, password, self._dummy)


class SessionTokenIssuer:
    """Токен — 256 бит из `secrets`; в БД хранится только SHA-256 (утечка таблицы не даёт войти)."""

    def issue(self) -> str:
        return secrets.token_urlsafe(32)

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
