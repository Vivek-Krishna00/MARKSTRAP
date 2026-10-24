"""Organization -> product -> campaign -> brief -> concepts -> review -> launch -> results -> next, offline."""
import json
import random
import re
import time
from pathlib import Path

import pytest

from engine import agency, concepts, db, evolve, hub, llm, reality, render, research

from test_engine import fake_llm

SITE_APP = Path(__file__).resolve().parent.parent / "site" / "src" / "app"
PROMPTS = []


def agency_llm(system, user, temperature=0.8):
    PROMPTS.append(user)
    if "careful marketing researcher" in system:
        src = re.findall(r"\[(src-[0-9a-f]+)\] \(public source\)", user)
        own = re.findall(r"\[(src-[0-9a-f]+)\] \(from the organization\)", user)
        return {"findings": [
            {"section": "summary", "value": "Northwind makes cosy co-op games", "source": src[0],
             "evidence": "Northwind Games makes cosy co-op games"},
            {"section": "proof_points", "value": "Two million players", "source": own[0] if own else src[0],
             "evidence": "two million players"},
            {"section": "claims", "value": "Best studio in the world", "source": src[0],
             "evidence": "the best studio in the whole world"},  # not in the source: must stay unconfirmed
            {"section": "brand_voice", "value": "Warm and playful", "source": src[0],
             "evidence": "cosy co-op games"}],
            "products": [{"name": "Lantern Pass", "description": "Game subscription", "customers": "families",
                          "source": src[0], "evidence": "Lantern Pass subscription"}],
            "missing": ["Pricing in other countries"]}
    if "senior strategist" in system:
        return {"objective": "sales", "audience": "families who play together", "insight": "evenings are short",
                "offer": "first month free", "main_message": "Play together tonight", "evidence": ["two million players"],
                "action": "Start the free month", "platforms_formats": "Instagram Reels",
                "creative_direction": "warm", "brand_requirements": "no violence", "restrictions": "no price claims",
                "success_metric": "1,000 sign-ups", "basis": {"offer": "campaign"}, "assumptions": ["UK only"],
                "missing": ["Which countries?"]}
    if "creative director explaining" in system:
        return {"summary": "Liked by most", "positives": ["warm"], "negatives": ["generic"], "ignored_because": [],
                "message": "clear", "visual": "cosy", "format": "fits", "platform": "fits", "brief_fit": "yes",
                "brief_notes": "", "brand_fit": "yes", "brand_notes": "", "human_review": []}
    if "revising one social media ad" in system or "combining parts" in system:
        return {"concept_name": "Sofa Squad", "main_idea": "the couch is the arena", "headline": "Sofa squad, assemble",
                "body": "b", "visual": "v", "font": "f", "platform": "instagram", "post_time": "19:00",
                "format": "video", "emotion": "warmth", "why_it_may_work": "w", "risks": "r"}
    if "performance marketing lead" in system:
        return {"what_worked": ["x"], "what_didnt": ["y"], "not_proven": ["z"], "caution": "c",
                "next": {"hypothesis": "h", "change": "one change", "audience": "a", "channel": "ig",
                         "success_metric": "s", "keep_same": ["offer"]}}
    if "creative team" in system:
        return {"concept_name": random.choice(["Couch Co-op", "Night Quest"]), "main_idea": "play together",
                "headline": random.choice(["cosy night in", "quest after dinner"]), "body": "b", "visual": "v",
                "font": "f", "platform": "instagram", "post_time": "18:00", "format": "image",
                "emotion": "joy", "why_it_may_work": "w", "risks": "r"}
    return fake_llm(system, user, temperature)


