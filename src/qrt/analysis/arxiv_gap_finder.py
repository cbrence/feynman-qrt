#!/usr/bin/env python3
"""
arxiv_gap_finder.py - Find research gaps by analyzing what's NOT being studied

This tool identifies:
1. Method-domain gaps (methods not applied to specific problems)
2. Temporal gaps (declining research areas that might be ripe for revival)
3. Computational bottlenecks (problems citing computational challenges)
4. Combination gaps (concepts that appear separately but never together)
"""

import glob
import json
import os
from collections import Counter, defaultdict
from itertools import combinations


def load_papers(json_file_or_dir):
    """Load papers from JSON file or directory"""
    all_papers = []

    if os.path.isfile(json_file_or_dir):
        files = [json_file_or_dir]
    else:
        files = glob.glob(os.path.join(json_file_or_dir, "*.json"))
        files = [f for f in files if "history" not in f and "manifest" not in f]

    for json_file in files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict) and "papers" in data:
                all_papers.extend(data["papers"])
            elif isinstance(data, list):
                all_papers.extend(data)
        except:
            continue

    # Deduplicate
    seen = set()
    unique_papers = []
    for paper in all_papers:
        arxiv_id = paper.get("arxiv_id", paper.get("title", ""))
        if arxiv_id not in seen:
            seen.add(arxiv_id)
            unique_papers.append(paper)

    return unique_papers


def extract_concepts(papers):
    """Extract key concepts from papers and categorize them"""

    # Define concept taxonomies
    METHODS = {
        "bayesian": ["bayesian", "mcmc", "metropolis", "gibbs", "posterior", "prior"],
        "machine_learning": [
            "machine learning",
            "neural network",
            "deep learning",
            "random forest",
            "gradient boosting",
            "reinforcement learning",
            "lstm",
            "transformer",
        ],
        "monte_carlo": [
            "monte carlo",
            "quasi monte carlo",
            "variance reduction",
            "importance sampling",
        ],
        "pde": ["pde", "finite difference", "finite element", "partial differential"],
        "fft": ["fft", "fast fourier", "fourier transform", "convolution"],
        "optimization": [
            "optimization",
            "gradient descent",
            "newton method",
            "conjugate gradient",
        ],
        "gpu_computing": [
            "gpu",
            "cuda",
            "parallel",
            "opencl",
            "acceleration",
            "distributed",
        ],
        "numerical_integration": [
            "quadrature",
            "integration",
            "trapezoidal",
            "simpson",
        ],
        "regression": ["regression", "least squares", "generalized linear"],
        "time_series": ["time series", "arima", "garch", "arch", "autoregressive"],
    }

    DOMAINS = {
        "option_pricing": [
            "option",
            "derivative pricing",
            "european",
            "american",
            "exotic option",
        ],
        "volatility_modeling": [
            "volatility",
            "stochastic volatility",
            "local volatility",
            "implied volatility",
            "volatility surface",
        ],
        "credit_risk": [
            "credit",
            "default",
            "cds",
            "credit spread",
            "credit derivative",
        ],
        "portfolio": ["portfolio", "asset allocation", "mean variance", "markowitz"],
        "risk_management": [
            "var",
            "value at risk",
            "cvar",
            "expected shortfall",
            "risk measure",
        ],
        "interest_rate": ["interest rate", "yield curve", "libor", "swap", "bond"],
        "market_microstructure": [
            "market microstructure",
            "liquidity",
            "order book",
            "high frequency",
        ],
        "structured_products": [
            "cdo",
            "cmo",
            "mbs",
            "abs",
            "tranche",
            "structured product",
        ],
        "commodity": ["commodity", "energy", "oil", "gas", "electricity"],
        "insurance": ["insurance", "actuarial", "longevity", "mortality"],
    }

    MODELS = {
        "heston": ["heston"],
        "sabr": ["sabr"],
        "black_scholes": ["black scholes", "black-scholes"],
        "rough_volatility": ["rough volatility", "rough heston", "fractional"],
        "jump_diffusion": ["jump", "merton jump", "kou"],
        "levy": ["levy", "variance gamma", "nig"],
        "libor_market": ["libor market", "bgm", "brace gatarek"],
        "hull_white": ["hull white", "hull-white"],
        "cir": ["cir", "cox ingersoll ross"],
    }

    # Extract what each paper covers
    paper_concepts = []

    for paper in papers:
        text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()

        concepts = {
            "methods": [],
            "domains": [],
            "models": [],
            "arxiv_id": paper.get("arxiv_id"),
            "title": paper.get("title"),
            "published": paper.get("published", "")[:4],  # Just year
            "text": text,
        }

        # Check for each concept
        for method, keywords in METHODS.items():
            if any(kw in text for kw in keywords):
                concepts["methods"].append(method)

        for domain, keywords in DOMAINS.items():
            if any(kw in text for kw in keywords):
                concepts["domains"].append(domain)

        for model, keywords in MODELS.items():
            if any(kw in text for kw in keywords):
                concepts["models"].append(model)

        paper_concepts.append(concepts)

    return paper_concepts, METHODS, DOMAINS, MODELS


