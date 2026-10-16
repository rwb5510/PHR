"""Phase 6: optional model. Off by default. No real network in tests."""
import os
import json
from typing import Optional

# Settings stored in env or a simple table later. Defaults off.
def get_model_mode() -> str:
    return os.getenv("LLM_MODE", "off")

def llm_autofile_enabled() -> bool:
    return os.getenv("LLM_AUTOFILE", "false").lower() == "true"

def call_model(text: str, aliases: list) -> Optional[dict]:
    """Returns parsed JSON or None. Never called when mode is off."""
    if get_model_mode() == "off":
        return None
    # In real mode would POST to LLM_BASE_URL. Tests inject a fake response.
    return None

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
                },
                "required": ["type"]
            }
        }
    },
    "required": ["proposals"]
}

def validate_model_output(data: dict) -> bool:
    if not isinstance(data, dict) or "proposals" not in data:
        return False
    for p in data.get("proposals", []):
        if not isinstance(p, dict) or "type" not in p:
            return False
    return True
