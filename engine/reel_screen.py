"""Screen finished Reels in MiroFish's feed, seen through Llama's eyes, with Llama's judgement weighted high.

1. Llama 4 watches each Reel's frames (reel.judge_frames): a blunt score, a viewer-eye `seen` that says how it
   looks (cheap included), and `couldBe`: the same Reel with its visual problems fixed, with a score for that.
2. Two OASIS feeds with the same people, so nobody compares a Reel with its own twin: one where every Reel
   appears as rendered, one where each appears as it could have been ("<name>~fixed"). People read the caption,
   Llama's description and its first impression; never scores. More people act per round than in the engine
   (reel.screen_active_div) so every post gets a fair look and reach isn't just recommender noise.
3. Per post: reach (people shown it / population), share, engage and dislike rates, the crowd score
   (evolve.sim_score, 0-10) and people's own words. Screening = w x Llama + (1 - w) x crowd,
   w = reel.screen_llama_weight (high by the user's choice: the crowd can't see pixels, Llama can).
Advisory only: real results still override every simulated score. Run: make reel-screen
"""
import hashlib
import json
import statistics
import time
from pathlib import Path

from . import audience, db, evolve, reel

DOCS = Path(__file__).resolve().parent.parent / "docs"


def population(con, goal: str, market: str) -> list[dict]:
    """The same people for every screening of this campaign, so runs are comparable."""
    key = "screen_people:" + hashlib.sha256(f"{goal}|{market}".encode()).hexdigest()[:12]
    people = db.get(con, key)
    if not people:
        d = evolve.CFG["dials"]
        people = evolve.make_people(goal, market, reel.CFG["screen_population"], d["naming_batch"],
                                    int(key[-8:], 16))
        db.put(con, key, people)
    return people


def candidates(con, ids: list[str] | None) -> list[dict]:
    """Reels with a rendered preview; latest per concept unless ids are given."""
    rows = [reel.load(con, r["id"]) for r in con.execute("SELECT id FROM reels ORDER BY updated")]
    rows = [r for r in rows if r.get("spec") and (reel.folder(r["id"]) / "preview.mp4").exists()]
    if ids:
        return [r for r in rows if r["id"] in ids]
    latest = {}
    for r in rows:
        latest[r["ad_id"]] = r
    return list(latest.values())


def post(spec: dict, brief: dict, seen: str, impression: str = "") -> dict:
    return {"headline": spec["title"], "body": f"{brief.get('idea', '')} {spec['callToAction']['onScreenText']}",
            "format": "video", "seen": seen + (f" First impression: {impression}" if impression else "")}


def crowd(reactions: list[dict], n: int) -> dict:
    k = {x: sum(r["reaction"] == x for r in reactions) for x in ("share", "engage", "ignore", "dislike")}
    shown = len(reactions)
    return {"reach": shown / n, "shown": shown, **{f"{x}_rate": k[x] / shown if shown else 0.0 for x in k},
            "crowd": round(10 * evolve.sim_score(reactions, 0, 0), 2)}


