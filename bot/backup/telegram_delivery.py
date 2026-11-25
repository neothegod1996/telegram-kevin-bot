"""Telegram delivery: direct copy/forward with download+upload fallback and ledger."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pyrogram import Client, errors, types

from bot.backup.delivery_ledger import DeliveryLedger
from bot.config import Config

logger = logging.getLogger(__name__)


class DeliveryMethod(str, Enum):
    COPY = "copy"
    DOWNLOAD_UPLOAD = "download_upload"
    SKIPPED = "skipped"


@dataclass
class ChannelRoute:
    destination_channel_id: int
    topic_id: Optional[int] = None
    paid_media: Optional[dict[str, Any]] = None
    mirror_topics: bool = False

    @classmethod
    def from_user_channel(cls, channel: dict, *, mirror_topics: bool = False) -> "ChannelRoute":
        return cls(
            destination_channel_id=int(channel["destination_channel_id"]),
            topic_id=channel.get("topic_id"),
            paid_media=channel.get("paid_media"),
            mirror_topics=mirror_topics,
        )


@dataclass
class DeliveryOutcome:
    dest_chat_id: int
    method: DeliveryMethod
    skipped: bool = False
    confirmed: bool = False
    dest_message_id: Optional[int] = None
    error: Optional[str] = None


COPY_FALLBACK_ERRORS = (
    errors.ChatForwardsRestricted,
    errors.MessageAuthorRequired,
    errors.MediaEmpty,
    errors.MessageIdInvalid,
    errors.ChannelPrivate,
    errors.PeerIdInvalid,
)


def direct_copy_supported(message: types.Message) -> bool:
    if message.service or message.sticker:
        return False
    return True


async def get_delivery_destinations(
    bot: Client,
    user_id: int,
    source_chat_id: int,
    *,
    db,
    app: Client | None = None,
) -> list[ChannelRoute]:
    from database import db as default_db

    database = db or default_db
    valid: list[ChannelRoute] = []

    user_channels = await database.user_channels.filter_documents(
        {"user_id": user_id, "source_channel_id": source_chat_id, "status": True}
    )
    for channel in user_channels:
        dest_channel_id = channel["destination_channel_id"]
        reachable = False
        is_forum = False
        for client in (app, bot):
            if client is None:
                continue
            try:
                chat = await client.get_chat(dest_channel_id)
                is_forum = getattr(chat, "is_forum", False) is True
                reachable = True
                break
            except Exception as exc:
                logger.debug(
                    "get_chat(%s) via %s failed: %s",
                    dest_channel_id,
                    type(client).__name__,
                    exc,
                )
        if not reachable:
            logger.warning(
                "Using destination %s from channel pair; clients could not get_chat (delivery may still work).",
                dest_channel_id,
            )
        valid.append(
            ChannelRoute.from_user_channel(
                channel, mirror_topics=is_forum and not channel.get("topic_id")
            )
        )

    if not valid:
        valid.append(ChannelRoute(destination_channel_id=user_id))
    return valid


def _copy_failure(exc: BaseException) -> bool:
    if isinstance(exc, COPY_FALLBACK_ERRORS):
        return True
    name = exc.__class__.__name__.lower()
    if "forward" in name or "restricted" in name or "protected" in name:
        return True
    return False


class TelegramDeliveryEngine:
    def __init__(self, ledger: DeliveryLedger) -> None:
        self.ledger = ledger

    async def try_direct_copy(
        self,
        app: Client,
        message: types.Message,
        route: ChannelRoute,
        kwargs: dict[str, Any],
    ) -> Optional[types.Message]:
        dest_id = route.destination_channel_id
        try:
            return await app.copy_message(
                chat_id=dest_id,
                from_chat_id=message.chat.id,
                message_id=message.id,
                caption=message.caption or message.text,
                reply_markup=message.reply_markup,
                message_thread_id=kwargs.get("message_thread_id"),
            )
        except Exception as exc:
            if _copy_failure(exc):
                logger.debug("Direct copy failed for %s:%s -> %s: %s", message.chat.id, message.id, dest_id, exc)
                return None
            raise

    async def deliver_to_destination(
        self,
        *,
        bot: Client,
        app: Client,
        message: types.Message,
        route: ChannelRoute,
        user_id: int,
        delivered_log: Optional[types.Message] = None,
    ) -> DeliveryOutcome:
        source_chat_id = message.chat.id
        source_message_id = message.id
        dest_id = route.destination_channel_id

        if await self.ledger.is_confirmed(source_chat_id, source_message_id, dest_id):
            return DeliveryOutcome(
                dest_chat_id=dest_id,
                method=DeliveryMethod.SKIPPED,
                skipped=True,
                confirmed=True,
            )

        kwargs: dict[str, Any] = {}
        topic_id = route.topic_id
        if route.mirror_topics and topic_id is None:
            from bot.utils.transmission.topics import resolve_destination_topic

            topic_id = await resolve_destination_topic(app, message, dest_id)
        paid_star = (
            route.paid_media.get("stars")
            if route.paid_media and route.paid_media.get("status")
            else None
        )
        if topic_id:
            kwargs["message_thread_id"] = topic_id

        sent: Optional[types.Message] = None
        method = DeliveryMethod.COPY

        if direct_copy_supported(message):
            sent = await self.try_direct_copy(app, message, route, kwargs)

        if sent is None and delivered_log is not None:
            method = DeliveryMethod.DOWNLOAD_UPLOAD
            caption = delivered_log.text or delivered_log.caption or ""
            if paid_star and (message.photo or message.video):
                if message.photo:
                    media = types.InputMediaPhoto(delivered_log.photo.file_id)
                elif message.video:
                    media = types.InputMediaVideo(delivered_log.video.file_id)
                sent = await bot.floodwait_handler(
                    bot.send_paid_media,
                    chat_id=dest_id,
                    stars_amount=paid_star,
                    media=[media],
                    caption=caption,
                    reply_to_message_id=topic_id,
                    **kwargs,
                )
            elif message.media:
                sent = await bot.floodwait_handler(
                    delivered_log.copy,
                    dest_id,
                    caption=caption,
                    reply_markup=message.reply_markup,
                    **kwargs,
                )
            else:
                sent = await bot.floodwait_handler(
                    bot.send_message,
                    dest_id,
                    caption,
                    reply_markup=message.reply_markup,
                    **kwargs,
                )

        if sent is None and delivered_log is None and not message.media and message.text:
            method = DeliveryMethod.COPY
            sent = await self.try_direct_copy(app, message, route, kwargs)

        if sent is None:
            return DeliveryOutcome(
                dest_chat_id=dest_id,
                method=method,
                confirmed=False,
                error="delivery_failed",
            )

        await self.ledger.confirm(
            source_chat_id,
            source_message_id,
            dest_id,
            dest_message_id=getattr(sent, "id", None),
            method=method.value,
        )
        return DeliveryOutcome(
            dest_chat_id=dest_id,
            method=method,
            confirmed=True,
            dest_message_id=getattr(sent, "id", None),
        )

    async def filter_pending_routes(
        self,
        message: types.Message,
        routes: list[ChannelRoute],
    ) -> list[ChannelRoute]:
        pending: list[ChannelRoute] = []
        for route in routes:
            if not await self.ledger.is_confirmed(message.chat.id, message.id, route.destination_channel_id):
                pending.append(route)
        return pending


async def build_delivery_ledger_for_user(user_id: int):
    from database import db

    return DeliveryLedger(db.delivery_ledger.store(), user_id=user_id)
