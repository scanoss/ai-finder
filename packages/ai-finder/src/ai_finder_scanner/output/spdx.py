"""SPDX SBOM output formatter."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from ai_finder_kb.matcher import purl_ecosystem, purl_name

from .. import __version__
from ..models import Finding, FindingType, ScanResult

if TYPE_CHECKING:
    from ..analyzers.graph import ComponentGraph
    from ..enrichment.kb_enricher import KBEnricher


class SPDX23Formatter:
    """Format scan results as SPDX 2.3 SBOM."""

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

    def _normalize_path(self, path: str) -> str:
        """Normalize file path for cross-platform consistency.

        Converts Windows backslashes to forward slashes.
        """
        return path.replace("\\", "/")

    def _infer_purl_type_from_manifest(self, manifest_file: str) -> str:
        """Infer PURL type from manifest filename."""
        filename = manifest_file.split("/")[-1]
        if filename in self.MANIFEST_PURL_TYPES:
            return self.MANIFEST_PURL_TYPES[filename]
        if filename.endswith(".csproj"):
            return "nuget"
        return "pypi"

    def _build_purl(self, purl_type: str, name: str, version: str | None = None) -> str:
        """Build a valid PURL with proper encoding.

        Args:
            purl_type: PURL type (pypi, npm, golang, etc.)
            name: Package name (may include scope for npm)
            version: Optional version string

        Returns:
            Valid PURL string per https://github.com/package-url/purl-spec
        """
        # Handle npm scoped packages: @scope/name -> namespace/name
        if purl_type == "npm" and name.startswith("@"):
            parts = name[1:].split("/", 1)
            if len(parts) == 2:
                namespace = quote(parts[0], safe="")
                pkg_name = quote(parts[1], safe="")
                purl = f"pkg:{purl_type}/{namespace}/{pkg_name}"
            else:
                purl = f"pkg:{purl_type}/{quote(name, safe='')}"
        elif purl_type == "golang":
            purl = f"pkg:{purl_type}/{quote(name, safe='/')}"
        else:
            purl = f"pkg:{purl_type}/{quote(name, safe='')}"

        # Append version if present
        if version:
            clean_version = re.sub(r"^[>=<~^]+", "", version)
            if clean_version:
                purl = f"{purl}@{quote(clean_version, safe='')}"

        return purl

    def _purl_for(self, purl_type: str, name: str, purl: str | None, version: str | None) -> str:
        """Same purl convention as the CycloneDX formatter (see its `_purl_for`)."""
        if purl_type == "npm" or not purl:
            return self._build_purl(purl_type, name, version)
        base, sep, qualifiers = purl.partition("?")
        last = base.rsplit("/", 1)[-1]
        if version and "@" not in last:
            base = f"{base}@{quote(re.sub(r'^[>=<~^]+', '', version), safe='')}"
        return base + sep + qualifiers

    @staticmethod
    def _identity(package: dict[str, Any]) -> str:
        """Registry and name for a package with a purl, so npm `openai` and PyPI
        `openai` stay two packages and an import merges with its manifest entry;
        the bare name otherwise."""
        name = package["name"]
        purl = next(
            (
                ref["referenceLocator"]
                for ref in package.get("externalRefs", [])
                if ref.get("referenceType") == "purl"
            ),
            None,
        )
        eco = purl_ecosystem(purl)
        if not eco:
            return f"name:{name}"
        key_name = name.lower()
        if eco == "pypi":
            key_name = re.sub(r"[-_.]+", "-", key_name)
        return f"{eco}:{key_name}"

    @staticmethod
    def _seen_at(finding: Finding) -> str:
        """`path:line (how)` for one finding; SPDX 2.3 has no occurrence field."""
        where = finding.file_path.replace("\\", "/")
        if finding.line:
            where += f":{finding.line}"
        how = None
        if finding.sdk_usage:
            how = finding.sdk_usage.import_statement
        elif finding.mcp_info:
            how = finding.mcp_info.how
        if how:
            where += f" ({' '.join(how.split())[:120]})"
        return where

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
            if sdk.purl:
                # Resolved by the KB: name the package, not the import.
                purl_type = purl_ecosystem(sdk.purl) or "generic"
                sdk_name = purl_name(sdk.purl)
                locator = self._purl_for(purl_type, sdk_name, sdk.purl, sdk.version)
            else:
                sdk_name = sdk.sdk
                purl_type = self._infer_purl_type_from_sdk(sdk.sdk)
                locator = self._build_purl(purl_type, sdk.sdk, sdk.version)
            package: dict[str, Any] = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": sdk_name,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
            }
            if sdk.version:
                package["versionInfo"] = sdk.version
            package["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": locator,
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
            # Generate PURL with proper encoding
            purl_type = self._infer_purl_type_from_manifest(dep.manifest_file)
            package["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": self._build_purl(purl_type, dep.name, dep.version),
                }
            ]
            return package

        if finding.type == FindingType.MODEL_FILE and finding.model_info:
            info = finding.model_info
            package = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                # Full normalized path, not the basename: format() keys packages by
                # name, so two shards both called model.safetensors in different
                # directories would collapse into the first one seen and the second
                # model would be missing from the SBOM entirely, checksum included.
                # spdx3.py already does this; cyclonedx.py now matches.
                "name": self._normalize_path(finding.file_path),
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

            # Content hash, when the scanner computed one. Doubles as the key
            # _enrich_packages uses to resolve this package by hash, which is the
            # only thing that identifies a generically named shard.
            if info.sha256:
                package["checksums"] = [{"algorithm": "SHA256", "checksumValue": info.sha256}]

            # Add external references for model metadata (SPDX 2.3 compatible)
            # Using OTHER category for AI/ML specific references
            ext_refs = []
            if info.format:
                ext_refs.append(
                    {
                        "referenceCategory": "OTHER",
                        "referenceType": "ai-finder-model-format",
                        "referenceLocator": info.format,
                    }
                )
            if info.architecture:
                ext_refs.append(
                    {
                        "referenceCategory": "OTHER",
                        "referenceType": "ai-finder-model-architecture",
                        "referenceLocator": info.architecture,
                    }
                )
            if ext_refs:
                package["externalRefs"] = ext_refs

            return package

        # Handle MCP types
        if finding.type in (FindingType.MCP_SERVER, FindingType.MCP_CLIENT):
            mcp = finding.mcp_info
            mcp_role = "server" if finding.type == FindingType.MCP_SERVER else "client"
            if mcp is not None:
                name = mcp.name
            elif finding.ai_component:
                name = finding.ai_component.name
            else:
                name = f"mcp-{mcp_role}"
            comment = f"MCP {mcp_role}"
            if mcp is not None:
                comment += f", found in {mcp.source}"
                if mcp.transport:
                    comment += f", {mcp.transport} transport"
            package = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": name,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "comment": comment,
                "externalRefs": [
                    {
                        "referenceCategory": "OTHER",
                        "referenceType": "ai-finder-mcp-role",
                        "referenceLocator": mcp_role,
                    }
                ],
            }
            if mcp is not None and mcp.purl:
                purl_type = purl_ecosystem(mcp.purl) or "generic"
                pkg = mcp.package or purl_name(mcp.purl)
                package["externalRefs"].append(
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": self._purl_for(purl_type, pkg, mcp.purl, mcp.version),
                    }
                )
                if mcp.version:
                    package["versionInfo"] = mcp.version
            return package

        # Handle Phase 2 types as packages
        if finding.type in (
            FindingType.AGENT,
            FindingType.TOOL,
            FindingType.EMBEDDING,
            FindingType.VECTOR_STORE,
            FindingType.PROMPT,
            FindingType.GUARDRAIL,
        ):
            name = self._get_phase2_package_name(finding)
            package = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": name,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
            }
            return package

        # Handle DATASET
        if finding.type == FindingType.DATASET and finding.dataset_info:
            ds_info = finding.dataset_info
            ds_name = ds_info.name or f"{ds_info.source}-dataset"
            package = {
                "SPDXID": f"SPDXRef-Package-{idx}",
                "name": ds_name,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "comment": f"Dataset from {ds_info.source}",
            }
            if ds_info.split:
                package["comment"] += f", split: {ds_info.split}"
            return package

        return None

    def _get_phase2_package_name(self, finding: Finding) -> str:
        """Get package name for Phase 2 finding types."""
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
        for key, package in packages.items():
            name = package.get("name", key)
            purpose = package.get("primaryPackagePurpose")

            if purpose == "APPLICATION":
                # This is a model file - enrich from KB, hash first. The package
                # carries the digest the scanner computed; a filename lookup
                # cannot resolve a generically named shard, a hash can.
                sha256 = next(
                    (
                        c.get("checksumValue")
                        for c in package.get("checksums", [])
                        if c.get("algorithm") == "SHA256"
                    ),
                    None,
                )
                # The package name is the full path, so pass the basename: the
                # filename fallback matches against models.name and would never
                # hit on a path. The hash lookup runs first regardless.
                model_data = enricher.lookup_model(name.split("/")[-1], sha256=sha256)
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
                    # The purl asserted below is a pick when several models claim
                    # this hash — disclose the ordered candidate list alongside.
                    # Space-joined within the part (a purl cannot contain an
                    # unencoded space); ", " stays the part separator.
                    if model_data.candidate_purls:
                        comment_parts.append(
                            "candidate_purls: " + " ".join(model_data.candidate_purls)
                        )
                    package["comment"] = ", ".join(filter(None, comment_parts))

                    # The resolved purl is the whole point of the lookup: on a hash
                    # hit this names the model that a generic shard filename never
                    # could.
                    if model_data.purl:
                        ext_refs = package.get("externalRefs", [])
                        ext_refs.append(
                            {
                                "referenceCategory": "PACKAGE-MANAGER",
                                "referenceType": "purl",
                                "referenceLocator": model_data.purl,
                            }
                        )
                        package["externalRefs"] = ext_refs

                    # Add external refs for source
                    if model_data.source_url:
                        ext_refs = package.get("externalRefs", [])
                        ext_refs.append(
                            {
                                "referenceCategory": "OTHER",
                                "referenceType": "ai-finder-source-url",
                                "referenceLocator": model_data.source_url,
                            }
                        )
                        package["externalRefs"] = ext_refs
            else:
                # A registry package - enrich by its own ecosystem and name. A
                # package with no purl (an agent, a tool, an MCP client) is not a
                # registry package: looking its name up returns whatever
                # unrelated package shares the name.
                purl = next(
                    (
                        ref["referenceLocator"]
                        for ref in package.get("externalRefs", [])
                        if ref.get("referenceType") == "purl"
                    ),
                    None,
                )
                if not purl:
                    continue
                eco = purl_ecosystem(purl)
                pkg_name = package.get("name", name)
                if eco in ("pypi", "npm"):
                    pkg_data = enricher.lookup_package(pkg_name, eco)
                elif eco == "docker":
                    pkg_data = None
                else:
                    pkg_data = enricher.lookup_sdk(pkg_name)
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

                    # Set downloadLocation from homepage if still NOASSERTION
                    if pkg_data.homepage and package.get("downloadLocation") == "NOASSERTION":
                        package["downloadLocation"] = pkg_data.homepage

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
            key = self._identity(package)
            existing = packages_by_name.get(key)
            seen_at = self._seen_at(finding)

            if existing is None:
                if seen_at:
                    package["sourceInfo"] = f"found at: {seen_at}"
                # First time seeing this package
                name_to_spdxid[name] = package["SPDXID"]
                packages_by_name[key] = package
                # Add DESCRIBES relationship
                relationships.append(
                    {
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "relatedSpdxElement": package["SPDXID"],
                        "relationshipType": "DESCRIBES",
                    }
                )
                idx += 1
                continue
            if seen_at and seen_at not in existing.get("sourceInfo", ""):
                prior = existing.get("sourceInfo")
                existing["sourceInfo"] = f"{prior}; {seen_at}" if prior else f"found at: {seen_at}"
            if "versionInfo" not in existing and "versionInfo" in package:
                # Existing has no version but new one does - update
                existing["versionInfo"] = package["versionInfo"]
                # Also update PURL in externalRefs if present
                if "externalRefs" in package:
                    existing["externalRefs"] = package["externalRefs"]

        # Enrich packages from KB if available
        if enricher:
            self._enrich_packages(packages_by_name, enricher)

        # Ensure all packages have license fields (NOASSERTION if unknown)
        for package in packages_by_name.values():
            if "licenseConcluded" not in package:
                package["licenseConcluded"] = "NOASSERTION"
            if "licenseDeclared" not in package:
                package["licenseDeclared"] = "NOASSERTION"

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
            "name": f"ai-finder-scan-{doc_uuid[:8]}",
            "documentNamespace": f"https://scanoss.com/spdx/{doc_uuid}",
            "creationInfo": {
                "created": timestamp,
                "creators": [f"Tool: ai-finder-{__version__}"],
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
