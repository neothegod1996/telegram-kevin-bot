"""Wait for the next in-chat reply (kurimod ``ask`` / ``chat.ask`` replacement)."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Optional, Union

from pyrogram.types import Message


class ConversationTimeout(TimeoutError):
    """No matching reply before the timeout."""


@dataclass
class _PendingAsk:
    future: asyncio.Future
    message_filter: Any


# (user_id, chat_id) -> pending ask
_pending: dict[tuple[int, int], _PendingAsk] = {}


async def _matches(client, message: Message, flt) -> bool:
    if flt is None:
        return True
    try:
        result = flt(client, message)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)
    except Exception:
        return False


def _key(user_id: int, chat_id: int) -> tuple[int, int]:
    return user_id, chat_id


def has_pending_ask(user_id: int, chat_id: int) -> bool:
    """True while this user is in a multi-step ask() flow (e.g. add channel pair)."""
    pending = _pending.get(_key(user_id, int(chat_id)))
    return pending is not None and not pending.future.done()


def clear_pending(user_id: int, chat_id: int) -> None:
    key = _key(user_id, chat_id)
    pending = _pending.pop(key, None)
    if pending and not pending.future.done():
        pending.future.cancel()


async def ask(
    client,
    chat_id: Union[int, str],
    text: str,
    *,
    user_id: Optional[int] = None,
    filters=None,
    timeout: Optional[float] = 300,
    reply_markup=None,
    **send_kwargs,
) -> Message:
    """
    Send *text* and return the next message from *user_id* in *chat_id* that passes *filters*.
    """
    chat_id = int(chat_id)
    uid = int(user_id) if user_id is not None else chat_id
    key = _key(uid, chat_id)

    clear_pending(uid, chat_id)

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _pending[key] = _PendingAsk(future=future, message_filter=filters)

    await client.send_message(
        chat_id, text, reply_markup=reply_markup, **send_kwargs
    )

    try:
        if timeout is not None:
            return await asyncio.wait_for(future, timeout)
        return await future
    except asyncio.TimeoutError as e:
        clear_pending(uid, chat_id)
        raise ConversationTimeout("Timed out waiting for a reply.") from e
    except asyncio.CancelledError:
        clear_pending(uid, chat_id)
        raise


async def try_resolve_pending(client, message: Message) -> bool:
    """If *message* answers an active ask, complete it and return True."""
    if not message.from_user:
        return False
    key = _key(message.from_user.id, message.chat.id)
    pending = _pending.get(key)
    if not pending or pending.future.done():
        return False
    if not await _matches(client, message, pending.message_filter):
        return False
    _pending.pop(key, None)
    pending.future.set_result(message)
    return True