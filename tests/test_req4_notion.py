import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("BOT_TOKEN", "12345:test_token")
os.environ.setdefault("OWNER_ID", "12345")
os.environ.setdefault("DATABASE_URL", "mongodb://localhost:27017")

from bot.backup.notion_backup import NotionBatchSummary, backup_message_to_notion
from types import SimpleNamespace


class NotionBackupTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_message_skipped(self):
        message = SimpleNamespace(
            id=1,
            chat=SimpleNamespace(id=-100),
            text="hello",
            media=None,
            download_id=1,
            index="1",
            link="x",
        )
        bot = MagicMock(send_message=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())))
        app = MagicMock()
        report = await backup_message_to_notion(bot, app, message, 1)
        self.assertEqual(report.status, "skipped")

    async def test_upload_success(self):
        message = SimpleNamespace(
            id=2,
            chat=SimpleNamespace(id=-100),
            text=None,
            caption="c",
            media=SimpleNamespace(value="document"),
            document=True,
            download_id=1,
            index="2",
            link="x",
        )
        bot = MagicMock(send_message=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())))
        with patch("bot.backup.notion_backup.download_media", AsyncMock(return_value="/tmp/f.bin")), patch(
            "bot.backup.notion_backup.upload_message_to_notion",
            return_value=SimpleNamespace(file_id="nid-1"),
        ), patch("os.remove"):
            report = await backup_message_to_notion(bot, MagicMock(), message, 1)
        self.assertEqual(report.status, "succeeded")
        self.assertEqual(report.file_id, "nid-1")

    def test_summary_text(self):
        summary = NotionBatchSummary()
        summary.failed.append(
            type("R", (), {"source_chat_id": 1, "source_message_id": 2, "error": "x"})()
        )
        self.assertIn("failed", summary.as_text().lower())


if __name__ == "__main__":
    unittest.main()