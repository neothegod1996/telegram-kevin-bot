"""Recover interrupted tasks safely after a server restart.

A running task from a previous process is no longer running. Always mark it
paused so the operator may resume it, regardless of auto-resume configuration.
By default, do NOT start network transfers automatically on boot.
"""

import logging

from pyrogram import Client

from bot.backup.task_control import WorkerPhase
from bot.config import Config
from database import db

logger = logging.getLogger(__name__)


async def resume_interrupted_batches(bot: Client) -> int:
    interrupted = await db.batch_tasks.filter_documents({"status": "running"})
    if not interrupted:
        return 0

    if Config.BATCH_AUTO_RESUME_ON_START:
        from bot.utils.batch.worker import start_background_batch

    resumed = 0
    for task in interrupted:
        task_id = task["_id"]
        user_id = task["user_id"]
        # A stale 'running' value would make the UI refuse a manual Resume.
        await db.batch_tasks.update_status(task_id, "paused")
        await db.batch_tasks.clear_control(
            task_id, worker_phase=WorkerPhase.PAUSED.value
        )
        if Config.BATCH_AUTO_RESUME_ON_START:
            await db.batch_tasks.update_status(task_id, "running")
            await db.batch_tasks.clear_control(
                task_id, worker_phase=WorkerPhase.PROCESSING.value
            )
            await start_background_batch(bot, user_id, task_id)
            resumed += 1
        try:
            action = "automatically resumed" if Config.BATCH_AUTO_RESUME_ON_START else "paused for manual Resume"
            await bot.send_message(
                user_id,
                f"🔄 Bot restarted — batch task #{task_id} {action} at message "
                f"{task.get('current_message_id', '?')}. Confirmed copies remain recorded.",
            )
        except Exception as exc:
            logger.debug("Could not notify user %s about batch recovery: %s", user_id, exc)

    logger.info("Recovered %s stale task(s); auto-resumed %s", len(interrupted), resumed)
    return resumed
