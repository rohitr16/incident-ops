# LangGraph Multi-Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a background-runnable LangGraph multi-agent pipeline into the FastAPI backend and build a real-time Collapsible Agent Timeline Sidebar in the Next.js frontend.

**Architecture:** A compiled LangGraph `StateGraph` will manage the multi-agent execution pipeline. When a log is ingested, the API returns immediately and executes the graph in a FastAPI `BackgroundTask`. As nodes execute, they write updates to SQLite and broadcast the incident state over WebSockets to be rendered by a vertical timeline in the frontend sidebar.

**Tech Stack:** FastAPI, SQLite, WebSockets, Next.js (React), LangGraph.

## Global Constraints

- **Backend dependencies**: Add `langgraph` without disrupting existing packages.
- **Database Schema**: Add `agent_history` column to `incidents` table. Enable WAL/thread-safe SQLite configurations.
- **UI Layout**: Implement a collapsible sidebar timeline panel alongside the playbook checklist.

---

### Task 1: Backend Dependencies & Database Extension

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/database.py`
- Modify: `verify_brain.py`

**Interfaces:**
- Produces: `update_agent_history(incident_id: int, entry: dict, db_path: Optional[str] = None) -> dict`

- [ ] **Step 1: Update backend requirements**
  Add `langgraph` to `backend/requirements.txt`.
  ```text
  fastapi
  uvicorn
  websockets
  sqlalchemy
  pydantic
  google-generativeai
  python-dotenv
  pandas
  psycopg2-binary
  openai
  google-genai
  langgraph
  ```

- [ ] **Step 2: Install dependencies**
  Run: `pip install -r backend/requirements.txt`
  Expected: Installation completes successfully.

- [ ] **Step 3: Add test code for database extension in `verify_brain.py`**
  Modify `verify_brain.py` to add `test_database_agent_history` to `main()` (lines 94-97):
  ```python
      # Add to verify_brain.py main test function
      from database import update_agent_history
      # Initialize test db
      db_test_path = "data/test_incidents.db"
      history_entry = {
          "node": "SmartQueue",
          "status": "completed",
          "message": "Triage done",
          "timestamp": "2026-07-02T21:30:00Z"
      }
      updated = update_agent_history(1, history_entry, db_test_path)
      assert len(updated["agent_history"]) == 1
      assert updated["agent_history"][0]["node"] == "SmartQueue"
  ```

- [ ] **Step 4: Run verify_brain.py to check failure**
  Run: `python3 verify_brain.py`
  Expected: FAIL with `ImportError: cannot import name 'update_agent_history'`.

- [ ] **Step 5: Modify `backend/database.py` to support `agent_history`**
  Add `agent_history` column in `init_db`, update save/retrieval functions, and implement `update_agent_history`.
  ```python
  # In backend/database.py:
  # 1. Update init_db to add agent_history if not present:
  def init_db(db_path: str) -> None:
      import sqlite3
      with sqlite3.connect(db_path) as conn:
          cursor = conn.cursor()
          cursor.execute("""
              CREATE TABLE IF NOT EXISTS incidents (
                  incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source TEXT NOT NULL,
                  raw_line TEXT,
                  structured_log TEXT NOT NULL,
                  detection TEXT NOT NULL,
                  triage TEXT NOT NULL,
                  resolution_status TEXT NOT NULL,
                  playbook_steps TEXT,
                  steps_executed TEXT,
                  recommendation TEXT,
                  notification TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              );
          """)
          # Check if agent_history exists, if not, add it
          cursor.execute("PRAGMA table_info(incidents);")
          columns = [info[1] for info in cursor.fetchall()]
          if "agent_history" not in columns:
              cursor.execute("ALTER TABLE incidents ADD COLUMN agent_history TEXT DEFAULT '[]';")
          conn.commit()

  # 2. Modify save_incident to serialize agent_history:
  # In save_incident, extract and save stored.get("agent_history", []) as JSON string:
  # query:
  # INSERT INTO incidents (..., agent_history) VALUES (..., ?)
  # 3. Modify get_all_incidents to deserialize agent_history:
  # row[12] for agent_history: json.loads(row[12]) if row[12] else []
  # 4. Implement update_agent_history:
  def update_agent_history(incident_id: int, entry: dict, db_path: str) -> dict:
      import sqlite3
      import json
      from database import _get_incident_by_id
      with sqlite3.connect(db_path) as conn:
          conn.execute("BEGIN TRANSACTION;")
          try:
              cursor = conn.cursor()
              cursor.execute("SELECT agent_history FROM incidents WHERE incident_id = ?", (incident_id,))
              row = cursor.fetchone()
              if not row:
                  raise ValueError(f"Incident {incident_id} not found")
              history = json.loads(row[0]) if row[0] else []
              history.append(entry)
              cursor.execute(
                  "UPDATE incidents SET agent_history = ?, updated_at = CURRENT_TIMESTAMP WHERE incident_id = ?",
                  (json.dumps(history), incident_id)
              )
              conn.commit()
          except Exception:
              conn.rollback()
              raise
      return _get_incident_by_id(incident_id, db_path)
  ```

- [ ] **Step 6: Run verify_brain.py to check pass**
  Run: `python3 verify_brain.py`
  Expected: PASS.

- [ ] **Step 7: Commit**
  ```bash
  git add backend/requirements.txt backend/database.py verify_brain.py
  git commit -m "feat: extend SQLite schema and database utilities to support agent_history"
  ```

---

### Task 2: Implement the LangGraph Workflow Engine

**Files:**
- Create: `backend/services/graph.py`
- Modify: `verify_brain.py`

**Interfaces:**
- Produces: `async def run_langgraph_pipeline(incident_id: int, raw_log: str, severity: str, db_path: str, broadcast_fn) -> None`

- [ ] **Step 1: Add LangGraph workflow execution test to `verify_brain.py`**
  Add mock test to `verify_brain.py`:
  ```python
  # Add to verify_brain.py
  async def test_langgraph_workflow():
      from services.graph import run_langgraph_pipeline
      db_test_path = "data/test_incidents.db"
      broadcasts = []
      async def mock_broadcast(incident):
          broadcasts.append(incident)
      
      # We need to pre-create a pending incident
      from database import save_incident
      dummy = {
          "source": "test_graph.log",
          "raw_line": "ERROR: database connection error timeout",
          "structured_log": {"message": "database connection error timeout", "severity": "ERROR"},
          "detection": {"is_incident": True, "severity": "ERROR"},
          "triage": {"category": "Application", "priority": "P4"},
          "resolution": {"status": "pending", "playbook_used": [], "steps_executed": []},
          "notification": "Alert!"
      }
      saved = save_incident(dummy, db_test_path)
      
      await run_langgraph_pipeline(
          incident_id=saved["incident_id"],
          raw_log="ERROR: database connection error timeout",
          severity="ERROR",
          db_path=db_test_path,
          broadcast_fn=mock_broadcast
      )
      
      assert len(broadcasts) > 0
      final_incident = broadcasts[-1]
      assert final_incident["resolution"]["status"] in ("resolved", "escalated")
      assert len(final_incident["agent_history"]) > 0
  ```

- [ ] **Step 2: Run verify_brain.py to check failure**
  Run: `python3 verify_brain.py`
  Expected: FAIL with `ModuleNotFoundError: No module named 'services.graph'`.

- [ ] **Step 3: Create `backend/services/graph.py`**
  Define `IncidentState`, multi-agent nodes, routing logic, compile the graph, and implement `run_langgraph_pipeline`.
  ```python
  import asyncio
  import datetime
  import json
  from typing import Any, Dict, List, Optional, TypedDict
  from langgraph.graph import StateGraph, END
  from database import update_agent_history, update_playbook_steps, resolve_incident

  class IncidentState(TypedDict):
      incident_id: int
      raw_log: str
      severity: str
      category: Optional[str]
      priority: Optional[str]
      playbook_steps: List[str]
      steps_executed: List[str]
      recommendation: str
      agent_history: List[Dict[str, Any]]
      health_check_passed: bool
      status: str
      retry_count: int
      db_path: str
      broadcast_fn: Any

  def _now() -> str:
      return datetime.datetime.now(datetime.timezone.utc).isoformat()

  async def notify_state(state: IncidentState, node: str, status: str, message: str):
      entry = {
          "node": node,
          "status": status,
          "message": message,
          "timestamp": _now()
      }
      # Update DB
      updated = update_agent_history(state["incident_id"], entry, state["db_path"])
      state["agent_history"] = updated.get("agent_history", [])
      # Broadcast
      if state["broadcast_fn"]:
          await state["broadcast_fn"](updated)

  async def smart_queue_node(state: IncidentState) -> Dict[str, Any]:
      await notify_state(state, "SmartQueue", "running", "Analyzing incident category and priority...")
      await asyncio.sleep(0.5)
      
      # Triage
      from agents.triage import TriageAgent
      triage_agent = TriageAgent()
      triage_res = triage_agent.transform({
          "severity": state["severity"],
          "message": state["raw_log"],
          "source": "incoming"
      })
      category = triage_res.get("category", "Application")
      priority = triage_res.get("priority", "P4")
      
      await notify_state(state, "SmartQueue", "completed", f"Triage complete: Category = {category}, Priority = {priority}")
      return {"category": category, "priority": priority}

  async def knowledge_rca_node(state: IncidentState) -> Dict[str, Any]:
      await notify_state(state, "KnowledgeAgent", "running", "Searching for recovery runbook and recommendations...")
      await asyncio.sleep(0.5)

      # Determine playbook
      from agents.resolver import build_default_engine
      resolver = build_default_engine()
      res = resolver.resolve({
          "is_incident": True,
          "category": state["category"] or "Application",
          "severity": state["severity"]
      })
      playbook = res.get("playbook_used") or ["Verify system resources", "Check service logs", "Restart component"]
      rec = res.get("recommendation", "Review raw logs for exceptions.")
      
      await notify_state(state, "KnowledgeAgent", "completed", f"Found playbook with {len(playbook)} steps.")
      return {"playbook_steps": playbook, "recommendation": rec}

  async def auto_infra_node(state: IncidentState) -> Dict[str, Any]:
      await notify_state(state, "AutoInfra", "running", "Executing playbook remediation steps in sandbox...")
      steps = state["playbook_steps"]
      executed = []
      for i, step in enumerate(steps):
          await asyncio.sleep(0.3)
          executed.append(step)
          await notify_state(state, "AutoInfra", "running", f"Executed ({i+1}/{len(steps)}): {step}")
      
      await notify_state(state, "AutoInfra", "completed", "Remediation execution steps complete.")
      return {"steps_executed": executed}

  async def compliance_health_node(state: IncidentState) -> Dict[str, Any]:
      await notify_state(state, "ComplianceAgent", "running", "Verifying system health checks...")
      await asyncio.sleep(0.5)
      
      # Mock routing trigger logic: if it's high priority (P0/P1) and retry_count == 0, trigger a retry
      passed = True
      if state["priority"] in ("P0", "P1") and state["retry_count"] == 0:
          passed = False
          await notify_state(state, "ComplianceAgent", "failed", "Health verification failed! System indicates lingering timeout. Triggering recovery retry loop.")
      else:
          await notify_state(state, "ComplianceAgent", "completed", "Health verification passed. System is fully operational.")
      
      return {"health_check_passed": passed}

  # Build the graph workflow
  workflow = StateGraph(IncidentState)
  workflow.add_node("smart_queue", smart_queue_node)
  workflow.add_node("knowledge_rca", knowledge_rca_node)
  workflow.add_node("auto_infra", auto_infra_node)
  workflow.add_node("compliance_health", compliance_health_node)

  workflow.set_entry_point("smart_queue")
  workflow.add_edge("smart_queue", "knowledge_rca")
  workflow.add_edge("knowledge_rca", "auto_infra")
  workflow.add_edge("auto_infra", "compliance_health")

  def compliance_router(state: IncidentState):
      if state["health_check_passed"]:
          return "resolve_success"
      elif state["retry_count"] < 1:
          return "retry_rca"
      else:
          return "escalate"

  async def finalize_resolution(state: IncidentState, resolution_status: str):
      import sqlite3
      with sqlite3.connect(state["db_path"]) as conn:
          conn.execute(
              "UPDATE incidents SET resolution_status = ?, playbook_steps = ?, steps_executed = ?, recommendation = ? WHERE incident_id = ?",
              (
                  resolution_status,
                  json.dumps(state["playbook_steps"]),
                  json.dumps(state["steps_executed"]),
                  state["recommendation"],
                  state["incident_id"]
              )
          )
          conn.commit()
      # Re-fetch and broadcast
      from database import _get_incident_by_id
      updated = _get_incident_by_id(state["incident_id"], state["db_path"])
      if state["broadcast_fn"]:
          await state["broadcast_fn"](updated)

  # Define custom routing handlers instead of raw edges to handle side-effects cleanly
  async def route_resolve_success(state: IncidentState):
      await finalize_resolution(state, "resolved")
      return END

  async def route_retry(state: IncidentState):
      state["retry_count"] += 1
      return "knowledge_rca"

  async def route_escalate(state: IncidentState):
      await notify_state(state, "ComplianceAgent", "failed", "Critical escalation: recovery loop limit exceeded.")
      await finalize_resolution(state, "escalated")
      return END

  workflow.add_node("route_resolve_success", route_resolve_success)
  workflow.add_node("route_retry", route_retry)
  workflow.add_node("route_escalate", route_escalate)

  workflow.add_conditional_edges(
      "compliance_health",
      compliance_router,
      {
          "resolve_success": "route_resolve_success",
          "retry_rca": "route_retry",
          "escalate": "route_escalate"
      }
  )
  workflow.add_edge("route_retry", "knowledge_rca")
  workflow.add_edge("route_resolve_success", END)
  workflow.add_edge("route_escalate", END)

  compiled_graph = workflow.compile()

  async def run_langgraph_pipeline(incident_id: int, raw_log: str, severity: str, db_path: str, broadcast_fn: Any) -> None:
      initial_state: IncidentState = {
          "incident_id": incident_id,
          "raw_log": raw_log,
          "severity": severity,
          "category": None,
          "priority": None,
          "playbook_steps": [],
          "steps_executed": [],
          "recommendation": "",
          "agent_history": [],
          "health_check_passed": False,
          "status": "pending",
          "retry_count": 0,
          "db_path": db_path,
          "broadcast_fn": broadcast_fn
      }
      await compiled_graph.ainvoke(initial_state)
  ```

- [ ] **Step 4: Run verify_brain.py to check pass**
  Run: `python3 verify_brain.py`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add backend/services/graph.py verify_brain.py
  git commit -m "feat: implement LangGraph multi-agent pipeline engine"
  ```

