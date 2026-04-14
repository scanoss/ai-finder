"""Python manifest parser (requirements.txt, pyproject.toml)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Finding, FindingType, ManifestDep
from .base import BaseManifestParser

# AI/ML package names to detect
AI_PACKAGES = frozenset(
    {
        # LLM Clients
        "openai",
        "anthropic",
        "cohere",
        "cohere-ai",
        "replicate",
        "together",
        "groq",
        "mistralai",
        "ollama",
        "google-generativeai",
        "vertexai",
        "azure-ai-openai",
        # Agent Frameworks
        "langchain",
        "langchain-core",
        "langchain-openai",
        "langchain-anthropic",
        "langchain-community",
        "langchain-experimental",
        "langgraph",
        "llama-index",
        "llama-index-core",
        "llama-index-llms-openai",
        "autogen",
        "pyautogen",
        "crewai",
        "crewai-tools",
        "strands-agents",
        "strands-agents-tools",
        "semantic-kernel",
        # ML Frameworks
        "transformers",
        "huggingface-hub",
        "torch",
        "pytorch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "tensorflow-cpu",
        "tensorflow-gpu",
        "tf-keras",
        "keras",
        "jax",
        "jaxlib",
        "flax",
        "scikit-learn",
        "xgboost",
        "lightgbm",
        "catboost",
        # Vector DBs / RAG
        "chromadb",
        "pinecone-client",
        "pinecone",
        "weaviate-client",
        "qdrant-client",
        "milvus",
        "pymilvus",
        "faiss-cpu",
        "faiss-gpu",
        "lancedb",
        # Embeddings
        "sentence-transformers",
        "instructor-embedding",
        # Tools & Utilities
        "tavily-python",
        "langsmith",
        "wandb",
        "mlflow",
        "accelerate",
        "datasets",
        "evaluate",
        "safetensors",
        "onnx",
        "onnxruntime",
        "onnxruntime-gpu",
        "peft",
        "trl",
        "bitsandbytes",
        # Speech / Audio AI
        "openai-whisper",
        "whisper",
        "faster-whisper",
        "speechrecognition",
        "pyaudio",
        "elevenlabs",
        "bark",
        # Vision AI
        "ultralytics",
        "opencv-python",
        "pillow",
        "timm",
        "albumentations",
        # Security / Guardrails
        "aiproxyguard-python-sdk",
        "guardrails-ai",
        "nemoguardrails",
        "llm-guard",
        # MCP / Tool Use
        "mcp",
        "anthropic-tools",
    }
)

# Regex for requirements.txt lines
# Matches: package, package==1.0.0, package>=1.0.0, package[extra]>=1.0.0
REQUIREMENTS_RE = re.compile(
    r"^(?P<name>[\w-]+)(?:\[[\w,]+\])?(?P<version>(?:[<>=!~]+[\d.]+(?:,\s*[<>=!~]+[\d.]+)*)?)",
    re.MULTILINE,
)


class PythonManifestParser(BaseManifestParser):
    """Parse Python manifest files for AI dependencies."""

    @property
    def manifest_names(self) -> frozenset[str]:
        return frozenset(
            {
                "requirements.txt",
                "requirements-dev.txt",
                "requirements-test.txt",
                "pyproject.toml",
                "setup.py",
                "setup.cfg",
                "Pipfile",
            }
        )

    def _normalize_name(self, name: str) -> str:
        """Normalize package name for comparison.

        PEP 503: all comparisons should be case-insensitive
        and treat hyphens and underscores as equivalent.
        """
        return name.lower().replace("_", "-")

    def _is_ai_package(self, name: str) -> bool:
        """Check if package is an AI package."""
        return self._normalize_name(name) in AI_PACKAGES

    def parse(self, content: str, path: Path) -> Iterator[Finding]:
        """Parse Python manifest for AI dependencies.

        Args:
            content: Manifest file content.
            path: File path (relative to scan root).

        Yields:
            Finding for each AI dependency found.
        """
        line_number = 0
        for line in content.splitlines():
            line_number += 1

            # Skip comments and empty lines
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Remove inline comments
            if "#" in stripped:
                stripped = stripped.split("#")[0].strip()

            # Match package spec
            match = REQUIREMENTS_RE.match(stripped)
            if match:
                name = match.group("name")
                version = match.group("version") or ""

                if self._is_ai_package(name):
                    yield Finding(
                        type=FindingType.MANIFEST_DEP,
                        file_path=str(path),
                        line=line_number,
                        confidence=1.0,
                        manifest_dep=ManifestDep(
                            name=name,
                            version=version,
                            manifest_file=str(path),
                        ),
                    )
