# Incident Dashboard Persistence & Interactive Playbooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist incident data in a local SQLite database, add API endpoints for interactive playbook checklist updates, and build a split-pane frontend UI to track resolution progress in real-time.

**Architecture:** Integrate a local SQLite database (`data/incidents.db`) via python's native `sqlite3` module. Replace the backend's in-memory list with database operations, add checklist update and manual resolution endpoints to FastAPI, and restructure the Next.js frontend into a dual-pane split view containing a scrollable feed and an interactive details inspector.

**Tech Stack:** Python 3, FastAPI, SQLite, Next.js, WebSockets

## Global Constraints

- Database persistence: Local SQLite database file at `data/incidents.db`.
- Database Table Name: `incidents` with fields mapping structured log info and playbook execution state.
- Split View Layout: Left pane for the incident feed (40% width), right pane for the inspector sidebar (60% width).
- In-place Updates: Mark incidents as resolved/completed in-place and push real-time updates via WebSockets.

---

### Task 1: SQLite Database Setup & Pipeline Integration

**Files:**
- Create: `backend/database.py`
- Modify: `backend/orchestrator.py`
- Modify: `verify_brain.py`

**Interfaces:**
- Consumes: Dictionary logs processed by the processing pipeline.
- Produces:
  - `init_db(db_path: str)` -> Creates table `incidents` if not exists.
  - `save_incident(incident: dict, db_path: str)` -> Inserts a new incident (converting dictionary/list metadata to JSON strings) and returns the inserted dictionary with its database `incident_id`.
  - `get_all_incidents(db_path: str)` -> Retrieves all incidents from the DB, parsing JSON strings back into dictionaries.
  - `update_playbook_steps(incident_id: int, steps_executed: list[str], db_path: str)` -> Updates executed steps for the incident and updates `updated_at`.
  - `resolve_incident(incident_id: int, db_path: str)` -> Sets status to `'resolved'` and completed steps to match all playbook steps.

- [ ] **Step 1: Write the failing test**

Add assertions to `verify_brain.py` to test database initialization, saving, and retrieval:
```python
# Insert at lines 9-10 in verify_brain.py
from database import init_db, save_incident, get_all_incidents

# Insert at the end of main() in verify_brain.py (before print("VERIFIED")):
    db_test_path = "data/test_incidents.db"
    import os
    if os.path.exists(db_test_path):
        os.remove(db_test_path)
    init_db(db_test_path)
    
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python verify_brain.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'database'` or similar import error.

- [ ] **Step 3: Write database helper module**

