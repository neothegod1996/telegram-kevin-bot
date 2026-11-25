import logging
import os

from pyrogram import Client, types

from bot.utils.ffmpeg import create_thumbnail

logger = logging.getLogger(__name__)


async def get_thumbnail(file_path: str):
    video_extensions = (
        ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg",
    )
    if not any(file_path.lower().endswith(ext) for ext in video_extensions):
        return None
    return await create_thumbnail(file_path)


async def download_thumbnail(app: Client, thumbnail_id: int):
    try:
        return await app.download_media(thumbnail_id)
    except Exception as e:
        logger.error(f"Error downloading thumbnail: {e}")
        return None


async def get_upload_function(message: types.Message, app: Client, file_path: str):
    media = message.document or message.video or message.photo or message.audio
    if not media:
        return None, None
    if message.document:
        return app.send_document, {"document": file_path}
    if message.video:
        return app.send_video, {"video": file_path}
    if message.audio:
        return app.send_audio, {"audio": file_path}
    if message.photo:
        return app.send_photo, {"photo": file_path}
    return None, None


def get_media(message: types.Message):
    if not message.media:
        return None
    return getattr(message, message.media.value)


def get_extension(message: types.Message) -> str:
    media = get_media(message)
    if not media:
        return ""
    file_name = getattr(media, "file_name", None)
    mimetype = getattr(media, "mime_type", None)
    if file_name:
        return file_name.split(".")[-1]
    if mimetype:
        return mimetype.split("/")[-1]
    return ""


def get_title(message: types.Message):
    title = message.document or message.video or message.audio
    if not title:
        return None
    return getattr(title, "file_name", None)


def get_mime_type(message: types.Message) -> str:
    media = message.document or message.video or message.audio
    if not media:
        return ""
    return media.mime_type.split("/")[0]


def get_file_name(message: types.Message):
    if not message.media:
        return None
    media = getattr(message, message.media.value, None)
    if not media:
        return None
    file_name = getattr(media, "file_name", None)
    if file_name:
        return file_name
    media_extensions = {"photo": ".jpg", "video": ".mp4", "audio": ".mp3"}
    media_type = message.media.value
    if media_type in media_extensions:
        return f"{media.file_id}{media_extensions[media_type]}"
    return None