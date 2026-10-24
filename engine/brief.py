"""The agency layer: materials in, a brief out, and real results turned into the next experiment."""
import io
import json
import re
from html.parser import HTMLParser

import httpx

from . import llm

OBJECTIVES = {  # objective -> locked ad type
    "awareness": "brand", "qualified inquiries": "direct", "registrations": "direct", "enrollment": "direct",
    "visits": "direct", "installations": "direct", "sales": "direct", "evidence of demand": "direct",
}
BRIEF_FIELDS = ["objective", "audience", "insight", "offer", "main_message", "evidence", "action",
                "platforms_formats", "creative_direction", "brand_requirements", "restrictions", "success_metric"]
LIST_FIELDS = ("evidence", "missing", "assumptions")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ("script", "style", "noscript")

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style", "noscript") and self.skip > 0

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.out.append(d.strip())


def read_url(url: str) -> str:
    if not re.match(r"^https?://", url):
        raise ValueError("only http(s) links")
    r = httpx.get(url, follow_redirects=True, timeout=15, headers={"User-Agent": "MarkStrap/0.1"})
    p = _Text()
    p.feed(r.text)
    return " ".join(p.out)[:8000]


def read_file(name: str, data: bytes) -> str:
    low = name.lower()
    if low.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(data)).pages)[:12000]
    if low.endswith((".txt", ".md", ".csv", ".json", ".html")):
        return data.decode(errors="ignore")[:12000]
    # ponytail: no vision model yet, images and footage are listed by name for the visual maker to reference
    return f"[{name}: image/footage asset available for creative use]"


def extract(profile: str, product: str, fields: dict, materials: str = "") -> dict:
    """Campaign brief from the approved organization profile, the approved product and the campaign form.
    Only approved research reaches this prompt; the organization's own materials are their own words."""
    b = llm.chat_json(
        "You are a senior strategist at a marketing agency writing a campaign brief. The client is the expert; "
        "organise what they gave you, never lecture, never invent facts. Anything not supported by the inputs is an "
        "assumption and must be listed as one. Ask only for details that truly block the campaign.",
        f"Organization profile (approved):\n{profile}\n\nProduct or service (approved):\n{product}\n\n"
        f"Campaign requirements from the client:\n{json.dumps(fields)}\n\n"
        f"Organization materials:\n{materials[:15000] or 'none'}\n\n"
        'Return {"objective": str, "audience": str (who and where), "insight": str (the customer truth the '
        'campaign rests on), "offer": str, "main_message": str (one sentence), "evidence": [str] (only facts '
        'present in the inputs), "action": str (what people should do and where they land), '
        '"platforms_formats": str, "creative_direction": str, "brand_requirements": str, "restrictions": str '
        '(claims and content that must not appear), "success_metric": str (measurable), '
        '"basis": {"<field>": "organization|product|campaign|assumption"}, '
        '"assumptions": [str], "missing": [str] (max 3, only true blockers, empty if none)}', temperature=0.3)
    for k in LIST_FIELDS:
        b[k] = [str(x) for x in (b.get(k) or []) if str(x).strip()]
    b["missing"] = b["missing"][:3]
    return b


def engine_brief(b: dict, fields: dict) -> dict:
    """The confirmed brief plus the keys the engine and the Reel Director already read."""
    required = [m.strip() for m in str(fields.get("required_messages") or "").split("\n") if m.strip()]
    return {**b, "offering": b.get("offer", ""), "goal": fields.get("goal") or b.get("success_metric", ""),
            "key_messages": [m for m in [b.get("main_message", "")] + required if m],
            "proof_points": b.get("evidence", []), "destination": fields.get("destination") or b.get("action", ""),
            "available": "built"}


def constraints(fields: dict, b: dict) -> dict:
    """Hard rules every concept must follow, taken from the campaign form and the confirmed brief."""
    return {k: v for k, v in {
        "language": fields.get("language", ""), "geography": fields.get("market", ""),
        "budget": fields.get("budget", ""), "start": fields.get("start", ""), "end": fields.get("end", ""),
        "required": fields.get("required_messages", ""), "tone": fields.get("tone", ""),
        "brand_rules": " ".join(x for x in (fields.get("brand_rules", ""), b.get("brand_requirements", "")) if x),
        "restricted_claims": " ".join(x for x in (fields.get("prohibited_claims", ""), b.get("restrictions", ""))
                                      if x),
        "platforms": fields.get("platforms", ""), "format": fields.get("format", ""),
    }.items() if v}


def next_experiment(campaign: dict, ads: list[dict], comparison: dict | None = None) -> dict:
    tested = [{"headline": a["content"].get("headline"), "visual": a["content"].get("visual"),
               "platform": a["content"].get("platform"), "approach": a["style"], "real_score": a["real_score"],
               "sim_score": a["sim_score"]} for a in ads]
    out = llm.chat_json(
        "You are a performance marketing lead reviewing a live experiment. Be specific and practical. "
        "A weak creative is not proof the offering has no market; say what the evidence does and does not show. "
        "Recommend ONE focused next experiment that changes a single thing, so its result can be read.",
        f"Campaign: {json.dumps(campaign)}\nTested ads with real scores (z vs campaign baseline) and simulation "
        f"scores:\n{json.dumps(tested)}\nSimulation vs reality, computed: {json.dumps(comparison or {})}\n"
        'Return {"what_worked": [str], "what_didnt": [str], "not_proven": [str], "caution": str, '
        '"next": {"hypothesis": str, "change": str (the single change to test), "audience": str, "channel": str, '
        '"success_metric": str, "keep_same": [str] (what must stay unchanged)}}',
        temperature=0.4)
    out.setdefault("not_proven", [])
    out.setdefault("next", {}).setdefault("keep_same", [])
    return out
