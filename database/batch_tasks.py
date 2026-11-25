from datetime import datetime
from typing import Optional
from database.core import Core


class BatchTasksDB(Core):
    """Database class for managing batch progress and tasks"""

    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "batch_tasks")

    async def create_task(self, doc_data: dict) -> int:
        """Create a new batch task in the database"""
        doc = {
            "_id": doc_data["task_id"],
            "user_id": int(doc_data["user_id"]),
            "source_chat_id": int(doc_data["source_chat_id"]),
            "source_chat_title": doc_data.get("source_chat_title", "Chat"),
            "first_message_id": int(doc_data["first_message_id"]),
            "last_message_id": int(doc_data["last_message_id"]),
            "current_message_id": int(doc_data["first_message_id"]),
            "total_messages": int(doc_data["total_messages"]),
            "processed_count": 0,
            "status": "running",
            "notion_enabled": bool(doc_data.get("notion_enabled", False)),
            "source_topic_id": doc_data.get("source_topic_id"),
            "priority_pass": bool(doc_data.get("priority_pass", False)),
            "notion_failed": [],
            "notion_skipped": [],
            "notion_succeeded": [],
            "telegram_failed": [],
            "telegram_skipped": [],
            "telegram_succeeded": [],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        return await super().create(doc)

    async def update_progress(self, task_id: int, current_message_id: int, processed_count: int):
        """Update current message and processed count of a task"""
        update_data = {
            "current_message_id": current_message_id,
            "processed_count": processed_count,
            "updated_at": datetime.now(),
        }
        return await super().update(task_id, update_data)

    async def set_control(
        self,
        task_id: int,
        control: str | None,
        *,
        worker_phase: str | None = None,
        worker_message_id: int | None = None,
    ):
        """Persist pause/cancel immediately (independent of worker loop)."""
        update_data = {
            "control": control,
            "control_updated_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        if worker_phase is not None:
            update_data["worker_phase"] = worker_phase
        if worker_message_id is not None:
            update_data["worker_message_id"] = worker_message_id
        return await super().update(task_id, update_data)

    async def set_worker_state(
        self, task_id: int, *, worker_phase: str, worker_message_id: int | None = None
    ):
        """Set progress display fields without overwriting a concurrent pause/cancel."""
        payload = {"worker_phase": worker_phase, "updated_at": datetime.now()}
        if worker_message_id is not None:
            payload["worker_message_id"] = worker_message_id
        return await super().update(task_id, payload)

    async def clear_control(self, task_id: int, worker_phase: str | None = None):
        payload = {
            "control": None,
            "updated_at": datetime.now(),
        }
        if worker_phase is not None:
            payload["worker_phase"] = worker_phase
        return await super().update(task_id, payload)

    async def update_status(self, task_id: int, status: str, processed_count: int = None):
        """Update status and optionally processed count of the task"""
        update_data = {
            "status": status,
            "updated_at": datetime.now(),
        }
        if processed_count is not None:
            update_data["processed_count"] = int(processed_count)
        return await super().update(task_id, update_data)

    async def get_user_tasks(self, user_id: int, status: str = None) -> list:
        """Get all batch tasks for a specific user"""
        query = {"user_id": int(user_id)}
        if status:
            query["status"] = status
        return await super().filter_documents(query, sort=[("created_at", -1)])

    async def get_active_task(self, user_id: int) -> dict:
        """Get the currently active (running) task for a user"""
        query = {"user_id": int(user_id), "status": "running"}
        return await super().filter_document(query)

    async def get_distinct_chats(self) -> list[dict]:
        """
        Get all distinct source chats (source_chat_id and source_chat_title) from batch tasks.
        
        Returns:
            List of dicts containing 'chat_id' and 'channel_name'
        """
        pipeline = [
            {
                "$group": {
                    "_id": "$source_chat_id",
                    "channel_name": {"$first": "$source_chat_title"}
                }
            },
            {
                "$project": {
                    "chat_id": "$_id",
                    "channel_name": 1,
                    "_id": 0
                }
            }
        ]
        cursor = self.col.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def resolve_message_failures(
        self, task_id: int, source_chat_id: int, source_message_id: int
    ):
        """Remove stale failure reports when the same message later succeeds.

        Keep failures for every other message; otherwise Sync could incorrectly
        consider an incompletely copied batch a clean baseline.
        """
        task = await self.read(task_id)
        if not task:
            return
        for key in ("telegram_failed", "notion_failed"):
            old = list(task.get(key, []))
            remaining = [
                item for item in old
                if not (
                    int(item.get("source_chat_id", 0)) == int(source_chat_id)
                    and int(item.get("source_message_id", 0)) == int(source_message_id)
                )
            ]
            if remaining != old:
                await self.update(task_id, {key: remaining})

    async def append_notion_result(self, task_id: int, bucket: str, entry: dict):
        key = f"notion_{bucket}"
        task = await self.read(task_id)
        if not task:
            return
        items = list(task.get(key, []))
        items.append(entry)
        await self.update(task_id, {key: items})

    async def append_telegram_result(self, task_id: int, bucket: str, entry: dict):
        key = f"telegram_{bucket}"
        task = await self.read(task_id)
        if not task:
            return
        items = list(task.get(key, []))
        items.append(entry)
        await self.update(task_id, {key: items})

    async def unfinished_general_tasks(self, chat_id: int, user_id: int) -> list[dict]:
        """Incomplete or failed general-chat tasks block automatic syncing.

        Topic-only priority jobs are excluded: they never establish a full-chat baseline.
        """
        tasks = await self.filter_documents({
            "source_chat_id": int(chat_id),
            "user_id": int(user_id),
            "source_topic_id": None,
        })
        return [t for t in tasks if (
            t.get("status") != "completed"
            or bool(t.get("telegram_failed"))
            or (t.get("notion_enabled") and bool(t.get("notion_failed")))
        )]

    async def get_max_message_id(self, chat_id: int, user_id: int | None = None) -> Optional[int]:
        """Highest *completed full-chat* range, never a started/priority topic range.

        Historical versions may have incorrectly marked a task completed.  Audit
        any legacy history before relying on it as a complete source archive.
        """
        query = {
            "source_chat_id": int(chat_id),
            "source_topic_id": None,
            "status": "completed",
            "telegram_failed": [],
        }
        if user_id is not None:
            query["user_id"] = int(user_id)
        cursor = self.col.find(query).sort("last_message_id", -1).limit(1)
        documents = await cursor.to_list(length=1)
        return documents[0]["last_message_id"] if documents else None
