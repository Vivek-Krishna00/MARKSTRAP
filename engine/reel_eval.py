"""Does the Reel judge tell a bad Reel from a good one? Same storyboard, three renders, each judged blind.

broken       grey low-contrast palette, the same shouty text on every scene, hard cuts, a generic hook
placeholder  the demo as shipped: motion graphics only, no real imagery
real         the demo with real CC photos from Openverse in scenes 1-5

Pass = broken < placeholder < real, on the vision model's own mean score and on the final (model + measured) score.
Writes docs/reel-eval.md and the frames each judge saw (docs/reel-eval/<variant>.jpg). Run: make reel-eval
"""
import copy
import io
import json
import os
import statistics
import time
from pathlib import Path

from PIL import Image

from . import reel
from . import reel_providers as P

DOCS = Path(__file__).resolve().parent.parent / "docs"
PHOTOS = {"scene-01": "student studying at night desk lamp", "scene-02": "closed shop shutter night",
          "scene-03": "chocolate cake slice", "scene-04": "bakery cakes display", "scene-05": "cake box"}


def variants(spec: dict) -> dict:
    broken = copy.deepcopy(spec)
    for s in broken["scenes"]:
        s.update(onScreenText="BEST CAKE EVER!!! BUY NOW LIMITED OFFER!!!", transitionOut="cut",
                 assetType="motion_graphics", referenceAssetIds=[])
    broken["scenes"][0]["voiceover"] = "Hello everyone, welcome to our video."
    broken["captionStyle"]["colors"] = ["#8A8A8A", "#939393"]
    real = copy.deepcopy(spec)
    for s in real["scenes"]:
        if s["id"] in PHOTOS:
            s.update(assetType="stock_video", subject=PHOTOS[s["id"]])
    return {"broken": (broken, {"colors": ["#6E6E6E", "#7A7A7A", "#858585"]}, False),
            "placeholder": (spec, {}, False), "real": (real, {}, True)}


