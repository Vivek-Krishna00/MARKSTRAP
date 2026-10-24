"""Simulation vs reality, computed from stored scores. Reality wins every disagreement, and wrong
predictions are reported as plainly as right ones."""
import json
import statistics

from . import concepts, evolve
from .db import get

CFG = evolve.CFG["measurement"]


def metrics_for(objective: str) -> list[str]:
    return CFG["by_objective"].get(objective or "", ["clicks", "impressions"])


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: -values[i])
    r = [0] * len(values)
    for rank, i in enumerate(order, 1):
        r[i] = rank
    return r


def spearman(x, y):
    if len(x) < 2:
        return None
    rx, ry = _ranks(x), _ranks(y)
    n = len(x)
    return 1 - 6 * sum((a - b) ** 2 for a, b in zip(rx, ry)) / (n * (n * n - 1))


def _best(ads, key):
    by = {}
    for a in ads:
        k = key(a)
        if k:
            by.setdefault(k, []).append(a["real_score"])
    if not by:
        return None
    k = max(by, key=lambda k: statistics.mean(by[k]))
    return {"name": k, "real": round(statistics.mean(by[k]), 2), "concepts": len(by[k]),
            "others": len(by) - 1}


def compare(con) -> dict:
    tested = [a for a in (dict(r) for r in con.execute("SELECT * FROM ads WHERE real_score IS NOT NULL"))]
    if not tested:
        return {"tested": 0}
    for a in tested:
        a["content"] = json.loads(a["content"])
    rows = get(con, "results_rows", [])
    need = CFG["min_results_for_rank"]
    sims, reals = [a["sim_score"] or 0 for a in tested], [a["real_score"] for a in tested]
    sr, rr = _ranks(sims), _ranks(reals)
    n = len(tested)
    gap = max(CFG["rank_miss"], n // 3)  # how far apart predicted and real rank must be to call it a miss
    per = []
    for a, ps, pr in zip(tested, sr, rr):
        if n < need:
            verdict = "Too few results to judge"
        elif pr - ps >= gap:
            verdict = "Simulation overrated it"
        elif ps - pr >= gap:
            verdict = "Simulation underrated it"
        else:
            verdict = "Roughly as predicted"
        raw = [r for r in rows if r.get("ad_id") == a["id"]]
        per.append({"id": a["id"], "name": a["content"].get("concept_name") or a["content"].get("headline"),
                    "headline": a["content"].get("headline"), "platform": a["content"].get("platform"),
                    "predicted_rank": ps, "real_rank": pr, "sim_score": round(a["sim_score"] or 0, 3),
                    "real_score": round(a["real_score"], 2), "verdict": verdict,
                    "metrics": raw[-1] if raw else {}})
    per.sort(key=lambda p: p["real_rank"])
    rho = spearman(sims, reals) if n >= need else None
    top_pred = min(per, key=lambda p: p["predicted_rank"])
    top_real = per[0]
    msg = _best(tested, lambda a: concepts.approach_label(a["style"])["message"])
    vis = _best(tested, lambda a: concepts.approach_label(a["style"])["visual"])
    aud = {}
    for r in rows:
        if r.get("audience"):
            ad = next((a for a in tested if a["id"] == r.get("ad_id")), None)
            if ad:
                aud.setdefault(r["audience"], []).append(ad["real_score"])
    best_aud = ({"name": max(aud, key=lambda k: statistics.mean(aud[k])),
                 "real": round(max(statistics.mean(v) for v in aud.values()), 2)} if aud else None)
    uncertain = []
    if n < need:
        uncertain.append(f"Only {n} concept{'s' if n != 1 else ''} with real results; rankings need at least {need}.")
    if not aud:
        uncertain.append("Results are not split by audience, so we cannot say which audience responded best.")
    if len({p["platform"] for p in per}) > 1:
        uncertain.append("Concepts ran on different platforms, so part of the difference may be the platform.")
    uncertain.append("Scores are relative to this campaign's own results, not to an industry benchmark.")
    right = [p for p in per if p["verdict"] == "Roughly as predicted"]
    wrong = [p for p in per if p["verdict"].startswith("Simulation")]
    return {"tested": n, "rank_agreement": None if rho is None else round(rho, 2),
            "top_predicted": top_pred["name"], "top_real": top_real["name"],
            "top_match": top_pred["id"] == top_real["id"], "concepts": per,
            "right": [p["name"] for p in right], "wrong": [p["name"] for p in wrong],
            "best_concept": top_real["name"], "best_message": msg, "best_visual": vis, "best_audience": best_aud,
            "uncertain": uncertain}
