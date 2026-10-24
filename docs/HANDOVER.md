# MarkStrap — Handover (2026-10-25, after the agency workflow)

Read this first, then `CLAUDE.md`, `docs/architecture.md` and `docs/reel-director.md`.
Repo: github.com/Vivek-Krishna00/MARKSTRAP (**public**), branch `main` (commits go straight to main).
`make test` = 48 passing (23 engine/personality + 15 Reel Director + 10 agency workflow).

## What this is
Hackathon project; every tool and model inside the product is open source / open weight (hard rule).
- **MarkStrap** = an AI marketing agency. App at `/app` (React, `site/src/app/`): Organization → knowledge →
  research (with approval) → labelled profile review → products → campaign (pre-filled, sources shown) → brief →
  concepts (simulated) → review/compare/revise/combine → assets + **Reel** → launch pack → real results →
  simulation vs reality → one next experiment. Home shows what needs attention.
- **Campaign Engine** underneath (design doc "Campaign Engine — Design Notes", PDF in `~/Downloads/`; Decision Log
  D1–D71 not in the PDF): breeds/castes of maker agents, queens breed keeper/explorer children, lessons inherited at
  birth, simulated audience **only demotes**, **reality judges**.
- Voice transcription says "my office" = **MiroFish**.
- Team: user (Vivek), teammate Kanishk (design doc + `github.com/KanishkRanjan/developmental-agent-simulator`).

## Fresh clone → running (not in git: `.env`, `secrets/`, `data/`)
1. `make setup` (venv, deps incl. MoviePy/Pillow/bundled ffmpeg; copies `.env.example` → `.env`).
2. `make reel-setup` — Kokoro-82M voices (~350 MB, default) + Piper fallback into `data/voices/`. Skip it and Reels
   render with a silent voice track.
3. Brain: fill `.env` (`LLM_PROVIDER=vertex` + `GCP_PROJECT_ID`, needs `gcloud auth application-default login`), or
   any OpenAI-compatible open model via `LLM_BASE_URL`. No brain: set `REEL_TEXT_PROVIDER=mock` for Reels.
4. Optional: `make audience-setup` (MiroFish/OASIS audience), FalkorDB password into `secrets/falkordb-password`.
5. `make dev` → http://localhost:8000. No-API smoke test: `make reel-demo FINAL=1`.

