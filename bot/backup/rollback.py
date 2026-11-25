"""Legacy cancellation helper: deliberately non-destructive.

Previously this module deleted destination messages and erased successful delivery
records.  A backup must never undo confirmed successful deliveries just because
an operator paused/cancelled during subsequent work.  Callers may still import
this function during a gradual migration; it is a safe no-op.
"""

import logging

logger = logging.getLogger(__name__)


async def rollback_message_delivery(bot, app, source_chat_id: int, source_message_id: int) -> None:
    logger.info(
        "Stop requested for %s:%s: confirmed copies and ledger intentionally retained",
        source_chat_id, source_message_id,
    )
