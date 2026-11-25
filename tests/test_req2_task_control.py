import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("BOT_TOKEN", "12345:test_token")
os.environ.setdefault("OWNER_ID", "12345")
os.environ.setdefault("DATABASE_URL", "mongodb://localhost:27017")

from bot.backup.task_control import (
    ControlCommand,
    WorkerPhase,
    control_status_line,
    interruptible_sleep,
)


class InterruptibleSleepTests(unittest.IsolatedAsyncioTestCase):
    async def test_sleep_stops_early(self):
        calls = 0

        async def should_stop():
            nonlocal calls
            calls += 1
            return calls >= 2

        stopped = await interruptible_sleep(10, should_stop, interval=0.05)
        self.assertTrue(stopped)
        self.assertLess(calls, 20)

    async def test_sleep_completes_without_stop(self):
        async def should_stop():
            return False

        stopped = await interruptible_sleep(0.15, should_stop, interval=0.05)
        self.assertFalse(stopped)


class ControlStatusTests(unittest.TestCase):
    def test_draining_vs_idle(self):
        self.assertIn("finishing", control_status_line(ControlCommand.PAUSE.value, WorkerPhase.DRAINING.value).lower())
        self.assertIn("idle", control_status_line(None, WorkerPhase.PAUSED.value).lower())


class BatchLoopControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_persists_and_halts_between_messages(self):
        from bot.utils.batch import worker as batch_worker

        task_id = 424242
        task_state = {
            "_id": task_id,
            "status": "running",
            "current_message_id": 1,
            "last_message_id": 15,
            "source_chat_id": -100,
            "processed_count": 0,
            "notion_enabled": False,
            "control": None,
        }

        mock_db = MagicMock()
        mock_db.batch_tasks.read = AsyncMock(side_effect=lambda _id: dict(task_state))
        mock_db.batch_tasks.update_progress = AsyncMock()
        mock_db.batch_tasks.set_control = AsyncMock(
            side_effect=lambda _id, control, **kw: task_state.update({"control": control, **kw}) or True
        )
        mock_db.batch_tasks.clear_control = AsyncMock()
        mock_db.batch_tasks.update_status = AsyncMock()

        messages_processed = []

        async def fake_process(*args, **kwargs):
            msg_id = args[3]
            messages_processed.append(msg_id)
            if msg_id == 3:
                task_state["control"] = ControlCommand.PAUSE.value
            return True, False

        with patch.object(batch_worker, "db", mock_db), patch.object(
            batch_worker, "process_message_item", fake_process
        ), patch.object(batch_worker, "interruptible_sleep", AsyncMock(return_value=False)), patch.object(
            batch_worker, "Config"
        ) as cfg:
            cfg.BATCH_SLEEP_TIME = 0
            count = await batch_worker.run_batch_loop(
                MagicMock(),
                MagicMock(),
                task_state,
                task_id,
                1,
            )
        self.assertEqual(messages_processed, [1, 2, 3])
        self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()