## What is built
| Area | Files | Notes |
|---|---|---|
| Evolution loop | `engine/evolve.py` | seed, interact (mentor lessons), produce & judge (parallel), queens reproduce, age-out to archive, demotion ratchet, boredom, import real results (per-platform ratios, z vs campaign baseline), revive, lineage |
| Personality | `engine/personality.py`, `engine/personas.py`, `engine/data/profile_population_v1_model.json` | 30 IPIP-NEO facets on the copula fitted to 271,547 people (Kanishk's data). z = √h2·G + E(age) + M(age) + deltas + context; lazy closed form, sha256-seeded per (id, purpose), no archetypes/MBTI/LLM. Age sampled first; LLM only adds name + habits. Spec `docs/research/personality_spec.md`, ledger `docs/research/personality_ledger.md`, `docs/PARAMETERS.md` |
| Audience (default) | `evolve.judge` | one batched LLM call per ad, `audience_size` 12; sees only caption + `seen` |
| Audience (MiroFish) | `audience/` (own Python 3.11 venv), `engine/audience.py` | `AUDIENCE_BACKEND=oasis`; MiroFish's OASIS runner copied (AGPL-3.0, `audience/NOTICE`); one shared Twitter feed per term; 100 people, population/15..population/5 active, 6 rounds |
| Text-only ads | `evolve.make_ad`, `audience.ad_text` | makers write `seen` = what a scroller perceives; nothing rendered for the simulation |
| Memory | `engine/memory.py` | `audience` = real wins/flops; `audience-sim` = feed history. SQLite always; Graphiti on FalkorDB/Neo4j when `MEMORY_BACKEND=graphiti`, SQLite fallback |
| LLM client | `engine/llm.py` | `chat_json`; `LLM_PROVIDER=vertex` → ADC token, else base URL + key |
| Agency layer | `engine/brief.py` | materials (text/URL/PDF), brief extraction, next-experiment proposal |
| Images | `engine/render.py` | approved concepts only; open-weight model behind `IMAGE_BASE_URL`. **Parked**: no host yet |
| **Reel Director** | `engine/reel.py`, `engine/reel_providers.py`, `engine/compose.py`, `site/src/app/pages/Reel.jsx` | see below |
| Agency layer | `engine/agency.py`, `engine/research.py`, `engine/concepts.py`, `engine/reality.py`, `engine/brief.py` | see "Agency workflow" below |
| API / UI | `engine/api.py`, `engine/routes/`, `engine/hub.py`, `site/` (website + `src/app/`), `web/console.html` | `/` site, `/app`, `/console?campaign=<id>`; both pages via `make site` (build output is committed) |
| Brand mark | `site/mark.py` → `web/mark.png`, `web/favicon.png` | Thomas attractor density-rendered in viridis |

## Agency workflow (built 2026-10-25, second session)
- Data: `data/agency.db` (orgs, sources, findings, products, campaigns). **One engine DB per campaign**:
  `data/campaign-data/<id>.db`; `evolve.py` runs unchanged inside it. Lessons (win/flop) copied only between
  campaigns of the same org; Graphiti groups per org. First start migrates `data/org.json` + `data/engine.db` into
  "My organization" (engine file referenced in place, not modified).
- Research runs only after "Research with my approval" (lists what it reads): own site (≤ `research.max_pages`),
  competitor home pages, Wikipedia (needs a UA with a contact URL). Labels set in Python from the evidence quote.
  Only approved findings and approved products reach prefill and the brief.
- Concepts: `make_ad` now also returns concept_name, main_idea, emotion, why_it_may_work, risks. `concepts.distinct`
  folds near-duplicates (idea words, not captions); audience groups from facets; reviews cached per concept version
  (written at the end of exploration); revise/combine judged on 12 simulated people, no maker credit.
- Assets: Reel needs an approved concept; brief has voice/captions on-off, voice style, music direction; capability
  notes shown before production; **final approval** required before it counts in the launch pack.
- Launch: user publishes and marks it; never auto-posts. Results by form (objective's metrics first, incl.
  impressions for direct objectives) or CSV. `reality.compare` + next experiment (one change, keep_same, not_proven).
- `db.Locked` wraps every shared SQLite connection (agency + engine): a race between parallel first requests after
  a restart once bound a campaign to the default engine file. Regression test included.
- Verified in Chrome with a stand-in model (no cloud credentials on that machine): Microsoft → Xbox Game Pass full
  story incl. real xbox.com/Wikipedia research, Reel export + approval, results, comparison, next experiment;
  light/dark; 390 px width (all pages except the campaign form and brief, which a browser extension blocked from
  being measured in a frame).

## Reel Director (built 2026-10-25)
- Flow: approved concept → **Create Reel** → brief pre-filled (`reel.prefill`: concept + campaign brief + constraints;
  hex colours in brand rules = palette) → references with roles (product/character/location/style/logo/music/font/
  reference Reel) + "must stay the same" notes → **storyboard** (`reel.direct`: open model, pydantic `ReelSpec`,
  1 re-ask with the validation error, else `template_spec`) → user edits scenes → **produce** (assets → voice →
  captions → critic → repair weak scenes only → preview) → **export** 1080×1920 → download.
- Prompts are assembled in Python (`scene_prompt`) from structured fields + the continuity profile, so subject,
  camera, lighting, palette, references, continuity and exclusions are always present.
- Per-scene `status/error/attempts` + hashes of what the visual and voice were made from; runs skip unchanged
  scenes; paid generations cached by content in `data/reels/cache/` (no double spend on retry/refresh); restart →
  reel marked `interrupted`, **Resume** continues. Reel work runs in a thread with its **own SQLite connection**
  (sharing the request connection broke under polling).
- Critic: measured rules (voice overrun from real audio length, text length, hook, CTA, failed/stand-in visuals)
  + model scores on 11 criteria (min wins); one repair round, max 3 scenes (`reel.critic_rounds`, `repair_max_scenes`).
- Providers (`REEL_<KIND>_PROVIDER`): text llm|mock · image `IMAGE_BASE_URL` · video none (no open model host) ·
  tts piper|silent · timing proportional|whisper · music upload or procedural · stock none|openverse.
- Composer: MoviePy + ffmpeg (bundled via imageio-ffmpeg), Pillow text layers, Manrope (OFL) in `engine/data/fonts/`.
  **Remotion rejected**: source-available, breaks the open-source rule.
- Measured (M-series Mac): 20 s preview ≈ 5 s, 1080p export ≈ 13 s; storyboard on DeepSeek V4.1 Flash ≈ 16 s;
  live critic repaired 3 scenes (6.5 → 7.5), then the measured pacing fix cut scene-05's voice 3.9 s → 1.5 s.
- **Visual judge** (added after the user found the demo Reel ugly while the blind critic said 8/10): keyframes →
  Llama 4 Maverick on Vertex (`VISION_PROVIDER=vertex`, us-east5, "Llama 4 API Service" — NOT "Deploy model",
  which rents GPUs hourly) with a harsh anchored rubric + measured scene variety / real-imagery share.
  `make reel-eval` proves ranking: broken 3.2 < placeholder 6.6 < real photos 7.3 → `docs/reel-eval.md`.
  Vertex Llama 4 accepts max 5 images per request (frames are tiled). `visual_variety_min` 0.12 sits between
  placeholder (0.10) and real (0.27). Openverse limited to licences allowing modification (captions = derivative).
- **MiroFish screening** (`make reel-screen`, user asked for Llama to weigh high): Llama's description of the real
  frames + a "with fixes" twin go into two separate OASIS feeds (same 100 people) → reach, reactions, quotes;
  score = 70% Llama + 30% crowd. Result: broken 3.4 < placeholder 5.8 < real 6.5, crowd alone agrees. Shown on the
  Reel page when present. `evolve.make_people` was extracted from `seed_campaign` (no behaviour change) for this.
- Fixed a UI race: `reel.view` now reads `busy` before the row (a run ending in between looked idle-but-unfinished).
- **Voice = Kokoro-82M** (Apache-2.0 via kokoro-onnx MIT): voice/speed from language + voice direction, Voice (`brief.speaker`;
  `brief.voice` is Kanishk's on/off switch) and Language pickers in the brief, Hindi voices `hf_alpha`/`hm_omega`. **Motion graphics per scene purpose** (slam,
  typewriter, card, counter+stars, price stamp, pulsing CTA, grain): demo screening 5.8 → 7.3.
- **Images on Vertex: blocked.** FLUX.1-schnell and Qwen-Image exist in Model Garden only as *deploy* (hourly GPU),
  no MaaS; free-trial accounts get no GPU quota. Needs: upgrade account (credit carries over) + L4 quota for
  Vertex serving, then deploy FLUX.1-schnell on L4 (~₹70–100/h while up) with up/down commands.
- Demo fixture: `engine/data/reel_demo.json` (Midnight Crumb cake delivery, 20 s, 6 scenes).
- UI verified with Playwright on system Chrome (Chrome extension was not connected): full flow, light/dark,
  390 px width, no console errors.

## Cloud setup (done 2026-10-25, project `project-1fba041d-5a2a-46ea-a94` "My First Project")
- **Brain**: DeepSeek V4.1 Flash (open weights) on Vertex AI MaaS, `LLM_PROVIDER=vertex`, gcloud ADC on this Mac
  (SA key creation blocked by org policy; unused SA `markstrap-engine` exists).
- **Memory VM** `markstrap-mem` (e2-standard-4, asia-south1-a, ~$0.15/h): FalkorDB (password in
  `secrets/falkordb-password`) + Ollama `nomic-embed-text`. Firewall `markstrap-mem-allow` admits 6379/11434 only
  from the user's IP (49.206.122.42 at setup). Stop when idle:
  `gcloud compute instances stop markstrap-mem --zone asia-south1-a`.
- **Budget alert** "MarkStrap hackathon": ₹16,500 (~$200), emails at 25/50/90 %.
- `.env`: `MEMORY_BACKEND=graphiti`, `AUDIENCE_BACKEND=oasis`. Experiments: `MEMORY_NAMESPACE=test-` + scratch `DB_PATH`.

## Pending
0. **Live run of the new agency flow on Vertex** (DeepSeek) has not been done: the second session's machine had no
   gcloud/ADC. Run the Microsoft → Xbox story once with the real brain and check research extraction quality,
   brief, concept distinctness and reviews. Reel CTA now uses the brief's action sentence (a long URL overflowed).
1. Images: user chose Vertex → waiting on account upgrade + L4 quota (see Reel Director section).
2. Generated video clips: needs a hosted open video model (Wan 2.x / LTX-Video) behind `reel_providers.video`.
3. Before demo: one Reel on Vertex with a real logo + 2–3 product photos; keep `make reel-demo FINAL=1` as fallback.
   Show `docs/reel-eval.md` as evidence the judge separates bad from good.
4. Owner decisions: unseen ad scores neutral 0.33 and passes `send_bar` 0.3 — keep or hold back? Personality [U]
   defaults (`disinhibition_weights`, maturation sizes, env curve, `audience.age_range` 18–45).
5. Watch: first e2e generation drew the `tension` caste for all 6 teams — check again on the next run.
6. Docker image untested (OASIS venv + torch; now also needs `make reel-setup` for the voice).

## Dev environment facts
- Main venv `.venv` (Python 3.13; Homebrew's default is now 3.15, whose Pillow lacks FreeType: build the venv with
  `uv venv -p 3.13 --seed .venv`); `uv` inside `.venv`; sidecar `audience/.venv` (Python 3.11, camel-oasis 0.2.5,
  `mcp==1.24.0` pinned). TwHIN-BERT cached in `~/.cache/huggingface`.
- Live runs: `set -a; . ./.env; set +a`, scratch `AGENCY_DB` + `DB_PATH` + `MEMORY_NAMESPACE=test-`;
  `data/agency.db`, `data/campaign-data/` and `data/engine.db` are the user's data — keep them untouched. `tests/conftest.py` strips live-service env vars.
- `make reel-demo` uses `data/reel-demo.db`; reels and the cache live in `data/reels/`, voices in `data/voices/`.
- Screenshots/UI checks: Playwright with `channel="chrome"` (cached Playwright browsers don't match the pip
  version), or headless Chrome `--headless=new --screenshot`. `timeout` is not installed on this Mac.

## Decisions made (don't re-ask)
- Open source / open weight only inside the product (hard constraint, user 2026-10-25): no Remotion, no Sora,
  no Zep, no Gemini/React Bits/GSAP. Piper (GPL-3.0) is fine.
- Graphiti + self-hosted FalkorDB replaces Zep. No fine-tuning. Copy MiroFish rather than reinvent.
- MiroFish sizing: 100 people, population/15..population/5 active, 6 rounds.
- Reels: MoviePy composer; planning in `reel.py`, drawing only in `compose.py`; timing of scenes is locked during repair.
- Phase-2 engine spec (employment, queen population, Loka, two currencies, …) is **parked, not built**.

## Not built / deferred
Phase-2 spec; OASIS for the makers' interact phase; generated video clips; vision analysis of reference Reels;
guardrails/legal labelling; auto-posting; auth; MiroFish's report agent / graph builder / UI.

## User preferences
- Normal website, never presentation-style; character in the UI; light + dark mode.
- Near-black #080A0E, off-white #F0F1ED, ice blue #91D0FF; Manrope / Georgia italic / IBM Plex Mono; ASCII + dither art.
- Mixes Hindi/English, types fast; prefers action over long question rounds; hackathon time pressure.
- Wants existing open-source projects reused ("don't reinvent the wheel").

## Open flags
- Repo is public: never commit `.env`, `secrets/`, or `data/` (campaign DB, client materials).
- No auth: organization, campaign and Reel endpoints are open to anyone who can reach the server.
- "Confidential" material is never quoted (prompt rule + an 8-word verbatim check in the review), but its text is
  still sent to the configured model for understanding. Fine for a self-hosted open model; say so to clients.
- `audience/` is AGPL-3.0 (copied MiroFish code); keep `audience/LICENSE` + `NOTICE`. Piper is GPL-3.0.
- Kanishk's repo (copula data) has no licence — confirm with him.
