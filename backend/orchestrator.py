from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional


class IncidentOrchestrator:
    def __init__(self, logs_dir: str = "logs") -> None:
        from agents.collector import LogCollector
        from agents.transformer import LogTransformer
        from agents.detector import IncidentDetector
        from agents.triage import TriageAgent
        from agents.resolver import build_default_engine, ResolutionEngine
        from agents.communicator import NotificationAgent

        self.logs_dir: str = logs_dir
        self.collector: LogCollector = LogCollector(logs_dir=logs_dir)
        self.transformer: LogTransformer = LogTransformer()
        self.detector: IncidentDetector = IncidentDetector()
        self.triage_agent: TriageAgent = TriageAgent()
        self.resolution_engine: ResolutionEngine = build_default_engine()
        self.notification_agent: NotificationAgent = NotificationAgent()
        self.incidents_store: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @staticmethod
    def _run_stage(name: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs), None
        except Exception as exc:  # noqa: BLE001
            return None, {"stage": name, "error": str(exc)}

    def start_pipeline(self, source: Optional[str] = None) -> Dict[str, Any]:
        raw_line: Optional[str] = None
        if source and source.endswith(".log"):
            raw_line = f"2026-07-01 12:00:00 ERROR {source}: simulated error line"

        structured_log_value = {
            "timestamp": None,
            "severity": "UNKNOWN",
            "source": source or "unknown",
            "message": raw_line or "",
        }
        structured, err = self._run_stage("transform", self.transformer.transform, raw_line or "")
        if isinstance(structured, dict):
            structured_log_value = structured
        if err:
            structured_log_value.setdefault("error_stage", "transform")

        detection, err = self._run_stage("detect", self.detector.transform, structured_log_value)
        if isinstance(detection, dict):
            detection = detection
        else:
            detection = {"is_incident": False, "severity": "UNKNOWN", "category": None, "reasoning": "Detection stage failed."}

        triage, err = self._run_stage("triage", self.triage_agent.transform, detection)
        if not isinstance(triage, dict):
            triage = dict(detection)
            triage["category"] = triage.get("category") or "Application"
            triage["priority"] = triage.get("priority") or "P4"

        resolution, err = self._run_stage("resolve", self.resolution_engine.resolve, triage)
        if not isinstance(resolution, dict):
            resolution = {"status": "pending", "playbook_used": None, "steps_executed": [], "recommendation": "Resolution stage failed."}

        notification_text, err = self._run_stage("notify", self.notification_agent.format_alert, triage, resolution)
        if not isinstance(notification_text, str):
            notification_text = "Notification formatting failed."

        stored: Dict[str, Any] = {
            "incident_id": None,
            "source": source or structured_log_value.get("source"),
            "raw_line": raw_line,
            "structured_log": structured_log_value,
            "detection": detection,
            "triage": triage,
            "resolution": resolution,
            "notification": notification_text,
            "error": None,
        }

        with self._lock:
            stored["incident_id"] = len(self.incidents_store) + 1
            self.incidents_store.append(dict(stored))

        response = dict(stored)
        return response
