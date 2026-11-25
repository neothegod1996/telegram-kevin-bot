from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import Config
from bot.utils import get_link_parts, get_user_client
from bot.utils.batch_utils import create_and_run_task, resolve_link_chat_id


@Client.on_message(
    filters.command("batch_topic")
    & filters.private
    & filters.incoming
    & filters.user(Config.OWNER_ID)
)
async def batch_topic(bot: Client, message: Message):
    """
    Priority pass: copy only messages in one forum topic first.

    Usage: /batch_topic <start_link> <last_message_id_or_link> <topic_id>
    """
    if len(message.command) < 4:
        return await message.reply_text(
            "Usage: `/batch_topic <start_link> <end_id_or_link> <topic_id>`\n"
            "Run a full `/batch` afterward; the done-ledger skips already copied messages."
        )

    start_parts = get_link_parts(message.command[1])
    if not start_parts:
        return await message.reply_text("Invalid start link.")

    raw_chat_id, start_id, _ = start_parts
    user_id = message.from_user.id
    app = await get_user_client(user_id)
    if not app:
        return await message.reply_text("Please log in first.")

    try:
        chat_id = await resolve_link_chat_id(app, raw_chat_id)
    except Exception as e:
        return await message.reply_text(f"Could not access chat: {e}")

    end_arg = message.command[2]
    if end_arg.isdigit():
        end_id = start_id + int(end_arg) - 1
    else:
        end_parts = get_link_parts(end_arg)
        if not end_parts:
            return await message.reply_text("Invalid end link or different chat.")
        try:
            end_chat_id = await resolve_link_chat_id(app, end_parts[0])
        except Exception:
            return await message.reply_text("Invalid end link or different chat.")
        if end_chat_id != chat_id:
            return await message.reply_text("Invalid end link or different chat.")
        end_id = end_parts[1]

    topic_id = int(message.command[3])

    chat = await app.get_chat(chat_id)
    title = f"{chat.title or 'Chat'} (topic {topic_id})"
    await create_and_run_task(
        bot,
        user_id,
        chat_id,
        start_id,
        end_id,
        notion=False,
        title=title,
        source_topic_id=topic_id,
        priority_pass=True,
    )
    await message.reply_text(
        f"⚡ Topic-priority batch started for topic `{topic_id}` (messages {start_id}-{end_id})."
    )