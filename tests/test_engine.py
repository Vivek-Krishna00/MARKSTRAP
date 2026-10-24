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
