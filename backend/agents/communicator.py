from __future__ import annotations

import datetime
from typing import Any, List, Optional


class NotificationAgent:
    """Formats and dispatches incident alerts to supported channels."""

    def __init__(self) -> None:
        self.memory: List[str] = []

    def format_alert(self, incident: dict[str, Any], resolution: dict[str, Any]) -> str:
        timestamp = datetime.datetime.now().isoformat(timespec="seconds")
        severity = str(incident.get("severity", "unknown")).upper()
        category = str(incident.get("category", "unknown"))
        priority = str(incident.get("priority", "unknown"))
        recommendation = str(resolution.get("recommendation", ""))
        status = str(resolution.get("status", "unknown"))

        lines = [
            f"🌐  [{timestamp}] Alert 🌐",
            f"[{severity}] {category} {status.upper()}",
            f"Priority : {priority}",
            f"Action   : {recommendation}",
        ]
        return "\n".join(lines)

    def send(self, incident_dict: dict[str, Any], resolution_dict: dict[str, Any], channel: str, log_path: str = "notifications.log") -> None:
        channels = {"console", "log", "memory"}
        if channel not in channels:
            raise ValueError(f"Unsupported channel: {channel!r}. Use one of {sorted(channels)}")

        text = self.format_alert(incident_dict, resolution_dict)

        if channel == "console":
            print(text)
        elif channel == "log":
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        elif channel == "memory":
            self.memory.append(text)
