"""The agency layer: materials in, a brief out, and real results turned into the next experiment."""
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx

from . import llm

ORG = Path("data/org.json")  # organization materials are reused across campaigns
OBJECTIVES = {  # objective -> locked ad type
    "awareness": "brand", "qualified inquiries": "direct", "registrations": "direct", "enrollment": "direct",
    "visits": "direct", "installations": "direct", "sales": "direct", "evidence of demand": "direct",
}


def load_org():
    return json.loads(ORG.read_text()) if ORG.exists() else {"materials": []}


def save_org(org):
    ORG.parent.mkdir(parents=True, exist_ok=True)
    ORG.write_text(json.dumps(org, indent=1))


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


def extract(objective: str, constraints: dict) -> dict:
    org = load_org()
    mats = "\n\n".join(f"### {m['name']}\n{m['text']}" for m in org["materials"])[:20000]
    return llm.chat_json(
        "You are a senior strategist at a marketing agency reading a client's materials. The client is an expert; "
        "organise what they gave you, never lecture. Ask only for details that block a campaign.",
        f"Materials:\n{mats}\n\nObjective: {objective}\nConstraints: {json.dumps(constraints)}\n"
        'Return {"offering": str, "available": "built|unbuilt", "audience": str (who and where), '
        '"goal": str (one sentence, measurable), "key_messages": [str], "proof_points": [str], '
        '"destination": str (where people should land: store/booking/admissions/visitor info/early-access page), '
        '"success_metric": str, "missing": [str] (max 3 critical questions, empty if none)}', temperature=0.3)


def next_experiment(campaign: dict, ads: list[dict]) -> dict:
    tested = [{"headline": a["content"].get("headline"), "visual": a["content"].get("visual"),
               "platform": a["content"].get("platform"), "style": a["style"], "real_score": a["real_score"],
               "sim_score": a["sim_score"]} for a in ads]
    return llm.chat_json(
        "You are a performance marketing lead reviewing a live experiment. Be specific and practical. "
        "A weak creative is not proof the offering has no market; say what the evidence does and does not show.",
        f"Campaign: {json.dumps(campaign)}\nTested ads with real scores (z vs campaign baseline) and simulation "
        f"scores:\n{json.dumps(tested)}\n"
        'Return {"what_worked": [str], "what_didnt": [str], "caution": str, '
        '"next": {"hypothesis": str, "change": str, "audience": str, "channel": str, "success_metric": str}}',
        temperature=0.4)
