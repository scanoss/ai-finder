"""Go go.mod manifest parser."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML module paths to detect
AI_MODULES = frozenset(
    {
        "github.com/sashabaranov/go-openai",
        "github.com/anthropics/anthropic-sdk-go",
        "github.com/tmc/langchaingo",
        "github.com/google/generative-ai-go",
        "github.com/cohere-ai/cohere-go",
        "github.com/replicate/replicate-go",
        "github.com/ollama/ollama",
        "github.com/gage-technologies/mistral-go",
        "gorgonia.org/gorgonia",
        "gorgonia.org/tensor",
        "github.com/nlpodyssey/spago",
        "github.com/owulveryck/onnx-go",
        "github.com/knights-analytics/hugot",
        "github.com/milvus-io/milvus-sdk-go",
        "github.com/pinecone-io/go-pinecone",
        "github.com/weaviate/weaviate-go-client",
        "github.com/qdrant/go-client",
    }
)

# Regex for go.mod require statements
# Matches: module/path v1.0.0
GOMOD_RE = re.compile(
    r"^\s*(?P<module>[\w./-]+)\s+(?P<version>v[\d.]+(?:-[\w.]+)?)",
    re.MULTILINE,
)


class GoModManifestParser(BaseManifestParser):
    """Parse go.mod for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset({"go.mod"})

    def _is_ai_package(self, module: str) -> bool:
        """Check if module is an AI package."""
        return any(module == ai_mod or module.startswith(ai_mod + "/") for ai_mod in AI_MODULES)

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find line number for a match position."""
        return content[:match_start].count("\n") + 1

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse go.mod for AI dependencies.

        Args:
            content: go.mod content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency detected.
        """
        seen_modules: set[str] = set()

        for match in GOMOD_RE.finditer(content):
            module = match.group("module")
            version = match.group("version")

            if self._is_ai_package(module) and module not in seen_modules:
                seen_modules.add(module)
                yield Finding(
                    type=FindingType.MANIFEST_DEP,
                    file_path=str(path),
                    line=self._find_line_number(content, match.start()),
                    confidence=1.0,
                    manifest_dep=ManifestDep(
                        name=module.split("/")[-1],  # Short name
                        version=version,
                        manifest_file=str(path),
                    ),
                )
