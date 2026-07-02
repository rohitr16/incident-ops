import os
import sys
import json

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

        print("VERIFIED")

    finally:
        # Ensure test database cleanup
        if os.path.exists(orchestrator.db_path):
            try:
                os.remove(orchestrator.db_path)
            except OSError:
                pass

if __name__ == "__main__":
    main()
