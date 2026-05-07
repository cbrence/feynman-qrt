"""
Quantitative Finance Research Toolkit
"""

__version__ = "1.0.0"
__author__ = "Colin Brence"

# Import main classes when available
try:
    from .search.aggregator import ResearchAggregator
    from .core.knowledge_graph import ResearchKnowledgeGraph
    from .analysis.gap_finder import GapFinder
    
    __all__ = [
        "ResearchAggregator",
        "ResearchKnowledgeGraph", 
        "GapFinder",
    ]
except ImportError:
    # Modules not yet available
    pass
