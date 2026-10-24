"""Personality: 30 IPIP-NEO facets, generated from origins and aged lazily, in closed form.

z(age) = sqrt(h2)*G + E(age) + M(age) + sum(deltas up to age) + O_context        (spec: docs/research/personality_spec.md)

Reused, not rebuilt (github.com/KanishkRanjan/developmental-agent-simulator):
- facet correlation = the fitted copula's latent_correlation (n=271,547), the same matrix personas.py samples from;
- sha256 (seed, id, purpose) draws from devsim/temperament.py, so a draw never depends on evaluation order;
- parent-mean + segregation inheritance (temperament.inherited) and piecewise-linear curves (development.curve_value).
Every number lives in config.yaml `personality:` with its evidence tag; see docs/PARAMETERS.md. No LLM, no archetypes.
"""
import json
import logging
import math
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from statistics import NormalDist

import numpy as np
import yaml

_HERE = Path(__file__).resolve().parent
MODEL = json.loads((_HERE / "data" / "profile_population_v1_model.json").read_text())
CFG = yaml.safe_load((_HERE.parent / "config.yaml").read_text())["personality"]
FACETS = MODEL["facets"]                                   # N1..N6, E1..E6, O1..O6, A1..A6, C1..C6
DOMAINS = {d: [i for i, f in enumerate(FACETS) if f[0] == d] for d in "NEOAC"}
_L = np.linalg.cholesky(np.array(MODEL["latent_correlation"]))
_CDF = NormalDist().cdf
PURPOSES = ("pers_genetic", "pers_env_baseline", "pers_env_innovation", "pers_origin_context")
log = logging.getLogger(__name__)


def _draw(identity, key, purpose: str) -> np.ndarray:
    """Correlated standard-normal facet vector, a pure function of (seed, identity, key, purpose)."""
    assert purpose in PURPOSES
    h = sha256(f"{CFG['seed']}:{identity}:{key}:{purpose}".encode()).digest()
    return _L @ np.random.default_rng(int.from_bytes(h[:8], "big")).standard_normal(len(FACETS))


