"""Phase 6: optional model client. Off by default. No real vendor calls in tests."""
import os
import json
import time
import logging
from typing import Optional, List, Dict, Any
import httpx

logger = logging.getLogger("phr.model")

# Defaults
_DEFAULT_MODE = "off"
_DEFAULT_BASE_URL = ""
_DEFAULT_MODEL = ""
_DEFAULT_AUTOFILE = False

# In-process settings (overridable by tests / settings endpoint)
_settings = {
    "mode": os.getenv("LLM_MODE", _DEFAULT_MODE),
    "base_url": os.getenv("LLM_BASE_URL", _DEFAULT_BASE_URL),
    "model": os.getenv("LLM_MODEL", _DEFAULT_MODEL),
    "llm_autofile": os.getenv("LLM_AUTOFILE", "false").lower() == "true",
}

def get_settings() -> Dict[str, Any]:
    return dict(_settings)

def update_settings(mode: Optional[str] = None, base_url: Optional[str] = None,
                    model: Optional[str] = None, llm_autofile: Optional[bool] = None) -> Dict[str, Any]:
    if mode is not None:
        _settings["mode"] = mode
    if base_url is not None:
        _settings["base_url"] = base_url
    if model is not None:
        _settings["model"] = model
    if llm_autofile is not None:
        _settings["llm_autofile"] = llm_autofile
    return get_settings()

def get_model_mode() -> str:
    return _settings["mode"]

def llm_autofile_enabled() -> bool:
    return bool(_settings["llm_autofile"])

MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "original_name": {"type": "string"},
                    "value_text": {"type": "string"},
                    "unit_original": {"type": "string"},
                    "quote": {"type": "string"},
                    "is_impression": {"type": "boolean"},
                },
                "required": ["type"]
            }
        }
    },
    "required": ["proposals"]
}

def validate_model_output(data: Any) -> bool:
    if not isinstance(data, dict) or "proposals" not in data:
        return False
    for p in data.get("proposals", []):
        if not isinstance(p, dict) or "type" not in p:
            return False
    return True

def call_model(document_id: int, text: str, aliases: List[str], use_model: bool) -> Optional[Dict]:
    """
    Call OpenAI-compatible chat endpoint.
    Returns parsed dict on success, None if mode off or use_model false.
    Raises on invalid JSON / schema fail (caller marks extraction failed).
    Logs only document_id, duration, success/failure. Never logs text, key, or raw response.
    """
    if not use_model or get_model_mode() == "off":
        return None
    base = _settings["base_url"].rstrip("/")
    model = _settings["model"]
    key = os.getenv("LLM_API_KEY", "")
    if not base or not model:
        logger.info("model_skip document_id=%s reason=no_url_or_model", document_id)
        return None
    prompt = (
        "Extract structured proposals from the document text. "
        "Return only JSON matching this schema: "
        + json.dumps(MODEL_SCHEMA)
        + "\nAliases: " + ", ".join(aliases)
        + "\n\nDocument:\n" + text
    )
    start = time.time()
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{base}/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"} if key else {},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
            )
            r.raise_for_status()
            body = r.json()
            content = body["choices"][0]["message"]["content"]
            data = json.loads(content)
            if not validate_model_output(data):
                raise ValueError("schema_invalid")
            duration = time.time() - start
            logger.info("model_ok document_id=%s duration=%.2f", document_id, duration)
            return data
    except Exception as e:
        duration = time.time() - start
        logger.info("model_fail document_id=%s duration=%.2f error=%s", document_id, duration, type(e).__name__)
        raise
