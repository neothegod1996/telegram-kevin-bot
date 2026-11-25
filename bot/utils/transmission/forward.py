import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Optional

from pyrogram import Client, types

from bot.backup.reports import ForwardResult, TelegramMessageReport
from bot.config import Config
from bot.exceptions import CancelledError
from bot.utils.transfer_cancel import is_transfer_cancelled
from bot.utils.transmission.media_io import download_media, upload_media
from database import db

logger = logging.getLogger(__name__)

ShouldAbort = Callable[[], Awaitable[bool]]


async def forward_message(
    bot: Client,
    app: Client,
    message: types.Message,
    user_id: int,
    *,
    retain_download_path: bool = False,
    should_abort: Optional[ShouldAbort] = None,
) -> ForwardResult:
    """Deliver message to Telegram destinations only (no Notion)."""
    from bot.backup.telegram_delivery import (
        TelegramDeliveryEngine,
        build_delivery_ledger_for_user,
        get_delivery_destinations,
    )

    chat_id = message.chat.id
    msg_id = message.id

    ledger = await build_delivery_ledger_for_user(user_id)
    engine = TelegramDeliveryEngine(ledger)
    routes = await get_delivery_destinations(
        bot, user_id, chat_id, db=db, app=app
    )
    pending_routes = await engine.filter_pending_routes(message, routes)

    if not pending_routes:
        logger.info(
            "Telegram: skipping %s:%s — all destinations already in done-ledger",
            chat_id,
            msg_id,
        )
        if is_transfer_cancelled(message.download_id):
            raise CancelledError
        return ForwardResult(
            telegram=TelegramMessageReport(
                chat_id,
                msg_id,
                "skipped",
                error="already_in_ledger",
                skipped_destinations=len(routes),
            )
        )

    file_path = None
    progress_msg = None
    delivered_log: types.Message | None = None
    skipped_destinations = len(routes) - len(pending_routes)

    for route in pending_routes:
        if should_abort and await should_abort():
            raise CancelledError
        await engine.deliver_to_destination(
            bot=bot,
            app=app,
            message=message,
            route=route,
            user_id=user_id,
            delivered_log=None,
        )

    still_pending = await engine.filter_pending_routes(message, pending_routes)

    if still_pending and message.media:
        try:
            progress_msg = await bot.send_message(
                user_id, f"📤 Telegram: fetching media ({message.index})..."
            )
            file_path = await download_media(
                bot, user_id, message, progress_msg, should_abort=should_abort
            )
            logger.info("Downloaded media file: %s: %s", file_path, message.link)
            if file_path:
                delivered_log, file_path = await upload_media(
                    user_id,
                    bot,
                    app,
                    file_path,
                    channel_id=Config.FILES_LOG,
                    message=message,
                    progress_msg=progress_msg,
                    should_abort=should_abort,
                )
            else:
                await bot.send_message(
                    user_id, "Failed to download protected media. Please try again."
                )
                return ForwardResult(
                    telegram=TelegramMessageReport(
                        chat_id, msg_id, "failed", error="download_failed"
                    )
                )
        finally:
            if progress_msg:
                with suppress(Exception):
                    await progress_msg.delete()

    needs_text_log = False
    if delivered_log is None:
        for route in pending_routes:
            if not await ledger.is_confirmed(
                message.chat.id, message.id, route.destination_channel_id
            ):
                needs_text_log = True
                break
    if needs_text_log and message.text and not message.media:
        delivered_log = await bot.send_message(
            Config.FILES_LOG, message.text, reply_markup=message.reply_markup
        )

    failed_destinations: list[int] = []
    for route in pending_routes:
        if should_abort and await should_abort():
            raise CancelledError
        if await ledger.is_confirmed(message.chat.id, message.id, route.destination_channel_id):
            continue
        outcome = await engine.deliver_to_destination(
            bot=bot,
            app=app,
            message=message,
            route=route,
            user_id=user_id,
            delivered_log=delivered_log,
        )
        if not outcome.confirmed:
            failed_destinations.append(route.destination_channel_id)

    retained: str | None = None
    if file_path:
        if retain_download_path:
            retained = file_path
        else:
            os.remove(file_path)

    if failed_destinations:
        await bot.send_message(
            user_id,
            "Failed to deliver to some destinations. Retry will skip confirmed copies.",
        )

    if is_transfer_cancelled(message.download_id):
        if retained and os.path.exists(retained):
            os.remove(retained)
        raise CancelledError
    if should_abort and await should_abort():
        if retained and os.path.exists(retained):
            os.remove(retained)
        raise CancelledError

    if failed_destinations:
        status = "partial" if len(failed_destinations) < len(pending_routes) else "failed"
        tg_report = TelegramMessageReport(
            chat_id,
            msg_id,
            status,
            error="some_destinations_failed",
            failed_destinations=failed_destinations,
            skipped_destinations=skipped_destinations,
        )
    else:
        tg_report = TelegramMessageReport(
            chat_id,
            msg_id,
            "succeeded",
            skipped_destinations=skipped_destinations,
        )

    return ForwardResult(telegram=tg_report, retained_path=retained)