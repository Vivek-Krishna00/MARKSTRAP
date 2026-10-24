# MarkStrap — Campaign Engine

Evolutionary campaign engine (hackathon MVP). **Start with `docs/HANDOVER.md`** (current state, pending setup, user preferences). Source of truth for design: "Campaign Engine — Design Notes"
(Decision Log D1–D71). Architecture: `docs/architecture.md`.

Note: voice transcription renders "MiroFish" as "my office" — always read it as MiroFish.

## Hackathon constraint
Only open-source tools and models may be used **inside the product**: open model via an OpenAI-compatible
endpoint, Graphiti + FalkorDB, FastAPI, SQLite. No proprietary APIs in `engine/`.

## Commands
- `make site` (rebuild the website after editing `site/`) · `make setup` · `make reel-setup` · `make reel-demo` · `make dev` (http://localhost:8000) · `make test` · `make gen N=3` · `make up` (Docker)
- CLI: `.venv/bin/python -m engine.cli --help`

## Layout
- `engine/evolve.py` — the whole loop: seed, interact (nurture), produce & judge, queens reproduce, age-out, import real results
- `engine/personality.py` — audience personality: 30 facets from genes + environment + maturation on the fitted copula (`engine/data/`), lazy, never LLM-invented; spec `docs/research/personality_spec.md`
- `engine/personas.py` — samples people (age first) through personality.py; LLM only adds name + habits
- `audience/` + `engine/audience.py` — MiroFish's OASIS feed as the audience (`AUDIENCE_BACKEND=oasis`, `make audience-setup`); copied AGPL code, no Zep
- `engine/memory.py` — audience memory (SQLite default, Graphiti when `MEMORY_BACKEND=graphiti`)
- `engine/llm.py` — single `chat_json` call; tests monkeypatch it
- `site/` (React + Vite) — two pages built by `make site` into `web/site/`: the website (`index.html` + `src/`, at `/`,
  reveals in `src/motion.jsx`) and the agency app (`app.html` + `src/app/`, at `/app`, hash routes, no router library)
- App flow: Organization → knowledge → research (with approval) → profile review → products → campaign (pre-filled,
  sources shown) → brief → concepts (simulated) → review/compare/revise/combine → assets + Reel → launch pack →
  real results → simulation vs reality → one next experiment. No castes/queens/breeding wording in `src/app`
  (a test checks); user-facing copy lives in `site/src/app/copy.js`
- `engine/agency.py` — orgs, knowledge sources, labelled findings, products, campaigns (`AGENCY_DB`, default
  `data/agency.db`); **each campaign has its own engine DB** `data/campaign-data/<id>.db`; lessons travel only
  within one org; one-time migration of the old `data/org.json` + `data/engine.db`
- `engine/research.py` — website + competitors + Wikipedia, only after approval; labels set in Python from where the
  evidence quote is (provided / research / AI / unconfirmed / missing)
- `engine/concepts.py` — distinct concepts, audience groups from sampled facets, score reasons, review, revise, combine
- `engine/reality.py` — simulation vs reality, computed; `engine/brief.py` — brief v2, next experiment (one change)
- `engine/reel.py` + `engine/reel_providers.py` + `engine/compose.py` — Reel Director: approved concept → validated
  storyboard → assets/voice/captions → critic + per-scene repair → MoviePy MP4 (`#/campaigns/<id>/reels/<rid>` in
  `/app`, `make reel-demo`); open source only, so no Remotion. Docs `docs/reel-director.md`
- `engine/api.py` (thin) + `engine/routes/{agency,campaign}.py` + `engine/hub.py` (shared connections, run lock,
  campaign stage). Campaign routes live under `/api/campaigns/{cid}/…`
- `web/console.html` (at `/console?campaign=<id>`) — engine console for one campaign (makers, lineage, dials);
  `engine/cli.py` — engine ops from the terminal on one engine file (`DB_PATH`)
- `config.yaml` — breeds, castes, dials, per-platform signal weights

## Rules
- Code exploration: use codebase-memory-mcp first (`search_graph`, `trace_path`); run `make index` after big changes.
- Keep the design invariants listed in `.claude/skills/evolve-campaign/SKILL.md`; tests enforce them.
- Every new number is a dial in `config.yaml`, not a constant.
