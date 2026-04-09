"""Relationship graph builder for AI component analysis."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .base import BaseAnalyzer, ComponentUsage, RelationshipGraph

# Tree-sitter analyzers are optional (require Python 3.10+)
_ANALYZERS_AVAILABLE = False
try:
    from .go_analyzer import GoAnalyzer
    from .javascript_analyzer import JavaScriptAnalyzer
    from .python_analyzer import PythonAnalyzer
    from .rust_analyzer import RustAnalyzer

    _ANALYZERS_AVAILABLE = True
except ImportError:
    GoAnalyzer = None  # type: ignore[misc, assignment]
    JavaScriptAnalyzer = None  # type: ignore[misc, assignment]
    PythonAnalyzer = None  # type: ignore[misc, assignment]
    RustAnalyzer = None  # type: ignore[misc, assignment]


@dataclass
class ComponentNode:
    """A node in the component graph."""

    id: str
    type: str  # "sdk", "function", "file"
    usages: list[ComponentUsage] = field(default_factory=list)
    files: set[str] = field(default_factory=set)


@dataclass
class ComponentEdge:
    """An edge in the component graph."""

    source: str
    target: str
    relationship: str  # "dependsOn", "contains", "calls"
    file_path: str | None = None
    line: int | None = None


@dataclass
class ComponentGraph:
    """Graph of AI component relationships."""

    nodes: dict[str, ComponentNode] = field(default_factory=dict)
    edges: list[ComponentEdge] = field(default_factory=list)

    def add_node(self, node_id: str, node_type: str) -> ComponentNode:
        """Add or get a node."""
        if node_id not in self.nodes:
            self.nodes[node_id] = ComponentNode(id=node_id, type=node_type)
        return self.nodes[node_id]

    def add_edge(
        self,
        source: str,
        target: str,
        relationship: str,
        file_path: str | None = None,
        line: int | None = None,
    ) -> None:
        """Add an edge to the graph."""
        self.edges.append(
            ComponentEdge(
                source=source,
                target=target,
                relationship=relationship,
                file_path=file_path,
                line=line,
            )
        )

    def get_dependencies(self, node_id: str) -> list[str]:
        """Get all nodes that the given node depends on."""
        return [
            e.target for e in self.edges if e.source == node_id and e.relationship == "dependsOn"
        ]

    def get_dependents(self, node_id: str) -> list[str]:
        """Get all nodes that depend on the given node."""
        return [
            e.source for e in self.edges if e.target == node_id and e.relationship == "dependsOn"
        ]

    def to_dict(self) -> dict:
        """Convert graph to dictionary for serialization."""
        return {
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type,
                    "files": list(n.files),
                    "usage_count": len(n.usages),
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relationship": e.relationship,
                    "file_path": e.file_path,
                    "line": e.line,
                }
                for e in self.edges
            ],
        }


class TreeSitterNotAvailableError(Exception):
    """Raised when tree-sitter analyzers are not available."""

    pass


class RelationshipAnalyzer:
    """Analyzes codebase to build component relationship graph."""

    def __init__(self) -> None:
        """Initialize with language-specific analyzers.

        Raises:
            TreeSitterNotAvailableError: If tree-sitter is not installed or
                incompatible with current Python version.
        """
        if not _ANALYZERS_AVAILABLE:
            raise TreeSitterNotAvailableError(
                "Relationship analysis requires tree-sitter which needs Python 3.10+. "
                "Install with: pip install 'scanoss-ai[relationships]' (Python 3.10+)"
            )

        self._analyzers: list[BaseAnalyzer] = [
            PythonAnalyzer(),
            JavaScriptAnalyzer(),
            GoAnalyzer(),
            RustAnalyzer(),
        ]

        # Build extension to analyzer mapping
        self._ext_to_analyzer: dict[str, BaseAnalyzer] = {}
        for analyzer in self._analyzers:
            for ext in analyzer.extensions:
                self._ext_to_analyzer[ext] = analyzer

    def analyze_file(self, content: str, path: Path) -> RelationshipGraph:
        """Analyze a single file for component relationships."""
        ext = path.suffix.lower()
        analyzer = self._ext_to_analyzer.get(ext)

        if not analyzer:
            return RelationshipGraph()

        usages = analyzer.analyze(content, path)
        calls = analyzer.extract_calls(content, path)

        return RelationshipGraph(usages=usages, calls=calls)

    def build_graph(self, file_results: dict[Path, RelationshipGraph]) -> ComponentGraph:
        """Build a component graph from multiple file analysis results.

        Args:
            file_results: Dictionary mapping file paths to their analysis results.

        Returns:
            ComponentGraph with nodes and edges.
        """
        graph = ComponentGraph()

        # Track which functions use which components
        function_to_components: dict[str, set[str]] = defaultdict(set)
        file_to_components: dict[str, set[str]] = defaultdict(set)

        # Process all usages
        for path, result in file_results.items():
            file_path = str(path)

            # Add file node
            graph.add_node(file_path, "file")

            for usage in result.usages:
                component_id = usage.component_id

                # Add component node
                component_node = graph.add_node(component_id, "sdk")
                component_node.usages.append(usage)
                component_node.files.add(file_path)

                # Track file -> component relationship
                file_to_components[file_path].add(component_id)

                # Track function -> component relationship
                if usage.function_context:
                    func_key = f"{file_path}::{usage.function_context}"
                    function_to_components[func_key].add(component_id)

                    # Add function node
                    func_node = graph.add_node(func_key, "function")
                    func_node.files.add(file_path)

                    # Function depends on component
                    graph.add_edge(
                        func_key,
                        component_id,
                        "dependsOn",
                        usage.file_path,
                        usage.line,
                    )

                # File contains component usage
                graph.add_edge(file_path, component_id, "contains", usage.file_path, usage.line)

        # Process function calls to find transitive dependencies
        for path, result in file_results.items():
            file_path = str(path)

            for call in result.calls:
                if call.caller != "<module>":
                    caller_key = f"{file_path}::{call.caller}"
                else:
                    caller_key = file_path
                callee_key = f"{file_path}::{call.callee}"

                # If callee function uses AI components, caller transitively depends on them
                if callee_key in function_to_components:
                    for component_id in function_to_components[callee_key]:
                        # Add transitive dependency
                        if caller_key not in [file_path]:
                            graph.add_edge(
                                caller_key,
                                component_id,
                                "dependsOn",
                                call.file_path,
                                call.line,
                            )

        return graph

    def analyze_directory(self, root: Path) -> ComponentGraph:
        """Analyze all supported files in a directory.

        Args:
            root: Root directory to analyze.

        Returns:
            ComponentGraph with all relationships.
        """
        from ..discovery import FileDiscovery

        discovery = FileDiscovery(root)
        file_results: dict[Path, RelationshipGraph] = {}

        for file_path in discovery.source_files():
            full_path = root / file_path
            ext = file_path.suffix.lower()

            if ext not in self._ext_to_analyzer:
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                result = self.analyze_file(content, file_path)
                if result.usages or result.calls:
                    file_results[file_path] = result
            except OSError:
                continue

        return self.build_graph(file_results)
