import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("BOT_TOKEN", "12345:test_token")
os.environ.setdefault("OWNER_ID", "12345")
os.environ.setdefault("DATABASE_URL", "mongodb://localhost:27017")

from bot.backup.delivery_ledger import DeliveryLedger, InMemoryLedgerStore, delivery_record_id
from bot.backup.telegram_delivery import (
    ChannelRoute,
    DeliveryMethod,
    TelegramDeliveryEngine,
    direct_copy_supported,
)


class DeliveryLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_and_skip(self):
        store = InMemoryLedgerStore()
        ledger = DeliveryLedger(store, user_id=42)
        await ledger.confirm(-1001, 10, 2001, dest_message_id=99, method="copy")
        self.assertTrue(await ledger.is_confirmed(-1001, 10, 2001))
        self.assertFalse(await ledger.is_confirmed(-1001, 10, 2002))
        self.assertEqual(
            delivery_record_id(-1001, 10, 2001),
            "-1001:10:2001",
        )

    async def test_all_destinations_confirmed(self):
        store = InMemoryLedgerStore()
        ledger = DeliveryLedger(store)
        await ledger.confirm(-1001, 5, 100, method="copy")
        await ledger.confirm(-1001, 5, 200, method="copy")
        self.assertTrue(await ledger.all_destinations_confirmed(-1001, 5, [100, 200]))
        self.assertFalse(await ledger.all_destinations_confirmed(-1001, 5, [100, 300]))


class MockCopyClient:
    def __init__(self, protected_ids: set[int]):
        self.protected_ids = protected_ids
        self.copy_calls = []

    async def copy_message(self, **kwargs):
        self.copy_calls.append(kwargs)
        msg_id = kwargs["message_id"]
        if msg_id in self.protected_ids:
            from pyrogram import errors

            raise errors.ChatForwardsRestricted()
        return SimpleNamespace(id=msg_id + 1000, chat=SimpleNamespace(id=kwargs["chat_id"]))


class SimulatedTopicRunner:
    """Process ~15 messages with a done-ledger; simulates restart after message 7."""

    SOURCE = -100555
    DEST = 9001

    def __init__(self, protected_ids: frozenset[int] = frozenset()):
        self.protected = protected_ids
        self.store = InMemoryLedgerStore()
        self.ledger = DeliveryLedger(self.store, user_id=1)
        self.engine = TelegramDeliveryEngine(self.ledger)
        self.client = MockCopyClient(set(protected_ids))
        self.download_upload_count = 0

    def make_message(self, msg_id: int, has_media: bool = True):
        return SimpleNamespace(
            id=msg_id,
            chat=SimpleNamespace(id=self.SOURCE),
            text=None if has_media else f"text-{msg_id}",
            caption=f"cap-{msg_id}" if has_media else None,
            media=SimpleNamespace(value="photo") if has_media else None,
            photo=True if has_media else None,
            video=None,
            service=False,
            sticker=False,
            reply_markup=None,
            link=f"link/{msg_id}",
            download_id=1,
            index=str(msg_id),
            topic=None,
        )

    async def deliver_one(self, message, delivered_log=None):
        route = ChannelRoute(destination_channel_id=self.DEST)

        async def floodwait_handler(fn, *a, **k):
            result = fn(*a, **k)
            if hasattr(result, "__await__"):
                return await result
            return result

        bot = SimpleNamespace(floodwait_handler=floodwait_handler)
        if message.id in self.protected and delivered_log is not None:
            self.download_upload_count += 1
            outcome = await self.engine.deliver_to_destination(
                bot=bot,
                app=self.client,
                message=message,
                route=route,
                user_id=1,
                delivered_log=delivered_log,
            )
            return outcome
        return await self.engine.deliver_to_destination(
            bot=bot,
            app=self.client,
            message=message,
            route=route,
            user_id=1,
            delivered_log=delivered_log,
        )

    async def run_topic(self, start_id: int, end_id: int, restart_at: int | None = None):
        delivered = 0
        skipped = 0
        for msg_id in range(start_id, end_id + 1):
            if restart_at and msg_id == restart_at:
                self.engine = TelegramDeliveryEngine(
                    DeliveryLedger(self.store, user_id=1)
                )
            message = self.make_message(msg_id, has_media=(msg_id % 3 != 0))
            if await self.ledger.is_confirmed(self.SOURCE, msg_id, self.DEST):
                skipped += 1
                continue
            outcome = await self.deliver_one(message)
            if not outcome.confirmed and message.media:
                fallback_log = SimpleNamespace(
                    id=1,
                    text=None,
                    caption=message.caption,
                    photo=SimpleNamespace(file_id="fid"),
                    copy=lambda *a, **k: SimpleNamespace(id=msg_id + 5000),
                )
                outcome = await self.deliver_one(message, delivered_log=fallback_log)
            if outcome.confirmed or outcome.skipped:
                delivered += 1
        return delivered, skipped, len(self.client.copy_calls)


class SimulatedTopicTests(unittest.IsolatedAsyncioTestCase):
    async def test_topic_direct_copy_and_restart_resume(self):
        runner = SimulatedTopicRunner(protected_ids=frozenset({4, 8, 11}))
        delivered, skipped, copies_first = await runner.run_topic(1, 15, restart_at=8)
        self.assertGreater(delivered, 0)
        self.assertEqual(skipped, 0)

        runner2 = SimulatedTopicRunner()
        runner2.store = runner.store
        runner2.ledger = DeliveryLedger(runner2.store, user_id=1)
        runner2.engine = TelegramDeliveryEngine(runner2.ledger)
        runner2.client = MockCopyClient(set())
        delivered2, skipped2, copies_second = await runner2.run_topic(1, 15)
        self.assertEqual(delivered2, 0)
        self.assertEqual(skipped2, 15)
        self.assertEqual(copies_second, 0)

    async def test_protected_uses_fallback_once_per_message(self):
        runner = SimulatedTopicRunner(protected_ids=frozenset({2, 5, 7}))
        await runner.run_topic(1, 12)
        self.assertEqual(runner.download_upload_count, 3)

    def test_direct_copy_supported(self):
        good = SimpleNamespace(service=False, sticker=False)
        bad = SimpleNamespace(service=True, sticker=False)
        self.assertTrue(direct_copy_supported(good))
        self.assertFalse(direct_copy_supported(bad))


if __name__ == "__main__":
    unittest.main()