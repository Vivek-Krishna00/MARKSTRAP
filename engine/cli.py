"""CLI over the same engine. python -m engine.cli <command>"""
import argparse
import csv
import json

from . import db, evolve


def main():
    p = argparse.ArgumentParser(prog="engine")
    s = p.add_subparsers(dest="cmd", required=True)
    c = s.add_parser("new-campaign")
    c.add_argument("goal")
    c.add_argument("market")
    c.add_argument("--type", choices=["direct", "brand"], default="direct")
    g = s.add_parser("run-generation")
    g.add_argument("-n", type=int, default=1)
    s.add_parser("import-results").add_argument("csv")
    s.add_parser("show-lineage").add_argument("agent_id")
    s.add_parser("show-team").add_argument("ad_id")
    s.add_parser("top-ads").add_argument("--type", choices=["direct", "brand"])
    s.add_parser("revive").add_argument("agent_id")
    d = s.add_parser("set")
    d.add_argument("dial")
    d.add_argument("value", type=float)
    s.add_parser("show-dials")
    s.add_parser("snapshot")
    s.add_parser("rollback").add_argument("snapshot_id")
    s.add_parser("check-ai").add_argument("--image", action="store_true", help="also render one test image")
    e = s.add_parser("reel-eval", help="proof: render bad / placeholder / real-photo variants, judge each blind")
    e.add_argument("--repeats", type=int, default=3)
    sc = s.add_parser("reel-screen", help="screen rendered Reels (+ a fixed twin each) in the MiroFish feed")
    sc.add_argument("reels", nargs="*", help="reel ids (default: latest per concept)")
    r = s.add_parser("reel-demo", help="render the demo reel fixture end to end (no paid providers)")
    r.add_argument("--final", action="store_true", help="also export the 1080x1920 MP4")
    a = p.parse_args()
    con = db.connect()

    if a.cmd == "check-ai":
        import os
        import time
        from . import llm, render
        t = time.time()
        out = llm.chat_json("You are a test.", 'Return {"ok": true, "model": "<your name>"}', temperature=0)
        print(f"brain   OK  {os.getenv('LLM_MODEL')}  {time.time() - t:.1f}s  {out}")
        if a.image:
            t = time.time()
            path = render.render("check-ai", {"platform": "instagram", "visual": "A study lamp on a wooden desk, warm light"}, {}, {})
            print(f"images  OK  {os.getenv('IMAGE_MODEL')}  {time.time() - t:.1f}s  saved {path}")
        return
    if a.cmd == "reel-eval":
        from . import reel_eval
        reel_eval.run(con, a.repeats)
        return
    if a.cmd == "reel-screen":
        from . import reel_screen
        reel_screen.screen(con, a.reels or None)
        print("report: docs/reel-screening.md")
        return
    if a.cmd == "reel-demo":
        from . import reel
        d = json.loads(reel.DEMO.read_text())
        rid = reel.create(con, d["ad"]["id"], reel.prefill(d["ad"], d["campaign"]))
        logo = reel.ROOT.parent.parent / "web" / "mark.png"
        if logo.exists():
            reel.add_asset(con, rid, "logo", "logo.png", logo.read_bytes())
        reel.set_spec(con, rid, d["spec"])
        for step in [reel.produce] + ([reel.export] if a.final else []):
            reel.claim(rid)
            step(con, rid)
        v = reel.view(con, rid)
        print(f"{rid}  critic {v['critic']['overall']}/10  providers {v['providers']}")
        for k in ("preview", "final"):
            if k in v["renders"]:
                print(f"  {k}: {reel.folder(rid) / v['renders'][k]}")
        return
    if a.cmd == "new-campaign":
        db.DB_PATH.unlink(missing_ok=True)
        con = db.connect()
        evolve.seed_campaign(con, a.goal, a.market, a.type)
        print("seeded", con.execute("SELECT COUNT(*) FROM agents").fetchone()[0], "agents")
    elif a.cmd == "run-generation":
        for _ in range(a.n):
            print("term", evolve.run_generation(con), "done")
    elif a.cmd == "import-results":
        with open(a.csv) as f:
            evolve.import_results(con, list(csv.DictReader(f)))
    elif a.cmd == "show-lineage":
        print(json.dumps(evolve.lineage(con, a.agent_id), indent=2))
    elif a.cmd == "show-team":
        print(json.dumps(db.row(con.execute("SELECT * FROM ads WHERE id=?", (a.ad_id,)).fetchone())["team"], indent=2))
    elif a.cmd == "top-ads":
        q = "SELECT * FROM ads" + (" WHERE ad_type=?" if a.type else "") + \
            " ORDER BY COALESCE(real_score, sim_score) DESC LIMIT 10"
        for r in con.execute(q, (a.type,) if a.type else ()):
            r = db.row(r)
            print(f"{r['id']}  t{r['term']}  sim={r['sim_score']:.2f}  real={r['real_score']}  {r['content'].get('headline')}")
    elif a.cmd == "revive":
        evolve.revive(con, a.agent_id)
    elif a.cmd == "set":
        evolve.set_dial(con, a.dial, int(a.value) if a.value.is_integer() else a.value)
        print("applies from next term")
    elif a.cmd == "show-dials":
        print(json.dumps({"active": evolve.dials(con), "pending": db.get(con, "pending", {})}, indent=2))
    elif a.cmd == "snapshot":
        print(db.snapshot())
    elif a.cmd == "rollback":
        db.rollback(a.snapshot_id)


if __name__ == "__main__":
    main()