def curve_value(points, x):
    """Piecewise-linear, flat outside the table (devsim/development.py)."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def env_var(age: float) -> float:
    """Cumulative nonshared-environment variance; equals 1-h2 at ref_age, so total variance is 1 there."""
    c = CFG["env_variance_curve"]
    return (1 - CFG["h2"]) * curve_value(c, age) / curve_value(c, CFG["ref_age"])


@dataclass
class PersonalityState:
    """Stored state only: no domain or metatrait values. The cache is a speed-up, never needed for correctness."""
    agent_id: str
    G: np.ndarray
    context: np.ndarray
    family: str | None = None
    deltas: list = field(default_factory=list)
    cache: dict = field(default_factory=dict, compare=False, repr=False)


def founder_genes(agent_id) -> np.ndarray:
    return _draw(agent_id, "G", "pers_genetic")


def inherit_genes(parent_genes: list, child_id) -> np.ndarray:
    """Parent mean + Mendelian segregation keeps unit variance (devsim temperament.inherited); siblings correlate 0.5."""
    if not parent_genes:
        return founder_genes(child_id)
    return 0.5 * sum(parent_genes) + math.sqrt(1 - len(parent_genes) / 4) * _draw(child_id, "seg", "pers_genetic")


def create_personality(agent_id, genesis_age: float = 0, context: dict | None = None,
                       genes: np.ndarray | None = None, family: str | None = None) -> PersonalityState:
    """Genesis at any age: stores G and context offsets only; nothing is simulated until a read."""
    offsets = np.zeros(len(FACETS))
    for kind, key in (context or {}).items():  # optional additive tables, default empty (P3, P9: no evidence)
        for facet, v in CFG["origin_offsets"].get(kind, {}).get(key, {}).items():
            offsets[FACETS.index(facet)] += v
    return PersonalityState(str(agent_id), founder_genes(agent_id) if genes is None else np.asarray(genes),
                            offsets, family)


def _environment(state: PersonalityState, age: float) -> np.ndarray:
    """Sum of per-year innovations keyed (agent, year): order-independent; the prefix sum is cached."""
    full = int(math.floor(age))
    y0, acc = state.cache.get("E", (-1, np.zeros(len(FACETS))))
    if y0 > full:
        y0, acc = -1, np.zeros(len(FACETS))
    for k in range(y0 + 1, full + 1):
        acc = acc + math.sqrt(max(env_var(k) - (env_var(k - 1) if k else 0), 0)) * \
            _draw(state.agent_id, k, "pers_env_innovation")
    state.cache["E"] = (full, acc)
    frac = max(env_var(age) - env_var(full), 0)  # part of the current year; zero at a whole age, so no draw
    part = math.sqrt(frac) * _draw(state.agent_id, full + 1, "pers_env_innovation") if frac else 0.0
    shared = 0.0
    if CFG["shared_env_var"] and state.family:
        shared = math.sqrt(CFG["shared_env_var"]) * _draw(state.family, "C", "pers_env_baseline")
    return acc + part + shared


def _maturation(age: float) -> np.ndarray:
    m = np.zeros(len(FACETS))
    for d, points in CFG["maturation"].items():  # one shared table for everyone (P4, direction only)
        m[DOMAINS[d]] = curve_value(points, age)
    return m


def _delta_sum(state: PersonalityState, age: float) -> np.ndarray:
    out = np.zeros(len(FACETS))
    hl = CFG["delta_reversion_halflife"]
    for rec_age, idx, d, _ in state.deltas:
        if rec_age <= age:
            out[idx] += d * (0.5 ** ((age - rec_age) / hl) if hl else 1.0)
    return out


def personality_at(state: PersonalityState, age: float) -> np.ndarray:
    """30 standardized facet z values. Pure and deterministic; skipping years equals stepping through them."""
    return (math.sqrt(CFG["h2"]) * state.G + _environment(state, age) + _maturation(age)
            + _delta_sum(state, age) + state.context)


def apply_trait_delta(state: PersonalityState, age: float, target: str, delta: float, source_tag: str):
    """Entry point for other modules (life events are not generated here). Small, clamped, logged (P6, P7)."""
    idx = DOMAINS[target] if target in DOMAINS else [FACETS.index(target)]
    d = max(-CFG["delta_clamp"], min(CFG["delta_clamp"], delta)) * curve_value(CFG["delta_age_window"], age)
    state.deltas.append((age, idx, d, source_tag))
    log.info("trait delta %s %s age=%s %+.3f (asked %+.3f) source=%s", state.agent_id, target, age, d, delta, source_tag)


def domains(z: np.ndarray) -> dict:
    return {d: float(np.mean(z[i])) for d, i in DOMAINS.items()}


def metatraits(z: np.ndarray) -> dict:
    dm = domains(z)
    w = CFG["disinhibition_weights"]
    return {"stability": (-dm["N"] + dm["A"] + dm["C"]) / 3,
            "plasticity": (dm["E"] + dm["O"]) / 2,
            "disinhibition": float(sum(v * z[FACETS.index(f)] for f, v in w.items()) / sum(abs(v) for v in w.values()))}


def to_percentiles(z: np.ndarray) -> dict:
    """Facet -> population percentile (0-100) through the fitted raw-score marginals, keeping their real skew."""
    out = {}
    for f, zi, counts in zip(FACETS, z, MODEL["marginal_counts"]):
        cum = np.cumsum(counts)
        i = min(int(np.searchsorted(cum / cum[-1], _CDF(max(-3.0, min(3.0, float(zi)))), side="right")), 16)
        out[f] = round(float(100 * (cum[i] - counts[i] / 2) / cum[-1]), 1)  # mid-rank percentile of the raw score
    return out