def calculate_impact_score(paper):
    """
    Calculate impact score based on citations and venue

    Returns score 0-3:
      3 = High impact (top venue + many citations)
      2 = Medium impact (good venue or good citations)
      1 = Low impact (some citations or known venue)
      0 = Minimal impact (arXiv only, few citations)
    """
    citations = paper.get("citation_count", 0)
    venue = paper.get("venue", "arXiv only")
    influential = paper.get("influential_citations", 0)

    score = 0

    # Citation score (0-2 points)
    if citations is None:
        # Not enriched
        score += 0
    elif citations >= 50:
        score += 2
    elif citations >= 10:
        score += 1

    # Venue score (0-1 point)
    top_venues = [
        "Mathematical Finance",
        "Journal of Financial Economics",
        "Review of Financial Studies",
        "Journal of Finance",
        "Quantitative Finance",
        "Finance and Stochastics",
        "SIAM Journal",
        "Journal of Computational Finance",
        "Operations Research",
        "Management Science",
        "NeurIPS",
        "ICML",
        "ICLR",
    ]

    if any(tv.lower() in venue.lower() for tv in top_venues):
        score += 1

    # Influential citation bonus
    if influential and influential >= 5:
        score += 1  # Cap at 3 total

    return min(score, 3)  # Cap at 3


def analyze_research_trends(paper_concepts):
    """
    Analyze trends based on citations and venues
    """
    print("\n" + "=" * 80)
    print("RESEARCH IMPACT ANALYSIS")
    print("=" * 80)

    # Get papers with citation data
    papers_with_data = [
        p for p in paper_concepts if p.get("citation_count") is not None
    ]

    if not papers_with_data:
        print("\nNo citation data available. Run enrich_arxiv_data.py first.")
        return

    print(f"\nAnalyzing {len(papers_with_data)} papers with citation data")

    # High-impact papers by domain
    domain_impact = {}
    for paper in papers_with_data:
        impact = calculate_impact_score(paper)
        if impact >= 2:  # Medium or high impact
            for domain in paper.get("domains", []):
                if domain not in domain_impact:
                    domain_impact[domain] = []
                domain_impact[domain].append(
                    {
                        "title": paper.get("title"),
                        "citations": paper.get("citation_count", 0),
                        "venue": paper.get("venue", "Unknown"),
                        "impact_score": impact,
                    }
                )

    print("\n" + "-" * 80)
    print("HIGH-IMPACT PAPERS BY DOMAIN")
    print("-" * 80)

    for domain, papers in sorted(
        domain_impact.items(),
        key=lambda x: sum(p["impact_score"] for p in x[1]),
        reverse=True,
    )[:5]:
        print(f"\n{domain.replace('_', ' ').title()}:")
        for paper in sorted(papers, key=lambda x: x["citations"], reverse=True)[:3]:
            print(f"  • {paper['title'][:60]}...")
            print(f"    Citations: {paper['citations']} | Venue: {paper['venue']}")

    # Venue prestige
    venue_stats = {}
    for paper in papers_with_data:
        venue = paper.get("venue", "arXiv only")
        if venue not in venue_stats:
            venue_stats[venue] = {"count": 0, "total_citations": 0, "papers": []}
        venue_stats[venue]["count"] += 1
        venue_stats[venue]["total_citations"] += paper.get("citation_count", 0)
        venue_stats[venue]["papers"].append(paper.get("title"))

    print("\n" + "-" * 80)
    print("TOP PUBLICATION VENUES (by avg citations)")
    print("-" * 80)

    venue_ranking = []
    for venue, stats in venue_stats.items():
        if stats["count"] >= 2:  # At least 2 papers
            avg_citations = stats["total_citations"] / stats["count"]
            venue_ranking.append((venue, stats["count"], avg_citations))

    for venue, count, avg in sorted(venue_ranking, key=lambda x: x[2], reverse=True)[
        :10
    ]:
        print(f"{venue:50} | {count:2} papers | Avg: {avg:.1f} citations")

    return domain_impact, venue_stats