SITE = {
    "https://northwind.test": "Northwind Games makes cosy co-op games. Lantern Pass subscription for families.",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "legacy-engine.db")
    monkeypatch.setattr(llm, "chat_json", agency_llm)
    monkeypatch.setattr(render, "OUT", tmp_path / "renders")
    monkeypatch.setattr(research, "crawl", lambda url, n: [{"url": url, "title": "Northwind", "text": SITE[url],
                                                            "links": []}])
    monkeypatch.setattr(research, "wikipedia", lambda name: None)
    monkeypatch.setattr(research, "fetch", lambda url: {"url": url, "title": "Rival", "text": "Rival games", "links": []})
    hub.init(tmp_path / "agency.db")
    from fastapi.testclient import TestClient
    from engine import api
    PROMPTS.clear()
    return TestClient(api.app)


def wait(c, url, key="busy", tries=200):
    for _ in range(tries):
        v = c.get(url).json()
        if not v.get(key) and (v.get("status") != "running"):
            return v
        time.sleep(0.05)
    raise AssertionError(f"{url} stayed busy")


def make_org(c):
    o = c.post("/api/orgs", json={"name": "Northwind Games", "fields": {
        "website": "https://northwind.test", "competitors": "rival.test", "voice": "warm", "colours": "#112233"}}).json()
    c.post(f"/api/orgs/{o['id']}/sources", data={"text": "We have two million players across Europe."})
    return o


def research_org(c, oid):
    assert c.post(f"/api/orgs/{oid}/research", json={"approved": False}).status_code == 400  # approval first
    assert c.post(f"/api/orgs/{oid}/research", json={"approved": True}).is_success
    for _ in range(200):
        st = c.get(f"/api/orgs/{oid}").json()["research"]
        if st.get("status") != "running":
            break
        time.sleep(0.05)
    assert st["status"] == "done", st
    return c.get(f"/api/orgs/{oid}").json()


