"""Backward-compatible re-exports. Prefer bot.utils.batch."""

from bot.utils.batch import (
    check_task_active,
    create_and_run_task,
    format_task_text,
    get_condensed_completed_text,
    get_latest_message_id,
    make_batch_menu,
    make_task_markup,
    process_batch_task,
    process_message_item,
    resolve_chat_id,
    resolve_link_chat_id,
    setup_custom_task,
    setup_sync_task,
    show_active_task,
    show_completed_tasks,
    start_background_batch,
)
from bot.utils.batch.worker import RUNNING_TASKS, run_batch_loop
from bot.utils.transfer_cancel import is_input_cancelled

__all__ = [
    "RUNNING_TASKS",
    "make_batch_menu",
    "format_task_text",
    "make_task_markup",
    "show_active_task",
    "show_completed_tasks",
    "get_condensed_completed_text",
    "resolve_link_chat_id",
    "resolve_chat_id",
    "get_latest_message_id",
    "create_and_run_task",
    "setup_custom_task",
    "setup_sync_task",
    "start_background_batch",
    "process_message_item",
    "process_batch_task",
    "check_task_active",
    "run_batch_loop",
    "is_input_cancelled",
]