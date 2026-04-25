import json
from pathlib import Path


class SmsSuppressionStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def is_suppressed(self, phone_number: str) -> bool:
        data = self._load()
        return phone_number in data

    def suppress(self, phone_number: str) -> None:
        data = self._load()
        data[phone_number] = {"status": "suppressed"}
        self._save(data)

    def unsuppress(self, phone_number: str) -> None:
        data = self._load()
        if phone_number in data:
            del data[phone_number]
            self._save(data)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))


class EmailSuppressionStore:
    """Simple local suppression list for email identifiers (address and/or domain)."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def is_suppressed(self, email: str) -> bool:
        email = (email or "").strip().lower()
        if not email:
            return False
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        data = self._load()
        return email in data or (domain and domain in data)

    def suppress(self, identifier: str, *, reason: str = "") -> None:
        key = (identifier or "").strip().lower()
        if not key:
            return
        data = self._load()
        data[key] = {"status": "suppressed", "reason": reason[:200]}
        self._save(data)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))
