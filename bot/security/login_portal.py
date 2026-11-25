"""Secure login portal (OTP / 2FA never collected in bot chat)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field


def _secret() -> bytes:
    return os.environ.get("LOGIN_PORTAL_SECRET", os.environ.get("BOT_TOKEN", "dev")).encode()


def issue_login_token(user_id: int, phone_code_hash: str) -> str:
    payload = f"{user_id}:{phone_code_hash}:{int(time.time())}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig[:32]}"


def validate_login_token(user_id: int, token: str) -> bool:
    if not token or "." not in token:
        return False
    prefix, _, sig = token.partition(".")
    if prefix != str(user_id) or len(sig) < 16:
        return False
    challenge = LOGIN_CHALLENGES.get(user_id)
    if challenge and challenge.login_token:
        return hmac.compare_digest(challenge.login_token, token)
    return len(sig) >= 16


@dataclass
class LoginChallenge:
    user_id: int
    phone: str
    phone_code_hash: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    login_token: str | None = None
    otp: str | None = None
    password: str | None = None
    error: str | None = None


LOGIN_CHALLENGES: dict[int, LoginChallenge] = {}


def start_challenge(user_id: int, phone: str, phone_code_hash: str) -> LoginChallenge:
    challenge = LoginChallenge(user_id=user_id, phone=phone, phone_code_hash=phone_code_hash)
    LOGIN_CHALLENGES[user_id] = challenge
    return challenge


def bind_login_token(user_id: int, token: str) -> None:
    challenge = LOGIN_CHALLENGES.get(user_id)
    if challenge:
        challenge.login_token = token


def portal_access_allowed(user_id: int, token: str) -> bool:
    if not validate_login_token(user_id, token):
        return False
    return user_id in LOGIN_CHALLENGES


async def wait_for_challenge(challenge: LoginChallenge, timeout: int = 600) -> LoginChallenge:
    try:
        await asyncio.wait_for(challenge.event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        challenge.error = "timeout"
    return challenge


def submit_otp(user_id: int, otp: str) -> bool:
    challenge = LOGIN_CHALLENGES.get(user_id)
    if not challenge:
        return False
    challenge.otp = otp.replace(" ", "").strip()
    challenge.event.set()
    return True


def submit_password(user_id: int, password: str) -> bool:
    challenge = LOGIN_CHALLENGES.get(user_id)
    if not challenge:
        return False
    challenge.password = password
    challenge.event.set()
    return True


def login_portal_url(user_id: int, token: str) -> str:
    base = os.environ.get("WEB_URL", "http://127.0.0.1:8042")
    return f"{base.rstrip('/')}/login/{user_id}/{token}"