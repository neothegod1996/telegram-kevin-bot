from bot.config import Config
from bot.enums import TransferStatus
from pyrogram import types


def is_transfer_cancelled(download_id) -> bool:
    return (
        Config.TRANSFERS.get(download_id, {}).get("status")
        == TransferStatus.CANCELLED.value
    )


async def is_input_cancelled(message: types.Message):
    if message.text and message.text.lower() == "/cancel":
        return await message.reply_text("❌ Operation cancelled.")
    return False