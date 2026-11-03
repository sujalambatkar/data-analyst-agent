import logging
import os
import re
import threading

import groq as groq_sdk
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

# Groq retires models without much notice (llama-4-scout and llama-3.3-70b
# were both removed from this account, taking every query down with a generic
# this list that Groq currently serves, and re-resolve if the chosen one
# disappears mid-run. Set GROQ_MODEL to pin a specific model.
_PREFERRED = [
    "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.1-8b-instant",
]

# Non-chat models, and gpt-oss, which insists on native tool-calling and
# errors out ("tool_use_failed") on our plain-text ReAct prompt.
_NOT_USABLE = re.compile(r"whisper|guard|orpheus|allam|gpt-oss|tts|embed", re.IGNORECASE)

_lock = threading.Lock()
_resolved: str | None = None
_dead: set[str] = set()


def _available_models() -> list[str]:
    client = groq_sdk.Groq(api_key=os.getenv("GROQ_API_KEY", ""), timeout=10, max_retries=1)
    return [m.id for m in client.models.list().data if getattr(m, "active", True)]


def get_model() -> str:
    global _resolved
    pinned = os.getenv("GROQ_MODEL", "").strip()
    if pinned:
        return pinned
    with _lock:
        if _resolved:
            return _resolved
        try:
            available = [m for m in _available_models() if m not in _dead]
        except Exception as e:
            logger.warning("Could not list Groq models (%s); using %s", e, _PREFERRED[0])
            return _PREFERRED[0]  # not cached, so the next call retries discovery

        choice = next((m for m in _PREFERRED if m in available), None)
        if choice is None:
            choice = next((m for m in available if not _NOT_USABLE.search(m)), None)
        if choice is None:
            raise RuntimeError(f"No usable Groq chat model available. Groq returned: {available}")
        logger.info("Using Groq model: %s", choice)
        _resolved = choice
        return choice


def _is_model_gone(exc: Exception) -> bool:
    if isinstance(exc, groq_sdk.NotFoundError):
        return True
    text = str(exc).lower()
    return isinstance(exc, groq_sdk.BadRequestError) and ("decommissioned" in text or "model_not_found" in text)


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def invoke_llm(messages: list, temperature: float = 0.0, stop: list[str] | None = None) -> str:
    """Single chat call with automatic fallback to another model if Groq has retired ours."""
    global _resolved
    last_exc: Exception | None = None
    for _ in range(3):
        model = get_model()
        llm = ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY", ""), temperature=temperature)
        try:
            content = llm.invoke(messages, stop=stop).content if stop else llm.invoke(messages).content
            return _THINK_RE.sub("", content).strip()
        except Exception as e:
            if os.getenv("GROQ_MODEL", "").strip() or not _is_model_gone(e):
                raise
            logger.error("Groq model %s is gone (%s); re-resolving", model, e)
            with _lock:
                _dead.add(model)
                _resolved = None
            last_exc = e
    raise last_exc  # type: ignore[misc]
