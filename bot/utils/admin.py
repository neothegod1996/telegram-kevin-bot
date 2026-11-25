import functools

from pyrogram import Client, types

from bot.config import Config
from database import db


async def set_commands(app: Client):
    commands = [
        types.BotCommand("start", "🚀 Get started with the bot"),
        types.BotCommand("help", "💡 Need assistance? Find help here"),
        types.BotCommand("settings", "⚙️ Manage your settings"),
        types.BotCommand("batch", "📦 Save an entire channel"),
        types.BotCommand("nbatch", "Save an entire channel to Notion and Telegram"),
        types.BotCommand("batch_status", "📊 View and manage batch transfer progress"),
        types.BotCommand("nchange", "Change Notion page"),
        types.BotCommand("account", "👤 Manage your Telegram account"),
        types.BotCommand("channels", "📢 Manage your channels like a pro"),
        types.BotCommand("cancel", "❌ Cancel an ongoing transfer"),
        types.BotCommand("ndelete", "❌ Delete all Notion messages from the database"),
        types.BotCommand("ndelete_pages", "❌ Delete all Notion pages from the database"),
    ]
    await app.set_bot_commands(commands, scope=types.BotCommandScopeAllPrivateChats())


async def get_admins():
    config = await db.config.get_config("ADMINS")
    return config["value"]


async def add_admin(user_id):
    config = await db.config.get_config("ADMINS")
    if config:
        admins = config["value"]
        if user_id not in admins:
            admins.append(user_id)
            await db.config.update_config("ADMINS", admins)
            return True
    else:
        await db.config.add_config("ADMINS", [user_id])
        return True
    return False


async def remove_admin(user_id):
    config = await db.config.get_config("ADMINS")
    if config:
        admins = config["value"]
        if user_id in admins:
            admins.remove(user_id)
            await db.config.update_config("ADMINS", admins)
            return True
    return False


async def add_user(bot: Client, user: types.User):
    user_id = user.id
    if await db.users.read(user_id):
        return
    await db.users.create(user_id)
    text = (
        "New user!\n\n"
        f"Name: {user.first_name}\n"
        f"ID: `{user_id}`\n"
        f"Mention: {user.mention}\n"
    )
    await bot.send_message(Config.USER_INFO_LOG, text)
    return True


def check_admin(func):
    @functools.wraps(func)
    async def wrapper(client: Client, message):
        chat_id = getattr(message.from_user, "id", None)
        admins = await get_admins()
        if chat_id not in admins:
            return await message.reply_text("You are not allowed to use this command.")
        return await func(client, message)

    return wrapper