"""Base analyzer interface for relationship analysis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dataflow import DataFlowGraph


@dataclass
class FunctionCall:
    """Represents a function/method call in the code."""

    caller: str  # Function making the call
    callee: str  # Function being called
    file_path: str
    line: int
    module: str | None = None  # Module the callee belongs to


@dataclass
class ComponentUsage:
    """Represents usage of an AI component (SDK/model)."""

    component_id: str  # SDK or model identifier
    usage_type: str  # "instantiation", "method_call", "import"
    function_context: str | None  # Function where usage occurs
    file_path: str
    line: int
    details: dict = field(default_factory=dict)


@dataclass
class RelationshipGraph:
    """Graph of component relationships in a codebase."""

    # Component usages keyed by file path
    usages: list[ComponentUsage] = field(default_factory=list)

    # Function call graph
    calls: list[FunctionCall] = field(default_factory=list)

    # Dependency edges: (source_component, target_component, relationship_type)
    edges: list[tuple[str, str, str]] = field(default_factory=list)


class BaseAnalyzer(ABC):
    """Base class for tree-sitter based code analyzers."""

    @property
    @abstractmethod
    def language(self) -> str:
        """Language this analyzer handles."""

    @property
    @abstractmethod
    def extensions(self) -> frozenset[str]:
        """File extensions this analyzer handles."""

    @abstractmethod
    def analyze(self, content: str, path: Path) -> list[ComponentUsage]:
        """Analyze source code for AI component usage patterns.

        Args:
            content: Source code content.
            path: File path (relative to scan root).

        Returns:
            List of component usages found.
        """

    @abstractmethod
    def extract_calls(self, content: str, path: Path) -> list[FunctionCall]:
        """Extract function call graph from source code.

        Args:
            content: Source code content.
            path: File path (relative to scan root).

        Returns:
            List of function calls found.
        """

    def extract_dataflow(self, content: str, path: Path) -> "DataFlowGraph":
        """Extract data flow graph showing how AI outputs propagate.

        Args:
            content: Source code content.
            path: File path (relative to scan root).

        Returns:
            DataFlowGraph tracking AI component output flow.
        """
        from .dataflow import DataFlowGraph

        return DataFlowGraph()  # Default: empty graph
