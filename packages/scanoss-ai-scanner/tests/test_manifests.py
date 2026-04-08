"""Tests for manifest parsers."""

from __future__ import annotations

from pathlib import Path

import pytest
from scanoss_ai_scanner.manifests.npm import NpmManifestParser
from scanoss_ai_scanner.manifests.python import PythonManifestParser
from scanoss_ai_scanner.models import FindingType


@pytest.fixture
def python_parser() -> PythonManifestParser:
    return PythonManifestParser()


class TestPythonManifestParser:
    def test_supported_files(self, python_parser: PythonManifestParser) -> None:
        assert "requirements.txt" in python_parser.manifest_names
        assert "pyproject.toml" in python_parser.manifest_names

    def test_parse_requirements_txt(self, python_parser: PythonManifestParser) -> None:
        content = """openai>=1.0.0
anthropic==0.5.0
langchain
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 3
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "openai" in names
        assert "anthropic" in names
        assert "langchain" in names

    def test_parse_requirements_with_comments(self, python_parser: PythonManifestParser) -> None:
        content = """# AI dependencies
openai>=1.0.0  # OpenAI SDK
# anthropic is not used
torch
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 2
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "openai" in names
        assert "torch" in names

    def test_parse_requirements_with_extras(self, python_parser: PythonManifestParser) -> None:
        content = "transformers[torch]>=4.0.0"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "transformers"

    def test_finding_type_is_manifest_dep(self, python_parser: PythonManifestParser) -> None:
        content = "openai>=1.0.0"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].type == FindingType.MANIFEST_DEP

    def test_version_captured(self, python_parser: PythonManifestParser) -> None:
        content = "openai>=1.0.0"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].manifest_dep.version == ">=1.0.0"

    def test_no_version(self, python_parser: PythonManifestParser) -> None:
        content = "openai"
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].manifest_dep.version == ""

    def test_ignores_non_ai_packages(self, python_parser: PythonManifestParser) -> None:
        content = """requests>=2.0.0
flask
django
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert len(findings) == 0

    def test_line_numbers(self, python_parser: PythonManifestParser) -> None:
        content = """# comment
requests
openai>=1.0.0
"""
        findings = list(python_parser.parse(content, Path("requirements.txt")))

        assert findings[0].line == 3


@pytest.fixture
def npm_parser() -> NpmManifestParser:
    return NpmManifestParser()


class TestNpmManifestParser:
    def test_supported_files(self, npm_parser: NpmManifestParser) -> None:
        assert "package.json" in npm_parser.manifest_names

    def test_parse_dependencies(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "openai": "^4.0.0",
        "@anthropic-ai/sdk": "^0.5.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 2
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "openai" in names
        assert "@anthropic-ai/sdk" in names

    def test_parse_dev_dependencies(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "devDependencies": {
        "openai": "^4.0.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 1
        assert findings[0].manifest_dep.name == "openai"

    def test_parse_langchain(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "langchain": "^0.1.0",
        "@langchain/openai": "^0.0.1"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 2
        names = {f.manifest_dep.name for f in findings if f.manifest_dep}
        assert "langchain" in names
        assert "@langchain/openai" in names

    def test_ignores_non_ai_packages(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "react": "^18.0.0",
        "express": "^4.0.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 0

    def test_invalid_json_returns_empty(self, npm_parser: NpmManifestParser) -> None:
        content = "not valid json"
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert len(findings) == 0

    def test_version_captured(self, npm_parser: NpmManifestParser) -> None:
        content = """{
    "dependencies": {
        "openai": "^4.0.0"
    }
}"""
        findings = list(npm_parser.parse(content, Path("package.json")))

        assert findings[0].manifest_dep.version == "^4.0.0"
