"""KB data models."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SDKMatch:
    """Match result for an SDK pattern."""

    id: str
    purl: str
    category: str
    license: Optional[str] = None
    confidence: float = 1.0


@dataclass
class ModelMatch:
    """Match result for a model name pattern."""

    purl: str
    name: str
    organization: Optional[str] = None
    architecture: Optional[str] = None
    format: Optional[str] = None
    parameter_count: Optional[int] = None
    license: Optional[str] = None
    confidence: float = 1.0


@dataclass
class MCPMatch:
    """Match result for an MCP server pattern."""

    id: str
    purl: str
    description: str
    confidence: float = 1.0


@dataclass
class AncestryEdge:
    """Edge in the model ancestry graph."""

    source_purl: str
    target_purl: str
    relation_type: str  # fine-tuned | merged | possibly-derived
    confidence: float
    declared: bool = False
