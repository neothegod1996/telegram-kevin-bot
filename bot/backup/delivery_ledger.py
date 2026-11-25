"""Done-ledger for confirmed Telegram deliveries (source chat + message id + destination)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Protocol


def delivery_record_id(source_chat_id: int, source_message_id: int, dest_chat_id: int) -> str:
    return f"{int(source_chat_id)}:{int(source_message_id)}:{int(dest_chat_id)}"


@dataclass(frozen=True)
class DeliveryRecord:
    source_chat_id: int
    source_message_id: int
    dest_chat_id: int
    dest_message_id: Optional[int]
    method: str
    confirmed_at: datetime

    @property
    def record_id(self) -> str:
        return delivery_record_id(self.source_chat_id, self.source_message_id, self.dest_chat_id)


class LedgerStore(Protocol):
    async def get(self, record_id: str) -> Optional[dict[str, Any]]: ...

    async def put(self, record_id: str, document: dict[str, Any]) -> None: ...

    async def filter_by_source(
        self, source_chat_id: int, source_message_id: int
    ) -> list[dict[str, Any]]: ...


class InMemoryLedgerStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}

    async def get(self, record_id: str) -> Optional[dict[str, Any]]:
        return self._docs.get(record_id)

    async def put(self, record_id: str, document: dict[str, Any]) -> None:
        self._docs[record_id] = document

    async def filter_by_source(
        self, source_chat_id: int, source_message_id: int
    ) -> list[dict[str, Any]]:
        prefix = f"{int(source_chat_id)}:{int(source_message_id)}:"
        return [doc for rid, doc in self._docs.items() if rid.startswith(prefix)]


class DeliveryLedger:
    """Records a message only after Telegram confirms delivery to a destination."""

    def __init__(self, store: LedgerStore, *, user_id: Optional[int] = None) -> None:
        self._store = store
        self._user_id = user_id

    async def is_confirmed(
        self, source_chat_id: int, source_message_id: int, dest_chat_id: int
    ) -> bool:
        rid = delivery_record_id(source_chat_id, source_message_id, dest_chat_id)
        doc = await self._store.get(rid)
        return doc is not None and doc.get("status") == "confirmed"

    async def all_destinations_confirmed(
        self,
        source_chat_id: int,
        source_message_id: int,
        dest_chat_ids: list[int],
    ) -> bool:
        if not dest_chat_ids:
            return False
        for dest in dest_chat_ids:
            if not await self.is_confirmed(source_chat_id, source_message_id, dest):
                return False
        return True

    async def confirm(
        self,
        source_chat_id: int,
        source_message_id: int,
        dest_chat_id: int,
        *,
        dest_message_id: Optional[int] = None,
        method: str = "copy",
    ) -> DeliveryRecord:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        rid = delivery_record_id(source_chat_id, source_message_id, dest_chat_id)
        document = {
            "_id": rid,
            "user_id": self._user_id,
            "source_chat_id": int(source_chat_id),
            "source_message_id": int(source_message_id),
            "dest_chat_id": int(dest_chat_id),
            "dest_message_id": dest_message_id,
            "method": method,
            "status": "confirmed",
            "confirmed_at": now,
        }
        await self._store.put(rid, document)
        return DeliveryRecord(
            source_chat_id=int(source_chat_id),
            source_message_id=int(source_message_id),
            dest_chat_id=int(dest_chat_id),
            dest_message_id=dest_message_id,
            method=method,
            confirmed_at=now,
        )

    async def confirmed_destinations(
        self, source_chat_id: int, source_message_id: int
    ) -> set[int]:
        docs = await self._store.filter_by_source(source_chat_id, source_message_id)
        return {
            int(doc["dest_chat_id"])
            for doc in docs
            if doc.get("status") == "confirmed"
        }