def screen(con, ids: list[str] | None = None) -> list[dict]:
    reels = candidates(con, ids)
    if not reels:
        raise SystemExit("no rendered Reels to screen (make reel-eval, or produce one in /app)")
    first = reels[0]["brief"]
    people = population(con, first.get("objective") or first.get("product", ""), first.get("audience", ""))
    who = {p["name"]: p for p in people}
    ads, meta = {}, {}
    for r in reels:
        mp4 = reel.folder(r["id"]) / "preview.mp4"
        frames = reel.keyframes(mp4, r["spec"])
        js = [reel.judge_frames(frames, r["spec"], r["brief"], temperature=0.7)
              for _ in range(reel.CFG["screen_judgements"])]  # one read is noisy; the feed gets the first's words
        j = js[0]
        name = r["ad_id"].removeprefix("eval-")
        llama = statistics.mean(statistics.mean(x["scores"].values()) for x in js if x["scores"])
        j["couldBeScore"] = statistics.mean(x["couldBeScore"] for x in js)
        ads[name] = post(r["spec"], r["brief"], j["seen"], j["verdict"])
        ads[f"{name}~fixed"] = post(r["spec"], r["brief"], j["couldBe"])
        meta[name] = {"reel": r["id"], "llama": llama, "verdict": j["verdict"], "seen": j["seen"]}
        meta[f"{name}~fixed"] = {"reel": r["id"], "llama": j["couldBeScore"], "verdict": "(Llama's estimate)",
                                 "seen": j["couldBe"]}
    d = evolve.CFG["dials"]
    n = len(people)
    lo, hi = reel.CFG["screen_active_div"]
    t = time.time()
    out = {"ads": {}}
    for world in (lambda k: "~" not in k, lambda k: "~" in k):  # as rendered | as it could have been
        part = {k: v for k, v in ads.items() if world(k)}
        out["ads"].update(audience.evaluate(part, people, [], d["oasis_rounds"], (n // lo, n // hi))["ads"])
    w = reel.CFG["screen_llama_weight"]
    rows = []
    for name, m in meta.items():
        reactions = out["ads"][name]["reactions"]
        c = crowd(reactions, n)
        words = [{"persona": x["persona"], "age": who.get(x["persona"], {}).get("age"), "reaction": x["reaction"],
                  "text": x["parts"]["copy"]["why"]} for x in reactions if x.get("parts", {}).get("copy", {}).get("why")]
        rows.append({"post": name, **m, **c, "score": round(w * m["llama"] + (1 - w) * c["crowd"], 2),
                     "words": words, "counts": out["ads"][name]["counts"]})
    for r in reels:  # keep the result on the Reel for the UI
        mine = [x for x in rows if x["reel"] == r["id"]]
        critic = r.get("critic") or {}
        reel.save(con, r["id"], critic={**critic, "screening": {"at": time.time(), "weight": w, "people": n,
                                                                "posts": mine}})
    write_report(rows, n, w, time.time() - t)
    return rows


def write_report(rows, n, w, secs):
    pct = lambda x: f"{x:.0%}"  # noqa: E731
    lines = [
        "# Reel screening: MiroFish feed with Llama's eyes", "",
        f"Run {time.strftime('%Y-%m-%d %H:%M')} · {n} simulated people (personality model) · two OASIS feeds "
        f"(as rendered / with fixes, same people) · "
        f"{evolve.CFG['dials']['oasis_rounds']} rounds · {secs / 60:.1f} min · `make reel-screen` · `engine/reel_screen.py`", "",
        f"Each Reel is screened twice, in separate feeds: **as rendered** (people read Llama's description of the real frames plus its "
        f"first impression) and **~fixed** (Llama's description of the same Reel with its visual problems fixed). "
        f"Screening score = {w:.0%} Llama + {1 - w:.0%} crowd. Advisory: real results override all of this.", "",
        "| Post | Llama (0–10) | Reach | Share | Engage | Dislike | Crowd (0–10) | **Screening** |",
        "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["post"]):
        lines.append(f"| {r['post']} | {r['llama']:.1f} | {pct(r['reach'])} ({r['shown']}) | {pct(r['share_rate'])} | "
                     f"{pct(r['engage_rate'])} | {pct(r['dislike_rate'])} | {r['crowd']:.1f} | **{r['score']:.1f}** |")
    lines += ["", "## How each could have performed", "",
              "| Reel | As rendered | With fixes | Gain |", "|---|---|---|---|"]
    by = {r["post"]: r for r in rows}
    for k, r in by.items():
        if "~" not in k and f"{k}~fixed" in by:
            f = by[f"{k}~fixed"]
            lines.append(f"| {k} | {r['score']:.1f} (reach {pct(r['reach'])}) | {f['score']:.1f} (reach "
                         f"{pct(f['reach'])}) | {f['score'] - r['score']:+.1f} |")
    for r in sorted(rows, key=lambda r: r["post"]):
        lines += ["", f"## {r['post']}", "", f"**What the feed was told it looks like:** {r['seen'][:700]}", "",
                  f"**Llama:** {r['verdict']}", ""]
        if r["words"]:
            lines += ["**What people said:**", ""] + [f"- *{x['persona']}, {x['age']}* ({x['reaction']}): "
                                                    f"“{x['text'][:220]}”" for x in r["words"][:5]]
        else:
            lines += ["*Nobody commented or quoted it.*"]
    (DOCS / "reel-screening.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:4 + len(rows) + 6 + len(rows) // 2 + 4]))
