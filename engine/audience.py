"""MiroFish/OASIS audience, run as a separate process (audience/feed.py on its own Python 3.11 venv).

AUDIENCE_BACKEND=oasis turns it on; otherwise evolve.judge() (one batched LLM call per ad) is used.
Persona text and remembered results are assembled here and only ever sent to the audience process,
never to makers: the process boundary is the guard against makers optimising for the judge.
"""
import json
import os
import subprocess
from pathlib import Path

import yaml

from . import llm, personas

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
PY = ROOT / "audience" / ".venv" / "bin" / "python"


def enabled() -> bool:
    return os.getenv("AUDIENCE_BACKEND") == "oasis"


def ad_text(ad: dict) -> str:
    return f"{ad.get('headline', '')}\n{ad.get('body', '')}\n[image: {ad.get('visual', '')}]".strip()


def people(audience: list, lessons: list) -> list:
    lo, hi = CFG["oasis"]["activity_from_E4"]  # [U] Activity facet percentile -> how often they act
    memory = (" From real campaigns you have seen, you remember: " + " ".join(lessons)) if lessons else ""
    return [{"name": p["name"], "age": p.get("age"), "bio": f"{p['name']}, {p.get('age', '')}. {p.get('habits', '')}",
             "persona": " ".join(p["tendencies"]) + " " + personas.EXPRESSION + memory,
             "activity_level": round(lo + (hi - lo) * p.get("facets", {}).get("E4", 50) / 100, 3)}
            for p in audience]


def _llm_env() -> dict:
    """MiroFish's runner reads LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME; reuse the engine's endpoint."""
    if os.getenv("LLM_PROVIDER") == "vertex":
        key, base = llm.gcp_token(), llm.vertex_base() + "/endpoints/openapi"
    else:
        key, base = os.getenv("LLM_API_KEY", "none"), os.getenv("LLM_BASE_URL", "")
    return {**os.environ, "LLM_API_KEY": key, "LLM_BASE_URL": base, "LLM_MODEL_NAME": os.getenv("LLM_MODEL", "")}


def evaluate(ads: dict, audience: list, lessons: list, rounds: int, workdir: Path | None = None) -> dict:
    """ads: {ad_id: ad content}. Returns {ad_id: {"reactions": [...], "counts": {...}}} from one shared feed."""
    job = {"people": people(audience, lessons), "rounds": rounds,
           "ads": [{"id": i, "text": ad_text(a)} for i, a in ads.items()],
           "workdir": str(workdir) if workdir else None}
    out = subprocess.run([str(PY), str(ROOT / "audience" / "feed.py")], input=json.dumps(job), text=True,
                         capture_output=True, env=_llm_env(), cwd=ROOT / "audience",
                         timeout=CFG["oasis"]["timeout_s"])
    if out.returncode:
        raise RuntimeError(f"audience feed failed: {out.stderr[-500:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])
