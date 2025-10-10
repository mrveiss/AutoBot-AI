"""
Safe expression evaluator to replace eval()
"""

import ast
import operator as op
from typing import Any, Dict
from src.constants.network_constants import NetworkConstants


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

    def _eval_node(self, node: ast.AST, context: Dict[str, Any]) -> Any:
        """Recursively evaluate an AST node"""

        if isinstance(node, ast.Constant):
            # Python 3.8+ uses ast.Constant
            return node.value

        elif isinstance(node, ast.Num):
            # Backwards compatibility
            return node.n

        elif isinstance(node, ast.Str):
            # Backwards compatibility
            return node.s

        elif isinstance(node, ast.Name):
            # Variable lookup
            if node.id in context:
                return context[node.id]
            else:
                raise ValueError(f"Unknown variable: {node.id}")

        elif isinstance(node, ast.Compare):
            # Comparison operations
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

        elif isinstance(node, ast.BinOp):
            # Binary operations
            op_type = type(node.op)
            if op_type not in self.OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")

            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)

            return self.OPERATORS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            # Unary operations
            op_type = type(node.op)
            if op_type not in self.OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")

            operand = self._eval_node(node.operand, context)

            return self.OPERATORS[op_type](operand)

        elif isinstance(node, ast.BoolOp):
            # Boolean operations (and, or)
            op_type = type(node.op)
            if op_type not in self.OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")

            # Evaluate with short-circuit behavior
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

        else:
            raise ValueError(f"Unsupported node type: {type(node).__name__}")


# Singleton instance
safe_evaluator = SafeExpressionEvaluator()
