"""SCANOSS AI Scanner library."""

from scanoss_ai_scanner.cache import ScanCache
from scanoss_ai_scanner.discovery import FileDiscovery
from scanoss_ai_scanner.license import OSSLILI_AVAILABLE, LicenseDetector, detect_license
from scanoss_ai_scanner.models import (
    AIComponent,
    Finding,
    FindingType,
    ManifestDep,
    ModelInfo,
    ScanResult,
    SDKUsage,
)
from scanoss_ai_scanner.scanner import Scanner

__version__ = "0.1.0"

__all__ = [
    # Core
    "Scanner",
    "ScanResult",
    "Finding",
    "FindingType",
    # Models
    "SDKUsage",
    "ManifestDep",
    "ModelInfo",
    "AIComponent",
    # Discovery
    "FileDiscovery",
    # Caching
    "ScanCache",
    # License detection
    "LicenseDetector",
    "detect_license",
    "OSSLILI_AVAILABLE",
]
