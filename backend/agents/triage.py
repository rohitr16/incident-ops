import re


class TriageAgent:
    CATEGORIES = ["Network", "Security", "Compute", "Storage", "Application"]
    PRIORITIES = ["P0", "P1", "P2", "P3", "P4"]

    SEVERITY_PRIORITY_MAP = {
        "CRITICAL": "P0",
        "FATAL": "P0",
        "ERROR": "P1",
        "WARNING": "P2",
        "INFO": "P3",
    }

    CATEGORY_KEYWORDS = {
        "Network": ["network", "dns", "tcp", "udp", "ip", "router", "switch", "latency", "packet"],
        "Security": ["auth", "security", "breach", "firewall", "login", "encryption", "certificate", "outage", "down"],
        "Compute": ["cpu", "memory", "oom", "process", "thread", "kernel", "panic", "crash", "exception"],
        "Storage": ["disk", "storage", "db", "database", "volume", "filesystem", "latency", "down"],
        "Application": ["app", "service", "api", "endpoint", "queue", "timeout", "failed", "exception"],
    }

    def categorize(self, incident: dict) -> str:
        text = " ".join([
            str(incident.get("severity", "")),
            str(incident.get("source", "")),
            str(incident.get("reasoning", "")),
            str(incident.get("message", "")),
        ]).lower()

        matches = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in text)
            if count:
                matches[category] = count

        if matches:
            return max(matches.items(), key=lambda item: item[1])[0]
        return "Application"

    def priority(self, incident: dict) -> str:
        category = incident.get("category") or self.categorize(incident)
        severity = (incident.get("severity") or "INFO").upper()

        base = self.SEVERITY_PRIORITY_MAP.get(severity, "P4")

        escalate_categories = {"Security", "Network", "Storage"}
        escalate_keywords = ["panic", "outage", "down", "crash", "fatal", "critical"]
        text = " ".join([
            str(incident.get("source", "")),
            str(incident.get("reasoning", "")),
            str(incident.get("message", "")),
        ]).lower()

        if category in escalate_categories or any(kw in text for kw in escalate_keywords):
            if base in ("P0", "P1"):
                return base
            if base == "P2":
                return "P1"
            if base in ("P3", "P4"):
                return "P2"

        return base

    def transform(self, incident: dict) -> dict:
        category = self.categorize(incident)
        priority = self.priority(incident)

        updated = dict(incident)
        updated["category"] = category
        updated["priority"] = priority
        return updated


if __name__ == "__main__":
    agent = TriageAgent()
    sample = {
        "is_incident": True,
        "severity": "ERROR",
        "category": None,
        "reasoning": "Incident detected. Message contains keywords: ['timeout'].",
        "source": "auth_service",
        "message": "Connection timeout",
    }
    print(agent.transform(sample))
