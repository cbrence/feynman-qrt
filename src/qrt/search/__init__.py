"""
Search functionality - Multi-source aggregation
"""

try:
    from .aggregator import ResearchAggregator
    
    __all__ = ["ResearchAggregator"]
except ImportError:
    pass
