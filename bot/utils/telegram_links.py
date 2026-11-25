from dataclasses import dataclass

from pyrogram import types


@dataclass
class ChannelInput:
    """Chat target from pairing flow; topic_id is set only from forum message links."""

    chat: int | str
    topic_id: int | None = None


def is_valid_link(message: types.Message) -> bool:
    domains = ["t.me", "telegram.me", "telegram.dog", "tg://"]
    return bool(message.text and any(domain in message.text for domain in domains))


def get_link_parts(link: str):
    topic_id = None

    if link.startswith("tg://"):
        if "openmessage?" not in link:
            return None
        try:
            params = dict(param.split("=") for param in link.split("?")[1].split("&"))
            chat_id = params.get("user_id")
            if chat_id.isdigit():
                chat_id = int(chat_id)
            else:
                chat_id = chat_id.replace("@", "")
            message_id = int(params.get("message_id"))
            return chat_id, message_id, topic_id
        except Exception:
            return None

    if not link.startswith("http"):
        return None

    parts = (
        link.replace("https://", "")
        .replace("http://", "")
        .replace("/c/", "/")
        .replace("/s/", "/")
        .replace("/b/", "/")
        .strip()
        .split("?")[0]
        .split("/")
    )

    if len(parts) < 3:
        return None

    chat_id = parts[1]
    if len(parts) == 4:
        try:
            topic_id = int(parts[2])
            message_id = int(parts[3])
        except ValueError:
            return None
    else:
        try:
            message_id = int(parts[2])
        except ValueError:
            return None

    if str(chat_id).isdigit():
        chat_id = int(f"-100{chat_id}")

    return chat_id, message_id, topic_id


def get_link_parts_from_forward(message: types.Message):
    return message.forward_from_chat.id, message.forward_from_message_id, None


def parse_channel_input(text: str) -> ChannelInput | None:
    if not text or not str(text).strip():
        return None
    text_val = str(text).strip()

    link_parts = get_link_parts(text_val)
    if link_parts:
        chat_id, _message_id, topic = link_parts
        return ChannelInput(chat=chat_id, topic_id=topic)

    if text_val.lstrip("-").isdigit():
        n = int(text_val)
        if n > 0 and len(str(n)) >= 10:
            return ChannelInput(chat=int(f"-100{n}"))
        return ChannelInput(chat=n)

    clean = text_val.replace("@", "").strip()
    if clean and not clean.lower().startswith("http"):
        return ChannelInput(chat=clean)
    return None


def parse_channel_target(text: str) -> int | str | None:
    parsed = parse_channel_input(text)
    return parsed.chat if parsed else None


def resolve_channel_input_from_message(message: types.Message) -> ChannelInput | None:
    if message.forward_from_chat:
        topic_id = getattr(message, "message_thread_id", None) or None
        return ChannelInput(chat=message.forward_from_chat.id, topic_id=topic_id)
    if message.text:
        return parse_channel_input(message.text)
    return None


def is_command(message: types.Message) -> bool:
    return bool(message.text and message.text.startswith("/"))