def test_full_story(client):
    c = client
    o = make_org(c)
    org = research_org(c, o["id"])
    by = {f["section"]: f for f in org["findings"]}
    assert by["summary"]["label"] == "research"
    assert by["proof_points"]["label"] == "provided"
    assert by["claims"]["label"] == "unconfirmed"  # quote not in any source
    assert by["brand_voice"]["label"] == "ai"
    assert by["missing"]["label"] == "missing"
    assert org["research"]["notes"] == [] and org["researched_at"]
    for f in org["findings"]:
        if f["section"] != "claims":
            c.patch(f"/api/findings/{f['id']}", json={"status": "approved"})
    c.patch(f"/api/findings/{by['claims']['id']}", json={"status": "rejected"})

    prod = next(p for p in org["products"] if p["name"] == "Lantern Pass")
    assert prod["status"] == "draft" and prod["origin"] == "research"
    assert c.get(f"/api/prefill?org={o['id']}&product={prod['id']}").status_code == 400  # not approved yet
    c.patch(f"/api/products/{prod['id']}", json={"status": "approved", "fields": {"pricing": "First month free"}})

    pre = c.get(f"/api/prefill?org={o['id']}&product={prod['id']}").json()["fields"]
    assert pre["offer"] == {"value": "First month free", "from": "Product · Lantern Pass · pricing or offer"}
    assert pre["tone"]["from"] == "Organization · brand voice"
    camp = c.post("/api/campaigns", json={"org_id": o["id"], "product_id": prod["id"], "name": "Holiday pass", "fields": {
        "objective": "sales", "offer": "First month free", "tone": "festive", "prohibited_claims": "no price claims"}}).json()
    assert camp["field_sources"]["offer"].startswith("Product · Lantern Pass")
    assert camp["field_sources"]["tone"] == "Set for this campaign"
    assert c.get(f"/api/orgs/{o['id']}").json()["fields"]["voice"] == "warm"  # org untouched
    cid = camp["id"]
    base = f"/api/campaigns/{cid}"

    assert c.post(f"{base}/explore").status_code == 400  # no confirmed brief
    v = c.post(f"{base}/brief").json()
    assert v["brief_status"] == "draft" and v["brief"]["missing"] == ["Which countries?"]
    prompt = next(p for p in PROMPTS if "Campaign requirements" in p)
    assert "Northwind makes cosy co-op games" in prompt and "Best studio" not in prompt  # approved only
    assert c.post(f"{base}/explore").status_code == 400  # still a draft
    v = c.post(f"{base}/brief/confirm", json={"brief": {"main_message": "Play together tonight"},
                                              "answers": "UK and Ireland"}).json()
    assert v["brief_status"] == "confirmed" and v["people"] > 0
    con = agency.engine_con(hub.A, cid)
    eng = db.get(con, "campaign")
    assert eng["ad_type"] == "direct" and "no price claims" in eng["constraints"]["restricted_claims"]
    assert eng["brief"]["offering"] == "first month free" and eng["brief"]["client_answers"] == "UK and Ireland"

    assert c.post(f"{base}/explore?rounds=1").is_success
    wait(c, base)
    cs = c.get(f"{base}/concepts").json()
    assert cs["concepts"] and "not real customers" in cs["limits"]
    first = cs["concepts"][0]
    assert first["score"]["confidence"] in ("Low", "Moderate") and first["review"]["summary"] == "Liked by most"
    assert first["approach"]["message"] in ("Tension and curiosity", "Human story")
    aid = first["id"]

    rv = c.post(f"{base}/concepts/{aid}/revise", json={"feedback": "make it about the sofa"}).json()
    assert rv["revised_from"] == aid and rv["content"]["headline"] == "Sofa squad, assemble"
    other = next((x["id"] for x in cs["concepts"][1:]), None) or rv["id"]
    cb = c.post(f"{base}/concepts/combine", json={"parts": {"headline": aid, "visual": other if other != aid else rv["id"]}})
    assert cb.is_success and cb.json()["combined_from"]
    assert c.post(f"{base}/concepts/combine", json={"parts": {"headline": aid}}).status_code == 400

    assert c.post(f"{base}/concepts/{aid}/reel").status_code == 400  # approve first
    c.post(f"{base}/concepts/{aid}/decision", json={"status": "approved", "feedback": "love it"})
    c.post(f"{base}/concepts/{rv['id']}/decision", json={"status": "saved"})
    assert c.get(base).json()["stage"] == "Ready to launch"
    pack = c.get(f"{base}/launch").json()
    assert [i["id"] for i in pack["items"]] == [aid] and "purchases" in pack["measure"]["metrics"]
    sheet = c.get(f"{base}/launch.csv").text
    assert aid in sheet and len(sheet.splitlines()) == 2

    c.post(f"{base}/published", json={"published": True})
    assert c.get(base).json()["stage"] == "Waiting for results"
    assert c.post(f"{base}/results/rows", json={"rows": [{"ad_id": aid, "clicks": "-3"}]}).status_code == 400
    assert c.post(f"{base}/results/rows", json={"rows": [{"ad_id": aid, "platform": "instagram",
                                                          "impressions": "1000", "clicks": "40"}]}).is_success
    real = c.get(f"{base}/reality").json()
    assert real["tested"] == 1 and real["rank_agreement"] is None
    assert any("audience" in u for u in real["uncertain"])
    nxt = c.post(f"{base}/next").json()
    assert nxt["next"]["keep_same"] == ["offer"] and nxt["not_proven"] == ["z"]
    assert c.get(base).json()["stage"] == "Next experiment ready"

    home = c.get("/api/home").json()
    assert home["orgs"][0]["name"] == "Northwind Games" and home["done"][0]["id"] == cid
    assert all(c.get(u).status_code in (200, 404) for u in ("/", "/app", "/console"))
    assert c.get(f"{base}/engine").json()["agents"]  # advanced console still sees the engine


def test_labels_come_from_where_the_quote_is():
    own = {"id": "s1", "origin": "provided", "text": "We serve 40 schools in Pune."}
    pub = {"id": "s2", "origin": "research", "text": "The company serves 40 schools in Pune, says the paper."}
    assert agency.label_for("proof_points", "serve 40 schools in Pune", [own, pub], 12)[0] == "provided"
    assert agency.label_for("proof_points", "serves 40 schools in Pune", [pub], 12)[0] == "research"
    assert agency.label_for("proof_points", "serves 400 schools", [pub], 12)[0] == "unconfirmed"
    assert agency.label_for("proof_points", "Pune", [pub], 12)[0] == "unconfirmed"  # too short to confirm
    assert agency.label_for("brand_personality", "serves 40 schools in Pune", [pub], 12)[0] == "ai"


