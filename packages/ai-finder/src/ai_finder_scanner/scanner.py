"""Main scanner orchestrator."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .detectors import (
    AgentDetector,
    CppDetector,
    CSharpDetector,
    DatasetDetector,
    GoDetector,
    JavaDetector,
    JavaScriptDetector,
    KotlinDetector,
    PHPDetector,
    PythonDetector,
    RAGDetector,
    RubyDetector,
    RustDetector,
    ScalaDetector,
    SwiftDetector,
    ToolsDetector,
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

if TYPE_CHECKING:
    from .analyzers.graph import ComponentGraph, RelationshipAnalyzer

# Progress callback: (current, total, phase) -> None
ProgressCallback = Callable[[int, int, str], None]

# Telemetry callback: (event_name, properties) -> None
# Uses Dict for Python 3.8 runtime compatibility (type aliases are evaluated eagerly)
TelemetryCallback = Callable[[str, dict[str, Any]], None]

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

        # Semantic detectors: AI-component constructs (agents, tools, RAG
        # embeddings/vector stores, datasets) that are orthogonal to SDK-import
        # detection and run on the same source files. Kept in their own list so
        # multiple run per file (the SDK dispatch below is one-detector-per-ext).
        self._semantic_detectors: list[BaseDetector] = [
            AgentDetector(),
            ToolsDetector(),
            RAGDetector(),
            DatasetDetector(),
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
        self._relationship_analyzer: RelationshipAnalyzer | None = None

    def _get_relationship_analyzer(self) -> RelationshipAnalyzer:
        """Lazily load the relationship analyzer."""
        if self._relationship_analyzer is None:
            from .analyzers.graph import RelationshipAnalyzer

            self._relationship_analyzer = RelationshipAnalyzer()
        return self._relationship_analyzer

    def build_relationship_graph(self, path: Path) -> ComponentGraph:
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
        telemetry_callback: TelemetryCallback | None = None,
    ) -> ScanResult:
        """Scan a directory for AI artifacts.

        Args:
            path: Root directory to scan.
            kb: Optional KnowledgeBase for enrichment.
            progress_callback: Optional callback for progress updates.
                Called with (current_file, total_files, phase_name).
            telemetry_callback: Optional callback for telemetry events.
                Called with (event_name, properties_dict).

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

        def track(event: str, props: dict[str, Any] | None = None) -> None:
            """Emit telemetry event."""
            if telemetry_callback:
                telemetry_callback(event, props or {})

        # Mark scan start
        track("scan.started", {})

        # Single-pass file discovery (efficient for large codebases)
        track("scan.discovery.started", {})
        discovery = FileDiscovery(path)
        file_cache = discovery.collect_all()

        # Calculate total for progress
        total_files = (
            len(file_cache["source"])
            + len(file_cache["manifest"])
            + len(file_cache["config"])
            + len(file_cache["model"])
        )

        track(
            "scan.discovery.completed",
            {
                "source_files": len(file_cache["source"]),
                "manifest_files": len(file_cache["manifest"]),
                "config_files": len(file_cache["config"]),
                "model_files": len(file_cache["model"]),
                "total_files": total_files,
            },
        )

        def report_progress(phase: str) -> None:
            if progress_callback:
                progress_callback(files_scanned, total_files, phase)

        # Scan source files for SDK usage
        track("scan.detection.started", {"phase": "sdk"})
        sdk_findings = 0
        sdk_by_name: dict[str, int] = {}
        for file_path in file_cache["source"]:
            files_scanned += 1
            report_progress("source")
            full_path = path / file_path
            ext = file_path.suffix.lower()

            sdk_detector = self._ext_to_detector.get(ext)
            semantic = [d for d in self._semantic_detectors if ext in d.extensions]
            if not sdk_detector and not semantic:
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
            except OSError as e:
                logger.warning("Failed to read %s: %s", file_path, e)
                continue
            if sdk_detector:
                for finding in sdk_detector.detect(content, file_path):
                    findings.append(finding)
                    sdk_findings += 1
                    if finding.sdk_usage:
                        sdk_name = finding.sdk_usage.sdk
                        sdk_by_name[sdk_name] = sdk_by_name.get(sdk_name, 0) + 1
            for detector in semantic:
                for finding in detector.detect(content, file_path):
                    findings.append(finding)
        track(
            "scan.detection.completed",
            {
                "phase": "sdk",
                "findings": sdk_findings,
                "unique_sdks": len(sdk_by_name),
            },
        )
        # Track each SDK found as discrete event
        for sdk_name in sdk_by_name:
            track("scan.sdk.found", {"name": sdk_name})

        # Scan manifest files for dependencies
        track("scan.detection.started", {"phase": "manifest"})
        manifest_findings = 0
        manifest_by_name: dict[str, int] = {}
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
                        manifest_findings += 1
                        if finding.manifest_dep:
                            dep_name = finding.manifest_dep.name
                            manifest_by_name[dep_name] = manifest_by_name.get(dep_name, 0) + 1
                except OSError as e:
                    logger.warning("Failed to read %s: %s", file_path, e)
        track(
            "scan.detection.completed",
            {
                "phase": "manifest",
                "findings": manifest_findings,
                "unique_deps": len(manifest_by_name),
            },
        )
        # Track each manifest dependency found as discrete event
        for dep_name in manifest_by_name:
            track("scan.manifest_dep.found", {"name": dep_name})

        # Scan config files (count only for now)
        for _file_path in file_cache["config"]:
            files_scanned += 1
            report_progress("config")

        # Scan model files
        track("scan.detection.started", {"phase": "model"})
        model_findings = 0
        model_formats: dict[str, int] = {}
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
                    model_findings += 1
                    if model_finding.model_info:
                        fmt = model_finding.model_info.format
                        model_formats[fmt] = model_formats.get(fmt, 0) + 1
        track(
            "scan.detection.completed",
            {
                "phase": "model",
                "findings": model_findings,
                "formats": list(model_formats.keys()),
            },
        )

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

        # Track overall scan metrics
        track(
            "scan.metrics",
            {
                "total_findings": len(findings),
                "sdk_findings": sdk_findings,
                "manifest_findings": manifest_findings,
                "model_findings": model_findings,
                "licenses_found": len(licenses),
                "files_scanned": files_scanned,
                "duration_ms": duration_ms,
            },
        )

        # Mark scan completed successfully
        track(
            "scan.completed",
            {
                "success": True,
                "total_findings": len(findings),
                "files_scanned": files_scanned,
                "duration_ms": duration_ms,
            },
        )

        return ScanResult(
            root_path=str(path),
            findings=findings,
            licenses=licenses,
            files_scanned=files_scanned,
            duration_ms=duration_ms,
        )
