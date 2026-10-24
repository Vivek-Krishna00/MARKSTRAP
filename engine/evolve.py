"""The evolutionary loop. One term = interact (nurture) -> produce & judge (frozen) -> reproduce (queens) & age.

Nature: each agent's genome (prompt, strategy, lessons) is inherited inside its breed and caste.
Nurture: in the interact phase a caste learns a lesson from its best ad; children inherit it at birth.
Breeders: competing queens pick parents and lay keeper or explorer children; they are rated and culled.
"""
import json
import math
import random
import statistics
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from . import audience, llm, memory, personas
from .db import get, put, row

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text())
QUEEN_RULES = ["top", "untried", "wild"]
REACTION = {"share": 1.0, "engage": 0.6, "ignore": 0.0, "dislike": -0.5}
_db_lock = threading.Lock()  # one sqlite connection shared by the judging threads
PART = {"copywriter": "copy", "visual_maker": "visual", "font_picker": "font", "posting_manager": "posting"}


def _id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def dials(con):
    return get(con, "dials") or dict(CFG["dials"])


def term_no(con):
    return get(con, "term", 0)


def caste_cfg(breed, caste):
    return CFG["breeds"][breed]["castes"][caste]


def alive(con, **where):
    sql = "SELECT * FROM agents WHERE alive=1" + "".join(f" AND {k}=?" for k in where)
    return [row(r) for r in con.execute(sql, tuple(where.values()))]


# ---------- campaign ----------

def seed_campaign(con, goal: str, market: str, ad_type: str, brief: dict | None = None,
                  constraints: dict | None = None):
    assert ad_type in ("direct", "brand"), "ad_type is locked to direct or brand"
    put(con, "campaign", {"goal": goal, "market": market, "ad_type": ad_type,
                          "brief": brief or {}, "constraints": constraints or {}})
    put(con, "term", 0)
    put(con, "dials", dict(CFG["dials"]))
    d = dials(con)
    seed = random.randrange(2**31)
    put(con, "personas", make_people(goal, market, d["population"], d["naming_batch"], seed))
    put(con, "persona_seed", seed)
    for breed, b in CFG["breeds"].items():
        for caste, c in b["castes"].items():
            for _ in range(c["target"]):
                _insert_agent(con, breed, caste, {"prompt": c["seed"], "strategy": "", "lessons": []},
                              [], "seed", None, 0)
    for i in range(d["queens"]):
        con.execute("INSERT INTO queens (id, rule) VALUES (?,?)", (_id("queen"), QUEEN_RULES[i % 3]))
    con.commit()


