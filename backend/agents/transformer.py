import re
import json

class LogTransformer:
    def __init__(self):
        # Pattern: timestamp SEVERITY source: message
        # Example: 2026-07-01 15:30:00 ERROR auth_service: Failed login attempt
        self.pattern = re.compile(r'^(?P<timestamp>[\d\- :]+)\s+(?P<severity>\w+)\s+(?P<source>[^:]+):\s+(?P<message>.*)$')

    def transform(self, raw_line: str) -> dict:
        match = self.pattern.match(raw_line)
        if match:
            return match.groupdict()
        return {
            "timestamp": None,
            "severity": "UNKNOWN",
            "source": "unknown",
            "message": raw_line
        }

if __name__ == "__main__":
    # Quick test
    transformer = LogTransformer()
    test_line = "2026-07-01 15:30:00 ERROR auth_service: Failed login attempt"
    print(f"Testing with: {test_line}")
    print(f"Result: {transformer.transform(test_line)}")
