"""Render approved concepts into image ads. Only survivors are rendered (design: evolve descriptions, render winners).

IMAGE_PROVIDER=vertex  → Google image model on Vertex AI, same service account as the brain (trial credit pays)
IMAGE_PROVIDER=gemini  → Gemini API with an API key (needs a billed key)
IMAGE_PROVIDER=openai  → any OpenAI-compatible images endpoint, e.g. FLUX.1-schnell on your GPU PC (open source)
"""
import base64
import os
from pathlib import Path

import httpx

OUT = Path(os.getenv("RENDER_DIR", "data/renders"))
ASPECT = {"instagram": "4:5", "tiktok": "9:16", "youtube": "16:9", "x": "16:9", "linkedin": "1:1"}


def prompt_for(ad: dict, brief: dict, constraints: dict) -> str:
    return (f"Social media ad image for {ad.get('platform', 'instagram')}. {ad.get('visual', '')} "
            f"Brand rules: {constraints.get('brand_rules') or 'none given'}. "
            "Photographic, natural light, no text, no logos, no watermarks; leave clean space for a headline. "
            f"Context: {brief.get('offering', '')}")


def _gemini(prompt: str, aspect: str, vertex: bool = False) -> bytes:
    model = os.getenv("IMAGE_MODEL", "gemini-2.5-flash-image")
    if vertex:
        from .llm import gcp_token, vertex_base
        url = f"{vertex_base()}/publishers/google/models/{model}:generateContent"
        headers = {"Authorization": f"Bearer {gcp_token()}"}
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"x-goog-api-key": os.getenv("IMAGE_API_KEY") or os.getenv("LLM_API_KEY", "")}
    r = httpx.post(url, headers=headers,
                   json={"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}},
                   timeout=120)
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except ValueError:
            msg = r.text
        raise RuntimeError(f"{r.status_code}: {msg[:300]}")
    for part in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError("model returned no image")


def _openai(prompt: str, aspect: str) -> bytes:
    from openai import OpenAI
    size = {"9:16": "768x1344", "16:9": "1344x768", "4:5": "896x1120"}.get(aspect, "1024x1024")
    client = OpenAI(base_url=os.getenv("IMAGE_BASE_URL"), api_key=os.getenv("IMAGE_API_KEY", "none"), timeout=300)
    res = client.images.generate(model=os.getenv("IMAGE_MODEL", "flux.1-schnell"), prompt=prompt, size=size,
                                 response_format="b64_json")
    return base64.b64decode(res.data[0].b64_json)


def render(ad_id: str, ad: dict, brief: dict, constraints: dict) -> Path:
    aspect = ASPECT.get((ad.get("platform") or "").lower(), "1:1")
    prompt = prompt_for(ad, brief, constraints)
    provider = os.getenv("IMAGE_PROVIDER", "vertex")
    data = _openai(prompt, aspect) if provider == "openai" else _gemini(prompt, aspect, vertex=provider == "vertex")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{ad_id}.png"
    path.write_bytes(data)
    return path
