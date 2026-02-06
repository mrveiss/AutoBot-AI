# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Semantic Hasher Module

Generates semantic fingerprints based on data and control flow analysis.
Used for Type 4 clone detection where code is functionally equivalent
but structurally different.

Extracted from code_fingerprinting.py as part of Issue #381 refactoring.
"""

import ast
import hashlib
from typing import Any, Dict, List, Optional, Set

# Module-level constant for function definition types (Issue #380)
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


class SemanticHasher:
    """
    Generates semantic fingerprints based on data and control flow.

    Used for Type 4 clone detection where code is functionally equivalent
    but structurally different.
    """

    def __init__(self):
        """Initialize semantic hasher with AST hasher dependency."""
        from src.code_intelligence.fingerprinting.ast_hasher import ASTHasher

        self.ast_hasher = ASTHasher()

    def hash_semantic(self, node: ast.AST) -> str:
        """
        Generate a semantic hash of an AST node.

        This captures:
        - Input/output signatures
        - Control flow patterns
        - Data dependencies
        """
        semantic_repr = self._extract_semantic_representation(node)
        return hashlib.sha256(str(semantic_repr).encode("utf-8")).hexdigest()[:32]

    def _extract_semantic_representation(self, node: ast.AST) -> Dict[str, Any]:
        """
        Extract semantic features from an AST node.

        Args:
            node: AST node to analyze

        Returns:
            Dictionary of semantic features including inputs, outputs, control flow
        """
        return {
            "input_variables": self._find_inputs(node),
            "output_variables": self._find_outputs(node),
            "control_flow_pattern": self._extract_control_flow(node),
            "operation_sequence": self._extract_operations(node),
            "call_graph": self._extract_calls(node),
        }

    # Built-in names to exclude from input detection
    _BUILTIN_NAMES = frozenset({
        "print", "len", "str", "int", "float", "list", "dict", "set",
        "tuple", "range", "enumerate", "zip", "True", "False", "None",
    })

    def _find_inputs(self, node: ast.AST) -> List[str]:
        """
        Find variables that are read but not defined in the node.

        Args:
            node: AST node to analyze

        Returns:
            Sorted list of input variable names
        """
        defined: Set[str] = set()
        used: Set[str] = set()

        for child in ast.walk(node):
            self._process_node_for_inputs(child, defined, used)

        inputs = used - defined - self._BUILTIN_NAMES
        return sorted(inputs)

    def _process_node_for_inputs(
        self, child: ast.AST, defined: Set[str], used: Set[str]
    ) -> None:
        """
        Process a single node for input/output variable tracking.

        Args:
            child: AST node to process
            defined: Set of defined variables (modified in place)
            used: Set of used variables (modified in place)
        """
        if isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Store):
                defined.add(child.id)
            elif isinstance(child.ctx, ast.Load):
                used.add(child.id)
        elif isinstance(child, _FUNCTION_DEF_TYPES):
            for arg in child.args.args:
                defined.add(arg.arg)

    def _find_outputs(self, node: ast.AST) -> List[str]:
        """
        Find variables that are defined/modified in the node.

        Args:
            node: AST node to analyze

        Returns:
            Sorted list of output variable names
        """
        outputs: Set[str] = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                outputs.add(child.id)
            elif isinstance(child, ast.Return) and child.value:
                outputs.add("$RETURN$")

        return sorted(outputs)

    # Dispatch table for control flow extraction
    _CONTROL_FLOW_MAP = {
        ast.If: "IF",
        ast.For: "FOR",
        ast.While: "WHILE",
        ast.Try: "TRY",
        ast.With: "WITH",
        ast.Return: "RETURN",
        ast.Raise: "RAISE",
        ast.Break: "BREAK",
        ast.Continue: "CONTINUE",
    }

    def _extract_control_flow(self, node: ast.AST) -> List[str]:
        """
        Extract control flow pattern as a sequence of control structures.

        Args:
            node: AST node to analyze

        Returns:
            List of control flow keywords in order of appearance
        """
        pattern: List[str] = []
        for child in ast.walk(node):
            label = self._CONTROL_FLOW_MAP.get(type(child))
            if label:
                pattern.append(label)
        return pattern

    def _extract_operations(self, node: ast.AST) -> List[str]:
        """
        Extract sequence of operations/operators used.

        Args:
            node: AST node to analyze

        Returns:
            List of operation strings
        """
        operations: List[str] = []
        for child in ast.walk(node):
            op_str = self._get_operation_string(child)
            if op_str:
                if isinstance(op_str, list):
                    operations.extend(op_str)
                else:
                    operations.append(op_str)
        return operations

    def _get_operation_string(self, child: ast.AST) -> Optional[str | List[str]]:
        """
        Get operation string for an AST node.

        Args:
            child: AST node to check

        Returns:
            Operation string or list of strings, None if not an operation
        """
        if isinstance(child, ast.BinOp):
            return f"BINOP:{type(child.op).__name__}"
        if isinstance(child, ast.UnaryOp):
            return f"UNARYOP:{type(child.op).__name__}"
        if isinstance(child, ast.Compare):
            return [f"COMPARE:{type(op).__name__}" for op in child.ops]
        if isinstance(child, ast.BoolOp):
            return f"BOOLOP:{type(child.op).__name__}"
        if isinstance(child, ast.AugAssign):
            return f"AUGASSIGN:{type(child.op).__name__}"
        return None

    def _extract_calls(self, node: ast.AST) -> List[str]:
        """
        Extract function calls made within the node.

        Args:
            node: AST node to analyze

        Returns:
            List of function call names
        """
        calls: List[str] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            call_name = self._get_call_name(child)
            if call_name:
                calls.append(call_name)
        return calls

    def _get_call_name(self, call_node: ast.Call) -> Optional[str]:
        """
        Extract the function name from a Call node.

        Args:
            call_node: AST Call node

        Returns:
            Function name string or None if not extractable
        """
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        if isinstance(call_node.func, ast.Attribute):
            return f"*.{call_node.func.attr}"
        return None
