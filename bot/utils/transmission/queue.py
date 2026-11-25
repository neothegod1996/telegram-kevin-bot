import logging

from pyrogram import Client, types

from bot.config import Config
from bot.enums import TransferStatus
from database import db

logger = logging.getLogger(__name__)


async def add_transfer_to_queue(
    user_id, download_id, links, link_index, status, **kwargs
):
    Config.TRANSFERS[download_id] = {
        "user_id": user_id,
        "links": links,
        "link_index": link_index,
        "status": status,
    }
    return await db.transfers.create(
        user_id, download_id, links, link_index, status, **kwargs
    )


async def remove_transfer_from_queue(download_id):
    Config.TRANSFERS.pop(download_id, None)
    return await db.transfers.delete(download_id)


async def update_transfer(download_id, **kwargs):
    if download_id in Config.TRANSFERS:
        Config.TRANSFERS[download_id].update(kwargs)
    return await db.transfers.update(download_id, kwargs)


async def resume_transfers(bot: Client):
    transfers = await db.transfers.filter_documents(
        {
            "status": {
                "$in": [TransferStatus.SLEEPING.value, TransferStatus.IN_PROGRESS.value]
            }
        }
    )
    for transfer in transfers:
        user_id = transfer["user_id"]
        text = (
            f"**Bot has been restarted. You can resume your transfers now from "
            f"{transfer['link_index']} to {len(transfer['links'])}.**"
        )
        markup = types.InlineKeyboardMarkup(
            [
                [
                    types.InlineKeyboardButton(
                        "Resume Transfers",
                        callback_data=f"resume_transfers {transfer['_id']}",
                    )
                ]
            ]
        )
        try:
            await bot.send_message(user_id, text, reply_markup=markup)
        except Exception as e:
            logger.error(e)
        await update_transfer(transfer["_id"], status=None)