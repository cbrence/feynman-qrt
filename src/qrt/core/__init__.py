"""
Core functionality - Knowledge Graph
"""

try:
    from .knowledge_graph import ResearchKnowledgeGraph, import_arxiv_data
    
    __all__ = ["ResearchKnowledgeGraph", "import_arxiv_data"]
except ImportError:
    pass
