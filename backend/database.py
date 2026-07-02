import sqlite3
import json
import os
from typing import List, Dict, Any

def init_db(db_path: str = "data/incidents.db") -> None:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = None
    try:
        with sqlite3.connect(db_path) as conn:
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
    finally:
        if conn:
            conn.close()

def save_incident(incident: Dict[str, Any], db_path: str = "data/incidents.db") -> Dict[str, Any]:
    init_db(db_path)
    conn = None
    try:
        with sqlite3.connect(db_path) as conn:
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
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
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
    conn = None
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get total playbook steps to check if fully resolved, and current status
            cursor.execute("SELECT playbook_steps, resolution_status FROM incidents WHERE incident_id = ?", (incident_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Incident {incident_id} not found")
                
            playbook_steps = json.loads(row["playbook_steps"] or "[]")
            current_status = row["resolution_status"] or "pending"
            
            # If all steps completed, transition to resolved; otherwise, preserve the existing status
            if len(steps_executed) >= len(playbook_steps) and len(playbook_steps) > 0:
                status = "resolved"
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
    conn = None
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT playbook_steps FROM incidents WHERE incident_id = ?", (incident_id,))
            row = cursor.fetchone()
            if not row:
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
    finally:
        if conn:
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

