# Spec: LM Studio API Key Configuration Support

## Overview
This design spec introduces support for a dedicated `LMSTUDIO_API_KEY` configuration environment variable. Currently, the system uses `OPENAI_API_KEY` as a catch-all for openai, ollama, and lmstudio. Adding a dedicated variable avoids credential overlap and is cleaner for users configuring local LM Studio authentication.

## Proposed Changes

### 1. Code Changes in `backend/services/llm.py`
We will update `LLMService.__init__` to check for `LMSTUDIO_API_KEY` first when the provider is `lmstudio`, falling back to `OPENAI_API_KEY`:

```python
        elif self.provider == "lmstudio":
            self.api_key = os.getenv("LMSTUDIO_API_KEY") or os.getenv("OPENAI_API_KEY")
        elif self.provider in ("openai", "ollama"):
            self.api_key = os.getenv("OPENAI_API_KEY")
```

### 2. Configuration Changes in `.env` and `.env.example`
We will add `LMSTUDIO_API_KEY=your-api-key-here` to both files.

## Verification Plan
1. Update files.
2. Verify environment variable loading using the system Python runner to ensure `LMSTUDIO_API_KEY` is loaded correctly.
3. Run `verify_brain.py` and `verify_nervous_system.py` to ensure no regression.
