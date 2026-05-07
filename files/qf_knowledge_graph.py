#!/usr/bin/env python3
"""
qf_knowledge_graph.py — Quantitative Finance Research Knowledge Graph
Feynman skill helper for qf-knowledge-graph

Persistent SQLite graph tracking papers, authors, methods, domains,
venues, co-occurrences, and research notes across sessions.

Key fixes vs. source repo:
  - update_cooccurrences() is idempotent (recomputes from scratch,
    no double-counting on re-import)
  - Taxonomy unified with qf_gap_analysis.py
  - normalize_paper_data() handles arXiv / Semantic Scholar / aggregated
  - Non-interactive CLI (no input() prompts)

Usage:
  python3 qf_knowledge_graph.py import <papers.json> [--db PATH]
  python3 qf_knowledge_graph.py stats    [--db PATH]
  python3 qf_knowledge_graph.py gaps     [--db PATH] [--min-papers N]
  python3 qf_knowledge_graph.py search   "<query>" [--method M] [--domain D]
  python3 qf_knowledge_graph.py trending [--months N] [--db PATH]
  python3 qf_knowledge_graph.py authors  [--min-collaborations N] [--db PATH]
  python3 qf_knowledge_graph.py sources  [--db PATH]
  python3 qf_knowledge_graph.py note     <arxiv_id> "<text>" [--tags t1,t2]
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

# Import unified taxonomy from sibling module if available, else redefine
try:
    _skill_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _skill_dir)
    from qf_gap_analysis import METHODS, DOMAINS  # type: ignore
except ImportError:
    # Fallback: inline copy (keep in sync with qf_gap_analysis.py)
    METHODS = {
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
    DOMAINS = {
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

DEFAULT_DB = os.path.expanduser("~/.feynman/qf-research.db")


# ---------------------------------------------------------------------------
# Database init
# ---------------------------------------------------------------------------

def get_conn(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS papers (
        arxiv_id            TEXT PRIMARY KEY,
        title               TEXT,
        abstract            TEXT,
        published           TEXT,
        citation_count      INTEGER,
        venue               TEXT,
        pdf_url             TEXT,
        added_date          TEXT,
        source_db           TEXT,
        doi                 TEXT,
        semantic_scholar_id TEXT,
        url                 TEXT
    );

    CREATE TABLE IF NOT EXISTS authors (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE,
        paper_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS methods (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE,
        paper_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS domains (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE,
        paper_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS venues (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE,
        paper_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS paper_authors (
        paper_id  TEXT,
        author_id INTEGER,
        PRIMARY KEY (paper_id, author_id)
    );

    CREATE TABLE IF NOT EXISTS paper_methods (
        paper_id  TEXT,
        method_id INTEGER,
        PRIMARY KEY (paper_id, method_id)
    );

    CREATE TABLE IF NOT EXISTS paper_domains (
        paper_id  TEXT,
        domain_id INTEGER,
        PRIMARY KEY (paper_id, domain_id)
    );

    -- Idempotent co-occurrence: count is RECOMPUTED, not incremented.
    -- See update_cooccurrences().
    CREATE TABLE IF NOT EXISTS method_domain_cooccurrence (
        method_id INTEGER,
        domain_id INTEGER,
        count     INTEGER DEFAULT 0,
        PRIMARY KEY (method_id, domain_id)
    );

    CREATE TABLE IF NOT EXISTS author_collaborations (
        author1_id INTEGER,
        author2_id INTEGER,
        paper_count INTEGER DEFAULT 0,
        PRIMARY KEY (author1_id, author2_id)
    );

    CREATE TABLE IF NOT EXISTS research_notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id   TEXT,
        note       TEXT,
        created_at TEXT,
        tags       TEXT
    );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Paper normalisation
# ---------------------------------------------------------------------------

def _make_id(paper: dict) -> str:
    """Derive a stable unique ID for a paper."""
    if paper.get("arxiv_id"):
        return str(paper["arxiv_id"])
    if paper.get("semantic_scholar_id"):
        return str(paper["semantic_scholar_id"])
    if paper.get("doi"):
        return str(paper["doi"])
    title = paper.get("title", "")
    return "hash_" + hashlib.md5(title.encode()).hexdigest()[:16]


def normalise_paper(paper: dict) -> dict:
    authors = paper.get("authors", [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(";")]
    elif authors and isinstance(authors[0], dict):
        authors = [a.get("name", "") for a in authors]

    year_raw = paper.get("published", paper.get("year", ""))
    published = str(year_raw)[:10] if year_raw else ""

    return {
        "arxiv_id":             _make_id(paper),
        "title":                paper.get("title") or "Unknown",
        "abstract":             paper.get("abstract") or paper.get("summary") or "",
        "published":            published,
        "citation_count":       paper.get("citation_count") or 0,
        "venue":                paper.get("venue") or "Unknown",
        "pdf_url":              paper.get("pdf_url") or "",
        "source_db":            paper.get("source_db") or paper.get("source") or "unknown",
        "doi":                  paper.get("doi"),
        "semantic_scholar_id":  paper.get("semantic_scholar_id"),
        "url":                  paper.get("url"),
        "authors":              authors,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_papers(path: str, conn: sqlite3.Connection, autotag: bool = True) -> int:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw = data["papers"] if isinstance(data, dict) and "papers" in data else data
    print(f"  Found {len(raw)} papers in file")

    added = 0
    for i, paper in enumerate(raw, 1):
        p = normalise_paper(paper)
        pid = p["arxiv_id"]

        # Upsert paper
        conn.execute("""
            INSERT INTO papers
                (arxiv_id, title, abstract, published, citation_count,
                 venue, pdf_url, added_date, source_db, doi,
                 semantic_scholar_id, url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(arxiv_id) DO UPDATE SET
                citation_count = excluded.citation_count,
                venue = excluded.venue
        """, (
            pid, p["title"], p["abstract"], p["published"],
            p["citation_count"], p["venue"], p["pdf_url"],
            datetime.now().isoformat(), p["source_db"],
            p["doi"], p["semantic_scholar_id"], p["url"],
        ))

        # Authors + collaborations
        author_ids = []
        for name in p["authors"]:
            if not name:
                continue
            conn.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", (name,))
            conn.execute(
                "UPDATE authors SET paper_count = paper_count + 1 WHERE name = ?", (name,)
            )
            row = conn.execute("SELECT id FROM authors WHERE name = ?", (name,)).fetchone()
            if row:
                aid = row["id"]
                author_ids.append(aid)
                conn.execute(
                    "INSERT OR IGNORE INTO paper_authors (paper_id, author_id) VALUES (?,?)",
                    (pid, aid),
                )
        for a1, a2 in [(min(x, y), max(x, y)) for x, y in
                       [(author_ids[i], author_ids[j])
                        for i in range(len(author_ids))
                        for j in range(i+1, len(author_ids))]]:
            conn.execute("""
                INSERT INTO author_collaborations (author1_id, author2_id, paper_count)
                VALUES (?,?,1)
                ON CONFLICT(author1_id, author2_id)
                DO UPDATE SET paper_count = paper_count + 1
            """, (a1, a2))

        # Venue
        venue = p["venue"]
        conn.execute("INSERT OR IGNORE INTO venues (name) VALUES (?)", (venue,))
        conn.execute(
            "UPDATE venues SET paper_count = paper_count + 1 WHERE name = ?", (venue,)
        )

        # Auto-tag methods and domains
        if autotag:
            text = (p["title"] + " " + p["abstract"]).lower()
            for method, kws in METHODS.items():
                if any(kw in text for kw in kws):
                    conn.execute("INSERT OR IGNORE INTO methods (name) VALUES (?)", (method,))
                    conn.execute(
                        "UPDATE methods SET paper_count = paper_count + 1 WHERE name = ?",
                        (method,)
                    )
                    mid = conn.execute(
                        "SELECT id FROM methods WHERE name = ?", (method,)
                    ).fetchone()["id"]
                    conn.execute(
                        "INSERT OR IGNORE INTO paper_methods (paper_id, method_id) VALUES (?,?)",
                        (pid, mid),
                    )
            for domain, kws in DOMAINS.items():
                if any(kw in text for kw in kws):
                    conn.execute("INSERT OR IGNORE INTO domains (name) VALUES (?)", (domain,))
                    conn.execute(
                        "UPDATE domains SET paper_count = paper_count + 1 WHERE name = ?",
                        (domain,)
                    )
                    did = conn.execute(
                        "SELECT id FROM domains WHERE name = ?", (domain,)
                    ).fetchone()["id"]
                    conn.execute(
                        "INSERT OR IGNORE INTO paper_domains (paper_id, domain_id) VALUES (?,?)",
                        (pid, did),
                    )

        added += 1
        if i % 50 == 0:
            print(f"    [{i}/{len(raw)}] processed...")

    conn.commit()

    # Recompute co-occurrence from scratch (idempotent)
    _recompute_cooccurrences(conn)
    return added


def _recompute_cooccurrences(conn: sqlite3.Connection) -> None:
    """Recompute method×domain co-occurrence counts from scratch.

    This replaces the previous approach of incrementing counts on each call,
    which caused double-counting when the same papers were re-imported.
    """
    conn.execute("DELETE FROM method_domain_cooccurrence")
    conn.execute("""
        INSERT INTO method_domain_cooccurrence (method_id, domain_id, count)
        SELECT pm.method_id, pd.domain_id, COUNT(DISTINCT pm.paper_id)
        FROM paper_methods pm
        JOIN paper_domains pd ON pm.paper_id = pd.paper_id
        GROUP BY pm.method_id, pd.domain_id
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def cmd_stats(conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 70)
    print("KNOWLEDGE GRAPH STATISTICS")
    print("=" * 70)
    for label, table in [("Papers", "papers"), ("Authors", "authors"),
                          ("Methods", "methods"), ("Domains", "domains")]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {label:<12} {n}")

    total_cites = conn.execute(
        "SELECT SUM(citation_count) FROM papers WHERE citation_count IS NOT NULL"
    ).fetchone()[0] or 0
    print(f"  {'Total cites':<12} {total_cites}")

    print("\nPapers by source:")
    for row in conn.execute(
        "SELECT source_db, COUNT(*) n FROM papers GROUP BY source_db ORDER BY n DESC"
    ):
        print(f"  {row['source_db']:<30} {row['n']}")

    print("\nTop methods:")
    for row in conn.execute(
        "SELECT name, paper_count FROM methods ORDER BY paper_count DESC LIMIT 10"
    ):
        print(f"  {row['name']:<35} {row['paper_count']}")

    print("\nTop domains:")
    for row in conn.execute(
        "SELECT name, paper_count FROM domains ORDER BY paper_count DESC LIMIT 10"
    ):
        print(f"  {row['name']:<35} {row['paper_count']}")

    print("\nTop authors:")
    for row in conn.execute(
        "SELECT name, paper_count FROM authors ORDER BY paper_count DESC LIMIT 10"
    ):
        print(f"  {row['name']:<40} {row['paper_count']}")


def cmd_gaps(conn: sqlite3.Connection, min_papers: int = 5) -> None:
    methods = conn.execute(
        "SELECT id, name FROM methods WHERE paper_count >= ?", (min_papers,)
    ).fetchall()
    domains = conn.execute(
        "SELECT id, name FROM domains WHERE paper_count >= ?", (min_papers,)
    ).fetchall()

    gaps = []
    for m in methods:
        for d in domains:
            row = conn.execute(
                "SELECT count FROM method_domain_cooccurrence WHERE method_id=? AND domain_id=?",
                (m["id"], d["id"]),
            ).fetchone()
            count = row["count"] if row else 0
            if count <= 2:
                m_pop = conn.execute(
                    "SELECT paper_count FROM methods WHERE id=?", (m["id"],)
                ).fetchone()["paper_count"]
                d_pop = conn.execute(
                    "SELECT paper_count FROM domains WHERE id=?", (d["id"],)
                ).fetchone()["paper_count"]
                gaps.append({
                    "method": m["name"],
                    "domain": d["name"],
                    "count": count,
                    "gap_type": "UNEXPLORED" if count == 0 else "UNDEREXPLORED",
                    "score": m_pop * d_pop,
                })

    gaps.sort(key=lambda x: x["score"], reverse=True)
    print("\n" + "=" * 70)
    print("RESEARCH GAPS (from persistent knowledge graph)")
    print("=" * 70)
    for i, g in enumerate(gaps[:20], 1):
        method = g["method"].replace("_", " ").title()
        domain = g["domain"].replace("_", " ").title()
        print(f"\n{i:2}. {method} × {domain}")
        print(f"    {g['gap_type']} ({g['count']} papers) | score: {g['score']}")


def cmd_search(conn, query, method=None, domain=None, min_citations=0):
    sql = "SELECT DISTINCT p.arxiv_id, p.title, p.citation_count, p.venue FROM papers p"
    conditions, params = [], []
    if method:
        sql += " JOIN paper_methods pm ON p.arxiv_id = pm.paper_id"
        sql += " JOIN methods m ON pm.method_id = m.id"
        conditions.append("m.name = ?"); params.append(method)
    if domain:
        sql += " JOIN paper_domains pd ON p.arxiv_id = pd.paper_id"
        sql += " JOIN domains d ON pd.domain_id = d.id"
        conditions.append("d.name = ?"); params.append(domain)
    if query:
        conditions.append("(p.title LIKE ? OR p.abstract LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]
    if min_citations:
        conditions.append("p.citation_count >= ?"); params.append(min_citations)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY p.citation_count DESC LIMIT 50"

    rows = conn.execute(sql, params).fetchall()
    print(f"\nFound {len(rows)} papers matching '{query}':")
    for row in rows:
        print(f"\n  • {row['title']}")
        print(f"    Citations: {row['citation_count'] or 0} | Venue: {row['venue']}")
        print(f"    ID: {row['arxiv_id']}")


def cmd_trending(conn, months=12):
    rows = conn.execute("""
        SELECT m.name, COUNT(*) n
        FROM methods m
        JOIN paper_methods pm ON m.id = pm.method_id
        JOIN papers p ON pm.paper_id = p.arxiv_id
        WHERE CAST(SUBSTR(p.published, 1, 4) AS INTEGER) >=
              CAST(STRFTIME('%Y', 'now', '-' || ? || ' months') AS INTEGER)
        GROUP BY m.name ORDER BY n DESC LIMIT 20
    """, (months,)).fetchall()
    print(f"\nTrending methods (last {months} months):")
    for r in rows:
        print(f"  {r['name']:<35} {r['n']}")


def cmd_authors(conn, min_collab=2):
    rows = conn.execute("""
        SELECT a1.name, a2.name, ac.paper_count
        FROM author_collaborations ac
        JOIN authors a1 ON ac.author1_id = a1.id
        JOIN authors a2 ON ac.author2_id = a2.id
        WHERE ac.paper_count >= ?
        ORDER BY ac.paper_count DESC
        LIMIT 30
    """, (min_collab,)).fetchall()
    print(f"\nAuthor collaborations (≥{min_collab} papers):")
    for r in rows:
        print(f"  {r[0]} + {r[1]}: {r[2]} papers")


def cmd_sources(conn):
    print("\nPapers by source:")
    for row in conn.execute("""
        SELECT source_db,
               COUNT(*) n,
               AVG(citation_count) avg_cites,
               COUNT(CASE WHEN citation_count > 0 THEN 1 END) with_cites
        FROM papers
        WHERE source_db IS NOT NULL
        GROUP BY source_db ORDER BY n DESC
    """):
        pct = 100 * row["with_cites"] / row["n"] if row["n"] else 0
        print(f"  {row['source_db']:<25} {row['n']:5} papers | "
              f"avg cites: {(row['avg_cites'] or 0):6.1f} | "
              f"with cites: {pct:.0f}%")


def cmd_note(conn, arxiv_id, note, tags=""):
    conn.execute(
        "INSERT INTO research_notes (paper_id, note, created_at, tags) VALUES (?,?,?,?)",
        (arxiv_id, note, datetime.now().isoformat(), tags),
    )
    conn.commit()
    print(f"✓ Note added to {arxiv_id}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="QF Knowledge Graph — Feynman skill helper"
    )
    parser.add_argument("command",
                        choices=["import", "stats", "gaps", "search",
                                 "trending", "authors", "sources", "note"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--min-papers", type=int, default=5)
    parser.add_argument("--min-collaborations", type=int, default=2)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--method", default=None)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--min-citations", type=int, default=0)
    parser.add_argument("--tags", default="")
    parser.add_argument("--no-autotag", action="store_true")
    a = parser.parse_args()

    conn = get_conn(a.db)

    try:
        if a.command == "import":
            if not a.args:
                print("Error: provide a JSON file path", file=sys.stderr); sys.exit(1)
            n = import_papers(a.args[0], conn, autotag=not a.no_autotag)
            print(f"✓ Imported {n} papers into {a.db}")

        elif a.command == "stats":
            cmd_stats(conn)

        elif a.command == "gaps":
            cmd_gaps(conn, min_papers=a.min_papers)

        elif a.command == "search":
            if not a.args:
                print("Error: provide a query string", file=sys.stderr); sys.exit(1)
            cmd_search(conn, a.args[0], method=a.method,
                       domain=a.domain, min_citations=a.min_citations)

        elif a.command == "trending":
            cmd_trending(conn, months=a.months)

        elif a.command == "authors":
            cmd_authors(conn, min_collab=a.min_collaborations)

        elif a.command == "sources":
            cmd_sources(conn)

        elif a.command == "note":
            if len(a.args) < 2:
                print("Error: provide arxiv_id and note text", file=sys.stderr); sys.exit(1)
            cmd_note(conn, a.args[0], a.args[1], tags=a.tags)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
