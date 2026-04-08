"""CycloneDX SBOM output formatter."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..models import Finding, FindingType, ScanResult


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

    def format(self, result: ScanResult) -> str:
        """Format scan result as CycloneDX SBOM.

        Args:
            result: Scan result to format.

        Returns:
            CycloneDX JSON string.
        """
        # Build components from findings
        components: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for finding in result.findings:
            component = self._finding_to_component(finding)
            if component and component["name"] not in seen_names:
                seen_names.add(component["name"])
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

        return json.dumps(bom, indent=self.indent)
