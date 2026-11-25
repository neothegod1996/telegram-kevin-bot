"""Encrypt Telegram session strings at rest (SESSION_ENCRYPTION_KEY env)."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet | None:
    raw = os.environ.get("SESSION_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def encrypt_session(session_string: str) -> str:
    f = _fernet()
    if not f or not session_string:
        return session_string
    return "enc:" + f.encrypt(session_string.encode()).decode()


def decrypt_session(value: str | None) -> str | None:
    if not value:
        return value
    if not value.startswith("enc:"):
        return value
    f = _fernet()
    if not f:
        raise RuntimeError("SESSION_ENCRYPTION_KEY required to decrypt sessions")
    try:
        return f.decrypt(value[4:].encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Failed to decrypt stored session") from exc