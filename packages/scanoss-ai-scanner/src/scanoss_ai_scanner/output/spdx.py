"""SPDX SBOM output formatter."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .. import __version__
from ..models import Finding, FindingType, ScanResult

if TYPE_CHECKING:
    from ..analyzers.graph import ComponentGraph
    from ..enrichment.kb_enricher import KBEnricher


class SPDXFormatter:
    """Format scan results as SPDX SBOM."""

    SPDX_VERSION = "SPDX-2.3"
    DATA_LICENSE = "CC0-1.0"

    # Manifest file to PURL type mapping
    MANIFEST_PURL_TYPES: dict[str, str] = {
        "requirements.txt": "pypi",
        "requirements-dev.txt": "pypi",
        "requirements-test.txt": "pypi",
        "pyproject.toml": "pypi",
        "setup.py": "pypi",
        "setup.cfg": "pypi",
        "Pipfile": "pypi",
        "package.json": "npm",
        "package-lock.json": "npm",
        "yarn.lock": "npm",
        "go.mod": "golang",
        "go.sum": "golang",
        "Cargo.toml": "cargo",
        "Cargo.lock": "cargo",
        "pom.xml": "maven",
        "build.gradle": "maven",
        "build.gradle.kts": "maven",
        "Gemfile": "gem",
        "Gemfile.lock": "gem",
        "composer.json": "composer",
        "composer.lock": "composer",
        "Package.swift": "swift",
        "Podfile": "cocoapods",
        "Podfile.lock": "cocoapods",
        "*.csproj": "nuget",
        "packages.config": "nuget",
    }

    def __init__(self, indent: int | None = 2) -> None:
        """Initialize formatter.

        Args:
            indent: JSON indentation level.
        """
        self.indent = indent

    def _infer_purl_type_from_sdk(self, sdk_name: str) -> str:
        """Infer PURL type from SDK name pattern."""
        if sdk_name.startswith("github.com/") or sdk_name.startswith("golang.org/"):
            return "golang"
        if sdk_name.startswith("@"):
            return "npm"
        if sdk_name.startswith("async-") or sdk_name.endswith("-rs"):
            return "cargo"
        return "pypi"

    def _infer_purl_type_from_manifest(self, manifest_file: str) -> str:
        """Infer PURL type from manifest filename."""
        filename = manifest_file.split("/")[-1]
        if filename in self.MANIFEST_PURL_TYPES:
            return self.MANIFEST_PURL_TYPES[filename]
        if filename.endswith(".csproj"):
            return "nuget"
        return "pypi"

    def _finding_to_package(self, finding: Finding, idx: int) -> dict[str, Any] | None:
        """Convert a finding to an SPDX package.

        Args:
            finding: Finding to convert.
            idx: Package index for SPDXID.

        Returns:
            Package dict or None if not applicable.
        """
        if finding.type == FindingType.SDK_USAGE and finding.sdk_usage:
            sdk = finding.sdk_usage
            package: dict[str, Any] = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": sdk.sdk,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
            }
            if sdk.version:
                package["versionInfo"] = sdk.version
            # Add external ref for PURL
            purl_type = self._infer_purl_type_from_sdk(sdk.sdk)
            package["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:{purl_type}/{sdk.sdk}",
                }
            ]
            return package

        if finding.type == FindingType.MANIFEST_DEP and finding.manifest_dep:
            dep = finding.manifest_dep
            package = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": dep.name,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
            }
            if dep.version:
                version = re.sub(r"^[>=<~^]+", "", dep.version)
                if version:
                    package["versionInfo"] = version
            # Generate PURL based on manifest type
            purl_type = self._infer_purl_type_from_manifest(dep.manifest_file)
            package["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:{purl_type}/{dep.name}",
                }
            ]
            return package

        if finding.type == FindingType.MODEL_FILE and finding.model_info:
            info = finding.model_info
            package: dict[str, Any] = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": finding.file_path.split("/")[-1],
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "primaryPackagePurpose": "APPLICATION",
            }

            # Build detailed comment with model metadata
            comment_parts = ["AI/ML model file"]
            if info.format:
                comment_parts.append(f"format: {info.format}")
            if info.architecture:
                comment_parts.append(f"architecture: {info.architecture}")
            if info.quantization:
                comment_parts.append(f"quantization: {info.quantization}")
            if info.parameter_count:
                comment_parts.append(f"parameters: {info.parameter_count:,}")
            package["comment"] = ", ".join(comment_parts)

            # Add external references for model metadata (SPDX 2.3 compatible)
            # Using OTHER category for AI/ML specific references
            ext_refs = []
            if info.format:
                ext_refs.append(
                    {
                        "referenceCategory": "OTHER",
                        "referenceType": "scanoss-ai-model-format",
                        "referenceLocator": info.format,
                    }
                )
            if info.architecture:
                ext_refs.append(
                    {
                        "referenceCategory": "OTHER",
                        "referenceType": "scanoss-ai-model-architecture",
                        "referenceLocator": info.architecture,
                    }
                )
            if ext_refs:
                package["externalRefs"] = ext_refs

            return package

        return None

    def _enrich_packages(
        self,
        packages: dict[str, dict[str, Any]],
        enricher: KBEnricher,
    ) -> None:
        """Enrich packages with KB metadata.

        Args:
            packages: Dict of package name to package dict (modified in place).
            enricher: KB enricher instance.
        """
        for name, package in packages.items():
            purpose = package.get("primaryPackagePurpose")

            if purpose == "APPLICATION":
                # This is a model file - enrich from KB
                model_data = enricher.lookup_model(name)
                if model_data:
                    # Add license
                    if model_data.license and "licenseConcluded" not in package:
                        package["licenseConcluded"] = model_data.license
                        package["licenseDeclared"] = model_data.license

                    # Update comment with more info
                    comment_parts = [package.get("comment", "")]
                    if model_data.architecture:
                        comment_parts.append(f"architecture: {model_data.architecture}")
                    if model_data.parameter_count:
                        comment_parts.append(f"parameters: {model_data.parameter_count:,}")
                    if model_data.task:
                        comment_parts.append(f"task: {model_data.task}")
                    package["comment"] = ", ".join(filter(None, comment_parts))

                    # Add external refs for source
                    if model_data.source_url:
                        ext_refs = package.get("externalRefs", [])
                        ext_refs.append(
                            {
                                "referenceCategory": "OTHER",
                                "referenceType": "scanoss-ai-source-url",
                                "referenceLocator": model_data.source_url,
                            }
                        )
                        package["externalRefs"] = ext_refs
            else:
                # SDK/package - enrich from KB
                pkg_data = enricher.lookup_sdk(name)
                if pkg_data:
                    # Add license
                    if pkg_data.license and "licenseConcluded" not in package:
                        package["licenseConcluded"] = pkg_data.license
                        package["licenseDeclared"] = pkg_data.license

                    # Add supplier
                    if pkg_data.author and "supplier" not in package:
                        package["supplier"] = pkg_data.author

                    # Add summary
                    if pkg_data.summary and "summary" not in package:
                        package["summary"] = pkg_data.summary

                    # Add homepage
                    if pkg_data.homepage and "homepage" not in package:
                        package["homepage"] = pkg_data.homepage

    def format(
        self,
        result: ScanResult,
        graph: ComponentGraph | None = None,
        enricher: KBEnricher | None = None,
    ) -> str:
        """Format scan result as SPDX SBOM.

        Args:
            result: Scan result to format.
            graph: Optional component relationship graph for dependencies.
            enricher: Optional KB enricher for metadata lookup.

        Returns:
            SPDX JSON string.
        """
        doc_uuid = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build packages from findings
        # Use dict to allow updating with better info (e.g., version)
        packages_by_name: dict[str, dict[str, Any]] = {}
        relationships: list[dict[str, Any]] = []
        name_to_spdxid: dict[str, str] = {}
        idx = 0

        for finding in result.findings:
            package = self._finding_to_package(finding, idx)
            if not package:
                continue

            name = package["name"]
            existing = packages_by_name.get(name)

            if existing is None:
                # First time seeing this package
                name_to_spdxid[name] = package["SPDXID"]
                packages_by_name[name] = package
                # Add DESCRIBES relationship
                relationships.append(
                    {
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "relatedSpdxElement": package["SPDXID"],
                        "relationshipType": "DESCRIBES",
                    }
                )
                idx += 1
            elif "versionInfo" not in existing and "versionInfo" in package:
                # Existing has no version but new one does - update
                existing["versionInfo"] = package["versionInfo"]
                # Also update PURL in externalRefs if present
                if "externalRefs" in package:
                    existing["externalRefs"] = package["externalRefs"]

        # Enrich packages from KB if available
        if enricher:
            self._enrich_packages(packages_by_name, enricher)

        packages = list(packages_by_name.values())

        # Add file packages and relationships from graph
        if graph:
            # Add file packages for files that use AI SDKs
            file_packages, name_to_spdxid, idx = self._build_file_packages(
                graph, name_to_spdxid, idx
            )
            for pkg in file_packages:
                packages.append(pkg)
                relationships.append(
                    {
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "relatedSpdxElement": pkg["SPDXID"],
                        "relationshipType": "DESCRIBES",
                    }
                )

            # Add dependency relationships
            dep_relationships = self._build_relationships(graph, name_to_spdxid)
            relationships.extend(dep_relationships)

        spdx: dict[str, Any] = {
            "spdxVersion": self.SPDX_VERSION,
            "dataLicense": self.DATA_LICENSE,
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"scanoss-ai-scan-{doc_uuid[:8]}",
            "documentNamespace": f"https://scanoss.com/spdx/{doc_uuid}",
            "creationInfo": {
                "created": timestamp,
                "creators": [f"Tool: scanoss-ai-{__version__}"],
            },
            "packages": packages,
            "relationships": relationships,
        }

        return json.dumps(spdx, indent=self.indent)

    def _build_file_packages(
        self,
        graph: ComponentGraph,
        name_to_spdxid: dict[str, str],
        start_idx: int,
    ) -> tuple[list[dict[str, Any]], dict[str, str], int]:
        """Build file packages from graph for files that use AI SDKs.

        Args:
            graph: Component relationship graph.
            name_to_spdxid: Existing mapping of component names to SPDX IDs.
            start_idx: Starting index for package IDs.

        Returns:
            Tuple of (file packages list, updated name_to_spdxid mapping, next idx).
        """
        file_packages: list[dict[str, Any]] = []
        updated_ids = dict(name_to_spdxid)
        idx = start_idx

        # Find files that contain AI SDK usage
        ai_files: set[str] = set()
        for edge in graph.edges:
            if edge.relationship == "contains" and edge.target in name_to_spdxid:
                ai_files.add(edge.source)

        for file_path in sorted(ai_files):
            # Only include actual file paths, not function paths
            if "::" not in file_path:
                spdx_id = f"SPDXRef-Package-{idx}"
                file_packages.append(
                    {
                        "SPDXID": spdx_id,
                        "name": file_path,
                        "downloadLocation": "NOASSERTION",
                        "filesAnalyzed": False,
                        "primaryPackagePurpose": "SOURCE",
                    }
                )
                updated_ids[file_path] = spdx_id
                idx += 1

        return file_packages, updated_ids, idx

    def _build_relationships(
        self, graph: ComponentGraph, name_to_spdxid: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Build SPDX relationships from component graph.

        Args:
            graph: Component relationship graph.
            name_to_spdxid: Mapping of component names to SPDX IDs.

        Returns:
            List of SPDX relationship objects.
        """
        relationships: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for edge in graph.edges:
            if edge.relationship == "dependsOn":
                source_id = name_to_spdxid.get(edge.source)
                target_id = name_to_spdxid.get(edge.target)

                if source_id and target_id:
                    pair = (source_id, target_id)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        relationships.append(
                            {
                                "spdxElementId": source_id,
                                "relatedSpdxElement": target_id,
                                "relationshipType": "DEPENDS_ON",
                            }
                        )
            elif edge.relationship == "contains":
                source_id = name_to_spdxid.get(edge.source)
                target_id = name_to_spdxid.get(edge.target)

                if source_id and target_id:
                    pair = (source_id, target_id)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        relationships.append(
                            {
                                "spdxElementId": source_id,
                                "relatedSpdxElement": target_id,
                                "relationshipType": "CONTAINS",
                            }
                        )

        return relationships
