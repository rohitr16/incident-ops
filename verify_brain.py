import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.append(str(backend_dir))

from agents.detector import IncidentDetector
from agents.transformer import LogTransformer

def main():
    transformer = LogTransformer()
    detector = IncidentDetector()

    critical_raw = "2026-07-01 15:30:00 CRITICAL database: Connection failed: panic in storage engine"
    normal_raw = "2026-07-01 15:31:00 INFO scheduler: Health check passed"

    critical_structured = transformer.transform(critical_raw)
    normal_structured = transformer.transform(normal_raw)

    critical_result = detector.transform(critical_structured)
    normal_result = detector.transform(normal_structured)

    assert critical_result["is_incident"] is True, critical_result
    assert normal_result["is_incident"] is False, normal_result
    assert critical_result["severity"] == "CRITICAL"
    assert normal_result["severity"] == "INFO"

    print("VERIFIED")

if __name__ == "__main__":
    main()
