# LLM Provider Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a flexible LLM provider abstraction supporting Ollama, LM Studio, OpenAI, and Gemini for dynamic incident triage and resolution recommendations.

**Architecture:** Create an `LLMService` class using `openai` and `google-genai` libraries, wrap its API calls with JSON Schema formatting constraints, and plug it into `IncidentOrchestrator` with automated rule-based fallback safety.

**Tech Stack:** Python, FastAPI, OpenAI Python SDK (`openai`), Google GenAI SDK (`google-genai`), python-dotenv.

## Global Constraints
- **Provider Choice:** Active provider configured via `.env` file (`LLM_PROVIDER`).
- **Standardized Outputs:** LLM outputs must exactly match the schema: `category` (str), `priority` (str), and `recommendation` (str).
- **Error Safety:** LLM failures must automatically fallback to the rule-based classes (`TriageAgent` and `ResolutionEngine`).

---

### Task 1: LLM Service Provider Setup & Unit Tests

**Files:**
- Create: `backend/services/llm.py`
- Modify: `verify_brain.py`

**Interfaces:**
- Produces: `llm_service = LLMService()`
- Produces: `async def analyze_incident(self, raw_line: str, severity: str) -> dict` returning `{"category": str, "priority": str, "recommendation": str}`

- [ ] **Step 1: Install new dependencies**
  Run: `pip install openai google-genai python-dotenv`
  
- [ ] **Step 2: Add test cases to `verify_brain.py`**
  Modify `verify_brain.py` to import `LLMService` and test both mock and fallback scenarios.
  ```python
  # Add to verify_brain.py
  async def test_llm_service():
      from services.llm import LLMService
      # Test fallback to empty/mock on invalid config
      svc = LLMService(provider="mock", model="mock")
      res = await svc.analyze_incident("Connection timeout to DB", "ERROR")
      assert res["category"] == "Application"
      assert res["priority"] == "P1"
      assert "Connection timeout" in res["recommendation"]
  ```

- [ ] **Step 3: Run verify_brain.py to check failure**
  Run: `python3 verify_brain.py`
  Expected: FAIL with `ModuleNotFoundError: No module named 'services'`

- [ ] **Step 4: Create `backend/services/llm.py`**
  Write the unified provider client logic:
  ```python
  import os
  import json
  from typing import Dict, Any
  
  class LLMService:
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
  ```

- [ ] **Step 5: Run verify_brain.py to check pass**
  Run: `python3 verify_brain.py`
  Expected: PASS

- [ ] **Step 6: Commit**
  Run:
  ```bash
  git add backend/services/llm.py verify_brain.py
  git commit -m "feat: setup LLMService class with Ollama/OpenAI/Gemini providers and unit tests"
  ```

---

### Task 2: Orchestrator Pipeline Integration & Fallbacks

**Files:**
- Modify: `backend/orchestrator.py`
- Modify: `backend/api/routes.py`
- Modify: `verify_nervous_system.py`

**Interfaces:**
- Consumes: `LLMService` from `backend/services/llm.py`
- Modifies: `IncidentOrchestrator.start_pipeline`

- [ ] **Step 1: Add pipeline test assertions to `verify_nervous_system.py`**
  Modify `verify_nervous_system.py` to load `.env` variables and verify that incident ingestion passes successfully even if the LLM provider fails.
  
- [ ] **Step 2: Modify `backend/orchestrator.py`**
  Integrate `LLMService` and add try-except fallback wrappers:
  ```python
  # Add import to backend/orchestrator.py
  from services.llm import LLMService
  
  # Initialize in __init__
  self.llm_service = LLMService()
  ```
  Update `start_pipeline` to run:
  ```python
  # Inside start_pipeline after detection check:
  triage = None
  resolution = None
  if detection.get("is_incident"):
      # Try calling the LLM provider
      try:
          # Since start_pipeline is synchronous, we run LLM async call in a block using asyncio
          import asyncio
          try:
              loop = asyncio.get_event_loop()
          except RuntimeError:
              loop = asyncio.new_event_loop()
              asyncio.set_event_loop(loop)
              
          llm_result = loop.run_until_complete(
              self.llm_service.analyze_incident(raw_line, detection.get("severity"))
          )
          
          triage = {
              "category": llm_result.get("category", "Application"),
              "priority": llm_result.get("priority", "P4")
          }
          resolution = {
              "status": "pending",
              "playbook_used": self.resolution_engine.resolve(triage).get("playbook_used") or [],
              "steps_executed": [],
              "recommendation": llm_result.get("recommendation", "")
          }
      except Exception as e:
          # Fallback to rules on LLM failure/timeout
          import sys
          print(f"LLM analysis failed, falling back to rule-based: {e}", file=sys.stderr)
          triage = self.triage_agent.transform(detection)
          resolution = self.resolution_engine.resolve(triage)
  ```

- [ ] **Step 3: Run verify_nervous_system.py**
  Run: `python3 verify_nervous_system.py`
  Expected: PASS (triggers fallback or mock successfully)

- [ ] **Step 4: Commit**
  Run:
  ```bash
  git add backend/orchestrator.py verify_nervous_system.py
  git commit -m "feat: integrate LLMService into orchestrator pipeline with fallback safety"
  ```

---

### Task 3: Configuration & Environment Setup

**Files:**
- Create: `.env.example`
- Modify: `backend/main.py`

- [ ] **Step 1: Create `.env.example`**
  Create `.env.example` with standard keys.
  
- [ ] **Step 2: Load `.env` on startup in `backend/main.py`**
  Add `from dotenv import load_dotenv` and call `load_dotenv()` before instantiating the API router.
  
- [ ] **Step 3: Run all verification tests**
  Run: `python3 verify_face.py && python3 verify_brain.py && python3 verify_nervous_system.py`
  Expected: ALL VERIFIED / PASS

- [ ] **Step 4: Commit**
  Run:
  ```bash
  git add .env.example backend/main.py
  git commit -m "feat: add .env configuration setup and load variables on startup"
  ```
