# MarkStrap — Handover (2026-10-25)

Read this first, then `CLAUDE.md` and `docs/architecture.md`. Repo: github.com/Vivek-Krishna00/MARKSTRAP, branch
`main` (commits go straight to main). `make test` = 29 passing.

## What this is
Hackathon project; every tool and model inside the product is open source / open weight.
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
| Images | `engine/render.py` | **approved** concepts only; open-weight model behind an OpenAI-compatible images endpoint (`IMAGE_BASE_URL`, e.g. FLUX.1-schnell via LocalAI). **Parked** by the user: no host yet (free trial has 0 GPU quota; CPU SD-Turbo or upgrade for an L4 are the options) |
| API / UI | `engine/api.py`, `web/app.html`, `web/console.html`, `site/` | `/` site, `/app`, `/console`, `/favicon.png`; site via `make site`; site depends on React only (reveals are CSS + IntersectionObserver in `site/src/motion.jsx`) |
| Brand mark | `site/mark.py` → `web/mark.png`, `web/favicon.png` | Thomas attractor (b=0.133, x0=(1.1,1.1,-0.01), dt=0.05, RK4, 800k steps, yaw 45, pitch -34) density-rendered in viridis; used as favicon + nav symbol |

## Cloud setup (done 2026-10-25, project `project-1fba041d-5a2a-46ea-a94` "My First Project")
- **Brain**: DeepSeek V4.1 Flash (open weights) on Vertex AI MaaS, `LLM_PROVIDER=vertex`. Auth = gcloud **Application
  Default Credentials** on this Mac (service-account key creation is blocked by org policy
  `iam.disableServiceAccountKeyCreation`; an unused SA `markstrap-engine` with Vertex AI User exists). `check-ai` OK.
- **Memory VM** `markstrap-mem` (e2-standard-4, asia-south1-a, ~$0.15/h): Docker with FalkorDB (password in
  `secrets/falkordb-password`, gitignored) and Ollama serving `nomic-embed-text`. Firewall rule `markstrap-mem-allow`
  admits tcp 6379/11434 **only from the user's IP** (49.206.122.42 at setup; update the rule if it changes).
  Host, password and embedding URL are in `.env`. Stop it when idle:
  `gcloud compute instances stop markstrap-mem --zone asia-south1-a` (start = same with `start`).
- **Budget alert** "MarkStrap hackathon": ₹16,500 (~$200), emails at 25/50/90 %, credits excluded.
- `.env` now: `MEMORY_BACKEND=graphiti`, `AUDIENCE_BACKEND=oasis`. Experiments: set `MEMORY_NAMESPACE=test-`
  (FalkorDB stores each memory group as its own graph) and a scratch `DB_PATH`.
- End-to-end run on this stack: 100 people seeded in 101 s; one generation (6 ads, 100-person feed, 6 rounds,
  Graphiti writes) 440 s; scores spread 0.33–0.77; viewer-eye `seen` scripts read well.

## Pending
1. Images (parked by the user): choose a host for an open-weight model, then set `IMAGE_BASE_URL`.
2. Owner decisions: unseen ad scores neutral 0.33 and passes `send_bar` 0.3 (sim only demotes) — keep or hold back?
   Personality [U] defaults (`disinhibition_weights`, maturation sizes, env curve, `audience.age_range` 18–45).
3. Watch: in the first e2e generation all 6 teams drew the `tension` copy caste (1-in-924 by chance;
   `assemble_teams` looks correct) — check again on the next run.

## Dev environment facts
- Main venv `.venv` (Python 3.13). `uv` was installed **inside `.venv`**; it fetched Python 3.11.17 into
  `~/.local/share/uv`. Sidecar venv `audience/.venv` (camel-oasis 0.2.5, camel-ai 0.2.78, torch) via
  `make audience-setup` (re-runnable). **`mcp==1.24.0` is pinned** (mcp 2.x breaks camel's FastMCP import).
- TwHIN-BERT recommender (~0.5 GB) is cached in `~/.cache/huggingface` after the first OASIS run.
- Docker is installed locally; the graph DB runs on the GCP VM instead (`make falkordb` would start a local one).
- Live runs: `set -a; . ./.env; set +a` then run with a scratch `DB_PATH` and `MEMORY_NAMESPACE=test-`.
  `tests/conftest.py` strips MEMORY/AUDIENCE/LLM_PROVIDER so `make test` never touches live services.
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
- No Zep (hosted service); Graphiti + a self-hosted FalkorDB replaces it. No fine-tuning: learning stays in prompts.
- Copy MiroFish's code rather than reinvent; only improve personality. OASIS runs as a separate process.
- MiroFish sizing: 100 people, population/15..population/5 active, 6 rounds.
- Everything inside the product is open source / open weight (user, 2026-10-25). Gemini, React Bits and GSAP were removed.
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
- Kanishk's repo (copula data) has no licence — confirm with him.
- Docker image build untested (now also builds the OASIS venv; heavy because of torch).
