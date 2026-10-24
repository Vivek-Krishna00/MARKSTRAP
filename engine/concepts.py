"""Concepts as a client sees them: distinct ideas, why each scored as it did, and who liked it.

Everything here reads the engine's stored ads and simulated reactions. Numbers (groups, confidence, score
reasons) are computed in Python; the one model call (review) only explains reactions already recorded.
Simulated reactions shortlist ideas; they are never presented as customer evidence.
"""
import hashlib
import json
import random
import re
import statistics
import uuid

from . import evolve, llm, memory
from .db import get, put, row

CFG = evolve.CFG["concepts"]
LIMITS = ("These are simulated people reacting to a written description of the ad, not real customers. "
          "Use them to shortlist, then let real results decide.")
STOP = set("the and for with your you our this that from into are was were have has will its it's not but all "
           "can more just than then them they their what when where which while who why how".split())


def approach_label(style: str) -> dict:
    """'tension/bold' -> plain words for the message approach and the visual approach."""
    parts = (style or "").split("/")
    castes = {c: v.get("label", c) for b in evolve.CFG["breeds"].values() for c, v in b["castes"].items()}
    return {"message": castes.get(parts[0], parts[0]) if parts and parts[0] else "",
            "visual": castes.get(parts[1], parts[1]) if len(parts) > 1 else ""}


def _words(c: dict) -> set:
    text = " ".join(str(c.get(k, "")) for k in ("concept_name", "main_idea", "headline", "body"))
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 3 and w not in STOP}