def find_method_domain_gaps(paper_concepts, methods_taxonomy, domains_taxonomy):
    """Find combinations of methods and domains that haven't been explored"""

    print("\n" + "=" * 80)
    print("METHOD-DOMAIN GAP ANALYSIS")
    print("=" * 80)

    # Build co-occurrence matrix
    method_domain_pairs = defaultdict(list)

    for paper in paper_concepts:
        for method in paper["methods"]:
            for domain in paper["domains"]:
                method_domain_pairs[(method, domain)].append(paper["title"])

    # Find gaps (combinations that don't exist or are rare)
    all_methods = list(methods_taxonomy.keys())
    all_domains = list(domains_taxonomy.keys())

    gaps = []

    for method in all_methods:
        for domain in all_domains:
            pair = (method, domain)
            count = len(method_domain_pairs.get(pair, []))

            if count == 0:
                gaps.append(
                    {
                        "method": method,
                        "domain": domain,
                        "count": 0,
                        "gap_type": "UNEXPLORED",
                        "priority": "HIGH",
                    }
                )
            elif count <= 2:
                gaps.append(
                    {
                        "method": method,
                        "domain": domain,
                        "count": count,
                        "gap_type": "UNDEREXPLORED",
                        "priority": "MEDIUM",
                        "existing_papers": method_domain_pairs[pair],
                    }
                )

    # Prioritize gaps based on how active the method and domain are separately
    method_counts = Counter()
    domain_counts = Counter()

    for paper in paper_concepts:
        for method in paper["methods"]:
            method_counts[method] += 1
        for domain in paper["domains"]:
            domain_counts[domain] += 1

    # Score gaps: high if both method and domain are popular but not combined
    for gap in gaps:
        method_pop = method_counts.get(gap["method"], 0)
        domain_pop = domain_counts.get(gap["domain"], 0)
        gap["score"] = method_pop * domain_pop

    # Sort by score
    gaps = sorted(gaps, key=lambda x: x["score"], reverse=True)

    # Display top gaps
    print("\nTop Research Gaps (Method + Domain combinations):")
    print("-" * 80)

    for i, gap in enumerate(gaps[:20], 1):
        method_display = gap["method"].replace("_", " ").title()
        domain_display = gap["domain"].replace("_", " ").title()

        print(f"\n{i}. {method_display} × {domain_display}")
        print(f"   Status: {gap['gap_type']} ({gap['count']} papers)")
        print(f"   Priority: {gap['priority']} (Score: {gap['score']})")

        if gap["count"] > 0 and gap["count"] <= 2:
            print("   Existing work:")
            for paper_title in gap["existing_papers"]:
                print(f"     • {paper_title[:70]}...")

    return gaps


