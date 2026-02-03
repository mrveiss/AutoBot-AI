# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AST Hasher Module

Generates fingerprints from AST nodes using multiple hashing strategies:
- Structural: Based on AST structure (Type 1 detection)
- Normalized: Normalized identifiers (Type 2 detection)

Extracted from code_fingerprinting.py as part of Issue #381 refactoring.
"""

import ast
import hashlib
import logging
from typing import Any, Dict, Tuple

from src.code_intelligence.fingerprinting.ast_normalizer import ASTNormalizer

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuples for AST node types used in isinstance checks
_EXPRESSION_TYPES = (ast.Expr, ast.BinOp, ast.UnaryOp, ast.Compare)
_CONTROL_FLOW_TYPES = (ast.If, ast.Try, ast.ExceptHandler)
_LOOP_TYPES = (ast.For, ast.While)
_ASSIGNMENT_TYPES = (ast.Assign, ast.AugAssign, ast.AnnAssign)
_DEFINITION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class ASTHasher:
    """
    Generates fingerprints from AST nodes.

    Provides multiple hashing strategies:
    - Structural: Based on AST structure (Type 1 detection)
    - Normalized: Normalized identifiers (Type 2 detection)
    """

    def __init__(self):
        """Initialize AST hasher with normalizer for identifier normalization."""
        self.normalizer = ASTNormalizer()

    def hash_structural(self, node: ast.AST) -> str:
        """
        Generate a structural hash of an AST node.

        This preserves all identifiers and is used for Type 1 clone detection.
        """
        return self._hash_node(node, normalize=False)

    def hash_normalized(self, node: ast.AST) -> str:
        """
        Generate a normalized hash of an AST node.

        Identifiers are replaced with placeholders for Type 2 clone detection.
        """
        return self._hash_node(node, normalize=True)

    def _hash_node(self, node: ast.AST, normalize: bool = False) -> str:
        """
        Hash an AST node with optional normalization.

        Args:
            node: AST node to hash
            normalize: Whether to normalize identifiers

        Returns:
            SHA-256 hash (first 32 characters) of the node structure
        """
        if normalize:
            # Create a fresh normalizer for each hash to ensure consistency
            normalizer = ASTNormalizer()
            try:
                node = normalizer.visit(node)
            except Exception as e:
                logger.debug("Normalization failed: %s", e)

        # Generate structural representation
        structure = self._node_to_structure(node)
        structure_str = str(structure)

        # Create hash
        return hashlib.sha256(structure_str.encode("utf-8")).hexdigest()[:32]

    def _node_to_structure(self, node: ast.AST) -> Tuple[str, ...]:
        """
        Convert AST node to a hashable structure tuple using dispatch table.

        Args:
            node: AST node to convert

        Returns:
            Tuple representing the node structure
        """
        if node is None:
            return ("None",)

        node_type = type(node).__name__

        # Use dispatch table for O(1) lookup instead of long if/elif chain
        handler = self._NODE_HANDLERS.get(type(node))
        if handler:
            return handler(self, node, node_type)

        # Fallback for any other node types
        children = tuple(
            self._node_to_structure(child) for child in ast.iter_child_nodes(node)
        )
        return (node_type, children)

    # =========================================================================
    # Node Handler Methods - Each handles one AST node type
    # =========================================================================

    def _handle_constant(self, node: ast.Constant, node_type: str) -> Tuple:
        """Handle Constant AST nodes."""
        return (node_type, type(node.value).__name__)

    def _handle_name(self, node: ast.Name, node_type: str) -> Tuple:
        """Handle Name AST nodes."""
        return (node_type, node.id, type(node.ctx).__name__)

    def _handle_function_def(self, node: ast.FunctionDef, node_type: str) -> Tuple:
        """Handle FunctionDef AST nodes."""
        args_tuple = self._args_to_structure(node.args)
        body_tuple = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, node.name, args_tuple, body_tuple)

    def _handle_async_function_def(
        self, node: ast.AsyncFunctionDef, node_type: str
    ) -> Tuple:
        """Handle AsyncFunctionDef AST nodes."""
        args_tuple = self._args_to_structure(node.args)
        body_tuple = tuple(self._node_to_structure(n) for n in node.body)
        return ("AsyncFunctionDef", node.name, args_tuple, body_tuple)

    def _handle_class_def(self, node: ast.ClassDef, node_type: str) -> Tuple:
        """Handle ClassDef AST nodes."""
        body_tuple = tuple(self._node_to_structure(n) for n in node.body)
        bases_tuple = tuple(self._node_to_structure(b) for b in node.bases)
        return (node_type, node.name, bases_tuple, body_tuple)

    def _handle_binop(self, node: ast.BinOp, node_type: str) -> Tuple:
        """Handle BinOp AST nodes."""
        left = self._node_to_structure(node.left)
        right = self._node_to_structure(node.right)
        op = type(node.op).__name__
        return (node_type, op, left, right)

    def _handle_compare(self, node: ast.Compare, node_type: str) -> Tuple:
        """Handle Compare AST nodes."""
        left = self._node_to_structure(node.left)
        ops = tuple(type(op).__name__ for op in node.ops)
        comparators = tuple(self._node_to_structure(c) for c in node.comparators)
        return (node_type, left, ops, comparators)

    def _handle_call(self, node: ast.Call, node_type: str) -> Tuple:
        """Handle Call AST nodes."""
        func = self._node_to_structure(node.func)
        args = tuple(self._node_to_structure(a) for a in node.args)
        return (node_type, func, args)

    def _handle_attribute(self, node: ast.Attribute, node_type: str) -> Tuple:
        """Handle Attribute AST nodes."""
        value = self._node_to_structure(node.value)
        return (node_type, value, node.attr)

    def _handle_if(self, node: ast.If, node_type: str) -> Tuple:
        """Handle If AST nodes."""
        test = self._node_to_structure(node.test)
        body = tuple(self._node_to_structure(n) for n in node.body)
        orelse = tuple(self._node_to_structure(n) for n in node.orelse)
        return (node_type, test, body, orelse)

    def _handle_for(self, node: ast.For, node_type: str) -> Tuple:
        """Handle For AST nodes."""
        target = self._node_to_structure(node.target)
        iter_node = self._node_to_structure(node.iter)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, target, iter_node, body)

    def _handle_while(self, node: ast.While, node_type: str) -> Tuple:
        """Handle While AST nodes."""
        test = self._node_to_structure(node.test)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, test, body)

    def _handle_return(self, node: ast.Return, node_type: str) -> Tuple:
        """Handle Return AST nodes."""
        value = self._node_to_structure(node.value) if node.value else ("None",)
        return (node_type, value)

    def _handle_assign(self, node: ast.Assign, node_type: str) -> Tuple:
        """Handle Assign AST nodes."""
        targets = tuple(self._node_to_structure(t) for t in node.targets)
        value = self._node_to_structure(node.value)
        return (node_type, targets, value)

    def _handle_aug_assign(self, node: ast.AugAssign, node_type: str) -> Tuple:
        """Handle AugAssign AST nodes."""
        target = self._node_to_structure(node.target)
        op = type(node.op).__name__
        value = self._node_to_structure(node.value)
        return (node_type, target, op, value)

    def _handle_expr(self, node: ast.Expr, node_type: str) -> Tuple:
        """Handle Expr AST nodes."""
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_try(self, node: ast.Try, node_type: str) -> Tuple:
        """Handle Try AST nodes."""
        body = tuple(self._node_to_structure(n) for n in node.body)
        handlers = tuple(self._node_to_structure(h) for h in node.handlers)
        orelse = tuple(self._node_to_structure(n) for n in node.orelse)
        finalbody = tuple(self._node_to_structure(n) for n in node.finalbody)
        return (node_type, body, handlers, orelse, finalbody)

    def _handle_except_handler(self, node: ast.ExceptHandler, node_type: str) -> Tuple:
        """Handle ExceptHandler AST nodes."""
        handler_type = self._node_to_structure(node.type) if node.type else ("None",)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, handler_type, node.name, body)

    def _handle_with(self, node: ast.With, node_type: str) -> Tuple:
        """Handle With AST nodes."""
        items = tuple(self._node_to_structure(i) for i in node.items)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, items, body)

    def _handle_withitem(self, node: ast.withitem, node_type: str) -> Tuple:
        """Handle withitem AST nodes."""
        context = self._node_to_structure(node.context_expr)
        optional_vars = (
            self._node_to_structure(node.optional_vars)
            if node.optional_vars
            else ("None",)
        )
        return ("withitem", context, optional_vars)

    def _handle_list(self, node: ast.List, node_type: str) -> Tuple:
        """Handle List AST nodes."""
        elts = tuple(self._node_to_structure(e) for e in node.elts)
        return (node_type, elts)

    def _handle_dict(self, node: ast.Dict, node_type: str) -> Tuple:
        """Handle Dict AST nodes."""
        keys = tuple(
            self._node_to_structure(k) if k else ("None",) for k in node.keys
        )
        values = tuple(self._node_to_structure(v) for v in node.values)
        return (node_type, keys, values)

    def _handle_tuple(self, node: ast.Tuple, node_type: str) -> Tuple:
        """Handle Tuple AST nodes."""
        elts = tuple(self._node_to_structure(e) for e in node.elts)
        return (node_type, elts)

    def _handle_set(self, node: ast.Set, node_type: str) -> Tuple:
        """Handle Set AST nodes."""
        elts = tuple(self._node_to_structure(e) for e in node.elts)
        return (node_type, elts)

    def _handle_list_comp(self, node: ast.ListComp, node_type: str) -> Tuple:
        """Handle ListComp AST nodes."""
        elt = self._node_to_structure(node.elt)
        generators = tuple(self._node_to_structure(g) for g in node.generators)
        return (node_type, elt, generators)

    def _handle_comprehension(self, node: ast.comprehension, node_type: str) -> Tuple:
        """Handle comprehension AST nodes."""
        target = self._node_to_structure(node.target)
        iter_node = self._node_to_structure(node.iter)
        ifs = tuple(self._node_to_structure(i) for i in node.ifs)
        return ("comprehension", target, iter_node, ifs, node.is_async)

    def _handle_lambda(self, node: ast.Lambda, node_type: str) -> Tuple:
        """Handle Lambda AST nodes."""
        args = self._args_to_structure(node.args)
        body = self._node_to_structure(node.body)
        return (node_type, args, body)

    def _handle_unary_op(self, node: ast.UnaryOp, node_type: str) -> Tuple:
        """Handle UnaryOp AST nodes."""
        op = type(node.op).__name__
        operand = self._node_to_structure(node.operand)
        return (node_type, op, operand)

    def _handle_bool_op(self, node: ast.BoolOp, node_type: str) -> Tuple:
        """Handle BoolOp AST nodes."""
        op = type(node.op).__name__
        values = tuple(self._node_to_structure(v) for v in node.values)
        return (node_type, op, values)

    def _handle_if_exp(self, node: ast.IfExp, node_type: str) -> Tuple:
        """Handle IfExp AST nodes (ternary operator)."""
        test = self._node_to_structure(node.test)
        body = self._node_to_structure(node.body)
        orelse = self._node_to_structure(node.orelse)
        return (node_type, test, body, orelse)

    def _handle_subscript(self, node: ast.Subscript, node_type: str) -> Tuple:
        """Handle Subscript AST nodes."""
        value = self._node_to_structure(node.value)
        slice_node = self._node_to_structure(node.slice)
        return (node_type, value, slice_node)

    def _handle_slice(self, node: ast.Slice, node_type: str) -> Tuple:
        """Handle Slice AST nodes."""
        lower = self._node_to_structure(node.lower) if node.lower else ("None",)
        upper = self._node_to_structure(node.upper) if node.upper else ("None",)
        step = self._node_to_structure(node.step) if node.step else ("None",)
        return (node_type, lower, upper, step)

    def _handle_raise(self, node: ast.Raise, node_type: str) -> Tuple:
        """Handle Raise AST nodes."""
        exc = self._node_to_structure(node.exc) if node.exc else ("None",)
        cause = self._node_to_structure(node.cause) if node.cause else ("None",)
        return (node_type, exc, cause)

    def _handle_assert(self, node: ast.Assert, node_type: str) -> Tuple:
        """Handle Assert AST nodes."""
        test = self._node_to_structure(node.test)
        msg = self._node_to_structure(node.msg) if node.msg else ("None",)
        return (node_type, test, msg)

    def _handle_import(self, node: ast.Import, node_type: str) -> Tuple:
        """Handle Import AST nodes."""
        names = tuple((alias.name, alias.asname) for alias in node.names)
        return (node_type, names)

    def _handle_import_from(self, node: ast.ImportFrom, node_type: str) -> Tuple:
        """Handle ImportFrom AST nodes."""
        names = tuple((alias.name, alias.asname) for alias in node.names)
        return (node_type, node.module, names)

    def _handle_simple_stmt(self, node: ast.AST, node_type: str) -> Tuple:
        """Handle simple statements with no children: Pass, Break, Continue."""
        return (node_type,)

    def _handle_global(self, node: ast.Global, node_type: str) -> Tuple:
        """Handle Global AST nodes."""
        return (node_type, tuple(node.names))

    def _handle_nonlocal(self, node: ast.Nonlocal, node_type: str) -> Tuple:
        """Handle Nonlocal AST nodes."""
        return (node_type, tuple(node.names))

    def _handle_await(self, node: ast.Await, node_type: str) -> Tuple:
        """Handle Await AST nodes."""
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_yield(self, node: ast.Yield, node_type: str) -> Tuple:
        """Handle Yield AST nodes."""
        value = self._node_to_structure(node.value) if node.value else ("None",)
        return (node_type, value)

    def _handle_yield_from(self, node: ast.YieldFrom, node_type: str) -> Tuple:
        """Handle YieldFrom AST nodes."""
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_formatted_value(
        self, node: ast.FormattedValue, node_type: str
    ) -> Tuple:
        """Handle FormattedValue AST nodes (f-string values)."""
        value = self._node_to_structure(node.value)
        return (node_type, value, node.conversion)

    def _handle_joined_str(self, node: ast.JoinedStr, node_type: str) -> Tuple:
        """Handle JoinedStr AST nodes (f-strings)."""
        values = tuple(self._node_to_structure(v) for v in node.values)
        return (node_type, values)

    def _handle_starred(self, node: ast.Starred, node_type: str) -> Tuple:
        """Handle Starred AST nodes (*args)."""
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_named_expr(self, node: ast.NamedExpr, node_type: str) -> Tuple:
        """Handle NamedExpr AST nodes (walrus operator :=)."""
        target = self._node_to_structure(node.target)
        value = self._node_to_structure(node.value)
        return (node_type, target, value)

    # Dispatch table mapping AST node types to handler methods
    _NODE_HANDLERS = {
        ast.Constant: _handle_constant,
        ast.Name: _handle_name,
        ast.FunctionDef: _handle_function_def,
        ast.AsyncFunctionDef: _handle_async_function_def,
        ast.ClassDef: _handle_class_def,
        ast.BinOp: _handle_binop,
        ast.Compare: _handle_compare,
        ast.Call: _handle_call,
        ast.Attribute: _handle_attribute,
        ast.If: _handle_if,
        ast.For: _handle_for,
        ast.While: _handle_while,
        ast.Return: _handle_return,
        ast.Assign: _handle_assign,
        ast.AugAssign: _handle_aug_assign,
        ast.Expr: _handle_expr,
        ast.Try: _handle_try,
        ast.ExceptHandler: _handle_except_handler,
        ast.With: _handle_with,
        ast.withitem: _handle_withitem,
        ast.List: _handle_list,
        ast.Dict: _handle_dict,
        ast.Tuple: _handle_tuple,
        ast.Set: _handle_set,
        ast.ListComp: _handle_list_comp,
        ast.comprehension: _handle_comprehension,
        ast.Lambda: _handle_lambda,
        ast.UnaryOp: _handle_unary_op,
        ast.BoolOp: _handle_bool_op,
        ast.IfExp: _handle_if_exp,
        ast.Subscript: _handle_subscript,
        ast.Slice: _handle_slice,
        ast.Raise: _handle_raise,
        ast.Assert: _handle_assert,
        ast.Import: _handle_import,
        ast.ImportFrom: _handle_import_from,
        ast.Pass: _handle_simple_stmt,
        ast.Break: _handle_simple_stmt,
        ast.Continue: _handle_simple_stmt,
        ast.Global: _handle_global,
        ast.Nonlocal: _handle_nonlocal,
        ast.Await: _handle_await,
        ast.Yield: _handle_yield,
        ast.YieldFrom: _handle_yield_from,
        ast.FormattedValue: _handle_formatted_value,
        ast.JoinedStr: _handle_joined_str,
        ast.Starred: _handle_starred,
        ast.NamedExpr: _handle_named_expr,
    }

    def _args_to_structure(self, args: ast.arguments) -> Tuple:
        """
        Convert arguments to a hashable structure.

        Args:
            args: AST arguments object

        Returns:
            Tuple with argument counts and flags
        """
        return (
            len(args.args),
            len(args.kwonlyargs),
            args.vararg is not None,
            args.kwarg is not None,
            len(args.defaults),
        )

    def extract_features(self, node: ast.AST) -> Dict[str, Any]:
        """
        Extract structural features from an AST node.

        Returns metrics useful for similarity comparison.
        """
        features: Dict[str, Any] = {
            "node_count": 0,
            "depth": 0,
            "statement_count": 0,
            "expression_count": 0,
            "control_flow_count": 0,
            "loop_count": 0,
            "function_call_count": 0,
            "assignment_count": 0,
            "operator_types": set(),
            "node_types": set(),
        }

        self._count_features(node, features, depth=0)

        # Convert sets to lists for JSON serialization
        features["operator_types"] = list(features["operator_types"])
        features["node_types"] = list(features["node_types"])

        return features

    def _count_node_types(self, node: ast.AST, features: Dict[str, Any]) -> None:
        """
        Count specific node types and update feature counters.

        Issue #665: Extracted from _count_features to improve maintainability.

        Args:
            node: AST node to check
            features: Dictionary to accumulate feature counts
        """
        if isinstance(node, _EXPRESSION_TYPES):
            features["expression_count"] += 1
        if isinstance(node, _CONTROL_FLOW_TYPES):
            features["control_flow_count"] += 1
        if isinstance(node, _LOOP_TYPES):
            features["loop_count"] += 1
        if isinstance(node, ast.Call):
            features["function_call_count"] += 1
        if isinstance(node, _ASSIGNMENT_TYPES):
            features["assignment_count"] += 1
        if isinstance(node, _DEFINITION_TYPES):
            features["statement_count"] += 1

    def _track_operator_types(self, node: ast.AST, features: Dict[str, Any]) -> None:
        """
        Track operator types from various operator nodes.

        Issue #665: Extracted from _count_features to improve maintainability.

        Args:
            node: AST node to check for operators
            features: Dictionary with operator_types set to update
        """
        if isinstance(node, ast.BinOp):
            features["operator_types"].add(type(node.op).__name__)
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                features["operator_types"].add(type(op).__name__)
        elif isinstance(node, ast.BoolOp):
            features["operator_types"].add(type(node.op).__name__)
        elif isinstance(node, ast.UnaryOp):
            features["operator_types"].add(type(node.op).__name__)

    def _count_features(
        self, node: ast.AST, features: Dict[str, Any], depth: int
    ) -> None:
        """
        Recursively count features in an AST node.

        Issue #665: Refactored to use extracted helpers for node type
        counting and operator tracking.

        Args:
            node: AST node to analyze
            features: Dictionary to accumulate feature counts
            depth: Current recursion depth
        """
        features["node_count"] += 1
        features["depth"] = max(features["depth"], depth)
        features["node_types"].add(type(node).__name__)

        # Issue #380: Use module-level constants for type checking
        self._count_node_types(node, features)
        self._track_operator_types(node, features)

        # Recurse into children
        for child in ast.iter_child_nodes(node):
            self._count_features(child, features, depth + 1)
