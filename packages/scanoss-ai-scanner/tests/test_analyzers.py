"""Tests for tree-sitter based analyzers."""

from pathlib import Path

import pytest

from scanoss_ai_scanner.analyzers.python_analyzer import PythonAnalyzer


class TestPythonAnalyzer:
    @pytest.fixture
    def analyzer(self) -> PythonAnalyzer:
        return PythonAnalyzer()

    def test_language_property(self, analyzer: PythonAnalyzer) -> None:
        assert analyzer.language == "python"

    def test_extensions_property(self, analyzer: PythonAnalyzer) -> None:
        assert ".py" in analyzer.extensions

    def test_detect_openai_instantiation(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = OpenAI(api_key="test")
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 1
        assert usages[0].component_id == "openai"
        assert usages[0].usage_type == "instantiation"
        assert usages[0].details["class"] == "OpenAI"

    def test_detect_anthropic_instantiation(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = Anthropic(api_key="test")
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 1
        assert usages[0].component_id == "anthropic"
        assert usages[0].usage_type == "instantiation"

    def test_detect_async_openai(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = AsyncOpenAI()
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 1
        assert usages[0].component_id == "asyncopenai"

    def test_detect_multiple_instantiations(self, analyzer: PythonAnalyzer) -> None:
        code = """
openai_client = OpenAI()
anthropic_client = Anthropic()
cohere_client = Cohere()
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 3
        components = {u.component_id for u in usages}
        assert "openai" in components
        assert "anthropic" in components
        assert "cohere" in components

    def test_detect_instantiation_in_function(self, analyzer: PythonAnalyzer) -> None:
        code = """
def setup():
    client = OpenAI()
    return client
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 1
        assert usages[0].function_context == "setup"

    def test_detect_method_call_create(self, analyzer: PythonAnalyzer) -> None:
        code = """
response = client.create(prompt="Hello")
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 1
        assert usages[0].usage_type == "method_call"
        assert usages[0].details["method"] == "create"

    def test_detect_method_call_generate(self, analyzer: PythonAnalyzer) -> None:
        code = """
result = model.generate(input_text)
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 1
        assert usages[0].details["method"] == "generate"

    def test_no_detection_for_unrelated_code(self, analyzer: PythonAnalyzer) -> None:
        code = """
x = MyClass()
y = other.something()
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert len(usages) == 0

    def test_extract_simple_calls(self, analyzer: PythonAnalyzer) -> None:
        code = """
def main():
    helper()
    process()
"""
        calls = analyzer.extract_calls(code, Path("test.py"))

        assert len(calls) >= 2
        callees = {c.callee for c in calls}
        assert "helper" in callees
        assert "process" in callees

    def test_extract_calls_with_caller_context(self, analyzer: PythonAnalyzer) -> None:
        code = """
def main():
    helper()

def helper():
    process()
"""
        calls = analyzer.extract_calls(code, Path("test.py"))

        # Find the call from main to helper
        main_calls = [c for c in calls if c.caller == "main"]
        assert any(c.callee == "helper" for c in main_calls)

        # Find the call from helper to process
        helper_calls = [c for c in calls if c.caller == "helper"]
        assert any(c.callee == "process" for c in helper_calls)

    def test_extract_method_calls(self, analyzer: PythonAnalyzer) -> None:
        code = """
result = client.chat()
"""
        calls = analyzer.extract_calls(code, Path("test.py"))

        assert len(calls) >= 1
        method_calls = [c for c in calls if c.module]
        assert any(c.callee == "chat" and c.module == "client" for c in method_calls)

    def test_file_path_preserved(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = OpenAI()
"""
        usages = analyzer.analyze(code, Path("src/main.py"))

        assert usages[0].file_path == "src/main.py"

    def test_line_numbers_correct(self, analyzer: PythonAnalyzer) -> None:
        code = """# Line 1
# Line 2
client = OpenAI()  # Line 3
"""
        usages = analyzer.analyze(code, Path("test.py"))

        assert usages[0].line == 3
