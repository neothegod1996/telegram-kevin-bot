import logging

from pyrogram import Client

from bot.utils.telegram_links import get_link_parts
from bot.utils.user_session import get_user_client

logger = logging.getLogger(__name__)


async def resolve_link_chat_id(app: Client, chat_id: int | str) -> int:
    if isinstance(chat_id, int):
        return chat_id
    text = str(chat_id).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    chat = await app.get_chat(text)
    return chat.id


async def resolve_chat_id(bot: Client, user_id: int, text: str) -> int:
    parts = get_link_parts(text)
    if parts:
        app = await get_user_client(user_id)
        if not app:
            return 0
        try:
            return await resolve_link_chat_id(app, parts[0])
        except Exception as e:
            await bot.send_message(user_id, f"❌ Chat not found: {e}")
            return 0
    if text.startswith("-100") and text[4:].isdigit():
        return int(text)
    if text.isdigit():
        return int(text)
    username = text.replace("@", "").strip()
    try:
        app = await get_user_client(user_id)
        chat = await app.get_chat(username)
        return chat.id
    except Exception as e:
        await bot.send_message(user_id, f"❌ Chat not found: {e}")
        return 0


async def get_latest_message_id(app: Client, chat_id: int) -> int:
    try:
        async for msg in app.get_chat_history(chat_id, limit=1):
            return msg.id
    except Exception as e:
        logger.error(f"Error fetching latest message ID: {e}")
    return 0