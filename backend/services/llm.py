import os
import json
from typing import Dict, Any

class LLMService:
    """Service provider setup for different LLM clients (OpenAI, Gemini, Ollama, LM Studio)."""
    
    def __init__(self, provider: str = None, model: str = None, base_url: str = None, api_key: str = None):
        self.provider = provider or os.getenv("LLM_PROVIDER", "mock")
        self.model = model or os.getenv("LLM_MODEL", "mock")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        self.openai_client = None
        self.gemini_client = None
        
        if self.provider in ("openai", "ollama", "lmstudio"):
            from openai import OpenAI
            # Use base_url for local models
            self.openai_client = OpenAI(api_key=self.api_key or "mock-key", base_url=self.base_url)
        elif self.provider == "gemini":
            from google import genai
            self.gemini_client = genai.Client(api_key=self.api_key)

    async def analyze_incident(self, raw_line: str, severity: str) -> Dict[str, Any]:
        """Analyze log line using the configured LLM provider and return structured results."""
        if self.provider == "mock":
            # Default mock response for unit tests/fallbacks
            return {
                "category": "Application",
                "priority": "P1",
                "recommendation": f"Mock recommendation for: {raw_line}"
            }
            
        prompt = f"""You are an expert incident response system. Analyze the following raw log line and classified severity:
Raw Log: {raw_line}
Detected Severity: {severity}

Analyze the incident and respond with a structured JSON object containing:
- category: One of "Network", "Security", "Compute", "Storage", "Application"
- priority: One of "P0", "P1", "P2", "P3", "P4"
- recommendation: A concise markdown-formatted recovery runbook/resolution steps.
"""
        
        if self.openai_client:
            # For Ollama, LM Studio, and OpenAI
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            return {
                "category": data.get("category", "Application"),
                "priority": data.get("priority", "P4"),
                "recommendation": data.get("recommendation", "")
            }
            
        elif self.gemini_client:
            from google.genai import types
            response = self.gemini_client.models.generate_content(
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
                ),
            )
            data = json.loads(response.text)
            return data
            
        return {
            "category": "Application",
            "priority": "P4",
            "recommendation": "No provider initialized"
        }
