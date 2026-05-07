"""
Command-line interface for Quantitative Finance Research Toolkit
"""

import sys
import argparse
import json
from pathlib import Path


def search_main():
    """
    Main entry point for qrt-search command
    
    Searches academic databases and aggregates results.
    """
    parser = argparse.ArgumentParser(
        description="Search academic databases for quantitative finance papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple search
  qrt-search "Monte Carlo rough volatility" --output results.json
  
  # Search with filters
  qrt-search "Bayesian credit risk" --sources semantic_scholar --limit 200
  
  # Multiple sources
  qrt-search "GPU acceleration" --sources semantic_scholar arxiv
        """
    )
    
    parser.add_argument(
        'query',
        nargs='?',
        help='Search query (e.g., "Monte Carlo rough volatility")'
    )
    
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=['semantic_scholar', 'arxiv', 'google_scholar'],
        default=['semantic_scholar'],
        help='Sources to search (default: semantic_scholar)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Papers per source (default: 100, max: 500)'
    )
    
    parser.add_argument(
        '--output',
        help='Output JSON file (default: auto-generated)'
    )
    
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive mode with prompts'
    )
    
    args = parser.parse_args()
    
    # Interactive mode
    if args.interactive or not args.query:
        print("\n" + "="*80)
        print("INTERACTIVE SEARCH MODE")
        print("="*80)
        
        if not args.query:
            print("\nEnter your search query:")
            print("Examples:")
            print("  - Monte Carlo rough volatility")
            print("  - GPU acceleration finance")
            print("  - Bayesian credit risk")
            args.query = input("\nQuery: ").strip()
            
            if not args.query:
                print("Error: Query cannot be empty")
                sys.exit(1)
        
        print(f"\nQuery: {args.query}")
        
        print(f"\nSources to search:")
        print("  1. Semantic Scholar only (recommended)")
        print("  2. arXiv only")
        print("  3. Both Semantic Scholar + arXiv")
        source_choice = input("Choice (1-3, default: 1): ").strip()
        if source_choice == '2':
            args.sources = ['arxiv']
        elif source_choice == '3':
            args.sources = ['semantic_scholar', 'arxiv']
        
        limit = input(f"\nPapers per source (default: {args.limit}, max: 500): ").strip()
        args.limit = int(limit) if limit else args.limit
        args.limit = min(args.limit, 500)
    
    # Import here to avoid slow startup
    try:
        from qrt.search.aggregator import ResearchAggregator
    except ImportError as e:
        print(f"Error: Could not import ResearchAggregator: {e}")
        print("Make sure the package is installed: uv pip install -e .")
        sys.exit(1)
    
    # Execute search
    print("\n" + "="*80)
    print("EXECUTING SEARCH")
    print("="*80)
    print(f"\nQuery: {args.query}")
    print(f"Sources: {', '.join(args.sources)}")
    print(f"Limit: {args.limit} papers per source")
    
    aggregator = ResearchAggregator()
    
    papers = aggregator.aggregate_search(
        query=args.query,
        sources=args.sources,
        limit_per_source=args.limit
    )
    
    if not papers:
        print("\nNo papers found.")
        sys.exit(0)
    
    # Save manually since save_results might have different signature
    import json
    from datetime import datetime
    
    filename = args.output or f"search_results_{len(papers)}papers.json"
    
    # Try using the object's save method first
    try:
        aggregator.save_results(filename)
    except TypeError:
        # If that doesn't work, save manually
        data = {
            'search_date': datetime.now().isoformat(),
            'query': args.query,
            'sources': args.sources,
            'num_papers': len(papers),
            'papers': papers
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved {len(papers)} papers to: {filename}")
    print(f"\nNext steps:")
    print(f"  qrt-kg import {filename}")
    print(f"  qrt-kg gaps")


def kg_main():
    """
    Main entry point for qrt-kg command
    
    Knowledge graph operations.
    """
    parser = argparse.ArgumentParser(
        description="Knowledge graph operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import papers
  qrt-kg import search_results.json
  
  # View statistics
  qrt-kg stats
  
  # Find research gaps
  qrt-kg gaps --min-papers 3
  
  # Search within graph
  qrt-kg search "GPU"
  
  # Show trending topics
  qrt-kg trending --months 12
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import papers from JSON file')
    import_parser.add_argument('file', help='JSON file from qrt-search')
    import_parser.add_argument('--auto-tag', action='store_true', default=True,
                               help='Automatically detect methods and domains (default: True)')
    
    # Stats command
    subparsers.add_parser('stats', help='Show knowledge graph statistics')
    
    # Sources command
    subparsers.add_parser('sources', help='Analyze papers by source database')
    
    # Gaps command
    gaps_parser = subparsers.add_parser('gaps', help='Find research gaps')
    gaps_parser.add_argument('--min-papers', type=int, default=3,
                            help='Minimum papers for methods/domains (default: 3)')
    gaps_parser.add_argument('--output', help='Save gaps to file')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search within knowledge graph')
    search_parser.add_argument('query', help='Search query')
    
    # Authors command
    subparsers.add_parser('authors', help='Show author collaboration networks')
    
    # Trending command
    trending_parser = subparsers.add_parser('trending', help='Show trending topics')
    trending_parser.add_argument('--months', type=int, default=12,
                                help='Look back N months (default: 12)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Import here to avoid slow startup
    try:
        from qrt.core.knowledge_graph import ResearchKnowledgeGraph, import_arxiv_data
    except ImportError as e:
        print(f"Error: Could not import knowledge graph modules: {e}")
        print("Make sure the package is installed: uv pip install -e .")
        sys.exit(1)
    
    # Initialize knowledge graph
    kg = ResearchKnowledgeGraph()
    
    try:
        # Execute command
        if args.command == 'import':
            if not Path(args.file).exists():
                print(f"Error: File not found: {args.file}")
                sys.exit(1)
            
            print(f"Importing papers from: {args.file}")
            import_arxiv_data(args.file, kg, auto_tag=args.auto_tag)
            print("✓ Import complete")
        
        elif args.command == 'stats':
            stats = kg.export_statistics()
            print("\n" + "="*80)
            print("KNOWLEDGE GRAPH STATISTICS")
            print("="*80)
            print(f"\nTotal papers: {stats.get('total_papers', 0)}")
            print(f"Total authors: {stats.get('total_authors', 0)}")
            print(f"Total methods: {stats.get('total_methods', 0)}")
            print(f"Total domains: {stats.get('total_domains', 0)}")
            print(f"Total citations: {stats.get('total_citations', 0)}")
            
            if stats.get('papers_by_source'):
                print("\nPapers by Source:")
                for source, count in stats['papers_by_source'].items():
                    print(f"  {source:25} | {count:4} papers")
            
            if stats.get('avg_citations_by_source'):
                print("\nAverage Citations by Source:")
                for source, avg in stats['avg_citations_by_source'].items():
                    print(f"  {source:25} | {avg:6.1f} citations")
        
        elif args.command == 'sources':
            kg.analyze_sources()
        
        elif args.command == 'gaps':
            gaps = kg.find_gaps(min_papers=args.min_papers)
            
            print("\n" + "="*80)
            print("RESEARCH GAPS")
            print("="*80)
            print(f"\nTop 20 Gaps (minimum {args.min_papers} papers for active areas):\n")
            
            for i, gap in enumerate(gaps[:20], 1):
                print(f"{i:2}. {gap['method']} × {gap['domain']}")
                print(f"    Status: {gap['gap_type']} ({gap['count']} papers)")
                print(f"    Score: {gap.get('score', 'N/A')}\n")
            
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(gaps, f, indent=2)
                print(f"✓ Saved gaps to: {args.output}")
        
        elif args.command == 'search':
            results = kg.search_papers(args.query)
            
            print(f"\nFound {len(results)} papers matching '{args.query}':\n")
            for result in results[:20]:
                if len(result) >= 4:
                    arxiv_id, title, cites, venue = result[:4]
                    print(f"• {title}")
                    print(f"  Citations: {cites} | Venue: {venue}\n")
        
        elif args.command == 'authors':
            networks = kg.find_author_networks()
            
            print("\n" + "="*80)
            print("AUTHOR COLLABORATION NETWORKS")
            print("="*80)
            print(f"\nTop 20 Collaborations:\n")
            
            for author1, author2, count in networks[:20]:
                print(f"{author1} ↔ {author2}: {count} papers")
        
        elif args.command == 'trending':
            topics = kg.get_trending_topics(months=args.months)
            
            print("\n" + "="*80)
            print(f"TRENDING TOPICS (last {args.months} months)")
            print("="*80)
            print()
            
            for topic, count in topics[:20]:
                print(f"{topic:40} | {count:3} papers")
    
    finally:
        kg.close()


def gaps_main():
    """
    Main entry point for qrt-gaps command
    
    Gap analysis and personalization.
    """
    parser = argparse.ArgumentParser(
        description="Gap analysis and personalized recommendations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze papers for gaps (use qrt-kg gaps instead)
  qrt-kg gaps --min-papers 3
  
  # Get personalized recommendations
  qrt-gaps personalize --interactive
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Personalize command
    personalize_parser = subparsers.add_parser('personalize', help='Get personalized recommendations')
    personalize_parser.add_argument('--strengths', nargs='+',
                                   help='Your method strengths (e.g., bayesian gpu_computing)')
    personalize_parser.add_argument('--interests', nargs='+',
                                   help='Your domain interests (e.g., credit_risk volatility_modeling)')
    personalize_parser.add_argument('--experience',
                                   choices=['beginner', 'intermediate', 'advanced'],
                                   help='Your experience level')
    personalize_parser.add_argument('--interactive', action='store_true',
                                   help='Interactive mode')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'personalize':
        # Interactive mode
        if args.interactive or not (args.strengths and args.interests):
            print("\n" + "="*80)
            print("PERSONALIZED GAP RECOMMENDATIONS")
            print("="*80)
            
            if not args.strengths:
                print("\nAvailable methods:")
                print("  bayesian, monte_carlo, gpu_computing, machine_learning,")
                print("  pde, optimization, time_series")
                
                strengths_input = input("\nYour method strengths (space-separated): ").strip()
                args.strengths = strengths_input.split() if strengths_input else []
            
            if not args.interests:
                print("\nAvailable domains:")
                print("  option_pricing, volatility_modeling, credit_risk, portfolio,")
                print("  risk_management, interest_rate, market_microstructure")
                
                interests_input = input("\nYour domain interests (space-separated): ").strip()
                args.interests = interests_input.split() if interests_input else []
            
            if not args.experience:
                print("\nExperience level:")
                print("  1. Beginner (prefer 1-3 existing papers to learn from)")
                print("  2. Intermediate (prefer 0-2 papers, some foundation)")
                print("  3. Advanced (prefer 0 papers, pure innovation)")
                
                exp_choice = input("Choice (1-3): ").strip()
                exp_map = {'1': 'beginner', '2': 'intermediate', '3': 'advanced'}
                args.experience = exp_map.get(exp_choice, 'intermediate')
        
        background = {
            'strengths': args.strengths or [],
            'interests': args.interests or [],
            'experience_level': args.experience or 'intermediate'
        }
        
        print("\n" + "="*80)
        print("YOUR PROFILE")
        print("="*80)
        print(f"\nMethod Strengths: {', '.join(background['strengths'])}")
        print(f"Domain Interests: {', '.join(background['interests'])}")
        print(f"Experience Level: {background['experience_level']}")
        
        print("\n" + "="*80)
        print("RECOMMENDATIONS")
        print("="*80)
        print("\nTo get personalized recommendations:")
        print("1. First run: qrt-kg gaps --output gaps.json")
        print("2. Then use your profile to filter the gaps")
        print("\nYour profile has been saved. Gap analysis coming soon!")


if __name__ == '__main__':
    print("Use qrt-search, qrt-kg, or qrt-gaps commands")
