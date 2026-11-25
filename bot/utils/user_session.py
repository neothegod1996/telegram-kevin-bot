from pyrogram import Client, types

from bot.config import Config
from database import db


def login_prompt_markup(back_callback: str | None = None) -> types.InlineKeyboardMarkup:
    rows = [[types.InlineKeyboardButton("🔐 Login", callback_data="connect_account")]]
    if back_callback:
        rows.append([types.InlineKeyboardButton("🔙 Back", callback_data=back_callback)])
    return types.InlineKeyboardMarkup(rows)


async def get_user_client(user_id) -> Client | None:
    from bot.security.session_crypto import decrypt_session

    user = await db.users.read(user_id)
    if not user:
        return None

    session_id = user["session"].get("id")
    client = Config.CLIENTS.get(session_id)
    if client:
        return client
    session_string = decrypt_session(user["session"].get("string"))
    if not session_string:
        return None
    from bot import User

    return User(session_string, name=f"user_{user_id}")


async def ensure_user_logged_in(
    bot: Client,
    user_id: int,
    reply_target,
    *,
    back_callback: str | None = None,
    hint: str | None = None,
) -> Client | None:
    app = await get_user_client(user_id)
    if app:
        return app
    text = hint or (
        "⚠️ **Log in first** to use this feature.\n\n"
        "Open **My Account → Login** or use `/account`."
    )
    await bot.reply(reply_target, text, reply_markup=login_prompt_markup(back_callback))
    return None


async def resolve_accessible_chat(
    chat_id: int | str,
    *,
    bot: Client | None = None,
    app: Client | None = None,
    prefer_app: bool = False,
):
    clients: list[Client] = []
    if prefer_app:
        clients.extend(c for c in (app, bot) if c is not None)
    else:
        clients.extend(c for c in (bot, app) if c is not None)

    last_error: Exception | None = None
    for client in clients:
        try:
            return await client.get_chat(chat_id)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("No Telegram client available to resolve this chat.")