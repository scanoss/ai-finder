"""CycloneDX SBOM output formatter."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..models import Finding, FindingType, ScanResult

if TYPE_CHECKING:
    from ..analyzers.graph import ComponentGraph


class CycloneDXFormatter:
    """Format scan results as CycloneDX SBOM."""

    SPEC_VERSION = "1.5"
    BOM_FORMAT = "CycloneDX"

    def __init__(self, indent: int | None = 2) -> None:
        """Initialize formatter.

        Args:
            indent: JSON indentation level.
        """
        self.indent = indent

    def _generate_bom_ref(self, name: str) -> str:
        """Generate a bom-ref for a component."""
        return f"pkg:{name.replace('/', '-').replace('@', '')}"

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
            # Generate PURL based on SDK name
            component["purl"] = f"pkg:pypi/{sdk.sdk}"
            return component

        if finding.type == FindingType.MANIFEST_DEP and finding.manifest_dep:
            dep = finding.manifest_dep
            component = {
                "type": "library",
                "name": dep.name,
            }
            if dep.version:
                # Clean version specifiers for CycloneDX
                version = dep.version.lstrip(">=<~^")
                if version:
                    component["version"] = version
            # Generate PURL based on manifest type
            if "package.json" in dep.manifest_file:
                component["purl"] = f"pkg:npm/{dep.name}"
            else:
                component["purl"] = f"pkg:pypi/{dep.name}"
            return component

        if finding.type == FindingType.MODEL_FILE and finding.model_info:
            info = finding.model_info
            component = {
                "type": "machine-learning-model",
                "name": finding.file_path.split("/")[-1],
            }
            if info.format:
                component["description"] = f"Format: {info.format}"
            return component

        return None

    def format(
        self, result: ScanResult, graph: "ComponentGraph | None" = None
    ) -> str:
        """Format scan result as CycloneDX SBOM.

        Args:
            result: Scan result to format.
            graph: Optional component relationship graph for dependencies.

        Returns:
            CycloneDX JSON string.
        """
        # Build components from findings
        components: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        name_to_ref: dict[str, str] = {}

        for finding in result.findings:
            component = self._finding_to_component(finding)
            if component and component["name"] not in seen_names:
                seen_names.add(component["name"])
                # Add bom-ref for dependency tracking
                bom_ref = self._generate_bom_ref(component["name"])
                component["bom-ref"] = bom_ref
                name_to_ref[component["name"]] = bom_ref
                components.append(component)

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
                        "version": "0.1.0",
                    }
                ],
            },
            "components": components,
        }

        # Add dependencies from graph if provided
        if graph:
            dependencies = self._build_dependencies(graph, name_to_ref)
            if dependencies:
                bom["dependencies"] = dependencies

        return json.dumps(bom, indent=self.indent)

    def _build_dependencies(
        self, graph: "ComponentGraph", name_to_ref: dict[str, str]
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
            if edge.relationship == "dependsOn":
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
