"""One OpenAI-compatible endpoint for every agent.

LLM_PROVIDER=vertex → open models served on Google Cloud Vertex AI (e.g. DeepSeek MaaS), authenticated with a
service account / ADC token that is refreshed automatically. Anything else → plain base URL + API key from .env.
"""
import base64
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


def vertex_base(loc: str | None = None) -> str:
    loc = loc or os.getenv("GCP_LOCATION", "global")
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
    return _json(r.choices[0].message.content)


def _json(content: str | None) -> dict:
    text = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"LLM returned no JSON: {text[:200]}")
    return json.loads(m.group(0))


def vision_json(system: str, user: str, images: list[bytes], temperature: float = 0.2) -> dict:
    """chat_json plus JPEG frames, for an open-weight vision model. VISION_PROVIDER=vertex → Llama 4 on Vertex
    (VISION_LOCATION, pay per token); else any OpenAI-compatible VISION_BASE_URL (e.g. Ollama + qwen2.5vl)."""
    opts = dict(timeout=float(os.getenv("VISION_TIMEOUT", "120")), max_retries=int(os.getenv("LLM_RETRIES", "3")))
    if os.getenv("VISION_PROVIDER") == "vertex":
        base = vertex_base(os.getenv("VISION_LOCATION", "us-east5")) + "/endpoints/openapi"
        client = OpenAI(base_url=base, api_key=gcp_token(), **opts)
    else:
        client = OpenAI(base_url=os.getenv("VISION_BASE_URL"), api_key=os.getenv("VISION_API_KEY", "none"), **opts)
    parts = [{"type": "text", "text": user}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
        for b in images]
    r = client.chat.completions.create(
        model=os.getenv("VISION_MODEL", "meta/llama-4-maverick-17b-128e-instruct-maas"), temperature=temperature,
        messages=[{"role": "system", "content": system + "\nReply with a single JSON object only."},
                  {"role": "user", "content": parts}])
    return _json(r.choices[0].message.content)
