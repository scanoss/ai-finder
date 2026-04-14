"""Component relationship analyzers using tree-sitter.

NOTE: tree-sitter is an optional dependency. The analyzers require Python 3.10+
due to tree-sitter API requirements. Core scanning works without tree-sitter.
"""

from .base import BaseAnalyzer, ComponentUsage, FunctionCall, RelationshipGraph
from .dataflow import DataFlowGraph, DataFlowNode, FlowType
from .graph import ComponentGraph, RelationshipAnalyzer, TreeSitterNotAvailableError

# Tree-sitter based analyzers are optional (require Python 3.10+)
_TREE_SITTER_AVAILABLE = False
try:
    from .go_analyzer import GoAnalyzer
    from .javascript_analyzer import JavaScriptAnalyzer
    from .python_analyzer import PythonAnalyzer
    from .rust_analyzer import RustAnalyzer

    _TREE_SITTER_AVAILABLE = True
except ImportError:
    # tree-sitter not available or incompatible Python version
    GoAnalyzer = None  # type: ignore[misc, assignment]
    JavaScriptAnalyzer = None  # type: ignore[misc, assignment]
    PythonAnalyzer = None  # type: ignore[misc, assignment]
    RustAnalyzer = None  # type: ignore[misc, assignment]


def is_tree_sitter_available() -> bool:
    """Check if tree-sitter analyzers are available."""
    return _TREE_SITTER_AVAILABLE


__all__ = [
    "BaseAnalyzer",
    "ComponentUsage",
    "FunctionCall",
    "RelationshipGraph",
    "DataFlowGraph",
    "DataFlowNode",
    "FlowType",
    "PythonAnalyzer",
    "JavaScriptAnalyzer",
    "GoAnalyzer",
    "RustAnalyzer",
    "ComponentGraph",
    "RelationshipAnalyzer",
    "TreeSitterNotAvailableError",
    "is_tree_sitter_available",
]
