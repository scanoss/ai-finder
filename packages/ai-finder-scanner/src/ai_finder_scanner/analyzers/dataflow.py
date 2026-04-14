"""Data flow tracking for AI component outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FlowType(Enum):
    """Type of data flow event."""

    DEFINITION = "definition"  # Variable assigned from AI call
    USE = "use"  # Variable used (passed to function, returned, etc.)
    RETURN = "return"  # Variable returned from function
    ARGUMENT = "argument"  # Variable passed as function argument


@dataclass
class DataFlowNode:
    """A node in the data flow graph."""

    variable: str  # Variable name
    flow_type: FlowType
    file_path: str
    line: int
    function_context: str | None = None  # Function where this occurs
    source_component: str | None = None  # AI component that produced this (for definitions)
    target_function: str | None = None  # Function receiving this (for arguments)
    details: dict = field(default_factory=dict)


@dataclass
class DataFlowEdge:
    """An edge connecting data flow nodes."""

    source_var: str  # Variable at source
    target_var: str | None  # Variable at target (None if passed directly)
    source_line: int
    target_line: int
    flow_type: str  # "assignment", "argument", "return"


@dataclass
class DataFlowGraph:
    """Graph tracking how AI component outputs flow through code."""

    nodes: list[DataFlowNode] = field(default_factory=list)
    edges: list[DataFlowEdge] = field(default_factory=list)

    # Track which variables hold AI component outputs
    ai_tainted_vars: dict[str, str] = field(default_factory=dict)  # var -> component_id

    def add_definition(
        self,
        variable: str,
        component_id: str,
        file_path: str,
        line: int,
        function_context: str | None = None,
    ) -> None:
        """Record a variable being assigned from an AI component call."""
        self.nodes.append(
            DataFlowNode(
                variable=variable,
                flow_type=FlowType.DEFINITION,
                file_path=file_path,
                line=line,
                function_context=function_context,
                source_component=component_id,
            )
        )
        # Mark this variable as tainted by AI component
        key = f"{function_context or '<module>'}::{variable}"
        self.ai_tainted_vars[key] = component_id

    def add_use(
        self,
        variable: str,
        flow_type: FlowType,
        file_path: str,
        line: int,
        function_context: str | None = None,
        target_function: str | None = None,
    ) -> None:
        """Record a variable being used (passed, returned, etc.)."""
        self.nodes.append(
            DataFlowNode(
                variable=variable,
                flow_type=flow_type,
                file_path=file_path,
                line=line,
                function_context=function_context,
                target_function=target_function,
            )
        )

    def is_tainted(self, variable: str, function_context: str | None = None) -> bool:
        """Check if a variable holds AI component output."""
        key = f"{function_context or '<module>'}::{variable}"
        return key in self.ai_tainted_vars

    def get_taint_source(self, variable: str, function_context: str | None = None) -> str | None:
        """Get the AI component that produced this variable's value."""
        key = f"{function_context or '<module>'}::{variable}"
        return self.ai_tainted_vars.get(key)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "nodes": [
                {
                    "variable": n.variable,
                    "flow_type": n.flow_type.value,
                    "file_path": n.file_path,
                    "line": n.line,
                    "function_context": n.function_context,
                    "source_component": n.source_component,
                    "target_function": n.target_function,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "source_var": e.source_var,
                    "target_var": e.target_var,
                    "source_line": e.source_line,
                    "target_line": e.target_line,
                    "flow_type": e.flow_type,
                }
                for e in self.edges
            ],
            "tainted_variables": list(self.ai_tainted_vars.keys()),
        }
