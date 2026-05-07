# Quantitative Finance Research Toolkit

Multi-source academic search, knowledge graph construction, and research gap
analysis for quantitative finance — with [Feynman](https://github.com/getcompanion-ai/feynman)
skill integration for AI-assisted research workflows.

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Overview

Most literature review tools tell you what exists. This toolkit tells you what
**doesn't** — and whether your skills put you in a position to fill that gap.

The core idea is a method×domain co-occurrence analysis: given a corpus of
papers, it builds a matrix of every (computational method, finance domain)
pair, identifies combinations that are sparse or absent, and scores them
against a user-supplied skill profile. The result is a ranked list of
underexplored research directions, grounded in what's actually in the
literature rather than general intuition.

The toolkit has two layers:

- **`src/qrt/`** — standalone Python CLI tools that search arXiv and Semantic
  Scholar, build a persistent SQLite knowledge graph, and run gap analysis
  locally
- **`feynman-skills/`** — skill files for the
  [Feynman](https://github.com/getcompanion-ai/feynman) AI research agent,
  integrating the gap analysis and knowledge graph as callable skills within
  Feynman's multi-agent pipeline

You can use either layer independently.

---

## Repository structure

```
quant-research-toolkit/
├── src/qrt/
│   ├── search/
│   │   └── research_aggregator.py   # Multi-source paper search
│   ├── core/
│   │   └── knowledge_graph.py       # SQLite knowledge graph
│   └── analysis/
│       └── arxiv_gap_finder.py      # Gap detection + opportunity scoring
│
├── feynman-skills/
│   ├── qf-gap-finder/
│   │   ├── SKILL.md                 # Feynman skill definition
│   │   └── qf_gap_analysis.py       # Consolidated gap analysis helper
│   └── qf-knowledge-graph/
│       ├── SKILL.md                 # Feynman skill definition
│       └── qf_knowledge_graph.py    # Hardened KG CLI helper
│
├── requirements.txt
└── setup.py
```

---

## Standalone Python tools

### Installation

```bash
git clone https://github.com/cbrence/feynman-qrt.git
cd feynman-qrt
uv pip install -r requirements.txt
```

Python 3.8+ required. No GPU or heavy dependencies — pure stdlib plus
`feedparser` for arXiv and `requests` for Semantic Scholar.

### 1. Search (`research_aggregator.py`)

Searches Semantic Scholar and arXiv (with optional Google Scholar via SerpAPI),
deduplicates across sources, and writes a combined JSON file.

```bash
python src/qrt/search/research_aggregator.py "rough volatility calibration"
```

Results are saved to `aggregated_search_<timestamp>.json` with a `papers` array
that the other tools consume directly.

Semantic Scholar and arXiv are free and require no API key. Google Scholar
requires a [SerpAPI](https://serpapi.com) key passed as `--serpapi-key` or the
`SERPAPI_KEY` environment variable.

### 2. Knowledge graph (`knowledge_graph.py`)

Builds a persistent SQLite knowledge graph from paper JSON files. The graph
accumulates across runs, so repeated searches over time build up a corpus you
can query holistically.

```bash
# Import papers
python src/qrt/core/knowledge_graph.py import aggregated_search_*.json

# Check what's accumulated
python src/qrt/core/knowledge_graph.py stats

# Find method×domain gaps in the full corpus
python src/qrt/core/knowledge_graph.py gaps --min-papers 3

# Search within the corpus
python src/qrt/core/knowledge_graph.py search "credit risk" --method bayesian

# See trending methods over the last year
python src/qrt/core/knowledge_graph.py trending --months 12

# View author collaboration networks
python src/qrt/core/knowledge_graph.py authors --min-collaborations 2
```

The database lives at `research_knowledge.db` in the working directory by
default.

### 3. Gap analysis (`arxiv_gap_finder.py`)

Runs a multi-dimensional gap analysis on a paper set and produces a structured
report. This is the core analytical piece.

```bash
python src/qrt/analysis/arxiv_gap_finder.py papers.json
```

The analysis covers four dimensions:

**Method × domain gaps** — computational methods (Bayesian, Monte Carlo, GPU,
FFT, etc.) that haven't been applied to specific finance domains (credit risk,
volatility modeling, structured products, etc.), scored by the individual
popularity of each component.

**Concept combination gaps** — pairs of concepts that each appear frequently
in the corpus but are never found in the same paper.

**Computational bottlenecks** — papers that explicitly flag unresolved
computational challenges, grouped by domain, indicating where algorithmic
contribution would be most valuable.

**Temporal gaps** — domains where publication volume has declined by 50%+
in recent years, which may indicate saturation, neglect, or an opportunity
for revival with new methods.

The tool also accepts a researcher profile for personalised scoring:

```bash
python src/qrt/analysis/arxiv_gap_finder.py papers.json \
  --strengths bayesian monte_carlo gpu_computing \
  --interests credit_risk volatility_modeling risk_management \
  --level intermediate
```

This produces a ranked list of opportunities (scored 0–10) with breakdowns
across method match, domain match, gap priority, research maturity, and
nearby citation impact.

### Taxonomy

The toolkit uses a fixed taxonomy of methods and domains. Concept detection is
keyword-based against paper titles and abstracts.

**Methods:** `bayesian`, `machine_learning`, `monte_carlo`, `pde`, `fft`,
`optimization`, `gpu_computing`, `time_series`, `stochastic_calculus`,
`numerical_integration`, `regression`

**Domains:** `option_pricing`, `volatility_modeling`, `credit_risk`,
`portfolio`, `risk_management`, `interest_rate`, `market_microstructure`,
`structured_products`, `commodity`, `insurance`

---

## Feynman skills

The `feynman-skills/` directory contains two Pi-compatible skill files that
integrate this toolkit into [Feynman](https://github.com/getcompanion-ai/feynman)'s
AI research agent pipeline. The skills are also compatible with Claude Code,
Codex CLI, and Amp.

The Feynman skills are consolidated, hardened ports of the standalone tools
with a few fixes applied:

- Unified taxonomy between the gap finder and KG (the source tools had slight
  divergence)
- Idempotent co-occurrence updates (re-importing the same papers won't inflate
  counts)
- Non-interactive CLI design (no `input()` prompts — safe to call from agent
  subprocesses)
- Gap scores persisted in the output JSON rather than recomputed on each query

### Installation

**For Feynman / pi-coding-agent:**

```bash
# User-level (available across all projects)
mkdir -p ~/.feynman/agent/skills
cp -r feynman-skills/qf-gap-finder ~/.feynman/agent/skills/
cp -r feynman-skills/qf-knowledge-graph ~/.feynman/agent/skills/
```

**For Claude Code:**

Claude Code looks one level deep for `SKILL.md` files, so the directory
structure needs to be flat under your skills folder:

```bash
mkdir -p ~/.claude/skills
cp -r feynman-skills/qf-gap-finder ~/.claude/skills/
cp -r feynman-skills/qf-knowledge-graph ~/.claude/skills/
```

**For Amp:**

```bash
mkdir -p ~/.config/amp/tools
cp -r feynman-skills/qf-gap-finder ~/.config/amp/tools/
cp -r feynman-skills/qf-knowledge-graph ~/.config/amp/tools/
```

### Usage within Feynman

Once installed, Feynman will invoke the skills automatically when requests
match their descriptions. You can also invoke them explicitly:

```
# After a lit review, run gap analysis on the output
"Run a gap analysis on the papers from the rough volatility lit review.
My strengths are bayesian and monte_carlo; I'm interested in volatility_modeling
and credit_risk."

# Build up the knowledge graph over time
"Import today's search results into the knowledge graph, then show me
the current gaps across my full corpus."
```

The skills write their outputs to Feynman's `outputs/` directory following
the project's file-naming conventions, and the knowledge graph persists at
`~/.feynman/qf-research.db` across sessions.

---

## Design notes

**Why keyword-based taxonomy rather than embeddings?**
Reproducibility and transparency. A keyword match is easy to audit, extend,
and reason about. Embedding-based concept detection would likely improve recall
on papers with unusual terminology, but at the cost of making the gap scores
harder to interpret and verify. Contributions extending the taxonomy or adding
an embedding-based fallback are welcome.

**Why SQLite for the knowledge graph?**
Zero infrastructure. The graph is a single file you can back up, copy between
machines, or inspect directly with any SQLite browser. For corpora under ~100k
papers the query performance is more than sufficient.

**Limitations worth knowing:**
- arXiv papers have `citation_count = 0` by default. Impact scoring
  underweights pre-prints unless you enrich them via Semantic Scholar's API
  (the aggregator does this automatically when Semantic Scholar is included
  as a source).
- SSRN is not searched automatically. The practitioner literature in credit
  risk and structured products lives disproportionately on SSRN; supplement
  manually if that's your area.
- Author disambiguation is by name string only. "J. Smith" and "John Smith"
  are treated as different authors.

---

## Contributing

Issues and pull requests are welcome. The most valuable contributions would be:

- Extending or refining the method/domain taxonomy
- Adding new paper sources to the aggregator
- Improving the opportunity scoring model
- Adding tests (currently none — the project is research tooling, not
  production software, but basic smoke tests would help)

---

## License

MIT. See [LICENSE](LICENSE).

---

## Citation

If this toolkit is useful for your research:

```bibtex
@software{quant_research_toolkit,
  author  = {Colin Brence},
  title   = {Quantitative Finance Research Toolkit},
  year    = {2026},
  url     = {https://github.com/cbrence/feynman-qrt}
}
```
