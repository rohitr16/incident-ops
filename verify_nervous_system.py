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
    app = create_app()
    client = TestClient(app)

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
    print("[PASS] /ingest")
    print(json.dumps(body, indent=2))

    print("VERIFIED")

if __name__ == "__main__":
    main()
