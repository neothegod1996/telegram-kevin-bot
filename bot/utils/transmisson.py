"""Backward-compatible alias (typo preserved). Use bot.utils.transmission."""

from bot.utils.media_message import get_file_name
from bot.utils.transmission import (
    add_transfer_to_queue,
    create_topic_if_not_exists,
    download_media,
    forward_message,
    get_source_topics,
    get_target_topics,
    get_topics_by_chat_id,
    handle_topic_thread,
    remove_transfer_from_queue,
    resume_transfers,
    update_transfer,
    upload_media,
)

__all__ = [
    "forward_message",
    "download_media",
    "upload_media",
    "add_transfer_to_queue",
    "remove_transfer_from_queue",
    "update_transfer",
    "resume_transfers",
    "get_file_name",
    "handle_topic_thread",
    "create_topic_if_not_exists",
    "get_topics_by_chat_id",
    "get_source_topics",
    "get_target_topics",
]