"""Notion integration configuration helpers."""

from __future__ import annotations

import re
import uuid

from bot.config import Config

_HEX32 = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)


def normalize_notion_page_id(value: str | None) -> str | None:
    """Return a canonical UUID string for Notion, or None if unset/invalid."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    compact = re.sub(r"[^a-fA-F0-9]", "", text)
    if len(compact) == 32 and _HEX32.match(compact):
        c = compact.lower()
        return f"{c[:8]}-{c[8:12]}-{c[12:16]}-{c[16:20]}-{c[20:]}"

    try:
        return str(uuid.UUID(text))
    except ValueError:
        return None


def notion_token_configured() -> bool:
    token = Config.NOTION_TOKEN
    return bool(token and str(token).strip())


def user_may_use_notion(user_id: int) -> bool:
    """Only the bot owner may write to Notion or change its destination."""
    return user_id == Config.OWNER_ID


def notion_indexing_enabled() -> bool:
    if not notion_token_configured():
        return False
    return normalize_notion_page_id(Config.NOTION_PARENT_PAGE_ID) is not None


def notion_enabled_for_user(user_id: int, requested: bool) -> bool:
    """Combine owner gate, feature flag, and caller request."""
    if not requested or not user_may_use_notion(user_id):
        return False
    return notion_indexing_enabled()


async def ensure_notion_parent_page_id() -> str | None:
    """Resolve parent page from memory Config, then MongoDB notion_config."""
    from database import db

    parent = normalize_notion_page_id(Config.NOTION_PARENT_PAGE_ID)
    if parent:
        return parent

    stored = await db.notion_config.get_page_id()
    parent = normalize_notion_page_id(stored)
    if parent:
        Config.NOTION_PARENT_PAGE_ID = parent
    return parent