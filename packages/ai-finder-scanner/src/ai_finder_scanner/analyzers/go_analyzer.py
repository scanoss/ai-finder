"""Go code analyzer using tree-sitter."""

from __future__ import annotations

from pathlib import Path

import tree_sitter_go as tsgo
from tree_sitter import Language, Parser, Query, QueryCursor

from .base import BaseAnalyzer, ComponentUsage, FunctionCall

# Known AI SDK package patterns (last part of import path)
AI_PACKAGE_PATTERNS = frozenset(
    {
        "openai",
        "go-openai",
        "anthropic",
        "langchaingo",
        "cohere",
        "replicate",
    }
)

# Known AI method/function patterns
AI_METHOD_PATTERNS = frozenset(
    {
        "CreateChatCompletion",
        "CreateCompletion",
        "CreateEmbedding",
        "Chat",
        "Complete",
        "Generate",
        "Embed",
        "Run",
        "Invoke",
        "Call",
    }
)


class GoAnalyzer(BaseAnalyzer):
    """Analyze Go code for AI component usage."""

    def __init__(self) -> None:
        """Initialize the Go analyzer with tree-sitter parser."""
        self._language = Language(tsgo.language())
        self._parser = Parser(self._language)

        # Query for function declarations
        self._func_query = Query(
            self._language,
            """
            (function_declaration
                name: (identifier) @func_name) @func_def
            """,
        )

        # Query for method declarations
        self._method_decl_query = Query(
            self._language,
            """
            (method_declaration
                name: (field_identifier) @func_name) @func_def
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

        # Query for method calls (selector expression)
        self._method_query = Query(
            self._language,
            """
            (call_expression
                function: (selector_expression
                    operand: (identifier) @object_name
                    field: (field_identifier) @method_name)) @call
            """,
        )

        # Query for package.Function calls
        self._pkg_call_query = Query(
            self._language,
            """
            (call_expression
                function: (selector_expression
                    operand: (identifier) @pkg_name
                    field: (field_identifier) @func_name)) @call
            """,
        )

    @property
    def language(self) -> str:
        return "go"

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".go"})

    def _get_function_ranges(self, tree: object) -> dict[tuple[int, int], str]:
        """Get function name to line range mapping."""
        functions: dict[tuple[int, int], str] = {}

        # Get regular functions
        cursor = QueryCursor(self._func_query)
        for _, captures in cursor.matches(tree.root_node):
            func_def_nodes = captures.get("func_def", [])
            func_name_nodes = captures.get("func_name", [])

            if func_def_nodes and func_name_nodes:
                func_def = func_def_nodes[0]
                func_name = func_name_nodes[0].text.decode("utf-8")
                functions[(func_def.start_point[0], func_def.end_point[0])] = func_name

        # Get methods
        cursor = QueryCursor(self._method_decl_query)
        for _, captures in cursor.matches(tree.root_node):
            func_def_nodes = captures.get("func_def", [])
            func_name_nodes = captures.get("func_name", [])

            if func_def_nodes and func_name_nodes:
                func_def = func_def_nodes[0]
                func_name = func_name_nodes[0].text.decode("utf-8")
                functions[(func_def.start_point[0], func_def.end_point[0])] = func_name

        return functions

    def _get_current_function(self, functions: dict[tuple[int, int], str], line: int) -> str | None:
        """Get the function name containing the given line."""
        for (start, end), name in functions.items():
            if start <= line <= end:
                return name
        return None

    def analyze(self, content: str, path: Path) -> list[ComponentUsage]:
        """Analyze Go code for AI component usage."""
        tree = self._parser.parse(content.encode("utf-8"))
        usages: list[ComponentUsage] = []
        functions = self._get_function_ranges(tree)

        # Find package.Function calls (e.g., openai.NewClient())
        cursor = QueryCursor(self._pkg_call_query)
        for _, captures in cursor.matches(tree.root_node):
            pkg_nodes = captures.get("pkg_name", [])
            func_nodes = captures.get("func_name", [])
            call_nodes = captures.get("call", [])

            if pkg_nodes and func_nodes and call_nodes:
                pkg_name = pkg_nodes[0].text.decode("utf-8")
                func_name = func_nodes[0].text.decode("utf-8")
                call_node = call_nodes[0]

                # Check if package matches AI patterns
                if pkg_name.lower() in AI_PACKAGE_PATTERNS or any(
                    p in pkg_name.lower() for p in AI_PACKAGE_PATTERNS
                ):
                    line = call_node.start_point[0]
                    usages.append(
                        ComponentUsage(
                            component_id=pkg_name,
                            usage_type="instantiation" if "New" in func_name else "function_call",
                            function_context=self._get_current_function(functions, line),
                            file_path=str(path),
                            line=line + 1,
                            details={"package": pkg_name, "function": func_name},
                        )
                    )

        # Find method calls that match AI patterns
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
        """Extract function call graph from Go code."""
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
                caller = self._get_current_function(functions, line) or "<package>"

                calls.append(
                    FunctionCall(
                        caller=caller,
                        callee=callee,
                        file_path=str(path),
                        line=line + 1,
                    )
                )

        # Get method/package calls
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
                caller = self._get_current_function(functions, line) or "<package>"

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
