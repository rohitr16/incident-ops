import re

class IncidentDetector:
    CRITICAL_SEVERITIES = {"ERROR", "CRITICAL", "FATAL"}
    INCIDENT_KEYWORDS = [
        "timeout", "failed", "crash", "down", "outage", "exception", "panic"
    ]

    def transform(self, structured_log: dict) -> dict:
        severity = structured_log.get("severity", "UNKNOWN")
        message = structured_log.get("message", "") or ""

        is_incident = False
        reasons = []

        if severity in self.CRITICAL_SEVERITIES:
            is_incident = True
            reasons.append(f"Severity is '{severity}'")

        lowered = message.lower()
        matched_keywords = [kw for kw in self.INCIDENT_KEYWORDS if kw in lowered]
        if matched_keywords:
            is_incident = True
            reasons.append(f"Message contains keywords: {matched_keywords}")

        if not reasons:
            reasoning = "No incident indicators found."
        else:
            reasoning = "Incident detected. " + "; ".join(reasons) + "."

        return {
            "is_incident": is_incident,
            "severity": severity,
            "category": None,
            "reasoning": reasoning,
        }

if __name__ == "__main__":
    detector = IncidentDetector()
    sample = {"severity": "ERROR", "source": "svc", "message": "Connection timeout"}
    print(detector.transform(sample))
