"""AI Finder Scanner library."""

from ai_finder_scanner.cache import ScanCache
from ai_finder_scanner.discovery import FileDiscovery
from ai_finder_scanner.license import OSSLILI_AVAILABLE, LicenseDetector, detect_license
from ai_finder_scanner.models import (
    AgentInfo,
    AIComponent,
    DatasetInfo,
    EmbeddingInfo,
    Finding,
    FindingType,
    GuardrailInfo,
    LicenseInfo,
    ManifestDep,
    ModelInfo,
    PromptInfo,
    ScanResult,
    SDKUsage,
    ToolInfo,
    VectorStoreInfo,
)
from ai_finder_scanner.scanner import Scanner

__version__ = "0.3.9"

__all__ = [
    # Core
    "Scanner",
    "ScanResult",
    "Finding",
    "FindingType",
    # Models - Core
    "SDKUsage",
    "ManifestDep",
    "ModelInfo",
    "AIComponent",
    "LicenseInfo",
    # Models - Phase 2 Agentic AI
    "AgentInfo",
    "ToolInfo",
    "EmbeddingInfo",
    "VectorStoreInfo",
    "PromptInfo",
    "GuardrailInfo",
    "DatasetInfo",
    # Discovery
    "FileDiscovery",
    # Caching
    "ScanCache",
    # License detection
    "LicenseDetector",
    "detect_license",
    "OSSLILI_AVAILABLE",
]
