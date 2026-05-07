---
name: qf-gap-finder
description: >
  Identify unexplored and underexplored research opportunities in quantitative
  finance by running a method×domain co-occurrence gap analysis over a corpus
  of papers. Use this skill when the user asks to find research gaps, identify
  publication opportunities, or discover where their technical skills are
  underrepresented in the literature.
---

# Quantitative Finance Gap Finder

This skill analyses a set of papers (collected from arXiv / Semantic Scholar
via a prior search or `/lit` run) and produces a structured gap report across
four dimensions:

1. **Method × Domain gaps** — method/technique combinations not yet applied to
   specific quant-finance problems
2. **Concept combination gaps** — popular concepts that appear individually but
   never together
3. **Computational bottlenecks** — papers that flag unresolved computational
   challenges
4. **Temporal gaps** — research areas in measurable decline (potential revival
   opportunities)

It also produces a **personalised opportunity ranking** when the user provides
their skill profile.

---

## When to invoke

Trigger this skill when the user says things like:

- "find research gaps in [topic]"
- "where could I publish based on my background in [X]"
- "what's underexplored in [domain]"
- "run a gap analysis on these papers"
- "which method × domain combinations are missing"

Do **not** use this skill for general literature summarisation — use `/lit` for
that. This skill is specifically for gap detection, not synthesis.

---

## Required inputs

Before running, confirm you have at least one of:

- A JSON file of papers (from a prior `qrt-search`, Semantic Scholar, or arXiv
  export) in the session's `outputs/` directory, **or**
- A completed `/lit` or `/deepresearch` run whose paper list can be serialised

If neither exists, run a paper search first:
```
feynman "collect papers on [topic]" --output papers.json
```

---

## Execution steps

### Step 1 — Locate or prepare paper data

Check `outputs/` for any `*.json` file containing a `papers` array or a flat
list of paper objects. Each paper object must have at minimum:
- `title` (string)
- `abstract` (string)
- `published` (year string, e.g. `"2023"`)

Citation counts and venue fields improve scoring quality but are optional.

If multiple JSON files exist, merge them (the helper script deduplicates on
title normalisation).

### Step 2 — Run the gap analysis script

Execute the helper script via Docker (isolated execution):

```bash
python3 {baseDir}/qf_gap_analysis.py \
  --input <path_to_papers_json> \
  --output outputs/<slug>-gap-report.json \
  [--strengths bayesian,monte_carlo,gpu_computing] \
  [--interests credit_risk,volatility_modeling] \
  [--level intermediate]
```

**`--strengths`** and **--interests** accept comma-separated values from the
taxonomies listed in the Taxonomy Reference section below. Omit them to get
the raw gap matrix without personalisation.

**`--level`** accepts `beginner`, `intermediate`, or `advanced` and shifts the
maturity bonus in the opportunity scorer.

### Step 3 — Interpret and present results

Read `outputs/<slug>-gap-report.json` and present findings in this order:

1. **Top 5 method × domain gaps** — show gap type (UNEXPLORED / UNDEREXPLORED),
   paper count, and gap score. Explain briefly *why* each gap is significant.
2. **Top 3 concept combination gaps** — concepts that are each well-studied but
   never combined.
3. **Computational bottlenecks** — list domains still citing unresolved
   computational challenges; note whether GPU or parallel methods could apply.
4. **Declining areas** — flag any domains with >40% decline in recent output;
   interpret whether this is saturation or genuine neglect.
5. **Personalised opportunities** (if `--strengths`/`--interests` provided) —
   top 5 scored opportunities with breakdown, framed as concrete research
   directions.

Present each opportunity as a one-paragraph research pitch, not just a label.
For example: "Applying Bayesian inference to credit risk is currently
underexplored (2 papers). Given your MCMC background, a natural entry point
would be a Bayesian hierarchical PD model that extends [cite nearest paper]..."

### Step 4 — Write output files

Following Feynman output conventions:

- `outputs/<slug>-gap-report.json` — raw structured output from the script
- `outputs/<slug>-gaps.md` — human-readable summary (see template below)
- `outputs/<slug>-gaps.provenance.md` — source accounting

#### `<slug>-gaps.md` template

```markdown
# Research Gap Analysis: <topic>

**Date:** <ISO date>
**Papers analysed:** <N>
**Sources:** <list>

## Top Method × Domain Gaps

| Rank | Method | Domain | Status | Papers | Score |
|------|--------|--------|--------|--------|-------|
| 1    | ...    | ...    | ...    | ...    | ...   |

## Concept Combination Gaps
...

## Computational Bottlenecks
...

## Declining Research Areas
...

## Personalised Opportunities
...

## Methodology Note
Gap scores are computed as method_popularity × domain_popularity for
unexplored pairs, normalised over the analysed corpus. Scores are
corpus-relative — they are not comparable across different paper sets.
```

---

## Taxonomy reference

The following are the recognised values for `--strengths` and `--interests`.
The script will also attempt fuzzy matching for unlisted values.

**Methods (use for `--strengths`)**

| Key | Covers |
|-----|--------|
| `bayesian` | MCMC, Gibbs, Metropolis, posterior inference |
| `machine_learning` | neural nets, deep learning, random forest, XGBoost, LSTM, transformers |
| `monte_carlo` | MC simulation, quasi-MC, variance reduction, importance sampling |
| `pde` | finite difference, finite element, PDEs |
| `fft` | fast Fourier transform, convolution methods |
| `optimization` | gradient descent, Newton methods, convex optimisation |
| `gpu_computing` | CUDA, OpenCL, parallel computing, distributed training |
| `time_series` | ARIMA, GARCH, ARCH, VAR, autoregressive models |
| `stochastic_calculus` | Itô calculus, Brownian motion, SDEs, Wiener processes |
| `numerical_integration` | quadrature, Gauss-Hermite integration |
| `regression` | GLM, logistic regression, penalised regression |

**Domains (use for `--interests`)**

| Key | Covers |
|-----|--------|
| `option_pricing` | European/American/exotic options, derivative pricing |
| `volatility_modeling` | stochastic vol, local vol, implied vol surfaces |
| `credit_risk` | PD models, CDS, credit spreads, counterparty risk |
| `portfolio` | mean-variance, asset allocation, factor models |
| `risk_management` | VaR, CVaR, expected shortfall, stress testing |
| `interest_rate` | yield curve, swap pricing, short-rate models |
| `market_microstructure` | order book, HFT, liquidity modelling |
| `structured_products` | CDO, CLO, tranche modelling, ABS |
| `commodity` | energy, oil, electricity markets |
| `insurance` | actuarial models, longevity, loss distributions |

---

## Helper script location

The analysis logic lives at `{baseDir}/qf_gap_analysis.py`.

This script is a cleaned, consolidated port of:
- `arxiv_gap_finder.py` — gap detection and scoring
- `knowledge_graph.py` — co-occurrence matrix construction

Key fixes relative to the source repo:
- Unified taxonomy (no divergence between KG import and gap finder)
- Co-occurrence update is idempotent (safe to re-run on the same corpus)
- Gap scores are stored in the output JSON rather than recomputed on each query

---

## Notes and limitations

- The taxonomy is keyword-based (title + abstract matching), so papers with
  unusual terminology may be missed. Treat gaps as hypotheses to verify, not
  definitive absences.
- arXiv pre-prints have `citation_count = 0` by default; impact scoring will
  underweight them unless enriched via Semantic Scholar first.
- SSRN papers are not automatically included. If the topic has significant
  practitioner literature on SSRN, supplement the corpus manually.
- Temporal gap analysis requires at least 3 years of data per domain; sparse
  corpora may produce no temporal findings.
