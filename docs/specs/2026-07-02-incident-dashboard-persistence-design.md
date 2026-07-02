# Spec: Incident Dashboard Persistence & Interactive Playbooks

**Date**: 2026-07-02  
**Status**: APPROVED  
**Scope**: SQLite Persistence & Interactive Checklist (Split View) for the Incident Dashboard POC.

---

## 1. Background & Goals

Currently, the Incident Dashboard POC collects and processes logs in real-time, displaying them in a simple list. However, it suffers from two major limitations:
1. **No Persistence**: All incidents are stored in-memory. Restarting the backend server wipes out the active feed.
2. **Static & Imperative Playbooks**: Playbooks are static instructions. Operators cannot track execution progress step-by-step or toggle steps interactively.

This design introduces a local **SQLite database** to persist incidents, updates the API to support **interactive playbook checklists** (progress tracking), and defines a **split-pane visual layout** for the frontend UI.

---

## 2. Architecture & Components

We will use an **Integrated FastAPI + SQLite Monolith** architecture:
- **FastAPI Backend Server**: Exposes REST endpoints for querying incidents, checking off playbook steps, and manually resolving incidents.
- **WebSocket Broadcast**: Maintains a real-time list of connections (`ConnectionManager`) and broadcasts any incident insertions or updates (e.g., progress toggling, manual resolution) to all connected clients.
- **Background Log Watcher**: Spawns on FastAPI startup, running in a daemon thread. It continues to watch files in `logs/` via the `LogCollector` agent. When a new line is collected, it executes the pipeline (transformer, detector, triage, resolution lookup) and writes the resulting record to SQLite, triggering a WebSocket broadcast.
- **SQLite Database**: A single local file (`data/incidents.db`) managed via Python's standard `sqlite3` library.
- **Next.js Frontend**: Presents a two-column Split View:
  - **Left**: Live Incident Feed with progress bars and severity badges.
  - **Right**: Inspector Pane (sidebar) containing log details, triage categories, and the checkable Playbook Checklist.

---

## 3. Database Schema

The SQLite database file will reside at `data/incidents.db`. We will define a single `incidents` table:

```sql
CREATE TABLE IF NOT EXISTS incidents (
    incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    raw_line TEXT,
    structured_log TEXT NOT NULL,  -- JSON string containing timestamp, severity, source, and message
    detection TEXT NOT NULL,       -- JSON string containing is_incident, severity, category, reasoning
    triage TEXT NOT NULL,          -- JSON string containing category, priority
    resolution_status TEXT NOT NULL, -- 'pending', 'resolved', 'escalated'
    playbook_steps TEXT,           -- JSON string array: ["Step 1", "Step 2", ...]
    steps_executed TEXT,           -- JSON string array of completed steps: ["Step 1", ...]
    recommendation TEXT,
    notification TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

*Note: Storing complex nested payloads (`structured_log`, `detection`, `triage`, `playbook_steps`, `steps_executed`) as JSON strings avoids heavy database schema overhead while retaining structural flexibility for this POC.*

---

## 4. API Endpoints

We will implement/update the following endpoints in `backend/api/routes.py`:

### `GET /incidents`
- **Description**: Returns all incidents from SQLite, sorted chronologically.
- **Response**: List of incident payloads, with JSON fields automatically parsed back into Python objects/dictionaries.

### `POST /ingest` (Existing)
- **Description**: Ingests a new log entry, runs the processing pipeline, writes the result to SQLite, and broadcasts it to all WebSocket clients.
- **Payload**: `{"source": "filename.log"}`

### `POST /incidents/{incident_id}/steps` (New)
- **Description**: Toggles or updates the checklist state of executed playbook steps.
- **Payload**: `{"steps_executed": ["Step 1", "Step 3"]}`
- **Behavior**:
  - Updates the `steps_executed` JSON list in the database.
  - If the count of completed steps matches the total number of steps in the playbook, automatically updates the `resolution_status` to `'resolved'`.
  - Broadcasts the updated incident object to all WebSocket clients.

### `POST /incidents/{incident_id}/resolve` (New)
- **Description**: Manually marks an incident as resolved.
- **Behavior**:
  - Updates `resolution_status` to `'resolved'`.
  - Automatically completes any remaining playbook steps.
  - Broadcasts the updated incident to WebSocket clients.

---

## 5. Frontend UI Design

The Next.js frontend (`frontend/app`) will transition to a Split View Layout:
1. **Split-Screen Layout**:
   - Left panel (40% width): Scrollable feed of incident cards.
   - Right panel (60% width): Incident Inspector Pane.
2. **Interactive Cards**:
   - Cards display a priority/severity badge, source details, and a progress bar showing percentage of playbook completion (`len(steps_executed) / len(playbook_steps)`).
   - Clicking a card loads that incident into the Inspector Pane.
3. **Playbook Checklist (Inspector)**:
   - Renders steps with interactive checkboxes.
   - Checking/unchecking a step fires `POST /incidents/{id}/steps` immediately to save progress.
   - Shows a "Mark as Resolved" button at the bottom of the inspector to manually close the incident.

---

## 6. Error Handling & Recovery

- **JSON Parsing Safeguards**: If database strings fail to parse back into JSON, fall back to empty structures (`[]` or `{}`) rather than crashing the client or API.
- **Database Thread Safety**: Since the log watcher thread and the FastAPI main thread both write to/read from SQLite, we will configure the SQLite connection with `check_same_thread=False` and implement a lock around write operations, or use WAL mode for concurrent read/write stability.

---

## 7. Verification & Testing

We will update and expand the test suite to verify the changes:
1. **Nervous System Integration (`verify_nervous_system.py`)**:
   - Ingest logs $\to$ verify they populate SQLite.
   - Call `POST /incidents/{id}/steps` $\to$ verify checklist state persists and retrieves via `GET /incidents`.
   - Call `POST /incidents/{id}/resolve` $\to$ verify status becomes `'resolved'`.
2. **Backend Unit Verification (`verify_hands.py`)**:
   - Verify resolution status and registry keys normalize correctly.
3. **Frontend Syntax & Integrity (`verify_face.py`)**:
   - Verify all React imports and JSX syntax are correct using standard linters.