def test_products_merge_and_campaigns_need_approved_products(client):
    c = client
    o = make_org(c)
    a = c.post(f"/api/orgs/{o['id']}/products", json={"name": "Pass", "fields": {"pricing": "£5"}}).json()
    b = c.post(f"/api/orgs/{o['id']}/products", json={"name": "Pass Ultimate", "fields": {"features": "cloud"}}).json()
    assert a["status"] == "approved"  # typed in by the user
    m = c.post(f"/api/products/{a['id']}/merge", json={"other": b["id"]}).json()
    assert m["fields"] == {"pricing": "£5", "features": "cloud"}
    assert all(p["id"] != b["id"] for p in c.get(f"/api/orgs/{o['id']}").json()["products"] if p["status"] != "merged")
    draft = agency.create_product(hub.A, o["id"], "Found thing", origin="research")
    r = c.post("/api/campaigns", json={"org_id": o["id"], "product_id": draft["id"], "name": "x"})
    assert r.status_code == 400
    c.patch(f"/api/products/{a['id']}", json={"status": "archived"})
    assert c.get(f"/api/products/{a['id']}").json()["status"] == "archived"


def test_campaigns_are_isolated_and_lessons_stay_inside_the_org(client):
    a = hub.A
    o1, o2 = agency.create_org(a, "One"), agency.create_org(a, "Two")
    c1 = agency.create_campaign(a, o1["id"], "first")
    e1 = agency.engine_con(a, c1["id"])
    e1.execute("INSERT INTO memory (term, kind, text) VALUES (1, 'flop', 'loud discount ad flopped')")
    e1.commit()
    c2 = agency.create_campaign(a, o1["id"], "second")
    c3 = agency.create_campaign(a, o2["id"], "other client")
    texts = lambda cid: [r[0] for r in agency.engine_con(a, cid).execute("SELECT text FROM memory")]  # noqa: E731
    assert texts(c2["id"]) == ["loud discount ad flopped"] and texts(c3["id"]) == []
    from engine import memory
    g1, g3 = memory.groups(agency.engine_con(a, c1["id"])), memory.groups(agency.engine_con(a, c3["id"]))
    assert g1 != g3 and g1[0].endswith(o1["id"]) and g1[0] != g1[1]
    assert c1["db_file"] != c2["db_file"]


def test_migration_moves_old_data_once_without_touching_the_engine_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    Path("data/org.json").write_text(json.dumps({"materials": [{"name": "brochure", "kind": "note", "text": "hi"}],
                                                 "draft": {"objective": "sales"}}))
    old = db.connect(tmp_path / "data" / "engine.db")
    db.put(old, "campaign", {"goal": "100 orders", "market": "students", "ad_type": "direct",
                             "brief": {"offering": "cakes"}})
    old.close()
    before = (tmp_path / "data" / "engine.db").read_bytes()
    a = agency.connect(tmp_path / "data" / "agency.db")
    moved = agency.migrate(a, engine_file=tmp_path / "data" / "engine.db")
    assert moved and agency.migrate(a) is None  # once
    camp = agency.campaign(a, moved["campaign"])
    assert camp["name"] == "cakes" and camp["brief_status"] == "confirmed"
    assert agency.sources(a, moved["org"])[0]["text"] == "hi"
    agency.close_all()
    assert (tmp_path / "data" / "engine.db").read_bytes() == before


