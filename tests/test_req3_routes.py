import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("BOT_TOKEN", "12345:test_token")
os.environ.setdefault("OWNER_ID", "12345")
os.environ.setdefault("DATABASE_URL", "mongodb://localhost:27017")

from bot.backup.routes import message_in_topic, parse_bulk_routes


class RouteParsingTests(unittest.TestCase):
    def test_forum_message_link_parts(self):
        from bot.utils.telegram_links import get_link_parts

        parts = get_link_parts("https://t.me/c/3968319793/1/52")
        self.assertIsNotNone(parts)
        chat_id, message_id, topic_id = parts
        self.assertEqual(chat_id, -1003968319793)
        self.assertEqual(topic_id, 1)
        self.assertEqual(message_id, 52)

    def test_bulk_parse(self):
        text = """
# my routes
-100111 -> -100222 # main
-100333 => -100444
"""
        routes, errors = parse_bulk_routes(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[0].source_channel_id, -100111)

    def test_topic_filter(self):
        in_topic = SimpleNamespace(topic=SimpleNamespace(id=7), message_thread_id=7)
        other = SimpleNamespace(topic=SimpleNamespace(id=9), message_thread_id=9)
        self.assertTrue(message_in_topic(in_topic, 7))
        self.assertFalse(message_in_topic(other, 7))
        self.assertTrue(message_in_topic(other, None))


class TopicBatchSimulation(unittest.IsolatedAsyncioTestCase):
    async def test_full_history_skips_topic_messages_already_ledgered(self):
        from bot.backup.delivery_ledger import DeliveryLedger, InMemoryLedgerStore
        from bot.utils import batch_utils
        from bot.utils.batch import worker as batch_worker

        store = InMemoryLedgerStore()
        ledger = DeliveryLedger(store, user_id=1)
        source = -100555
        default_dest = 1
        for mid in (2, 4, 6):
            await ledger.confirm(source, mid, default_dest, method="copy")

        async def fake_get_messages(_chat, mid):
            topic_id = 7 if mid % 2 == 0 else 9
            return SimpleNamespace(
                id=mid,
                empty=False,
                sticker=False,
                service=False,
                media=None,
                text=f"t{mid}",
                chat=SimpleNamespace(id=source),
                topic=SimpleNamespace(id=topic_id),
                message_thread_id=topic_id,
            )

        app = SimpleNamespace(get_messages=fake_get_messages)
        bot = MagicMock()
        bot.floodwait_handler = AsyncMock()
        bot.get_chat = AsyncMock(return_value=SimpleNamespace(id=1))

        mock_db = MagicMock()
        mock_db.user_channels.filter_documents = AsyncMock(return_value=[])

        with patch.object(batch_worker, "db", mock_db), patch("database.db", mock_db), patch(
            "bot.backup.telegram_delivery.build_delivery_ledger_for_user",
            AsyncMock(return_value=ledger),
        ), patch.object(
            batch_worker, "get_media_type", AsyncMock(return_value=["text"])
        ):
            from bot.backup.reports import ForwardResult, TelegramMessageReport

            forward = AsyncMock(
                return_value=ForwardResult(
                    telegram=TelegramMessageReport(source, 1, "succeeded"),
                )
            )
            with patch.object(batch_worker, "forward_message", forward):
                for mid in range(1, 11):
                    await batch_utils.process_message_item(
                        bot, app, source, mid, 1, False, source_topic_id=None
                    )
        self.assertEqual(forward.await_count, 7)

        topic_only = 0
        with patch.object(batch_worker, "db", mock_db), patch("database.db", mock_db), patch(
            "bot.backup.telegram_delivery.build_delivery_ledger_for_user",
            AsyncMock(return_value=ledger),
        ), patch.object(batch_worker, "get_media_type", AsyncMock(return_value=["text"])):
            for mid in range(1, 11):
                message = await app.get_messages(source, mid)
                if message_in_topic(message, 7):
                    topic_only += 1
        self.assertEqual(topic_only, 5)


if __name__ == "__main__":
    unittest.main()