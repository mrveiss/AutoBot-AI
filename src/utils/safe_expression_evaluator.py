# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Safe expression evaluator to replace eval()
"""

import ast
import operator as op
from typing import Any, Dict


class SafeExpressionEvaluator:
    """Safely evaluate mathematical and logical expressions without eval()"""

    # Supported operators
    OPERATORS = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.Mod: op.mod,
        ast.Eq: op.eq,
        ast.NotEq: op.ne,
        ast.Lt: op.lt,
        ast.LtE: op.le,
        ast.Gt: op.gt,
        ast.GtE: op.ge,
        ast.And: lambda x, y: x and y,
        ast.Or: lambda x, y: x or y,
        ast.Not: op.not_,
    }

    def evaluate(self, expression: str, context: Dict[str, Any] = None) -> Any:
        """
        Safely evaluate an expression

        Args:
            expression: The expression to evaluate
            context: Dictionary of variable names to values

        Returns:
            The result of the expression

        Raises:
            ValueError: If the expression contains unsupported operations
        """
        if context is None:
            context = {}

        try:
            # Parse the expression into an AST
            tree = ast.parse(expression, mode="eval")

            # Evaluate the AST
            return self._eval_node(tree.body, context)

        except Exception as e:
            raise ValueError(f"Invalid expression: {e}")

    def _eval_constant(self, node: ast.Constant, context: Dict[str, Any]) -> Any:
        """Evaluate constant node (Issue #315 - extracted method)."""
        return node.value

    def _eval_num(self, node: ast.Num, context: Dict[str, Any]) -> Any:
        """Evaluate legacy Num node (Issue #315 - extracted method)."""
        return node.n

    def _eval_str(self, node: ast.Str, context: Dict[str, Any]) -> Any:
        """Evaluate legacy Str node (Issue #315 - extracted method)."""
        return node.s

    def _eval_node(self, node: ast.AST, context: Dict[str, Any]) -> Any:
        """Recursively evaluate an AST node (Issue #315 - dispatch table)."""
        # O(1) dispatch table lookup
        dispatch = {
            ast.Constant: self._eval_constant,
            ast.Name: self._eval_name,
            ast.Compare: self._eval_compare,
            ast.BinOp: self._eval_binop,
            ast.UnaryOp: self._eval_unaryop,
            ast.BoolOp: self._eval_boolop,
            # Backwards compatibility with older Python AST
            ast.Num: self._eval_num,
            ast.Str: self._eval_str,
        }

        handler = dispatch.get(type(node))
        if handler:
            return handler(node, context)

        raise ValueError(f"Unsupported node type: {type(node).__name__}")

    def _eval_name(self, node: ast.Name, context: Dict[str, Any]) -> Any:
        """Evaluate variable name (Issue #315 - extracted method)"""
        if node.id not in context:
            raise ValueError(f"Unknown variable: {node.id}")
        return context[node.id]

    def _eval_compare(self, node: ast.Compare, context: Dict[str, Any]) -> bool:
        """Evaluate comparison (Issue #315 - extracted method)"""
        left = self._eval_node(node.left, context)

        for op_node, comparator in zip(node.ops, node.comparators):
            op_type = type(op_node)
            if op_type not in self.OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")

            right = self._eval_node(comparator, context)

            if not self.OPERATORS[op_type](left, right):
                return False

            left = right

        return True

    def _eval_binop(self, node: ast.BinOp, context: Dict[str, Any]) -> Any:
        """Evaluate binary operation (Issue #315 - extracted method)"""
        op_type = type(node.op)
        if op_type not in self.OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")

        left = self._eval_node(node.left, context)
        right = self._eval_node(node.right, context)

        return self.OPERATORS[op_type](left, right)

    def _eval_unaryop(self, node: ast.UnaryOp, context: Dict[str, Any]) -> Any:
        """Evaluate unary operation (Issue #315 - extracted method)"""
        op_type = type(node.op)
        if op_type not in self.OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")

        operand = self._eval_node(node.operand, context)

        return self.OPERATORS[op_type](operand)

    def _eval_boolop(self, node: ast.BoolOp, context: Dict[str, Any]) -> bool:
        """Evaluate boolean operation with short-circuit (Issue #315 - extracted method)"""
        op_type = type(node.op)
        if op_type not in self.OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")

        # Short-circuit evaluation
        if isinstance(node.op, ast.And):
            for value in node.values:
                result = self._eval_node(value, context)
                if not result:
                    return False
            return True
        else:  # ast.Or
            for value in node.values:
                result = self._eval_node(value, context)
                if result:
                    return True
            return False


# Singleton instance
safe_evaluator = SafeExpressionEvaluator()
