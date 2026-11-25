import asyncio
import logging
import os
import random

from pyrogram import Client

from bot.backup.rollback import rollback_message_delivery
from bot.backup.task_control import ControlCommand, WorkerPhase, interruptible_sleep
from bot.config import Config
from bot.enums import TransferStatus
from bot.exceptions import CancelledError
from bot.utils.transfer_cancel import is_transfer_cancelled
from bot.utils.media_type import get_media_type
from bot.utils.transmission import forward_message
from bot.utils.user_session import get_user_client
from database import db

logger = logging.getLogger(__name__)

RUNNING_TASKS: set[int] = set()


async def safe_status_message(bot: Client, user_id: int, text: str) -> None:
    """Failure to notify the operator must never change a successful batch into failed."""
    try:
        await bot.send_message(user_id, text)
    except Exception as exc:
        logger.warning("Could not notify user %s about batch status: %s", user_id, exc)


async def start_background_batch(bot: Client, user_id: int, task_id: int):
    if task_id in RUNNING_TASKS:
        return
    RUNNING_TASKS.add(task_id)
    asyncio.create_task(process_batch_task(bot, user_id, task_id))


async def load_task_context(task_id: int, user_id: int):
    app = await get_user_client(user_id)
    if not app:
        await db.batch_tasks.update_status(task_id, "failed")
        return None, None
    task = await db.batch_tasks.read(task_id)
    return app, task


async def batch_should_halt(task_id: int) -> tuple[bool, str | None]:
    task = await db.batch_tasks.read(task_id)
    if not task:
        return True, "missing"
    control = task.get("control")
    status = task.get("status")
    if control in (ControlCommand.CANCEL.value, ControlCommand.STOP.value):
        return True, "cancel"
    if control == ControlCommand.PAUSE.value:
        return True, "pause"
    if status in ("stopped", "paused", "completed", "failed"):
        return True, status
    return False, None


