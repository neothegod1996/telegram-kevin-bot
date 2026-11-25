from datetime import datetime

from database.core import Core


class RouteTemplatesDB(Core):
    def __init__(self, uri, database_name):
        super().__init__(uri, database_name, "route_templates")

    async def upsert_template(self, user_id: int, name: str, routes: list[dict]) -> str:
        template_id = f"{user_id}:{name}"
        doc = {
            "_id": template_id,
            "user_id": int(user_id),
            "name": name,
            "routes": routes,
            "updated_at": datetime.now(),
        }
        existing = await self.read(template_id)
        if existing:
            await self.update(template_id, doc)
        else:
            doc["created_at"] = datetime.now()
            await self.create(doc)
        return template_id

    async def list_templates(self, user_id: int) -> list:
        return await self.filter_documents({"user_id": int(user_id)}, sort=[("updated_at", -1)])

    async def get_template(self, user_id: int, name: str):
        return await self.read(f"{user_id}:{name}")