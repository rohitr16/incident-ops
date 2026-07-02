import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.append(str(backend_dir))

from agents.detector import IncidentDetector
from agents.transformer import LogTransformer
from database import init_db, save_incident, get_all_incidents

import asyncio

async def test_llm_service():
    from services.llm import LLMService
    # Test fallback to empty/mock on invalid config
    svc = LLMService(provider="mock", model="mock")
    res = await svc.analyze_incident("Connection timeout to DB", "ERROR")
    assert res["category"] == "Application"
    assert res["priority"] == "P1"
    assert "Connection timeout" in res["recommendation"]

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

    db_test_path = "data/test_incidents.db"
    import os
    if os.path.exists(db_test_path):
        os.remove(db_test_path)
    init_db(db_test_path)
    
    try:
        dummy = {
            "source": "test_db.log",
            "raw_line": "ERROR: fail",
            "structured_log": {"message": "fail", "severity": "ERROR"},
            "detection": {"is_incident": True},
            "triage": {"category": "Application", "priority": "P1"},
            "resolution": {"status": "pending", "playbook_used": ["Step A", "Step B"], "steps_executed": []},
            "notification": "Alert!"
        }
        saved = save_incident(dummy, db_test_path)
        assert saved["incident_id"] == 1
        assert saved["resolution"]["status"] == "pending"
        
        all_incidents = get_all_incidents(db_test_path)
        assert len(all_incidents) == 1
        assert all_incidents[0]["source"] == "test_db.log"
        assert all_incidents[0]["resolution"]["playbook_used"] == ["Step A", "Step B"]

        # Test update_playbook_steps and resolve_incident
        from database import update_playbook_steps, resolve_incident
        updated = update_playbook_steps(1, ["Step A"], db_test_path)
        assert updated["resolution"]["steps_executed"] == ["Step A"]
        assert updated["resolution"]["status"] == "pending"
        
        # Test resolving via update_playbook_steps (when all steps completed)
        updated_resolved = update_playbook_steps(1, ["Step A", "Step B"], db_test_path)
        assert updated_resolved["resolution"]["steps_executed"] == ["Step A", "Step B"]
        assert updated_resolved["resolution"]["status"] == "resolved"
        
        # Test resolve_incident
        # Let's reset it back to pending first to test resolve_incident
        update_playbook_steps(1, [], db_test_path)
        resolved = resolve_incident(1, db_test_path)
        assert resolved["resolution"]["status"] == "resolved"
        assert resolved["resolution"]["steps_executed"] == ["Step A", "Step B"]
    finally:
        for suffix in ["", "-wal", "-shm"]:
            p = db_test_path + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    asyncio.run(test_llm_service())
    print("VERIFIED")

if __name__ == "__main__":
    main()

