import os
import json
import asyncio
import sys
from typing import Dict, Any

from dotenv import load_dotenv

# Ensure parent directory is in sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.triage import TriageAgent
from agents.resolver import build_default_engine

class LLMService:
    """Service provider setup for different LLM clients (OpenAI, Gemini, Ollama, LM Studio)."""
    
    def __init__(self, provider: str = None, model: str = None, base_url: str = None, api_key: str = None):
        load_dotenv()
        self.provider = provider or os.getenv("LLM_PROVIDER", "mock")
        self.model = model or os.getenv("LLM_MODEL", "mock")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        self.openai_client = None
        self.gemini_client = None
        
        self.triage_agent = TriageAgent()
        self.resolver = build_default_engine()
        
        if self.provider in ("openai", "ollama", "lmstudio"):
            from openai import OpenAI
            # Use base_url for local models
            self.openai_client = OpenAI(api_key=self.api_key or "mock-key", base_url=self.base_url)
        elif self.provider == "gemini":
            from google import genai
            self.gemini_client = genai.Client(api_key=self.api_key)

    def _rule_based_fallback(self, raw_line: str, severity: str) -> Dict[str, Any]:
        """Runs the rule-based agent pipeline as a fallback or mock response."""
        dummy = {
            "severity": severity,
            "raw_line": raw_line,
            "message": raw_line
        }
        triage = self.triage_agent.transform(dummy)
        res = self.resolver.resolve(triage)
        return {
            "category": str(triage.get("category", "Application")),
            "priority": str(triage.get("priority", "P4")),
            "recommendation": str(res.get("recommendation", f"Fallback recommendation for log: {raw_line}"))
        }

    async def analyze_incident(self, raw_line: str, severity: str) -> Dict[str, Any]:
        """Analyze log line using the configured LLM provider and return structured results."""
        if self.provider == "mock":
            return self._rule_based_fallback(raw_line, severity)
            
        prompt = f"""You are an expert incident response system. Analyze the following raw log line and classified severity:
Raw Log: {raw_line}
Detected Severity: {severity}

Analyze the incident and respond with a structured JSON object containing:
- category: One of "Network", "Security", "Compute", "Storage", "Application"
- priority: One of "P0", "P1", "P2", "P3", "P4"
- recommendation: A concise markdown-formatted recovery runbook/resolution steps.
"""
        
        try:
            if self.openai_client:
                # Run synchronous API call in a thread pool to avoid blocking the event loop
                response = await asyncio.to_thread(
                    self.openai_client.chat.completions.create,
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                data = json.loads(response.choices[0].message.content)
                return {
                    "category": str(data.get("category", "Application")),
                    "priority": str(data.get("priority", "P4")),
                    "recommendation": str(data.get("recommendation", ""))
                }
                
            elif self.gemini_client:
                from google.genai import types
                response = await asyncio.to_thread(
                    self.gemini_client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "category": types.Schema(type=types.Type.STRING),
                                "priority": types.Schema(type=types.Type.STRING),
                                "recommendation": types.Schema(type=types.Type.STRING),
                            },
                            required=["category", "priority", "recommendation"],
                        ),
                    )
                )
                data = json.loads(response.text)
                return {
                    "category": str(data.get("category", "Application")),
                    "priority": str(data.get("priority", "P4")),
                    "recommendation": str(data.get("recommendation", ""))
                }
        except Exception as e:
            # Fall back cleanly to rule-based triage/recommendations on any API or parsing exception
            print(f"LLM API call failed, falling back to rule-based triage: {e}", file=sys.stderr)
            return self._rule_based_fallback(raw_line, severity)
            
        return self._rule_based_fallback(raw_line, severity)
