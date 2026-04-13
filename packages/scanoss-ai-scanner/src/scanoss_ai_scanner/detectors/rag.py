"""RAG detector for embeddings and vector stores."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import EmbeddingInfo, Finding, FindingType, VectorStoreInfo


@dataclass
class EmbeddingPattern:
    """Pattern for detecting embeddings."""

    pattern: re.Pattern[str]
    provider: str
    model: str | None = None


@dataclass
class VectorStorePattern:
    """Pattern for detecting vector stores."""

    pattern: re.Pattern[str]
    provider: str


class RAGDetector:
    """Detect embeddings and vector stores in code."""

    EMBEDDING_PATTERNS = [
        EmbeddingPattern(
            re.compile(r"OpenAIEmbeddings|openai\.embeddings|embed_query.*openai", re.IGNORECASE),
            "openai",
        ),
        EmbeddingPattern(
            re.compile(r"CohereEmbeddings|cohere\.embed", re.IGNORECASE),
            "cohere",
        ),
        EmbeddingPattern(
            re.compile(r"HuggingFaceEmbeddings|sentence_transformers", re.IGNORECASE),
            "huggingface",
        ),
    ]

    VECTOR_STORE_PATTERNS = [
        VectorStorePattern(re.compile(r"Chroma|chromadb", re.IGNORECASE), "chroma"),
        VectorStorePattern(re.compile(r"Pinecone|pinecone\.", re.IGNORECASE), "pinecone"),
        VectorStorePattern(re.compile(r"FAISS|faiss\.", re.IGNORECASE), "faiss"),
        VectorStorePattern(re.compile(r"Qdrant|qdrant_client", re.IGNORECASE), "qdrant"),
        VectorStorePattern(re.compile(r"Weaviate|weaviate\.", re.IGNORECASE), "weaviate"),
        VectorStorePattern(re.compile(r"Milvus|pymilvus", re.IGNORECASE), "milvus"),
    ]

    @property
    def extensions(self) -> frozenset[str]:
        """File extensions this detector handles.

        Returns:
            Set of extensions (e.g., {".py"}).
        """
        return frozenset({".py"})

    def detect(self, content: str, path: Path | str, matcher: Any | None = None) -> Iterator[Finding]:
        """Detect embeddings and vector stores in code.

        Args:
            content: Source code content.
            path: Path to source file.
            matcher: Optional KB Matcher (unused for now).

        Yields:
            Finding for each embedding or vector store detected.
        """
        path_str = str(path)
        seen_embeddings: set[str] = set()
        seen_vector_stores: set[str] = set()

        for match in re.finditer(r"^.*$", content, re.MULTILINE):
            line = match.group()
            line_num = content[: match.start()].count("\n") + 1

            # Check embeddings
            for pattern in self.EMBEDDING_PATTERNS:
                if pattern.pattern.search(line):
                    if pattern.provider not in seen_embeddings:
                        seen_embeddings.add(pattern.provider)
                        yield Finding(
                            type=FindingType.EMBEDDING,
                            file_path=path_str,
                            confidence=0.9,
                            line=line_num,
                            embedding_info=EmbeddingInfo(
                                provider=pattern.provider,
                                model=pattern.model,
                            ),
                        )
                    break

            # Check vector stores
            for pattern in self.VECTOR_STORE_PATTERNS:
                if pattern.pattern.search(line):
                    if pattern.provider not in seen_vector_stores:
                        seen_vector_stores.add(pattern.provider)
                        yield Finding(
                            type=FindingType.VECTOR_STORE,
                            file_path=path_str,
                            confidence=0.9,
                            line=line_num,
                            vector_store_info=VectorStoreInfo(
                                provider=pattern.provider,
                            ),
                        )
                    break