def overlap(a: dict, b: dict) -> float:
    x, y = _words(a), _words(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def distinct(ads: list[dict], decisions: dict, n: int | None = None) -> list[dict]:
    """One lead per distinct idea. Near-duplicates (or the same approach with similar words) become
    variations of it. Concepts the user already acted on always lead their own group."""
    n = n or CFG["shown"]
    th = CFG["dup_threshold"]
    order = sorted(ads, key=lambda a: (decisions.get(a["id"]) not in ("approved", "saved", "revise"),
                                       -(a["real_score"] if a.get("real_score") is not None else a["sim_score"] or 0)))
    groups = []
    for a in order:
        home = None
        if decisions.get(a["id"]) not in ("approved", "saved", "revise"):
            for g in groups:
                o = overlap(a["content"], g["lead"]["content"])
                if o >= th or (a["style"] == g["lead"]["style"] and o >= th / 2):
                    home = g
                    break
        if home:
            home["variations"].append(a)
        else:
            groups.append({"lead": a, "variations": []})
    shown = [g for g in groups if decisions.get(g["lead"]["id"]) != "rejected"][:n]
    rejected = [g for g in groups if decisions.get(g["lead"]["id"]) == "rejected"]
    return shown + rejected


# ---------- audience groups ----------

def _band(age):
    for lo, hi in CFG["age_bands"]:
        if lo <= (age or 0) <= hi:
            return f"Ages {lo}–{hi}"
    return "Other ages"


def _trait(facets: dict) -> str:
    means = {d: statistics.mean(v for k, v in facets.items() if k[0] == d) for d in "NEOAC"
             if any(k[0] == d for k in facets)}
    if not means:
        return ""
    d = max(means, key=lambda k: (abs(means[k] - 50), k))
    hi, lo = CFG["traits"][d]
    return hi if means[d] >= 50 else lo


def groups_for(people: list[dict]) -> dict:
    """name -> [age band, personality group]; deterministic, from the sampled facets, never the model."""
    return {p["name"]: [_band(p.get("age")), _trait(p.get("facets") or {})] for p in people}


def audience_breakdown(ad: dict, people: list[dict]) -> dict:
    gmap = groups_for(people)
    stats = {}
    for r in ad.get("reactions") or []:
        v = evolve.REACTION.get(r.get("reaction"), 0.0)
        for g in gmap.get(r.get("persona"), []):
            if g:
                stats.setdefault(g, []).append(v)
    vals = [evolve.REACTION.get(r.get("reaction"), 0.0) for r in ad.get("reactions") or []]
    overall = statistics.mean(vals) if vals else 0.0
    rows = [{"group": g, "people": len(v), "response": round(statistics.mean(v), 2)}
            for g, v in stats.items() if len(v) >= CFG["min_group_size"]]
    m = CFG["group_margin"]
    pos = sorted([r for r in rows if r["response"] >= overall + m], key=lambda r: -r["response"])
    neg = sorted([r for r in rows if r["response"] <= overall - m], key=lambda r: r["response"])
    split = None
    if pos and neg:
        split = {"liked": pos[0]["group"], "disliked": neg[0]["group"],
                 "gap": round(pos[0]["response"] - neg[0]["response"], 2)}
    return {"overall": round(overall, 2), "positive": pos, "negative": neg, "disagreement": split,
            "groups": sorted(rows, key=lambda r: -r["response"])}


# ---------- score explanation ----------

def counts(ad: dict) -> dict:
    n = {"share": 0, "engage": 0, "ignore": 0, "dislike": 0}
    for r in ad.get("reactions") or []:
        if r.get("reaction") in n:
            n[r["reaction"]] += 1
    return n


def explain(ad: dict, dials: dict, demotions: int = 0) -> dict:
    n = counts(ad)
    total = sum(n.values())
    vals = [evolve.REACTION.get(r.get("reaction"), 0.0) for r in ad.get("reactions") or []]
    raw = (statistics.mean(vals) + 0.5) / 1.5 if vals else 0.0
    familiar = raw > 0 and (ad.get("sim_score") or 0) < raw * 0.99
    bar = dials["send_bar"] + dials["reclimb_penalty"] * demotions
    why = []
    if total:
        why.append(f"{n['share']} of {total} simulated people would share it and {n['engage']} would engage; "
                   f"{n['ignore']} scrolled past and {n['dislike']} were annoyed.")
    if familiar:
        why.append("The score was lowered because the audience had recently seen similar ideas.")
    if demotions:
        why.append("This creative approach underperformed before, so it has to clear a higher bar.")
    why.append("It cleared the bar for a real test." if ad.get("shortlisted") else
               f"It did not clear the bar for a real test ({bar:.2f}).")
    spread = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    level = "Low" if total < CFG["confident_sample"] or spread > 0.6 else "Moderate"
    return {"counts": n, "people": total, "score": round(ad.get("sim_score") or 0, 3), "bar": round(bar, 3),
            "why": why, "confidence": level, "limits": LIMITS,
            "confidence_note": f"Based on {total} simulated reactions; "
                               f"{'they broadly agree' if spread <= 0.6 else 'they disagree a lot'}."}


def part_reasons(ad: dict, part: str, k: int = 4) -> list[dict]:
    out = []
    for r in ad.get("reactions") or []:
        p = (r.get("parts") or {}).get(part) or {}
        if p.get("why"):
            out.append({"persona": r.get("persona"), "score": evolve._num(p.get("score")), "why": p["why"]})
    return sorted(out, key=lambda x: -abs(x["score"]))[:k]


def confidential_hits(content: dict, texts: list[str]) -> list[str]:
    """Runs of words copied verbatim from a confidential source into the public concept."""
    k = CFG["confidential_span_words"]
    words = re.findall(r"[a-z0-9']+", " ".join(str(v) for v in content.values()).lower())
    spans = {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}
    hits = []
    for t in texts:
        tw = " ".join(re.findall(r"[a-z0-9']+", (t or "").lower()))
        hits += [s for s in spans if s in tw]
    return sorted(set(hits))[:3]


# ---------- review (one model call, cached per concept version) ----------

def _key(ad):
    return hashlib.sha256(json.dumps([ad["content"], ad.get("reactions")], sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


def review(con, ad: dict, confidential: list[str], force=False) -> dict:
    cache = get(con, "reviews", {})
    k = _key(ad)
    if not force and cache.get(ad["id"], {}).get("key") == k:
        return cache[ad["id"]]
    camp = get(con, "campaign") or {}
    reasons = {p: part_reasons(ad, p, 6) for p in ("copy", "visual", "font", "posting")}
    out = llm.chat_json(
        "You are a creative director explaining simulated audience reactions to a client. Be plain and specific. "
        "These reactions are simulated, not customer evidence; never overstate them. Check the concept strictly "
        "against the brief and the brand rules, and name anything a human must review before it goes live.",
        f"Brief: {json.dumps(camp.get('brief', {}))[:5000]}\nRules: {json.dumps(camp.get('constraints', {}))}\n"
        f"Concept: {json.dumps(ad['content'])}\nReaction counts: {json.dumps(counts(ad))}\n"
        f"Reasons by part: {json.dumps(reasons)[:6000]}\n"
        'Return {"summary": str (overall response in one sentence), "positives": [str], "negatives": [str], '
        '"ignored_because": [str], "message": str, "visual": str, "format": str, "platform": str, '
        '"brief_fit": "yes|partly|no", "brief_notes": str, "brand_fit": "yes|partly|no", "brand_notes": str, '
        '"human_review": [str] (claims, legal, sensitive or factual points a person must check)}', temperature=0.3)
    hits = confidential_hits(ad["content"], confidential)
    if hits:
        out.setdefault("human_review", []).insert(0, "Repeats wording from a confidential document: “"
                                                  + hits[0] + "…”. Remove it before publishing.")
    out["confidential_hits"] = hits
    out["key"] = k
    cache[ad["id"]] = out
    put(con, "reviews", cache)
    return out


def recommended(ad: dict, rv: dict | None) -> bool:
    if not ad.get("shortlisted"):
        return False
    rv = rv or {}
    return rv.get("brief_fit") != "no" and rv.get("brand_fit") != "no" and not rv.get("confidential_hits")


# ---------- revise and combine: new concepts tested on the same simulated audience ----------

def _judge_and_store(con, content: dict, style: str, origin: dict) -> str:
    people = get(con, "personas") or []
    d = evolve.dials(con)
    sample = random.sample(people, min(CFG["revision_audience"], len(people))) if people else []
    lessons = memory.recall(con, f"{content.get('headline', '')} {content.get('visual', '')}")
    reactions = evolve.judge(sample, content, lessons) if sample else []
    score = evolve.sim_score(reactions, 0, d["boredom_rate"])
    dem = (con.execute("SELECT n FROM demotions WHERE style=?", (style,)).fetchone() or [0])[0]
    aid = f"ad-{uuid.uuid4().hex[:6]}"
    camp = get(con, "campaign") or {}
    con.execute("INSERT INTO ads (id, term, ad_type, style, team, content, reactions, sim_score, shortlisted)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (aid, evolve.term_no(con), camp.get("ad_type", "direct"), style, "[]",
                 json.dumps({**content, **origin}), json.dumps(reactions), score,
                 int(score >= d["send_bar"] + d["reclimb_penalty"] * dem)))
    con.commit()
    return aid


def _ad(con, ad_id) -> dict:
    r = con.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not r:
        raise KeyError(ad_id)
    return row(r)


def revise(con, ad_id: str, feedback: str) -> str:
    ad = _ad(con, ad_id)
    camp = get(con, "campaign") or {}
    content = llm.chat_json(
        "You are a senior creative revising one social media ad after client feedback. Keep what the feedback "
        "does not mention; change what it asks for. Follow the brief and hard constraints exactly.",
        f"Brief: {json.dumps(camp.get('brief', {}))[:5000]}\nHard constraints: {json.dumps(camp.get('constraints', {}))}\n"
        f"Current concept: {json.dumps(ad['content'])}\nClient feedback: {feedback}\n" + evolve.AD_FORMAT,
        temperature=0.6)
    fb = get(con, "feedback", {})
    fb.setdefault(ad_id, []).append(feedback)
    put(con, "feedback", fb)
    return _judge_and_store(con, content, ad["style"], {"revised_from": ad_id, "feedback": feedback})


COMBINE_PARTS = ("main_idea", "headline", "body", "visual", "format", "platform", "post_time")


def combine(con, parts: dict) -> str:
    """parts: {part: ad_id}. The model joins the chosen parts into one coherent concept."""
    chosen = {}
    for part, aid in parts.items():
        if part in COMBINE_PARTS and aid:
            chosen[part] = _ad(con, aid)["content"].get(part, "")
    if len(set(parts.values())) < 2:
        raise ValueError("pick parts from at least two concepts")
    camp = get(con, "campaign") or {}
    content = llm.chat_json(
        "You are a senior creative combining parts of different ad concepts into ONE coherent ad. Keep each chosen "
        "part as close to the original as possible; adjust only what is needed for the parts to fit together.",
        f"Brief: {json.dumps(camp.get('brief', {}))[:5000]}\nHard constraints: {json.dumps(camp.get('constraints', {}))}\n"
        f"Chosen parts: {json.dumps(chosen)}\n" + evolve.AD_FORMAT, temperature=0.5)
    base = _ad(con, parts.get("headline") or next(iter(parts.values())))
    return _judge_and_store(con, content, base["style"], {"combined_from": sorted(set(parts.values()))})
