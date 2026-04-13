"""SCANOSS AI Scanner library."""

from scanoss_ai_scanner.cache import ScanCache
from scanoss_ai_scanner.discovery import FileDiscovery
from scanoss_ai_scanner.license import OSSLILI_AVAILABLE, LicenseDetector, detect_license
from scanoss_ai_scanner.models import (
    AIComponent,
    AgentInfo,
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
from scanoss_ai_scanner.scanner import Scanner

__version__ = "0.2.11"

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
