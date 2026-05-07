#!/usr/bin/env python3
"""
knowledge_graph.py - Build a knowledge graph from arXiv papers

Tracks relationships between:
- Papers
- Methods (Bayesian, GPU, Monte Carlo, etc.)
- Domains (Credit Risk, Options, etc.)
- Authors
- Venues
- Citations
"""

import json
import sqlite3
from datetime import datetime


class ResearchKnowledgeGraph:
    """
    Simple knowledge graph for research papers
    """

    def __init__(self, db_path="research_knowledge.db"):
        self.db_path = db_path
        self.conn = None
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for knowledge graph"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # Papers table (updated to handle multiple sources)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                arxiv_id TEXT PRIMARY KEY,
                title TEXT,
                abstract TEXT,
                published DATE,
                citation_count INTEGER,
                venue TEXT,
                pdf_url TEXT,
                added_date TIMESTAMP,
                source_db TEXT,
                doi TEXT,
                semantic_scholar_id TEXT,
                url TEXT
            )
        """)

        # Authors table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                paper_count INTEGER DEFAULT 0
            )
        """)

        # Methods table (Bayesian, GPU, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                paper_count INTEGER DEFAULT 0
            )
        """)

        # Domains table (Credit Risk, Options, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                paper_count INTEGER DEFAULT 0
            )
        """)

        # Venues table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                avg_citations REAL,
                paper_count INTEGER DEFAULT 0
            )
        """)

        # Relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_authors (
                paper_id TEXT,
                author_id INTEGER,
                FOREIGN KEY (paper_id) REFERENCES papers(arxiv_id),
                FOREIGN KEY (author_id) REFERENCES authors(id),
                PRIMARY KEY (paper_id, author_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_methods (
                paper_id TEXT,
                method_id INTEGER,
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (paper_id) REFERENCES papers(arxiv_id),
                FOREIGN KEY (method_id) REFERENCES methods(id),
                PRIMARY KEY (paper_id, method_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_domains (
                paper_id TEXT,
                domain_id INTEGER,
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (paper_id) REFERENCES papers(arxiv_id),
                FOREIGN KEY (domain_id) REFERENCES domains(id),
                PRIMARY KEY (paper_id, domain_id)
            )
        """)

        # Co-occurrence tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS method_domain_cooccurrence (
                method_id INTEGER,
                domain_id INTEGER,
                count INTEGER DEFAULT 0,
                last_seen TIMESTAMP,
                FOREIGN KEY (method_id) REFERENCES methods(id),
                FOREIGN KEY (domain_id) REFERENCES domains(id),
                PRIMARY KEY (method_id, domain_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS author_collaborations (
                author1_id INTEGER,
                author2_id INTEGER,
                paper_count INTEGER DEFAULT 0,
                FOREIGN KEY (author1_id) REFERENCES authors(id),
                FOREIGN KEY (author2_id) REFERENCES authors(id),
                PRIMARY KEY (author1_id, author2_id)
            )
        """)

        # Notes and insights
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                note TEXT,
                created_at TIMESTAMP,
                tags TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(arxiv_id)
            )
        """)

        self.conn.commit()

    def add_paper(self, paper_data):
        """
        Add a paper to the knowledge graph

        Args:
            paper_data: dict with paper information
        """
        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        # Insert paper
        cursor.execute(
            """
            INSERT OR REPLACE INTO papers 
            (arxiv_id, title, abstract, published, citation_count, venue, pdf_url, 
             added_date, source_db, doi, semantic_scholar_id, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                paper_data.get("arxiv_id"),
                paper_data.get("title"),
                paper_data.get("abstract"),
                paper_data.get("published"),
                paper_data.get("citation_count", 0),
                paper_data.get("venue", "Unknown"),
                paper_data.get("pdf_url"),
                datetime.now().isoformat(),
                paper_data.get("source_db", "unknown"),
                paper_data.get("doi"),
                paper_data.get("semantic_scholar_id"),
                paper_data.get("url"),
            ),
        )

        # Add authors
        authors = paper_data.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(";")]

        author_ids = []
        for author in authors:
            cursor.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", (author,))
            cursor.execute(
                "UPDATE authors SET paper_count = paper_count + 1 WHERE name = ?",
                (author,),
            )
            cursor.execute("SELECT id FROM authors WHERE name = ?", (author,))
            author_id = cursor.fetchone()[0]
            author_ids.append(author_id)

            # Link paper to author
            cursor.execute(
                """
                INSERT OR IGNORE INTO paper_authors (paper_id, author_id) 
                VALUES (?, ?)
            """,
                (paper_data.get("arxiv_id"), author_id),
            )

        # Track collaborations
        for i, aid1 in enumerate(author_ids):
            for aid2 in author_ids[i + 1 :]:
                if aid1 != aid2:
                    # Ensure smaller ID is first
                    a1, a2 = min(aid1, aid2), max(aid1, aid2)
                    cursor.execute(
                        """
                        INSERT INTO author_collaborations (author1_id, author2_id, paper_count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(author1_id, author2_id) 
                        DO UPDATE SET paper_count = paper_count + 1
                    """,
                        (a1, a2),
                    )

        # Add venue
        venue = paper_data.get("venue", "arXiv only")
        cursor.execute("INSERT OR IGNORE INTO venues (name) VALUES (?)", (venue,))
        cursor.execute(
            "UPDATE venues SET paper_count = paper_count + 1 WHERE name = ?", (venue,)
        )

        self.conn.commit()

    def add_methods_to_paper(self, arxiv_id, methods):
        """
        Tag a paper with methods it uses

        Args:
            arxiv_id: arXiv ID
            methods: list of method names
        """
        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        for method in methods:
            # Add method if doesn't exist
            cursor.execute("INSERT OR IGNORE INTO methods (name) VALUES (?)", (method,))
            cursor.execute(
                "UPDATE methods SET paper_count = paper_count + 1 WHERE name = ?",
                (method,),
            )

            # Get method ID
            cursor.execute("SELECT id FROM methods WHERE name = ?", (method,))
            method_id = cursor.fetchone()[0]

            # Link to paper
            cursor.execute(
                """
                INSERT OR IGNORE INTO paper_methods (paper_id, method_id)
                VALUES (?, ?)
            """,
                (arxiv_id, method_id),
            )

        self.conn.commit()

    def add_domains_to_paper(self, arxiv_id, domains):
        """
        Tag a paper with domains it covers

        Args:
            arxiv_id: arXiv ID
            domains: list of domain names
        """
        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        for domain in domains:
            # Add domain if doesn't exist
            cursor.execute("INSERT OR IGNORE INTO domains (name) VALUES (?)", (domain,))
            cursor.execute(
                "UPDATE domains SET paper_count = paper_count + 1 WHERE name = ?",
                (domain,),
            )

            # Get domain ID
            cursor.execute("SELECT id FROM domains WHERE name = ?", (domain,))
            domain_id = cursor.fetchone()[0]

            # Link to paper
            cursor.execute(
                """
                INSERT OR IGNORE INTO paper_domains (paper_id, domain_id)
                VALUES (?, ?)
            """,
                (arxiv_id, domain_id),
            )

        self.conn.commit()

    def update_cooccurrences(self):
        """Update method-domain co-occurrence matrix"""
        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        # Get all papers with their methods and domains
        cursor.execute("""
            SELECT DISTINCT pm.method_id, pd.domain_id
            FROM paper_methods pm
            JOIN paper_domains pd ON pm.paper_id = pd.paper_id
        """)

        for method_id, domain_id in cursor.fetchall():
            cursor.execute(
                """
                INSERT INTO method_domain_cooccurrence (method_id, domain_id, count, last_seen)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(method_id, domain_id)
                DO UPDATE SET count = count + 1, last_seen = ?
            """,
                (
                    method_id,
                    domain_id,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )

        self.conn.commit()

    def find_gaps(self, min_papers=5):
        """
        Find method-domain gaps (combinations with few papers)

        Returns:
            List of (method, domain, count) tuples
        """
        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        # Get all methods and domains with enough papers
        cursor.execute(
            "SELECT id, name FROM methods WHERE paper_count >= ?", (min_papers,)
        )
        methods = cursor.fetchall()

        cursor.execute(
            "SELECT id, name FROM domains WHERE paper_count >= ?", (min_papers,)
        )
        domains = cursor.fetchall()

        gaps = []

        for method_id, method_name in methods:
            for domain_id, domain_name in domains:
                # Check co-occurrence
                cursor.execute(
                    """
                    SELECT count FROM method_domain_cooccurrence
                    WHERE method_id = ? AND domain_id = ?
                """,
                    (method_id, domain_id),
                )

                result = cursor.fetchone()
                count = result[0] if result else 0

                if count <= 2:  # Gap threshold
                    gaps.append(
                        {
                            "method": method_name,
                            "domain": domain_name,
                            "count": count,
                            "gap_type": "UNEXPLORED" if count == 0 else "UNDEREXPLORED",
                        }
                    )

        # Sort by potential (both popular separately but rare together)
        cursor = self.conn.cursor()
        for gap in gaps:
            cursor.execute(
                "SELECT paper_count FROM methods WHERE name = ?", (gap["method"],)
            )
            method_pop = cursor.fetchone()[0]
            cursor.execute(
                "SELECT paper_count FROM domains WHERE name = ?", (gap["domain"],)
            )
            domain_pop = cursor.fetchone()[0]
            gap["score"] = method_pop * domain_pop

        return sorted(gaps, key=lambda x: x["score"], reverse=True)

    def find_author_networks(self, min_collaborations=2):
        """Find research collaboration networks"""

        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT a1.name, a2.name, ac.paper_count
            FROM author_collaborations ac
            JOIN authors a1 ON ac.author1_id = a1.id
            JOIN authors a2 ON ac.author2_id = a2.id
            WHERE ac.paper_count >= ?
            ORDER BY ac.paper_count DESC
        """,
            (min_collaborations,),
        )

        return cursor.fetchall()

    def get_trending_topics(self, months=12):
        """
        Identify trending topics based on recent publications
        """
        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        # Get recent methods
        cursor.execute(
            """
            SELECT m.name, COUNT(*) as count
            FROM methods m
            JOIN paper_methods pm ON m.id = pm.method_id
            JOIN papers p ON pm.paper_id = p.arxiv_id
            WHERE p.published >= date('now', '-' || ? || ' months')
            GROUP BY m.name
            ORDER BY count DESC
            LIMIT 20
        """,
            (months,),
        )

        return cursor.fetchall()

    def add_note(self, arxiv_id, note, tags=None):
        """Add a research note to a paper"""

        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO research_notes (paper_id, note, created_at, tags)
            VALUES (?, ?, ?, ?)
        """,
            (arxiv_id, note, datetime.now().isoformat(), tags or ""),
        )

        self.conn.commit()

    def search_papers(self, query, method=None, domain=None, min_citations=0):
        """
        Search papers in the knowledge graph

        Args:
            query: Text to search in title/abstract
            method: Filter by method
            domain: Filter by domain
            min_citations: Minimum citation count
        """

        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        sql = "SELECT DISTINCT p.arxiv_id, p.title, p.citation_count, p.venue FROM papers p"
        conditions = []
        params = []

        if method:
            sql += " JOIN paper_methods pm ON p.arxiv_id = pm.paper_id"
            sql += " JOIN methods m ON pm.method_id = m.id"
            conditions.append("m.name = ?")
            params.append(method)

        if domain:
            sql += " JOIN paper_domains pd ON p.arxiv_id = pd.paper_id"
            sql += " JOIN domains d ON pd.domain_id = d.id"
            conditions.append("d.name = ?")
            params.append(domain)

        if query:
            conditions.append("(p.title LIKE ? OR p.abstract LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        if min_citations > 0:
            conditions.append("p.citation_count >= ?")
            params.append(min_citations)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY p.citation_count DESC LIMIT 50"

        cursor.execute(sql, params)
        return cursor.fetchall()

    def export_statistics(self):
        """Export knowledge graph statistics"""
        if not self.conn:
            raise RuntimeError("Database connection not initialized")
        cursor = self.conn.cursor()

        stats = {}

        # Papers
        cursor.execute("SELECT COUNT(*) FROM papers")
        stats["total_papers"] = cursor.fetchone()[0]

        # Papers by source
        cursor.execute("""
            SELECT source_db, COUNT(*) 
            FROM papers 
            GROUP BY source_db
        """)
        stats["papers_by_source"] = dict(cursor.fetchall())

        # Authors
        cursor.execute("SELECT COUNT(*) FROM authors")
        stats["total_authors"] = cursor.fetchone()[0]

        # Methods
        cursor.execute("SELECT COUNT(*) FROM methods")
        stats["total_methods"] = cursor.fetchone()[0]

        # Domains
        cursor.execute("SELECT COUNT(*) FROM domains")
        stats["total_domains"] = cursor.fetchone()[0]

        # Citations
        cursor.execute(
            "SELECT SUM(citation_count) FROM papers WHERE citation_count IS NOT NULL"
        )
        result = cursor.fetchone()[0]
        stats["total_citations"] = result if result else 0

        # Average citations by source
        cursor.execute("""
            SELECT source_db, AVG(citation_count)
            FROM papers
            WHERE citation_count IS NOT NULL
            GROUP BY source_db
        """)
        stats["avg_citations_by_source"] = dict(cursor.fetchall())

        # Top authors
        cursor.execute(
            "SELECT name, paper_count FROM authors ORDER BY paper_count DESC LIMIT 10"
        )
        stats["top_authors"] = cursor.fetchall()

        # Top methods
        cursor.execute(
            "SELECT name, paper_count FROM methods ORDER BY paper_count DESC LIMIT 10"
        )
        stats["top_methods"] = cursor.fetchall()

        # Top domains
        cursor.execute(
            "SELECT name, paper_count FROM domains ORDER BY paper_count DESC LIMIT 10"
        )
        stats["top_domains"] = cursor.fetchall()

        return stats

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def analyze_sources(self):
    """Analyze paper distribution by source database"""
    cursor = self.conn.cursor()

    print("\n" + "=" * 80)
    print("SOURCE ANALYSIS")
    print("=" * 80)

    # Papers by source
    cursor.execute("""
            SELECT source_db, COUNT(*) as count, 
                   AVG(citation_count) as avg_citations,
                   COUNT(CASE WHEN citation_count > 0 THEN 1 END) as with_citations
            FROM papers
            WHERE source_db IS NOT NULL
            GROUP BY source_db
            ORDER BY count DESC
        """)

    print("\nPapers by Source:")
    print(
        f"{'Source':<25} | {'Count':>6} | {'Avg Citations':>13} | {'With Citations':>15}"
    )
    print("-" * 80)

    for source, count, avg_cites, with_cites in cursor.fetchall():
        avg_cites = avg_cites or 0
        pct_with_cites = 100 * with_cites / count if count > 0 else 0
        print(
            f"{source:<25} | {count:>6} | {avg_cites:>13.1f} | {with_cites:>6} ({pct_with_cites:>5.1f}%)"
        )

    # Papers with multiple IDs (cross-indexed)
    cursor.execute("""
            SELECT COUNT(*) FROM papers
            WHERE arxiv_id IS NOT NULL 
            AND semantic_scholar_id IS NOT NULL
        """)
    cross_indexed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM papers")
    total = cursor.fetchone()[0]

    print(
        f"\nCross-indexed papers: {cross_indexed} ({100 * cross_indexed / total:.1f}%)"
    )
    print("(Papers appearing in multiple databases)")

    # Venue distribution by source
    print("\n" + "-" * 80)
    print("TOP VENUES BY SOURCE:")
    print("-" * 80)

    cursor.execute("""
            SELECT source_db, venue, COUNT(*) as count
            FROM papers
            WHERE source_db IS NOT NULL AND venue != 'Unknown'
            GROUP BY source_db, venue
            ORDER BY source_db, count DESC
        """)

    by_source = {}
    for source, venue, count in cursor.fetchall():
        if source not in by_source:
            by_source[source] = []
        by_source[source].append((venue, count))

    for source, venues in by_source.items():
        print(f"\n{source}:")
        for venue, count in venues[:5]:  # Top 5 per source
            print(f"  {venue[:55]:55} | {count:3} papers")


def import_arxiv_data(json_file, kg, auto_tag=True):
    """
    Import papers into knowledge graph
    Handles both arXiv format and aggregated search format

    Args:
        json_file: JSON file from arxiv_search.py or research_aggregator.py
        kg: ResearchKnowledgeGraph instance
        auto_tag: Automatically detect methods and domains
    """
    print(f"Importing data from: {json_file}")

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Detect format
    if isinstance(data, dict) and "papers" in data:
        papers = data["papers"]
        source_type = data.get("sources", ["arxiv"])  # May be list of sources
        print(f"Format: Structured (sources: {source_type})")
    elif isinstance(data, list):
        papers = data
        source_type = ["unknown"]
        print("Format: List")
    else:
        print("Unknown format. Exiting.")
        return

    print(f"Found {len(papers)} papers to import")

    # Method keywords (from gap finder taxonomy)
    METHOD_KEYWORDS = {
        "bayesian": ["bayesian", "mcmc", "metropolis", "gibbs", "posterior", "prior"],
        "machine_learning": [
            "machine learning",
            "neural network",
            "deep learning",
            "random forest",
            "gradient boosting",
            "xgboost",
        ],
        "monte_carlo": [
            "monte carlo",
            "quasi monte carlo",
            "variance reduction",
            "importance sampling",
        ],
        "pde": ["pde", "finite difference", "finite element", "partial differential"],
        "fft": ["fft", "fast fourier", "fourier transform"],
        "optimization": [
            "optimization",
            "gradient descent",
            "newton method",
            "convex optimization",
        ],
        "gpu_computing": ["gpu", "cuda", "parallel", "acceleration", "opencl"],
        "time_series": ["time series", "arima", "garch", "arch", "var model"],
        "numerical_integration": [
            "numerical integration",
            "quadrature",
            "gauss hermite",
        ],
        "regression": ["regression", "linear regression", "logistic regression", "glm"],
        "stochastic_calculus": [
            "stochastic calculus",
            "ito",
            "brownian motion",
            "wiener process",
        ],
    }

    DOMAIN_KEYWORDS = {
        "option_pricing": [
            "option",
            "derivative pricing",
            "european",
            "american",
            "asian option",
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
            "counterparty risk",
        ],
        "portfolio": [
            "portfolio",
            "asset allocation",
            "mean variance",
            "portfolio optimization",
        ],
        "risk_management": [
            "var",
            "value at risk",
            "cvar",
            "expected shortfall",
            "risk measure",
        ],
        "interest_rate": [
            "interest rate",
            "yield curve",
            "swap",
            "bond pricing",
            "libor",
        ],
        "market_microstructure": [
            "market microstructure",
            "order book",
            "limit order",
            "high frequency",
        ],
        "structured_products": ["structured product", "cdo", "clo", "tranche", "abs"],
        "commodity": ["commodity", "energy", "oil", "natural gas"],
        "insurance": ["insurance", "actuarial", "loss distribution"],
    }

    for i, paper in enumerate(papers, 1):
        print(f"[{i}/{len(papers)}] Importing: {paper.get('title', 'Unknown')[:60]}...")

        # Normalize paper data (handle different formats)
        normalized_paper = normalize_paper_data(paper)

        # Add paper to knowledge graph
        kg.add_paper(normalized_paper)

        if auto_tag:
            # Detect methods
            text = (
                (normalized_paper.get("title") or "")
                + " "
                + (normalized_paper.get("abstract") or "")
            ).lower()

            detected_methods = []
            for method, keywords in METHOD_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    detected_methods.append(method)

            if detected_methods:
                kg.add_methods_to_paper(
                    normalized_paper.get("arxiv_id")
                    or normalized_paper.get("semantic_scholar_id")
                    or str(i),
                    detected_methods,
                )

            # Detect domains
            detected_domains = []
            for domain, keywords in DOMAIN_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    detected_domains.append(domain)

            if detected_domains:
                kg.add_domains_to_paper(
                    normalized_paper.get("arxiv_id")
                    or normalized_paper.get("semantic_scholar_id")
                    or str(i),
                    detected_domains,
                )

    # Update co-occurrences
    print("\nUpdating co-occurrence matrix...")
    kg.update_cooccurrences()

    print("✓ Import complete!")


def normalize_paper_data(paper):
    """
    Normalize paper data from different sources into consistent format

    Handles:
    - arXiv format
    - Semantic Scholar format
    - Aggregated format
    """
    # Detect source and normalize
    source_db = paper.get("source_db", paper.get("source", "unknown"))

    # Create base normalized structure
    normalized = {
        "title": paper.get("title") or "Unknown",
        "abstract": paper.get("abstract") or paper.get("summary") or "",
        "published": paper.get("published") or paper.get("year") or "",
        "citation_count": paper.get("citation_count") or 0,
        "venue": paper.get("venue") or "Unknown",
        "pdf_url": paper.get("pdf_url") or "",
        "source_db": source_db,
    }

    # Handle authors (may be list of strings or list of dicts)
    authors = paper.get("authors", [])
    if authors:
        if isinstance(authors[0], dict):
            # Format: [{'name': 'John Doe'}, ...]
            normalized["authors"] = [a.get("name", str(a)) for a in authors]
        elif isinstance(authors[0], str):
            # Format: ['John Doe', ...]
            normalized["authors"] = authors
        else:
            # Single string or other format
            if isinstance(authors, str):
                normalized["authors"] = [a.strip() for a in authors.split(";")]
            else:
                normalized["authors"] = [str(authors)]
    else:
        normalized["authors"] = []

    # Handle IDs (different sources use different ID schemes)
    if paper.get("arxiv_id"):
        normalized["arxiv_id"] = paper["arxiv_id"]
    elif paper.get("semantic_scholar_id"):
        normalized["arxiv_id"] = paper["semantic_scholar_id"]
    elif paper.get("doi"):
        normalized["arxiv_id"] = paper["doi"]
    else:
        # Generate a unique ID
        import hashlib

        title_hash = hashlib.md5(paper.get("title", "").encode()).hexdigest()[:12]
        normalized["arxiv_id"] = f"custom_{title_hash}"

    # Preserve additional metadata
    if paper.get("doi"):
        normalized["doi"] = paper["doi"]
    if paper.get("semantic_scholar_id"):
        normalized["semantic_scholar_id"] = paper["semantic_scholar_id"]
    if paper.get("venue_details"):
        normalized["venue_details"] = paper["venue_details"]
    if paper.get("url"):
        normalized["url"] = paper["url"]

    return normalized


def main():
    """Main CLI interface"""
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python knowledge_graph.py import <arxiv_json_file>")
        print("  python knowledge_graph.py stats")
        print("  python knowledge_graph.py sources")
        print("  python knowledge_graph.py gaps")
        print("  python knowledge_graph.py search <query>")
        print("  python knowledge_graph.py authors")
        print("  python knowledge_graph.py trending")
        sys.exit(1)

    command = sys.argv[1]
    kg = ResearchKnowledgeGraph()

    try:
        if command == "import":
            if len(sys.argv) < 3:
                print("Usage: python knowledge_graph.py import <json_file>")
                sys.exit(1)
            import_arxiv_data(sys.argv[2], kg)

        elif command == "stats":
            stats = kg.export_statistics()
            print("\n" + "=" * 80)
            print("KNOWLEDGE GRAPH STATISTICS")
            print("=" * 80)
            print(f"\nTotal papers: {stats['total_papers']}")
            print(f"Total authors: {stats['total_authors']}")
            print(f"Total methods: {stats['total_methods']}")
            print(f"Total domains: {stats['total_domains']}")
            print(f"Total citations: {stats['total_citations']}")

            print("\nPapers by Source:")
            for source, count in stats["papers_by_source"].items():
                print(f"  {source:25} | {count:4} papers")

            print("\nAverage Citations by Source:")
            for source, avg in stats["avg_citations_by_source"].items():
                print(f"  {source:25} | {avg:6.1f} citations")

            print("\nTop Authors:")
            for name, count in stats["top_authors"]:
                print(f"  {name:40} | {count:3} papers")

            print("\nTop Methods:")
            for name, count in stats["top_methods"]:
                print(f"  {name:40} | {count:3} papers")

            print("\nTop Domains:")
            for name, count in stats["top_domains"]:
                print(f"  {name:40} | {count:3} papers")

        elif command == "sources":
            kg.analyze_sources()

        elif command == "gaps":
            gaps = kg.find_gaps(min_papers=3)
            print("\n" + "=" * 80)
            print("RESEARCH GAPS")
            print("=" * 80)
            for i, gap in enumerate(gaps[:20], 1):
                print(
                    f"\n{i}. {gap['method'].replace('_', ' ').title()} × "
                    f"{gap['domain'].replace('_', ' ').title()}"
                )
                print(f"   Status: {gap['gap_type']} ({gap['count']} papers)")
                print(f"   Score: {gap['score']}")

        elif command == "search":
            if len(sys.argv) < 3:
                print("Usage: python knowledge_graph.py search <query>")
                sys.exit(1)
            query = sys.argv[2]
            results = kg.search_papers(query)
            print(f"\nFound {len(results)} papers matching '{query}':")
            for arxiv_id, title, citations, venue in results:
                print(f"\n• {title}")
                print(f"  Citations: {citations or 0} | Venue: {venue}")
                print(f"  arXiv: {arxiv_id}")

        elif command == "authors":
            networks = kg.find_author_networks(min_collaborations=2)
            print("\n" + "=" * 80)
            print("AUTHOR COLLABORATION NETWORKS")
            print("=" * 80)
            for author1, author2, count in networks[:20]:
                print(f"{author1} ↔ {author2}: {count} papers")

        elif command == "trending":
            topics = kg.get_trending_topics(months=12)
            print("\n" + "=" * 80)
            print("TRENDING TOPICS (Last 12 months)")
            print("=" * 80)
            for topic, count in topics:
                print(f"{topic:40} | {count:3} papers")

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    finally:
        kg.close()


if __name__ == "__main__":
    main()
