from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import Script
from bot.utils import add_user
from bot.utils.helpers import LINK_PREVIEW_DISABLED


@Client.on_message(filters.command("start") & filters.private & filters.incoming)
@Client.on_callback_query(filters.regex("^start$"))
async def start(bot: Client, message: Message):
    await add_user(bot, message.from_user)
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📢 Channels", callback_data="channels"),
                InlineKeyboardButton("📦 Batch", callback_data="bmenu_home_False"),
            ],
            [
                InlineKeyboardButton("👤 My Account", callback_data="connected_account"),
                InlineKeyboardButton("📋 Media Types", callback_data="mediatype_main"),
            ],
            [
                InlineKeyboardButton("❓ Help", callback_data="help_1"),
            ],
        ]
    )

    await bot.reply(
        message,
        text=Script.START_MESSAGE,
        reply_markup=markup,
        link_preview_options=LINK_PREVIEW_DISABLED,
    )
