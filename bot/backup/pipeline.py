"""Run Telegram delivery, then Notion backup — always in that order."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Optional

from pyrogram import Client, types

from bot.backup.notion_backup import NotionJobReport, backup_message_to_notion
from bot.backup.reports import ForwardResult, TelegramMessageReport
from bot.backup.rollback import rollback_message_delivery
from bot.exceptions import CancelledError
from bot.utils.notion_settings import notion_enabled_for_user, notion_indexing_enabled
from bot.utils.transmission.forward import forward_message

ShouldAbort = Callable[[], Awaitable[bool]]


async def run_telegram_then_notion(
    bot: Client,
    app: Client,
    message: types.Message,
    user_id: int,
    *,
    notion_requested: bool = False,
    should_abort: Optional[ShouldAbort] = None,
) -> tuple[ForwardResult, NotionJobReport | None]:
    """
    Phase 1: Telegram destinations (copy / download+upload).
    Phase 2: Notion file backup + page index (only after phase 1 returns).
    """
    try:
        fwd = await forward_message(
            bot,
            app,
            message,
            user_id,
            retain_download_path=True,
            should_abort=should_abort,
        )
    except CancelledError:
        await rollback_message_delivery(bot, app, message.chat.id, message.id)
        raise

    notion_on = notion_enabled_for_user(user_id, notion_requested) and notion_indexing_enabled()
    if not notion_on:
        _cleanup_retained(fwd)
        return fwd, None

    if should_abort and await should_abort():
        _cleanup_retained(fwd)
        await rollback_message_delivery(bot, app, message.chat.id, message.id)
        raise CancelledError

    try:
        notion_report = await backup_message_to_notion(
            bot,
            app,
            message,
            user_id,
            file_path=fwd.retained_path,
            should_abort=should_abort,
        )
    except CancelledError:
        _cleanup_retained(fwd)
        await rollback_message_delivery(bot, app, message.chat.id, message.id)
        raise
    _cleanup_retained(fwd)
    if should_abort and await should_abort():
        await rollback_message_delivery(bot, app, message.chat.id, message.id)
        raise CancelledError
    return fwd, notion_report


def _cleanup_retained(fwd: ForwardResult) -> None:
    path = fwd.retained_path
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


async def run_telegram_only(
    bot: Client,
    app: Client,
    message: types.Message,
    user_id: int,
    *,
    should_abort: Optional[ShouldAbort] = None,
) -> ForwardResult:
    """Telegram-only step (batch /nbatch uses this before a separate notion call)."""
    return await forward_message(
        bot,
        app,
        message,
        user_id,
        should_abort=should_abort,
    )