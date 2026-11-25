import random

from pyrogram import Client

from bot.utils.batch.resolve import get_latest_message_id, resolve_link_chat_id
from bot.utils.batch.ui import format_task_text, make_task_markup
from bot.utils.batch.worker import start_background_batch
from bot.utils.telegram_links import get_link_parts
from bot.utils.user_session import get_user_client
from database import db


async def create_and_run_task(
    bot: Client,
    user_id: int,
    chat_id: int,
    start_id: int,
    end_id: int,
    notion: bool,
    title: str = "Chat",
    *,
    source_topic_id: int | None = None,
    priority_pass: bool = False,
):
    active = await db.batch_tasks.get_active_task(user_id)
    if active:
        return await bot.send_message(user_id, "⚠️ You already have a running batch task. Pause it first.")

    task_id = random.randint(100000, 999999)
    doc = {
        "task_id": task_id,
        "user_id": user_id,
        "source_chat_id": chat_id,
        "source_chat_title": title,
        "first_message_id": start_id,
        "last_message_id": end_id,
        "total_messages": end_id - start_id + 1,
        "notion_enabled": notion,
        "source_topic_id": source_topic_id,
        "priority_pass": priority_pass,
    }
    await db.batch_tasks.create_task(doc)
    await start_background_batch(bot, user_id, task_id)

    task = await db.batch_tasks.read(task_id)
    if task:
        await bot.send_message(user_id, format_task_text(task), reply_markup=make_task_markup(task))


async def setup_custom_task(
    bot: Client, user_id: int, first_parts: tuple, last_text: str, notion: bool
):
    raw_chat_id, first_id, _ = first_parts
    app = await get_user_client(user_id)
    if not app:
        return await bot.send_message(user_id, "⚠️ Please log in first.")
    try:
        chat_id = await resolve_link_chat_id(app, raw_chat_id)
    except Exception as e:
        return await bot.send_message(user_id, f"❌ Could not access source chat: {e}")

    if last_text.isdigit():
        last_id = first_id + int(last_text) - 1
    else:
        last_parts = get_link_parts(last_text)
        if not last_parts:
            return await bot.send_message(user_id, "❌ Invalid link or different chat.")
        try:
            last_chat_id = await resolve_link_chat_id(app, last_parts[0])
        except Exception:
            return await bot.send_message(user_id, "❌ Invalid link or different chat.")
        if last_chat_id != chat_id:
            return await bot.send_message(user_id, "❌ Invalid link or different chat.")
        last_id = last_parts[1]

    if last_id < first_id:
        return await bot.send_message(user_id, "❌ Last message must be older/higher than first message.")

    chat = await app.get_chat(chat_id)
    title = chat.title or getattr(chat, "first_name", "Chat") if chat else "Chat"
    await create_and_run_task(bot, user_id, chat_id, first_id, last_id, notion, title)


async def setup_sync_task(
    bot: Client, user_id: int, chat_id: int, notion: bool, title: str | None = None
):
    app = await get_user_client(user_id)
    if not app:
        return await bot.send_message(user_id, "⚠️ Please log in first.")

    incomplete = await db.batch_tasks.unfinished_general_tasks(chat_id, user_id)
    if incomplete:
        return await bot.send_message(
            user_id,
            "⚠️ This chat has unfinished/failed batch work. Resume or audit it "
            "before Sync; skipping ahead could miss messages.",
        )

    max_indexed = await db.batch_tasks.get_max_message_id(chat_id, user_id)
    if max_indexed is None:
        return await bot.send_message(
            user_id,
            "❌ No indexed messages found for this chat. Run a Custom Batch first to initialize.",
        )

    latest_id = await get_latest_message_id(app, chat_id)
    if latest_id == 0:
        return await bot.send_message(user_id, "❌ Could not fetch channel history.")

    start_id = max_indexed + 1
    if latest_id < start_id:
        return await bot.send_message(user_id, "✅ Channel is already fully indexed/synced!")

    if not title:
        try:
            chat = await app.get_chat(chat_id)
            title = chat.title or getattr(chat, "first_name", "Chat") if chat else "Chat"
        except Exception:
            title = "Chat"

    await bot.send_message(user_id, f"ℹ️ Syncing from message ID {start_id} to {latest_id}.")
    await create_and_run_task(bot, user_id, chat_id, start_id, latest_id, notion, title)