async def process_message_item(
    bot: Client,
    app: Client,
    chat_id: int,
    message_id: int,
    user_id: int,
    notion_enabled: bool,
    *,
    source_topic_id: int | None = None,
    task_id: int | None = None,
) -> tuple[bool | None, bool]:
    from bot.utils.notion_settings import notion_enabled_for_user

    notion_enabled = notion_enabled_for_user(user_id, notion_enabled)
    try:
        message = await app.get_messages(chat_id, message_id)
    except Exception as e:
        logger.warning("Cannot read %s:%s; leave checkpoint unchanged: %s", chat_id, message_id, e)
        return None, False

    if not message or message.empty or message.sticker or message.service:
        return False, False

    from bot.backup.routes import message_in_topic

    if not message_in_topic(message, source_topic_id):
        return False, False

    from bot.backup.telegram_delivery import (
        build_delivery_ledger_for_user,
        get_delivery_destinations,
    )

    ledger = await build_delivery_ledger_for_user(user_id)
    routes = await get_delivery_destinations(bot, user_id, chat_id, db=db, app=app)
    dest_ids = [r.destination_channel_id for r in routes]
    telegram_done = await ledger.all_destinations_confirmed(chat_id, message_id, dest_ids)
    if telegram_done and not notion_enabled:
        logger.debug("Message %s:%s already fully backed up — skipping", chat_id, message_id)
        return True, False

    allowed_media = await get_media_type()
    if message.media and message.media.value not in allowed_media:
        return False, False
    if message.text and "text" not in allowed_media:
        return False, False

    download_id = random.randint(100000, 999999)
    message.download_id = download_id
    message.index = f"{message_id}"
    Config.TRANSFERS[download_id] = {
        "user_id": user_id,
        "status": TransferStatus.IN_PROGRESS.value,
    }

    async def should_abort() -> bool:
        if is_transfer_cancelled(download_id):
            return True
        if task_id is not None:
            halt, _ = await batch_should_halt(task_id)
            return halt
        return False

    def _tg_bucket(status: str) -> str:
        if status == "succeeded":
            return "succeeded"
        if status == "skipped":
            return "skipped"
        return "failed"

    try:
        try:
            fwd = await forward_message(
                bot,
                app,
                message,
                user_id,
                retain_download_path=notion_enabled and bool(message.media),
                should_abort=should_abort,
            )
        except CancelledError:
            await rollback_message_delivery(bot, app, chat_id, message_id)
            raise
        tg = fwd.telegram
        tid = task_id
        if tid is None:
            active = await db.batch_tasks.get_active_task(user_id)
            tid = active["_id"] if active else None
        if tid is not None:
            await db.batch_tasks.append_telegram_result(
                tid,
                _tg_bucket(tg.status),
                {
                    "source_message_id": tg.source_message_id,
                    "source_chat_id": tg.source_chat_id,
                    "error": tg.error,
                    "failed_destinations": tg.failed_destinations,
                },
            )
        # Avoid expensive optional uploads when Telegram has missing destinations.
        if tg.status not in ("succeeded", "skipped"):
            if fwd.retained_path and os.path.exists(fwd.retained_path):
                try:
                    os.remove(fwd.retained_path)
                except OSError:
                    pass
            logger.warning("Unconfirmed Telegram destination(s) for %s:%s", chat_id, message_id)
            return None, False
        if notion_enabled:
            if await should_abort():
                await rollback_message_delivery(bot, app, chat_id, message_id)
                raise CancelledError
            from bot.backup.notion_backup import backup_message_to_notion

            try:
                notion_report = await backup_message_to_notion(
                    bot,
                    app,
                    message,
                    user_id,
                    file_path=fwd.retained_path,
                    should_abort=should_abort,
                )
            except CancelledError:
                if fwd.retained_path and os.path.exists(fwd.retained_path):
                    try:
                        os.remove(fwd.retained_path)
                    except OSError:
                        pass
                await rollback_message_delivery(bot, app, chat_id, message_id)
                raise
            if fwd.retained_path and os.path.exists(fwd.retained_path):
                try:
                    os.remove(fwd.retained_path)
                except OSError:
                    pass
            if await should_abort():
                await rollback_message_delivery(bot, app, chat_id, message_id)
                raise CancelledError
            if tid is not None:
                nb = (
                    notion_report.status
                    if notion_report.status in ("failed", "skipped", "succeeded")
                    else "failed"
                )
                await db.batch_tasks.append_notion_result(
                    tid,
                    nb,
                    {
                        "source_message_id": notion_report.source_message_id,
                        "source_chat_id": notion_report.source_chat_id,
                        "file_id": notion_report.file_id,
                        "error": notion_report.error,
                    },
                )
        # A partial or failed Telegram delivery is NOT an acknowledged message.
        # Keep the checkpoint on this message so the ledger can retry only missing routes.
        if notion_enabled and notion_report.status == "failed":
            logger.warning("Notion failed for %s:%s; do not advance", chat_id, message_id)
            return None, False
        return True, True
    except CancelledError:
        logger.info("Batch item %s:%s interrupted; confirmed copies are retained", chat_id, message_id)
        raise
    except Exception:
        logger.exception("Batch save failed for %s:%s; checkpoint unchanged", chat_id, message_id)
        return None, False
    finally:
        Config.TRANSFERS.pop(download_id, None)


