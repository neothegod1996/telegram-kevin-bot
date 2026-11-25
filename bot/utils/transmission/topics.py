import logging
from typing import Dict

from pyrogram import Client, types

logger = logging.getLogger(__name__)


async def get_topics_by_chat_id(client: Client, chat_id: int) -> Dict[str, int]:
    topics: Dict[str, int] = {}
    try:
        async for topic in client.get_forum_topics(chat_id):
            topics[topic.name] = topic.id
    except Exception as e:
        logger.error(f"Error getting topics from chat {chat_id}: {e}")
    return topics


async def get_source_topics(client: Client, source_chat_id: int):
    return await get_topics_by_chat_id(client, source_chat_id)


async def get_target_topics(client: Client, target_chat_id: int):
    return await get_topics_by_chat_id(client, target_chat_id)


async def create_topic_if_not_exists(
    client: Client, target_chat_id: int, topic_name: str, existing_topics: dict
):
    if topic_name in existing_topics:
        logger.info(
            "Topic '%s' already exists with ID %s",
            topic_name,
            existing_topics[topic_name],
        )
        return existing_topics[topic_name]
    try:
        topic = await client.create_forum_topic(chat_id=target_chat_id, title=topic_name)
        logger.info("Created new topic '%s' with ID %s", topic_name, topic.id)
        existing_topics[topic_name] = topic.id
        return topic.id
    except Exception as e:
        logger.error(f"Error creating topic '{topic_name}': {e}")
        return None


async def handle_topic_thread(
    app: Client, message: types.Message, channel_id: int, kwargs: dict
):
    source_topic = message.topic and message.topic.id
    if not source_topic:
        return
    source_topic_name = message.topic.name
    target_topics = await get_target_topics(app, channel_id)
    target_topic = await create_topic_if_not_exists(
        app, channel_id, source_topic_name, target_topics
    )
    if target_topic:
        kwargs["message_thread_id"] = target_topic