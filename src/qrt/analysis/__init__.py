"""
Analysis functionality - Gap finding
"""

try:
    from .gap_finder import GapFinder
    
    __all__ = ["GapFinder"]
except ImportError:
    pass
