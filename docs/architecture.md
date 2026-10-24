# Architecture — MarkStrap Campaign Engine (MVP)

The simulation filters, reality judges. Everything else serves that loop.

```
               ┌──────────────────────── one term ────────────────────────┐
 campaign ──►  │ 1 INTERACT (nurture)   best ad per caste ─► mentor LLM ─► lesson │
 goal, market, │ 2 PRODUCE & JUDGE      teams (1 agent/breed) ─► ad JSON          │
 ad_type       │   (genomes frozen)     ad + recalled memory ─► audience LLM      │
               │                        ─► reactions + per-part reasons ─► score  │
               │                        boredom: same style seen recently ↓       │
               │                        shortlist if score ≥ bar + penalty×demotions│
               │ 3 REPRODUCE (queens)   per caste: elite kept, gate → eligible     │
               │                        queens pick parents ─► keeper | explorer   │
               │                        child inherits genome + caste lessons      │
               │                        no offspring 3 terms ─► archive (revivable)│
               └──────────────────────────────────────────────────────────────────┘
                     │ shortlist.csv                          ▲
                     ▼                                        │ real_score overrides sim,
               human posts on real platforms ─► results.csv ──┘ shared by team; flop/win
                                                                 written to audience memory
```

## Components

| Part | File | Open-source tech |
|---|---|---|
| LLM for every agent | `engine/llm.py` | any open model behind an OpenAI-compatible API (Qwen, Llama via vLLM/Ollama) |
| Evolution loop | `engine/evolve.py` | Python stdlib |
| Store (agents, ads, lineage, dial log) | `engine/db.py` | SQLite |
| Audience personality | `engine/personality.py`, `engine/personas.py` | 30-facet IPIP-NEO-120 copula (n=271,547) from developmental-agent-simulator; genes + nonshared environment + maturation, lazy closed form |
| Audience feed (optional) | `audience/` (own Python 3.11 venv), `engine/audience.py` | MiroFish's OASIS runner (AGPL-3.0, copied), OASIS / camel-oasis (Apache-2.0); `AUDIENCE_BACKEND=oasis` |
| Audience memory | `engine/memory.py` | Graphiti + FalkorDB (or SQLite fallback) |
| API + dashboard | `engine/api.py`, `web/index.html` | FastAPI, vanilla JS |
| Config / dials | `config.yaml` | YAML |

## Nature · nurture · breeders
- **Nature** — `agents.genome` (prompt, strategy, lessons), fixed breed + caste, `parents`, `child_kind`.
- **Nurture** — phase 1 lessons stored per caste in `meta.lessons`; land in children at birth, never mid-life.
- **Breeders** — `queens` table, rules `top` / `untried` / `wild`; rated on children's fitness, culled after
  `queen_poor_terms` below-median terms and replaced.

## Audience personas (from developmental-agent-simulator)
- Personality is **sampled, not invented**: correlated facet percentiles from a copula fitted on 271,547 IPIP-NEO-120
  respondents, turned into behavioural sentences (extreme deciles first). The LLM only adds name + media habits.
- Facets over Big Five domains: their 27B pilot got the expected action 21/24 with facet language vs 8/24 with domains.
  No activation steering needed.
- Judge prompt carries "tendencies, not obligations" (situational variability research: no caricatures).
- Not taken: memory decay, mood, hormones, sleep, household, lifespan; attention model (household-shaped, uncalibrated).

## Audience feed (MiroFish without Zep)
With `AUDIENCE_BACKEND=oasis`, phase 2 makes all of a term's ads first, then judges them together in **one shared
OASIS Twitter feed**: each ad is posted by its own brand account; the campaign's `population` (100) people browse
for `oasis_rounds` (6) rounds, of whom population/15 .. population/5 act per round (MiroFish's sizing rule), and see
what the TwHIN-BERT recommender shows them. Actions come back from the OASIS sqlite as one reaction per person who
was shown the ad (repost/quote → share, like/comment/follow → engage, dislike/mute → dislike, seen → ignore), so
`sim_score`, boredom, shortlist and demotion are unchanged. Without the flag, the batched judge samples
`audience_size` (12) of the population per ad.

**Text only, never rendered.** Makers write `seen`: what a scroller perceives, in order (video second by second with
on-screen text and audio, image framing and overlay text, carousel slides). Both judges see only caption + `seen`
(`audience.ad_text`), never the maker's notes or the personas' raw facets. Images are rendered once, after approval.

**Memory (MiroFish's Zep role, on Graphiti).** After each feed, every person's actions become English sentences
(`audience/activity.py`, ported from MiroFish's memory updater) packed into ≤9,500-char episodes and stored by
`memory.remember_feed` in group `audience-sim`; next term each person's persona includes `memory.recall_person`.
Real wins/flops live in group `audience` and are the only thing `memory.recall` returns: simulated history never
teaches the audience what works. SQLite is always written; Graphiti (FalkorDB or Neo4j, local or hosted) is an
index over it and falls back to SQLite if unreachable.
Measured: ~30 s startup; 15 people, 2–5 active, 2 rounds ≈ 50 s per term with Gemini.

## Cut for the hackathon (from the design notes' MVP brief)
- OASIS feed for the interact phase (makers copying each other) → still one mentor LLM call per term. OASIS is used for the audience only.
- Graphiti is opt-in (`MEMORY_BACKEND=graphiti`): it needs an embeddings endpoint.
- No image rendering; visuals are evolved as descriptions (the design defers rendering to survivors anyway).
- Later per design: Loka, relegation, team economy, executives, classifier judge (D69–D71), fine-tuning.
