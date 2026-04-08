"""Rust code analyzer using tree-sitter."""

from __future__ import annotations

from pathlib import Path

import tree_sitter_rust as tsrust
from tree_sitter import Language, Parser, Query, QueryCursor

from .base import BaseAnalyzer, ComponentUsage, FunctionCall

# Known AI SDK crate patterns
AI_CRATE_PATTERNS = frozenset(
    {
        "async_openai",
        "openai_api",
        "anthropic",
        "candle",
        "candle_core",
        "candle_nn",
        "llm",
        "llm_chain",
        "rust_bert",
        "ort",
        "tch",
        "tract",
    }
)

# Known AI method patterns
AI_METHOD_PATTERNS = frozenset(
    {
        "create",
        "generate",
        "complete",
        "chat",
        "embed",
        "run",
        "invoke",
        "predict",
        "forward",
        "inference",
    }
)


class RustAnalyzer(BaseAnalyzer):
    """Analyze Rust code for AI component usage."""

    def __init__(self) -> None:
        """Initialize the Rust analyzer with tree-sitter parser."""
        self._language = Language(tsrust.language())
        self._parser = Parser(self._language)

        # Query for function definitions
        self._func_query = Query(
            self._language,
            """
            (function_item
                name: (identifier) @func_name) @func_def
            """,
        )

        # Query for impl method definitions
        self._impl_method_query = Query(
            self._language,
            """
            (impl_item
                body: (declaration_list
                    (function_item
                        name: (identifier) @func_name) @func_def))
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
                function: (field_expression
                    value: (identifier) @object_name
                    field: (field_identifier) @method_name)) @call
            """,
        )

        # Query for scoped calls (crate::function)
        self._scoped_call_query = Query(
            self._language,
            """
            (call_expression
                function: (scoped_identifier
                    path: (identifier) @crate_name
                    name: (identifier) @func_name)) @call
            """,
        )

        # Query for struct instantiation
        self._struct_query = Query(
            self._language,
            """
            (struct_expression
                name: (type_identifier) @struct_name) @struct_expr
            """,
        )

    @property
    def language(self) -> str:
        return "rust"

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".rs"})

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

        # Get impl methods
        cursor = QueryCursor(self._impl_method_query)
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
        """Analyze Rust code for AI component usage."""
        tree = self._parser.parse(content.encode("utf-8"))
        usages: list[ComponentUsage] = []
        functions = self._get_function_ranges(tree)

        # Find scoped calls (crate::function)
        cursor = QueryCursor(self._scoped_call_query)
        for _, captures in cursor.matches(tree.root_node):
            crate_nodes = captures.get("crate_name", [])
            func_nodes = captures.get("func_name", [])
            call_nodes = captures.get("call", [])

            if crate_nodes and func_nodes and call_nodes:
                crate_name = crate_nodes[0].text.decode("utf-8")
                func_name = func_nodes[0].text.decode("utf-8")
                call_node = call_nodes[0]

                if crate_name in AI_CRATE_PATTERNS:
                    line = call_node.start_point[0]
                    usages.append(
                        ComponentUsage(
                            component_id=crate_name,
                            usage_type="function_call",
                            function_context=self._get_current_function(functions, line),
                            file_path=str(path),
                            line=line + 1,
                            details={"crate": crate_name, "function": func_name},
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

        # Find struct instantiations (e.g., Client::new())
        cursor = QueryCursor(self._struct_query)
        for _, captures in cursor.matches(tree.root_node):
            struct_nodes = captures.get("struct_name", [])
            expr_nodes = captures.get("struct_expr", [])

            if struct_nodes and expr_nodes:
                struct_name = struct_nodes[0].text.decode("utf-8")
                expr_node = expr_nodes[0]

                # Check if struct name suggests AI client
                if any(p in struct_name.lower() for p in ["client", "openai", "anthropic"]):
                    line = expr_node.start_point[0]
                    usages.append(
                        ComponentUsage(
                            component_id=struct_name.lower(),
                            usage_type="instantiation",
                            function_context=self._get_current_function(functions, line),
                            file_path=str(path),
                            line=line + 1,
                            details={"struct": struct_name},
                        )
                    )

        return usages

    def extract_calls(self, content: str, path: Path) -> list[FunctionCall]:
        """Extract function call graph from Rust code."""
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