Create `backend/database.py` with sqlite3 helper functions:
```python
import sqlite3
import json
import os
from typing import List, Dict, Any

def init_db(db_path: str = "data/incidents.db") -> None:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            raw_line TEXT,
            structured_log TEXT,
            detection TEXT,
            triage TEXT,
            resolution_status TEXT,
            playbook_steps TEXT,
            steps_executed TEXT,
            recommendation TEXT,
            notification TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def save_incident(incident: Dict[str, Any], db_path: str = "data/incidents.db") -> Dict[str, Any]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    struct_log = incident.get("structured_log") or {}
    detection = incident.get("detection") or {}
    triage = incident.get("triage") or {}
    res = incident.get("resolution") or {}
    
    playbook_steps = res.get("playbook_used") or []
    steps_executed = res.get("steps_executed") or []
    status = res.get("status") or "pending"
    recommendation = res.get("recommendation") or ""
    notification = incident.get("notification") or ""
    
    cursor.execute("""
        INSERT INTO incidents (
            source, raw_line, structured_log, detection, triage, 
            resolution_status, playbook_steps, steps_executed, 
            recommendation, notification
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        incident.get("source"),
        incident.get("raw_line"),
        json.dumps(struct_log),
        json.dumps(detection),
        json.dumps(triage),
        status,
        json.dumps(playbook_steps),
        json.dumps(steps_executed),
        recommendation,
        notification
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    
    updated_incident = dict(incident)
    updated_incident["incident_id"] = new_id
    return updated_incident

def get_all_incidents(db_path: str = "data/incidents.db") -> List[Dict[str, Any]]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents ORDER BY incident_id ASC")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        results.append({
            "incident_id": row["incident_id"],
            "source": row["source"],
            "raw_line": row["raw_line"],
            "structured_log": json.loads(row["structured_log"] or "{}"),
            "detection": json.loads(row["detection"] or "{}"),
            "triage": json.loads(row["triage"] or "{}"),
            "resolution": {
                "status": row["resolution_status"],
                "playbook_used": json.loads(row["playbook_steps"] or "[]"),
                "steps_executed": json.loads(row["steps_executed"] or "[]"),
                "recommendation": row["recommendation"],
            },
            "notification": row["notification"]
        })
    return results

def update_playbook_steps(incident_id: int, steps_executed: List[str], db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get total playbook steps to check if fully resolved
    cursor.execute("SELECT playbook_steps FROM incidents WHERE incident_id = ?", (incident_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Incident {incident_id} not found")
        
    playbook_steps = json.loads(row["playbook_steps"] or "[]")
    
    # If all steps completed, transition to resolved
    status = "pending"
    if len(steps_executed) >= len(playbook_steps) and len(playbook_steps) > 0:
        status = "resolved"
        
    cursor.execute("""
        UPDATE incidents 
        SET steps_executed = ?, resolution_status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE incident_id = ?
    """, (json.dumps(steps_executed), status, incident_id))
    conn.commit()
    
    cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
    row = cursor.fetchone()
    conn.close()
    
    return {
        "incident_id": row["incident_id"],
        "source": row["source"],
        "raw_line": row["raw_line"],
        "structured_log": json.loads(row["structured_log"] or "{}"),
        "detection": json.loads(row["detection"] or "{}"),
        "triage": json.loads(row["triage"] or "{}"),
        "resolution": {
            "status": row["resolution_status"],
            "playbook_used": playbook_steps,
            "steps_executed": steps_executed,
            "recommendation": row["recommendation"],
        },
        "notification": row["notification"]
    }

def resolve_incident(incident_id: int, db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT playbook_steps FROM incidents WHERE incident_id = ?", (incident_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Incident {incident_id} not found")
        
    playbook_steps = json.loads(row["playbook_steps"] or "[]")
    
    cursor.execute("""
        UPDATE incidents 
        SET resolution_status = 'resolved', steps_executed = ?, updated_at = CURRENT_TIMESTAMP
        WHERE incident_id = ?
    """, (json.dumps(playbook_steps), incident_id))
    conn.commit()
    
    cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
    row = cursor.fetchone()
    conn.close()
    
    return {
        "incident_id": row["incident_id"],
        "source": row["source"],
        "raw_line": row["raw_line"],
        "structured_log": json.loads(row["structured_log"] or "{}"),
        "detection": json.loads(row["detection"] or "{}"),
        "triage": json.loads(row["triage"] or "{}"),
        "resolution": {
            "status": row["resolution_status"],
            "playbook_used": playbook_steps,
            "steps_executed": playbook_steps,
            "recommendation": row["recommendation"],
        },
        "notification": row["notification"]
    }
```

- [ ] **Step 4: Hook DB into IncidentOrchestrator**

Modify `backend/orchestrator.py` to read/write from SQLite:
- In `__init__`, add `from database import init_db; init_db(self.logs_dir.replace('logs', 'data/incidents.db'))`
- Update `start_pipeline` to write to SQLite and return the saved dictionary:
```python
        # In backend/orchestrator.py - Replace line 82-87:
        from database import save_incident
        db_path = os.path.join(self.logs_dir, "..", "data", "incidents.db")
        response = save_incident(stored, db_path)
        return response
```
- In `backend/orchestrator.py` define a property to retrieve incidents from the DB:
```python
    @property
    def incidents_store(self) -> List[Dict[str, Any]]:
        from database import get_all_incidents
        db_path = os.path.join(self.logs_dir, "..", "data", "incidents.db")
        return get_all_incidents(db_path)
```

- [ ] **Step 5: Run tests and verify they pass**

Run: `python verify_brain.py`
Expected: `VERIFIED`

- [ ] **Step 6: Commit**

```bash
git add backend/database.py backend/orchestrator.py verify_brain.py
git commit -m "feat: setup SQLite database and integrate with pipeline"
```

---

### Task 2: API Endpoints Update (Playbook Steps & Resolve)

**Files:**
- Modify: `backend/api/routes.py`
- Modify: `verify_nervous_system.py`

