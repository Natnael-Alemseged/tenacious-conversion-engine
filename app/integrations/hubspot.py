from app.core.config import settings  # noqa: F401


class HubSpotClient:
    def upsert_contact(self, identifier: str, source: str, properties: dict | None = None) -> dict:
        # TODO: POST /crm/v3/objects/contacts with HubSpot API key
        return {}

    def update_contact(self, contact_id: str, properties: dict) -> dict:
        # TODO: PATCH /crm/v3/objects/contacts/{id}
        return {}
