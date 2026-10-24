"""Render approved concepts into image ads. Only survivors are rendered (design: evolve descriptions, render winners).

Open-weight image model behind an OpenAI-compatible images endpoint (IMAGE_BASE_URL), e.g. FLUX.1-schnell
(Apache-2.0) served by LocalAI or a diffusers server. Not configured yet: rendering is parked until a host is chosen.
"""
import base64
import os
from pathlib import Path

OUT = Path(os.getenv("RENDER_DIR", "data/renders"))
ASPECT = {"instagram": "4:5", "tiktok": "9:16", "youtube": "16:9", "x": "16:9", "linkedin": "1:1"}


def prompt_for(ad: dict, brief: dict, constraints: dict) -> str:
    return (f"Social media ad image for {ad.get('platform', 'instagram')}. {ad.get('visual', '')} "
            f"Brand rules: {constraints.get('brand_rules') or 'none given'}. "
            "Photographic, natural light, no text, no logos, no watermarks; leave clean space for a headline. "
            f"Context: {brief.get('offering', '')}")


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
    if not os.getenv("IMAGE_BASE_URL"):
        raise RuntimeError("no image model configured (set IMAGE_BASE_URL to an open-weight model's endpoint)")
    data = _openai(prompt, aspect)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{ad_id}.png"
    path.write_bytes(data)
    return path
