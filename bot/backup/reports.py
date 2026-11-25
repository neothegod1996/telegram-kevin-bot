"""Per-job status reports for Telegram delivery and Notion backup."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TelegramMessageReport:
    source_chat_id: int
    source_message_id: int
    status: str
    error: str | None = None
    failed_destinations: list[int] = field(default_factory=list)
    skipped_destinations: int = 0


@dataclass
class ForwardResult:
    """Result of a Telegram-only forward/save job."""

    telegram: TelegramMessageReport
    retained_path: str | None = None


def format_telegram_line(report: TelegramMessageReport) -> str:
    ref = f"`{report.source_chat_id}:{report.source_message_id}`"
    if report.status == "succeeded":
        return f"📤 TG {ref} ✅"
    if report.status == "skipped":
        reason = report.error or "skipped"
        return f"📤 TG {ref} ⏭️ {reason}"
    if report.status == "partial":
        dests = ", ".join(str(d) for d in report.failed_destinations[:3])
        return f"📤 TG {ref} ⚠️ partial (failed: {dests})"
    reason = report.error or "failed"
    return f"📤 TG {ref} ❌ {reason}"