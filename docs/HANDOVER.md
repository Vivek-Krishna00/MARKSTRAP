# MarkStrap — Handover (2026-10-24)

Read this first, then `CLAUDE.md` and `docs/architecture.md`. Nothing is committed to git yet (repo has no commits).

## What this is
Hackathon project (6-hour build, open-source tools/models must be used **inside** the product).
- **MarkStrap** = the product: an AI marketing agency. User hands over materials → objective + constraints →
  extracted brief → explore concepts → approve → launch pack → import real results → next experiment.
- **Campaign Engine** = the evolutionary engine underneath (design doc "Campaign Engine — Design Notes",
  PDF at `~/Downloads/Evolutionary Ad Swarm — Design Notes.pdf`; Decision Log D1–D71 not in the PDF).
  Breeds/castes of maker agents, queens breed children (keeper/explorer), lessons passed at birth (nurture),
  simulated audience only demotes, reality judges. Built on ideas from MiroFish (voice transcription says
  "my office" = MiroFish), OASIS, Graphiti + FalkorDB.
- Team: user (Vivek), teammate Kanishk (design doc + `github.com/KanishkRanjan/developmental-agent-simulator`).

## What is built (all working, `make test` = 29 passing)
| Area | Files | Notes |
|---|---|---|
| Evolution loop | `engine/evolve.py` | seed, interact (lessons), produce & judge (parallel), queens reproduce, age-out to archive, demotion ratchet, boredom, import real results (per-platform ratios, z vs campaign baseline), revive, lineage |
| Audience personality | `engine/personality.py`, `engine/personas.py`, `engine/data/profile_population_v1_model.json` | 30-facet copula (n=271,547) from Kanishk's repo; z = √h2·G + E(age) + M(age) + deltas, lazy closed form, sha256-seeded, no archetypes/MBTI. Age sampled first; LLM only names people + habits. Spec `docs/research/personality_spec.md`, ledger + `docs/PARAMETERS.md`. Twin test recovers h2 0.385 vs 0.40 |
| Audience feed | `audience/` (Python 3.11 venv, `make audience-setup`), `engine/audience.py` | `AUDIENCE_BACKEND=oasis`: MiroFish's own OASIS runner (AGPL, copied, `audience/NOTICE`), no Zep; all ads of a term in one Twitter feed; population 100, population/15..population/5 act per round, 6 rounds (MiroFish sizing); ads judged from text only (`seen` viewer-eye script); OASIS actions → share/engage/ignore/dislike. Live-tested with Gemini: works; free tier (15 req/min) runs out during breeding — use Vertex |
| Memory | `engine/memory.py` | Real results (group `audience`) + simulated feed history per person (group `audience-sim`, MiroFish's Zep role). SQLite always; Graphiti on FalkorDB or Neo4j (`GRAPH_DB`, local or hosted) when `MEMORY_BACKEND=graphiti`, auto-fallback to SQLite. **Pending: user's GCP graph DB endpoint + embeddings model** |
| LLM client | `engine/llm.py` | `chat_json`; `LLM_PROVIDER=vertex` uses Google service-account token (auto-refresh) else base URL + key; 60s timeout, 3 retries; strips `<think>` |
| Agency layer | `engine/brief.py` | materials (text/URL/PDF; images listed by name), brief extraction, next-experiment proposal |
| Images | `engine/render.py` | renders **approved** concepts only; providers `vertex` / `gemini` / `openai` (e.g. local FLUX) |
| API | `engine/api.py` | `/` site, `/app` user app, `/console` engine console, `/api/*`, `/renders/{id}.png` |
| CLI | `engine/cli.py` | new-campaign, run-generation, import-results, show-lineage, set/show-dials, snapshot/rollback, `check-ai --image` |
| User app | `web/app.html` | plain website (user rejected anything slide-like): top nav, step bar with progress line, sticky side panel (ASCII orb, guide, learned), objective cards, drop zone, concept cards, image slots, **dark + light theme** (toggle, `localStorage ms-theme`) |
| Engine console | `web/console.html` | breeds/queens/dials/lineage view for judges |
| Website | `site/` (React + Vite + React Bits BlurText/AnimatedContent/CountUp) → `make site` builds into `web/site/` | normal scrolling marketing site: ASCII hands hero, evidence (verified stats), 36-variation cost, how it works, before/after, architecture, closing; light/dark toggle shared with app |
| Infra | `Makefile`, `Dockerfile`, `docker-compose.yml` (engine + FalkorDB, mounts `secrets/`), `.mcp.json` (codebase-memory-mcp), `.claude/settings.json` (plugins), `.claude/skills/evolve-campaign/` | |

Verified stats used on the site (sources in site footer): Adobe 2025 — 71% expect content demand ≥5x by 2027;
56% biggest social challenge = knowing what resonates. Nielsen 2025 AMR — 54% tightening budgets; 32% measure
cross-channel comprehensively.

## Current AI setup — IN PROGRESS
Target: **Google Cloud Vertex AI** (user has ₹28.8k free-trial credit), one service account for both:
- Brain: `deepseek-ai/deepseek-v4.1-flash-maas` (open-weight → fits open-source rule)
- Images: `gemini-2.5-flash-image` (Nano Banana) on Vertex — proprietary placeholder; swap to a hosted open-weight model (`IMAGE_PROVIDER=openai`, e.g. FLUX) before presenting

`.env` is already set (`LLM_PROVIDER=vertex`, `GCP_LOCATION=global`, `GOOGLE_APPLICATION_CREDENTIALS=secrets/gcp-sa.json`).
**User still must:** fill `GCP_PROJECT_ID`, enable Vertex AI API, enable DeepSeek model in Model Garden,
create service account (role Vertex AI User) → JSON key → `secrets/gcp-sa.json`. Then run `make ai-check`
and restart `make dev`. If ai-check fails: model not enabled / trial blocks partner models / image model name differs.

History of attempts: Command Code key = valid but "Go plan doesn't include API access" (403). Gemini AI Studio key
(`AQ.` key, kept in `.env` as fallback via OpenAI-compat URL) works for text (`gemini-3.5-flash-lite`, real run:
26 calls/generation, 0 failures, ~81s) but free tier has **0 image quota**; `gemini-flash-latest` returned 503.
Before the presentation: keep the brain on an open model; images either Vertex (proprietary) or FLUX on GPU PC.

## Cost (measured call counts, estimated tokens)
3-round exploration ≈ 80 calls ≈ 110k input + 44k output tokens; +2 rounds ≈ +52 calls. Judge calls dominate
(reduce `audience_size` / `ads_per_term`). Ad spend + asset production are the real costs (human posts in MVP).

## How to run / verify
`make setup` · `make dev` (http://localhost:8000; restart after `.env` changes) · `make test` · `make site` after
editing `site/` · `make ai-check`. Demo with a fake LLM: scratchpad `demo_server.py` pattern (patch `engine.llm.chat_json`).
Screenshots: headless Chrome `--screenshot` with a kill timeout (it hangs on endless canvas animations; use
`--force-prefers-reduced-motion`). Claude-in-Chrome extension was not connected.

## Not built / deferred (per design "Later")
OASIS for the interact phase (makers; audience uses OASIS now), Phase-2 spec (employment, executives, Loka, currencies, classifier), Loka/relegation, team economy, executives, classifier judge
(D69–D71), fine-tuning, video/reels (user chose images only), guardrails/legal labelling, auto-posting.

## User preferences learned
- Wants a **normal website**, not presentation-style (no scene counters, snap scrolling, speaker notes, fullscreen chrome).
- Wants character in the UI (rejected "plain"), with light + dark mode.
- Mixes Hindi/English; prefers fast action over long question rounds; hackathon time pressure.
- Visual direction: near-black #080A0E, off-white #F0F1ED, ice blue #91D0FF; Manrope / Georgia italic / IBM Plex Mono; ASCII + dither art.

## Open flags
- `audience/` is AGPL-3.0 (copied MiroFish code). Fine for an open-source hackathon; keep `LICENSE` + `NOTICE`.
- Personality [U] defaults need the owner: `disinhibition_weights`, maturation sizes, env curve, `audience.age_range`.
- With the OASIS feed an ad nobody was shown scores neutral (0.33) and passes `send_bar` 0.3 (sim only demotes).
- React Bits license is MIT + Commons Clause (source-available, not OSI) — swap for CSS if judges are strict.
- `profile_population_v1_model.json` came from Kanishk's repo (no license stated) — confirm with him.
- Docker image build untested. Homepage scrolling / theme toggle / wheel behaviour only checked via screenshots.
- No git commits yet; user hasn't asked to commit.
