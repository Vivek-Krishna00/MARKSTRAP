# MarkStrap — Handover (2026-10-25)

Read this first, then `CLAUDE.md` and `docs/architecture.md`. Repo: github.com/Vivek-Krishna00/MARKSTRAP, branch
`main` (commits go straight to main; last pushed: `2b899a9`). `make test` = 29 passing.

## What this is
Hackathon project; open-source tools / open-weight models must be used **inside** the product (proprietary is
tolerated for now where noted, e.g. Gemini, to be swapped before presenting).
- **MarkStrap** = an AI marketing agency. User flow at `/app`: materials → goal & limits → brief → explore →
  approve → launch sheet → import real results → next experiment.
- **Campaign Engine** underneath (design doc "Campaign Engine — Design Notes", PDF in `~/Downloads/`; Decision Log
  D1–D71 not in the PDF): breeds/castes of maker agents, queens breed keeper/explorer children, lessons inherited at
  birth, simulated audience **only demotes**, **reality judges**.
- Voice transcription says "my office" = **MiroFish**.
- Team: user (Vivek), teammate Kanishk (design doc + `github.com/KanishkRanjan/developmental-agent-simulator`).

## What is built
| Area | Files | Notes |
|---|---|---|
| Evolution loop | `engine/evolve.py` | seed, interact (mentor lessons), produce & judge (parallel), queens reproduce, age-out to archive, demotion ratchet, boredom, import real results (per-platform ratios, z vs campaign baseline), revive, lineage |
| Personality | `engine/personality.py`, `engine/personas.py`, `engine/data/profile_population_v1_model.json` | 30 IPIP-NEO facets on the copula fitted to 271,547 people (Kanishk's data). z = √h2·G + E(age) + M(age) + deltas + context; lazy closed form, sha256-seeded per (id, purpose), no archetypes/MBTI/LLM. Age sampled first; LLM only adds name + habits (batched, names unique). Spec `docs/research/personality_spec.md` (user's brief, revised: 9 corrections), ledger `docs/research/personality_ledger.md`, `docs/PARAMETERS.md`. Population tests: twin h2 0.385 vs 0.40; rank-order stability ↑ with age; heritable share 0.57→0.37→0.32 |
| Audience (default) | `evolve.judge` | one batched LLM call per ad, `audience_size` 12 sampled from the population; sees only caption + `seen` (no maker notes, no raw facets) |
| Audience (MiroFish) | `audience/` (own Python 3.11 venv), `engine/audience.py` | `AUDIENCE_BACKEND=oasis`. MiroFish's own OASIS runner + action logger copied verbatim, profile writer copied minus Zep/MBTI, `activity.py` ported from its Zep memory updater (AGPL-3.0, see `audience/NOTICE`). `feed.py`: all ads of a term in **one shared Twitter feed**, one brand account per ad; population 100, population/15..population/5 act per round, 6 rounds (MiroFish's sizing). OASIS actions → share/engage/ignore/dislike, so scoring/shortlist/UI unchanged. Twitter only: OASIS's Reddit prompt hard-codes MBTI |
| Text-only ads | `evolve.make_ad`, `audience.ad_text` | makers write `seen` = what a scroller perceives (video second by second, image framing + overlay, carousel slides). Nothing is rendered for the simulation |
| Memory | `engine/memory.py` | group `audience` = real wins/flops (only thing `recall` returns); group `audience-sim` = each person's feed history (`remember_feed` / `recall_person`, MiroFish's Zep role). SQLite always written; Graphiti on FalkorDB or Neo4j (`GRAPH_DB`, local or hosted) when `MEMORY_BACKEND=graphiti`; after one failure falls back to SQLite until restart |
| LLM client | `engine/llm.py` | `chat_json`; `LLM_PROVIDER=vertex` → service-account token, else base URL + key |
| Agency layer | `engine/brief.py` | materials (text/URL/PDF), brief extraction, next-experiment proposal |
| Images | `engine/render.py` | **approved** concepts only; `IMAGE_MODEL=gemini-2.5-flash-image` (Nano Banana) on Vertex for now → swap to hosted open-weight (`IMAGE_PROVIDER=openai`, e.g. FLUX) before presenting |
| API / UI | `engine/api.py`, `web/app.html`, `web/console.html`, `site/` | `/` site, `/app`, `/console`, `/favicon.png`; site via `make site` |
| Brand mark | `site/mark.py` → `web/mark.png`, `web/favicon.png` | Thomas attractor (b=0.133, x0=(1.1,1.1,-0.01), dt=0.05, RK4, 800k steps, yaw 45, pitch -34) density-rendered in viridis; used as favicon + nav symbol |