def find_computational_bottlenecks(paper_concepts):
    """Find problems that explicitly mention computational challenges"""

    print("\n" + "=" * 80)
    print("COMPUTATIONAL BOTTLENECK ANALYSIS")
    print("=" * 80)

    # Keywords indicating computational challenges
    challenge_keywords = [
        "computationally expensive",
        "computational cost",
        "computational challenge",
        "computationally intensive",
        "time consuming",
        "intractable",
        "prohibitively expensive",
        "high dimensional",
        "curse of dimensionality",
        "slow convergence",
        "difficult to compute",
        "numerical challenge",
    ]

    bottlenecks = []

    for paper in paper_concepts:
        text = paper["text"]

        # Check if paper mentions computational challenges
        mentions_challenge = any(kw in text for kw in challenge_keywords)

        if mentions_challenge:
            # Check if it proposes a solution
            solution_keywords = [
                "accelerate",
                "fast",
                "efficient",
                "reduce cost",
                "improve",
                "speedup",
                "optimize",
            ]
            proposes_solution = any(kw in text for kw in solution_keywords)

            bottlenecks.append(
                {
                    "title": paper["title"],
                    "arxiv_id": paper["arxiv_id"],
                    "domains": paper["domains"],
                    "models": paper["models"],
                    "proposes_solution": proposes_solution,
                    "year": paper["published"],
                }
            )

    print(f"\nFound {len(bottlenecks)} papers mentioning computational challenges")

    # Categorize by whether they solve the problem or just mention it
    unsolved = [b for b in bottlenecks if not b["proposes_solution"]]
    solved = [b for b in bottlenecks if b["proposes_solution"]]

    print(f"\nProblems with proposed solutions: {len(solved)}")
    print(f"Problems still mentioning challenges: {len(unsolved)}")

    if unsolved:
        print("\n" + "-" * 80)
        print("COMPUTATIONAL CHALLENGES STILL SEEKING SOLUTIONS:")
        print("-" * 80)

        # Group by domain
        by_domain = defaultdict(list)
        for b in unsolved:
            for domain in b["domains"]:
                by_domain[domain].append(b)

        for domain, papers in sorted(
            by_domain.items(), key=lambda x: len(x[1]), reverse=True
        ):
            print(f"\n{domain.replace('_', ' ').title()} ({len(papers)} papers):")
            for paper in papers[:3]:
                print(f"  • {paper['title'][:70]}... [{paper['year']}]")

    return bottlenecks


def find_temporal_gaps(paper_concepts):
    """Find research areas with declining activity (potential revival opportunities)"""

    print("\n" + "=" * 80)
    print("TEMPORAL GAP ANALYSIS (Declining Research Areas)")
    print("=" * 80)

    # Count papers per domain per year
    domain_timeline = defaultdict(lambda: defaultdict(int))

    for paper in paper_concepts:
        year = paper["published"]
        if year and year.isdigit():
            for domain in paper["domains"]:
                domain_timeline[domain][year] += 1

    # Identify domains with declining activity
    declining_domains = []

    for domain, years in domain_timeline.items():
        if len(years) < 3:  # Need at least 3 years of data
            continue

        sorted_years = sorted(years.items())
        recent_years = sorted_years[-2:]  # Last 2 years
        earlier_years = sorted_years[:-2]  # Previous years

        if not recent_years or not earlier_years:
            continue

        recent_avg = sum(count for _, count in recent_years) / len(recent_years)
        earlier_avg = sum(count for _, count in earlier_years) / len(earlier_years)

        if recent_avg < earlier_avg * 0.5:  # 50% decline
            declining_domains.append(
                {
                    "domain": domain,
                    "earlier_avg": earlier_avg,
                    "recent_avg": recent_avg,
                    "decline_pct": ((earlier_avg - recent_avg) / earlier_avg) * 100,
                    "timeline": sorted_years,
                }
            )

    if declining_domains:
        declining_domains = sorted(
            declining_domains, key=lambda x: x["decline_pct"], reverse=True
        )

        print("\nResearch areas with declining activity (revival opportunities):")
        print("-" * 80)

        for i, domain in enumerate(declining_domains, 1):
            print(f"\n{i}. {domain['domain'].replace('_', ' ').title()}")
            print(f"   Decline: {domain['decline_pct']:.1f}% drop")
            print(f"   Earlier average: {domain['earlier_avg']:.1f} papers/year")
            print(f"   Recent average: {domain['recent_avg']:.1f} papers/year")
            print(
                f"   Timeline: {', '.join([f'{y}: {c}' for y, c in domain['timeline']])}"
            )
    else:
        print("\nNo significant declining trends detected (all areas remain active)")

    return declining_domains


