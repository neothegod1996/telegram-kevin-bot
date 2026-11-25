"""Bulk route import and topic-priority helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedRoute:
    source_channel_id: int
    destination_channel_id: int
    topic_id: int | None = None
    label: str | None = None


_ROUTE_LINE = re.compile(
    r"^\s*(?P<src>-?\d+)\s*(?:->|➡|=>)\s*(?P<dst>-?\d+)(?:\s+#\s*(?P<label>.+))?\s*$"
)


def parse_bulk_routes(text: str) -> tuple[list[ParsedRoute], list[str]]:
    routes: list[ParsedRoute] = []
    errors: list[str] = []
    for lineno, raw in enumerate(text.strip().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ROUTE_LINE.match(line)
        if not match:
            errors.append(f"Line {lineno}: invalid format (use -100123 -> -100456)")
            continue
        routes.append(
            ParsedRoute(
                source_channel_id=int(match.group("src")),
                destination_channel_id=int(match.group("dst")),
                label=match.group("label"),
            )
        )
    return routes, errors


def message_in_topic(message, topic_id: int | None) -> bool:
    if topic_id is None:
        return True
    msg_topic = None
    if getattr(message, "topic", None):
        msg_topic = message.topic.id
    if msg_topic is None:
        msg_topic = getattr(message, "message_thread_id", None)
    return msg_topic == topic_id