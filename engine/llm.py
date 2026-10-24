"""One OpenAI-compatible endpoint for every agent.

LLM_PROVIDER=vertex → open models served on Google Cloud Vertex AI (e.g. DeepSeek MaaS), authenticated with a
service account / ADC token that is refreshed automatically. Anything else → plain base URL + API key from .env.
"""
import json
import os
import re
import threading

from openai import OpenAI

_client = None
_token = None
_creds = None
_lock = threading.Lock()


def gcp_token() -> str:
    """Short-lived Google access token from GOOGLE_APPLICATION_CREDENTIALS (or gcloud ADC), refreshed when stale."""
    global _creds
    import google.auth
    import google.auth.transport.requests
    with _lock:
        if _creds is None:
            _creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _creds.valid:
            _creds.refresh(google.auth.transport.requests.Request())
        return _creds.token


def vertex_base() -> str:
    loc = os.getenv("GCP_LOCATION", "global")
    host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{os.environ['GCP_PROJECT_ID']}/locations/{loc}"


def _c():
    global _client, _token
    # Fail fast on an overloaded provider instead of hanging a whole generation.
    opts = dict(timeout=float(os.getenv("LLM_TIMEOUT", "60")), max_retries=int(os.getenv("LLM_RETRIES", "3")))
    if os.getenv("LLM_PROVIDER") == "vertex":
        tok = gcp_token()
        if _client is None or tok != _token:  # tokens expire hourly; rebuild the client on refresh
            _client, _token = OpenAI(base_url=vertex_base() + "/endpoints/openapi", api_key=tok, **opts), tok
    elif _client is None:
        _client = OpenAI(base_url=os.getenv("LLM_BASE_URL"), api_key=os.getenv("LLM_API_KEY", "none"), **opts)
    return _client


def chat_json(system: str, user: str, temperature: float = 0.8) -> dict:
    """Ask for JSON, tolerate models that wrap it in prose, ```json fences or <think> reasoning."""
    r = _c().chat.completions.create(
        model=os.getenv("LLM_MODEL", "qwen2.5"),
        temperature=temperature,
        messages=[{"role": "system", "content": system + "\nReply with a single JSON object only."},
                  {"role": "user", "content": user}],
    )
    text = re.sub(r"<think>.*?</think>", "", r.choices[0].message.content or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"LLM returned no JSON: {text[:200]}")
    return json.loads(m.group(0))
