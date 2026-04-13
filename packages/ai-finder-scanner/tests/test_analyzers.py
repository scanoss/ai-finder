"""Tests for tree-sitter based analyzers.

These tests require tree-sitter which needs Python 3.10+.
This file is skipped during collection on Python < 3.10 (see conftest.py).
"""

from pathlib import Path

import pytest
from ai_finder_scanner.analyzers.dataflow import FlowType
from ai_finder_scanner.analyzers.go_analyzer import GoAnalyzer
from ai_finder_scanner.analyzers.graph import ComponentGraph, RelationshipAnalyzer
from ai_finder_scanner.analyzers.javascript_analyzer import JavaScriptAnalyzer
from ai_finder_scanner.analyzers.python_analyzer import PythonAnalyzer
from ai_finder_scanner.analyzers.rust_analyzer import RustAnalyzer


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

    def test_dataflow_tracks_ai_assignment(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = OpenAI()
response = client.create(prompt="Hello")
"""
        graph = analyzer.extract_dataflow(code, Path("test.py"))

        # Should track the client assignment
        definitions = [n for n in graph.nodes if n.flow_type == FlowType.DEFINITION]
        assert len(definitions) >= 1
        assert any(n.variable == "client" for n in definitions)

    def test_dataflow_tracks_tainted_return(self, analyzer: PythonAnalyzer) -> None:
        code = """
def get_client():
    client = OpenAI()
    return client
"""
        graph = analyzer.extract_dataflow(code, Path("test.py"))

        # Should track the return of tainted variable
        returns = [n for n in graph.nodes if n.flow_type == FlowType.RETURN]
        assert len(returns) == 1
        assert returns[0].variable == "client"
        assert returns[0].function_context == "get_client"

    def test_dataflow_tracks_tainted_argument(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = OpenAI()
process(client)
"""
        graph = analyzer.extract_dataflow(code, Path("test.py"))

        # Should track client being passed as argument
        args = [n for n in graph.nodes if n.flow_type == FlowType.ARGUMENT]
        assert len(args) == 1
        assert args[0].variable == "client"
        assert args[0].target_function == "process"

    def test_dataflow_is_tainted(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = OpenAI()
other = SomeClass()
"""
        graph = analyzer.extract_dataflow(code, Path("test.py"))

        assert graph.is_tainted("client", None)
        assert not graph.is_tainted("other", None)

    def test_dataflow_to_dict(self, analyzer: PythonAnalyzer) -> None:
        code = """
client = OpenAI()
"""
        graph = analyzer.extract_dataflow(code, Path("test.py"))
        data = graph.to_dict()

        assert "nodes" in data
        assert "edges" in data
        assert "tainted_variables" in data


class TestJavaScriptAnalyzer:
    @pytest.fixture
    def analyzer(self) -> JavaScriptAnalyzer:
        return JavaScriptAnalyzer()

    def test_language_property(self, analyzer: JavaScriptAnalyzer) -> None:
        assert analyzer.language == "javascript"

    def test_extensions_property(self, analyzer: JavaScriptAnalyzer) -> None:
        assert ".js" in analyzer.extensions
        assert ".ts" in analyzer.extensions
        assert ".jsx" in analyzer.extensions
        assert ".tsx" in analyzer.extensions

    def test_detect_openai_instantiation(self, analyzer: JavaScriptAnalyzer) -> None:
        code = """
const client = new OpenAI({ apiKey: 'test' });
"""
        usages = analyzer.analyze(code, Path("app.js"))

        assert len(usages) == 1
        assert usages[0].component_id == "openai"
        assert usages[0].usage_type == "instantiation"

    def test_detect_anthropic_instantiation(self, analyzer: JavaScriptAnalyzer) -> None:
        code = """
const anthropic = new Anthropic();
"""
        usages = analyzer.analyze(code, Path("app.js"))

        assert len(usages) == 1
        assert usages[0].component_id == "anthropic"

    def test_detect_method_call(self, analyzer: JavaScriptAnalyzer) -> None:
        code = """
const response = client.create({ prompt: 'Hello' });
"""
        usages = analyzer.analyze(code, Path("app.js"))

        assert len(usages) == 1
        assert usages[0].usage_type == "method_call"
        assert usages[0].details["method"] == "create"

    def test_no_detection_for_unrelated(self, analyzer: JavaScriptAnalyzer) -> None:
        code = """
const x = new MyClass();
const y = obj.doSomething();
"""
        usages = analyzer.analyze(code, Path("app.js"))

        assert len(usages) == 0


class TestGoAnalyzer:
    @pytest.fixture
    def analyzer(self) -> GoAnalyzer:
        return GoAnalyzer()

    def test_language_property(self, analyzer: GoAnalyzer) -> None:
        assert analyzer.language == "go"

    def test_extensions_property(self, analyzer: GoAnalyzer) -> None:
        assert ".go" in analyzer.extensions

    def test_detect_openai_client(self, analyzer: GoAnalyzer) -> None:
        code = """
package main

func main() {
    client := openai.NewClient("key")
}
"""
        usages = analyzer.analyze(code, Path("main.go"))

        assert len(usages) >= 1
        assert any(u.component_id == "openai" for u in usages)

    def test_detect_method_call(self, analyzer: GoAnalyzer) -> None:
        code = """
package main

func main() {
    resp, _ := client.CreateChatCompletion(ctx, req)
}
"""
        usages = analyzer.analyze(code, Path("main.go"))

        assert len(usages) >= 1
        method_calls = [u for u in usages if u.usage_type == "method_call"]
        assert any(u.details.get("method") == "CreateChatCompletion" for u in method_calls)


class TestRustAnalyzer:
    @pytest.fixture
    def analyzer(self) -> RustAnalyzer:
        return RustAnalyzer()

    def test_language_property(self, analyzer: RustAnalyzer) -> None:
        assert analyzer.language == "rust"

    def test_extensions_property(self, analyzer: RustAnalyzer) -> None:
        assert ".rs" in analyzer.extensions

    def test_detect_method_call(self, analyzer: RustAnalyzer) -> None:
        code = """
fn main() {
    let result = client.create(prompt);
}
"""
        usages = analyzer.analyze(code, Path("main.rs"))

        assert len(usages) >= 1
        assert any(u.details.get("method") == "create" for u in usages)

    def test_extract_function_calls(self, analyzer: RustAnalyzer) -> None:
        code = """
fn main() {
    helper();
    process();
}

fn helper() {
    do_work();
}
"""
        calls = analyzer.extract_calls(code, Path("main.rs"))

        assert len(calls) >= 2
        callees = {c.callee for c in calls}
        assert "helper" in callees
        assert "process" in callees


class TestRelationshipAnalyzer:
    @pytest.fixture
    def analyzer(self) -> RelationshipAnalyzer:
        return RelationshipAnalyzer()

    def test_analyze_python_file(self, analyzer: RelationshipAnalyzer) -> None:
        code = """
client = OpenAI()
response = client.create(prompt="Hello")
"""
        result = analyzer.analyze_file(code, Path("app.py"))

        assert len(result.usages) >= 1
        assert any(u.component_id == "openai" for u in result.usages)

    def test_analyze_javascript_file(self, analyzer: RelationshipAnalyzer) -> None:
        code = """
const client = new OpenAI();
"""
        result = analyzer.analyze_file(code, Path("app.js"))

        assert len(result.usages) >= 1
        assert any(u.component_id == "openai" for u in result.usages)

    def test_build_graph_creates_nodes(self, analyzer: RelationshipAnalyzer) -> None:
        code = """
client = OpenAI()
"""
        result = analyzer.analyze_file(code, Path("app.py"))
        graph = analyzer.build_graph({Path("app.py"): result})

        assert len(graph.nodes) >= 1
        assert "openai" in graph.nodes

    def test_build_graph_creates_edges(self, analyzer: RelationshipAnalyzer) -> None:
        code = """
client = OpenAI()
"""
        result = analyzer.analyze_file(code, Path("app.py"))
        graph = analyzer.build_graph({Path("app.py"): result})

        assert len(graph.edges) >= 1
        contains_edges = [e for e in graph.edges if e.relationship == "contains"]
        assert len(contains_edges) >= 1

    def test_graph_to_dict(self, analyzer: RelationshipAnalyzer) -> None:
        code = """
client = OpenAI()
"""
        result = analyzer.analyze_file(code, Path("app.py"))
        graph = analyzer.build_graph({Path("app.py"): result})
        data = graph.to_dict()

        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 1


class TestComponentGraph:
    def test_add_node(self) -> None:
        graph = ComponentGraph()
        node = graph.add_node("openai", "sdk")

        assert node.id == "openai"
        assert node.type == "sdk"
        assert "openai" in graph.nodes

    def test_add_node_idempotent(self) -> None:
        graph = ComponentGraph()
        node1 = graph.add_node("openai", "sdk")
        node2 = graph.add_node("openai", "sdk")

        assert node1 is node2
        assert len(graph.nodes) == 1

    def test_add_edge(self) -> None:
        graph = ComponentGraph()
        graph.add_edge("app.py", "openai", "contains")

        assert len(graph.edges) == 1
        assert graph.edges[0].source == "app.py"
        assert graph.edges[0].target == "openai"
        assert graph.edges[0].relationship == "contains"

    def test_get_dependencies(self) -> None:
        graph = ComponentGraph()
        graph.add_edge("main", "openai", "dependsOn")
        graph.add_edge("main", "anthropic", "dependsOn")

        deps = graph.get_dependencies("main")

        assert "openai" in deps
        assert "anthropic" in deps

    def test_get_dependents(self) -> None:
        graph = ComponentGraph()
        graph.add_edge("main", "openai", "dependsOn")
        graph.add_edge("helper", "openai", "dependsOn")

        dependents = graph.get_dependents("openai")

        assert "main" in dependents
        assert "helper" in dependents