## Pending — needs the user
1. **Graph DB on GCP**: user will send endpoints. Need: host/port or URI, username/password, **FalkorDB or Neo4j**,
   and which **embeddings model** Graphiti should use. Then set in `.env`: `MEMORY_BACKEND=graphiti`, `GRAPH_DB`,
   `FALKORDB_*` or `NEO4J_*`, `EMBED_BASE_URL` / `EMBED_MODEL` / `EMBED_API_KEY` (see `.env.example`).
   Graphiti has **not** been run against a real graph yet.
2. **Vertex AI setup** (unchanged): `.env` has `LLM_PROVIDER=vertex` but `GCP_PROJECT_ID` is empty and
   `secrets/gcp-sa.json` is missing → fill project ID (project "My First Project"), service account with Vertex AI
   User role, JSON key to `secrets/gcp-sa.json`, enable DeepSeek in Model Garden, `make ai-check`. Brain target:
   `deepseek-ai/deepseek-v4.1-flash-maas`.
3. Owner decisions: unseen ad scores neutral 0.33 and passes `send_bar` 0.3 (sim only demotes) — keep or hold back?
   Personality [U] defaults (`disinhibition_weights`, maturation sizes, env curve, `audience.age_range` 18–45).

## Dev environment facts
- Main venv `.venv` (Python 3.13). `uv` was installed **inside `.venv`**; it fetched Python 3.11.17 into
  `~/.local/share/uv`. Sidecar venv `audience/.venv` (camel-oasis 0.2.5, camel-ai 0.2.78, torch) via
  `make audience-setup` (re-runnable). **`mcp==1.24.0` is pinned** (mcp 2.x breaks camel's FastMCP import).
- TwHIN-BERT recommender (~0.5 GB) is cached in `~/.cache/huggingface` after the first OASIS run.
- Docker is installed; FalkorDB not running locally (`make falkordb` starts it).
- Gemini AI Studio key in `.env` works for text via the OpenAI-compatible URL, but the **free tier is 15 requests/min**:
  a full generation in OASIS mode hits 429 during breeding. For live tests override in the shell, never edit `.env`:
  `set -a; . ./.env; set +a; unset LLM_PROVIDER; export LLM_MODEL=gemini-3.5-flash-lite`.
- Live tests: use a scratch `DB_PATH` so `data/engine.db` (user's campaign) is untouched.
- Screenshots: headless Chrome `--headless=new --screenshot` with a kill after a few seconds; `timeout` is not
  installed on this Mac.

## Measured
- Default judge: 3-round exploration ≈ 80 LLM calls.
- OASIS: ~30 s startup; 4 people/2 rounds ≈ 10 s per round; 15 people, 2–5 active, 2 rounds ≈ 50 s per term.
  Full default (100 people, 6–20 active, 6 rounds) ≈ 36–120 agent calls per term — not yet run end to end (needs Vertex).
- Live results looked right: specific ads beat generic ones, uneven exposure from the recommender, real quotes,
  and people carried memories into the next run.

## Decisions made in this session (don't re-ask)
- No Zep (not open source); Graphiti + a self-hosted graph DB replaces it. No fine-tuning: learning stays in prompts.
- Copy MiroFish's code rather than reinvent; only improve personality. OASIS runs as a separate process.
- MiroFish sizing: 100 people, population/15..population/5 active, 6 rounds.
- Gemini is acceptable for now (brain fallback, images); swap to open-weight before presenting.
- The pasted **Phase-2 engine spec** (employment/resumes, queen population with hybrid breeds and evolvable rules,
  executives/companies/contracts/wages/backward pay, lower world + Loka with seasons, two currencies,
  classifier + MiroFish hand-off + risk slice, idle fine-tune) is **parked, not built**. Fine-tuning is dropped.

## Not built / deferred
Phase-2 spec above; OASIS for the makers' interact phase; video rendering (images only); guardrails/legal labelling;
auto-posting; MiroFish's report agent / graph builder / UI.

## User preferences
- Normal website, never presentation-style; character in the UI; light + dark mode.
- Visual direction: near-black #080A0E, off-white #F0F1ED, ice blue #91D0FF; Manrope / Georgia italic / IBM Plex Mono; ASCII + dither art.
- Mixes Hindi/English, types fast; prefers action over long question rounds; hackathon time pressure.
- Wants existing open-source projects reused ("don't reinvent the wheel").

## Open flags
- `audience/` is AGPL-3.0 (copied MiroFish code); keep `audience/LICENSE` + `NOTICE`.
- React Bits = MIT + Commons Clause (not OSI) — swap for CSS if judges are strict.
- Kanishk's repo (copula data) has no licence — confirm with him.
- Docker image build untested (now also builds the OASIS venv; heavy because of torch).
- Graphiti's Vertex token is taken once per process (expires after ~1 h).
