from pyrogram import Client, filters
from pyrogram.types import Message

from bot.backup.routes import parse_bulk_routes
from bot.config import Config
from database import db


@Client.on_message(
    filters.command("routes_import")
    & filters.private
    & filters.incoming
    & filters.user(Config.OWNER_ID)
)
async def routes_import(bot: Client, message: Message):
    """
    Bulk import reusable routes.

    Reply to a message with lines like:
    -100111 -> -100222 # creator-main
  -100111 -> -100333 # creator-archive
    """
    source = message.reply_to_message.text if message.reply_to_message else None
    if not source:
        return await message.reply_text(
            "Reply to a message that contains route lines.\n\n"
            "Format per line: `-100SOURCE -> -100DEST # optional label`"
        )

    routes, errors = parse_bulk_routes(source)
    if errors:
        return await message.reply_text("❌ Import errors:\n" + "\n".join(errors))

    name = (message.command[1] if len(message.command) > 1 else "default").strip()
    user_id = message.from_user.id
    created = 0
    for route in routes:
        existing = await db.user_channels.filter_document(
            {
                "user_id": user_id,
                "source_channel_id": route.source_channel_id,
                "destination_channel_id": route.destination_channel_id,
            }
        )
        if existing:
            await db.user_channels.update(
                existing["_id"],
                {"status": True, "topic_id": route.topic_id},
            )
        else:
            await db.user_channels.create(
                user_id,
                route.source_channel_id,
                route.label or str(route.source_channel_id),
                route.destination_channel_id,
                route.label or str(route.destination_channel_id),
                route.topic_id,
            )
            created += 1

    await db.route_templates.upsert_template(
        user_id,
        name,
        [
            {
                "source_channel_id": r.source_channel_id,
                "destination_channel_id": r.destination_channel_id,
                "label": r.label,
            }
            for r in routes
        ],
    )
    await message.reply_text(
        f"✅ Imported {len(routes)} routes into template `{name}` "
        f"({created} new channel pairs)."
    )


@Client.on_message(
    filters.command("routes_apply")
    & filters.private
    & filters.incoming
    & filters.user(Config.OWNER_ID)
)
async def routes_apply(bot: Client, message: Message):
    """Re-activate all routes from a saved template without re-entering them."""
    name = message.command[1] if len(message.command) > 1 else "default"
    template = await db.route_templates.get_template(message.from_user.id, name)
    if not template:
        return await message.reply_text(f"❌ Template `{name}` not found.")

    for route in template["routes"]:
        existing = await db.user_channels.filter_document(
            {
                "user_id": message.from_user.id,
                "source_channel_id": route["source_channel_id"],
                "destination_channel_id": route["destination_channel_id"],
            }
        )
        if existing:
            await db.user_channels.update(existing["_id"], {"status": True})
        else:
            await db.user_channels.create(
                message.from_user.id,
                route["source_channel_id"],
                route.get("label") or str(route["source_channel_id"]),
                route["destination_channel_id"],
                route.get("label") or str(route["destination_channel_id"]),
                route.get("topic_id"),
            )

    await message.reply_text(f"✅ Applied template `{name}` ({len(template['routes'])} routes).")