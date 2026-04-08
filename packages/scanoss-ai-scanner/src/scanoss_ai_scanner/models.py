"""Scanner data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FindingType(Enum):
    """Types of findings detected by the scanner."""

    SDK_USAGE = "sdk_usage"
    MANIFEST_DEP = "manifest_dep"
    MODEL_FILE = "model_file"
    MCP_SERVER = "mcp_server"
    AI_COMPONENT = "ai_component"


@dataclass
class SDKUsage:
    """SDK usage finding details."""

    sdk: str
    import_statement: str
    version: str | None = None


@dataclass
class ManifestDep:
    """Manifest dependency finding details."""

    name: str
    version: str
    manifest_file: str


@dataclass
class ModelInfo:
    """Model file finding details."""

    format: str
    architecture: str | None = None
    parameter_count: int | None = None
    quantization: str | None = None


@dataclass
class AIComponent:
    """AI component finding details."""

    component_type: str
    name: str


@dataclass
class LicenseInfo:
    """Detected license information."""

    spdx_id: str
    file_path: str
    confidence: float = 1.0


@dataclass
class Finding:
    """A single finding from the scanner."""

    type: FindingType
    file_path: str
    confidence: float
    line: int | None = None
    sdk_usage: SDKUsage | None = None
    manifest_dep: ManifestDep | None = None
    model_info: ModelInfo | None = None
    ai_component: AIComponent | None = None


@dataclass
class ScanResult:
    """Complete result from a scan operation."""

    root_path: str
    findings: list[Finding] = field(default_factory=list)
    licenses: list[LicenseInfo] = field(default_factory=list)
    files_scanned: int = 0
    duration_ms: int = 0
