# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AST Normalizer Module

Normalizes AST nodes for code fingerprinting by replacing identifiers
with placeholders to enable Type 2 clone detection.

Extracted from code_fingerprinting.py as part of Issue #381 refactoring.
"""

import ast
from typing import Dict

# Module-level constant for numeric type checking
_NUMERIC_TYPES = (int, float)


class ASTNormalizer(ast.NodeTransformer):
    """
    Normalizes AST by replacing identifiers with placeholders.

    This enables detection of Type 2 clones where only variable/function
    names have been changed.
    """

    def __init__(self):
        """Initialize normalizer with counters and preserved names list."""
        self.var_counter = 0
        self.func_counter = 0
        self.name_mapping: Dict[str, str] = {}
        # Common names that shouldn't be normalized
        self.preserved_names = {
            "self",
            "cls",
            "True",
            "False",
            "None",
            "__init__",
            "__str__",
            "__repr__",
            "__eq__",
            "__hash__",
            "__len__",
            "__iter__",
            "__next__",
            "__enter__",
            "__exit__",
            "__call__",
            "print",
            "len",
            "str",
            "int",
            "float",
            "list",
            "dict",
            "set",
            "tuple",
            "range",
            "enumerate",
            "zip",
            "map",
            "filter",
            "open",
            "isinstance",
            "issubclass",
            "hasattr",
            "getattr",
            "setattr",
            "super",
            "type",
            "Exception",
            "ValueError",
            "TypeError",
            "KeyError",
            "IndexError",
            "AttributeError",
        }

    def _get_placeholder(self, name: str, prefix: str) -> str:
        """
        Get or create a placeholder for an identifier.

        Args:
            name: Original identifier name
            prefix: Placeholder prefix (VAR or FUNC)

        Returns:
            Placeholder name or preserved original name
        """
        if name in self.preserved_names:
            return name
        if name not in self.name_mapping:
            if prefix == "VAR":
                self.var_counter += 1
                self.name_mapping[name] = f"${prefix}_{self.var_counter}$"
            else:
                self.func_counter += 1
                self.name_mapping[name] = f"${prefix}_{self.func_counter}$"
        return self.name_mapping[name]

    def visit_Name(self, node: ast.Name) -> ast.Name:
        """
        Normalize variable names.

        Args:
            node: AST Name node to normalize

        Returns:
            Name node with normalized identifier
        """
        new_name = self._get_placeholder(node.id, "VAR")
        return ast.Name(id=new_name, ctx=node.ctx)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """
        Normalize function names while preserving structure.

        Args:
            node: AST FunctionDef node to normalize

        Returns:
            FunctionDef node with normalized name and arguments
        """
        new_name = self._get_placeholder(node.name, "FUNC")
        new_args = self._normalize_arguments(node.args)
        new_body = [self.visit(stmt) for stmt in node.body]
        new_decorators = [self.visit(d) for d in node.decorator_list]
        return ast.FunctionDef(
            name=new_name,
            args=new_args,
            body=new_body,
            decorator_list=new_decorators,
            returns=self.visit(node.returns) if node.returns else None,
            lineno=node.lineno,
            col_offset=node.col_offset,
        )

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        """
        Normalize async function names.

        Args:
            node: AST AsyncFunctionDef node to normalize

        Returns:
            AsyncFunctionDef node with normalized name and arguments
        """
        new_name = self._get_placeholder(node.name, "FUNC")
        new_args = self._normalize_arguments(node.args)
        new_body = [self.visit(stmt) for stmt in node.body]
        new_decorators = [self.visit(d) for d in node.decorator_list]
        return ast.AsyncFunctionDef(
            name=new_name,
            args=new_args,
            body=new_body,
            decorator_list=new_decorators,
            returns=self.visit(node.returns) if node.returns else None,
            lineno=node.lineno,
            col_offset=node.col_offset,
        )

    def _normalize_arguments(self, args: ast.arguments) -> ast.arguments:
        """
        Normalize function arguments.

        Args:
            args: AST arguments object to normalize

        Returns:
            Normalized arguments with placeholder names
        """
        new_args = []
        for arg in args.args:
            new_name = self._get_placeholder(arg.arg, "VAR")
            new_args.append(
                ast.arg(
                    arg=new_name,
                    annotation=self.visit(arg.annotation) if arg.annotation else None,
                )
            )

        new_kwonlyargs = []
        for arg in args.kwonlyargs:
            new_name = self._get_placeholder(arg.arg, "VAR")
            new_kwonlyargs.append(
                ast.arg(
                    arg=new_name,
                    annotation=self.visit(arg.annotation) if arg.annotation else None,
                )
            )

        return ast.arguments(
            posonlyargs=[],
            args=new_args,
            vararg=(
                ast.arg(arg=self._get_placeholder(args.vararg.arg, "VAR"))
                if args.vararg
                else None
            ),
            kwonlyargs=new_kwonlyargs,
            kw_defaults=[
                self.visit(d) if d else None for d in args.kw_defaults
            ],
            kwarg=(
                ast.arg(arg=self._get_placeholder(args.kwarg.arg, "VAR"))
                if args.kwarg
                else None
            ),
            defaults=[self.visit(d) for d in args.defaults],
        )

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        """
        Normalize constants while preserving type information.

        Args:
            node: AST Constant node to normalize

        Returns:
            Constant node with normalized value
        """
        # Keep type but normalize value for string/number comparisons
        if isinstance(node.value, str):
            return ast.Constant(value="$STRING$")
        elif isinstance(node.value, _NUMERIC_TYPES):
            return ast.Constant(value=0)  # Normalize numbers
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        """
        Normalize argument names.

        Args:
            node: AST arg node to normalize

        Returns:
            arg node with normalized name
        """
        new_name = self._get_placeholder(node.arg, "VAR")
        return ast.arg(
            arg=new_name,
            annotation=self.visit(node.annotation) if node.annotation else None,
        )
