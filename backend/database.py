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
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default_val if default_val is not None else {}

def is_postgres(db_path: str) -> bool:
    return db_path.startswith("postgresql://") or db_path.startswith("postgres://") or "dbname=" in db_path

def get_connection(db_path: str):
    if is_postgres(db_path):
        import psycopg2
        return psycopg2.connect(db_path)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

def get_placeholder(db_path: str) -> str:
    return "%s" if is_postgres(db_path) else "?"

def init_db(db_path: str = "data/incidents.db") -> None:
    conn = None
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        if is_postgres(db_path):
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id SERIAL PRIMARY KEY,
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
                    agent_history TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Check if agent_history exists, if not, add it
            cursor.execute("""
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'incidents' AND column_name = 'agent_history';
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE incidents ADD COLUMN agent_history TEXT DEFAULT '[]';")
                
            # Create trigger to notify new incident insertion
            cursor.execute("""
                CREATE OR REPLACE FUNCTION notify_new_incident()
                RETURNS TRIGGER AS $$
                BEGIN
                  PERFORM pg_notify('incident_new', NEW.incident_id::text);
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cursor.execute("""
                DROP TRIGGER IF EXISTS trigger_notify_new_incident ON incidents;
            """)
            cursor.execute("""
                CREATE TRIGGER trigger_notify_new_incident
                AFTER INSERT ON incidents
                FOR EACH ROW
                EXECUTE FUNCTION notify_new_incident();
            """)
        else:
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
                    agent_history TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("PRAGMA table_info(incidents);")
            columns = [info[1] for info in cursor.fetchall()]
            if "agent_history" not in columns:
                cursor.execute("ALTER TABLE incidents ADD COLUMN agent_history TEXT DEFAULT '[]';")
                
        conn.commit()
    finally:
        if conn:
            conn.close()

def save_incident(incident: Dict[str, Any], db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = None
    with db_write_lock:
        try:
            conn = get_connection(db_path)
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
            agent_history = incident.get("agent_history") or []
            
            p = get_placeholder(db_path)
            
            if is_postgres(db_path):
                cursor.execute(f"""
                    INSERT INTO incidents (
                        source, raw_line, structured_log, detection, triage, 
                        resolution_status, playbook_steps, steps_executed, 
                        recommendation, notification, agent_history
                    ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                    RETURNING incident_id
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
                    notification,
                    json.dumps(agent_history)
                ))
                new_id = cursor.fetchone()[0]
            else:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute(f"""
                    INSERT INTO incidents (
                        source, raw_line, structured_log, detection, triage, 
                        resolution_status, playbook_steps, steps_executed, 
                        recommendation, notification, agent_history
                    ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
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
                    notification,
                    json.dumps(agent_history)
                ))
                new_id = cursor.lastrowid
                
            conn.commit()
        finally:
            if conn:
                conn.close()
    
    updated_incident = dict(incident)
    updated_incident["incident_id"] = new_id
    updated_incident["agent_history"] = agent_history
    return updated_incident

def _row_to_dict(row) -> Dict[str, Any]:
    return {
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
        "notification": row["notification"],
        "agent_history": _safe_json_loads(row["agent_history"], [])
    }

def _get_incident_by_id(incident_id: int, db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = None
    try:
        conn = get_connection(db_path)
        if is_postgres(db_path):
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()
            
        p = get_placeholder(db_path)
        cursor.execute(f"SELECT * FROM incidents WHERE incident_id = {p}", (incident_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Incident {incident_id} not found")
        return _row_to_dict(row)
    finally:
        if conn:
            conn.close()

def get_all_incidents(db_path: str = "data/incidents.db") -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = get_connection(db_path)
        if is_postgres(db_path):
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()
            
        cursor.execute("SELECT * FROM incidents ORDER BY incident_id ASC")
        rows = cursor.fetchall()
    finally:
        if conn:
            conn.close()
    
    results = []
    for row in rows:
        results.append(_row_to_dict(row))
    return results

def update_playbook_steps(incident_id: int, steps_executed: List[str], db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = None
    with db_write_lock:
        try:
            conn = get_connection(db_path)
            if is_postgres(db_path):
                from psycopg2.extras import RealDictCursor
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
                
            p = get_placeholder(db_path)
            
            # Get total playbook steps to check if fully resolved, and current status
            cursor.execute(f"SELECT playbook_steps, resolution_status FROM incidents WHERE incident_id = {p}", (incident_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Incident {incident_id} not found")
                
            playbook_steps = _safe_json_loads(row["playbook_steps"], [])
            current_status = row["resolution_status"] or "pending"
            
            # If all steps completed, transition to resolved
            if len(steps_executed) >= len(playbook_steps) and len(playbook_steps) > 0:
                status = "resolved"
            elif current_status == "resolved":
                status = "pending"
            else:
                status = current_status
                
            cursor.execute(f"""
                UPDATE incidents 
                SET steps_executed = {p}, resolution_status = {p}, updated_at = CURRENT_TIMESTAMP
                WHERE incident_id = {p}
            """, (json.dumps(steps_executed), status, incident_id))
            conn.commit()
            
            cursor.execute(f"SELECT * FROM incidents WHERE incident_id = {p}", (incident_id,))
            row = cursor.fetchone()
        finally:
            if conn:
                conn.close()
    
    return _row_to_dict(row)

def resolve_incident(incident_id: int, db_path: str = "data/incidents.db") -> Dict[str, Any]:
    conn = None
    with db_write_lock:
        try:
            conn = get_connection(db_path)
            if is_postgres(db_path):
                from psycopg2.extras import RealDictCursor
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
                
            p = get_placeholder(db_path)
            
            cursor.execute(f"SELECT playbook_steps FROM incidents WHERE incident_id = {p}", (incident_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Incident {incident_id} not found")
                
            playbook_steps = _safe_json_loads(row["playbook_steps"], [])
            
            cursor.execute(f"""
                UPDATE incidents 
                SET resolution_status = 'resolved', steps_executed = {p}, updated_at = CURRENT_TIMESTAMP
                WHERE incident_id = {p}
            """, (json.dumps(playbook_steps), incident_id))
            conn.commit()
            
            cursor.execute(f"SELECT * FROM incidents WHERE incident_id = {p}", (incident_id,))
            row = cursor.fetchone()
        finally:
            if conn:
                conn.close()
    
    return _row_to_dict(row)

def update_agent_history(incident_id: int, entry: dict, db_path: str = "data/incidents.db") -> dict:
    conn = None
    with db_write_lock:
        try:
            conn = get_connection(db_path)
            if is_postgres(db_path):
                from psycopg2.extras import RealDictCursor
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
                
            p = get_placeholder(db_path)
            
            cursor.execute(f"SELECT agent_history FROM incidents WHERE incident_id = {p}", (incident_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Incident {incident_id} not found")
            
            history = _safe_json_loads(row[0] if isinstance(row, tuple) else row["agent_history"], [])
            history.append(entry)
            
            cursor.execute(f"""
                UPDATE incidents SET agent_history = {p}, updated_at = CURRENT_TIMESTAMP WHERE incident_id = {p}
            """, (json.dumps(history), incident_id))
            conn.commit()
        finally:
            if conn:
                conn.close()
    return _get_incident_by_id(incident_id, db_path)

def finalize_incident_resolution(incident_id: int, resolution_status: str, playbook_steps: List[str], steps_executed: List[str], recommendation: str, category: str, priority: str, db_path: str) -> None:
    conn = None
    with db_write_lock:
        try:
            conn = get_connection(db_path)
            cursor = conn.cursor()
            p = get_placeholder(db_path)
            
            triage_dict = {
                "category": category,
                "priority": priority
            }
            
            cursor.execute(f"""
                UPDATE incidents 
                SET resolution_status = {p}, playbook_steps = {p}, steps_executed = {p}, recommendation = {p}, triage = {p}, updated_at = CURRENT_TIMESTAMP
                WHERE incident_id = {p}
            """, (
                resolution_status,
                json.dumps(playbook_steps),
                json.dumps(steps_executed),
                recommendation,
                json.dumps(triage_dict),
                incident_id
            ))
            conn.commit()
        finally:
            if conn:
                conn.close()