---

### Task 3: API & WebSockets Background Task Integration

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/orchestrator.py`
- Modify: `verify_nervous_system.py`

**Interfaces:**
- Updates: `POST /ingest` endpoint response behavior.

- [ ] **Step 1: Update API tests in `verify_nervous_system.py`**
  Modify tests to expect immediate return from `/ingest` with status `"pending"`.
  ```python
  # In verify_nervous_system.py:
  # Assert that ingestion response returns quickly and has status pending
  # The WS client will receive the progressive updates
  ```

- [ ] **Step 2: Modify `backend/main.py` to trigger Background Task**
  Update the `/ingest` route inside `backend/main.py` (or `backend/api/routes.py` if present) to insert the base incident, broadcast initial WebSocket state, and queue the LangGraph execution.
  ```python
  # In backend/main.py:
  from fastapi import BackgroundTasks
  from services.graph import run_langgraph_pipeline

  # In the ingest endpoint:
  @app.post("/ingest")
  async def ingest_log(payload: dict, background_tasks: BackgroundTasks):
      source = payload.get("source", "test.log")
      raw_line = payload.get("raw_line", "2026-07-02 21:00:00 ERROR server: DB connection error")
      
      # 1. Detect if it is an incident
      from agents.transformer import LogTransformer
      from agents.detector import IncidentDetector
      transformer = LogTransformer()
      detector = IncidentDetector()
      
      structured = transformer.transform(raw_line)
      detection = detector.transform(structured)
      
      if not detection.get("is_incident"):
          return {"status": "ignored", "reason": "Not an incident"}
          
      # 2. Save base pending incident to DB
      from database import save_incident
      db_path = app.state.orchestrator.db_path
      dummy = {
          "source": source,
          "raw_line": raw_line,
          "structured_log": structured,
          "detection": detection,
          "triage": {"category": "Application", "priority": "P4"},
          "resolution": {"status": "pending", "playbook_used": [], "steps_executed": []},
          "notification": "Incident Detected"
      }
      incident = save_incident(dummy, db_path)
      
      # 3. Broadcast initial incident via WebSockets
      # define safe broadcast
      async def ws_broadcast(data: dict):
          await manager.broadcast(data)
          
      await ws_broadcast(incident)
      
      # 4. Trigger LangGraph background task
      background_tasks.add_task(
          run_langgraph_pipeline,
          incident["incident_id"],
          raw_line,
          detection.get("severity", "ERROR"),
          db_path,
          ws_broadcast
      )
      
      return incident
  ```

- [ ] **Step 3: Update `backend/orchestrator.py`**
  Modify orchestrator pipeline entry to align with this schema or support graph background trigger inside collector loops.

- [ ] **Step 4: Run verify_nervous_system.py**
  Run: `python3 verify_nervous_system.py`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add backend/main.py backend/orchestrator.py verify_nervous_system.py
  git commit -m "feat: hook up LangGraph pipeline execution to FastAPI BackgroundTasks and WebSocket manager"
  ```

