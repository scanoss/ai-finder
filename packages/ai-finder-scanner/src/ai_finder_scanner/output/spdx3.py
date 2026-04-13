"""SPDX 3.0 SBOM output formatter."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .. import __version__
from ..models import Finding, FindingType, ScanResult

if TYPE_CHECKING:
    from ..analyzers.graph import ComponentGraph
    from ..enrichment.kb_enricher import KBEnricher


class SPDX3Formatter:
    """Format scan results as SPDX 3.0 SBOM."""

    SPDX_VERSION = "3.0.1"
    CONTEXT_URL = "https://spdx.github.io/spdx-spec/v3.0.1/rdf/spdx-context.jsonld"

    def __init__(self, indent: int | None = 2) -> None:
        self.indent = indent

    def _generate_spdx_id(self, prefix: str, name: str) -> str:
        safe_name = name.replace("/", "-").replace("@", "").replace(" ", "-")[:50]
        return f"urn:spdx:{prefix}-{safe_name}-{uuid.uuid4().hex[:8]}"

    def _generate_stable_spdx_id(self, prefix: str, name: str, version: str = "") -> str:
        """Generate a stable (deterministic) SPDX ID for deduplication.

        Args:
            prefix: Element type prefix (e.g., "package", "ai-package").
            name: Element name.
            version: Optional version string to include in ID.

        Returns:
            Deterministic SPDX ID that includes version when provided.
        """
        safe_name = name.replace("/", "-").replace("@", "").replace(" ", "-")[:50]
        if version:
            # Normalize version before using in ID (v1.0.0 → 1.0.0, ^1.2.3 → 1.2.3)
            normalized = self._normalize_version(version)
            safe_version = normalized.replace("/", "-").replace("@", "").replace(" ", "-")[:20]
            return f"urn:spdx:{prefix}-{safe_name}-{safe_version}"
        return f"urn:spdx:{prefix}-{safe_name}"

    def _normalize_path(self, path: str) -> str:
        """Normalize file path for cross-platform consistency.

        Converts Windows backslashes to forward slashes.
        """
        return path.replace("\\", "/")

    def _normalize_version(self, version: str) -> str:
        """Normalize version string for consistent deduplication.

        Handles common variations:
        - Strip leading 'v' or 'V' prefix (v1.0.0 → 1.0.0)
        - Strip semver range prefixes (^1.0.0 → 1.0.0, ~1.2.3 → 1.2.3)
        - Strip comparison operators (>=2.0 → 2.0, ==1.0 → 1.0)
        - Strip whitespace

        Args:
            version: Raw version string.

        Returns:
            Normalized version string.
        """
        v = version.strip()
        # Strip leading v/V prefix
        if v.startswith(("v", "V")) and len(v) > 1 and v[1].isdigit():
            v = v[1:]
        # Strip semver range prefixes
        v = v.lstrip("^~")
        # Strip comparison operators
        for op in (">=", "<=", "==", "!=", ">", "<", "="):
            if v.startswith(op):
                v = v[len(op):]
                break
        return v.strip()

    def _get_phase2_element_name(self, finding: Finding) -> str:
        """Get element name for Phase 2 finding types."""
        if finding.agent_info:
            return f"{finding.agent_info.framework}-agent"
        if finding.embedding_info:
            return f"{finding.embedding_info.provider}-embeddings"
        if finding.vector_store_info:
            return finding.vector_store_info.provider
        if finding.tool_info:
            return finding.tool_info.name
        if finding.guardrail_info:
            return finding.guardrail_info.framework
        if finding.prompt_info:
            return f"prompt-{finding.prompt_info.template_type}"
        return "unknown-component"

    def _create_tool_agent(self) -> dict[str, Any]:
        """Create the Tool agent element for createdBy reference."""
        tool_id = f"urn:spdx:tool-ai-finder-{__version__}"
        return {
            "type": "agent_Tool",
            "spdxId": tool_id,
            "name": f"ai-finder-{__version__}",
            "description": f"AI Finder Scanner version {__version__}",
        }

    def _create_document(
        self, doc_id: str, root_elements: list[str], tool_id: str
    ) -> dict[str, Any]:
        return {
            "type": "SpdxDocument",
            "spdxId": doc_id,
            "creationInfo": {
                "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "createdBy": [tool_id],
                "specVersion": self.SPDX_VERSION,
            },
            "rootElement": root_elements,
        }

    def format(
        self,
        result: ScanResult,
        graph: ComponentGraph | None = None,
        enricher: KBEnricher | None = None,
    ) -> str:
        elements: list[dict[str, Any]] = []
        root_elements: list[str] = []

        # Create the tool agent first (fixes dangling createdBy reference)
        tool_agent = self._create_tool_agent()
        tool_id = tool_agent["spdxId"]
        elements.append(tool_agent)

        # Build elements with deduplication by (type, name, version) to avoid
        # incorrectly merging different versions or element types
        elements_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

        for finding in result.findings:
            element = self._finding_to_element(finding, enricher)
            if not element:
                continue

            # Key by (type, name, version) to keep different versions separate
            elem_type = element["type"]
            name = element["name"]
            version = element.get("software_packageVersion", "")
            key = (elem_type, name, version)
            existing = elements_by_key.get(key)

            if existing is None:
                # First time seeing this element
                elements_by_key[key] = element
            else:
                # Merge metadata from new element into existing
                self._merge_element_metadata(existing, element)

        # Convert dict to list and collect root elements
        for element in elements_by_key.values():
            elements.append(element)
            root_elements.append(element["spdxId"])

        # Build spdxId lookup for relationships - use spdxId as key to avoid
        # collisions when different element types share the same name
        name_to_id: dict[str, str] = {}
        for element in elements_by_key.values():
            name_to_id[element["name"]] = element["spdxId"]
            # Also add by spdxId for direct lookups
            name_to_id[element["spdxId"]] = element["spdxId"]

        # Add file elements and relationships from graph if available
        if graph:
            # Add file elements for files that contain AI components
            file_elements = self._build_file_elements(graph, name_to_id)
            elements.extend(file_elements)

            # Update name_to_id with file elements (files NOT added to rootElement)
            for elem in file_elements:
                name_to_id[elem["name"]] = elem["spdxId"]

            # Build relationships using updated name_to_id
            # Only include supported SPDX 3.0 relationship types
            relationships = self._build_relationships_with_lookup(graph, name_to_id)
            elements.extend(relationships)

        doc_id = f"urn:spdx:document-{uuid.uuid4().hex[:12]}"
        doc = self._create_document(doc_id, root_elements, tool_id)
        elements.insert(0, doc)

        spdx: dict[str, Any] = {
            "@context": self.CONTEXT_URL,
            "@graph": elements,
        }

        return json.dumps(spdx, indent=self.indent)

    def _is_sentinel_value(self, value: Any) -> bool:
        """Check if a value is a sentinel/placeholder that should be replaced."""
        return value in ("NOASSERTION", "", None)

    def _merge_element_metadata(
        self, existing: dict[str, Any], new: dict[str, Any]
    ) -> None:
        """Merge metadata from new element into existing element.

        Args:
            existing: Existing element dict (modified in place).
            new: New element with potentially additional metadata.
        """
        # Fields to merge - replace if missing OR if existing has sentinel value
        merge_fields = [
            "software_packageVersion",
            "software_declaredLicense",
            "software_downloadLocation",
            "summary",
            "ai_domain",
            "ai_typeOfModel",
            "dataset_datasetType",
            "dataset_intendedUse",
        ]

        for field in merge_fields:
            new_value = new.get(field)
            if new_value and not self._is_sentinel_value(new_value):
                existing_value = existing.get(field)
                # Replace if missing or existing is a sentinel
                if field not in existing or self._is_sentinel_value(existing_value):
                    existing[field] = new_value

        # Special handling for comments - always append
        if "comment" in new:
            existing_comment = existing.get("comment", "")
            new_comment = new["comment"]
            if new_comment and new_comment not in existing_comment:
                existing["comment"] = (
                    f"{existing_comment}; {new_comment}"
                    if existing_comment
                    else new_comment
                )

        # Merge hyperparameters for AI packages
        if "ai_hyperparameter" in new and "ai_hyperparameter" not in existing:
            existing["ai_hyperparameter"] = new["ai_hyperparameter"]

    def _build_file_elements(
        self,
        graph: ComponentGraph,
        name_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Build SPDX 3.0 File elements for files that contain AI components.

        Args:
            graph: Component relationship graph.
            name_to_id: Mapping of component names/spdxIds to SPDX IDs.

        Returns:
            List of software_File elements.
        """
        file_elements: list[dict[str, Any]] = []

        # Find files that contain AI SDK usage
        ai_files: set[str] = set()
        for edge in graph.edges:
            if edge.relationship == "contains" and edge.target in name_to_id:
                ai_files.add(edge.source)

        for file_path in sorted(ai_files):
            # Only include actual file paths, not function paths
            if "::" not in file_path:
                # Normalize path for cross-platform consistency
                normalized_path = self._normalize_path(file_path)
                file_elements.append({
                    "type": "software_File",
                    "spdxId": self._generate_stable_spdx_id("file", normalized_path),
                    "name": normalized_path,
                })

        return file_elements

    def _build_relationships_with_lookup(
        self,
        graph: ComponentGraph,
        name_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Build SPDX 3.0 Relationship elements from graph.

        Args:
            graph: Component relationship graph.
            name_to_id: Mapping of component names to SPDX IDs.

        Returns:
            List of Relationship elements.
        """
        relationships: list[dict[str, Any]] = []

        # Only include valid SPDX 3.0 relationship types
        valid_rel_types = {
            "dependsOn": "DEPENDS_ON",
            "contains": "CONTAINS",
        }

        # Add relationships from graph edges (ComponentEdge dataclass)
        for edge in graph.edges:
            # Skip unsupported relationship types (like "calls")
            if edge.relationship not in valid_rel_types:
                continue

            from_id = name_to_id.get(edge.source)
            to_id = name_to_id.get(edge.target)

            if from_id and to_id:
                rel_type = valid_rel_types[edge.relationship]
                relationships.append({
                    "type": "Relationship",
                    "spdxId": self._generate_spdx_id("rel", f"{edge.source}-{edge.target}"),
                    "relationshipType": rel_type,
                    "from": from_id,
                    "to": [to_id],
                })

        return relationships

    def _finding_to_element(
        self,
        finding: Finding,
        enricher: KBEnricher | None = None,
    ) -> dict[str, Any] | None:
        if finding.type == FindingType.SDK_USAGE and finding.sdk_usage:
            sdk = finding.sdk_usage
            version = sdk.version or ""
            element: dict[str, Any] = {
                "type": "software_Package",
                "spdxId": self._generate_stable_spdx_id("package", sdk.sdk, version),
                "name": sdk.sdk,
                "software_downloadLocation": "NOASSERTION",
            }
            # Only include version if present (null is invalid in SPDX 3.0)
            if sdk.version:
                element["software_packageVersion"] = sdk.version
            # Enrich from KB if available
            if enricher:
                self._enrich_package(element, sdk.sdk, enricher)
            return element

        if finding.type == FindingType.MANIFEST_DEP and finding.manifest_dep:
            dep = finding.manifest_dep
            version = dep.version or ""
            element = {
                "type": "software_Package",
                "spdxId": self._generate_stable_spdx_id("package", dep.name, version),
                "name": dep.name,
                "software_downloadLocation": "NOASSERTION",
            }
            # Only include version if present (null is invalid in SPDX 3.0)
            if dep.version:
                element["software_packageVersion"] = dep.version
            # Enrich from KB if available
            if enricher:
                self._enrich_package(element, dep.name, enricher)
            return element

        if finding.type == FindingType.MODEL_FILE and finding.model_info:
            return self._model_to_ai_package(finding, enricher)

        # Handle DATASET as dataset_DatasetPackage
        if finding.type == FindingType.DATASET and finding.dataset_info:
            ds_info = finding.dataset_info
            ds_name = ds_info.name or f"{ds_info.source}-dataset"
            dataset_element: dict[str, Any] = {
                "type": "dataset_DatasetPackage",
                "spdxId": self._generate_stable_spdx_id("dataset", ds_name),
                "name": ds_name,
                "dataset_datasetType": "text",
            }
            if ds_info.split:
                dataset_element["dataset_intendedUse"] = f"Model {ds_info.split}ing"
            return dataset_element

        # Handle MCP types as software_Package
        if finding.type in (FindingType.MCP_SERVER, FindingType.MCP_CLIENT):
            if finding.ai_component:
                name = finding.ai_component.name
            else:
                name = "mcp-server" if finding.type == FindingType.MCP_SERVER else "mcp-client"
            mcp_role = "server" if finding.type == FindingType.MCP_SERVER else "client"
            return {
                "type": "software_Package",
                "spdxId": self._generate_stable_spdx_id("package", name),
                "name": name,
                "software_downloadLocation": "NOASSERTION",
                # Human-readable description
                "summary": f"Model Context Protocol (MCP) {mcp_role}",
                # Machine-readable: use comment with structured format
                # (SPDX 3.0 externalIdentifier requires vocabulary compliance)
                "comment": f"ai-finder:mcp:role={mcp_role}",
            }

        # Handle other Phase 2 types as software_Package
        if finding.type in (
            FindingType.AGENT,
            FindingType.TOOL,
            FindingType.EMBEDDING,
            FindingType.VECTOR_STORE,
            FindingType.PROMPT,
            FindingType.GUARDRAIL,
        ):
            name = self._get_phase2_element_name(finding)
            return {
                "type": "software_Package",
                "spdxId": self._generate_stable_spdx_id("package", name),
                "name": name,
                "software_downloadLocation": "NOASSERTION",
            }

        return None

    def _enrich_package(
        self,
        element: dict[str, Any],
        name: str,
        enricher: KBEnricher,
    ) -> None:
        """Enrich a software_Package element with KB metadata.

        Args:
            element: Element dict to enrich (modified in place).
            name: Package name for KB lookup.
            enricher: KB enricher instance.
        """
        pkg_data = enricher.lookup_sdk(name)
        if pkg_data:
            # Add license as declared license (SPDX 3.0 style)
            if pkg_data.license:
                element["software_declaredLicense"] = pkg_data.license

            # Add supplier info in comment (avoids dangling agent reference)
            if pkg_data.author:
                existing_comment = element.get("comment", "")
                author_comment = f"Author: {pkg_data.author}"
                element["comment"] = (
                    f"{existing_comment}; {author_comment}"
                    if existing_comment
                    else author_comment
                )

            # Add description
            if pkg_data.summary:
                element["summary"] = pkg_data.summary

            # Add homepage as download location if we have NOASSERTION
            if pkg_data.homepage and element.get("software_downloadLocation") == "NOASSERTION":
                element["software_downloadLocation"] = pkg_data.homepage

    def _model_to_ai_package(
        self,
        finding: Finding,
        enricher: KBEnricher | None = None,
    ) -> dict[str, Any]:
        info = finding.model_info
        # Use full path to avoid collisions between models with same filename
        # in different directories (e.g., models/v1/model.bin vs models/v2/model.bin)
        # Normalize path for cross-platform consistency (Windows backslashes → forward slashes)
        model_path = self._normalize_path(finding.file_path)
        filename = model_path.split("/")[-1]

        element: dict[str, Any] = {
            "type": "ai_AIPackage",
            "spdxId": self._generate_stable_spdx_id("ai-package", model_path),
            "name": model_path,
            "ai_autonomyType": "assistive",
        }

        if info:
            if info.architecture:
                element["ai_typeOfModel"] = info.architecture
            element["ai_domain"] = self._infer_domain(info.architecture)

            hyperparams = []
            if info.parameter_count:
                hyperparams.append({"name": "parameter_count", "value": str(info.parameter_count)})
            if info.quantization:
                hyperparams.append({"name": "quantization", "value": info.quantization})
            if hyperparams:
                element["ai_hyperparameter"] = hyperparams

        # Enrich from KB if available
        if enricher:
            model_data = enricher.lookup_model(filename)
            if model_data:
                if model_data.license:
                    element["software_declaredLicense"] = model_data.license
                if model_data.source_url:
                    element["software_downloadLocation"] = model_data.source_url
                if model_data.task and "ai_domain" not in element:
                    element["ai_domain"] = model_data.task

        return element

    def _infer_domain(self, architecture: str | None) -> str:
        if not architecture:
            return "NOASSERTION"

        arch_lower = architecture.lower()

        if any(p in arch_lower for p in ["llama", "gpt", "mistral", "phi", "gemma"]):
            return "text-generation"
        if any(p in arch_lower for p in ["bert", "embed"]):
            return "embedding"
        if any(p in arch_lower for p in ["whisper", "wav2vec"]):
            return "speech-to-text"
        if any(p in arch_lower for p in ["stable-diffusion", "sdxl"]):
            return "image-generation"
        if any(p in arch_lower for p in ["resnet", "vgg", "yolo"]):
            return "image-classification"

        return "NOASSERTION"
