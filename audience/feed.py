"""One shared feed for a term's ads, run by MiroFish's own OASIS runner. The only new code in audience/.

stdin : {"people": [{name, age, bio, persona, activity_level}], "ads": [{id, text}], "rounds": int, "active": [min, max]}
stdout: {"ads": {"<ad id>": {"reactions": [{persona, reaction: share|engage|ignore|dislike, actions}], "counts": {}}},
         "episodes": [{"people": [names], "text": "..."}]}   <- what people did, for the engine's graph memory

Each ad is posted by its own brand account (MiroFish's runner keys opening posts by account, one post each).
Brand accounts never act afterwards; people act for `rounds` rounds and see whatever the recommender shows them.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from activity import SKIP, AgentActivity, episodes
from profiles import OasisAgentProfile, save_twitter_csv

HERE = Path(__file__).resolve().parent


def build(job: dict, workdir: Path) -> Path:
    ads, people = job["ads"], job["people"]
    brands = [OasisAgentProfile(i, f"brand{i}", "Brand", "A brand page that posts ads.", "Posts ads.")
              for i in range(len(ads))]
    folk = [OasisAgentProfile(len(ads) + i, f"user{i}", p["name"], p["bio"], p["persona"], age=p.get("age"))
            for i, p in enumerate(people)]
    save_twitter_csv(brands + folk, str(workdir / "twitter_profiles.csv"))
    rounds = int(job["rounds"])
    lo, hi = job.get("active") or (len(people), len(people))
    config = {  # MiroFish simulation_config.json shape; lo..hi people act per round, no time-of-day effects
        "time_config": {"total_simulation_hours": rounds, "minutes_per_round": 60,
                        "agents_per_hour_min": lo, "agents_per_hour_max": hi,
                        "peak_hours": [], "off_peak_hours": []},
        "agent_configs": [{"agent_id": b.user_id, "entity_name": b.user_name, "activity_level": 0.0,
                           "active_hours": list(range(24))} for b in brands]
                         + [{"agent_id": f.user_id, "entity_name": f.name, "activity_level": p["activity_level"],
                             "active_hours": list(range(24))} for f, p in zip(folk, people)],
        "event_config": {"initial_posts": [{"poster_agent_id": i, "content": a["text"]} for i, a in enumerate(ads)]},
    }
    path = workdir / "simulation_config.json"
    path.write_text(json.dumps(config, ensure_ascii=False))
    return path


def read(db: Path, ads: list, names: list) -> dict:
    """Per ad: one reaction per person who was shown it, in the engine's existing vocabulary, plus raw counts."""
    con = sqlite3.connect(db)
    q = lambda sql, *a: con.execute(sql, a).fetchall()
    agent = dict(q("SELECT user_id, agent_id FROM user"))
    brand_ad = {u: ads[a]["id"] for u, a in agent.items() if a < len(ads)}
    post_ad = {pid: brand_ad[uid] for pid, uid in
               q("SELECT post_id, user_id FROM post WHERE original_post_id IS NULL") if uid in brand_ad}
    acts = {}  # (user, ad) -> set of actions
    for uid, info in q("SELECT user_id, info FROM trace WHERE action='refresh'"):
        for p in json.loads(info).get("posts", []):
            ad = post_ad.get(p.get("post_id")) or post_ad.get(p.get("original_post_id"))
            if ad:
                acts.setdefault((uid, ad), set()).add("seen")
    why = {}
    for table in ("like", "dislike", "comment"):
        cols = "post_id, user_id" + (", content" if table == "comment" else "")
        for pid, uid, *text in q(f"SELECT {cols} FROM {table}"):
            if pid in post_ad:
                acts.setdefault((uid, post_ad[pid]), set()).add(table)
                if text:
                    why[(uid, post_ad[pid])] = text[0]
    for orig, uid, quote in q("SELECT original_post_id, user_id, quote_content FROM post WHERE original_post_id IS NOT NULL"):
        if orig in post_ad:
            acts.setdefault((uid, post_ad[orig]), set()).add("quote" if quote else "repost")
            if quote:
                why[(uid, post_ad[orig])] = quote
    for table, who, whom in (("follow", "follower_id", "followee_id"), ("mute", "muter_id", "mutee_id")):
        for a, b in q(f"SELECT {who}, {whom} FROM {table}"):
            if b in brand_ad:
                acts.setdefault((a, brand_ad[b]), set()).add(table)
    out = {a["id"]: {"reactions": [], "counts": {}} for a in ads}
    for (uid, ad), done in acts.items():
        if uid in brand_ad:
            continue
        reaction = ("share" if done & {"repost", "quote"} else "dislike" if done & {"dislike", "mute"}
                    else "engage" if done & {"like", "comment", "follow"} else "ignore")
        r = {"persona": names[agent[uid] - len(ads)], "reaction": reaction, "actions": sorted(done)}
        if (uid, ad) in why:
            r["parts"] = {"copy": {"why": why[(uid, ad)]}}
        out[ad]["reactions"].append(r)
        for act in done:
            out[ad]["counts"][act] = out[ad]["counts"].get(act, 0) + 1
    return out


def activities(log: Path, n_brands: int) -> list:
    """The runner's actions.jsonl (MiroFish action_logger), people only, without no-op actions."""
    out = []
    for line in log.read_text().splitlines() if log.exists() else []:
        a = json.loads(line)
        if a.get("action_type") and a["agent_id"] >= n_brands and a["action_type"] not in SKIP:
            out.append(AgentActivity("twitter", a["agent_id"], a["agent_name"], a["action_type"],
                                     a.get("action_args") or {}, a["round"], a["timestamp"]))
    return out


def main():
    job = json.load(sys.stdin)
    workdir = Path(job.get("workdir") or tempfile.mkdtemp(prefix="feed-"))
    workdir.mkdir(parents=True, exist_ok=True)
    config = build(job, workdir)
    with open(workdir / "runner.log", "w") as log:
        subprocess.run([sys.executable, str(HERE / "run_parallel_simulation.py"), "--config", str(config),
                        "--twitter-only", "--max-rounds", str(job["rounds"]), "--no-wait"],
                       stdout=log, stderr=subprocess.STDOUT, check=True, env=os.environ)
    print(json.dumps({"ads": read(workdir / "twitter_simulation.db", job["ads"], [p["name"] for p in job["people"]]),
                      "episodes": episodes(activities(workdir / "twitter" / "actions.jsonl", len(job["ads"])))}))


if __name__ == "__main__":
    main()
