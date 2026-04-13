"""Java Gradle build.gradle manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML dependency patterns to detect
AI_DEPENDENCIES = frozenset(
    {
        "com.theokanning.openai-gpt3-java",
        "com.anthropic",
        "dev.langchain4j",
        "com.google.cloud:google-cloud-aiplatform",
        "com.google.ai.generativelanguage",
        "ai.djl",
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

# Regex for Gradle dependency declarations
# Matches: implementation 'group:artifact:version' or implementation "group:artifact:version"
GRADLE_DEP_RE = re.compile(
    r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*['\"]"
    r"(?P<group>[\w.-]+):(?P<artifact>[\w.-]+):(?P<version>[^'\"]+)['\"]",
    re.MULTILINE,
)

# Kotlin DSL style: implementation("group:artifact:version")
GRADLE_KOTLIN_RE = re.compile(
    r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*\(\s*['\"]"
    r"(?P<group>[\w.-]+):(?P<artifact>[\w.-]+):(?P<version>[^'\"]+)['\"]\s*\)",
    re.MULTILINE,
)


class GradleManifestParser(BaseManifestParser):
    """Parse build.gradle for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"build.gradle", "build.gradle.kts"})

    def _is_ai_package(self, group: str, artifact: str) -> bool:
        """Check if dependency is an AI package."""
        full_id = f"{group}:{artifact}"
        for ai_dep in AI_DEPENDENCIES:
            if full_id.startswith(ai_dep) or group.startswith(ai_dep):
                return True
        return False

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse build.gradle for AI dependencies.

        Args:
            content: build.gradle content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_artifacts: set[str] = set()

        # Check both Groovy and Kotlin DSL patterns
        for pattern in [GRADLE_DEP_RE, GRADLE_KOTLIN_RE]:
            for match in pattern.finditer(content):
                group = match.group("group")
                artifact = match.group("artifact")
                version = match.group("version")
                full_id = f"{group}:{artifact}"

                if self._is_ai_package(group, artifact) and full_id not in seen_artifacts:
                    seen_artifacts.add(full_id)
                    yield Finding(
                        type=FindingType.MANIFEST_DEP,
                        file_path=str(path),
                        line=self._find_line_number(content, match.start()),
                        confidence=1.0,
                        manifest_dep=ManifestDep(
                            name=artifact,
                            version=version,
                            manifest_file=str(path),
                        ),
                    )
