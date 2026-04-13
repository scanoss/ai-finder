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

    def _generate_stable_spdx_id(self, prefix: str, name: str) -> str:
        """Generate a stable (deterministic) SPDX ID for deduplication."""
        safe_name = name.replace("/", "-").replace("@", "").replace(" ", "-")[:50]
        return f"urn:spdx:{prefix}-{safe_name}"

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
        tool_id = f"urn:spdx:tool-scanoss-ai-{__version__}"
        return {
            "type": "Tool",
            "spdxId": tool_id,
            "name": "scanoss-ai",
            "software_packageVersion": __version__,
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

        # Build elements with deduplication (like SPDX 2.3)
        elements_by_name: dict[str, dict[str, Any]] = {}

        for finding in result.findings:
            element = self._finding_to_element(finding, enricher)
            if not element:
                continue

            name = element["name"]
            existing = elements_by_name.get(name)

            if existing is None:
                # First time seeing this element
                elements_by_name[name] = element
            elif (
                "software_packageVersion" not in existing
                and "software_packageVersion" in element
            ):
                # Existing has no version but new one does - update
                existing["software_packageVersion"] = element["software_packageVersion"]

        # Convert dict to list and collect root elements
        for element in elements_by_name.values():
            elements.append(element)
            root_elements.append(element["spdxId"])

        # Build name->spdxId lookup for relationships
        name_to_id = {e["name"]: e["spdxId"] for e in elements_by_name.values()}

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

    def _build_file_elements(
        self,
        graph: ComponentGraph,
        name_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Build SPDX 3.0 File elements for files that contain AI components.

        Args:
            graph: Component relationship graph.
            name_to_id: Mapping of component names to SPDX IDs.

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
                file_elements.append({
                    "type": "software_File",
                    "spdxId": self._generate_stable_spdx_id("file", file_path),
                    "name": file_path,
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
            element: dict[str, Any] = {
                "type": "software_Package",
                "spdxId": self._generate_stable_spdx_id("package", sdk.sdk),
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
            element = {
                "type": "software_Package",
                "spdxId": self._generate_stable_spdx_id("package", dep.name),
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
            info = finding.dataset_info
            name = info.name or f"{info.source}-dataset"
            element: dict[str, Any] = {
                "type": "dataset_DatasetPackage",
                "spdxId": self._generate_stable_spdx_id("dataset", name),
                "name": name,
                "dataset_datasetType": "text",
            }
            if info.split:
                element["dataset_intendedUse"] = f"Model {info.split}ing"
            return element

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
                "comment": f"scanoss:mcp:role={mcp_role}",
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
        filename = finding.file_path.split("/")[-1]

        element: dict[str, Any] = {
            "type": "ai_AIPackage",
            "spdxId": self._generate_stable_spdx_id("ai-package", filename),
            "name": filename,
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
