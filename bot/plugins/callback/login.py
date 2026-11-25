import asyncio

from pyrogram.types import Message
from pyrogram import Client, filters
from asyncio.exceptions import TimeoutError
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from pyrogram.errors import (
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid,
)
from bot import User
from bot.security.login_portal import (
    bind_login_token,
    issue_login_token,
    login_portal_url,
    start_challenge,
    wait_for_challenge,
)
from bot.security.session_crypto import encrypt_session
from bot.utils.conversation import ask
from bot.utils.helpers import LINK_PREVIEW_DISABLED
from database import db


class Data:
    generate_single_button = [
        InlineKeyboardButton("🔒 Secure Login", callback_data="connect_account")
    ]

    home_buttons = [
        [InlineKeyboardButton("🔐 Account", callback_data="connected_account")],
        [InlineKeyboardButton(text="🏠 Return Home ", callback_data="start")],
    ]

    generate_button = [generate_single_button]


async def generate_session(bot: Client, msg: Message):

    user_id = msg.from_user.id

    api_id = bot.api_id
    api_hash = bot.api_hash

    t = "📲 Now please send your Phone number along with the country code. \nExample: `+19876543210`"
    t += f"\n\nNote: **Use the same number as the account you are now using.**"
    t += "\n\n/cancel to cancel ❌"

    phone_number_msg: Message = await ask(
        bot,
        user_id,
        t,
        user_id=user_id,
        filters=filters.text | filters.contact,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Send Phone Number", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
        timeout=300,
    )
    if await cancelled(phone_number_msg):
        return

    if phone_number_msg.contact:
        phone_number = phone_number_msg.contact.phone_number
    else:
        phone_number = phone_number_msg.text

    await msg.reply("🔐 Logging in as User...", reply_markup=ReplyKeyboardRemove())

    client = Client(
        name=f"user_{user_id}", api_id=api_id, api_hash=api_hash, in_memory=True
    )

    await client.connect()
    try:
        code = None
        code = await client.send_code(phone_number)
    except PhoneNumberInvalid:
        await msg.reply(
            "🚫 Phone number is invalid. Please start generating the session again.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    challenge = start_challenge(user_id, phone_number, code.phone_code_hash)
    token = issue_login_token(user_id, code.phone_code_hash)
    bind_login_token(user_id, token)
    portal = login_portal_url(user_id, token)
    await msg.reply(
        "📩 **Telegram sent you a login code in the official app.**\n\n"
        "For security, **do not type your OTP or 2FA password in this chat.**\n"
        f"Open the secure login page: {portal}\n\n"
        "Waiting for you to submit the code there…",
        link_preview_options=LINK_PREVIEW_DISABLED,
    )
    challenge = await wait_for_challenge(challenge, timeout=600)
    if challenge.error == "timeout" or not challenge.otp:
        await msg.reply(
            "⏰ Login timed out. Start again from Account.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    phone_code = challenge.otp
    try:
        await client.sign_in(phone_number, code.phone_code_hash, phone_code)
    except PhoneCodeInvalid:
        await msg.reply(
            "❌ OTP is invalid. Please start generating the session again.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    except PhoneCodeExpired:
        await msg.reply(
            "⌛ OTP has expired. Please start generating the session again.",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return
    except SessionPasswordNeeded:
        challenge.event = asyncio.Event()
        challenge.password = None
        portal_2fa = f"{login_portal_url(user_id, token)}?step=2fa"
        await msg.reply(
            "🔐 2FA required. Submit your password on the **same secure login page** "
            f"(do not send it in chat): {portal_2fa}",
            link_preview_options=LINK_PREVIEW_DISABLED,
        )
        challenge = await wait_for_challenge(challenge, timeout=300)
        if not challenge.password:
            await msg.reply(
                "⏰ 2FA timed out. Start again.",
                reply_markup=InlineKeyboardMarkup(Data.generate_button),
            )
            return
        try:
            await client.check_password(password=challenge.password)
        except PasswordHashInvalid:
            await msg.reply(
                "🚫 Invalid password. Start login again.",
                reply_markup=InlineKeyboardMarkup(Data.generate_button),
            )
            return

    string_session = await client.export_session_string()
    me = await client.get_me()

    if me.id != user_id:
        await msg.reply(
            "🚫 You are not the owner of the account. Please start generating the session again with your own number",
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return

    await db.users.update(
        user_id,
        {
            "session.string": encrypt_session(string_session),
            "session.id": me.id,
            "session.username": me.username,
        },
    )

    await bot.send_message(
        msg.chat.id,
        "🎉 Successfully logged in! Please continue with the buttons below.",
        reply_markup=InlineKeyboardMarkup(Data.home_buttons),
    )

    client = User(string_session, name=f"user_{user_id}")
    await client.start()


async def cancelled(msg):
    if not msg.text:
        return
    if "/cancel" in msg.text:
        await msg.reply(
            "🚫 Generation process cancelled!",
            quote=True,
            reply_markup=ReplyKeyboardRemove(),
        )
        await msg.reply(
            "You can login again by clicking the button below.",
            quote=True,
            reply_markup=InlineKeyboardMarkup(Data.generate_button),
        )
        return True
    elif msg.text.startswith("/"):  # Bot Commands
        await msg.reply(
            "🚫 Generation process cancelled!",
            quote=True,
            reply_markup=ReplyKeyboardRemove(),
        )
        return True
    else:
        return False
