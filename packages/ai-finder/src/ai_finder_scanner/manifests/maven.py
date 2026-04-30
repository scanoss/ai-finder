"""Java Maven pom.xml manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML artifact IDs to detect (groupId:artifactId patterns)
AI_ARTIFACTS = frozenset(
    {
        "com.theokanning.openai-gpt3-java",
        "com.anthropic",
        "dev.langchain4j",
        "com.google.cloud:google-cloud-aiplatform",
        "com.google.ai.generativelanguage",
        "ai.djl",
        "ai.djl.huggingface",
        "org.tensorflow",
        "ai.onnxruntime",
        "org.pytorch",
        "org.deeplearning4j",
        "org.apache.mxnet",
        "io.milvus",
        "io.pinecone",
        "io.weaviate",
        "io.qdrant",
        "com.cohere",
        "ai.replicate",
    }
)

# Regex for Maven dependency
# Simple pattern for <groupId> and <artifactId> within <dependency> blocks
MAVEN_DEP_RE = re.compile(
    r"<dependency>\s*"
    r"<groupId>(?P<groupId>[^<]+)</groupId>\s*"
    r"<artifactId>(?P<artifactId>[^<]+)</artifactId>\s*"
    r"(?:<version>(?P<version>[^<]+)</version>)?",
    re.DOTALL,
)


class MavenManifestParser(BaseManifestParser):
    """Parse pom.xml for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"pom.xml"})

    def _is_ai_package(self, group_id: str, artifact_id: str) -> bool:
        """Check if dependency is an AI package."""
        full_id = f"{group_id}:{artifact_id}"
        # Check full ID or group prefix
        for ai_art in AI_ARTIFACTS:
            if full_id.startswith(ai_art) or group_id.startswith(ai_art):
                return True
        return False

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse pom.xml for AI dependencies.

        Args:
            content: pom.xml content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_artifacts: set[str] = set()

        for match in MAVEN_DEP_RE.finditer(content):
            group_id = match.group("groupId")
            artifact_id = match.group("artifactId")
            version = match.group("version") or "*"
            full_id = f"{group_id}:{artifact_id}"

            if self._is_ai_package(group_id, artifact_id) and full_id not in seen_artifacts:
                seen_artifacts.add(full_id)
                yield Finding(
                    type=FindingType.MANIFEST_DEP,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    manifest_dep=ManifestDep(
                        name=artifact_id,
                        version=version,
                        manifest_file=str(path),
                    ),
                )
