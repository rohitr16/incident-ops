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
    return {}

async def route_retry(state: IncidentState):
    return {"retry_count": state["retry_count"] + 1}

async def route_escalate(state: IncidentState):
    await notify_state(state, "ComplianceAgent", "failed", "Critical escalation: recovery loop limit exceeded.")
    await finalize_resolution(state, "escalated")
    return {}

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
