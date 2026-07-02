import sqlite3
import json
import os
import threading
from typing import List, Dict, Any

# Global database lock to prevent concurrent write collisions across background thread and API thread pool
db_write_lock = threading.Lock()

def _safe_json_loads(val: Any, default_val: Any = None) -> Any:
    if not val:
        return default_val if default_val is not None else {}
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default_val if default_val is not None else {}

def init_db(db_path: str = "data/incidents.db") -> None:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = None
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            # Enable WAL (Write-Ahead Logging) mode for concurrent read/write stability
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    raw_line TEXT,
                    structured_log TEXT NOT NULL,
                    detection TEXT NOT NULL,
                    triage TEXT NOT NULL,
                    resolution_status TEXT NOT NULL,
                    playbook_steps TEXT NOT NULL,
                    steps_executed TEXT NOT NULL,
                    recommendation TEXT,
                    notification TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
    finally:
        if conn:
            conn.close()

def save_incident(incident: Dict[str, Any], db_path: str = "data/incidents.db") -> Dict[str, Any]:
    init_db(db_path)
    conn = None
    with db_write_lock:
        try:
            with sqlite3.connect(db_path, timeout=10.0) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                
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
                    incident.get("source") or "unknown",
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
        finally:
            if conn:
                conn.close()
    
    updated_incident = dict(incident)
    updated_incident["incident_id"] = new_id
    return updated_incident

def get_all_incidents(db_path: str = "data/incidents.db") -> List[Dict[str, Any]]:
    init_db(db_path)
    conn = None
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("SELECT * FROM incidents ORDER BY incident_id ASC")
            rows = cursor.fetchall()
    finally:
        if conn:
            conn.close()
    
    results = []
    for row in rows:
        results.append({
            "incident_id": row["incident_id"],
            "source": row["source"],
            "raw_line": row["raw_line"],
            "structured_log": _safe_json_loads(row["structured_log"], {}),
            "detection": _safe_json_loads(row["detection"], {}),
            "triage": _safe_json_loads(row["triage"], {}),
            "resolution": {
                "status": row["resolution_status"],
                "playbook_used": _safe_json_loads(row["playbook_steps"], []),
                "steps_executed": _safe_json_loads(row["steps_executed"], []),
                "recommendation": row["recommendation"],
            },
            "notification": row["notification"]
        })
    return results

def update_playbook_steps(incident_id: int, steps_executed: List[str], db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = None
    with db_write_lock:
        try:
            with sqlite3.connect(db_path, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                
                # Get total playbook steps to check if fully resolved, and current status
                cursor.execute("SELECT playbook_steps, resolution_status FROM incidents WHERE incident_id = ?", (incident_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Incident {incident_id} not found")
                    
                playbook_steps = _safe_json_loads(row["playbook_steps"], [])
                current_status = row["resolution_status"] or "pending"
                
                # If all steps completed, transition to resolved
                if len(steps_executed) >= len(playbook_steps) and len(playbook_steps) > 0:
                    status = "resolved"
                elif current_status == "resolved":
                    # Re-toggling back: if was resolved but steps unchecked, revert to pending
                    status = "pending"
                else:
                    status = current_status
                    
                cursor.execute("""
                    UPDATE incidents 
                    SET steps_executed = ?, resolution_status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE incident_id = ?
                """, (json.dumps(steps_executed), status, incident_id))
                conn.commit()
                
                cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
                row = cursor.fetchone()
        finally:
            if conn:
                conn.close()
    
    return {
        "incident_id": row["incident_id"],
        "source": row["source"],
        "raw_line": row["raw_line"],
        "structured_log": _safe_json_loads(row["structured_log"], {}),
        "detection": _safe_json_loads(row["detection"], {}),
        "triage": _safe_json_loads(row["triage"], {}),
        "resolution": {
            "status": row["resolution_status"],
            "playbook_used": playbook_steps,
            "steps_executed": steps_executed,
            "recommendation": row["recommendation"],
        },
        "notification": row["notification"]
    }

def resolve_incident(incident_id: int, db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = None
    with db_write_lock:
        try:
            with sqlite3.connect(db_path, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                
                cursor.execute("SELECT playbook_steps FROM incidents WHERE incident_id = ?", (incident_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Incident {incident_id} not found")
                    
                playbook_steps = _safe_json_loads(row["playbook_steps"], [])
                
                cursor.execute("""
                    UPDATE incidents 
                    SET resolution_status = 'resolved', steps_executed = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE incident_id = ?
                """, (json.dumps(playbook_steps), incident_id))
                conn.commit()
                
                cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
                row = cursor.fetchone()
        finally:
            if conn:
                conn.close()
    
    return {
        "incident_id": row["incident_id"],
        "source": row["source"],
        "raw_line": row["raw_line"],
        "structured_log": _safe_json_loads(row["structured_log"], {}),
        "detection": _safe_json_loads(row["detection"], {}),
        "triage": _safe_json_loads(row["triage"], {}),
        "resolution": {
            "status": row["resolution_status"],
            "playbook_used": playbook_steps,
            "steps_executed": playbook_steps,
            "recommendation": row["recommendation"],
        },
        "notification": row["notification"]
    }