**Interfaces:**
- Consumes:
  - `POST /incidents/{incident_id}/steps` with `{ "steps_executed": [...] }`
  - `POST /incidents/{incident_id}/resolve`
- Produces: Updated incident JSON broadcasted via WebSockets and returned in JSONResponse.

- [ ] **Step 1: Write failing tests**

Add assertions to `verify_nervous_system.py`:
```python
# Replace verification step 3 in verify_nervous_system.py:
# 3. Ingest pipeline
resp = client.post("/ingest", json={"source": "test.log"})
assert resp.status_code == 200, f"ingest failed: {resp.status_code}: {resp.text}"
body = resp.json()
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python verify_nervous_system.py`
Expected: FAIL with `404` status code on `/incidents/1/steps`.

- [ ] **Step 3: Implement route updates**

Modify `backend/api/routes.py`:
- Import DB update functions:
```python
from database import update_playbook_steps, resolve_incident
```
- Define new routes and update `list_incidents`:
```python
# Replace list_incidents with a database retrieval
@router.get("/incidents")
async def list_incidents():
    return JSONResponse(content=orchestrator.incidents_store)

@router.post("/incidents/{incident_id}/steps")
async def update_steps(incident_id: int, payload: dict):
    steps = payload.get("steps_executed", [])
    import os
    db_path = os.path.join(orchestrator.logs_dir, "..", "data", "incidents.db")
    updated = update_playbook_steps(incident_id, steps, db_path)
    await manager.broadcast(updated)
    return JSONResponse(content=updated)

@router.post("/incidents/{incident_id}/resolve")
async def resolve(incident_id: int):
    import os
    db_path = os.path.join(orchestrator.logs_dir, "..", "data", "incidents.db")
    updated = resolve_incident(incident_id, db_path)
    await manager.broadcast(updated)
    return JSONResponse(content=updated)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python verify_nervous_system.py`
Expected: `VERIFIED`

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes.py verify_nervous_system.py
git commit -m "feat: add FastAPI routes for playbook steps and resolution"
```

---

### Task 3: Frontend Split-Screen Layout & Checkable Playbook Checklist

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/IncidentCard.js`
- Modify: `frontend/app/IncidentDashboard.js`
- Modify: `verify_face.py`

**Interfaces:**
- Consumes: `/incidents` list and real-time WebSockets feed.
- Produces: React elements with classes `feed-panel`, `inspector-panel`, `playbook-checklist-container`, `checklist-step-checkbox`.

- [ ] **Step 1: Write failing checks**

Modify `verify_face.py` to check that the layout components are imported correctly and elements with split view class exist:
```python
# In verify_face.py, replace lines 16-20 (IMPORT_CHECKS) with:
IMPORT_CHECKS = {
    'layout.js': ["./globals.css"],
    'IncidentDashboard.js': ["./IncidentCard"],
    'page.js': ["./IncidentDashboard"],
}

# Add layout file validation in verify_face.py main():
# Before print('VERIFIED') insert:
    dashboard_path = ROOT / 'incident-dashboard-poc' / 'frontend' / 'app' / 'IncidentDashboard.js'
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'feed-panel' not in content or 'inspector-panel' not in content:
        print('MISSING: feed-panel or inspector-panel elements in IncidentDashboard.js')
        sys.exit(1)
```

- [ ] **Step 2: Run checks to verify they fail**

Run: `python verify_face.py`
Expected: FAIL with `MISSING: feed-panel or inspector-panel elements in IncidentDashboard.js`.

- [ ] **Step 3: Update CSS layout classes**

