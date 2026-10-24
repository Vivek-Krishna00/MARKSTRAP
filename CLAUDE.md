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
- `site/` (React + Vite, reveals in `site/src/motion.jsx`, no animation library) — the MarkStrap website, built by `make site` into `web/site/`, served at `/`
- `web/app.html` (at `/app`) — the user flow: materials → goal & limits → brief → explore → approve → launch → results & next
- `engine/reel.py` + `engine/reel_providers.py` + `engine/compose.py` — Reel Director: approved concept → validated
  storyboard → assets/voice/captions → critic + per-scene repair → MoviePy MP4 (`#reel/<id>` in `/app`,
  `make reel-demo`); open source only, so no Remotion. Docs `docs/reel-director.md`
- `engine/brief.py` — materials ingestion (text/links/PDF), brief extraction, next-experiment proposal
- `engine/api.py` + `web/console.html` (at `/console`) — engine console; `engine/cli.py` — same ops from the terminal
- `config.yaml` — breeds, castes, dials, per-platform signal weights

## Rules
- Code exploration: use codebase-memory-mcp first (`search_graph`, `trace_path`); run `make index` after big changes.
- Keep the design invariants listed in `.claude/skills/evolve-campaign/SKILL.md`; tests enforce them.
- Every new number is a dial in `config.yaml`, not a constant.
