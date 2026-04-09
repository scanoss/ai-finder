"""Main scanner orchestrator."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .analyzers.graph import ComponentGraph

# Progress callback: (current, total, phase) -> None
ProgressCallback = Callable[[int, int, str], None]

from .detectors import (
    CppDetector,
    CSharpDetector,
    GoDetector,
    JavaDetector,
    JavaScriptDetector,
    KotlinDetector,
    PHPDetector,
    PythonDetector,
    RubyDetector,
    RustDetector,
    ScalaDetector,
    SwiftDetector,
)
from .detectors.base import BaseDetector
from .discovery import FileDiscovery
from .license import LicenseDetector
from .manifests import (
    CargoManifestParser,
    CocoaPodsManifestParser,
    ComposerManifestParser,
    GemfileManifestParser,
    GoModManifestParser,
    GradleManifestParser,
    MavenManifestParser,
    NpmManifestParser,
    NuGetManifestParser,
    PythonManifestParser,
    SwiftPMManifestParser,
)
from .manifests.base import BaseManifestParser
from .models import Finding, LicenseInfo, ScanResult
from .parsers import (
    CoreMLParser,
    GGUFParser,
    JAXParser,
    KerasParser,
    MXNetParser,
    ONNXParser,
    PaddleParser,
    PickleParser,
    PyTorchParser,
    SafeTensorsParser,
    TensorFlowParser,
    TFLiteParser,
)
from .parsers.base import BaseModelParser

logger = logging.getLogger(__name__)


class Scanner:
    """Main scanner that orchestrates file discovery, detection, and parsing."""

    def __init__(self, detect_licenses: bool = True) -> None:
        """Initialize scanner with default detectors and parsers.

        Args:
            detect_licenses: Whether to detect licenses using osslili.
        """
        # License detector
        self._license_detector = LicenseDetector() if detect_licenses else None

        # SDK detectors by extension (12 languages)
        self._detectors: list[BaseDetector] = [
            PythonDetector(),
            JavaScriptDetector(),  # Also handles TypeScript (.ts, .tsx)
            GoDetector(),
            RustDetector(),
            JavaDetector(),
            RubyDetector(),
            PHPDetector(),
            CSharpDetector(),
            CppDetector(),
            SwiftDetector(),
            KotlinDetector(),
            ScalaDetector(),
        ]

        # Manifest parsers by filename (11 formats)
        self._manifest_parsers: list[BaseManifestParser] = [
            PythonManifestParser(),  # requirements.txt, pyproject.toml, setup.py
            NpmManifestParser(),  # package.json
            CargoManifestParser(),  # Cargo.toml
            GoModManifestParser(),  # go.mod
            GemfileManifestParser(),  # Gemfile
            MavenManifestParser(),  # pom.xml
            GradleManifestParser(),  # build.gradle, build.gradle.kts
            ComposerManifestParser(),  # composer.json
            NuGetManifestParser(),  # packages.config, *.csproj
            SwiftPMManifestParser(),  # Package.swift
            CocoaPodsManifestParser(),  # Podfile
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

        # Model file parsers (12 formats)
        self._model_parsers: list[BaseModelParser] = [
            GGUFParser(),
            SafeTensorsParser(),
            ONNXParser(),
            PyTorchParser(),
            TensorFlowParser(),
            TFLiteParser(),
            CoreMLParser(),
            KerasParser(),
            JAXParser(),
            MXNetParser(),
            PaddleParser(),
            PickleParser(),
        ]

        # Build extension -> model parser mapping
        self._ext_to_model_parser: dict[str, BaseModelParser] = {}
        for model_parser in self._model_parsers:
            for ext in model_parser.extensions:
                self._ext_to_model_parser[ext] = model_parser

        # Relationship analyzer (lazy loaded)
        self._relationship_analyzer = None

    def _get_relationship_analyzer(self):
        """Lazily load the relationship analyzer."""
        if self._relationship_analyzer is None:
            from .analyzers.graph import RelationshipAnalyzer

            self._relationship_analyzer = RelationshipAnalyzer()
        return self._relationship_analyzer

    def build_relationship_graph(self, path: Path) -> "ComponentGraph":
        """Build a component relationship graph for the given path.

        Args:
            path: Root directory to analyze.

        Returns:
            ComponentGraph with component relationships.
        """
        analyzer = self._get_relationship_analyzer()
        return analyzer.analyze_directory(path)

    def scan(
        self,
        path: Path,
        kb: object | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ScanResult:
        """Scan a directory for AI artifacts.

        Args:
            path: Root directory to scan.
            kb: Optional KnowledgeBase for enrichment.
            progress_callback: Optional callback for progress updates.
                Called with (current_file, total_files, phase_name).

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

        # Single-pass file discovery (efficient for large codebases)
        discovery = FileDiscovery(path)
        file_cache = discovery.collect_all()

        # Calculate total for progress
        total_files = (
            len(file_cache["source"])
            + len(file_cache["manifest"])
            + len(file_cache["config"])
            + len(file_cache["model"])
        )

        def report_progress(phase: str) -> None:
            if progress_callback:
                progress_callback(files_scanned, total_files, phase)

        # Scan source files for SDK usage
        for file_path in file_cache["source"]:
            files_scanned += 1
            report_progress("source")
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
        for file_path in file_cache["manifest"]:
            files_scanned += 1
            report_progress("manifest")
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

        # Scan config files (count only for now)
        for file_path in file_cache["config"]:
            files_scanned += 1
            report_progress("config")

        # Scan model files
        for file_path in file_cache["model"]:
            files_scanned += 1
            report_progress("model")
            full_path = path / file_path
            ext = file_path.suffix.lower()

            model_parser = self._ext_to_model_parser.get(ext)
            if model_parser:
                model_finding = model_parser.parse(full_path, file_path)
                if model_finding:
                    findings.append(model_finding)

        # Detect licenses
        report_progress("licenses")
        licenses: list[LicenseInfo] = []
        if self._license_detector and self._license_detector.available:
            result = self._license_detector.detect_path(path)
            if result and result.licenses:
                for lic in result.licenses:
                    if lic.spdx_id:
                        licenses.append(
                            LicenseInfo(
                                spdx_id=lic.spdx_id,
                                file_path=lic.file_path if hasattr(lic, "file_path") else "",
                                confidence=lic.confidence if hasattr(lic, "confidence") else 1.0,
                            )
                        )

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return ScanResult(
            root_path=str(path),
            findings=findings,
            licenses=licenses,
            files_scanned=files_scanned,
            duration_ms=duration_ms,
        )
