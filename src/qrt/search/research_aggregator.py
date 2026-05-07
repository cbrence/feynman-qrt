#!/usr/bin/env python3
"""
research_aggregator.py - Search multiple academic databases

Searches:
- Semantic Scholar (free, comprehensive)
- arXiv (pre-prints)
- SSRN (finance-specific)
- Google Scholar (via serpapi or scraping)

Combines results with deduplication and enrichment.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime

import feedparser


class ResearchAggregator:
    """
    Multi-source academic paper search
    """

    def __init__(self):
        self.papers = []
        self.seen_titles = set()  # For deduplication
        self.seen_dois = set()

    def normalize_title(self, title):
        """Normalize title for deduplication"""
        # Remove special chars, lowercase, remove extra spaces
        import re

        normalized = re.sub(r"[^a-z0-9\s]", "", title.lower())
        normalized = " ".join(normalized.split())
        return normalized

    def add_paper(self, paper_data, source):
        """Add paper with deduplication"""
        title = paper_data.get("title", "")
        doi = paper_data.get("doi")

        # Check duplicates
        norm_title = self.normalize_title(title)

        if norm_title in self.seen_titles:
            return False  # Duplicate

        if doi and doi in self.seen_dois:
            return False  # Duplicate

        # Add paper
        paper_data["source"] = source
        paper_data["added_at"] = datetime.now().isoformat()
        self.papers.append(paper_data)

        self.seen_titles.add(norm_title)
        if doi:
            self.seen_dois.add(doi)

        return True

    def search_semantic_scholar(self, query, limit=100):
        """
        Search Semantic Scholar API

        Docs: https://api.semanticscholar.org/api-docs/graph
        """
        print(f"\n{'=' * 80}")
        print("Searching Semantic Scholar")
        print(f"{'=' * 80}")

        base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

        # Semantic Scholar uses different query syntax
        params = {
            "query": query,
            "limit": min(limit, 100),  # Max 100 per request
            "fields": "paperId,title,abstract,authors,year,citationCount,venue,publicationVenue,externalIds,url,openAccessPdf",
        }

        all_papers = []
        offset = 0

        while len(all_papers) < limit:
            params["offset"] = offset
            url = base_url + "?" + urllib.parse.urlencode(params)

            try:
                print(
                    f"  Fetching papers {offset + 1} to {offset + params['limit']}...",
                    end="",
                    flush=True,
                )

                request = urllib.request.Request(url)
                request.add_header("User-Agent", "Mozilla/5.0 (Research Tool)")

                response = urllib.request.urlopen(request, timeout=30)
                data = json.loads(response.read().decode("utf-8"))

                papers = data.get("data", [])

                if not papers:
                    print(" No more results.")
                    break

                for paper in papers:
                    # Extract and normalize data
                    paper_data = {
                        "title": paper.get("title"),
                        "abstract": paper.get("abstract"),
                        "authors": [a.get("name") for a in paper.get("authors", [])],
                        "year": paper.get("year"),
                        "citation_count": paper.get("citationCount", 0),
                        "venue": paper.get("venue", "Unknown"),
                        "venue_details": paper.get("publicationVenue", {}),
                        "doi": paper.get("externalIds", {}).get("DOI"),
                        "arxiv_id": paper.get("externalIds", {}).get("ArXiv"),
                        "semantic_scholar_id": paper.get("paperId"),
                        "url": paper.get("url"),
                        "pdf_url": paper.get("openAccessPdf", {}).get("url")
                        if paper.get("openAccessPdf")
                        else None,
                        "source_db": "Semantic Scholar",
                    }

                    if self.add_paper(paper_data, "semantic_scholar"):
                        all_papers.append(paper_data)

                print(f" ✓ Got {len(papers)} (total: {len(all_papers)} unique)")

                # Check if we've reached the end
                if len(papers) < params["limit"]:
                    break

                offset += params["limit"]

                # Rate limiting
                time.sleep(1)

            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(" Rate limited. Waiting 5 seconds...")
                    time.sleep(5)
                    continue
                else:
                    print(f" HTTP Error {e.code}")
                    break
            except Exception as e:
                print(f" Error: {e}")
                break

        print(f"\n✓ Semantic Scholar: {len(all_papers)} papers")
        return all_papers

    def search_arxiv(self, query, limit=200):
        """
        Search arXiv (reusing existing functionality)
        """
        print(f"\n{'=' * 80}")
        print("Searching arXiv")
        print(f"{'=' * 80}")

        base_url = "http://export.arxiv.org/api/query?"

        all_papers = []
        start = 0
        batch_size = 100

        while len(all_papers) < limit:
            params = {
                "search_query": query,
                "start": start,
                "max_results": min(batch_size, limit - len(all_papers)),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            try:
                print(
                    f"  Fetching papers {start + 1} to {start + params['max_results']}...",
                    end="",
                    flush=True,
                )

                url = base_url + urllib.parse.urlencode(params)
                response = urllib.request.urlopen(url, timeout=30).read()
                feed = feedparser.parse(response)

                if not feed.entries:
                    print(" No more results.")
                    break

                for entry in feed.entries:
                    # Handle id safely - it may be a list
                    arxiv_id = entry.id[0] if isinstance(entry.id, list) else entry.id

                    paper_data = {
                        "title": entry.title,
                        "abstract": entry.summary,
                        "authors": [author.name for author in entry.authors],
                        "year": entry.published.split("-")[0],
                        "citation_count": 0,  # arXiv doesn't provide this
                        "venue": "arXiv (pre-print)",
                        "venue_details": {},
                        "doi": entry.get("arxiv_doi"),
                        "arxiv_id": arxiv_id.split("/abs/")[-1],
                        "semantic_scholar_id": None,
                        "url": arxiv_id,
                        "pdf_url": arxiv_id.replace("/abs/", "/pdf/"),
                        "source_db": "arXiv",
                    }

                    if self.add_paper(paper_data, "arxiv"):
                        all_papers.append(paper_data)

                print(f" ✓ Got {len(feed.entries)} (total: {len(all_papers)} unique)")

                if len(feed.entries) < batch_size:
                    break

                start += batch_size
                time.sleep(3)  # arXiv rate limit

            except Exception as e:
                print(f" Error: {e}")
                break

        print(f"\n✓ arXiv: {len(all_papers)} papers")
        return all_papers

    def search_ssrn(self, query, limit=100):
        """
        Search SSRN (Social Science Research Network)

        Note: SSRN doesn't have a public API, but we can scrape search results
        or use their RSS feeds for specific topics.

        This is a placeholder - full implementation requires web scraping
        """
        print(f"\n{'=' * 80}")
        print("Searching SSRN")
        print(f"{'=' * 80}")

        print("⚠ SSRN requires web scraping or manual access")
        print("  Consider using Semantic Scholar instead (it indexes SSRN papers)")

        # SSRN search URL format:
        # https://papers.ssrn.com/sol3/results.cfm?npage=1&q=YOUR_QUERY

        # For now, return empty
        return []

    def search_google_scholar(self, query, limit=100, api_key=None):
        """
        Search Google Scholar

        Options:
        1. Use SerpAPI (paid, reliable): https://serpapi.com/
        2. Use scholarly library (free, but fragile): pip install scholarly
        3. Web scraping (against ToS, not recommended)

        This implementation uses SerpAPI if you have a key.
        """
        print(f"\n{'=' * 80}")
        print("Searching Google Scholar")
        print(f"{'=' * 80}")

        if not api_key:
            print("⚠ Google Scholar requires SerpAPI key")
            print("  Get free key at: https://serpapi.com/users/sign_up")
            print("  Then set: export SERPAPI_KEY='your_key'")
            print("  Or pass as argument: api_key='your_key'")
            return []

        # SerpAPI implementation
        base_url = "https://serpapi.com/search"

        all_papers = []
        start = 0

        while len(all_papers) < limit:
            params = {
                "engine": "google_scholar",
                "q": query,
                "api_key": api_key,
                "start": start,
                "num": 20,  # Results per page
            }

            try:
                print(
                    f"  Fetching papers {start + 1} to {start + 20}...",
                    end="",
                    flush=True,
                )

                url = base_url + "?" + urllib.parse.urlencode(params)
                response = urllib.request.urlopen(url, timeout=30)
                data = json.loads(response.read().decode("utf-8"))

                results = data.get("organic_results", [])

                if not results:
                    print(" No more results.")
                    break

                for result in results:
                    paper_data = {
                        "title": result.get("title"),
                        "abstract": result.get("snippet"),
                        "authors": [
                            result.get("publication_info", {}).get("authors", [])
                        ],
                        "year": result.get("publication_info", {})
                        .get("summary", "")
                        .split(",")[-1]
                        .strip(),
                        "citation_count": result.get("inline_links", {})
                        .get("cited_by", {})
                        .get("total", 0),
                        "venue": result.get("publication_info", {}).get("summary", ""),
                        "venue_details": {},
                        "doi": None,  # Google Scholar doesn't always provide
                        "arxiv_id": None,
                        "semantic_scholar_id": None,
                        "url": result.get("link"),
                        "pdf_url": result.get("resources", [{}])[0].get("link")
                        if result.get("resources")
                        else None,
                        "source_db": "Google Scholar",
                    }

                    if self.add_paper(paper_data, "google_scholar"):
                        all_papers.append(paper_data)

                print(f" ✓ Got {len(results)} (total: {len(all_papers)} unique)")

                start += 20
                time.sleep(2)  # Be polite

            except Exception as e:
                print(f" Error: {e}")
                break

        print(f"\n✓ Google Scholar: {len(all_papers)} papers")
        return all_papers

    def aggregate_search(
        self,
        query,
        sources=["semantic_scholar", "arxiv"],
        limit_per_source=100,
        serpapi_key=None,
    ):
        """
        Search multiple sources and combine results

        Args:
            query: Search query
            sources: List of sources to search
            limit_per_source: Max papers per source
            serpapi_key: API key for Google Scholar (optional)
        """
        print("=" * 80)
        print("MULTI-SOURCE RESEARCH AGGREGATOR")
        print("=" * 80)
        print(f"\nQuery: {query}")
        print(f"Sources: {', '.join(sources)}")
        print(f"Limit per source: {limit_per_source}")

        results_by_source = {}

        if "semantic_scholar" in sources:
            results_by_source["semantic_scholar"] = self.search_semantic_scholar(
                query, limit_per_source
            )

        if "arxiv" in sources:
            results_by_source["arxiv"] = self.search_arxiv(query, limit_per_source)

        if "google_scholar" in sources:
            results_by_source["google_scholar"] = self.search_google_scholar(
                query, limit_per_source, serpapi_key
            )

        if "ssrn" in sources:
            results_by_source["ssrn"] = self.search_ssrn(query, limit_per_source)

        # Summary
        print("\n" + "=" * 80)
        print("AGGREGATION SUMMARY")
        print("=" * 80)

        total = len(self.papers)
        print(f"\nTotal unique papers: {total}")

        print("\nBy source:")
        for source, papers in results_by_source.items():
            print(f"  {source:20} | {len(papers):4} papers")

        # Overlap analysis
        papers_with_doi = sum(1 for p in self.papers if p.get("doi"))
        papers_with_citations = sum(
            1 for p in self.papers if p.get("citation_count", 0) > 0
        )

        print("\nQuality indicators:")
        print(
            f"  Papers with DOI: {papers_with_doi} ({100 * papers_with_doi / total:.1f}%)"
        )
        print(
            f"  Papers with citations: {papers_with_citations} ({100 * papers_with_citations / total:.1f}%)"
        )

        # Top cited
        top_cited = sorted(
            self.papers, key=lambda x: x.get("citation_count", 0), reverse=True
        )[:10]

        print("\nTop 10 most cited:")
        for i, paper in enumerate(top_cited, 1):
            citations = paper.get("citation_count", 0)
            print(f"  {i:2}. [{citations:4} cites] {paper['title'][:60]}...")

        return self.papers

    def save_results(self, filename=None):
        """Save aggregated results"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"aggregated_search_{timestamp}.json"

        data = {
            "search_date": datetime.now().isoformat(),
            "num_papers": len(self.papers),
            "sources": list(set(p["source"] for p in self.papers)),
            "papers": self.papers,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Saved {len(self.papers)} papers to: {filename}")
        return filename

    def export_by_source(self):
        """Export separate files for each source"""
        by_source = defaultdict(list)

        for paper in self.papers:
            by_source[paper["source"]].append(paper)

        files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for source, papers in by_source.items():
            filename = f"{source}_{timestamp}.json"

            data = {
                "source": source,
                "search_date": datetime.now().isoformat(),
                "num_papers": len(papers),
                "papers": papers,
            }

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            files.append(filename)
            print(f"✓ {source}: {len(papers)} papers → {filename}")

        return files


def main():
    """Main CLI interface"""
    import os
    import sys

    print("\n" + "=" * 80)
    print("Research Aggregator - Multi-Source Paper Search")
    print("=" * 80)

    # Get query
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        print("\nExample queries:")
        print("  GPU acceleration finance")
        print("  rough volatility calibration")
        print("  Bayesian credit risk")
        query = input("\nEnter your query: ").strip()

    if not query:
        print("No query provided. Exiting.")
        sys.exit(1)

    # Select sources
    print("\nAvailable sources:")
    print("  1. Semantic Scholar (free, comprehensive, published papers)")
    print("  2. arXiv (free, pre-prints)")
    print("  3. Google Scholar (requires SerpAPI key)")
    print("  4. All of the above")

    source_choice = input("\nSelect sources (1-4, default: 1): ").strip() or "1"

    if source_choice == "1":
        sources = ["semantic_scholar"]
    elif source_choice == "2":
        sources = ["arxiv"]
    elif source_choice == "3":
        sources = ["google_scholar"]
    else:
        sources = ["semantic_scholar", "arxiv"]

    # Get API key if needed
    serpapi_key = None
    if "google_scholar" in sources:
        serpapi_key = os.environ.get("SERPAPI_KEY")
        if not serpapi_key:
            serpapi_key = input(
                "\nEnter SerpAPI key (or press Enter to skip Google Scholar): "
            ).strip()
            if not serpapi_key:
                sources.remove("google_scholar")
                print("Skipping Google Scholar")

    # Limits
    limit = input("\nPapers per source (default: 100, max: 500): ").strip()
    limit = int(limit) if limit else 100
    limit = min(limit, 500)

    # Execute search
    aggregator = ResearchAggregator()
    papers = aggregator.aggregate_search(query, sources, limit, serpapi_key)

    # Save results
    print("\n" + "=" * 80)
    save_choice = input("\nSave results? (y/n): ").strip().lower()

    if save_choice == "y":
        aggregator.save_results()

        separate = input("Also save separate files per source? (y/n): ").strip().lower()
        if separate == "y":
            aggregator.export_by_source()

        # Import to knowledge graph
        kg_import = input("\nImport to knowledge graph? (y/n): ").strip().lower()
        if kg_import == "y":
            try:
                from knowledge_graph import ResearchKnowledgeGraph

                filename = (
                    f"aggregated_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                )
                kg = ResearchKnowledgeGraph()

                # Load and import
                with open(filename, "r") as f:
                    data = json.load(f)

                print(f"\nImporting {len(data['papers'])} papers to knowledge graph...")
                # Import each paper (adapt import function for new format)
                for paper in data["papers"]:
                    kg.add_paper(paper)
                    # Auto-tag would go here

                kg.close()
                print("✓ Imported to knowledge graph")
            except Exception as e:
                print(f"✗ Could not import: {e}")


if __name__ == "__main__":
    main()
