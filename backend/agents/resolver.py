from __future__ import annotations

from typing import Any


class ResolutionEngine:
    """Registry of resolution playbooks and resolver."""

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], list[str]] = {}

    def register_playbook(self, category: str, severity: str, steps: list[str]) -> None:
        self._registry[(category, severity)] = list(steps)

    def resolve(self, incident_dict: dict[str, Any]) -> dict[str, Any]:
        category = incident_dict.get("category", "unknown")
        severity = incident_dict.get("severity", "low")
        is_incident = incident_dict.get("is_incident", False)

        if not is_incident:
            return {
                "status": "pending",
                "playbook_used": None,
                "steps_executed": [],
                "recommendation": "No incident detected; monitor."
            }

        key = (category, severity)
        steps = self._registry.get(key, [])

        if key not in self._registry:
            status = "escalated"
            recommendation = f"No registered playbook for {category}/{severity}."
        else:
            status = "resolved"
            recommendation = f"Applied playbook steps for {category}/{severity}."

        return {
            "status": status,
            "playbook_used": self._registry.get(key),
            "steps_executed": list(steps),
            "recommendation": recommendation,
        }


def build_default_engine() -> ResolutionEngine:
    engine = ResolutionEngine()
    engine.register_playbook("Network timeout", "high", [
        "Verify upstream service health endpoints",
        "Check DNS resolution for affected hosts",
        "Review network peering logs for packet loss",
        "Restart border routers if anomalous",
        "Fail over to secondary uplink",
    ])
    engine.register_playbook("Security breach", "critical", [
        "Isolate impacted subnet from production",
        "Capture memory dump from compromised node",
        "Rotate exposed credentials and API keys",
        "Enable enhanced logging in firewall rules",
        "Notify security operations and compliance",
    ])
    engine.register_playbook("Compute overload", "medium", [
        "Identify runaway processes via CPU profiling",
        "Scale horizontal workers to reduce load",
        "Throttle low priority background jobs",
        "Enable autoscaling thresholds for headroom",
        "Review recent deployments for regression",
    ])
    engine.register_playbook("Storage full", "high", [
        "Audit disk consumption by directory",
        "Purge rotated logs exceeding retention",
        "Compress inactive datasets",
        "Expand persistent volume capacity",
        "Set disk usage alert at 80% threshold",
    ])
    engine.register_playbook("Application crash", "medium", [
        "Collect application error logs and stack traces",
        "Restart crashed service instance",
        "Validate dependencies and connectivity",
        "Smoke test critical user journeys",
        "Create postmortem ticket for review",
    ])
    return engine