---

### Task 4: Frontend Timeline Sidebar UI

**Files:**
- Modify: `frontend/app/IncidentDashboard.js`
- Modify: `frontend/app/globals.css`
- Modify: `verify_face.py`

- [ ] **Step 1: Update Next.js globals styling**
  Add css rules to `frontend/app/globals.css` for timeline view:
  ```css
  .agent-timeline-container {
    padding: 1rem;
    background: #f5f5f7;
    border-left: 1px solid #d1d1d6;
    width: 300px;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }
  .timeline-node {
    margin-bottom: 1.5rem;
    position: relative;
    padding-left: 1.5rem;
  }
  .timeline-status-dot {
    position: absolute;
    left: 0;
    top: 3px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }
  .status-pending { background: #d1d1d6; }
  .status-running { background: #007aff; animation: pulse 1s infinite alternate; }
  .status-completed { background: #34c759; }
  .status-failed { background: #ff3b30; }
  ```

- [ ] **Step 2: Update `frontend/app/IncidentDashboard.js`**
  Create a collapsible right panel inside the incident detail view. Render the Vertical Timeline of the four agents (SmartQueue, Knowledge, AutoInfra, Compliance) using status matches from the `agent_history` list.
  ```javascript
  // Read agent_history from activeIncident
  const history = activeIncident.agent_history || [];

  // Inside the details container, render:
  <div style={{ display: 'flex', flexDirection: 'row', height: '100%' }}>
    {/* Main details on left */}
    <div style={{ flex: 1, padding: '1rem', overflowY: 'auto' }}>
       {/* Default detail fields and playbook checkboxes */}
    </div>
    
    {/* Agent timeline sidebar on right */}
    <div className="agent-timeline-container">
      <h3>🤖 Agent Timeline</h3>
      {['SmartQueue', 'KnowledgeAgent', 'AutoInfra', 'ComplianceAgent'].map(node => {
         const nodeEvents = history.filter(e => e.node === node);
         const lastEvent = nodeEvents[nodeEvents.length - 1];
         const status = lastEvent ? lastEvent.status : 'pending';
         const message = lastEvent ? lastEvent.message : 'Waiting...';
         
         return (
           <div key={node} className="timeline-node">
             <div className={`timeline-status-dot status-${status}`} />
             <strong>{node}</strong>
             <div style={{ fontSize: '0.8rem', color: '#86868b' }}>{message}</div>
           </div>
         );
      })}
    </div>
  </div>
  ```

- [ ] **Step 3: Run `verify_face.py`**
  Run: `python3 verify_face.py`
  Expected: PASS.

- [ ] **Step 4: Commit**
  ```bash
  git add frontend/app/IncidentDashboard.js frontend/app/globals.css verify_face.py
  git commit -m "feat: build real-time interactive Agent Timeline Sidebar UI in Next.js"
  ```
