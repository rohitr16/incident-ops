# LM Studio API Key Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a dedicated environment configuration variable `LMSTUDIO_API_KEY` for LM Studio, update code logic in `backend/services/llm.py` to support it (with a fallback to `OPENAI_API_KEY`), and add placeholders to `.env` and `.env.example`.

**Architecture:** Update environment variable checking in LLMService so `lmstudio` uses `LMSTUDIO_API_KEY` first, then falls back to `OPENAI_API_KEY`. Modify configuration files and verify changes with a unit test.

**Tech Stack:** Python, dotenv

## Global Constraints
- Target python environment: system python3 (3.14.4)
- Repository root: `/home/rohit/incident-dashboard-poc`

---

### Task 1: Update API Key logic in backend/services/llm.py

**Files:**
- Modify: `backend/services/llm.py:28-29`
- Modify: `verify_brain.py:21-22`

**Interfaces:**
- Consumes: Environment variables `LMSTUDIO_API_KEY` and `OPENAI_API_KEY`
- Produces: `LLMService.api_key` resolved correctly for LM Studio provider.

- [ ] **Step 1: Write a failing test for LM Studio API key loading**

  Modify `verify_brain.py` around line 21 to add the following test case:

  ```python
  async def test_lmstudio_api_key_loading():
      import os
      from services.llm import LLMService
      os.environ["LMSTUDIO_API_KEY"] = "test-lmstudio-key"
      os.environ["LLM_PROVIDER"] = "lmstudio"
      svc = LLMService()
      assert svc.api_key == "test-lmstudio-key", f"Expected test-lmstudio-key, got {svc.api_key}"
      
      # Clean up environment variables
      del os.environ["LMSTUDIO_API_KEY"]
      del os.environ["LLM_PROVIDER"]

  # And update test_llm_service to run it:
  async def test_llm_service():
      from services.llm import LLMService
      svc = LLMService(provider="mock", model="mock")
      res = await svc.analyze_incident("Connection timeout to DB", "ERROR")
      assert res["category"] == "Storage"
      assert res["priority"] == "P1"
      assert res["recommendation"] is not None
      
      # Run the new key loading test
      await test_lmstudio_api_key_loading()
  ```

- [ ] **Step 2: Run test to verify it fails**

  Run: `python3 verify_brain.py`
  Expected: FAIL with `AssertionError` (or similar assertion mismatch where `svc.api_key` is not `test-lmstudio-key`)

- [ ] **Step 3: Update LLMService initialization**

  Modify `backend/services/llm.py` starting at line 28 to look like:

  ```python
          elif self.provider == "lmstudio":
              self.api_key = os.getenv("LMSTUDIO_API_KEY") or os.getenv("OPENAI_API_KEY")
          elif self.provider in ("openai", "ollama"):
              self.api_key = os.getenv("OPENAI_API_KEY")
  ```

- [ ] **Step 4: Run test to verify it passes**

  Run: `python3 verify_brain.py`
  Expected: PASS / Prints `VERIFIED`

- [ ] **Step 5: Commit changes**

  ```bash
  git add backend/services/llm.py verify_brain.py
  git commit -m "feat: add support for LMSTUDIO_API_KEY with fallback"
  ```

---

### Task 2: Configuration Update in .env and .env.example

**Files:**
- Modify: `.env`
- Modify: `.env.example`

- [ ] **Step 1: Add environment variable placeholder to .env and .env.example**

  In `.env` and `.env.example`, insert the placeholder variable:

  ```env
  # LM Studio API Key (optional/required based on your server settings)
  LMSTUDIO_API_KEY=your-api-key-here
  ```

- [ ] **Step 2: Verify environment variable parsing loads the placeholder**

  Run:
  ```bash
  python3 -c '
  import sys
  from pathlib import Path
  sys.path.append(str(Path.cwd() / "backend"))
  from services.llm import LLMService
  svc = LLMService()
  print("Provider API Key:", svc.api_key)
  '
  ```
  Expected Output:
  ```text
  Provider API Key: your-api-key-here
  ```

- [ ] **Step 3: Run full validation suite**

  Run: `python3 verify_brain.py` and `python3 verify_nervous_system.py`
  Expected Output: Both print `VERIFIED`

- [ ] **Step 4: Commit changes**

  ```bash
  git add .env .env.example
  git commit -m "config: add LMSTUDIO_API_KEY placeholder to env files"
  ```