def find_combination_gaps(paper_concepts):
    """Find concepts that appear frequently but never together"""

    print("\n" + "=" * 80)
    print("CONCEPT COMBINATION GAP ANALYSIS")
    print("=" * 80)

    # Get all unique concepts
    all_methods = set()
    all_models = set()

    for paper in paper_concepts:
        all_methods.update(paper["methods"])
        all_models.update(paper["models"])

    all_concepts = list(all_methods) + list(all_models)

    # Count individual concept frequencies
    concept_counts = Counter()
    for paper in paper_concepts:
        concepts = set(paper["methods"] + paper["models"])
        concept_counts.update(concepts)

    # Count co-occurrences
    co_occurrences = defaultdict(int)

    for paper in paper_concepts:
        concepts = set(paper["methods"] + paper["models"])
        for c1, c2 in combinations(sorted(concepts), 2):
            co_occurrences[(c1, c2)] += 1

    # Find gaps: popular concepts that don't appear together
    gaps = []

    popular_concepts = [c for c, count in concept_counts.items() if count >= 3]

    for c1, c2 in combinations(popular_concepts, 2):
        if c1 == c2:
            continue

        pair = tuple(sorted([c1, c2]))
        co_occur_count = co_occurrences.get(pair, 0)

        if co_occur_count == 0:
            # Calculate expected co-occurrence based on individual frequencies
            c1_freq = concept_counts[c1]
            c2_freq = concept_counts[c2]
            expected = (c1_freq * c2_freq) / len(paper_concepts)

            gaps.append(
                {
                    "concept1": c1,
                    "concept2": c2,
                    "c1_count": c1_freq,
                    "c2_count": c2_freq,
                    "expected_score": expected,
                    "actual": 0,
                }
            )

    # Sort by expected score (high = both concepts popular but never combined)
    gaps = sorted(gaps, key=lambda x: x["expected_score"], reverse=True)

    print("\nTop concept pairs that should exist but don't:")
    print("-" * 80)

    for i, gap in enumerate(gaps[:15], 1):
        c1 = gap["concept1"].replace("_", " ").title()
        c2 = gap["concept2"].replace("_", " ").title()

        print(f"\n{i}. {c1} + {c2}")
        print(
            f"   Individual frequencies: {c1} ({gap['c1_count']} papers), "
            f"{c2} ({gap['c2_count']} papers)"
        )
        print(f"   Combined: 0 papers (Expected: {gap['expected_score']:.1f})")

    return gaps


