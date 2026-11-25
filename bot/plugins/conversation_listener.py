from pyrogram import Client, StopPropagation, filters

from bot.utils.conversation import try_resolve_pending


@Client.on_message(filters.private & filters.incoming, group=-1)
async def _conversation_listener(client: Client, message):
    if await try_resolve_pending(client, message):
        raise StopPropagation