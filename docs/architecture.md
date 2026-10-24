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
OASIS Twitter feed**: each ad is posted by its own brand account, the 12 people act for `oasis_rounds` rounds and
see whatever the TwHIN-BERT recommender shows them. Their actions are read back from the OASIS sqlite as one
reaction per person who was shown the ad (repost/quote → share, like/comment/follow → engage, dislike/mute →
dislike, seen only → ignore), so `sim_score`, boredom, shortlist and demotion are unchanged.
The runner and profile writer are MiroFish's own code (`audience/NOTICE`); Zep is not used, and MiroFish's
LLM-written MBTI personas are replaced by `engine/personality.py`. Personas and memories are built in
`engine/audience.py` and only reach the audience process, never makers. Without the flag, the batched judge is used.
Measured: first run downloads TwHIN-BERT (~0.5 GB, once); then ~30 s startup + ~10 s per round for 4 people.

## Cut for the hackathon (from the design notes' MVP brief)
- OASIS feed for the interact phase (makers copying each other) → still one mentor LLM call per term. OASIS is used for the audience only.
- Graphiti is opt-in (`MEMORY_BACKEND=graphiti`): it needs an embeddings endpoint.
- No image rendering; visuals are evolved as descriptions (the design defers rendering to survivors anyway).
- Later per design: Loka, relegation, team economy, executives, classifier judge (D69–D71), fine-tuning.