def identify_your_opportunities(
    gaps, bottlenecks, combinations, background, paper_concepts
):
    """
    Given your background, identify specific opportunities with enhanced scoring

    Args:
        background: dict with keys 'strengths', 'interests', 'experience_level'
        paper_concepts: list of paper concept dictionaries with citation data
    """
    print("\n" + "=" * 80)
    print("PERSONALIZED OPPORTUNITY ANALYSIS")
    print("=" * 80)

    strengths = background.get("strengths", [])
    interests = background.get("interests", [])
    experience_level = background.get("experience_level", "intermediate")

    print(f"\nYour strengths: {', '.join(strengths)}")
    print(f"Your interests: {', '.join(interests)}")
    print(f"Experience level: {experience_level}")

    opportunities = []

    # Match method-domain gaps to your strengths
    print("\n" + "-" * 80)
    print("OPPORTUNITIES MATCHING YOUR PROFILE:")
    print("-" * 80)

    for gap in gaps[:50]:  # Check top 50 gaps (increased from 30)
        method = gap["method"]
        domain = gap["domain"]

        # Calculate relevance score (0-10)
        score = 0
        score_breakdown = {}

        # 1. Method match (0-3 points)
        method_matches = [s for s in strengths if s in method or method in s]
        if len(method_matches) >= 2:
            score += 3
            score_breakdown["method"] = 3
        elif len(method_matches) == 1:
            score += 2
            score_breakdown["method"] = 2
        else:
            # Partial match (e.g., 'gpu' matches 'gpu_computing')
            if any(s in method for s in strengths):
                score += 1
                score_breakdown["method"] = 1
            else:
                score_breakdown["method"] = 0

        # 2. Domain match (0-3 points)
        domain_matches = [i for i in interests if i in domain or domain in i]
        if len(domain_matches) >= 2:
            score += 3
            score_breakdown["domain"] = 3
        elif len(domain_matches) == 1:
            score += 2
            score_breakdown["domain"] = 2
        else:
            # Partial match
            if any(i in domain for i in interests):
                score += 1
                score_breakdown["domain"] = 1
            else:
                score_breakdown["domain"] = 0

        # Only include if at least method OR domain matches
        if score == 0:
            continue

        # 3. Gap priority bonus (0-2 points)
        if gap["gap_type"] == "UNEXPLORED" and gap["priority"] == "HIGH":
            score += 2
            score_breakdown["priority"] = 2
        elif gap["gap_type"] == "UNEXPLORED" or gap["priority"] == "HIGH":
            score += 1
            score_breakdown["priority"] = 1
        else:
            score_breakdown["priority"] = 0

        # 4. Research maturity bonus (0-2 points)
        # Adjust based on experience level and existing papers
        if experience_level == "beginner":
            # Prefer underexplored (some papers exist to learn from)
            if gap["count"] >= 1 and gap["count"] <= 3:
                score += 2
                score_breakdown["maturity"] = 2
            elif gap["count"] == 0:
                score += 1
                score_breakdown["maturity"] = 1
            else:
                score_breakdown["maturity"] = 0
        elif experience_level == "intermediate":
            # Prefer mix of unexplored and underexplored
            if gap["count"] == 0:
                score += 2
                score_breakdown["maturity"] = 2
            elif gap["count"] <= 2:
                score += 1
                score_breakdown["maturity"] = 1
            else:
                score_breakdown["maturity"] = 0
        else:  # advanced
            # Prefer completely unexplored
            if gap["count"] == 0:
                score += 2
                score_breakdown["maturity"] = 2
            else:
                score_breakdown["maturity"] = 0

        # 5. Impact bonus (0-2 points) - if we have enriched data
        impact_score = 0
        if gap.get("existing_papers"):
            # Check if gap has citation data
            for paper_title in gap["existing_papers"]:
                # Find matching paper in our dataset
                matching = [
                    p
                    for p in paper_concepts
                    if p.get("title") == paper_title
                    and p.get("citation_count") is not None
                ]
                if matching:
                    paper_impact = calculate_impact_score(matching[0])
                    impact_score = max(impact_score, paper_impact)

        # Adjust interpretation: high impact in underexplored area = great opportunity
        if impact_score >= 2 and gap["count"] <= 2:
            score += 2  # Hot area with room for contribution
            score_breakdown["impact"] = 2
        elif impact_score >= 1:
            score += 1
            score_breakdown["impact"] = 1
        else:
            score_breakdown["impact"] = 0

        opportunities.append(
            {
                "type": "method_domain_gap",
                "description": f"Apply {method.replace('_', ' ')} to {domain.replace('_', ' ')}",
                "gap": gap,
                "relevance_score": score,
                "score_breakdown": score_breakdown,
            }
        )

    # Check computational bottlenecks matching your interests
    for bottleneck in bottlenecks:
        if not bottleneck["proposes_solution"]:
            # Calculate score for bottlenecks
            score = 0
            score_breakdown = {}

            # Domain match (0-3)
            domain_matches = sum(
                1 for d in bottleneck["domains"] for i in interests if i in d or d in i
            )
            if domain_matches >= 2:
                score += 3
                score_breakdown["domain"] = 3
            elif domain_matches == 1:
                score += 2
                score_breakdown["domain"] = 2
            else:
                # Partial match
                partial = any(
                    any(i in d for i in interests) for d in bottleneck["domains"]
                )
                if partial:
                    score += 1
                    score_breakdown["domain"] = 1
                else:
                    score_breakdown["domain"] = 0

            if score == 0:
                continue

            # Computational bottleneck bonus (automatic +2 for relevant computational skills)
            comp_skills = ["gpu_computing", "optimization", "parallel", "distributed"]
            if any(s in strengths for s in comp_skills):
                score += 2
                score_breakdown["computational"] = 2
            else:
                score_breakdown["computational"] = 0

            # Recency bonus (0-2)
            year = int(bottleneck["year"]) if bottleneck["year"].isdigit() else 0
            if year >= 2024:
                score += 2
                score_breakdown["recency"] = 2
            elif year >= 2022:
                score += 1
                score_breakdown["recency"] = 1
            else:
                score_breakdown["recency"] = 0

            # Method match bonus (0-1)
            score_breakdown["method"] = 0

            # Priority and maturity
            score_breakdown["priority"] = 1  # Bottlenecks are inherently important
            score_breakdown["maturity"] = 0

            opportunities.append(
                {
                    "type": "computational_bottleneck",
                    "description": f"Solve computational challenge in {', '.join(bottleneck['domains'])}",
                    "paper": bottleneck,
                    "relevance_score": score,
                    "score_breakdown": score_breakdown,
                }
            )

    # Sort by relevance
    opportunities = sorted(
        opportunities, key=lambda x: x["relevance_score"], reverse=True
    )

    if opportunities:
        print(f"\nFound {len(opportunities)} opportunities matching your profile:\n")

        for i, opp in enumerate(opportunities[:15], 1):  # Show top 15
            score = opp["relevance_score"]
            breakdown = opp["score_breakdown"]

            # Visual score representation
            stars = "★" * score + "☆" * (10 - score)

            print(f"{i}. {opp['description']}")
            print(f"   Relevance: {score}/10 {stars}")
            print(
                f"   Breakdown: Method={breakdown.get('method', 0)} | "
                f"Domain={breakdown.get('domain', 0)} | "
                f"Priority={breakdown.get('priority', 0)} | "
                f"Maturity={breakdown.get('maturity', 0)}"
                + (
                    f" | Impact={breakdown.get('impact', 0)}"
                    if "impact" in breakdown
                    else ""
                )
                + (
                    f" | Computational={breakdown.get('computational', 0)}"
                    if "computational" in breakdown
                    else ""
                )
                + (
                    f" | Recency={breakdown.get('recency', 0)}"
                    if "recency" in breakdown
                    else ""
                )
            )

            if opp["type"] == "method_domain_gap":
                gap = opp["gap"]
                print(f"   Status: {gap['gap_type']} ({gap['count']} existing papers)")
                print(f"   Priority: {gap['priority']}")
            else:
                paper = opp["paper"]
                print(f"   Computational bottleneck: {paper['title'][:60]}...")
                print(f"   Year: {paper['year']}")

            print()
    else:
        print(
            "\nNo direct matches found. Consider broadening your interests or adjusting experience level."
        )

    return opportunities


