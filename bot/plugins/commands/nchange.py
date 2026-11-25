import re

from pyrogram import Client, filters
from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                            InlineKeyboardMarkup, Message)

from bot.config import Config
from bot.utils.helpers import LINK_PREVIEW_DISABLED
from bot.utils.notion_settings import normalize_notion_page_id
from database import db


@Client.on_message(
    filters.command("nchange") & filters.private & filters.user(Config.OWNER_ID)
)
async def nchange_command(bot: Client, message: Message):
    if not message.command or len(message.command) < 2:
        current_page_id = Config.NOTION_PARENT_PAGE_ID
        return await message.reply(
            "❌ Please provide a Notion page link.\n\n"
            "**Usage:** `/nchange [page_link]`\n"
            "**Example:** `/nchange https://www.notion.so/carlosmr/Dwarf-Guild-2f10ae7ffdc0812ca599e9c8fdb47625`\n\n"
            f"**Current Page ID:** `https://www.notion.so/test-{current_page_id}`"
        )

    link = message.command[1]
    # Extract 32-character hex ID (Notion ID format)
    match = re.search(r"([a-f0-9]{32})", link)
    if not match:
        return await message.reply("❌ **Invalid link!** Could not extract Notion Page ID from the URL.")

    page_id = match.group(1)
    
    text = (
        f"🔍 **Found Page ID:** `{page_id}`\n\n"
        "⚠️ **Wait!** Before proceeding, please ensure you have added your integration to this page:\n\n"
        "1️⃣ Open https://www.notion.so/profile/integrations\n"
        "2️⃣ Click the integration name and go to 'Access' tab\n"
        "3️⃣ Select 'Edit access'\n"
        "4️⃣ Find and select your integration (e.g., Dwarf-Guild).\n\n"
        "Check your integrations at: [notion.so/profile/integrations](https://www.notion.so/profile/integrations)\n\n"
        "**Have you added the integration to this page?**"
    )
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Open Notion Integrations", url="https://www.notion.so/profile/integrations")
        ],
        [
            InlineKeyboardButton("✅ Yes, proceed", callback_data=f"nchange_yes|{page_id}"),
            InlineKeyboardButton("❌ No, not yet", callback_data="nchange_no")
        ]
    ])
    
    await message.reply(text, reply_markup=buttons, link_preview_options=LINK_PREVIEW_DISABLED)


@Client.on_callback_query(
    filters.regex(r"^nchange_") & filters.user(Config.OWNER_ID)
)
async def nchange_callback(bot: Client, query: CallbackQuery):
    if not query.data:
        return
        
    data = query.data.split("|")
    action = data[0]

    if action == "nchange_no":
        await query.answer("Please add the integration and try again.", show_alert=True)
        await query.message.edit("❌ **Aborted!**\n\nPlease add the integration to the Notion page first, then run the /nchange command again.")
        return

    if action == "nchange_yes":
        if len(data) < 2:
            return await query.answer("❌ Error: Missing Page ID.", show_alert=True)
            
        page_id = normalize_notion_page_id(data[1])
        if not page_id:
            return await query.answer("❌ Invalid Page ID.", show_alert=True)

        await db.notion_config.update_page_id(page_id, actor_user_id=query.from_user.id)
        Config.NOTION_PARENT_PAGE_ID = page_id
        
        await query.answer("✅ Notion Page ID updated!", show_alert=True)
        await query.message.edit(
            f"✅ **Notion Configuration Updated!**\n\n"
            f"**New Parent Page ID:** `{page_id}`\n\n"
            "The bot will now use this page for storing content."
        )