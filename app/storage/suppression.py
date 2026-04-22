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