def save_gap_report(
    gaps,
    bottlenecks,
    declining,
    combinations,
    opportunities=None,
    filename="research_gap_report.txt",
):
    """Save comprehensive gap analysis report"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("RESEARCH GAP ANALYSIS REPORT\n")
        f.write("=" * 80 + "\n\n")

        f.write("1. METHOD-DOMAIN GAPS\n")
        f.write("-" * 80 + "\n")
        for i, gap in enumerate(gaps[:20], 1):
            method = gap["method"].replace("_", " ").title()
            domain = gap["domain"].replace("_", " ").title()
            f.write(f"\n{i}. {method} × {domain}\n")
            f.write(f"   Status: {gap['gap_type']} ({gap['count']} papers)\n")
            f.write(f"   Priority: {gap['priority']} (Score: {gap['score']})\n")

        f.write("\n\n2. COMPUTATIONAL BOTTLENECKS\n")
        f.write("-" * 80 + "\n")
        unsolved = [b for b in bottlenecks if not b["proposes_solution"]]
        for i, b in enumerate(unsolved[:15], 1):
            f.write(f"\n{i}. {b['title']}\n")
            f.write(f"   Domains: {', '.join(b['domains'])}\n")
            f.write(f"   Year: {b['year']}\n")

        f.write("\n\n3. DECLINING RESEARCH AREAS\n")
        f.write("-" * 80 + "\n")
        for i, d in enumerate(declining, 1):
            f.write(f"\n{i}. {d['domain'].replace('_', ' ').title()}\n")
            f.write(f"   Decline: {d['decline_pct']:.1f}%\n")
            f.write(
                f"   Timeline: {', '.join([f'{y}: {c}' for y, c in d['timeline']])}\n"
            )

        f.write("\n\n4. CONCEPT COMBINATION GAPS\n")
        f.write("-" * 80 + "\n")
        for i, gap in enumerate(combinations[:20], 1):
            c1 = gap["concept1"].replace("_", " ").title()
            c2 = gap["concept2"].replace("_", " ").title()
            f.write(f"\n{i}. {c1} + {c2}\n")
            f.write(
                f"   Individual: {c1} ({gap['c1_count']}), {c2} ({gap['c2_count']})\n"
            )
            f.write("   Combined: 0 papers\n")

        if opportunities:
            f.write("\n\n5. PERSONALIZED OPPORTUNITIES\n")
            f.write("-" * 80 + "\n")
            for i, opp in enumerate(opportunities[:15], 1):
                score = opp["relevance_score"]
                breakdown = opp["score_breakdown"]

                f.write(f"\n{i}. {opp['description']}\n")
                f.write(f"   Relevance: {score}/10\n")
                f.write(
                    f"   Breakdown: Method={breakdown.get('method', 0)} | "
                    f"Domain={breakdown.get('domain', 0)} | "
                    f"Priority={breakdown.get('priority', 0)} | "
                    f"Maturity={breakdown.get('maturity', 0)}\n"
                )

    print(f"\n✓ Gap analysis report saved to: {filename}")


def main():
    """Main gap finder interface"""
    import sys

    print("=" * 80)
    print("arXiv Research Gap Finder")
    print("Identify unexplored research opportunities")
    print("=" * 80)

    # Load papers
    if len(sys.argv) < 2:
        print("\nUsage: python arxiv_gap_finder.py <json_file_or_directory>")
        print("Example: python arxiv_gap_finder.py .")
        sys.exit(1)

    path = sys.argv[1]
    papers = load_papers(path)

    print(f"\nLoaded {len(papers)} papers")

    if len(papers) < 10:
        print("Warning: Need at least 10 papers for meaningful gap analysis")
        print("Try collecting more papers first using arxiv_search.py")
        sys.exit(1)

    # Extract concepts
    print("\nExtracting concepts from papers...")
    paper_concepts, methods, domains, models = extract_concepts(papers)

    # Run gap analyses
    print("\nRunning gap analysis...")

    gaps = find_method_domain_gaps(paper_concepts, methods, domains)
    bottlenecks = find_computational_bottlenecks(paper_concepts)
    declining = find_temporal_gaps(paper_concepts)
    combinations = find_combination_gaps(paper_concepts)

    # Personalized analysis
    # Personalized analysis
    print("\n" + "=" * 80)
    personalize = (
        input("\nWould you like personalized opportunity analysis? (y/n): ")
        .strip()
        .lower()
    )

    opportunities = None
    if personalize == "y":
        print("\nWhat are your key strengths/methods? (comma-separated)")
        print("Examples: bayesian, gpu_computing, machine_learning, optimization")
        strengths_input = input("Your strengths: ").strip()
        strengths = [
            s.strip().lower().replace(" ", "_") for s in strengths_input.split(",")
        ]

        print("\nWhat domains interest you? (comma-separated)")
        print("Examples: credit_risk, volatility_modeling, option_pricing")
        interests_input = input("Your interests: ").strip()
        interests = [
            i.strip().lower().replace(" ", "_") for i in interests_input.split(",")
        ]

        print("\nWhat is your experience level?")
        print("  1. Beginner (prefer some existing work to learn from)")
        print("  2. Intermediate (mix of explored and unexplored)")
        print("  3. Advanced (prefer completely unexplored areas)")
        exp_choice = input("Your choice (1-3, default: 2): ").strip()

        exp_map = {"1": "beginner", "2": "intermediate", "3": "advanced"}
        experience_level = exp_map.get(exp_choice, "intermediate")

        background = {
            "strengths": strengths,
            "interests": interests,
            "experience_level": experience_level,
        }

        opportunities = identify_your_opportunities(
            gaps, bottlenecks, combinations, background, paper_concepts
        )

    # Save report
    save_gap_report(gaps, bottlenecks, declining, combinations, opportunities)

    print("\n" + "=" * 80)
    print("Gap analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
