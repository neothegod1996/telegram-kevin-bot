"""Notion backup jobs independent from Telegram delivery."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Optional

from pyrogram import Client, types

from bot.utils.archive_handler import is_archive
from bot.utils.notion import NotionUploadError, upload_archive_to_notion, upload_message_to_notion
from bot.utils.notion_settings import notion_indexing_enabled, user_may_use_notion
from bot.utils.transmisson import download_media
from database import db

logger = logging.getLogger(__name__)


@dataclass
class NotionJobReport:
    source_chat_id: int
    source_message_id: int
    status: str
    file_id: str | None = None
    error: str | None = None


@dataclass
class NotionBatchSummary:
    succeeded: list[NotionJobReport] = field(default_factory=list)
    failed: list[NotionJobReport] = field(default_factory=list)
    skipped: list[NotionJobReport] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            "🌐 **Notion backup summary**",
            f"✅ attached: `{len(self.succeeded)}`",
            f"⏭️ skipped: `{len(self.skipped)}`",
            f"❌ failed: `{len(self.failed)}`",
        ]
        for item in self.failed[:5]:
            lines.append(f"• `{item.source_chat_id}:{item.source_message_id}` — {item.error}")
        for item in self.skipped[:5]:
            lines.append(f"• `{item.source_chat_id}:{item.source_message_id}` — {item.error}")
        return "\n".join(lines)


def format_notion_line(report: NotionJobReport) -> str:
    ref = f"`{report.source_chat_id}:{report.source_message_id}`"
    if report.status == "succeeded":
        return f"🌐 Notion {ref} ✅"
    if report.status == "skipped":
        reason = report.error or "skipped"
        return f"🌐 Notion {ref} ⏭️ {reason}"
    reason = report.error or "failed"
    return f"🌐 Notion {ref} ❌ {reason[:80]}"


async def backup_message_to_notion(
    bot: Client,
    app: Client,
    message: types.Message,
    user_id: int,
    *,
    file_path: str | None = None,
    should_abort: Optional[Callable[[], Awaitable[bool]]] = None,
    index_after_upload: bool = True,
) -> NotionJobReport:
    """Download (if needed), upload file to Notion, persist metadata, optionally index page."""

    async def aborted() -> bool:
        return bool(should_abort and await should_abort())

    report = NotionJobReport(message.chat.id, message.id, "pending")
    if not user_may_use_notion(user_id) or not notion_indexing_enabled():
        report.status = "skipped"
        report.error = "not_allowed"
        return report
    if message.text and not message.media:
        report.status = "skipped"
        report.error = "text_only"
        return report
    if not message.media:
        report.status = "skipped"
        report.error = "no_media"
        return report

    owns_file = False
    progress = None
    notion_file_id: str | None = None
    archive_metadata = None

    try:
        if await aborted():
            report.status = "skipped"
            report.error = "aborted"
            return report
        if not file_path:
            progress = await bot.send_message(user_id, f"🌐 Notion: fetching {message.id}...")
            file_path = await download_media(
                bot, user_id, message, progress, should_abort=should_abort
            )
            owns_file = True
        if await aborted():
            report.status = "skipped"
            report.error = "aborted"
            return report
        if not file_path:
            report.status = "failed"
            report.error = "download_failed"
            return report

        if is_archive(file_path):
            # Notion archive extraction can consume many times the compressed size.
            # Keep it off until explicitly enabled, and enforce resource limits.
            if os.environ.get("NOTION_EXTRACT_ARCHIVES", "false").lower() not in ("true", "1", "yes"):
                report.status = "skipped"
                report.error = "archive_extraction_disabled"
                return report
            archive_result = await asyncio.to_thread(upload_archive_to_notion, file_path)
            if archive_result and archive_result.file_ids:
                notion_file_id = archive_result.file_ids[0]
                archive_metadata = {
                    "file_ids": archive_result.file_ids,
                    "file_names": archive_result.file_names,
                    "archive_name": archive_result.archive_name,
                    "total_files": archive_result.total_files,
                }
            else:
                report.status = "failed"
                report.error = "archive_upload_empty"
                return report
        else:
            result = await asyncio.to_thread(upload_message_to_notion, message, file_path)
            if await aborted():
                report.status = "skipped"
                report.error = "aborted"
                return report
            if result and result.file_id:
                notion_file_id = result.file_id
            else:
                report.status = "failed"
                report.error = "upload_empty"
                return report

        await db.messages.get_or_update_from_pyrogram(
            message,
            file_id=notion_file_id,
            archive_files=archive_metadata,
        )
        report.status = "succeeded"
        report.file_id = notion_file_id

        if index_after_upload:
            from bot.utils.notion_indexer import index_messages_to_notion

            try:
                await index_messages_to_notion(user_id=user_id)
            except Exception as exc:
                logger.error("Notion page indexing failed after upload: %s", exc)
                report.error = "indexed_page_failed"
    except NotionUploadError as exc:
        report.status = "failed"
        report.error = str(exc)[:120]
    except Exception as exc:
        logger.exception("Notion backup failed for %s", message.id)
        report.status = "failed"
        report.error = exc.__class__.__name__
    finally:
        if owns_file and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        if progress:
            try:
                await progress.delete()
            except Exception:
                pass

    return report