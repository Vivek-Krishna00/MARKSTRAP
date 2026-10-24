import json
import random

import pytest

from engine import db, evolve, llm


def fake_llm(system, user, temperature=0.8):
    if "media habits" in system:
        return {"personas": [{"name": f"p{i}", "traits": "", "habits": ""} for i in range(3)]}
    if "mentor" in system:
        return {"lessons": {"copywriter/tension": "lead with the conflict"}}
    if "creative team" in system:
        return {"headline": random.choice(["cake rush", "midnight cake"]), "body": "b", "visual": "v",
                "font": "f", "platform": "instagram", "post_time": "18:00", "format": "image"}
    if "crowd" in system:
        cold = "FLOP" in user  # the audience remembers a real flop and reacts colder
        return {"reactions": [{"persona": "p", "reaction": "ignore" if cold else "share",
                               "parts": {"copy": {"score": 0.5, "why": "ok"}}}] * 3}
    if "breed instructions" in system:
        return {"prompt": "mutated", "strategy": "s"}
    raise AssertionError(system)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", fake_llm)
    c = db.connect(tmp_path / "t.db")
    evolve.seed_campaign(c, "make a cake shop go viral", "Bangalore students", "direct")
    return c


def test_generation_keeps_castes_capped_and_breeds_alive(con):
    for _ in range(4):
        evolve.run_generation(con)
    for breed, b in evolve.CFG["breeds"].items():
        assert evolve.alive(con, breed=breed), f"{breed} went extinct"
        for caste, c in b["castes"].items():
            pop = evolve.alive(con, breed=breed, caste=caste)
            newborns = [a for a in pop if a["born"] == evolve.term_no(con)]
            assert len(pop) - len(newborns) <= c["target"]


def test_children_stay_in_caste_and_inherit_lessons(con):
    evolve.run_generation(con)
    evolve.run_generation(con)
    for a in map(db.row, con.execute("SELECT * FROM agents WHERE born>0")):
        for pid in a["parents"]:
            p = db.row(con.execute("SELECT * FROM agents WHERE id=?", (pid,)).fetchone())
            assert (p["breed"], p["caste"]) == (a["breed"], a["caste"])
    kids = [db.row(r) for r in con.execute("SELECT * FROM agents WHERE born=2 AND caste='tension'")]
    assert any("lead with the conflict" in k["genome"]["lessons"] for k in kids)


def test_keeper_explorer_split_follows_dial(con):
    con.execute("UPDATE meta SET v=? WHERE k='dials'", (json.dumps({**evolve.dials(con), "explorer_share": 1.0,
                                                                  "explorer_stress_boost": 0}),))
    evolve.run_generation(con)
    kinds = {r[0] for r in con.execute("SELECT child_kind FROM agents WHERE born=1")}
    assert kinds == {"explorer"}


def test_age_out_archives_never_deletes(con):
    n = con.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    for _ in range(4):
        evolve.run_generation(con)
    assert con.execute("SELECT COUNT(*) FROM agents WHERE alive=0").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM agents").fetchone()[0] >= n


def test_real_score_shared_by_team_ratios_and_flop_memory(con):
    evolve.run_generation(con)
    ads = [db.row(r) for r in con.execute("SELECT * FROM ads")]
    good, bad = ads[0], ads[1]
    evolve.import_results(con, [
        {"ad_id": good["id"], "platform": "instagram", "impressions": 1000, "clicks": 100, "purchases": 20},
        {"ad_id": bad["id"], "platform": "instagram", "impressions": 1000, "clicks": 1, "purchases": 0}])
    fits = {r[0] for m in bad["team"] for r in con.execute("SELECT fitness FROM agents WHERE id=?", (m["id"],))}
    assert len(fits) == 1  # whole team shares the real verdict
    assert evolve.real_raw({"clicks": 10, "impressions": 100}, "direct", 0) == \
        evolve.real_raw({"clicks": 100, "impressions": 1000}, "direct", 0)  # ratios, not counts
    assert con.execute("SELECT COUNT(*) FROM memory WHERE kind='flop'").fetchone()[0] == 1
    evolve.run_generation(con)
    later = [r[0] for r in con.execute("SELECT sim_score FROM ads WHERE term=2")]
    assert max(later) < min(a["sim_score"] for a in ads)  # remembered flop cools later ads


