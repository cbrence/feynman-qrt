---
name: qf-knowledge-graph
description: >
  Build and query a persistent SQLite knowledge graph of quantitative finance
  papers, tracking method/domain co-occurrences, author collaboration networks,
  citation trends, and venue prestige. Use this skill when the user wants to
  accumulate a research corpus over multiple sessions, track what they've read,
  query across their full paper collection, or find trending topics and author
  networks.
---

# Quantitative Finance Knowledge Graph

This skill maintains a **persistent SQLite knowledge graph** at
`~/.feynman/qf-research.db` that survives across sessions. It stores papers,
authors, methods, domains, venues, and their relationships, and supports
queries that span your entire accumulated corpus — not just the current session.

Think of it as a private research database that grows each time you run a
search or lit review.

---

## When to invoke

Trigger this skill when the user says things like:

- "add these papers to my knowledge graph"
- "import my search results into the KG"
- "show me stats on my research database"
- "what are the trending methods in my corpus"
- "which authors collaborate most in [domain]"
- "search my paper collection for [topic]"
- "show gaps in my knowledge graph"
- "what venues appear most in my corpus"

---

## Database location

The graph lives at `~/.feynman/qf-research.db` by default. This path can be
overridden with `--db <path>` on any command.

If the file does not exist, the import command creates it automatically.

---

## Commands

### `import` — Add papers to the graph

```bash
python3 {baseDir}/qf_knowledge_graph.py import \
  <papers_json> \
  [--db ~/.feynman/qf-research.db] \
  [--no-autotag]
```

Reads a JSON file (flat list or `{"papers": [...]}` wrapper) and adds all
papers to the graph. Automatically tags each paper with detected methods and
domains using the shared taxonomy. Safe to re-run — papers are upserted, not
duplicated.

**Use this after every `/lit`, `/deepresearch`, or `qrt-search` run to keep
the graph current.**

### `stats` — Graph statistics

```bash
python3 {baseDir}/qf_knowledge_graph.py stats [--db ...]
```

Prints: total papers, authors, methods, domains; papers by source; average
citations by source; top authors, methods, and domains.

### `gaps` — Find method × domain gaps in the accumulated corpus

```bash
python3 {baseDir}/qf_knowledge_graph.py gaps \
  [--min-papers 5] \
  [--db ...]
```

Finds method × domain pairs that are co-occurring in fewer than 3 papers in
your corpus. More powerful than the one-shot gap finder because it operates
over your entire accumulated collection across sessions.

`--min-papers` controls the minimum individual popularity threshold — only
methods/domains with at least N papers are included in the gap matrix.

### `search` — Full-text search across the corpus

```bash
python3 {baseDir}/qf_knowledge_graph.py search \
  "<query>" \
  [--method bayesian] \
  [--domain credit_risk] \
  [--min-citations 10] \
  [--db ...]
```

Returns papers matching the query, optionally filtered by method, domain, and
citation threshold. Results sorted by citation count descending.

### `trending` — Recent activity by method

```bash
python3 {baseDir}/qf_knowledge_graph.py trending \
  [--months 12] \
  [--db ...]
```

Shows the most active methods in papers published in the last N months.
Useful for tracking what's currently hot in your corpus.

### `authors` — Collaboration networks

```bash
python3 {baseDir}/qf_knowledge_graph.py authors \
  [--min-collaborations 2] \
  [--db ...]
```

Lists author pairs who have co-authored at least N papers in the corpus.
Useful for identifying active research groups in your interest areas.

### `sources` — Source and venue breakdown

```bash
python3 {baseDir}/qf_knowledge_graph.py sources [--db ...]
```

Breaks down papers by source database, shows venue distribution per source,
and reports cross-indexed papers (appearing in multiple sources).

### `note` — Attach a research note to a paper

```bash
python3 {baseDir}/qf_knowledge_graph.py note \
  <arxiv_id> \
  "<note text>" \
  [--tags "tag1,tag2"] \
  [--db ...]
```

Attaches a freetext note to a specific paper by its arXiv ID. Notes are
stored in the graph and retrievable via search. Use this to record personal
observations, relevance assessments, or follow-up tasks.

---

## Typical session workflow

```
# After a lit review or search run:
python3 {baseDir}/qf_knowledge_graph.py import outputs/rough-vol-lit-papers.json

# Check what's accumulated:
python3 {baseDir}/qf_knowledge_graph.py stats

# Find gaps across the full corpus:
python3 {baseDir}/qf_knowledge_graph.py gaps --min-papers 3

# Find all papers on Bayesian credit risk in the corpus:
python3 {baseDir}/qf_knowledge_graph.py search "credit risk" --method bayesian

# See what's trending in the last 6 months:
python3 {baseDir}/qf_knowledge_graph.py trending --months 6
```

---

## Integration with qf-gap-finder

The gap finder skill (`qf-gap-finder`) operates on a single paper set per run.
The knowledge graph operates across your **entire accumulated corpus**. Use
both together:

1. Run `/lit <topic>` → papers go to `outputs/<slug>-papers.json`
2. `qf-knowledge-graph import` → adds them to the persistent graph
3. `qf-knowledge-graph gaps` → gap analysis over *all* your papers, not just
   this session's
4. `qf-gap-finder` (per-run) → deeper analysis with personalisation scoring on
   the current session's corpus

The two approaches are complementary: the KG gives you cumulative coverage,
the gap finder gives you focused, session-specific analysis with opportunity
scoring.

---

## Output files

After `gaps` or `stats`, write results to:

- `outputs/<slug>-kg-gaps.md` — formatted gap table from the persistent graph
- `outputs/<slug>-kg-stats.md` — graph statistics snapshot

Use the same slug convention as the AGENTS.md file-naming rules.

---

## Schema overview

The graph tracks these entities and relationships:

```
papers ──< paper_authors >── authors
  │                            │
  └──< paper_methods >── methods   author_collaborations
  │
  └──< paper_domains >── domains
  │
  └── venues
  │
  └──< research_notes

method_domain_cooccurrence (method_id, domain_id, count)
```

All co-occurrence counts are idempotent — re-importing the same paper file
will not inflate counts.

---

## Helper script location

The graph logic lives at `{baseDir}/qf_knowledge_graph.py`.

This is a hardened port of `knowledge_graph.py` from the
`quant-research-toolkit` repo with the following fixes applied:

- `update_cooccurrences()` is now idempotent (recomputes from scratch rather
  than incrementing, preventing double-counting on re-import)
- Taxonomy is unified with `qf_gap_analysis.py` — no silent divergence
- `normalize_paper_data()` handles arXiv, Semantic Scholar, and aggregated
  formats consistently
- All CLI commands exit cleanly with a non-zero code on error

---

## Notes and limitations

- The SQLite file is local to the machine running Feynman. It is not synced
  across devices automatically. Back it up with:
  `cp ~/.feynman/qf-research.db ~/backups/qf-research-$(date +%Y%m%d).db`
- SSRN papers can be added manually by constructing the paper JSON format and
  using the `import` command directly.
- Author disambiguation is by name string only — "J. Smith" and "John Smith"
  are treated as different authors.
- The `trending` command uses `published` date from the paper metadata; arXiv
  pre-prints may have submission dates rather than publication dates.