Append modern split-view CSS styling to `frontend/app/globals.css`:
```css
/* Split Layout */
.feed-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

.feed-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1.5rem;
  background-color: #ffffff;
  border-bottom: 1px solid #d1d1d6;
  flex-shrink: 0;
}

.feed-title {
  font-weight: 700;
  font-size: 1.25rem;
}

.status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.connected { background-color: #34c759; }
.status-dot.disconnected { background-color: #ff3b30; }

.main-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.feed-panel {
  width: 40%;
  border-right: 1px solid #d1d1d6;
  padding: 1.5rem;
  overflow-y: auto;
  background-color: #ffffff;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.inspector-panel {
  width: 60%;
  padding: 2rem;
  overflow-y: auto;
  background-color: #f5f5f7;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.empty {
  color: #86868b;
  text-align: center;
  padding: 3rem;
  font-size: 1rem;
}

/* Incident Cards */
.card {
  border: 1px solid #d1d1d6;
  border-radius: 12px;
  padding: 1.25rem;
  background-color: #ffffff;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.card:hover {
  border-color: #0071e3;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.card.active {
  border-color: #0071e3;
  border-width: 2px;
  background-color: #f5f9ff;
}

.card.resolving {
  opacity: 0.7;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 700;
  font-size: 1rem;
}

.badge {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  text-transform: uppercase;
}
.severity-critical { background-color: #ff3b30; color: white; }
.severity-fatal { background-color: #ff3b30; color: white; }
.severity-error { background-color: #ff9f0a; color: white; }
.severity-warning { background-color: #ffcc00; color: black; }
.severity-info { background-color: #0071e3; color: white; }

.card-meta {
  display: flex;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: #86868b;
}

.progress-container {
  margin-top: 0.25rem;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  font-weight: 600;
  color: #86868b;
  margin-bottom: 0.25rem;
}

.progress-bar-bg {
  width: 100%;
  height: 6px;
  background-color: #e5e5e7;
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease, background-color 0.3s ease;
}

/* Playbook Checklist */
.playbook-step {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background-color: #ffffff;
  border: 1px solid #d1d1d6;
  border-radius: 8px;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s;
  font-size: 0.9rem;
}

.playbook-step:hover {
  background-color: #f5f5f7;
}

.playbook-step.checked {
  border-color: #34c759;
  background-color: rgba(52, 199, 89, 0.05);
}

.playbook-step input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: #34c759;
  cursor: pointer;
}

/* Meta info grid */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  background-color: #ffffff;
  border: 1px solid #d1d1d6;
  border-radius: 12px;
  padding: 1.25rem;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.meta-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  color: #86868b;
}

.meta-val {
  font-size: 0.95rem;
  font-weight: 500;
}

.resolve-btn {
  background-color: #34c759;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s;
}

.resolve-btn:hover {
  background-color: #28a745;
}

.resolve-btn:disabled {
  background-color: #e5e5e7;
  color: #aeaeb2;
  cursor: not-allowed;
}

.debug {
  background-color: #1d1d1f;
  color: #34c759;
  font-family: monospace;
  padding: 1rem;
  height: 120px;
  overflow-y: auto;
  font-size: 0.75rem;
  border-top: 1px solid #d1d1d6;
  flex-shrink: 0;
}
```

- [ ] **Step 4: Implement checkable progress bar in IncidentCard**

Modify `frontend/app/IncidentCard.js` to render the completion bar:
```javascript
import { useMemo } from 'react';

function normalizeIncident(incident) {
  if (!incident || typeof incident !== 'object') return {};
  const structured = incident.structured_log || incident.structuredLog || {};
  const detection = incident.detection || {};
  const triage = incident.triage || {};
  const resolution = incident.resolution || {};
  return {
    id: incident.incident_id ?? incident.id ?? '#',
    severity: structured.severity ?? incident.severity ?? 'info',
    timestamp: incident.timestamp || structured.timestamp || detection.timestamp || triage.timestamp || '',
    priority: triage.priority || incident.priority || 'minor',
    category: triage.category || detection.category || incident.category || '',
    message: structured.message || incident.message || detection.summary || '',
    playbook_steps: resolution.playbook_used || [],
    steps_executed: resolution.steps_executed || [],
    status: resolution.status || 'pending',
  };
}

export default function IncidentCard({ incident, active, onClick }) {
  const data = normalizeIncident(incident);
  const severityClass = data.severity ? `severity-${data.severity.toLowerCase()}` : '';

  const pct = useMemo(() => {
    if (!data.playbook_steps.length) return 0;
    return Math.round((data.steps_executed.length / data.playbook_steps.length) * 100);
  }, [data.playbook_steps, data.steps_executed]);

  const barColor = useMemo(() => {
    if (data.status === 'resolved') return '#34c759';
    if (data.severity === 'CRITICAL' || data.severity === 'FATAL') return '#ff3b30';
    return '#ff9f0a';
  }, [data.status, data.severity]);

  return (
    <div 
      className={`card ${active ? 'active' : ''}`} 
      onClick={onClick}
    >
      <div className="card-header">
        <div className="card-title">INC-{data.id}</div>
        <div className={`badge ${severityClass}`}>{data.severity}</div>
      </div>
      <div className="card-meta">
        <span>{data.timestamp.split(' ')[1] || data.timestamp}</span>
        <span>{data.priority}</span>
        <span>{data.category}</span>
      </div>
      <div className="card-body" style={{ fontSize: '0.85rem', color: '#1d1d1f' }}>
        {data.message}
      </div>
      
      {data.playbook_steps.length > 0 && (
        <div className="progress-container">
          <div className="progress-header">
            <span>Playbook Checklist</span>
            <span>{pct}%</span>
          </div>
          <div className="progress-bar-bg">
            <div 
              className="progress-bar-fill" 
              style={{ width: `${pct}%`, backgroundColor: barColor }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Implement Split-Screen & Active Inspector in IncidentDashboard**

Modify `frontend/app/IncidentDashboard.js` to render the side-by-side dashboard layout and handle checklist API interactions:
```javascript
'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import IncidentCard from './IncidentCard';

