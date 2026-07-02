from __future__ import annotations

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from agents.resolver import ResolutionEngine, build_default_engine  # noqa: E402
from agents.communicator import NotificationAgent  # noqa: E402


def main() -> int:
    resolver = build_default_engine()
    agent = NotificationAgent()

    incident = {
        "is_incident": True,
        "category": "Security breach",
        "severity": "critical",
        "priority": "P1",
    }

    resolution = resolver.resolve(incident)
    print("Resolution:", resolution)

    channels = ("console", "memory")
    for ch in channels:
        agent.send(incident, resolution, ch)

    assert len(agent.memory) == 1, "Memory notifications mismatch"
    assert "Security breach" in agent.memory[0], "Memory alert missing category"
    print("VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