def test_reclimb_bar_rises_with_demotions(con):
    con.execute("INSERT INTO demotions VALUES ('tension/bold', 3)")
    d = {**evolve.dials(con), "send_bar": 0.5, "reclimb_penalty": 0.2}
    assert d["send_bar"] + d["reclimb_penalty"] * 3 > 1.0  # unreachable: score is in [0,1]


def test_poor_queen_is_culled(con):
    qs = [r[0] for r in con.execute("SELECT id FROM queens")]
    for q, f in zip(qs, (0.9, 0.8, 0.1)):
        evolve._insert_agent(con, "copywriter", "tension", {"prompt": ""}, [], "keeper", q, 0)
        con.execute("UPDATE agents SET fitness=? WHERE queen=?", (f, q))
    d = {**evolve.dials(con), "queen_poor_terms": 1}
    evolve.rate_queens(con, 1, d)
    assert con.execute("SELECT alive FROM queens WHERE id=?", (qs[2],)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM queens WHERE alive=1").fetchone()[0] == 3


def test_dials_apply_next_term_and_are_logged(con):
    evolve.set_dial(con, "ads_per_term", 2)
    assert evolve.dials(con)["ads_per_term"] == 6
    evolve.run_generation(con)
    assert con.execute("SELECT COUNT(*) FROM ads WHERE term=1").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM dial_log").fetchone()[0] == 1


def test_audience_personality_comes_from_fitted_model_not_llm(con):
    from engine import personas
    people = db.get(con, "personas")
    assert len(people) == evolve.dials(con)["population"]
    assert len({p["name"] for p in people}) == len(people)  # named in batches, unique (they key memory)
    phrases = {b for pair in personas.BEHAVIORS.values() for b in pair}
    assert all(any(p in t for p in phrases) for person in people for t in person["tendencies"])
    personas_ok = __import__("subprocess").run(
        [__import__("sys").executable, "-m", "engine.personas"], capture_output=True, text=True)
    assert personas_ok.stdout.strip() == "ok", personas_ok.stderr


def test_agency_flow_end_to_end(tmp_path, monkeypatch):
    """Materials -> brief -> confirm -> explore -> approve -> launch sheet -> results -> next experiment."""
    import importlib
    import time
    monkeypatch.setenv("DB_PATH", str(tmp_path / "e.db"))
    monkeypatch.chdir(tmp_path)

    def agency_llm(system, user, temperature=0.8):
        if "strategist" in system:
            return {"offering": "cakes", "available": "built", "audience": "students", "goal": "100 orders",
                    "key_messages": ["fresh"], "proof_points": [], "destination": "order page",
                    "success_metric": "orders", "missing": []}
        if "performance marketing lead" in system:
            return {"what_worked": ["x"], "what_didnt": ["y"], "caution": "c",
                    "next": {"hypothesis": "h", "change": "c", "audience": "a", "channel": "ig", "success_metric": "s"}}
        return fake_llm(system, user, temperature)

    monkeypatch.setattr(llm, "chat_json", agency_llm)
    importlib.reload(db)
    from engine import api, brief
    importlib.reload(api)
    from fastapi.testclient import TestClient
    c = TestClient(api.app)
    assert c.post("/api/materials", data={"text": "Fresh cakes near campus"}).status_code == 200
    assert c.post("/api/brief", json={"objective": "sales", "constraints": {"restricted_claims": "no health claims"}}).is_success
    assert c.post("/api/brief/confirm", json={"brief": {"goal": "100 orders", "audience": "students"}}).is_success
    assert c.post("/api/explore?rounds=1").is_success
    for _ in range(50):
        if not c.get("/api/state").json()["busy"]:
            break
        time.sleep(0.1)
    s = c.get("/api/state").json()
    assert s["campaign"]["ad_type"] == "direct" and s["campaign"]["constraints"]["restricted_claims"]
    ad = s["ads"][0]["id"]
    c.post(f"/api/ads/{ad}/approval", json={"status": "approved"})
    sheet = c.get("/api/launch.csv").text
    assert ad in sheet and len(sheet.splitlines()) == 2
    c.post("/api/results", files={"file": ("r.csv", f"ad_id,platform,impressions,clicks\n{ad},instagram,1000,5\n")})
    assert c.post("/api/next").json()["next"]["hypothesis"] == "h"
    assert c.get("/api/state").json()["campaign"]["brief"]["current_experiment"]["hypothesis"] == "h"
    assert all(c.get(u).status_code == 200 for u in ("/", "/app", "/console"))

    from engine import render
    monkeypatch.setattr(render, "OUT", tmp_path / "renders")
    monkeypatch.setattr(render, "_gemini", lambda prompt, aspect, vertex=False: b"\x89PNG fake")
    other = next(a["id"] for a in c.get("/api/state").json()["ads"] if a["id"] != ad)
    assert c.post(f"/api/ads/{other}/render").status_code == 400  # only approved concepts are rendered
    assert c.post(f"/api/ads/{ad}/render").json()["url"] == f"/renders/{ad}.png"
    assert c.get(f"/renders/{ad}.png").content == b"\x89PNG fake"
    assert ad in c.get("/api/state").json()["renders"]


def test_oasis_feed_path_scores_with_existing_vocabulary(con, monkeypatch):
    from engine import audience, memory
    seen = {}

    def fake_evaluate(ads, people, lessons, rounds, active=None, history=None, workdir=None):
        seen.update(n=len(ads), people=len(people), rounds=rounds, active=active, history=history)
        first = next(iter(ads))
        return {"ads": {a: {"reactions": [{"persona": "p", "reaction": "share" if a == first else "ignore"}] * 3,
                            "counts": {}} for a in ads},
                "episodes": [{"people": [people[0]["name"]],
                              "text": f"[t] [twitter round 1] {people[0]['name']}: liked Brand's post: «cake»"}]}

    monkeypatch.setattr(audience, "enabled", lambda: True)
    monkeypatch.setattr(audience, "evaluate", fake_evaluate)
    evolve.run_generation(con)
    d, people = evolve.dials(con), db.get(con, "personas")
    ads = [db.row(r) for r in con.execute("SELECT * FROM ads ORDER BY sim_score DESC")]
    assert (seen["n"], seen["people"], seen["rounds"]) == (len(ads), d["population"], d["oasis_rounds"])
    assert seen["active"] == (max(1, len(people) // 15), max(5, len(people) // 5))   # MiroFish's sizing rule
    assert ads[0]["sim_score"] == 1.0 and ads[0]["shortlisted"]           # (1 + 0.5) / 1.5
    assert all(a["sim_score"] <= 1 / 3 + 1e-9 for a in ads[1:])             # ignored = neutral (less if bored)
    # people remember their own feed history next term; real-result recall never includes it
    assert memory.recall_person(con, people[0]["name"]) == [f"[t] [twitter round 1] {people[0]['name']}: liked Brand's post: «cake»"]
    assert not any("twitter round" in m for m in memory.recall(con, "cake"))
    evolve.run_generation(con)
    assert seen["history"][people[0]["name"]]


def test_makers_never_see_audience_personas_or_scoring(con, monkeypatch):
    prompts = []

    def spy(system, user, temperature=0.8):
        if "creative team" in system or "breed instructions" in system:
            prompts.append(system + user)
        return fake_llm(system, user, temperature)

    monkeypatch.setattr(llm, "chat_json", spy)
    evolve.run_generation(con)
    people = db.get(con, "personas")
    secret = {t for p in people for t in p["tendencies"]} | {"Strong tendency", "Somewhat inclined", "reaction"}
    assert prompts and not any(s in p for p in prompts for s in secret)


def test_feed_reader_maps_oasis_actions_to_reactions(tmp_path):
    import sqlite3
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "audience"))
    import feed
    d = sqlite3.connect(tmp_path / "t.db")
    d.executescript("""
      CREATE TABLE user (user_id INTEGER, agent_id INTEGER, name TEXT);
      CREATE TABLE post (post_id INTEGER, user_id INTEGER, original_post_id INTEGER, quote_content TEXT);
      CREATE TABLE trace (user_id INTEGER, action TEXT, info TEXT);
      CREATE TABLE "like" (post_id INTEGER, user_id INTEGER);
      CREATE TABLE dislike (post_id INTEGER, user_id INTEGER);
      CREATE TABLE comment (post_id INTEGER, user_id INTEGER, content TEXT);
      CREATE TABLE follow (follower_id INTEGER, followee_id INTEGER);
      CREATE TABLE mute (muter_id INTEGER, mutee_id INTEGER);
      INSERT INTO user VALUES (1,0,'brand0'),(2,1,'brand1'),(3,2,'user0'),(4,3,'user1'),(5,4,'user2');
      INSERT INTO post VALUES (10,1,NULL,NULL),(11,2,NULL,NULL),(12,3,10,NULL),(13,5,11,'lol no');
      INSERT INTO trace VALUES (3,'refresh','{"posts":[{"post_id":10},{"post_id":11}]}'),
                               (4,'refresh','{"posts":[{"post_id":12,"original_post_id":10}]}'),
                               (5,'refresh','{"posts":[{"post_id":11}]}');
      INSERT INTO "like" VALUES (10,4);
      INSERT INTO comment VALUES (11,3,'too pricey');
      INSERT INTO mute VALUES (3,2);
    """)
    d.commit()
    out = feed.read(tmp_path / "t.db", [{"id": "adA"}, {"id": "adB"}], ["Asha", "Ravi", "Meera"])
    a = {r["persona"]: r["reaction"] for r in out["adA"]["reactions"]}
    b = {r["persona"]: r for r in out["adB"]["reactions"]}
    assert a == {"Asha": "share", "Ravi": "engage"}             # repost; like seen via the repost
    assert b["Asha"]["reaction"] == "dislike" and b["Asha"]["parts"]["copy"]["why"] == "too pricey"
    assert b["Meera"]["reaction"] == "share" and out["adB"]["counts"]["quote"] == 1


def test_activity_text_and_episode_packing_follow_mirofish():
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "audience"))
    from activity import AgentActivity, episodes
    a = AgentActivity("twitter", 3, "Ravi", "QUOTE_POST", {"original_content": "Cake\nat 2am",
                      "original_author_name": "brand0", "quote_content": "need this"}, 2, "t")
    assert a.to_episode_text() == "[t] [twitter round 2] Ravi: quoted brand0's post: «Cake / at 2am», adding: «need this»"
    many = [AgentActivity("twitter", i, f"p{i}", "LIKE_POST", {"post_content": "x" * 900}, 1, "t") for i in range(30)]
    eps = episodes(many)
    assert len(eps) > 1 and all(len(e["text"]) <= 9_500 for e in eps)
    assert sum(len(e["people"]) for e in eps) == 30


def test_batched_judge_sees_only_what_a_scroller_sees(con, monkeypatch):
    calls = []

    def spy(system, user, temperature=0.8):
        if "crowd" in system:
            calls.append(user)
        return fake_llm(system, user, temperature)

    monkeypatch.setattr(llm, "chat_json", spy)
    evolve.run_generation(con)
    assert calls and all("post_time" not in u and '"facets"' not in u and "E4" not in u for u in calls)
    assert all(u.count('"tendencies"') == evolve.dials(con)["audience_size"] for u in calls)