const WS_URL = 'ws://localhost:8000/ws/incidents';
const API_URL = 'http://localhost:8000';

export default function IncidentDashboard() {
  const [incidents, setIncidents] = useState([]);
  const [activeIncidentId, setActiveIncidentId] = useState(null);
  const [connected, setConnected] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [debugLog, setDebugLog] = useState([]);
  const pollRef = useRef(null);

  const log = useCallback((msg) => {
    const time = new Date().toISOString().split('T')[1].slice(0, -1);
    setDebugLog((prev) => [...prev.slice(-30), `[${time}] ${msg}`]);
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/incidents`);
      const data = await res.json();
      setIncidents(Array.isArray(data) ? data : []);
    } catch (e) {
      log(`/incidents ERROR: ${e?.message || e}`);
    }
  }, [log]);

  useEffect(() => {
    load();
    pollRef.current = setInterval(load, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [load]);

  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(WS_URL);
      ws.addEventListener('open', () => {
        setConnected(true);
        log('WS Connected');
      });
      ws.addEventListener('close', () => {
        setConnected(false);
        log('WS Disconnected');
      });
      ws.addEventListener('message', (event) => {
        try {
          const parsed = JSON.parse(event.data || '{}');
          if (parsed && parsed.incident_id) {
            setIncidents((prev) => {
              const exists = prev.find((item) => item.incident_id === parsed.incident_id);
              if (exists) return prev.map((item) => (item.incident_id === parsed.incident_id ? { ...item, ...parsed } : item));
              return [...prev, parsed];
            });
          }
        } catch (e) {
          log('WS msg non-json');
        }
      });
    } catch (e) {
      log(`WS error: ${e?.message || e}`);
    }
    return () => { if (ws) ws.close(); };
  }, [log]);

  const activeIncident = incidents.find(
    (inc) => (inc.incident_id ?? inc.id) === activeIncidentId
  );

  // Auto-select first incident on load
  useEffect(() => {
    if (incidents.length > 0 && activeIncidentId === null) {
      setActiveIncidentId(incidents[0].incident_id ?? incidents[0].id);
    }
  }, [incidents, activeIncidentId]);

  const toggleStep = async (step) => {
    if (!activeIncident || isUpdating) return;
    setIsUpdating(true);
    
    const currentSteps = activeIncident.resolution?.steps_executed || [];
    let updatedSteps;
    if (currentSteps.includes(step)) {
      updatedSteps = currentSteps.filter((s) => s !== step);
    } else {
      updatedSteps = [...currentSteps, step];
    }
    
    try {
      const res = await fetch(`${API_URL}/incidents/${activeIncidentId}/steps`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ steps_executed: updatedSteps }),
      });
      if (res.ok) {
        const data = await res.json();
        setIncidents((prev) =>
          prev.map((item) => ((item.incident_id ?? item.id) === activeIncidentId ? data : item))
        );
      }
    } catch (e) {
      log(`Update steps error: ${e?.message || e}`);
    } finally {
      setIsUpdating(false);
    }
  };

  const resolveIncident = async () => {
    if (!activeIncident || isUpdating) return;
    setIsUpdating(true);
    
    try {
      const res = await fetch(`${API_URL}/incidents/${activeIncidentId}/resolve`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setIncidents((prev) =>
          prev.map((item) => ((item.incident_id ?? item.id) === activeIncidentId ? data : item))
        );
      }
    } catch (e) {
      log(`Resolve error: ${e?.message || e}`);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="feed-root">
      <div className="feed-header">
        <div className="feed-title">⚡ Ops-Center Dash</div>
        <div className="status">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span>{connected ? 'WebSocket Live' : 'Disconnected (Polling)'}</span>
        </div>
      </div>

      <div className="main-layout">
        
        {/* Left Side: Incidents Feed */}
        <div className="feed-panel">
          {incidents.length === 0 && <div className="empty">No active incidents.</div>}
          {incidents.map((incident) => {
            const incId = incident.incident_id ?? incident.id;
            return (
              <IncidentCard
                key={incId}
                incident={incident}
                active={activeIncidentId === incId}
                onClick={() => setActiveIncidentId(incId)}
              />
            );
          })}
        </div>

        {/* Right Side: Inspector Panel */}
        <div className="inspector-panel">
          {activeIncident ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #d1d1d6', paddingBottom: '0.75rem' }}>
                <h2 style={{ margin: 0 }}>INC-{activeIncident.incident_id}: {activeIncident.structured_log?.message || 'Storage Overload'}</h2>
                <span style={{ fontSize: '0.8rem', color: '#86868b' }}>
                  {activeIncident.structured_log?.timestamp || activeIncident.timestamp || 'N/A'}
                </span>
              </div>

              <div className="meta-grid">
                <div className="meta-item">
                  <span class="meta-label">Severity</span>
                  <span class="meta-val" style={{ color: activeIncident.structured_log?.severity === 'CRITICAL' ? '#ff3b30' : '#ff9f0a' }}>
                    {activeIncident.structured_log?.severity}
                  </span>
                </div>
                <div className="meta-item">
                  <span class="meta-label">Priority</span>
                  <span class="meta-val">{activeIncident.triage?.priority}</span>
                </div>
                <div className="meta-item">
                  <span class="meta-label">Category</span>
                  <span class="meta-val">{activeIncident.triage?.category}</span>
                </div>
                <div className="meta-item">
                  <span class="meta-label">Source Host</span>
                  <span class="meta-val"><code>{activeIncident.source}</code></span>
                </div>
              </div>

              {activeIncident.resolution?.playbook_used?.length > 0 ? (
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.8rem', color: '#86868b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.75rem' }}>
                    Playbook Steps
                  </div>
                  {activeIncident.resolution.playbook_used.map((step, idx) => {
                    const isChecked = activeIncident.resolution.steps_executed?.includes(step);
                    return (
                      <div 
                        key={idx} 
                        className={`playbook-step ${isChecked ? 'checked' : ''}`}
                        onClick={() => toggleStep(step)}
                      >
                        <input 
                          type="checkbox" 
                          checked={isChecked} 
                          onChange={() => {}} // handled by click
                        />
                        <span style={isChecked ? { textDecoration: 'line-through', color: '#86868b' } : {}}>
                          {step}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ color: '#86868b', fontStyle: 'italic', fontSize: '0.9rem' }}>
                  No registered playbook for this incident category/severity.
                </div>
              )}

              <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid #d1d1d6', display: 'flex', justifyContent: 'flex-end' }}>
                <button 
                  onClick={resolveIncident} 
                  disabled={activeIncident.resolution?.status === 'resolved' || isUpdating}
                  className="resolve-btn"
                >
                  {activeIncident.resolution?.status === 'resolved' ? '✓ Resolved' : 'Mark as Resolved'}
                </button>
              </div>
            </>
          ) : (
            <div className="empty">Select an incident from the feed to inspect.</div>
          )}
        </div>

      </div>

      <div className="debug">
        <div style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>SYSTEM EVENT LOG</div>
        {debugLog.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run checks to verify they pass**

Run: `python verify_face.py`
Expected: `VERIFIED`

- [ ] **Step 7: Commit**

```bash
git add frontend/app/globals.css frontend/app/IncidentCard.js frontend/app/IncidentDashboard.js verify_face.py
git commit -m "feat: implement split view layout and checkable playbook UI"
```
