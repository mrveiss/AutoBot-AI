# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Type Inference Service (Issue #907)

Static type analysis for better completion suggestions.
"""

import ast
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class TypeInferencer:
    """
    Infers variable types from code context.

    Uses static analysis to track types through assignments,
    function returns, and type annotations.
    """

    def __init__(self):
        self.type_map: Dict[str, str] = {}
        self.builtins = {
            "int",
            "str",
            "float",
            "bool",
            "list",
            "dict",
            "set",
            "tuple",
            "None",
        }

    def infer_from_assignment(self, target: str, value: ast.expr) -> Optional[str]:
        """
        Infer type from assignment.

        Args:
            target: Variable name
            value: AST node of assigned value

        Returns:
            Inferred type name or None
        """
        if isinstance(value, ast.Constant):
            return type(value.value).__name__

        if isinstance(value, ast.List):
            return "list"
        if isinstance(value, ast.Dict):
            return "dict"
        if isinstance(value, ast.Set):
            return "set"
        if isinstance(value, ast.Tuple):
            return "tuple"

        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                # Constructor call like int(), str()
                if value.func.id in self.builtins:
                    return value.func.id
                # Function call - return type unknown
                return "Any"

        if isinstance(value, ast.Name):
            # Assignment from another variable
            return self.type_map.get(value.id, "Any")

        if isinstance(value, ast.BinOp):
            return self._infer_binop_type(value)

        if isinstance(value, ast.Compare):
            return "bool"

        return "Any"

    def _infer_binop_type(self, node: ast.BinOp) -> str:
        """
        Infer type from binary operation.

        Helper for infer_from_assignment (Issue #907).
        """
        left_type = self._get_expr_type(node.left)
        right_type = self._get_expr_type(node.right)

        # String concatenation
        if isinstance(node.op, ast.Add) and (left_type == "str" or right_type == "str"):
            return "str"

        # Numeric operations
        if isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow),
        ):
            if left_type == "float" or right_type == "float":
                return "float"
            if left_type == "int" and right_type == "int":
                return "int"

        return "Any"

    def _get_expr_type(self, node: ast.expr) -> str:
        """
        Get type of expression.

        Helper for _infer_binop_type (Issue #907).
        """
        if isinstance(node, ast.Constant):
            return type(node.value).__name__
        if isinstance(node, ast.Name):
            return self.type_map.get(node.id, "Any")
        return "Any"

    def infer_from_annotation(self, annotation: ast.expr) -> Optional[str]:
        """
        Extract type from type annotation.

        Args:
            annotation: AST annotation node

        Returns:
            Type name
        """
        if isinstance(annotation, ast.Name):
            return annotation.id

        if isinstance(annotation, ast.Subscript):
            # List[int], Dict[str, int], etc.
            if isinstance(annotation.value, ast.Name):
                container = annotation.value.id
                if isinstance(annotation.slice, ast.Name):
                    element = annotation.slice.id
                    return f"{container}[{element}]"
                return container

        if isinstance(annotation, ast.Constant):
            return str(annotation.value)

        return "Any"

    def infer_function_return_type(self, func_node: ast.FunctionDef) -> Optional[str]:
        """
        Infer function return type from annotation or body.

        Args:
            func_node: Function definition AST node

        Returns:
            Return type name
        """
        # Check explicit annotation
        if func_node.returns:
            return self.infer_from_annotation(func_node.returns)

        # Infer from return statements
        return_types: Set[str] = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value:
                inferred = self.infer_from_assignment("_return", node.value)
                if inferred:
                    return_types.add(inferred)

        # If all returns same type, use it
        if len(return_types) == 1:
            return return_types.pop()

        # Multiple or no returns
        return "Any" if return_types else "None"

    def extract_function_params(self, func_node: ast.FunctionDef):
        """
        Extract parameter types from function.

        Args:
            func_node: Function definition AST node

        Returns:
            List of (name, type) tuples
        """
        params = []
        for arg in func_node.args.args:
            param_name = arg.arg
            param_type = "Any"
            if arg.annotation:
                param_type = self.infer_from_annotation(arg.annotation)
            params.append((param_name, param_type))
        return params

    def analyze_scope(self, tree: ast.AST, scope_node: Optional[ast.AST] = None):
        """
        Analyze variables in scope.

        Args:
            tree: AST tree to analyze
            scope_node: Optional scope boundary (function/class)

        Returns:
            Dictionary mapping variable names to types
        """
        variables: Dict[str, str] = {}

        for node in ast.walk(scope_node or tree):
            # Skip nested functions/classes
            if scope_node and isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if node != scope_node:
                    continue

            # Assignment
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        inferred = self.infer_from_assignment(target.id, node.value)
                        if inferred:
                            variables[target.id] = inferred

            # Annotated assignment
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    var_type = self.infer_from_annotation(node.annotation)
                    if var_type:
                        variables[node.target.id] = var_type

            # For loop variable
            if isinstance(node, ast.For):
                if isinstance(node.target, ast.Name):
                    variables[node.target.id] = "Any"

        self.type_map.update(variables)
        return variables
