import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Optional

from pyrogram import Client, types

from bot.config import Config
from bot.exceptions import CancelledError
from bot.utils.ffmpeg import get_video_details
from bot.utils.media_message import (
    get_file_name,
    get_thumbnail,
    get_title,
    get_upload_function,
)
from bot.utils.media_type import get_media_type
from bot.utils.progress import progress_for_pyrogram
from bot.utils.transfer_cancel import is_transfer_cancelled
from bot.utils.transmission.topics import handle_topic_thread

logger = logging.getLogger(__name__)


ShouldAbort = Callable[[], Awaitable[bool]]


async def download_media(
    bot,
    user_id,
    message: types.Message,
    progress_msg,
    *,
    should_abort: Optional[ShouldAbort] = None,
):
    media = message.document or message.video or message.photo or message.audio
    if not media:
        return None

    filename = get_file_name(message)
    if not filename:
        await bot.send_message(user_id, "No file name found.")
        return None

    start = time.time()
    file_path = await bot.floodwait_handler(
        message.download,
        file_name=filename,
        progress=progress_for_pyrogram,
        progress_args=(
            start,
            message,
            progress_msg.edit,
            message.download_id,
            f"Downloading ({message.index})",
        ),
        should_abort=should_abort,
    )
    if not file_path and is_transfer_cancelled(message.download_id):
        raise CancelledError
    return file_path


async def upload_media(
    user_id,
    bot: Client,
    app: Client,
    file_path: str,
    channel_id: int,
    message: types.Message,
    progress_msg,
    *,
    should_abort: Optional[ShouldAbort] = None,
):
    await bot.floodwait_handler(
        progress_msg.edit, "Starting upload...", should_abort=should_abort
    )

    upload_instance = app
    thumbnail = await get_thumbnail(file_path)
    function, kwargs = await get_upload_function(message, upload_instance, file_path)

    if not function:
        return await bot.send_message(
            user_id, "Invalid file upload mode. Please select a valid file upload mode."
        )

    if function == upload_instance.send_video:
        width, height, duration = await get_video_details(file_path)
        kwargs["duration"] = duration
        kwargs["width"] = width
        kwargs["height"] = height

    kwargs["chat_id"] = channel_id
    await handle_topic_thread(app, message, channel_id, kwargs)

    media = ["audio", "document", "video", "photo"]
    if any(media_type in kwargs for media_type in media) and thumbnail:
        kwargs["thumb"] = thumbnail

    title = get_title(message)
    if title:
        kwargs["file_name"] = title

    kwargs["progress"] = progress_for_pyrogram
    kwargs["progress_args"] = (
        time.time(),
        message,
        progress_msg.edit,
        message.download_id,
        f"Uploading ({message.index})",
    )
    logger.info("upload start")

    caption = message.text or message.caption or ""
    media_type = await get_media_type()
    if "text" in media_type:
        kwargs["caption"] = caption

    await bot.floodwait_handler(
        progress_msg.edit, "Uploading...", should_abort=should_abort
    )
    log = await bot.floodwait_handler(function, should_abort=should_abort, **kwargs)
    if thumbnail:
        os.remove(thumbnail)
    if not log:
        if is_transfer_cancelled(message.download_id):
            raise CancelledError
        raise Exception("Failed to upload message")

    log = await bot.get_messages(log.chat.id, log.id)
    return log, file_path