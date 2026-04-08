"""Main scanner orchestrator."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .detectors import GoDetector, JavaScriptDetector, PythonDetector, RustDetector
from .detectors.base import BaseDetector
from .discovery import FileDiscovery
from .manifests import NpmManifestParser, PythonManifestParser
from .manifests.base import BaseManifestParser
from .models import Finding, ScanResult

logger = logging.getLogger(__name__)


class Scanner:
    """Main scanner that orchestrates file discovery, detection, and parsing."""

    def __init__(self) -> None:
        """Initialize scanner with default detectors and parsers."""
        # SDK detectors by extension
        self._detectors: list[BaseDetector] = [
            PythonDetector(),
            JavaScriptDetector(),
            GoDetector(),
            RustDetector(),
        ]

        # Manifest parsers by filename
        self._manifest_parsers: list[BaseManifestParser] = [
            PythonManifestParser(),
            NpmManifestParser(),
        ]

        # Build extension -> detector mapping
        self._ext_to_detector: dict[str, BaseDetector] = {}
        for detector in self._detectors:
            for ext in detector.extensions:
                self._ext_to_detector[ext] = detector

        # Build filename -> parser mapping
        self._name_to_parser: dict[str, BaseManifestParser] = {}
        for parser in self._manifest_parsers:
            for name in parser.manifest_names:
                self._name_to_parser[name] = parser

    def scan(self, path: Path, kb: object | None = None) -> ScanResult:
        """Scan a directory for AI artifacts.

        Args:
            path: Root directory to scan.
            kb: Optional KnowledgeBase for enrichment.

        Returns:
            ScanResult with all findings.

        Raises:
            FileNotFoundError: If path doesn't exist.
        """
        path = Path(path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        start_time = time.monotonic()
        findings: list[Finding] = []
        files_scanned = 0

        discovery = FileDiscovery(path)

        # Scan source files for SDK usage
        for file_path in discovery.source_files():
            files_scanned += 1
            full_path = path / file_path
            ext = file_path.suffix.lower()

            detector = self._ext_to_detector.get(ext)
            if detector:
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    for finding in detector.detect(content, file_path):
                        findings.append(finding)
                except OSError as e:
                    logger.warning("Failed to read %s: %s", file_path, e)

        # Scan manifest files for dependencies
        for file_path in discovery.manifest_files():
            files_scanned += 1
            full_path = path / file_path
            name = file_path.name

            parser = self._name_to_parser.get(name)
            if parser:
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    for finding in parser.parse(content, file_path):
                        findings.append(finding)
                except OSError as e:
                    logger.warning("Failed to read %s: %s", file_path, e)

        # Scan config and model files (count only for now)
        for _ in discovery.config_files():
            files_scanned += 1

        for _ in discovery.model_files():
            files_scanned += 1

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return ScanResult(
            root_path=str(path),
            findings=findings,
            files_scanned=files_scanned,
            duration_ms=duration_ms,
        )