async def run_batch_loop(
    bot: Client, app: Client, task: dict, task_id: int, user_id: int
) -> int:
    start_id = task["current_message_id"]
    end_id = task["last_message_id"]
    chat_id = task["source_chat_id"]
    from bot.utils.notion_settings import notion_enabled_for_user

    notion = notion_enabled_for_user(user_id, task.get("notion_enabled", False))
    count = task.get("processed_count", 0)

    async def should_stop() -> bool:
        halt, _ = await batch_should_halt(task_id)
        return halt

    for msg_id in range(start_id, end_id + 1):
        halt, reason = await batch_should_halt(task_id)
        if halt and reason in (
            "cancel",
            "stopped",
            "paused",
            "pause",
            "failed",
            "completed",
            "missing",
        ):
            if reason == "pause":
                await db.batch_tasks.set_control(
                    task_id, ControlCommand.PAUSE.value, worker_phase=WorkerPhase.DRAINING.value
                )
            break

        # Do NOT write stale task["control"] here: that could erase a pause/cancel
        # set concurrently by a callback immediately before this worker step.
        await db.batch_tasks.set_worker_state(
            task_id, worker_phase=WorkerPhase.PROCESSING.value, worker_message_id=msg_id
        )
        try:
            counted, throttle = await process_message_item(
                bot,
                app,
                chat_id,
                msg_id,
                user_id,
                notion,
                source_topic_id=task.get("source_topic_id"),
                task_id=task_id,
            )
        except CancelledError:
            await db.batch_tasks.update_progress(task_id, msg_id, count)
            break
        if counted is None:
            # An API failure, partial delivery or Notion failure is recoverable.
            # Do not skip it, even if other destinations were already confirmed.
            await db.batch_tasks.update_status(task_id, "paused", count)
            await db.batch_tasks.set_worker_state(task_id, worker_phase=WorkerPhase.PAUSED.value)
            await db.batch_tasks.update(
                task_id,
                {"retry_message_id": msg_id, "last_error": "Delivery/read failed; resume to retry"},
            )
            logger.warning("Paused task %s at retryable message %s", task_id, msg_id)
            break
        if counted:
            await db.batch_tasks.resolve_message_failures(task_id, chat_id, msg_id)
            count += 1
        await db.batch_tasks.update_progress(task_id, msg_id + 1, count)
        if task.get("retry_message_id") == msg_id:
            await db.batch_tasks.update(task_id, {"retry_message_id": None, "last_error": None})

        halt, reason = await batch_should_halt(task_id)
        if halt:
            break
        if throttle and Config.BATCH_SLEEP_TIME > 0:
            await interruptible_sleep(Config.BATCH_SLEEP_TIME, should_stop)
    return count


async def complete_or_pause_task(
    bot: Client, task_id: int, user_id: int, processed_count: int
):
    task = await db.batch_tasks.read(task_id)
    if not task or task.get("status") != "running":
        return
    control = task.get("control")
    if control in (ControlCommand.CANCEL.value, ControlCommand.STOP.value):
        await db.batch_tasks.update_status(task_id, "stopped", processed_count)
        await db.batch_tasks.clear_control(task_id, worker_phase=WorkerPhase.STOPPED.value)
        await safe_status_message(
            bot, user_id, f"⏹️ Batch task #{task_id} stopped. Saved {processed_count} messages."
        )
        return
    if control == ControlCommand.PAUSE.value or task["current_message_id"] <= task["last_message_id"]:
        await db.batch_tasks.update_status(task_id, "paused", processed_count)
        await db.batch_tasks.clear_control(task_id, worker_phase=WorkerPhase.PAUSED.value)
        await safe_status_message(
            bot, user_id,
            f"⏸️ Batch task #{task_id} paused at message {task['current_message_id']}. "
            "Worker is idle; use Resume to continue.",
        )
        return
    if task["current_message_id"] > task["last_message_id"]:
        await db.batch_tasks.update_status(task_id, "completed", processed_count)
        await db.batch_tasks.clear_control(task_id, worker_phase=WorkerPhase.IDLE.value)
        await safe_status_message(
            bot, user_id, f"✅ Batch task #{task_id} completed. Processed {processed_count} messages."
        )


async def process_batch_task(bot: Client, user_id: int, task_id: int):
    try:
        app, task = await load_task_context(task_id, user_id)
        if not app or not task:
            return
        processed_count = await run_batch_loop(bot, app, task, task_id, user_id)
        current_task = await db.batch_tasks.read(task_id)
        if current_task and current_task.get("status") == "paused" and current_task.get("retry_message_id") is not None:
            await safe_status_message(
                bot, user_id,
                f"⚠️ Batch #{task_id} paused on message "
                f"{current_task['retry_message_id']} after a recoverable failure. "
                "Confirmed copies were kept. Fix the cause and Resume to retry this message.",
            )
        await complete_or_pause_task(bot, task_id, user_id, processed_count)
    except Exception:
        logger.exception("Unexpected error in batch task %s", task_id)
        await db.batch_tasks.update_status(task_id, "failed")
    finally:
        RUNNING_TASKS.discard(task_id)


async def check_task_active(task_id: int) -> bool:
    task = await db.batch_tasks.read(task_id)
    return task is not None and task.get("status") == "running"