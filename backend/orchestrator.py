from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class IncidentOrchestrator:
    def __init__(self, logs_dir: str = "logs") -> None:
        from agents.collector import LogCollector
        from agents.transformer import LogTransformer
        from agents.detector import IncidentDetector
        from agents.triage import TriageAgent
        from agents.resolver import build_default_engine, ResolutionEngine
        from agents.communicator import NotificationAgent
        from services.llm import LLMService

        self.logs_dir: str = os.path.abspath(logs_dir)
        self.db_path: str = os.path.join(_REPO_ROOT, "data", "incidents.db")
        self.collector: LogCollector = LogCollector(logs_dir=logs_dir)
        self.transformer: LogTransformer = LogTransformer()
        self.detector: IncidentDetector = IncidentDetector()
        self.triage_agent: TriageAgent = TriageAgent()
        self.resolution_engine: ResolutionEngine = build_default_engine()
        self.notification_agent: NotificationAgent = NotificationAgent()
        self.llm_service: LLMService = LLMService()
        
        from database import init_db
        init_db(self.db_path)
        self._lock = threading.Lock()

    @staticmethod
    def _run_stage(name: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs), None
        except Exception as exc:  # noqa: BLE001
            return None, {"stage": name, "error": str(exc)}

    def start_pipeline(self, source: Optional[str] = None, raw_line: Optional[str] = None) -> Dict[str, Any]:
        if not raw_line and source and source.endswith(".log"):
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

        triage = None
        resolution = None
        if detection.get("is_incident"):
            try:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                llm_result = loop.run_until_complete(
                    self.llm_service.analyze_incident(raw_line or "", detection.get("severity", "UNKNOWN"))
                )
                
                triage = dict(detection)
                triage["category"] = llm_result.get("category", "Application")
                triage["priority"] = llm_result.get("priority", "P4")
                
                resolution = {
                    "status": "pending",
                    "playbook_used": self.resolution_engine.resolve(triage).get("playbook_used") or [],
                    "steps_executed": [],
                    "recommendation": llm_result.get("recommendation", "")
                }
            except Exception as e:
                import sys
                print(f"LLM analysis failed, falling back to rule-based: {e}", file=sys.stderr)
                triage = self.triage_agent.transform(detection)
                resolution = self.resolution_engine.resolve(triage)
        else:
            triage = self.triage_agent.transform(detection)
            resolution = self.resolution_engine.resolve(triage)

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
            from database import save_incident
            response = save_incident(stored, self.db_path)
            return response

    @property
    def incidents_store(self) -> List[Dict[str, Any]]:
        from database import get_all_incidents
        return get_all_incidents(self.db_path)