def _insert_agent(con, breed, caste, genome, parents, kind, queen, born):
    aid = _id(breed[:4])
    con.execute("INSERT INTO agents (id, breed, caste, genome, parents, child_kind, queen, born, last_offspring)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (aid, breed, caste, json.dumps(genome), json.dumps(parents), kind, queen, born, born))
    return aid


# ---------- phase 1: interact (nurture) ----------

def interact(con, term):
    """Each caste studies its best ad of last term and writes one lesson. Lessons land at birth, not mid-life."""
    best = {}
    for a in con.execute("SELECT * FROM ads WHERE term=? ORDER BY COALESCE(real_score, sim_score) DESC",
                         (term - 1,)):
        a = row(a)
        for m in a["team"]:
            key = f"{m['breed']}/{m['caste']}"
            best.setdefault(key, {"content": a["content"], "why": _reasons(a, m["breed"])})
    if not best:
        return {}
    out = llm.chat_json(
        "You are a mentor watching a team of ad makers. Write one short, concrete lesson per caste.",
        f"Best ad each caste worked on last term, with audience reasons:\n{json.dumps(best)[:6000]}\n"
        'Return {"lessons": {"<breed/caste>": "<lesson>"}}', temperature=0.4).get("lessons", {})
    lessons = get(con, "lessons", {})
    for k, v in out.items():
        lessons.setdefault(k, []).append(v)
        lessons[k] = lessons[k][-3:]
    put(con, "lessons", lessons)
    return out


def _reasons(ad, breed):
    part = PART[breed]
    return [r.get("parts", {}).get(part, {}).get("why", "") for r in (ad["reactions"] or [])][:4]


# ---------- phase 2: produce and judge (genomes frozen) ----------

def assemble_teams(con, n):
    tested = {r["id"]: 0 for r in con.execute("SELECT id FROM agents WHERE alive=1")}
    for (team,) in con.execute("SELECT team FROM ads"):
        for m in json.loads(team):
            if m["id"] in tested:
                tested[m["id"]] += 1
    teams = [[] for _ in range(n)]
    for breed, b in CFG["breeds"].items():
        pool = sorted(alive(con, breed=breed), key=lambda a: (tested[a["id"]], random.random()))
        for i, team in enumerate(teams):
            if pool and (b["required"] or random.random() < 0.7):
                team.append(pool[i % len(pool)])
    return teams


def make_ad(campaign, team):
    brief = "\n".join(f"- {a['breed']} ({a['caste']}): {a['genome']['prompt']} {a['genome'].get('strategy', '')}"
                      f" Lessons: {'; '.join(a['genome'].get('lessons', []))}" for a in team)
    return llm.chat_json(
        "You are a small creative team making ONE social media ad. Each member follows their own instructions.",
        f"Campaign goal: {campaign['goal']}\nMarket: {campaign['market']}\nAd type: {campaign['ad_type']}\n"
        f"Client brief: {json.dumps(campaign.get('brief', {}))}\n"
        f"Hard constraints (language, brand rules, required info, claims you must NEVER make): "
        f"{json.dumps(campaign.get('constraints', {}))}\n"
        f"Team:\n{brief}\n"
        'Return {"headline": str, "body": str (the caption), "format": "image|video|carousel", '
        '"seen": str (exactly what a person scrolling past perceives, in order, as plain text. Video: second by '
        'second, the 0-2s hook first, what is on screen, on-screen text, voiceover/audio. Image: what is in frame '
        'and any overlay text. Carousel: what each slide shows. No production notes), '
        '"visual": str (art direction for rendering the image later), '
        '"font": str, "platform": "instagram|youtube|tiktok|x|linkedin", "post_time": str}')


def judge(people, ad, lessons):
    """Batched judge: the people see only what a scroller sees (audience.ad_text), never the maker's notes."""
    crowd = [{k: p.get(k) for k in ("name", "age", "habits", "tendencies")} for p in people]
    return llm.chat_json(
        "You simulate a crowd of real people scrolling their feed. Stay in character; most ads get ignored. "
        + personas.EXPRESSION,
        f"Audience:\n{json.dumps(crowd)}\n\nWhat this audience remembers from real campaigns "
        f"(react colder to ideas like past flops, warmer to ideas like past wins):\n"
        f"{chr(10).join(lessons) or 'nothing yet'}\n\nWhat they see on {ad.get('platform', 'their feed')}:\n"
        f"{audience.ad_text(ad)}\n"
        'For every persona return {"reactions": [{"persona": str, "reaction": "share|engage|ignore|dislike", '
        '"parts": {"copy": {"score": -1..1, "why": str}, "visual": {...}, "font": {...}, "posting": {...}}}]}',
        temperature=0.7)["reactions"]


def sim_score(reactions, seen, boredom_rate):
    raw = statistics.mean(REACTION.get(r.get("reaction"), 0.0) for r in reactions) if reactions else 0.0
    return (raw + 0.5) / 1.5 * (1 - boredom_rate) ** seen


def make_people(goal: str, market: str, n: int, batch: int, seed: int) -> list[dict]:
    """n people from the personality model; the LLM only names them and gives media habits."""
    sampled = personas.sample_people(n, seed)
    profiles = [personas.describe(f) for _, f in sampled]
    people = []
    for start in range(0, len(sampled), batch):  # names + habits only, in batches
        chunk = list(enumerate(zip(sampled, profiles)))[start:start + batch]
        got = llm.chat_json(
            "You give names and media habits to audience archetypes for a marketing simulation. "
            "Their age and personality are fixed; do not change or restate them. Every name is different.",
            f"Target market: {market}\nCampaign: {goal}\nNames already used: {[p['name'] for p in people]}\n"
            + "\n".join(f"{i}. Age {a}. {' '.join(t)}" for i, ((a, _), t) in chunk)
            + '\nFor each numbered person return {"personas": [{"name": str, "habits": str (platforms, '
              'when and why they scroll)}]} in the same order.', temperature=0.9)["personas"]
        people += [dict(got[j % len(got)]) for j in range(len(chunk))]
    used = set()
    for i, p in enumerate(people):  # names are memory keys: keep them unique
        if p.get("name") in used or not p.get("name"):
            p["name"] = f"{p.get('name') or 'Person'} {i}"
        used.add(p["name"])
    return [{**people[i], "age": a, "facets": f, "tendencies": t}
            for i, ((a, f), t) in enumerate(zip(sampled, profiles))]


def produce_and_judge(con, term, d):
    campaign, people = get(con, "campaign"), get(con, "personas")
    teams = [t for t in assemble_teams(con, d["ads_per_term"]) if t]

    feed = audience.enabled()

    def work(team):
        ad = make_ad(campaign, team)
        if feed:  # judged together below, in one shared feed
            return _id("ad"), team, ad, None
        q = f"{ad.get('headline', '')} {ad.get('visual', '')}"
        with _db_lock:
            lessons = memory.recall(con, q)
        return _id("ad"), team, ad, judge(random.sample(people, min(d["audience_size"], len(people))), ad, lessons)

    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(work, teams))
    if feed:  # MiroFish sizing: population/15 .. population/5 people act per round
        active = (max(1, len(people) // d["oasis_active_min_div"]), max(5, len(people) // d["oasis_active_max_div"]))
        history = {p["name"]: memory.recall_person(con, p["name"]) for p in people}
        out = audience.evaluate({aid: ad for aid, _, ad, _ in results}, people, memory.recall(con, campaign["goal"]),
                                d["oasis_rounds"], active, history)
        memory.remember_feed(con, term, out["episodes"])
        results = [(aid, team, ad, out["ads"][aid]["reactions"]) for aid, team, ad, _ in results]

    for aid, team, ad, reactions in results:
        style = "/".join(f"{a['caste']}" for a in team if a["breed"] in ("copywriter", "visual_maker"))
        seen = con.execute("SELECT COUNT(*) FROM ads WHERE style=? AND term>=?",
                           (style, term - d["boredom_recovery_terms"])).fetchone()[0]
        score = sim_score(reactions, seen, d["boredom_rate"])
        dem = (con.execute("SELECT n FROM demotions WHERE style=?", (style,)).fetchone() or [0])[0]
        shortlisted = score >= d["send_bar"] + d["reclimb_penalty"] * dem
        if not shortlisted:
            _demote(con, style)
        con.execute("INSERT INTO ads (id, term, ad_type, style, team, content, reactions, sim_score, shortlisted)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (aid, term, campaign["ad_type"], style,
                     json.dumps([{"id": a["id"], "breed": a["breed"], "caste": a["caste"]} for a in team]),
                     json.dumps(ad), json.dumps(reactions), score, int(shortlisted)))
    con.commit()
    _credit(con, term)


def _demote(con, style):
    con.execute("INSERT INTO demotions VALUES (?,1) ON CONFLICT(style) DO UPDATE SET n=n+1", (style,))


def _credit(con, term):
    """Simulation credits each part separately: ad score + that member's part rating."""
    per = {}
    for a in con.execute("SELECT * FROM ads WHERE term=?", (term,)):
        a = row(a)
        for m in a["team"]:
            if a["real_score"] is not None:
                f = _sigmoid(a["real_score"])  # reality overrides, shared by the whole team
            else:
                parts = [r.get("parts", {}).get(PART[m["breed"]], {}).get("score", 0) for r in a["reactions"]]
                f = a["sim_score"] + 0.25 * (statistics.mean(_num(p) for p in parts) if parts else 0)
            per.setdefault(m["id"], []).append(f)
    for aid, fs in per.items():
        con.execute("UPDATE agents SET fitness=? WHERE id=?", (statistics.mean(fs), aid))
    con.commit()


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _sigmoid(z):
    return 1 / (1 + math.exp(-z))


# ---------- phase 3: reproduce (queens) and age ----------

def reproduce(con, term, d):
    queens = [dict(q) for q in con.execute("SELECT * FROM queens WHERE alive=1")]
    crossed = set(map(tuple, get(con, "crossed", [])))
    medians = get(con, "caste_medians", {})
    lessons = get(con, "lessons", {})
    qi = 0
    for breed, b in CFG["breeds"].items():
        for caste, c in b["castes"].items():
            pop = sorted(alive(con, breed=breed, caste=caste), key=lambda a: -a["fitness"])
            if not pop:
                continue
            key = f"{breed}/{caste}"
            elite = pop[:max(1, math.ceil(d["elite_share"] * len(pop)))]
            eligible = pop[:max(1, math.ceil((1 - c["gate"]) * len(pop)))]
            med = statistics.median(a["fitness"] for a in pop)
            explorer = d["explorer_share"] + (d["explorer_stress_boost"] if med < medians.get(key, med) else 0)
            medians[key] = med
            births = max(c["target"] - len(pop), 0) + len(eligible)
            for _ in range(births):
                q = queens[qi % len(queens)]
                qi += 1
                p1, p2 = pick_parents(q["rule"], eligible, pop, crossed)
                kind = "explorer" if random.random() < explorer else "keeper"
                genome = breed_genome(kind, p1["genome"], p2["genome"], breed, caste)
                genome["lessons"] = (p1["genome"].get("lessons", []) + lessons.get(key, []))[-3:]
                _insert_agent(con, breed, caste, genome, [p1["id"], p2["id"]], kind, q["id"], term)
                crossed.add(tuple(sorted((p1["id"], p2["id"]))))
                con.execute("UPDATE agents SET last_offspring=? WHERE id IN (?,?)", (term, p1["id"], p2["id"]))
            age_out(con, term, d, breed, caste, {a["id"] for a in elite})
    put(con, "crossed", [list(p) for p in crossed])
    put(con, "caste_medians", medians)
    rate_queens(con, term, d)
    con.commit()


def pick_parents(rule, eligible, pop, crossed):
    w = [max(a["fitness"], 0.01) for a in eligible]  # offspring scale with score
    if rule == "untried":
        pairs = [(a, b) for a in eligible for b in eligible
                 if a["id"] < b["id"] and (a["id"], b["id"]) not in crossed]
        if pairs:
            return random.choice(pairs)
    if rule == "wild":
        return random.choices(eligible, w)[0], random.choice(pop)
    return tuple(random.choices(eligible, w, k=2))


def breed_genome(kind, g1, g2, breed, caste):
    if kind == "keeper":
        ask = ("Make a SMALL, safe mutation: rewrite exactly one part of this genome slightly "
               f"(e.g. 'bold fonts' -> 'bold fonts with high contrast').\nGenome: {json.dumps(g1)}")
    else:
        ask = ("Cross these two parent genomes and make a LARGE, bold mutation. Most explorers fail; "
               f"aim for something genuinely new but still a {caste} {breed}.\n"
               f"Parent A: {json.dumps(g1)}\nParent B: {json.dumps(g2)}")
    out = llm.chat_json(f"You breed instructions for a {breed} agent of the '{caste}' style.",
                        ask + '\nReturn {"prompt": str, "strategy": str}', temperature=1.0 if kind == "explorer" else 0.5)
    return {"prompt": out.get("prompt", g1["prompt"]), "strategy": out.get("strategy", "")}


def age_out(con, term, d, breed, caste, protected):
    """No offspring for N terms -> archive (never delete). Then cap the caste, sparing newborns and elites."""
    c = caste_cfg(breed, caste)
    for a in sorted(alive(con, breed=breed, caste=caste), key=lambda a: a["fitness"]):
        if a["id"] in protected or len(alive(con, breed=breed)) <= 1:
            continue
        old = term - a["last_offspring"] >= d["terms_without_offspring"]
        over = len(alive(con, breed=breed, caste=caste)) > c["target"] and a["born"] < term
        if old or over:
            con.execute("UPDATE agents SET alive=0 WHERE id=?", (a["id"],))


def rate_queens(con, term, d):
    ratings = {}
    for q in con.execute("SELECT id FROM queens WHERE alive=1"):
        fs = [r[0] for r in con.execute("SELECT fitness FROM agents WHERE queen=? AND born=?", (q[0], term - 1))]
        if fs:
            ratings[q[0]] = statistics.mean(fs)
    if len(ratings) < 2:
        return
    med = statistics.median(ratings.values())
    for qid, r in ratings.items():
        con.execute("UPDATE queens SET rating=?, poor_terms=CASE WHEN ? THEN poor_terms+1 ELSE 0 END WHERE id=?",
                    (r, r < med, qid))
    for q in con.execute("SELECT * FROM queens WHERE alive=1 AND poor_terms>=?", (d["queen_poor_terms"],)).fetchall():
        con.execute("UPDATE queens SET alive=0 WHERE id=?", (q["id"],))
        con.execute("INSERT INTO queens (id, rule) VALUES (?,?)", (_id("queen"), random.choice(QUEEN_RULES)))


# ---------- the term ----------

def run_generation(con):
    term = term_no(con) + 1
    d = dials(con)
    pending = get(con, "pending", {})
    if pending:  # dial changes apply from the next term only
        d.update(pending)
        put(con, "dials", d)
        put(con, "pending", {})
    interact(con, term)
    produce_and_judge(con, term, d)
    reproduce(con, term, d)
    put(con, "term", term)
    return term


def set_dial(con, name, value):
    if name not in dials(con):
        raise KeyError(f"unknown dial {name}")
    p = get(con, "pending", {})
    p[name] = value
    put(con, "pending", p)
    con.execute("INSERT INTO dial_log (term, dial, value, ts) VALUES (?,?,?,strftime('%s','now'))",
                (term_no(con) + 1, name, json.dumps(value)))
    con.commit()


# ---------- reality ----------

def real_raw(r, ad_type, early_w):
    """Per-platform weighted ratios (saves/reach, not raw saves) plus early velocity."""
    signals = CFG["platforms"]["direct" if ad_type == "direct" else r.get("platform", "instagram")]
    total = 0.0
    for sig, (w, denom) in signals.items():
        v = float(r.get(sig) or 0)
        total += w * (v / max(float(r.get(denom) or 0), 1) if denom else v)
    early = float(r.get("engagement_first_hours") or 0) / max(float(r.get("impressions") or 0), 1)
    return total + early_w * early


def import_results(con, rows):
    """rows: dicts from the results CSV. Real scores override sim, are shared by the team, and teach the audience."""
    d, term = dials(con), term_no(con)
    matched = 0
    for r in rows:
        ad = con.execute("SELECT * FROM ads WHERE id=?", (r.get("ad_id"),)).fetchone()
        if ad:
            matched += 1
            con.execute("UPDATE ads SET real_raw=? WHERE id=?", (real_raw(r, ad["ad_type"], d["early_velocity_weight"]),
                                                                  r["ad_id"]))
    logs = [math.log1p(x[0]) for x in con.execute("SELECT real_raw FROM ads WHERE real_raw IS NOT NULL")]
    if not matched:
        raise ValueError("no row matched a known ad_id; use the downloaded results sheet")
    mu, sd = statistics.mean(logs), (statistics.pstdev(logs) or 1.0)  # baseline = this campaign's own results
    for r in rows:
        ad = con.execute("SELECT * FROM ads WHERE id=?", (r["ad_id"],)).fetchone()
        if not ad:
            continue
        z = max(-d["outlier_clip"], min(d["outlier_clip"], (math.log1p(ad["real_raw"]) - mu) / sd))
        con.execute("UPDATE ads SET real_score=? WHERE id=?", (z, ad["id"]))
        for m in json.loads(ad["team"]):
            con.execute("UPDATE agents SET fitness=? WHERE id=?", (_sigmoid(z), m["id"]))
        if z == 0:  # at the baseline (e.g. the only result so far): nothing to teach yet
            continue
        c = json.loads(ad["content"])
        kind = "win" if z > 0 else "flop"
        if kind == "flop":
            _demote(con, ad["style"])
        memory.remember(con, term, kind, f"'{c.get('headline')}' / {c.get('visual')} on {r.get('platform')} "
                                         f"(style {ad['style']}) scored {z:+.2f} vs campaign baseline")
    con.commit()
    return matched


def revive(con, agent_id):
    con.execute("UPDATE agents SET alive=1, last_offspring=? WHERE id=?", (term_no(con), agent_id))
    con.commit()


def lineage(con, agent_id, depth=6):
    a = con.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not a or depth == 0:
        return None
    a = row(a)
    a["parent_tree"] = [lineage(con, p, depth - 1) for p in dict.fromkeys(a["parents"])]
    return a
