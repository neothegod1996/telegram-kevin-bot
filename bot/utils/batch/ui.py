from datetime import datetime

from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.backup.task_control import WorkerPhase, control_status_line


def make_batch_menu(notion_enabled: bool) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "📦 **Batch Transfer Manager**\n\n"
        "This tool allows you to copy messages from channels or groups in bulk.\n\n"
        "**Button Guide**:\n"
        "- **Custom Batch**: Start a new copying task by specifying the start and end message links.\n\n"
        "- **Sync Last Indexed**: Automatically scan and copy new messages from previously processed chats.\n\n"
        "- **Active Task**: View status and manage the currently running copy task.\n\n"
        "- **All Tasks**: View full task history to resume paused copy tasks or delete records.\n\n"
        "Choose an action below:"
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Custom Batch", callback_data=f"bmenu_new_{notion_enabled}"),
                InlineKeyboardButton("🔄 Sync Last Indexed", callback_data=f"bmenu_sync_{notion_enabled}"),
            ],
            [InlineKeyboardButton("⚡ Active Task", callback_data="bmenu_active")],
            [InlineKeyboardButton("📜 All Tasks", callback_data="bmenu_completed")],
            [InlineKeyboardButton("🔙 Back", callback_data="start")],
        ]
    )
    return text, markup


def abbreviate_timezone(tz_name: str) -> str:
    if not tz_name:
        return ""
    mappings = {
        "india standard time": "IST",
        "coordinated universal time": "UTC",
        "greenwich mean time": "GMT",
        "eastern standard time": "EST",
        "eastern daylight time": "EDT",
        "central standard time": "CST",
        "central daylight time": "CDT",
        "mountain standard time": "MST",
        "mountain daylight time": "MDT",
        "pacific standard time": "PST",
        "pacific daylight time": "PDT",
    }
    mapped = mappings.get(tz_name.lower())
    if mapped:
        return mapped
    if len(tz_name) <= 5 and tz_name.isupper():
        return tz_name
    abbrev = "".join(char for char in tz_name if char.isupper())
    return abbrev if abbrev else tz_name


def format_time_and_duration(created_at) -> tuple[str, str]:
    if not created_at:
        return "Unknown", "N/A"
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except Exception:
            return str(created_at), "N/A"
    if created_at.tzinfo is None:
        created_at = created_at.astimezone()
    raw_tz = created_at.strftime("%Z")
    if not raw_tz:
        tz_offset = created_at.strftime("%z")
        raw_tz = f"{tz_offset[:3]}:{tz_offset[3:]}" if len(tz_offset) == 5 else tz_offset
    tz_name = abbreviate_timezone(raw_tz)
    started_str = created_at.strftime("%d %b %y, %H:%M")
    if tz_name:
        started_str += f" {tz_name}"

    diff_sec = int((datetime.now().astimezone() - created_at).total_seconds())
    if diff_sec < 60:
        return started_str, "just now"
    if diff_sec < 3600:
        return started_str, f"{diff_sec // 60}m ago"
    if diff_sec < 86400:
        return started_str, f"{diff_sec // 3600}h {(diff_sec % 3600) // 60}m ago"
    return started_str, f"{diff_sec // 86400}d {(diff_sec % 86400) // 3600}h ago"


def format_task_text(task: dict) -> str:
    scanned_count = (
        (task["current_message_id"] - task["first_message_id"])
        if task["status"] != "completed"
        else task["total_messages"]
    )
    scanned_count = max(0, min(scanned_count, task["total_messages"]))
    pct = (scanned_count / task["total_messages"]) * 100 if task["total_messages"] > 0 else 0
    left_count = max(0, task["total_messages"] - scanned_count)
    chat_id = task["source_chat_id"]
    chat_title = task.get("source_chat_title", "Chat")
    chat_id_raw = str(chat_id).replace("-100", "")
    msg_link = f"https://t.me/c/{chat_id_raw}/{task['current_message_id']}"
    last_msg_link = f"https://t.me/c/{chat_id_raw}/{task['last_message_id']}"
    started_at, running_since = format_time_and_duration(task.get("created_at"))

    status_emoji = {
        "running": "⚡ RUNNING",
        "completed": "✅ COMPLETED",
        "paused": "⏸️ PAUSED",
        "stopped": "⏹️ STOPPED",
        "failed": "❌ FAILED",
    }.get(task["status"].lower(), task["status"].upper())

    notion_tag = " (🌐 Notion)" if task.get("notion_enabled", False) else ""
    topic_tag = ""
    if task.get("source_topic_id") is not None:
        topic_tag = f" | 🎯 topic `{task['source_topic_id']}`"
    if task.get("priority_pass"):
        topic_tag += " (priority)"

    control_line = control_status_line(task.get("control"), task.get("worker_phase"))
    retry_line = f"⚠️ **Retry pending at message** `{task['retry_message_id']}`\n" if task.get("retry_message_id") is not None else ""
    worker_line = ""
    if task.get("worker_message_id") and task.get("worker_phase") == WorkerPhase.PROCESSING.value:
        worker_line = f"**Current message id**: `{task['worker_message_id']}`\n"

    text = (
        f"📦 **Task #{task['_id']}** | {status_emoji}{notion_tag}{topic_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "This card shows the progress of your copy task. Use the control buttons below to manage it.\n\n"
    )
    if control_line:
        text += f"{control_line}\n\n"
    text += (
        f"**Chat**: {chat_title}\n"
        f"{worker_line}"
        f"{retry_line}"
        f"**Progress**: `{scanned_count}`/`{task['total_messages']}` (`{pct:.1f}%` - `{left_count}` left)\n"
        f"**Saved**: `{task['processed_count']}` messages\n"
        f"**Telegram**: ✅ `{len(task.get('telegram_succeeded', []))}` | "
        f"⏭️ `{len(task.get('telegram_skipped', []))}` | "
        f"❌ `{len(task.get('telegram_failed', []))}`\n"
        f"**Notion**: ✅ `{len(task.get('notion_succeeded', []))}` | "
        f"⏭️ `{len(task.get('notion_skipped', []))}` | "
        f"❌ `{len(task.get('notion_failed', []))}`\n"
        f"**Started**: {started_at} ({running_since})\n"
        f"**Links**: [Current]({msg_link}) | [Last]({last_msg_link})\n\n"
        "ℹ️ __Empty, deleted, or unsupported messages in the range are skipped.__"
    )
    return text