def sheet(frames: list[dict], path: Path):
    tiles = [Image.open(io.BytesIO(f["jpg"])).convert("RGB").resize((135, 240)) for f in frames]
    im = Image.new("RGB", (135 * len(tiles), 240))
    for i, t in enumerate(tiles):
        im.paste(t, (135 * i, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=80)


def render_variant(con, name, spec, brief_over, stock):
    d = json.loads(reel.DEMO.read_text())
    rid = reel.create(con, f"eval-{name}", {**reel.prefill(d["ad"], d["campaign"]), **brief_over})
    logo = DOCS.parent / "web" / "mark.png"
    reel.add_asset(con, rid, "logo", "logo.png", logo.read_bytes())
    old = os.environ.get("REEL_STOCK_PROVIDER")
    os.environ["REEL_STOCK_PROVIDER"] = "openverse" if stock else "none"
    try:
        spec = reel.set_spec(con, rid, spec)
        al = reel.assets(con, rid)
        reel.stage_assets(con, rid, spec, al)
        reel.stage_voice(con, rid, spec)
        reel.stage_captions(con, rid, spec)
    finally:
        os.environ.pop("REEL_STOCK_PROVIDER") if old is None else os.environ.__setitem__("REEL_STOCK_PROVIDER", old)
    out = reel.folder(rid) / "preview.mp4"
    brief = reel.load(con, rid)["brief"]
    reel.compose(reel.timeline(spec, brief, reel.scene_state(con, rid), al, True, rid), out)
    return spec, brief, out, reel.scene_state(con, rid)


def run(con, repeats: int = 3):
    if not P.available()["vision"]:
        raise SystemExit("set VISION_PROVIDER=vertex (or VISION_BASE_URL) first: this test needs a vision model")
    base = json.loads(reel.DEMO.read_text())["spec"]
    rows = {}
    for name, (spec, brief_over, stock) in variants(base).items():
        spec, brief, mp4, st = render_variant(con, name, spec, brief_over, stock)
        frames = reel.keyframes(mp4, spec)
        sheet(frames, DOCS / "reel-eval" / f"{name}.jpg")
        measured, stats = reel.visual_checks(frames, spec, st)
        js = [reel.judge_frames(frames, spec, brief, temperature=0.7) for _ in range(repeats)]
        model = [statistics.mean(j["scores"].values()) for j in js if j["scores"]]
        vq = 8.0 - sum(3 if i["severity"] == "major" else 1 for i in measured)
        final = [statistics.mean(min(v, vq) if k == "visual_quality" else v for k, v in j["scores"].items())
                 for j in js if j["scores"]]
        rows[name] = {"model": model, "final": final, "stop": [j["stopScroll"] for j in js], "stats": stats,
                      "verdict": js[0]["verdict"], "measured": [i["problem"] for i in measured], "mp4": str(mp4),
                      "attributions": [(s.get("asset") or {}).get("attribution") for s in st.values()
                                       if (s.get("asset") or {}).get("attribution")]}
        print(f"{name:12s} model {statistics.mean(model):.2f}  final {statistics.mean(final):.2f}  "
              f"stop {statistics.mean(rows[name]['stop']):.1f}  {stats}  {mp4}")
    m = {k: statistics.mean(v["model"]) for k, v in rows.items()}
    f = {k: statistics.mean(v["final"]) for k, v in rows.items()}
    ok_model = m["broken"] < m["placeholder"] < m["real"]
    ok_final = f["broken"] < f["placeholder"] < f["real"]
    write_report(rows, repeats, ok_model, ok_final)
    print(f"\nmodel ranks broken < placeholder < real: {'PASS' if ok_model else 'FAIL'}")
    print(f"final ranks broken < placeholder < real: {'PASS' if ok_final else 'FAIL'}")
    print(f"report: {DOCS / 'reel-eval.md'}")


def write_report(rows, repeats, ok_model, ok_final):
    sd = lambda v: statistics.stdev(v) if len(v) > 1 else 0.0  # noqa: E731
    lines = [
        "# Reel judge: does it tell bad from good?", "",
        f"Run {time.strftime('%Y-%m-%d %H:%M')} · vision model `{os.getenv('VISION_MODEL', 'meta/llama-4-maverick-17b-128e-instruct-maas')}`"
        f" · {repeats} blind judgements per variant (temperature 0.7) · `make reel-eval` · source `engine/reel_eval.py`", "",
        "Same storyboard rendered three ways. The judge sees only the frames and the script, never the variant name.", "",
        "| Variant | Vision model mean (0–10) | Final with measured checks | Stop-scroll | Scene variety | Real imagery |",
        "|---|---|---|---|---|---|"]
    for k, r in rows.items():
        lines.append(f"| {k} | {statistics.mean(r['model']):.2f} ± {sd(r['model']):.2f} | "
                     f"{statistics.mean(r['final']):.2f} ± {sd(r['final']):.2f} | {statistics.mean(r['stop']):.1f} | "
                     f"{r['stats']['variety']:.2f} | {r['stats']['real_imagery']:.0%} |")
    lines += ["", f"**Vision model alone ranks broken < placeholder < real: {'PASS' if ok_model else 'FAIL'}**  ",
              f"**Final score ranks broken < placeholder < real: {'PASS' if ok_final else 'FAIL'}**", ""]
    for k, r in rows.items():
        lines += [f"## {k}", "", f"![{k} frames](reel-eval/{k}.jpg)", "", f"> {r['verdict']}", ""]
        if r["measured"]:
            lines += [f"Measured: {'; '.join(r['measured'])}", ""]
        if r["attributions"]:
            lines += ["Photos (Openverse, CC): " + "; ".join(r["attributions"]), ""]
    (DOCS / "reel-eval.md").write_text("\n".join(lines) + "\n")
