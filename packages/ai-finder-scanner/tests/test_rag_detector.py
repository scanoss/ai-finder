"""Tests for RAG detector (embeddings and vector stores)."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_finder_scanner.detectors.rag import RAGDetector
from ai_finder_scanner.models import FindingType


class TestRAGDetector:
    @pytest.fixture
    def detector(self) -> RAGDetector:
        return RAGDetector()

    def test_detect_openai_embeddings(self, detector: RAGDetector) -> None:
        code = """
from langchain_openai import OpenAIEmbeddings
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
"""
        findings = list(detector.detect(code, Path("rag.py")))

        embedding_findings = [f for f in findings if f.type == FindingType.EMBEDDING]
        assert len(embedding_findings) >= 1
        assert embedding_findings[0].embedding_info.provider == "openai"

    def test_detect_chroma_vector_store(self, detector: RAGDetector) -> None:
        code = """
from langchain_chroma import Chroma
vectorstore = Chroma.from_documents(docs, embeddings)
"""
        findings = list(detector.detect(code, Path("rag.py")))

        vs_findings = [f for f in findings if f.type == FindingType.VECTOR_STORE]
        assert len(vs_findings) >= 1
        assert vs_findings[0].vector_store_info.provider == "chroma"

    def test_detect_pinecone(self, detector: RAGDetector) -> None:
        code = """
import pinecone
pinecone.init(api_key="xxx")
index = pinecone.Index("my-index")
"""
        findings = list(detector.detect(code, Path("pinecone_app.py")))

        vs_findings = [f for f in findings if f.type == FindingType.VECTOR_STORE]
        assert len(vs_findings) >= 1
        assert vs_findings[0].vector_store_info.provider == "pinecone"

    def test_detect_faiss(self, detector: RAGDetector) -> None:
        code = """
from langchain_community.vectorstores import FAISS
vectorstore = FAISS.from_documents(docs, embeddings)
"""
        findings = list(detector.detect(code, Path("faiss_app.py")))

        vs_findings = [f for f in findings if f.type == FindingType.VECTOR_STORE]
        assert len(vs_findings) >= 1
        assert vs_findings[0].vector_store_info.provider == "faiss"

    def test_detect_cohere_embeddings(self, detector: RAGDetector) -> None:
        code = """
from langchain_cohere import CohereEmbeddings
embeddings = CohereEmbeddings(model="embed-english-v3.0")
"""
        findings = list(detector.detect(code, Path("rag.py")))

        embedding_findings = [f for f in findings if f.type == FindingType.EMBEDDING]
        assert len(embedding_findings) >= 1
        assert embedding_findings[0].embedding_info.provider == "cohere"

    def test_detect_huggingface_embeddings(self, detector: RAGDetector) -> None:
        code = """
from langchain_community.embeddings import HuggingFaceEmbeddings
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
"""
        findings = list(detector.detect(code, Path("rag.py")))

        embedding_findings = [f for f in findings if f.type == FindingType.EMBEDDING]
        assert len(embedding_findings) >= 1
        assert embedding_findings[0].embedding_info.provider == "huggingface"

    def test_detect_qdrant_vector_store(self, detector: RAGDetector) -> None:
        code = """
from langchain_qdrant import Qdrant
from qdrant_client import QdrantClient
client = QdrantClient(":memory:")
vectorstore = Qdrant(client, "my-collection", embeddings)
"""
        findings = list(detector.detect(code, Path("qdrant_app.py")))

        vs_findings = [f for f in findings if f.type == FindingType.VECTOR_STORE]
        assert len(vs_findings) >= 1
        assert vs_findings[0].vector_store_info.provider == "qdrant"

    def test_detect_weaviate_vector_store(self, detector: RAGDetector) -> None:
        code = """
from langchain_weaviate import Weaviate
from weaviate.client import Client
client = Client("http://localhost:8080")
vectorstore = Weaviate(client, "MyClass", embeddings)
"""
        findings = list(detector.detect(code, Path("weaviate_app.py")))

        vs_findings = [f for f in findings if f.type == FindingType.VECTOR_STORE]
        assert len(vs_findings) >= 1
        assert vs_findings[0].vector_store_info.provider == "weaviate"

    def test_detect_milvus_vector_store(self, detector: RAGDetector) -> None:
        code = """
from langchain_milvus import Milvus
from pymilvus import Collection
vectorstore = Milvus(embeddings, collection_name="my-collection")
"""
        findings = list(detector.detect(code, Path("milvus_app.py")))

        vs_findings = [f for f in findings if f.type == FindingType.VECTOR_STORE]
        assert len(vs_findings) >= 1
        assert vs_findings[0].vector_store_info.provider == "milvus"

    def test_no_false_positives(self, detector: RAGDetector) -> None:
        code = """
import requests
response = requests.get("https://api.example.com")
"""
        findings = list(detector.detect(code, Path("app.py")))

        assert len(findings) == 0

    def test_multiple_findings_in_same_file(self, detector: RAGDetector) -> None:
        code = """
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

embeddings = OpenAIEmbeddings()
vectorstore = Chroma.from_documents(docs, embeddings)
"""
        findings = list(detector.detect(code, Path("rag.py")))

        assert len(findings) == 2
        types = [f.type for f in findings]
        assert FindingType.EMBEDDING in types
        assert FindingType.VECTOR_STORE in types