def test_concepts_fold_near_duplicates_and_groups_are_deterministic():
    ad = lambda i, h, style="tension/bold", s=0.5: {"id": i, "style": style, "sim_score": s, "real_score": None,  # noqa: E731
                                                     "content": {"headline": h, "main_idea": h}}
    ads = [ad("a", "midnight cake delivery for hungry students", s=0.9),
           ad("b", "midnight cake delivery for hungry students tonight", s=0.8),
           ad("c", "grandma's recipe baked fresh every morning", "storytelling/candid", 0.7)]
    g = concepts.distinct(ads, {})
    assert [x["lead"]["id"] for x in g] == ["a", "c"] and [v["id"] for v in g[0]["variations"]] == ["b"]
    g = concepts.distinct(ads, {"b": "approved", "c": "rejected"})
    assert g[0]["lead"]["id"] == "b" and g[-1]["lead"]["id"] == "c"  # decisions lead; rejected go last

    people = [{"name": f"p{i}", "age": 20 + i * 5, "facets": {"O1": 95, "O2": 90, "C1": 50, "N1": 50}}
              for i in range(6)]
    assert concepts.groups_for(people) == concepts.groups_for(people)
    assert concepts.groups_for(people)["p0"] == ["Ages 18–24", "Curious, novelty-seeking"]
    reactions = [{"persona": f"p{i}", "reaction": "share" if i < 2 else "dislike"} for i in range(6)]
    br = concepts.audience_breakdown({"reactions": reactions}, people)
    assert br["positive"] and br["negative"] and br["disagreement"]["liked"] == br["positive"][0]["group"]
    hits = concepts.confidential_hits({"body": "our margin target is forty two percent next year honestly"},
                                      ["Internal: our margin target is forty two percent next year."])
    assert hits


def test_reality_reports_wrong_predictions(tmp_path):
    con = db.connect(tmp_path / "r.db")
    for i, (sim, real) in enumerate([(0.9, -1.0), (0.5, 0.2), (0.2, 1.1)]):
        con.execute("INSERT INTO ads (id, style, content, sim_score, real_score) VALUES (?,?,?,?,?)",
                    (f"a{i}", ["tension/bold", "storytelling/candid", "storytelling/bold"][i],
                     json.dumps({"headline": f"h{i}", "platform": "instagram"}), sim, real))
    con.commit()
    r = reality.compare(con)
    assert r["tested"] == 3 and r["rank_agreement"] == -1.0 and not r["top_match"]
    assert r["best_concept"] == "h2" and "h0" in r["wrong"]
    assert r["best_message"]["name"] == "Human story"
    assert reality.spearman([1, 2, 3], [1, 2, 3]) == 1.0


def test_research_refuses_private_addresses():
    with pytest.raises(ValueError):
        research._public("http://127.0.0.1:8000/")
    assert research.plan({"name": "X", "fields": {"website": "x.com", "competitors": "a.com, b.org\nnot a url"}}) \
        ["competitors"] == ["https://a.com", "https://b.org"]


def test_app_never_shows_engine_jargon():
    """The client-facing app talks marketing, not castes, queens, breeding or genomes."""
    if not SITE_APP.exists():
        pytest.skip("app not built yet")
    bad = re.compile(r"\b(caste|castes|queen|queens|breed|breeding|bred|genome|genomes)\b", re.I)
    for f in SITE_APP.rglob("*.js*"):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            assert not bad.search(line), f"{f.name}:{n}: {line.strip()[:80]}"


def test_concurrent_first_requests_bind_each_campaign_to_its_own_file(client, tmp_path):
    """After a restart, parallel first requests once bound a campaign to the default engine file."""
    from concurrent.futures import ThreadPoolExecutor
    o = agency.create_org(hub.A, "Org")
    cids = [agency.create_campaign(hub.A, o["id"], f"c{i}")["id"] for i in range(4)]
    hub.init(tmp_path / "agency.db")  # like a restart: no cached connections
    urls = [f"/api/campaigns/{c}{s}" for c in cids for s in ("", "/launch", "/reality", "/engine")] * 5
    with ThreadPoolExecutor(16) as ex:
        codes = list(ex.map(lambda u: client.get(u).status_code, urls))
    assert set(codes) == {200}
    for cid in cids:
        path = agency.engine_con(hub.A, cid).execute("PRAGMA database_list").fetchone()[2]
        assert path.endswith(f"{cid}.db")
