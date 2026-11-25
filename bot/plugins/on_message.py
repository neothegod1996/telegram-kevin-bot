import asyncio
import logging
import random

from pyrogram import Client, errors, filters, types

from bot.backup.task_control import interruptible_sleep
from bot.config import Config
from bot.enums import TransferStatus
from bot.exceptions import CancelledError
from bot.utils import (
    add_transfer_to_queue,
    get_link_parts,
    get_media_type,
    get_user_client,
    is_transfer_cancelled,
    is_valid_link,
    remove_transfer_from_queue,
    update_transfer,
)
from bot.backup.rollback import rollback_message_delivery
from bot.utils.conversation import has_pending_ask
from bot.backup.notion_backup import format_notion_line
from bot.backup.pipeline import run_telegram_then_notion
from bot.backup.reports import format_telegram_line
from bot.utils.notion_settings import notion_enabled_for_user, notion_indexing_enabled
from database import db


def CANCEL_MARKUP(download_id):
    return types.InlineKeyboardMarkup([[types.InlineKeyboardButton("Cancel Transfer", callback_data=f"cancel {download_id}")]])


@Client.on_message(
    filters.text
    & filters.private
    & filters.incoming
    & (filters.regex(r"^https?://") | filters.regex(r"^tg://"))
    & filters.user(Config.OWNER_ID)
)
async def on_https_message(bot: Client, message: types.Message, **kwargs):
    user_message = message
    is_batch = kwargs.get("is_batch", False)
    notion_requested = kwargs.get("notion_enabled", True)
    link = None

    user_id = message.from_user.id
    notion_enabled = notion_enabled_for_user(user_id, notion_requested)
    if has_pending_ask(user_id, message.chat.id):
        return

    if not is_valid_link(message):
        return await message.reply_text("Invalid link.")

    for download_id, transfer in Config.TRANSFERS.items():
        if (
            transfer["user_id"] == user_id
            and transfer["status"] == TransferStatus.IN_PROGRESS.value
        ):
            return await message.reply_text(
                "You have a transfer in progress. Please wait for it to complete."
            )

    app = await get_user_client(user_id)

    if not app:
        return await bot.floodwait_handler(
            bot.send_message,
            user_id,
            "You need to login first to use this bot.",
            reply_markup=types.InlineKeyboardMarkup(
                [
                    [
                        types.InlineKeyboardButton(
                            "Login", callback_data="connect_account"
                        )
                    ],
                ]
            ),
        )

    links = message.text.split()
    if not links:
        return await message.reply_text("No links found.")

    success, failed, not_allowed, deleted = 0, 0, 0, 0
    tg_ok, tg_skip, tg_fail = 0, 0, 0
    notion_ok, notion_skip, notion_fail = 0, 0, 0
    job_lines: list[str] = []
    out = await bot.floodwait_handler(
        bot.send_message, user_id, f"Processing {len(links)} links..."
    )
    await (await out.pin(both_sides=True)).delete()

    for i, link in enumerate(links, 1):
        parts = get_link_parts(link)

        if not parts:
            failed += 1
            await bot.floodwait_handler(
                bot.send_message, user_id, f"Invalid link - {link}"
            )
            continue

        chat_id, message_id, topic_id = parts

        try:
            error_message = ""
            chat = None
            try:
                chat = await app.get_chat(chat_id)
            except Exception as e:
                error_message += f"Error: {e}\n"
                continue

            if chat is None:
                try:
                    chat = await app.get_users(chat_id)
                except Exception as e:
                    error_message += f"Error: {e}\n"
                    continue

            if chat is None:
                raise Exception(f"Could not access chat {chat_id} {error_message}")
        except errors.AuthKeyDuplicated:
            await db.users.remove_session(user_id)
            await out.unpin()
            return await out.edit(
                "Your session has expired. Please login again.",
                reply_markup=types.InlineKeyboardMarkup(
                    [
                        [
                            types.InlineKeyboardButton(
                                "Login", callback_data="connected_account"
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            failed += 1
            logging.error(f"Failed to access chat {chat_id}: {e}")
            text = "⚠️ Unable to access the content!\n\n"
            text += "🔹 Please join the channel first and try again\n"
            text += "🔹 For private chats:\n"
            text += "- First time: Use their @username\n"
            text += "- Next time: You can use their User ID\n"
            text += "🔹 Make sure you have access to this chat"
            text += f"\n\n💡 Chat: {chat_id}\n\n💡 Error: {error_message}"

            await bot.floodwait_handler(bot.send_message, user_id, text)
            if is_batch:
                logging.info(f"Batch transfer cancelled for message {message.link}")
                break
            continue

        try:
            message = await bot.floodwait_handler(
                app.get_messages, chat_id, message_id
            )
        except Exception as e:
            failed += 1
            logging.error(f"Message not found for link {link}: {e}")
            await bot.floodwait_handler(
                bot.send_message, user_id, f"Message not found - {link}"
            )
            continue

        if message.empty or message.sticker or message.service:
            deleted += 1
            continue


        allowed_media_types = await get_media_type()

        if message.media and message.media.value not in allowed_media_types:
            not_allowed += 1
            continue

        if message.text and "text" not in allowed_media_types:
            not_allowed += 1
            continue

        download_id = random.randint(100000, 999999)
        message.download_id = download_id
        message.index = f"{i} of {len(links)}"

        await add_transfer_to_queue(
            user_id=user_id,
            download_id=download_id,
            links=links,
            link_index=i - 1,
            status=TransferStatus.IN_PROGRESS.value,
            user_message_id=user_message.id,
            user_message_chat_id=user_message.chat.id,
        )

        progress_text = f"Downloading: {i} of {len(links)}\n"
        progress_text += f"Success: {success}\n"
        progress_text += f"Failed: {failed}"
        progress_text += f"\n\nRunning: {message.link}"

        await bot.floodwait_handler(
            out.edit_text, progress_text, reply_markup=CANCEL_MARKUP(download_id)
        )

        async def should_abort_link() -> bool:
            return is_transfer_cancelled(download_id)

        try:
            fwd, notion_report = await run_telegram_then_notion(
                bot,
                app,
                message,
                user_id,
                notion_requested=notion_enabled,
                should_abort=should_abort_link,
            )
            tg = fwd.telegram
            job_lines.append(format_telegram_line(tg))
            if tg.status == "succeeded":
                tg_ok += 1
            elif tg.status == "skipped":
                tg_skip += 1
            else:
                tg_fail += 1
            if notion_report is not None:
                job_lines.append(format_notion_line(notion_report))
                if notion_report.status == "succeeded":
                    notion_ok += 1
                elif notion_report.status == "skipped":
                    notion_skip += 1
                else:
                    notion_fail += 1
        except CancelledError:
            logging.info(f"Transfer cancelled for message {message.link}; confirmed deliveries remain saved")
            await rollback_message_delivery(bot, app, message.chat.id, message.id)
            Config.TRANSFERS.pop(download_id, None)
            await update_transfer(
                download_id,
                link_index=i - 1,
                status=TransferStatus.SLEEPING.value,
            )
            markup = types.InlineKeyboardMarkup(
                [
                    [
                        types.InlineKeyboardButton(
                            "▶️ Resume this link",
                            callback_data=f"resume_transfers {download_id}",
                        )
                    ]
                ]
            )
            await bot.floodwait_handler(
                bot.send_message,
                user_id,
                f"⏹️ Stopped on link {i}/{len(links)}. Confirmed copies preserved — resume to finish this message.",
                reply_markup=markup,
            )
            break
        except Exception as e:
            failed += 1
            tg_fail += 1
            logging.exception(f"Pipeline failed for {message.link}: {e}")
            job_lines.append(f"📤 TG `{message.chat.id}:{message.id}` ❌ {e}")
            await bot.floodwait_handler(
                bot.send_message, user_id, f"Save error: {e}: {message.link}"
            )

        if is_transfer_cancelled(download_id):
            await rollback_message_delivery(bot, app, message.chat.id, message.id)
            Config.TRANSFERS.pop(download_id, None)
            await update_transfer(
                download_id,
                link_index=i - 1,
                status=TransferStatus.SLEEPING.value,
            )
            await bot.floodwait_handler(
                bot.send_message,
                user_id,
                f"⏹️ Stopped on link {i}/{len(links)}. Resume to retry this message.",
                reply_markup=types.InlineKeyboardMarkup(
                    [
                        [
                            types.InlineKeyboardButton(
                                "▶️ Resume this link",
                                callback_data=f"resume_transfers {download_id}",
                            )
                        ]
                    ]
                ),
            )
            break

        success += 1

        if Config.SLEEP_TIME > 0:
            if await interruptible_sleep(Config.SLEEP_TIME, should_abort_link):
                await rollback_message_delivery(bot, app, message.chat.id, message.id)
                Config.TRANSFERS.pop(download_id, None)
                await update_transfer(
                    download_id,
                    link_index=i - 1,
                    status=TransferStatus.SLEEPING.value,
                )
                await bot.floodwait_handler(
                    bot.send_message,
                    user_id,
                    f"⏹️ Stopped during wait on link {i}/{len(links)}.",
                    reply_markup=types.InlineKeyboardMarkup(
                        [
                            [
                                types.InlineKeyboardButton(
                                    "▶️ Resume",
                                    callback_data=f"resume_transfers {download_id}",
                                )
                            ]
                        ]
                    ),
                )
                break

        await remove_transfer_from_queue(download_id)

    await out.delete()

    reply_text = (
        f"Processed {i} of {len(links)} links\n"
        f"Links OK: {success} | Failed: {failed}\n"
        f"Not allowed types: {not_allowed} | Deleted/empty: {deleted}\n\n"
        f"📤 **Telegram:** ✅ `{tg_ok}` | ⏭️ `{tg_skip}` | ❌ `{tg_fail}`\n"
    )
    if notion_indexing_enabled() and notion_enabled:
        reply_text += (
            f"🌐 **Notion:**     ✅ `{notion_ok}` | ⏭️ `{notion_skip}` | ❌ `{notion_fail}`\n"
        )
    if job_lines:
        sample = job_lines[-6:]
        reply_text += "\n**Last jobs:**\n" + "\n".join(sample)
    reply_text += f"\n\nLast link: {link}"
    await bot.floodwait_handler(
        bot.send_message,
        user_id,
        reply_text,
    )
