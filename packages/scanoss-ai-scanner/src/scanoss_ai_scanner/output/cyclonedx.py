"""CycloneDX SBOM output formatter."""

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


class CycloneDXFormatter:
    """Format scan results as CycloneDX SBOM."""

    SPEC_VERSION = "1.5"
    BOM_FORMAT = "CycloneDX"

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

    def _generate_bom_ref(self, name: str) -> str:
        """Generate a bom-ref for a component."""
        return f"pkg:{name.replace('/', '-').replace('@', '')}"

    def _infer_purl_type_from_sdk(self, sdk_name: str) -> str:
        """Infer PURL type from SDK name pattern.

        Args:
            sdk_name: SDK name or import path.

        Returns:
            PURL type string (pypi, npm, golang, etc.)
        """
        # Go modules start with domain paths
        if sdk_name.startswith("github.com/") or sdk_name.startswith("golang.org/"):
            return "golang"
        # npm scoped packages
        if sdk_name.startswith("@"):
            return "npm"
        # Rust crates (typically lowercase with hyphens, async- prefix common)
        if sdk_name.startswith("async-") or sdk_name.endswith("-rs"):
            return "cargo"
        # Default to pypi for Python-style names
        return "pypi"

    def _infer_purl_type_from_manifest(self, manifest_file: str) -> str:
        """Infer PURL type from manifest filename.

        Args:
            manifest_file: Path to manifest file.

        Returns:
            PURL type string.
        """
        filename = manifest_file.split("/")[-1]

        # Check exact matches first
        if filename in self.MANIFEST_PURL_TYPES:
            return self.MANIFEST_PURL_TYPES[filename]

        # Check for .csproj files
        if filename.endswith(".csproj"):
            return "nuget"

        # Default to pypi
        return "pypi"

    def _finding_to_component(self, finding: Finding) -> dict[str, Any] | None:
        """Convert a finding to a CycloneDX component.

        Args:
            finding: Finding to convert.

        Returns:
            Component dict or None if not applicable.
        """
        if finding.type == FindingType.SDK_USAGE and finding.sdk_usage:
            sdk = finding.sdk_usage
            component: dict[str, Any] = {
                "type": "library",
                "name": sdk.sdk,
            }
            if sdk.version:
                component["version"] = sdk.version
            # Generate PURL based on SDK name pattern
            purl_type = self._infer_purl_type_from_sdk(sdk.sdk)
            component["purl"] = f"pkg:{purl_type}/{sdk.sdk}"
            return component

        if finding.type == FindingType.MANIFEST_DEP and finding.manifest_dep:
            dep = finding.manifest_dep
            component = {
                "type": "library",
                "name": dep.name,
            }
            if dep.version:
                # Clean version specifiers for CycloneDX (strip leading operators)
                version = re.sub(r"^[>=<~^]+", "", dep.version)
                if version:
                    component["version"] = version
            # Generate PURL based on manifest type
            purl_type = self._infer_purl_type_from_manifest(dep.manifest_file)
            component["purl"] = f"pkg:{purl_type}/{dep.name}"
            return component

        if finding.type == FindingType.MODEL_FILE and finding.model_info:
            info = finding.model_info
            filename = finding.file_path.split("/")[-1]
            component: dict[str, Any] = {
                "type": "machine-learning-model",
                "name": filename,
            }

            # Build modelCard per CycloneDX 1.5 ML-BOM spec
            model_params: dict[str, Any] = {}

            # Map our architecture to CycloneDX modelArchitecture
            if info.architecture:
                model_params["modelArchitecture"] = info.architecture
                # Infer architecture family from known architectures
                arch_families = {
                    "llama": "transformer",
                    "mistral": "transformer",
                    "mixtral": "transformer",
                    "phi": "transformer",
                    "gemma": "transformer",
                    "qwen": "transformer",
                    "falcon": "transformer",
                    "gpt": "transformer",
                    "bert": "transformer",
                    "t5": "transformer",
                    "resnet": "convolutional neural network",
                    "yolo": "convolutional neural network",
                    "vgg": "convolutional neural network",
                    "lstm": "recurrent neural network",
                }
                for pattern, family in arch_families.items():
                    if pattern in info.architecture.lower():
                        model_params["architectureFamily"] = family
                        break

            # Add format-specific info
            if info.format:
                # Use description for format since CycloneDX doesn't have a format field
                component["description"] = f"Model format: {info.format}"
                if info.quantization:
                    component["description"] += f", quantization: {info.quantization}"

            # Add modelCard if we have model parameters
            if model_params:
                component["modelCard"] = {"modelParameters": model_params}

            # Add properties for additional metadata not in modelCard
            properties = []
            if info.format:
                properties.append({"name": "scanoss:model:format", "value": info.format})
            if info.quantization:
                properties.append(
                    {"name": "scanoss:model:quantization", "value": info.quantization}
                )
            if info.parameter_count:
                properties.append(
                    {"name": "scanoss:model:parameters", "value": str(info.parameter_count)}
                )
            if properties:
                component["properties"] = properties

            return component

        return None

    def _enrich_components(
        self,
        components: dict[str, dict[str, Any]],
        enricher: KBEnricher,
    ) -> None:
        """Enrich components with KB metadata.

        Args:
            components: Dict of component name to component dict (modified in place).
            enricher: KB enricher instance.
        """
        for name, component in components.items():
            comp_type = component.get("type")

            if comp_type == "machine-learning-model":
                # Enrich model from KB
                model_data = enricher.lookup_model(name)
                if model_data:
                    # Update PURL if we have a better one
                    if model_data.purl:
                        component["purl"] = model_data.purl

                    # Add license if not present
                    if model_data.license and "licenses" not in component:
                        component["licenses"] = [{"license": {"id": model_data.license}}]

                    # Update modelCard with KB data
                    model_card = component.get("modelCard", {})
                    model_params = model_card.get("modelParameters", {})

                    if model_data.architecture and "modelArchitecture" not in model_params:
                        model_params["modelArchitecture"] = model_data.architecture
                    if model_data.architecture_family and "architectureFamily" not in model_params:
                        model_params["architectureFamily"] = model_data.architecture_family
                    if model_data.task and "task" not in model_params:
                        model_params["task"] = model_data.task

                    if model_params:
                        model_card["modelParameters"] = model_params
                        component["modelCard"] = model_card

                    # Add properties for additional metadata
                    properties = component.get("properties", [])
                    has_params = any(p["name"] == "scanoss:model:parameters" for p in properties)
                    if model_data.parameter_count and not has_params:
                        properties.append(
                            {
                                "name": "scanoss:model:parameters",
                                "value": str(model_data.parameter_count),
                            }
                        )
                    if model_data.source_url:
                        properties.append(
                            {
                                "name": "scanoss:model:source_url",
                                "value": model_data.source_url,
                            }
                        )
                    if model_data.base_model_purl:
                        properties.append(
                            {
                                "name": "scanoss:model:base_model",
                                "value": model_data.base_model_purl,
                            }
                        )
                    if properties:
                        component["properties"] = properties

            elif comp_type == "library":
                # Enrich SDK/package from KB
                pkg_data = enricher.lookup_sdk(name)
                if pkg_data:
                    # Add license if not present
                    if pkg_data.license and "licenses" not in component:
                        component["licenses"] = [{"license": {"id": pkg_data.license}}]

                    # Add supplier/author
                    if pkg_data.author and "supplier" not in component:
                        component["supplier"] = {"name": pkg_data.author}

                    # Add description
                    if pkg_data.summary and "description" not in component:
                        component["description"] = pkg_data.summary

                    # Add external reference for homepage
                    if pkg_data.homepage:
                        ext_refs = component.get("externalReferences", [])
                        ext_refs.append(
                            {
                                "type": "website",
                                "url": pkg_data.homepage,
                            }
                        )
                        component["externalReferences"] = ext_refs

    def format(
        self,
        result: ScanResult,
        graph: ComponentGraph | None = None,
        enricher: KBEnricher | None = None,
    ) -> str:
        """Format scan result as CycloneDX SBOM.

        Args:
            result: Scan result to format.
            graph: Optional component relationship graph for dependencies.
            enricher: Optional KB enricher for metadata lookup.

        Returns:
            CycloneDX JSON string.
        """
        # Build components from findings
        # Use dict to allow updating with better info (e.g., version)
        components_by_name: dict[str, dict[str, Any]] = {}
        name_to_ref: dict[str, str] = {}

        for finding in result.findings:
            component = self._finding_to_component(finding)
            if not component:
                continue

            name = component["name"]
            existing = components_by_name.get(name)

            # Add or update component - prefer one with version
            if existing is None:
                # First time seeing this component
                bom_ref = self._generate_bom_ref(name)
                component["bom-ref"] = bom_ref
                name_to_ref[name] = bom_ref
                components_by_name[name] = component
            elif "version" not in existing and "version" in component:
                # Existing has no version but new one does - update
                existing["version"] = component["version"]
                # Also update PURL if new component has better type
                if "purl" in component:
                    existing["purl"] = component["purl"]

        # Enrich components from KB if available
        if enricher:
            self._enrich_components(components_by_name, enricher)

        components = list(components_by_name.values())

        bom: dict[str, Any] = {
            "bomFormat": self.BOM_FORMAT,
            "specVersion": self.SPEC_VERSION,
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tools": [
                    {
                        "vendor": "SCANOSS",
                        "name": "scanoss-ai",
                        "version": __version__,
                    }
                ],
            },
            "components": components,
        }

        # Add file components and dependencies from graph if provided
        if graph:
            # Add file components for files that use AI SDKs
            file_components, name_to_ref = self._build_file_components(graph, name_to_ref)
            components.extend(file_components)

            # Build dependencies
            dependencies = self._build_dependencies(graph, name_to_ref)
            if dependencies:
                bom["dependencies"] = dependencies

        return json.dumps(bom, indent=self.indent)

    def _build_file_components(
        self, graph: ComponentGraph, name_to_ref: dict[str, str]
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Build file components from graph for files that use AI SDKs.

        Args:
            graph: Component relationship graph.
            name_to_ref: Existing mapping of component names to bom-refs.

        Returns:
            Tuple of (file components list, updated name_to_ref mapping).
        """
        file_components: list[dict[str, Any]] = []
        updated_refs = dict(name_to_ref)

        # Find files that contain AI SDK usage
        ai_files: set[str] = set()
        for edge in graph.edges:
            if edge.relationship == "contains" and edge.target in name_to_ref:
                ai_files.add(edge.source)

        for file_path in sorted(ai_files):
            # Only include actual file paths, not function paths
            if "::" not in file_path:
                bom_ref = f"pkg:file/{file_path.replace('/', '-')}"
                file_components.append(
                    {
                        "type": "file",
                        "name": file_path,
                        "bom-ref": bom_ref,
                    }
                )
                updated_refs[file_path] = bom_ref

        return file_components, updated_refs

    def _build_dependencies(
        self, graph: ComponentGraph, name_to_ref: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Build CycloneDX dependencies from component graph.

        Args:
            graph: Component relationship graph.
            name_to_ref: Mapping of component names to bom-refs.

        Returns:
            List of CycloneDX dependency objects.
        """
        from collections import defaultdict

        # Group edges by source
        source_to_targets: dict[str, set[str]] = defaultdict(set)

        for edge in graph.edges:
            # Handle both dependsOn and contains relationships
            if edge.relationship in ("dependsOn", "contains"):
                # Map source and target to bom-refs
                source_ref = name_to_ref.get(edge.source)
                target_ref = name_to_ref.get(edge.target)

                if source_ref and target_ref:
                    source_to_targets[source_ref].add(target_ref)

        # Build dependency list
        dependencies: list[dict[str, Any]] = []
        for ref, depends_on in source_to_targets.items():
            dependencies.append({"ref": ref, "dependsOn": sorted(depends_on)})

        return dependencies
