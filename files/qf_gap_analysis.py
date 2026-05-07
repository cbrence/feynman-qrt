#!/usr/bin/env python3
"""
qf_gap_analysis.py — Quantitative Finance Research Gap Finder
Feynman skill helper for qf-gap-finder

Consolidated port of:
  - arxiv_gap_finder.py  (gap detection + opportunity scoring)
  - knowledge_graph.py   (co-occurrence matrix construction)

Key fixes vs. source repo:
  - Unified taxonomy (no divergence between KG and gap finder)
  - Co-occurrence update is idempotent
  - Gap scores persisted in output JSON (not recomputed each query)
  - CLI designed for non-interactive use (no input() prompts)

Usage:
  python3 qf_gap_analysis.py \\
      --input papers.json \\
      --output gap-report.json \\
      [--strengths bayesian,monte_carlo] \\
      [--interests credit_risk,volatility_modeling] \\
      [--level intermediate]
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations

# ---------------------------------------------------------------------------
# Unified taxonomy
# Single source of truth — used by both gap analysis and KG import.
# ---------------------------------------------------------------------------

METHODS: dict[str, list[str]] = {
    "bayesian": ["bayesian", "mcmc", "metropolis", "gibbs", "posterior", "prior"],
    "machine_learning": [
        "machine learning", "neural network", "deep learning",
        "random forest", "gradient boosting", "xgboost",
        "reinforcement learning", "lstm", "transformer",
    ],
    "monte_carlo": [
        "monte carlo", "quasi monte carlo", "variance reduction",
        "importance sampling",
    ],
    "pde": ["pde", "finite difference", "finite element", "partial differential"],
    "fft": ["fft", "fast fourier", "fourier transform", "convolution"],
    "optimization": [
        "optimization", "gradient descent", "newton method",
        "convex optimization", "conjugate gradient",
    ],
    "gpu_computing": ["gpu", "cuda", "parallel", "opencl", "acceleration", "distributed"],
    "time_series": ["time series", "arima", "garch", "arch", "autoregressive", "var model"],
    "stochastic_calculus": [
        "stochastic calculus", "ito", "brownian motion",
        "wiener process", "sde",
    ],
    "numerical_integration": [
        "quadrature", "numerical integration", "trapezoidal",
        "gauss hermite", "simpson",
    ],
    "regression": ["regression", "least squares", "generalized linear", "glm"],
}

DOMAINS: dict[str, list[str]] = {
    "option_pricing": [
        "option", "derivative pricing", "european", "american",
        "exotic option", "asian option",
    ],
    "volatility_modeling": [
        "volatility", "stochastic volatility", "local volatility",
        "implied volatility", "volatility surface",
    ],
    "credit_risk": [
        "credit", "default", "cds", "credit spread",
        "credit derivative", "counterparty risk", "probability of default",
    ],
    "portfolio": [
        "portfolio", "asset allocation", "mean variance",
        "markowitz", "portfolio optimization",
    ],
    "risk_management": [
        "var", "value at risk", "cvar", "expected shortfall",
        "risk measure", "stress test",
    ],
    "interest_rate": [
        "interest rate", "yield curve", "libor", "swap", "bond pricing",
    ],
    "market_microstructure": [
        "market microstructure", "liquidity", "order book",
        "high frequency", "limit order",
    ],
    "structured_products": [
        "cdo", "clo", "cmo", "mbs", "abs", "tranche", "structured product",
    ],
    "commodity": ["commodity", "energy", "oil", "natural gas", "electricity"],
    "insurance": ["insurance", "actuarial", "longevity", "mortality", "loss distribution"],
}

MODELS: dict[str, list[str]] = {
    "heston": ["heston"],
    "sabr": ["sabr"],
    "black_scholes": ["black scholes", "black-scholes"],
    "rough_volatility": ["rough volatility", "rough heston", "fractional brownian"],
    "jump_diffusion": ["jump diffusion", "merton jump", "kou"],
    "levy": ["levy", "variance gamma", "nig"],
    "hull_white": ["hull white", "hull-white"],
    "cir": ["cir", "cox ingersoll ross"],
}


# ---------------------------------------------------------------------------
# Paper loading
# ---------------------------------------------------------------------------

def load_papers(path: str) -> list[dict]:
    """Load papers from a JSON file or directory of JSON files."""
    all_papers = []
    files = [path] if os.path.isfile(path) else glob.glob(os.path.join(path, "*.json"))
    files = [f for f in files if "history" not in f and "manifest" not in f]

    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "papers" in data:
                all_papers.extend(data["papers"])
            elif isinstance(data, list):
                all_papers.extend(data)
        except Exception as e:
            print(f"  Warning: could not load {fpath}: {e}", file=sys.stderr)

    # Deduplicate on arxiv_id, falling back to normalised title
    seen: set[str] = set()
    unique = []
    for p in all_papers:
        key = p.get("arxiv_id") or _normalise_title(p.get("title", ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def _normalise_title(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", "", title.lower()).split())


# ---------------------------------------------------------------------------
# Concept extraction
# ---------------------------------------------------------------------------

def extract_concepts(papers: list[dict]) -> list[dict]:
    """Tag each paper with detected methods, domains, and models."""
    results = []
    for p in papers:
        text = ((p.get("title") or "") + " " + (p.get("abstract") or "")).lower()
        year_raw = p.get("published", p.get("year", ""))
        year = str(year_raw)[:4] if year_raw else ""
        results.append({
            "arxiv_id": p.get("arxiv_id", p.get("semantic_scholar_id", "")),
            "title": p.get("title", ""),
            "published": year,
            "citation_count": p.get("citation_count"),
            "venue": p.get("venue", "Unknown"),
            "influential_citations": p.get("influential_citations", 0),
            "text": text,
            "methods": [m for m, kws in METHODS.items() if any(kw in text for kw in kws)],
            "domains": [d for d, kws in DOMAINS.items() if any(kw in text for kw in kws)],
            "models":  [m for m, kws in MODELS.items()  if any(kw in text for kw in kws)],
        })
    return results


# ---------------------------------------------------------------------------
# Impact scoring
# ---------------------------------------------------------------------------

TOP_VENUES = {
    "mathematical finance", "journal of financial economics",
    "review of financial studies", "journal of finance",
    "quantitative finance", "finance and stochastics",
    "siam journal", "journal of computational finance",
    "operations research", "management science",
    "neurips", "icml", "iclr",
}

def impact_score(paper: dict) -> int:
    """0–3 impact score based on citations and venue."""
    score = 0
    citations = paper.get("citation_count")
    if citations is not None:
        score += 2 if citations >= 50 else (1 if citations >= 10 else 0)
    venue = (paper.get("venue") or "").lower()
    if any(v in venue for v in TOP_VENUES):
        score += 1
    if (paper.get("influential_citations") or 0) >= 5:
        score += 1
    return min(score, 3)


# ---------------------------------------------------------------------------
# Gap analyses
# ---------------------------------------------------------------------------

def method_domain_gaps(concepts: list[dict]) -> list[dict]:
    """Return method × domain gaps, scored by individual popularity."""
    pairs: dict[tuple, list[str]] = defaultdict(list)
    for p in concepts:
        for m in p["methods"]:
            for d in p["domains"]:
                pairs[(m, d)].append(p["title"])

    method_counts = Counter(m for p in concepts for m in p["methods"])
    domain_counts = Counter(d for p in concepts for d in p["domains"])

    gaps = []
    for method in METHODS:
        for domain in DOMAINS:
            count = len(pairs.get((method, domain), []))
            if count <= 2:
                gaps.append({
                    "method": method,
                    "domain": domain,
                    "count": count,
                    "gap_type": "UNEXPLORED" if count == 0 else "UNDEREXPLORED",
                    "priority": "HIGH" if count == 0 else "MEDIUM",
                    "score": method_counts[method] * domain_counts[domain],
                    "existing_papers": pairs.get((method, domain), []),
                })

    return sorted(gaps, key=lambda x: x["score"], reverse=True)


def concept_combination_gaps(concepts: list[dict]) -> list[dict]:
    """Find popular concepts (methods + models) that never co-occur."""
    counts: Counter = Counter()
    for p in concepts:
        for c in set(p["methods"] + p["models"]):
            counts[c] += 1

    cooccur: Counter = Counter()
    for p in concepts:
        cs = sorted(set(p["methods"] + p["models"]))
        for c1, c2 in combinations(cs, 2):
            cooccur[tuple(sorted([c1, c2]))] += 1

    popular = [c for c, n in counts.items() if n >= 3]
    gaps = []
    for c1, c2 in combinations(popular, 2):
        pair = tuple(sorted([c1, c2]))
        if cooccur[pair] == 0:
            gaps.append({
                "concept1": c1,
                "concept2": c2,
                "c1_count": counts[c1],
                "c2_count": counts[c2],
                "expected_score": (counts[c1] * counts[c2]) / max(len(concepts), 1),
                "actual": 0,
            })

    return sorted(gaps, key=lambda x: x["expected_score"], reverse=True)


BOTTLENECK_KEYWORDS = [
    "computationally expensive", "computational cost", "computationally intensive",
    "intractable", "prohibitively expensive", "high dimensional",
    "curse of dimensionality", "slow convergence", "difficult to compute",
    "numerical challenge", "time consuming",
]
SOLUTION_KEYWORDS = [
    "accelerate", "fast", "efficient", "reduce cost", "improve",
    "speedup", "optimize",
]

def computational_bottlenecks(concepts: list[dict]) -> list[dict]:
    """Papers citing unresolved computational challenges."""
    results = []
    for p in concepts:
        if any(kw in p["text"] for kw in BOTTLENECK_KEYWORDS):
            results.append({
                "title": p["title"],
                "arxiv_id": p["arxiv_id"],
                "domains": p["domains"],
                "models": p["models"],
                "year": p["published"],
                "proposes_solution": any(kw in p["text"] for kw in SOLUTION_KEYWORDS),
            })
    return results


def temporal_gaps(concepts: list[dict]) -> list[dict]:
    """Domains with ≥50% decline in recent activity."""
    timeline: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in concepts:
        if p["published"] and p["published"].isdigit():
            for d in p["domains"]:
                timeline[d][p["published"]] += 1

    declining = []
    for domain, years in timeline.items():
        if len(years) < 3:
            continue
        sorted_years = sorted(years.items())
        recent = sorted_years[-2:]
        earlier = sorted_years[:-2]
        if not recent or not earlier:
            continue
        recent_avg = sum(c for _, c in recent) / len(recent)
        earlier_avg = sum(c for _, c in earlier) / len(earlier)
        if earlier_avg > 0 and recent_avg < earlier_avg * 0.5:
            declining.append({
                "domain": domain,
                "earlier_avg": round(earlier_avg, 1),
                "recent_avg": round(recent_avg, 1),
                "decline_pct": round(((earlier_avg - recent_avg) / earlier_avg) * 100, 1),
                "timeline": sorted_years,
            })

    return sorted(declining, key=lambda x: x["decline_pct"], reverse=True)


# ---------------------------------------------------------------------------
# Personalised opportunity scoring
# ---------------------------------------------------------------------------

def score_opportunities(
    gaps: list[dict],
    bottlenecks: list[dict],
    concepts: list[dict],
    strengths: list[str],
    interests: list[str],
    level: str = "intermediate",
) -> list[dict]:
    """Score and rank research opportunities against a user's profile."""
    opportunities = []

    for gap in gaps[:60]:
        method, domain = gap["method"], gap["domain"]
        score = 0
        breakdown: dict[str, int] = {}

        # Method match (0–3)
        m_matches = sum(1 for s in strengths if s in method or method in s
                        or any(s in method for s in strengths))
        breakdown["method"] = min(m_matches + (1 if any(s in method for s in strengths) else 0), 3)
        score += breakdown["method"]

        # Domain match (0–3)
        d_matches = sum(1 for i in interests if i in domain or domain in i
                        or any(i in domain for i in interests))
        breakdown["domain"] = min(d_matches + (1 if any(i in domain for i in interests) else 0), 3)
        score += breakdown["domain"]

        if score == 0:
            continue  # No relevance to this profile

        # Priority bonus (0–2)
        breakdown["priority"] = 2 if gap["gap_type"] == "UNEXPLORED" else 1
        score += breakdown["priority"]

        # Maturity bonus (0–2)
        if level == "beginner":
            breakdown["maturity"] = 2 if 1 <= gap["count"] <= 3 else (1 if gap["count"] == 0 else 0)
        elif level == "advanced":
            breakdown["maturity"] = 2 if gap["count"] == 0 else 0
        else:  # intermediate
            breakdown["maturity"] = 2 if gap["count"] == 0 else (1 if gap["count"] <= 2 else 0)
        score += breakdown["maturity"]

        # Impact bonus (0–2): is there a high-impact paper nearby?
        nearby_impact = 0
        for title in gap["existing_papers"]:
            matches = [p for p in concepts if p.get("title") == title
                       and p.get("citation_count") is not None]
            if matches:
                nearby_impact = max(nearby_impact, impact_score(matches[0]))
        breakdown["impact"] = min(nearby_impact, 2) if gap["count"] <= 2 else 0
        score += breakdown["impact"]

        opportunities.append({
            "type": "method_domain_gap",
            "description": f"Apply {method.replace('_',' ')} to {domain.replace('_',' ')}",
            "gap": gap,
            "relevance_score": score,
            "score_breakdown": breakdown,
        })

    # Computational bottlenecks matching interests
    for b in [b for b in bottlenecks if not b["proposes_solution"]]:
        score = 0
        breakdown = {}
        d_matches = sum(1 for d in b["domains"] for i in interests if i in d or d in i)
        breakdown["domain"] = min(d_matches, 3)
        score += breakdown["domain"]
        if score == 0:
            continue
        breakdown["computational"] = 2 if any(s in ["gpu_computing", "optimization"]
                                               for s in strengths) else 0
        score += breakdown["computational"]
        try:
            year = int(b["year"])
        except (ValueError, TypeError):
            year = 0
        breakdown["recency"] = 2 if year >= 2024 else (1 if year >= 2022 else 0)
        score += breakdown["recency"]
        breakdown["priority"] = 1
        breakdown["maturity"] = 0
        breakdown["method"] = 0
        opportunities.append({
            "type": "computational_bottleneck",
            "description": f"Solve computational challenge in {', '.join(b['domains']) or 'unknown domain'}",
            "paper": b,
            "relevance_score": score,
            "score_breakdown": breakdown,
        })

    return sorted(opportunities, key=lambda x: x["relevance_score"], reverse=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="QF Research Gap Finder — Feynman skill helper"
    )
    parser.add_argument("--input", required=True,
                        help="Path to papers JSON file or directory")
    parser.add_argument("--output", required=True,
                        help="Output JSON path for gap report")
    parser.add_argument("--strengths", default="",
                        help="Comma-separated method keys (e.g. bayesian,monte_carlo)")
    parser.add_argument("--interests", default="",
                        help="Comma-separated domain keys (e.g. credit_risk,volatility_modeling)")
    parser.add_argument("--level", default="intermediate",
                        choices=["beginner", "intermediate", "advanced"])
    args = parser.parse_args()

    strengths = [s.strip() for s in args.strengths.split(",") if s.strip()]
    interests  = [i.strip() for i in args.interests.split(",")  if i.strip()]

    print(f"Loading papers from: {args.input}")
    papers = load_papers(args.input)
    if not papers:
        print("Error: no papers found.", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(papers)} unique papers loaded")

    print("Extracting concepts...")
    concepts = extract_concepts(papers)

    print("Computing method × domain gaps...")
    md_gaps = method_domain_gaps(concepts)

    print("Computing concept combination gaps...")
    cc_gaps = concept_combination_gaps(concepts)

    print("Finding computational bottlenecks...")
    bottlenecks = computational_bottlenecks(concepts)

    print("Analysing temporal trends...")
    t_gaps = temporal_gaps(concepts)

    opportunities = []
    if strengths or interests:
        print(f"Scoring personalised opportunities (strengths={strengths}, interests={interests})...")
        opportunities = score_opportunities(
            md_gaps, bottlenecks, concepts, strengths, interests, args.level
        )

    report = {
        "generated": datetime.now().isoformat(),
        "papers_analysed": len(papers),
        "profile": {"strengths": strengths, "interests": interests, "level": args.level},
        "method_domain_gaps": md_gaps[:30],
        "concept_combination_gaps": cc_gaps[:20],
        "computational_bottlenecks": {
            "total": len(bottlenecks),
            "unsolved": [b for b in bottlenecks if not b["proposes_solution"]][:20],
            "solved": [b for b in bottlenecks if b["proposes_solution"]][:10],
        },
        "temporal_gaps": t_gaps,
        "opportunities": opportunities[:20],
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Gap report written to: {args.output}")
    print(f"  Method×domain gaps:       {len(md_gaps)}")
    print(f"  Concept combination gaps: {len(cc_gaps)}")
    print(f"  Computational bottlenecks:{len(bottlenecks)} ({len([b for b in bottlenecks if not b['proposes_solution']])} unsolved)")
    print(f"  Temporal gaps:            {len(t_gaps)}")
    if opportunities:
        print(f"  Personalised opportunities: {len(opportunities)} (top score: {opportunities[0]['relevance_score']}/10)")


if __name__ == "__main__":
    main()
