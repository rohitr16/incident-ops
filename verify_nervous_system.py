import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi.testclient import TestClient
from main import create_app

def main():
    from main import orchestrator
    
    # Decouple integration tests from production DB
    orchestrator.db_path = os.path.join(REPO_ROOT, "data", "test_incidents_api.db")
    if os.path.exists(orchestrator.db_path):
        try:
            os.remove(orchestrator.db_path)
        except OSError:
            pass
            
    from database import init_db
    init_db(orchestrator.db_path)
    app = create_app()
    client = TestClient(app)

    try:
        # 1. Health
        health = client.get("/health")
        assert health.status_code == 200, health.text
        assert health.json() == {"status": "ok"}
        print("[PASS] /health")

        # 2. Incidents list
        list_resp = client.get("/incidents")
        assert list_resp.status_code == 200, list_resp.text
        assert isinstance(list_resp.json(), list)
        print("[PASS] /incidents")

        # 3. Ingest pipeline
        resp = client.post("/ingest", json={"source": "test.log"})
        assert resp.status_code == 200, f"ingest failed: {resp.status_code}: {resp.text}"
        body = resp.json()
        required = {"incident_id", "source", "structured_log", "detection", "triage", "resolution", "notification"}
        missing = required - set(body.keys())
        assert not missing, f"Missing keys in response: {missing}"
        incident_id = body["incident_id"]
        assert body["resolution"]["status"] == "pending"

        # Verify background execution finished using /incidents
        list_res = client.get("/incidents")
        incidents = list_res.json()
        ingested = next(inc for inc in incidents if inc["incident_id"] == incident_id)
        assert ingested["resolution"]["status"] in ("resolved", "escalated")

        # Test step execution endpoint
        steps_payload = {"steps_executed": ["Step A"]}
        resp_steps = client.post(f"/incidents/{incident_id}/steps", json=steps_payload)
        assert resp_steps.status_code == 200, resp_steps.text
        body_steps = resp_steps.json()
        assert body_steps["resolution"]["steps_executed"] == ["Step A"]

        # Test resolve endpoint
        resp_resolve = client.post(f"/incidents/{incident_id}/resolve")
        assert resp_resolve.status_code == 200, resp_resolve.text
        body_resolve = resp_resolve.json()
        assert body_resolve["resolution"]["status"] == "resolved"

        # 4. LLM integration & fallback verification
        # Verify llm_service is initialized on orchestrator
        assert hasattr(orchestrator, "llm_service"), "orchestrator does not have llm_service"
        from services.llm import LLMService
        assert isinstance(orchestrator.llm_service, LLMService), "orchestrator.llm_service is not an instance of LLMService"
        print("[PASS] LLMService initialization checked")

        # Test case A: LLM succeeds (returns specific mock output)
        original_analyze = orchestrator.llm_service.analyze_incident
        async def mock_success_analyze(raw_line, severity):
            return {
                "category": "Storage",
                "priority": "P1",
                "recommendation": "Mocked LLM recommendation"
            }
        orchestrator.llm_service.analyze_incident = mock_success_analyze
        try:
            resp_success = client.post("/ingest", json={"source": "test_llm_success.log"})
            assert resp_success.status_code == 200, f"success ingest failed: {resp_success.text}"
            body_success = resp_success.json()
            assert body_success["resolution"]["status"] == "pending"

            list_res = client.get("/incidents")
            success_incident = next(inc for inc in list_res.json() if inc["source"] == "test_llm_success.log")
            assert success_incident["triage"]["category"] == "Storage"
            assert success_incident["triage"]["priority"] == "P1"
            assert success_incident["resolution"]["recommendation"] == "Mocked LLM recommendation"
            print("[PASS] Ingest pipeline with LLM success")
        finally:
            orchestrator.llm_service.analyze_incident = original_analyze

        # Test case B: LLM fails (raises Exception) -> Fallback should happen
        async def mock_fail_analyze(raw_line, severity):
            raise RuntimeError("Simulated LLM failure")
        orchestrator.llm_service.analyze_incident = mock_fail_analyze
        try:
            resp_fail = client.post("/ingest", json={"source": "test_llm_fail.log"})
            assert resp_fail.status_code == 200, f"fail ingest failed: {resp_fail.text}"
            body_fail = resp_fail.json()
            assert body_fail["resolution"]["status"] == "pending"

            list_res = client.get("/incidents")
            fail_incident = next(inc for inc in list_res.json() if inc["source"] == "test_llm_fail.log")
            # Triage and resolution should fall back to rules
            expected_triage = orchestrator.triage_agent.transform(fail_incident["detection"])
            expected_res = orchestrator.resolution_engine.resolve(expected_triage)
            
            assert fail_incident["triage"]["category"] == expected_triage["category"]
            assert fail_incident["triage"]["priority"] == expected_triage["priority"]
            assert fail_incident["resolution"]["recommendation"] == expected_res["recommendation"]
            print("[PASS] Ingest pipeline with LLM fallback")
        finally:
            orchestrator.llm_service.analyze_incident = original_analyze

        print("VERIFIED")

    finally:
        # Ensure test database cleanup including WAL and SHM files
        if 'orchestrator' in locals() or 'orchestrator' in globals():
            for suffix in ["", "-wal", "-shm"]:
                p = orchestrator.db_path + suffix
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

if __name__ == "__main__":
    main()
