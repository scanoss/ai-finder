"""SPDX SBOM output formatter."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..models import Finding, FindingType, ScanResult

if TYPE_CHECKING:
    from ..analyzers.graph import ComponentGraph


class SPDXFormatter:
    """Format scan results as SPDX SBOM."""

    SPDX_VERSION = "SPDX-2.3"
    DATA_LICENSE = "CC0-1.0"

    def __init__(self, indent: int | None = 2) -> None:
        """Initialize formatter.

        Args:
            indent: JSON indentation level.
        """
        self.indent = indent

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
            package["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:pypi/{sdk.sdk}",
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
                version = dep.version.lstrip(">=<~^")
                if version:
                    package["versionInfo"] = version
            # Generate PURL based on manifest type
            purl_type = "npm" if "package.json" in dep.manifest_file else "pypi"
            package["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:{purl_type}/{dep.name}",
                }
            ]
            return package

        if finding.type == FindingType.MODEL_FILE and finding.model_info:
            package = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": finding.file_path.split("/")[-1],
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "primaryPackagePurpose": "APPLICATION",
            }
            if finding.model_info.format:
                package["comment"] = f"AI model file, format: {finding.model_info.format}"
            return package

        return None

    def format(
        self, result: ScanResult, graph: "ComponentGraph | None" = None
    ) -> str:
        """Format scan result as SPDX SBOM.

        Args:
            result: Scan result to format.
            graph: Optional component relationship graph for dependencies.

        Returns:
            SPDX JSON string.
        """
        doc_uuid = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build packages from findings
        packages: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        name_to_spdxid: dict[str, str] = {}
        idx = 0

        for finding in result.findings:
            package = self._finding_to_package(finding, idx)
            if package and package["name"] not in seen_names:
                seen_names.add(package["name"])
                name_to_spdxid[package["name"]] = package["SPDXID"]
                packages.append(package)
                # Add DESCRIBES relationship
                relationships.append(
                    {
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "relatedSpdxElement": package["SPDXID"],
                        "relationshipType": "DESCRIBES",
                    }
                )
                idx += 1

        # Add DEPENDS_ON relationships from graph
        if graph:
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
                "creators": ["Tool: scanoss-ai-0.1.0"],
            },
            "packages": packages,
            "relationships": relationships,
        }

        return json.dumps(spdx, indent=self.indent)

    def _build_relationships(
        self, graph: "ComponentGraph", name_to_spdxid: dict[str, str]
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
