import logging
import math
import random
import time

from pyrogram import StopTransmission, types

from bot.config import Script
from bot.utils.constants import LINK_PREVIEW_DISABLED
from bot.utils.formatting import TimeFormatter, humanbytes
from bot.utils.transfer_cancel import is_transfer_cancelled

logger = logging.getLogger(__name__)


async def progress_for_pyrogram(
    current, total, start, file_message, edit_func, download_id, mode="Uploading"
):
    if is_transfer_cancelled(download_id):
        raise StopTransmission
    if total < 50_000_000:
        return

    progress_data = [
        ("■", "□"),
        ("★", "❍"),
        ("✿", "○"),
        ("❥", "♡"),
        ("♛", "❍"),
        ("✪", "❍"),
        ("★", "✩"),
    ]
    a, b = random.choice(progress_data)
    now = time.time()
    diff = now - start

    if round(diff % 25.0) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff else 0
        elapsed_ms = round(diff) * 1000
        eta_ms = round((total - current) / speed) * 1000 if speed else 0

        progress = "{0}{1}\n".format(
            "".join([a for _ in range(math.floor(percentage / (100 / 15)))]),
            "".join([b for _ in range(15 - math.floor(percentage / (100 / 15)))]),
        ).strip()

        tmp = Script.PROGRESS_MESSAGE.format(
            mode=mode,
            percentage=round(percentage, 2),
            progress=progress,
            speed=humanbytes(speed),
            eta=TimeFormatter(milliseconds=eta_ms) if eta_ms else "0 s",
            finished=humanbytes(current),
            total=humanbytes(total),
        )

        try:
            await edit_func(
                tmp,
                reply_markup=types.InlineKeyboardMarkup(
                    [[types.InlineKeyboardButton("Cancel", callback_data=f"cancel {download_id}")]]
                ),
                link_preview_options=LINK_PREVIEW_DISABLED,
            )
        except Exception as e:
            logger.error(f"Error editing progress message: {e}")