def make_task_markup(task: dict) -> InlineKeyboardMarkup:
    buttons = []
    if task["status"] == "running":
        buttons.append(InlineKeyboardButton("⏸️ Pause", callback_data=f"b_pause_{task['_id']}"))
        buttons.append(InlineKeyboardButton("⏹️ Stop/Cancel", callback_data=f"b_cancel_{task['_id']}"))
    elif task["status"] in ["paused", "failed"]:
        buttons.append(InlineKeyboardButton("▶️ Resume", callback_data=f"b_resume_{task['_id']}"))
        buttons.append(InlineKeyboardButton("❌ Delete", callback_data=f"b_delete_{task['_id']}"))
    else:
        buttons.append(InlineKeyboardButton("❌ Delete", callback_data=f"b_delete_{task['_id']}"))
    notion = task.get("notion_enabled", False)
    return InlineKeyboardMarkup(
        [
            buttons,
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"b_refresh_{task['_id']}")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data=f"bmenu_home_{notion}")],
        ]
    )


def get_condensed_completed_text(tasks: list) -> str:
    text = (
        "📜 **Completed & Inactive Tasks**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Here is the history of your past copy tasks. Click any task ID button below to view its details, resume a paused copy, or delete it from history.\n\n"
    )
    completed_tasks = [t for t in tasks if t["status"] != "running"]
    if not completed_tasks:
        return text + "No completed or inactive tasks found."
    for task in completed_tasks[:10]:
        title = task.get("source_chat_title", "Chat")
        saved = task.get("processed_count", 0)
        scanned = task.get("total_messages", 0)
        status_tag = {
            "completed": "✅ COMPLETED",
            "paused": "⏸️ PAUSED",
            "stopped": "⏹️ STOPPED",
            "failed": "❌ FAILED",
        }.get(task["status"].lower(), task["status"].upper())
        started_at = "Unknown"
        if task.get("created_at"):
            created_at = task["created_at"]
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at)
                except Exception:
                    pass
            if not isinstance(created_at, str):
                started_at = created_at.strftime("%d-%m-%Y %H:%M")
        text += (
            f"• **Task #{task['_id']}** | {status_tag}\n"
            f"  **Chat**: {title}\n"
            f"  Progress: `{scanned}/{scanned}` | Saved: `{saved}` | `{started_at}`\n\n"
        )
    return text.strip()


async def show_active_task(bot: Client, chat_id: int, user_id: int, query=None):
    from database import db

    task = await db.batch_tasks.get_active_task(user_id)
    if not task:
        text = (
            "⚠️ **No active task currently running.**\n\n"
            "Active tasks are bulk copy processes that are currently in progress. "
            "You can start a new bulk copy via the main menu."
        )
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back to Menu", callback_data="bmenu_home_False")]]
        )
        if query:
            await query.message.edit_text(text, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, reply_markup=markup)
        return
    text = format_task_text(task)
    markup = make_task_markup(task)
    if query:
        await query.message.edit_text(text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, reply_markup=markup)


async def show_completed_tasks(bot: Client, chat_id: int, user_id: int, query=None):
    from database import db

    tasks = await db.batch_tasks.get_user_tasks(user_id)
    completed_tasks = [t for t in tasks if t["status"] != "running"]
    text = get_condensed_completed_text(tasks)
    buttons = []
    current_row = []
    for task in completed_tasks[:10]:
        task_id = task["_id"]
        current_row.append(InlineKeyboardButton(f"#{task_id}", callback_data=f"b_view_{task_id}"))
        if len(current_row) == 3:
            buttons.append(current_row)
            current_row = []
    if current_row:
        buttons.append(current_row)
    buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="bmenu_home_False")])
    markup = InlineKeyboardMarkup(buttons)
    if query:
        await query.message.edit_text(text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, reply_markup=markup)