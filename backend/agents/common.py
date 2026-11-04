import json
import threading
import time

from groq import Groq, GroqError

from config import (
    GROQ_API_KEY,
    GROQ_MAX_CONCURRENT_REQUESTS,
    GROQ_MODEL,
    GROQ_TIMEOUT_SECONDS,
)
from observability import increment, observe

_client = (
    Groq(
        api_key=GROQ_API_KEY,
        timeout=GROQ_TIMEOUT_SECONDS,
        max_retries=1,
    )
    if GROQ_API_KEY
    else None
)
_llm_slots = threading.BoundedSemaphore(GROQ_MAX_CONCURRENT_REQUESTS)

def llm_json(system: str, user: str, fallback: dict) -> dict:
    if not _client:
        increment("llm.fallback.no_provider")
        return fallback
    if not _llm_slots.acquire(timeout=GROQ_TIMEOUT_SECONDS):
        increment("llm.fallback.concurrency_limit")
        return fallback
    started = time.perf_counter()
    try:
        r = _client.chat.completions.create(model=GROQ_MODEL, temperature=0.1, max_tokens=700,
          response_format={"type":"json_object"}, messages=[{"role":"system","content":system},{"role":"user","content":user}])
        output = json.loads(r.choices[0].message.content or "{}")
        increment("llm.success")
        return output if isinstance(output, dict) else fallback
    except (GroqError, json.JSONDecodeError, TypeError, ValueError):
        increment("llm.failure")
        return fallback
    finally:
        observe("llm.inference", (time.perf_counter() - started) * 1000)
        _llm_slots.release()

def event(name, action, output, started, status="success"):
    return {"agent":name,"action":action,"output":output,"duration_ms":round((time.perf_counter()-started)*1000),"status":status}
