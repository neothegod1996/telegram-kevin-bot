from datetime import datetime

from bot.backup.delivery_ledger import delivery_record_id
from database.core import Core


class DeliveryLedgerDB(Core):
    """Persistent done-ledger for confirmed Telegram copies."""

    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "delivery_ledger")

    def store(self) -> "_MongoLedgerStore":
        return _MongoLedgerStore(self)

    async def is_confirmed(
        self, source_chat_id: int, source_message_id: int, dest_chat_id: int
    ) -> bool:
        rid = delivery_record_id(source_chat_id, source_message_id, dest_chat_id)
        doc = await self.read(rid)
        return doc is not None and doc.get("status") == "confirmed"

    async def confirm(
        self,
        source_chat_id: int,
        source_message_id: int,
        dest_chat_id: int,
        *,
        dest_message_id: int | None = None,
        method: str = "copy",
        user_id: int | None = None,
    ):
        rid = delivery_record_id(source_chat_id, source_message_id, dest_chat_id)
        document = {
            "_id": rid,
            "user_id": user_id,
            "source_chat_id": int(source_chat_id),
            "source_message_id": int(source_message_id),
            "dest_chat_id": int(dest_chat_id),
            "dest_message_id": dest_message_id,
            "method": method,
            "status": "confirmed",
            "confirmed_at": datetime.now(),
        }
        existing = await self.read(rid)
        if existing:
            await self.update(rid, document)
        else:
            await self.create(document)
        return document

    async def filter_by_source(self, source_chat_id: int, source_message_id: int) -> list:
        return await self.filter_documents(
            {
                "source_chat_id": int(source_chat_id),
                "source_message_id": int(source_message_id),
                "status": "confirmed",
            }
        )


class _MongoLedgerStore:
    def __init__(self, db: DeliveryLedgerDB) -> None:
        self._db = db

    async def get(self, record_id: str):
        return await self._db.read(record_id)

    async def put(self, record_id: str, document: dict) -> None:
        existing = await self._db.read(record_id)
        if existing:
            await self._db.update(record_id, document)
        else:
            await self._db.create(document)

    async def filter_by_source(self, source_chat_id: int, source_message_id: int) -> list:
        return await self._db.filter_by_source(source_chat_id, source_message_id)