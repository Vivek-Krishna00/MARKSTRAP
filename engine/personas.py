"""Audience archetypes grounded in real personality data, not invented by the LLM.

Facet profiles are sampled from a Gaussian copula over the 30 IPIP-NEO-120 facets, fitted on 271,547 adults
(data/profile_population_v1_model.json, from github.com/KanishkRanjan/developmental-agent-simulator).
The model only names the person and their media habits; the facets stay authoritative.

Why facets, not five domain scores: in that repo's 27B pilot, plain-language facet prompts gave the expected
action in 21/24 situations vs 8/24 for domain-only prompts; activation steering was not needed.
"""
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np

MODEL = json.loads((Path(__file__).resolve().parent / "data" / "profile_population_v1_model.json").read_text())

# (higher-score tendency, lower-score tendency) per facet.
BEHAVIORS = {
    'N1': ('anticipate possible problems and seek reassurance under uncertainty', 'remain relatively unworried when outcomes are uncertain'),
    'N2': ('feel irritation more readily when frustrated', 'be slow to anger when frustrated'),
    'N3': ('become discouraged more readily after setbacks', 'maintain their spirits relatively well after setbacks'),
    'N4': ('feel self-conscious when being evaluated', 'feel relatively unselfconscious when being evaluated'),
    'N5': ('find immediate temptations harder to resist', 'find immediate temptations easier to resist'),
    'N6': ('feel overwhelmed more readily under pressure', 'feel relatively capable of coping under pressure'),
    'E1': ('approach others warmly and readily', 'take time to warm up to unfamiliar people'),
    'E2': ('enjoy frequent contact with groups', 'prefer a smaller amount of social contact'),
    'E3': ('speak up and advocate their preferences', 'hold back or defer before voicing their preferences'),
    'E4': ('prefer a busy and energetic pace', 'prefer a slower and more unhurried pace'),
    'E5': ('seek stimulating and exciting experiences', 'prefer quieter and less stimulating experiences'),
    'E6': ('express enthusiasm and positive feelings readily', 'express positive feelings in a more reserved way'),
    'O1': ('explore imaginative possibilities and fantasy', 'focus on concrete, readily observable possibilities'),
    'O2': ('notice and value artistic and aesthetic experiences', 'give artistic and aesthetic experiences less attention'),
    'O3': ('notice and explore their own feelings', 'give their inner emotional experience less attention'),
    'O4': ('try unfamiliar activities and experiences', 'prefer familiar activities and routines'),
    'O5': ('enjoy exploring abstract ideas and complex questions', 'prefer practical questions to extended abstract discussion'),
    'O6': ('question conventions and consider alternative ways of doing things', 'value familiar conventions and established ways of doing things'),
    'A1': ('initially give others the benefit of the doubt', "initially check others' claims and motives cautiously"),
    'A2': ('communicate candidly and straightforwardly', 'be guarded and strategic about what they disclose'),
    'A3': ("notice others' needs and offer assistance", 'prioritize their own demands before offering assistance'),
    'A4': ('seek compromise when preferences conflict', 'stand their ground when preferences conflict'),
    'A5': ('avoid emphasizing their own status and achievements', 'draw attention to their own strengths and achievements'),
    'A6': ("be moved by others' difficulties", "approach others' difficulties in a more detached way"),
    'C1': ('feel confident in their ability to handle tasks', 'doubt their ability until they have concrete reassurance'),
    'C2': ('organize materials and prefer orderly surroundings', 'tolerate disorder and use flexible arrangements'),
    'C3': ('feel a strong obligation to follow through on commitments', 'treat commitments more flexibly when circumstances change'),
    'C4': ('set demanding goals and invest in achievement', 'be satisfied with less demanding achievement goals'),
    'C5': ('persist with tasks despite boredom', 'find it harder to continue once a task becomes tedious'),
    'C6': ('consider consequences before deciding', 'decide quickly without prolonged deliberation'),
}
# Situational-variability guard: personality shapes reactions, it does not script them.
EXPRESSION = ("These are tendencies, not obligations. Let the situation shape their expression; "
              "never turn one disposition into a constant caricature.")


def sample_facets(n: int, seed: int) -> list[dict]:
    """n correlated facet profiles as population percentiles (0-100)."""
    rng = np.random.default_rng(seed)
    z = rng.multivariate_normal(np.zeros(30), np.array(MODEL["latent_correlation"]), size=n)
    cdf = NormalDist().cdf
    out = []
    for row in z:
        p = {}
        for facet, zi, counts in zip(MODEL["facets"], row, MODEL["marginal_counts"]):
            cum = np.cumsum(counts)
            i = min(int(np.searchsorted(cum / cum[-1], cdf(zi), side="right")), 16)
            p[facet] = round(100 * (cum[i] - counts[i] / 2) / cum[-1], 1)  # mid-rank percentile of the raw score
        out.append(p)
    return out


def describe(facets: dict, max_facets: int = 8) -> list[str]:
    """Extreme-decile facets first; an all-moderate person gets up to 4 milder ones, never a blank default."""
    ranked = sorted(facets, key=lambda k: (-abs(facets[k] - 50), k))
    picked = [k for k in ranked if facets[k] <= 10 or facets[k] >= 90][:max_facets] or \
             [k for k in ranked if abs(facets[k] - 50) >= 10][:4]
    return [("Strong tendency to " if facets[k] <= 10 or facets[k] >= 90 else "Somewhat inclined to ")
            + BEHAVIORS[k][0 if facets[k] >= 50 else 1] + "." for k in picked]


if __name__ == "__main__":
    ps = sample_facets(3000, 1)
    n1, n6 = np.array([p["N1"] for p in ps]), np.array([p["N6"] for p in ps])
    assert np.corrcoef(n1, n6)[0, 1] > 0.5, "anxiety and vulnerability should co-vary (fitted r=0.76)"
    assert all(0 <= v <= 100 for p in ps for v in p.values())
    assert describe({**{k: 50 for k in BEHAVIORS}, "E3": 95})[0].startswith("Strong tendency to speak up")
    assert "hold back" in describe({**{k: 50 for k in BEHAVIORS}, "E3": 5})[0]
    print("ok")
