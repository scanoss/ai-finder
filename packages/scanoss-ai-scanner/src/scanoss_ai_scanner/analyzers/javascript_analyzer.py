"""JavaScript/TypeScript code analyzer using tree-sitter."""

from __future__ import annotations

from pathlib import Path

import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser, Query, QueryCursor

from .base import BaseAnalyzer, ComponentUsage, FunctionCall

# Known AI SDK client class/function patterns
AI_CLIENT_PATTERNS = frozenset(
    {
        "OpenAI",
        "Anthropic",
        "Cohere",
        "Replicate",
        "GoogleGenerativeAI",
        "HfInference",
        "Together",
        "Groq",
        "MistralClient",
        "Ollama",
    }
)

# Known AI method patterns
AI_METHOD_PATTERNS = frozenset(
    {
        "chat",
        "complete",
        "completions",
        "create",
        "generate",
        "embed",
        "embeddings",
        "invoke",
        "run",
        "predict",
        "inference",
        "messages",
    }
)


class JavaScriptAnalyzer(BaseAnalyzer):
    """Analyze JavaScript/TypeScript code for AI component usage."""

    def __init__(self) -> None:
        """Initialize the JavaScript analyzer with tree-sitter parser."""
        self._language = Language(tsjs.language())
        self._parser = Parser(self._language)

        # Query for function/arrow function definitions
        self._func_query = Query(
            self._language,
            """
            [
                (function_declaration
                    name: (identifier) @func_name) @func_def
                (variable_declarator
                    name: (identifier) @func_name
                    value: (arrow_function)) @func_def
                (method_definition
                    name: (property_identifier) @func_name) @func_def
            ]
            """,
        )

        # Query for new expressions (class instantiation)
        self._new_query = Query(
            self._language,
            """
            (new_expression
                constructor: (identifier) @class_name) @new_expr
            """,
        )

        # Query for function calls
        self._call_query = Query(
            self._language,
            """
            (call_expression
                function: (identifier) @func_name) @call
            """,
        )

        # Query for method calls
        self._method_query = Query(
            self._language,
            """
            (call_expression
                function: (member_expression
                    object: (identifier) @object_name
                    property: (property_identifier) @method_name)) @call
            """,
        )

    @property
    def language(self) -> str:
        return "javascript"

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

    def _get_function_ranges(self, tree: object) -> dict[tuple[int, int], str]:
        """Get function name to line range mapping."""
        cursor = QueryCursor(self._func_query)
        functions: dict[tuple[int, int], str] = {}

        for _, captures in cursor.matches(tree.root_node):
            func_def_nodes = captures.get("func_def", [])
            func_name_nodes = captures.get("func_name", [])

            if func_def_nodes and func_name_nodes:
                func_def = func_def_nodes[0]
                func_name = func_name_nodes[0].text.decode("utf-8")
                functions[(func_def.start_point[0], func_def.end_point[0])] = func_name

        return functions

    def _get_current_function(
        self, functions: dict[tuple[int, int], str], line: int
    ) -> str | None:
        """Get the function name containing the given line."""
        for (start, end), name in functions.items():
            if start <= line <= end:
                return name
        return None

    def analyze(self, content: str, path: Path) -> list[ComponentUsage]:
        """Analyze JavaScript code for AI component usage."""
        tree = self._parser.parse(content.encode("utf-8"))
        usages: list[ComponentUsage] = []
        functions = self._get_function_ranges(tree)

        # Find new expressions (class instantiations)
        cursor = QueryCursor(self._new_query)
        for _, captures in cursor.matches(tree.root_node):
            class_nodes = captures.get("class_name", [])
            new_nodes = captures.get("new_expr", [])

            if class_nodes and new_nodes:
                class_name = class_nodes[0].text.decode("utf-8")
                new_node = new_nodes[0]

                if class_name in AI_CLIENT_PATTERNS:
                    line = new_node.start_point[0]
                    usages.append(
                        ComponentUsage(
                            component_id=class_name.lower(),
                            usage_type="instantiation",
                            function_context=self._get_current_function(functions, line),
                            file_path=str(path),
                            line=line + 1,
                            details={"class": class_name},
                        )
                    )

        # Find method calls
        cursor = QueryCursor(self._method_query)
        for _, captures in cursor.matches(tree.root_node):
            object_nodes = captures.get("object_name", [])
            method_nodes = captures.get("method_name", [])
            call_nodes = captures.get("call", [])

            if object_nodes and method_nodes and call_nodes:
                obj_name = object_nodes[0].text.decode("utf-8")
                method_name = method_nodes[0].text.decode("utf-8")
                call_node = call_nodes[0]

                if method_name in AI_METHOD_PATTERNS:
                    line = call_node.start_point[0]
                    usages.append(
                        ComponentUsage(
                            component_id=obj_name,
                            usage_type="method_call",
                            function_context=self._get_current_function(functions, line),
                            file_path=str(path),
                            line=line + 1,
                            details={"object": obj_name, "method": method_name},
                        )
                    )

        return usages

    def extract_calls(self, content: str, path: Path) -> list[FunctionCall]:
        """Extract function call graph from JavaScript code."""
        tree = self._parser.parse(content.encode("utf-8"))
        calls: list[FunctionCall] = []
        functions = self._get_function_ranges(tree)

        # Get simple function calls
        cursor = QueryCursor(self._call_query)
        for _, captures in cursor.matches(tree.root_node):
            func_name_nodes = captures.get("func_name", [])
            call_nodes = captures.get("call", [])

            if func_name_nodes and call_nodes:
                callee = func_name_nodes[0].text.decode("utf-8")
                call_node = call_nodes[0]
                line = call_node.start_point[0]
                caller = self._get_current_function(functions, line) or "<module>"

                calls.append(
                    FunctionCall(
                        caller=caller,
                        callee=callee,
                        file_path=str(path),
                        line=line + 1,
                    )
                )

        # Get method calls
        cursor = QueryCursor(self._method_query)
        for _, captures in cursor.matches(tree.root_node):
            object_nodes = captures.get("object_name", [])
            method_nodes = captures.get("method_name", [])
            call_nodes = captures.get("call", [])

            if object_nodes and method_nodes and call_nodes:
                obj_name = object_nodes[0].text.decode("utf-8")
                method_name = method_nodes[0].text.decode("utf-8")
                call_node = call_nodes[0]
                line = call_node.start_point[0]
                caller = self._get_current_function(functions, line) or "<module>"

                calls.append(
                    FunctionCall(
                        caller=caller,
                        callee=method_name,
                        file_path=str(path),
                        line=line + 1,
                        module=obj_name,
                    )
                )

        return calls
