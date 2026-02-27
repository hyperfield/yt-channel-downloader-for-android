import json
from typing import Any, Dict, Mapping, Optional, Union

from .settings import CoreSettings, coerce_settings


class SettingsManager:
    """In-memory settings wrapper with optional JSON serialization."""

    def __init__(self, settings: Optional[Union[CoreSettings, Mapping[str, Any]]] = None) -> None:
        self.settings = coerce_settings(settings)

    def update(self, updates: Mapping[str, Any]) -> None:
        merged = self.settings.to_dict()
        merged.update(updates)
        self.settings = CoreSettings.from_dict(merged, download_directory=merged.get("download_directory"))

    def to_dict(self) -> Dict[str, Any]:
        return self.settings.to_dict()

    @classmethod
    def from_json(cls, path: str) -> "SettingsManager":
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return cls(data)

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.settings.to_dict(), handle)
