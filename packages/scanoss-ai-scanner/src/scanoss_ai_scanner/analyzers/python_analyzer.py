"""Python code analyzer using tree-sitter."""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Query, QueryCursor

from .base import BaseAnalyzer, ComponentUsage, FunctionCall
from .dataflow import DataFlowGraph, FlowType

# Known AI SDK client class patterns
AI_CLIENT_PATTERNS = frozenset(
    {
        "OpenAI",
        "AsyncOpenAI",
        "Anthropic",
        "AsyncAnthropic",
        "ChatOpenAI",
        "ChatAnthropic",
        "Cohere",
        "Replicate",
        "Together",
        "Groq",
        "HuggingFaceHub",
        "GoogleGenerativeAI",
    }
)

# Known AI method patterns (method names that indicate AI usage)
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
    }
)


class PythonAnalyzer(BaseAnalyzer):
    """Analyze Python code for AI component usage using tree-sitter."""

    def __init__(self) -> None:
        """Initialize the Python analyzer with tree-sitter parser."""
        self._language = Language(tspython.language())
        self._parser = Parser(self._language)

        # Query for function definitions
        self._func_query = Query(
            self._language,
            """
            (function_definition
                name: (identifier) @func_name) @func_def
            """,
        )

        # Query for simple function calls (identifier)
        self._simple_call_query = Query(
            self._language,
            """
            (call
                function: (identifier) @func_name) @call
            """,
        )

        # Query for method calls (attribute access)
        self._method_call_query = Query(
            self._language,
            """
            (call
                function: (attribute
                    object: (identifier) @object_name
                    attribute: (identifier) @method_name)) @call
            """,
        )

        # Query for assignments: var = expr
        self._assignment_query = Query(
            self._language,
            """
            (assignment
                left: (identifier) @var_name
                right: (call) @call_expr) @assignment
            """,
        )

        # Query for return statements
        self._return_query = Query(
            self._language,
            """
            (return_statement
                (identifier) @var_name) @return
            """,
        )

        # Query for function call arguments
        self._call_args_query = Query(
            self._language,
            """
            (call
                function: (_) @func
                arguments: (argument_list
                    (identifier) @arg_name)) @call
            """,
        )

    @property
    def language(self) -> str:
        return "python"

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({".py"})

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
        """Analyze Python code for AI component usage.

        Detects:
        - Client instantiations (OpenAI(), Anthropic(), etc.)
        - Method calls on AI clients (.chat.completions.create(), etc.)

        Args:
            content: Python source code.
            path: File path.

        Returns:
            List of AI component usages found.
        """
        tree = self._parser.parse(content.encode("utf-8"))
        usages: list[ComponentUsage] = []
        functions = self._get_function_ranges(tree)

        # Find simple function calls (class instantiations)
        cursor = QueryCursor(self._simple_call_query)
        for _, captures in cursor.matches(tree.root_node):
            func_name_nodes = captures.get("func_name", [])
            call_nodes = captures.get("call", [])

            if func_name_nodes and call_nodes:
                func_name = func_name_nodes[0].text.decode("utf-8")
                call_node = call_nodes[0]

                if func_name in AI_CLIENT_PATTERNS:
                    line = call_node.start_point[0]
                    usages.append(
                        ComponentUsage(
                            component_id=func_name.lower(),
                            usage_type="instantiation",
                            function_context=self._get_current_function(functions, line),
                            file_path=str(path),
                            line=line + 1,
                            details={"class": func_name},
                        )
                    )

        # Find method calls
        cursor = QueryCursor(self._method_call_query)
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
        """Extract function call graph from Python code.

        Args:
            content: Python source code.
            path: File path.

        Returns:
            List of function calls.
        """
        tree = self._parser.parse(content.encode("utf-8"))
        calls: list[FunctionCall] = []
        functions = self._get_function_ranges(tree)

        # Get simple function calls
        cursor = QueryCursor(self._simple_call_query)
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
        cursor = QueryCursor(self._method_call_query)
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

    def extract_dataflow(self, content: str, path: Path) -> DataFlowGraph:
        """Extract data flow graph showing how AI outputs propagate.

        Tracks:
        - Variable assignments from AI SDK calls (definitions)
        - Variables passed to functions (arguments)
        - Variables returned from functions (returns)

        Args:
            content: Python source code.
            path: File path.

        Returns:
            DataFlowGraph tracking AI component output flow.
        """
        tree = self._parser.parse(content.encode("utf-8"))
        graph = DataFlowGraph()
        functions = self._get_function_ranges(tree)

        # Phase 1: Find variable definitions from AI SDK calls
        cursor = QueryCursor(self._assignment_query)
        for _, captures in cursor.matches(tree.root_node):
            var_nodes = captures.get("var_name", [])
            call_nodes = captures.get("call_expr", [])

            if var_nodes and call_nodes:
                var_name = var_nodes[0].text.decode("utf-8")
                call_node = call_nodes[0]
                line = call_node.start_point[0]
                func_ctx = self._get_current_function(functions, line)

                # Check if the call is an AI SDK instantiation
                call_text = call_node.text.decode("utf-8")
                component_id = self._extract_ai_component(call_text)
                if component_id:
                    graph.add_definition(
                        variable=var_name,
                        component_id=component_id,
                        file_path=str(path),
                        line=line + 1,
                        function_context=func_ctx,
                    )

        # Phase 2: Find returns of tainted variables
        cursor = QueryCursor(self._return_query)
        for _, captures in cursor.matches(tree.root_node):
            var_nodes = captures.get("var_name", [])
            return_nodes = captures.get("return", [])

            if var_nodes and return_nodes:
                var_name = var_nodes[0].text.decode("utf-8")
                return_node = return_nodes[0]
                line = return_node.start_point[0]
                func_ctx = self._get_current_function(functions, line)

                if graph.is_tainted(var_name, func_ctx):
                    graph.add_use(
                        variable=var_name,
                        flow_type=FlowType.RETURN,
                        file_path=str(path),
                        line=line + 1,
                        function_context=func_ctx,
                    )

        # Phase 3: Find tainted variables passed as arguments
        cursor = QueryCursor(self._call_args_query)
        for _, captures in cursor.matches(tree.root_node):
            func_nodes = captures.get("func", [])
            arg_nodes = captures.get("arg_name", [])
            call_nodes = captures.get("call", [])

            if arg_nodes and call_nodes:
                for arg_node in arg_nodes:
                    arg_name = arg_node.text.decode("utf-8")
                    call_node = call_nodes[0]
                    line = call_node.start_point[0]
                    func_ctx = self._get_current_function(functions, line)

                    if graph.is_tainted(arg_name, func_ctx):
                        # Get target function name
                        target_func = None
                        if func_nodes:
                            target_func = func_nodes[0].text.decode("utf-8")

                        graph.add_use(
                            variable=arg_name,
                            flow_type=FlowType.ARGUMENT,
                            file_path=str(path),
                            line=line + 1,
                            function_context=func_ctx,
                            target_function=target_func,
                        )

        return graph

    def _extract_ai_component(self, call_text: str) -> str | None:
        """Extract AI component ID from a call expression text."""
        for pattern in AI_CLIENT_PATTERNS:
            if pattern in call_text:
                return pattern.lower()
        for pattern in AI_METHOD_PATTERNS:
            if f".{pattern}(" in call_text:
                return pattern
        return None
