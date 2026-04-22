from app.core.config import settings  # noqa: F401


class CalComClient:
    def create_booking(self, name: str, email: str, start: str, timezone: str = "UTC") -> dict:
        # TODO: POST {calcom_base_url}/bookings with calcom_api_key
        return {}

    def get_available_slots(self, date: str) -> list[str]:
        # TODO: GET {calcom_base_url}/slots
        return []
