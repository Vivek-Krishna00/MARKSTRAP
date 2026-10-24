import copy
import io
import json
import time

import pytest
from PIL import Image

from engine import db, reel, render
from engine import reel_providers as P

DEMO = json.loads(reel.DEMO.read_text())


def png(color=(200, 120, 80), size=(60, 100)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Offline providers that count calls: image endpoint on, silent voice, no text model."""
    calls = {"image": 0}

    def fake_image(prompt, aspect):
        calls["image"] += 1
        return png((calls["image"] * 40 % 255, 90, 90))
    monkeypatch.setattr(P, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(reel, "ROOT", tmp_path / "reels")
    monkeypatch.setattr(render, "_openai", fake_image)
    monkeypatch.setattr(P, "available", lambda: {"text": "mock", "image": "openai", "video": None, "tts": "silent",
                                                 "timing": "proportional", "music": "procedural", "stock": None})
    monkeypatch.setattr(reel, "compose", lambda tl, out: out.write_bytes(b"mp4"))  # real render: test_compose
    con = db.connect(tmp_path / "t.db")
    rid = reel.create(con, "ad1", reel.prefill(DEMO["ad"], DEMO["campaign"]))
    return con, rid, calls


def spec_with(**over):
    s = copy.deepcopy(DEMO["spec"])
    s.update(over)
    return s


# ---------- schema ----------

def test_fixture_is_valid_and_bad_timing_is_rejected():
    reel.validate(DEMO["spec"], [])
    gap = spec_with()
    gap["scenes"][1]["startSeconds"] = 3.0
    slow_hook = spec_with()
    slow_hook["scenes"][0]["endSeconds"] = slow_hook["scenes"][1]["startSeconds"] = 4.0
    short = spec_with(durationSeconds=30)
    for bad in (gap, slow_hook, short, spec_with(aspectRatio="16:9")):
        with pytest.raises(ValueError):
            reel.validate(bad, [])
    ref = spec_with()
    ref["scenes"][2]["referenceAssetIds"] = ["asset-nope"]
    with pytest.raises(ValueError, match="unknown reference"):
        reel.validate(ref, ["asset-real"])


def test_template_storyboards_are_valid_at_every_length():
    b = reel.prefill(DEMO["ad"], DEMO["campaign"])
    for d in (6, 9, 15, 20, 30, 60, 90):
        s = reel.validate(reel.template_spec({**b, "durationSeconds": d}, []), [])
        assert s.scenes[0].purpose == "hook" and s.scenes[-1].purpose == "cta"


def test_scene_prompt_is_complete_and_inherits_continuity(env):
    con, rid, _ = env
    a = reel.add_asset(con, rid, "product", "box.png", png(), "pink moon sticker")
    s = spec_with()
    s["scenes"][2]["referenceAssetIds"] = [a["id"]]
    spec = reel.set_spec(con, rid, s)
    p = spec["scenes"][2]["generationPrompt"]
    for part in ("Subject:", "Action:", "Environment:", "Composition:", "Camera:", "Camera movement:", "Lighting:",
                 "Visual style:", "Color palette:", "Emotional tone:", "Duration:", "9:16", "Motion:",
                 "Product placement:", "References:", "Continuity:", "Exclusions:"):
        assert part in p, part
    assert "pink moon sticker" in p and "kraft box" in p  # reference note + continuity profile
    assert all(len(x["voiceover"].split()) <= reel.words_budget(x) for x in spec["scenes"])


# ---------- director ----------

def test_director_reasks_once_then_falls_back_to_template(monkeypatch):
    b = reel.prefill(DEMO["ad"], DEMO["campaign"])
    answers = [{"title": "broken"}, DEMO["spec"]]
    monkeypatch.setattr(P, "text_json", lambda *a, **k: answers.pop(0))
    spec, by = reel.direct(b, [])
    assert by == "llm" and spec["title"] == DEMO["spec"]["title"] and not answers
    monkeypatch.setattr(P, "text_json", lambda *a, **k: {"title": "still broken"})
    spec, by = reel.direct(b, [])
    assert by.startswith("template") and "validation" in by
    reel.validate(spec, [])


# ---------- pipeline ----------

def test_produce_is_idempotent_and_regenerates_one_scene(env):
    con, rid, calls = env
    reel.set_spec(con, rid, DEMO["spec"])
    reel.produce(con, rid)
    v = reel.view(con, rid)
    assert v["status"] == "produced" and v["renders"]["preview"] == "preview.mp4"
    assert calls["image"] == 1  # only scene-03 is generated_image; the rest are motion graphics
    reel.produce(con, rid)  # refresh / retry: nothing paid twice
    assert calls["image"] == 1
    before = {s["id"]: s["state"]["asset"]["path"] for s in reel.view(con, rid)["scenes"]}
    reel.regenerate(con, rid, "scene-03")
    reel.produce(con, rid)
    after = {s["id"]: s["state"]["asset"]["path"] for s in reel.view(con, rid)["scenes"]}
    assert calls["image"] == 2 and after["scene-03"] != before["scene-03"]
    assert {k: v for k, v in after.items() if k != "scene-03"} == {k: v for k, v in before.items() if k != "scene-03"}


def test_failed_scene_is_isolated_and_recoverable(env, monkeypatch):
    con, rid, calls = env
    reel.set_spec(con, rid, DEMO["spec"])

    def boom(*a):
        raise TimeoutError("provider timed out")
    monkeypatch.setattr(render, "_openai", boom)
    reel.produce(con, rid)
    v = reel.view(con, rid)
    st = {s["id"]: s["state"] for s in v["scenes"]}
    assert st["scene-03"]["status"] == "failed" and "timed out" in st["scene-03"]["error"]
    assert all(s["status"] == "done" for k, s in st.items() if k != "scene-03")
    assert v["status"] == "produced"  # the reel still renders, with a motion-graphics stand-in
    assert any(i["sceneId"] == "scene-03" for i in v["critic"]["issues"])
    a = reel.add_asset(con, rid, "product", "shot.png", png())
    reel.replace(con, rid, "scene-03", a["id"])
    reel.produce(con, rid)
    s3 = next(s for s in reel.view(con, rid)["scenes"] if s["id"] == "scene-03")["state"]
    assert s3["status"] == "done" and s3["asset"]["provider"] == "upload"


def test_critic_repairs_only_weak_scenes_within_cap(env, monkeypatch):
    con, rid, _ = env
    s = spec_with()
    s["scenes"][1]["voiceover"] = "short line"
    spec = reel.set_spec(con, rid, s)
    real_tts = P.tts

    def slow_tts(text, wpm):  # scene-02's voice runs long, like a slow real voice would
        return real_tts(text + " ." * 40 if text == "short line" else text, wpm)
    monkeypatch.setattr(P, "tts", slow_tts)
    revised = []
    real_revise = reel.revise_scene
    monkeypatch.setattr(reel, "revise_scene", lambda sp, sid, *a: revised.append(sid) or real_revise(sp, sid, *a))
    reel.produce(con, rid)
    v = reel.view(con, rid)
    assert revised == ["scene-02"]  # one critic round, only the weak scene
    assert v["critic"]["history"][0]["repaired"] == ["scene-02"]
    untouched = [x for x in v["spec"]["scenes"] if x["id"] != "scene-02"]
    assert [x["voiceover"] for x in untouched] == [x["voiceover"] for x in spec["scenes"] if x["id"] != "scene-02"]
    assert set(v["critic"]["scores"]) == set(reel.CRITERIA)


def test_timeline_is_deterministic_and_ducks_under_voice(env):
    con, rid, _ = env
    reel.set_spec(con, rid, DEMO["spec"])
    reel.produce(con, rid)
    r = reel.load(con, rid)
    args = (r["spec"], r["brief"], reel.scene_state(con, rid), reel.assets(con, rid), False, rid)
    tl = reel.timeline(*args)
    assert tl == reel.timeline(*args)
    assert tl["size"] == [1080, 1920] and tl["duration"] == 20
    for sc in r["spec"]["scenes"]:
        ws = [w for w in tl["words"] if sc["startSeconds"] <= w["t0"] < sc["endSeconds"]]
        assert all(w["t1"] <= sc["endSeconds"] + 1e-6 for w in ws)
    assert len(tl["vo"]) == 6 and tl["music"]["duck"] < tl["music"]["volume"]


def test_uploads_are_sanitized_and_checked(env):
    con, rid, _ = env
    a = reel.add_asset(con, rid, "logo", "../../etc/My Logo!.PNG", png())
    assert "/" not in a["name"] and a["name"].endswith(".png") and str(reel.folder(rid)) in a["path"]
    with pytest.raises(ValueError):
        reel.add_asset(con, rid, "logo", "x.exe", b"MZ")
    with pytest.raises(Exception):
        reel.add_asset(con, rid, "product", "fake.png", b"not an image")
    with pytest.raises(ValueError):
        reel.add_asset(con, rid, "boss", "a.png", png())


# ---------- composer (real render, tiny) ----------

def test_compose_renders_a_tiny_reel(tmp_path):
    from engine import compose
    img = tmp_path / "p.png"
    img.write_bytes(png())
    voice = tmp_path / "v.wav"
    P._write_wav(voice, __import__("numpy").zeros(22050), 22050)
    tl = {"size": [180, 320], "fps": 6, "duration": 2.0, "preview": True,
          "safe": {"top": 40, "bottom": 80, "side": 12}, "colors": ["#1A1033", "#FFB84D", "#FF5C8A"],
          "caption": {"position": "bottom", "colors": ["#FFFFFF", "#FFB84D"], "words": 3, "max_chars": 20},
          "font": str(reel.Path(reel.__file__).parent / "data" / "fonts" / "Manrope.ttf"),
          "scenes": [{"id": "a", "start": 0, "end": 1, "purpose": "hook", "kind": "image", "path": str(img),
                      "text": "Hi ★", "transition": "crossfade", "zoom": [1, 1.1], "pan": [0.04, 0.03]},
                     {"id": "b", "start": 1, "end": 2, "purpose": "cta", "kind": "motion", "path": None,
                      "text": "Go", "transition": "cut", "zoom": [1.1, 1], "pan": [-0.04, 0.03]}],
          "words": [{"w": "hello", "t0": 0.1, "t1": 0.5}, {"w": "there.", "t0": 0.5, "t1": 0.9}],
          "vo": [{"path": str(voice), "start": 0.1, "end": 1.1}],
          "music": {"path": None, "volume": 0.3, "duck": 0.1, "ramp": 0.1},
          "sfx": [{"kind": "whoosh", "t": 1.0}], "sfx_volume": 0.5, "transition_s": 0.3,
          "logo": str(img), "cta": "shop.in", "title": "t"}
    out = tmp_path / "o.mp4"
    compose.render(tl, str(out))
    assert out.stat().st_size > 1000


# ---------- API ----------

def test_api_reel_flow(env, monkeypatch, tmp_path):
    _, _, calls = env
    from fastapi.testclient import TestClient
    from engine import agency, api, hub
    hub.init(tmp_path / "agency.db")
    o = agency.create_org(hub.A, "Midnight Crumb")
    cid = agency.create_campaign(hub.A, o["id"], "Cakes")["id"]
    con = agency.engine_con(hub.A, cid)
    db.put(con, "campaign", DEMO["campaign"])
    con.execute("INSERT INTO ads (id, content) VALUES (?,?)", ("ad9", json.dumps(DEMO["ad"]["content"])))
    con.commit()
    c = TestClient(api.app)
    base = f"/api/campaigns/{cid}"
    assert c.post(f"{base}/concepts/missing/reel").status_code == 404
    assert c.post(f"{base}/concepts/ad9/reel").status_code == 400  # approve the concept first
    c.post(f"{base}/concepts/ad9/decision", json={"status": "approved"})
    r = c.post(f"{base}/concepts/ad9/reel").json()
    rid = r["id"]
    assert r["brief"]["platform"] == "instagram_reels" and r["status"] == "draft" and r["capabilities"]["notes"]
    assert c.post(f"{base}/concepts/ad9/reel").json()["id"] == rid  # one Reel per concept
    assert c.patch(f"{base}/reels/{rid}/brief", json={"durationSeconds": 500}).status_code == 400
    assert c.patch(f"{base}/reels/{rid}/brief", json={"voice": "maybe"}).status_code == 400
    assert c.patch(f"{base}/reels/{rid}/brief", json={"durationSeconds": 15, "cta": "Order now"}).json()["brief"]["cta"] == "Order now"
    up = c.post(f"{base}/reels/{rid}/assets", data={"role": "product", "note": "box"},
                files={"file": ("box.png", png(), "image/png")})
    assert up.status_code == 200 and up.json()["assets"][0]["role"] == "product"
    assert c.post(f"{base}/reels/{rid}/assets", files={"file": ("x.exe", b"MZ")}).status_code == 400

    def wait():
        for _ in range(200):
            v = c.get(f"{base}/reels/{rid}").json()
            if not v["busy"]:
                return v
            time.sleep(0.05)
        raise AssertionError("reel stayed busy")
    c.post(f"{base}/reels/{rid}/storyboard")
    v = wait()
    assert v["status"] == "storyboard" and v["spec"]["durationSeconds"] == 15
    sid = v["scenes"][1]["id"]
    assert c.put(f"{base}/reels/{rid}/scenes/{sid}", json={"assetType": "hologram"}).status_code == 400
    ok = c.put(f"{base}/reels/{rid}/scenes/{sid}", json={"onScreenText": "New line"}).json()
    assert ok["scenes"][1]["onScreenText"] == "New line"
    c.post(f"{base}/reels/{rid}/produce")
    assert wait()["status"] == "produced"
    assert c.get(f"/campaigns/{cid}/reels/{rid}/preview.mp4").status_code == 200
    assert c.get(f"/campaigns/{cid}/reels/{rid}/..%2F..%2Fengine.db").status_code == 404
    rep = c.post(f"{base}/reels/{rid}/scenes/{sid}/replace", files={"file": ("new.png", png((1, 2, 3)), "image/png")})
    assert rep.status_code == 200
    v = wait()
    assert next(s for s in v["scenes"] if s["id"] == sid)["state"]["asset"]["provider"] == "upload"
    assert c.post(f"{base}/reels/{rid}/approve", json={"approved": True}).status_code == 400  # export first
    c.post(f"{base}/reels/{rid}/export")
    assert wait()["renders"]["final"] == "final.mp4"
    assert c.post(f"{base}/reels/{rid}/approve", json={"approved": True}).json()["approved"]
    assert c.get(f"{base}/launch").json()["items"][0]["reel"]["approved"]
    assert any(x["id"] == rid for x in c.get(base).json()["reels"])


# ---------- visual review ----------

def jpg(color, noise=False):
    import numpy as np
    a = np.full((640, 360, 3), color, np.uint8)
    if noise:
        a = np.random.default_rng(sum(color)).integers(0, 255, (640, 360, 3), dtype=np.uint8)
    b = io.BytesIO()
    Image.fromarray(a).save(b, "JPEG")
    return b.getvalue()


def test_visual_checks_flag_lookalike_placeholder_scenes():
    spec = reel.validate(DEMO["spec"], []).model_dump()
    same = [{"sceneId": s["id"], "label": "", "t": 0, "jpg": jpg((60, 20, 80))} for s in spec["scenes"]]
    varied = [{"sceneId": s["id"], "label": "", "t": 0, "jpg": jpg((40 * i, 200 - 30 * i, 90), noise=i % 2 == 1)}
              for i, s in enumerate(spec["scenes"])]
    motion = {s["id"]: {"asset": {"kind": "motion"}} for s in spec["scenes"]}
    photos = {s["id"]: {"asset": {"kind": "image"}} for s in spec["scenes"]}
    bad, bs = reel.visual_checks(same, spec, motion)
    good, gs = reel.visual_checks(varied, spec, photos)
    assert bs["variety"] < gs["variety"] and bs["real_imagery"] == 0 and gs["real_imagery"] == 1
    assert len(bad) == 2 and not good


def test_frames_are_tiled_to_the_endpoint_limit_and_judge_is_optional(monkeypatch):
    frames = [{"sceneId": f"s{i}", "label": "", "t": i, "jpg": jpg((i * 30, 0, 0))} for i in range(7)]
    images, per = reel.tile(frames, 5)
    assert per == 2 and len(images) == 4 and Image.open(io.BytesIO(images[0])).width == 720
    spec = reel.validate(DEMO["spec"], []).model_dump()
    monkeypatch.setattr(reel, "keyframes", lambda mp4, sp: frames[:6])
    monkeypatch.setattr(P, "available", lambda: {"vision": None})
    v = reel.visual_review(spec, {}, {}, None)
    assert "not judged" in v["note"] and v["scores"]["visual_quality"] < 8
    monkeypatch.setattr(P, "available", lambda: {"vision": "vertex"})
    monkeypatch.setattr(P, "vision_json", lambda *a: {"scores": {"hook": 3, "visual_quality": 9, "pacing": 1},
                                                      "stopScroll": 2, "verdict": "meh", "issues": []})
    v = reel.visual_review(spec, {}, {}, None)
    assert v["scores"]["hook"] == 3 and "pacing" not in v["scores"]  # judge may only score what frames show
    assert v["scores"]["visual_quality"] < 9  # measured checks cap a generous judge
