# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Fingerprinting System for Clone Detection

Provides comprehensive code clone detection capabilities including:
- AST-based structural fingerprinting
- Semantic hashing for deeper analysis
- Fuzzy matching for approximate clone detection
- Clone type classification (Type 1-4)
- Similarity scoring algorithms
- Refactoring suggestions for clone elimination

Clone Types Detected:
- Type 1: Exact clones (identical code)
- Type 2: Renamed clones (variable/function names changed)
- Type 3: Near-miss clones (statements added/removed/modified)
- Type 4: Semantic clones (functionally equivalent, structurally different)

Part of Issue #237 - Code Fingerprinting System for Clone Detection
Parent Epic: #217 - Advanced Code Intelligence
"""

import ast
import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for function definition AST nodes
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


# =============================================================================
# Enums and Constants
# =============================================================================


class CloneType(Enum):
    """Classification of code clone types."""

    TYPE_1 = "type_1"  # Exact clones (identical code)
    TYPE_2 = "type_2"  # Renamed clones (variable/function names changed)
    TYPE_3 = "type_3"  # Near-miss clones (statements modified)
    TYPE_4 = "type_4"  # Semantic clones (functionally equivalent)


class FingerprintType(Enum):
    """Types of fingerprints generated."""

    AST_STRUCTURAL = "ast_structural"  # Based on AST structure
    AST_NORMALIZED = "ast_normalized"  # Normalized identifiers
    SEMANTIC = "semantic"  # Based on data/control flow
    TOKEN_SEQUENCE = "token_sequence"  # Based on token patterns


class CloneSeverity(Enum):
    """Severity levels for detected clones."""

    INFO = "info"  # Single occurrence, just documentation
    LOW = "low"  # 2-3 occurrences, minor duplication
    MEDIUM = "medium"  # 4-6 occurrences, should be refactored
    HIGH = "high"  # 7+ occurrences, significant technical debt
    CRITICAL = "critical"  # Large clones, urgent refactoring needed


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CodeFragment:
    """Represents a code fragment that can be fingerprinted."""

    file_path: str
    start_line: int
    end_line: int
    source_code: str
    ast_node: Optional[ast.AST] = None
    fragment_type: str = "unknown"  # function, class, block, etc.
    entity_name: str = ""

    def __hash__(self) -> int:
        """
        Generate hash for use in sets and dictionaries.

        Returns:
            Hash value based on file path and line numbers
        """
        return hash((self.file_path, self.start_line, self.end_line))

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another CodeFragment.

        Args:
            other: Object to compare with

        Returns:
            True if fragments have same file path and line range
        """
        if not isinstance(other, CodeFragment):
            return False
        return (
            self.file_path == other.file_path
            and self.start_line == other.start_line
            and self.end_line == other.end_line
        )

    @property
    def line_count(self) -> int:
        """Get the number of lines in this fragment."""
        return self.end_line - self.start_line + 1


@dataclass
class Fingerprint:
    """A fingerprint representing code structure or semantics."""

    hash_value: str
    fingerprint_type: FingerprintType
    fragment: CodeFragment
    normalized_tokens: List[str] = field(default_factory=list)
    structural_features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hash_value": self.hash_value,
            "fingerprint_type": self.fingerprint_type.value,
            "file_path": self.fragment.file_path,
            "start_line": self.fragment.start_line,
            "end_line": self.fragment.end_line,
            "entity_name": self.fragment.entity_name,
            "line_count": self.fragment.line_count,
            "structural_features": self.structural_features,
        }


@dataclass
class CloneInstance:
    """Represents a single instance of a clone."""

    fragment: CodeFragment
    fingerprint: Fingerprint
    similarity_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.fragment.file_path,
            "start_line": self.fragment.start_line,
            "end_line": self.fragment.end_line,
            "entity_name": self.fragment.entity_name,
            "line_count": self.fragment.line_count,
            "similarity_score": self.similarity_score,
            "source_preview": self._get_source_preview(),
        }

    def _get_source_preview(self, max_lines: int = 5) -> str:
        """
        Get a preview of the source code.

        Args:
            max_lines: Maximum number of lines to include in preview

        Returns:
            Source code preview with ellipsis if truncated
        """
        lines = self.fragment.source_code.split("\n")[:max_lines]
        if len(self.fragment.source_code.split("\n")) > max_lines:
            lines.append("...")
        return "\n".join(lines)


@dataclass
class CloneGroup:
    """A group of code fragments that are clones of each other."""

    clone_type: CloneType
    severity: CloneSeverity
    instances: List[CloneInstance]
    canonical_fingerprint: str
    similarity_range: Tuple[float, float]  # (min, max) similarity
    total_duplicated_lines: int
    refactoring_suggestion: str = ""
    estimated_effort: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "clone_type": self.clone_type.value,
            "severity": self.severity.value,
            "instance_count": len(self.instances),
            "instances": [i.to_dict() for i in self.instances],
            "canonical_fingerprint": self.canonical_fingerprint,
            "similarity_range": {
                "min": self.similarity_range[0],
                "max": self.similarity_range[1],
            },
            "total_duplicated_lines": self.total_duplicated_lines,
            "refactoring_suggestion": self.refactoring_suggestion,
            "estimated_effort": self.estimated_effort,
        }


@dataclass
class CloneDetectionReport:
    """Complete report of clone detection analysis."""

    scan_path: str
    total_files: int
    total_fragments: int
    clone_groups: List[CloneGroup]
    clone_type_distribution: Dict[str, int]
    severity_distribution: Dict[str, int]
    total_duplicated_lines: int
    duplication_percentage: float
    top_cloned_files: List[Dict[str, Any]]
    refactoring_priorities: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scan_path": self.scan_path,
            "total_files": self.total_files,
            "total_fragments": self.total_fragments,
            "total_clone_groups": len(self.clone_groups),
            "clone_groups": [g.to_dict() for g in self.clone_groups],
            "clone_type_distribution": self.clone_type_distribution,
            "severity_distribution": self.severity_distribution,
            "total_duplicated_lines": self.total_duplicated_lines,
            "duplication_percentage": round(self.duplication_percentage, 2),
            "top_cloned_files": self.top_cloned_files,
            "refactoring_priorities": self.refactoring_priorities,
        }


# =============================================================================
# AST Normalizer - Prepares AST for fingerprinting
# =============================================================================


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
        elif isinstance(node.value, (int, float)):
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


# =============================================================================
# Fingerprint Generators
# =============================================================================


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
                logger.debug(f"Normalization failed: {e}")

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
        children = tuple(self._node_to_structure(child) for child in ast.iter_child_nodes(node))
        return (node_type, children)

    # =========================================================================
    # Node Handler Methods - Each handles one AST node type
    # =========================================================================

    def _handle_constant(self, node: ast.Constant, node_type: str) -> Tuple:
        """
        Handle Constant AST nodes.

        Args:
            node: Constant node
            node_type: String name of node type

        Returns:
            Tuple with node type and value type
        """
        return (node_type, type(node.value).__name__)

    def _handle_name(self, node: ast.Name, node_type: str) -> Tuple:
        """
        Handle Name AST nodes.

        Args:
            node: Name node
            node_type: String name of node type

        Returns:
            Tuple with node type, identifier, and context type
        """
        return (node_type, node.id, type(node.ctx).__name__)

    def _handle_function_def(self, node: ast.FunctionDef, node_type: str) -> Tuple:
        """
        Handle FunctionDef AST nodes.

        Args:
            node: FunctionDef node
            node_type: String name of node type

        Returns:
            Tuple with node type, name, arguments, and body
        """
        args_tuple = self._args_to_structure(node.args)
        body_tuple = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, node.name, args_tuple, body_tuple)

    def _handle_async_function_def(self, node: ast.AsyncFunctionDef, node_type: str) -> Tuple:
        """
        Handle AsyncFunctionDef AST nodes.

        Args:
            node: AsyncFunctionDef node
            node_type: String name of node type

        Returns:
            Tuple with node type, name, arguments, and body
        """
        args_tuple = self._args_to_structure(node.args)
        body_tuple = tuple(self._node_to_structure(n) for n in node.body)
        return ("AsyncFunctionDef", node.name, args_tuple, body_tuple)

    def _handle_class_def(self, node: ast.ClassDef, node_type: str) -> Tuple:
        """
        Handle ClassDef AST nodes.

        Args:
            node: ClassDef node
            node_type: String name of node type

        Returns:
            Tuple with node type, name, bases, and body
        """
        body_tuple = tuple(self._node_to_structure(n) for n in node.body)
        bases_tuple = tuple(self._node_to_structure(b) for b in node.bases)
        return (node_type, node.name, bases_tuple, body_tuple)

    def _handle_binop(self, node: ast.BinOp, node_type: str) -> Tuple:
        """
        Handle BinOp AST nodes.

        Args:
            node: BinOp node
            node_type: String name of node type

        Returns:
            Tuple with node type, operator, left, and right operands
        """
        left = self._node_to_structure(node.left)
        right = self._node_to_structure(node.right)
        op = type(node.op).__name__
        return (node_type, op, left, right)

    def _handle_compare(self, node: ast.Compare, node_type: str) -> Tuple:
        """
        Handle Compare AST nodes.

        Args:
            node: Compare node
            node_type: String name of node type

        Returns:
            Tuple with node type, left operand, operators, and comparators
        """
        left = self._node_to_structure(node.left)
        ops = tuple(type(op).__name__ for op in node.ops)
        comparators = tuple(self._node_to_structure(c) for c in node.comparators)
        return (node_type, left, ops, comparators)

    def _handle_call(self, node: ast.Call, node_type: str) -> Tuple:
        """
        Handle Call AST nodes.

        Args:
            node: Call node
            node_type: String name of node type

        Returns:
            Tuple with node type, function, and arguments
        """
        func = self._node_to_structure(node.func)
        args = tuple(self._node_to_structure(a) for a in node.args)
        return (node_type, func, args)

    def _handle_attribute(self, node: ast.Attribute, node_type: str) -> Tuple:
        """
        Handle Attribute AST nodes.

        Args:
            node: Attribute node
            node_type: String name of node type

        Returns:
            Tuple with node type, value, and attribute name
        """
        value = self._node_to_structure(node.value)
        return (node_type, value, node.attr)

    def _handle_if(self, node: ast.If, node_type: str) -> Tuple:
        """
        Handle If AST nodes.

        Args:
            node: If node
            node_type: String name of node type

        Returns:
            Tuple with node type, test condition, body, and orelse
        """
        test = self._node_to_structure(node.test)
        body = tuple(self._node_to_structure(n) for n in node.body)
        orelse = tuple(self._node_to_structure(n) for n in node.orelse)
        return (node_type, test, body, orelse)

    def _handle_for(self, node: ast.For, node_type: str) -> Tuple:
        """
        Handle For AST nodes.

        Args:
            node: For node
            node_type: String name of node type

        Returns:
            Tuple with node type, target, iterator, and body
        """
        target = self._node_to_structure(node.target)
        iter_node = self._node_to_structure(node.iter)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, target, iter_node, body)

    def _handle_while(self, node: ast.While, node_type: str) -> Tuple:
        """
        Handle While AST nodes.

        Args:
            node: While node
            node_type: String name of node type

        Returns:
            Tuple with node type, test condition, and body
        """
        test = self._node_to_structure(node.test)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, test, body)

    def _handle_return(self, node: ast.Return, node_type: str) -> Tuple:
        """
        Handle Return AST nodes.

        Args:
            node: Return node
            node_type: String name of node type

        Returns:
            Tuple with node type and return value
        """
        value = self._node_to_structure(node.value) if node.value else ("None",)
        return (node_type, value)

    def _handle_assign(self, node: ast.Assign, node_type: str) -> Tuple:
        """
        Handle Assign AST nodes.

        Args:
            node: Assign node
            node_type: String name of node type

        Returns:
            Tuple with node type, targets, and value
        """
        targets = tuple(self._node_to_structure(t) for t in node.targets)
        value = self._node_to_structure(node.value)
        return (node_type, targets, value)

    def _handle_aug_assign(self, node: ast.AugAssign, node_type: str) -> Tuple:
        """
        Handle AugAssign AST nodes.

        Args:
            node: AugAssign node
            node_type: String name of node type

        Returns:
            Tuple with node type, target, operator, and value
        """
        target = self._node_to_structure(node.target)
        op = type(node.op).__name__
        value = self._node_to_structure(node.value)
        return (node_type, target, op, value)

    def _handle_expr(self, node: ast.Expr, node_type: str) -> Tuple:
        """
        Handle Expr AST nodes.

        Args:
            node: Expr node
            node_type: String name of node type

        Returns:
            Tuple with node type and expression value
        """
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_try(self, node: ast.Try, node_type: str) -> Tuple:
        """
        Handle Try AST nodes.

        Args:
            node: Try node
            node_type: String name of node type

        Returns:
            Tuple with node type, body, handlers, orelse, and finalbody
        """
        body = tuple(self._node_to_structure(n) for n in node.body)
        handlers = tuple(self._node_to_structure(h) for h in node.handlers)
        orelse = tuple(self._node_to_structure(n) for n in node.orelse)
        finalbody = tuple(self._node_to_structure(n) for n in node.finalbody)
        return (node_type, body, handlers, orelse, finalbody)

    def _handle_except_handler(self, node: ast.ExceptHandler, node_type: str) -> Tuple:
        """
        Handle ExceptHandler AST nodes.

        Args:
            node: ExceptHandler node
            node_type: String name of node type

        Returns:
            Tuple with node type, exception type, name, and body
        """
        handler_type = self._node_to_structure(node.type) if node.type else ("None",)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, handler_type, node.name, body)

    def _handle_with(self, node: ast.With, node_type: str) -> Tuple:
        """
        Handle With AST nodes.

        Args:
            node: With node
            node_type: String name of node type

        Returns:
            Tuple with node type, items, and body
        """
        items = tuple(self._node_to_structure(i) for i in node.items)
        body = tuple(self._node_to_structure(n) for n in node.body)
        return (node_type, items, body)

    def _handle_withitem(self, node: ast.withitem, node_type: str) -> Tuple:
        """
        Handle withitem AST nodes.

        Args:
            node: withitem node
            node_type: String name of node type

        Returns:
            Tuple with context expression and optional vars
        """
        context = self._node_to_structure(node.context_expr)
        optional_vars = (
            self._node_to_structure(node.optional_vars)
            if node.optional_vars
            else ("None",)
        )
        return ("withitem", context, optional_vars)

    def _handle_list(self, node: ast.List, node_type: str) -> Tuple:
        """
        Handle List AST nodes.

        Args:
            node: List node
            node_type: String name of node type

        Returns:
            Tuple with node type and list elements
        """
        elts = tuple(self._node_to_structure(e) for e in node.elts)
        return (node_type, elts)

    def _handle_dict(self, node: ast.Dict, node_type: str) -> Tuple:
        """
        Handle Dict AST nodes.

        Args:
            node: Dict node
            node_type: String name of node type

        Returns:
            Tuple with node type, keys, and values
        """
        keys = tuple(self._node_to_structure(k) if k else ("None",) for k in node.keys)
        values = tuple(self._node_to_structure(v) for v in node.values)
        return (node_type, keys, values)

    def _handle_tuple(self, node: ast.Tuple, node_type: str) -> Tuple:
        """
        Handle Tuple AST nodes.

        Args:
            node: Tuple node
            node_type: String name of node type

        Returns:
            Tuple with node type and tuple elements
        """
        elts = tuple(self._node_to_structure(e) for e in node.elts)
        return (node_type, elts)

    def _handle_set(self, node: ast.Set, node_type: str) -> Tuple:
        """
        Handle Set AST nodes.

        Args:
            node: Set node
            node_type: String name of node type

        Returns:
            Tuple with node type and set elements
        """
        elts = tuple(self._node_to_structure(e) for e in node.elts)
        return (node_type, elts)

    def _handle_list_comp(self, node: ast.ListComp, node_type: str) -> Tuple:
        """
        Handle ListComp AST nodes.

        Args:
            node: ListComp node
            node_type: String name of node type

        Returns:
            Tuple with node type, element, and generators
        """
        elt = self._node_to_structure(node.elt)
        generators = tuple(self._node_to_structure(g) for g in node.generators)
        return (node_type, elt, generators)

    def _handle_comprehension(self, node: ast.comprehension, node_type: str) -> Tuple:
        """
        Handle comprehension AST nodes.

        Args:
            node: comprehension node
            node_type: String name of node type

        Returns:
            Tuple with target, iterator, conditions, and async flag
        """
        target = self._node_to_structure(node.target)
        iter_node = self._node_to_structure(node.iter)
        ifs = tuple(self._node_to_structure(i) for i in node.ifs)
        return ("comprehension", target, iter_node, ifs, node.is_async)

    def _handle_lambda(self, node: ast.Lambda, node_type: str) -> Tuple:
        """
        Handle Lambda AST nodes.

        Args:
            node: Lambda node
            node_type: String name of node type

        Returns:
            Tuple with node type, arguments, and body
        """
        args = self._args_to_structure(node.args)
        body = self._node_to_structure(node.body)
        return (node_type, args, body)

    def _handle_unary_op(self, node: ast.UnaryOp, node_type: str) -> Tuple:
        """
        Handle UnaryOp AST nodes.

        Args:
            node: UnaryOp node
            node_type: String name of node type

        Returns:
            Tuple with node type, operator, and operand
        """
        op = type(node.op).__name__
        operand = self._node_to_structure(node.operand)
        return (node_type, op, operand)

    def _handle_bool_op(self, node: ast.BoolOp, node_type: str) -> Tuple:
        """
        Handle BoolOp AST nodes.

        Args:
            node: BoolOp node
            node_type: String name of node type

        Returns:
            Tuple with node type, operator, and values
        """
        op = type(node.op).__name__
        values = tuple(self._node_to_structure(v) for v in node.values)
        return (node_type, op, values)

    def _handle_if_exp(self, node: ast.IfExp, node_type: str) -> Tuple:
        """
        Handle IfExp AST nodes (ternary operator).

        Args:
            node: IfExp node
            node_type: String name of node type

        Returns:
            Tuple with node type, test, body, and orelse
        """
        test = self._node_to_structure(node.test)
        body = self._node_to_structure(node.body)
        orelse = self._node_to_structure(node.orelse)
        return (node_type, test, body, orelse)

    def _handle_subscript(self, node: ast.Subscript, node_type: str) -> Tuple:
        """
        Handle Subscript AST nodes.

        Args:
            node: Subscript node
            node_type: String name of node type

        Returns:
            Tuple with node type, value, and slice
        """
        value = self._node_to_structure(node.value)
        slice_node = self._node_to_structure(node.slice)
        return (node_type, value, slice_node)

    def _handle_slice(self, node: ast.Slice, node_type: str) -> Tuple:
        """
        Handle Slice AST nodes.

        Args:
            node: Slice node
            node_type: String name of node type

        Returns:
            Tuple with node type, lower, upper, and step bounds
        """
        lower = self._node_to_structure(node.lower) if node.lower else ("None",)
        upper = self._node_to_structure(node.upper) if node.upper else ("None",)
        step = self._node_to_structure(node.step) if node.step else ("None",)
        return (node_type, lower, upper, step)

    def _handle_raise(self, node: ast.Raise, node_type: str) -> Tuple:
        """
        Handle Raise AST nodes.

        Args:
            node: Raise node
            node_type: String name of node type

        Returns:
            Tuple with node type, exception, and cause
        """
        exc = self._node_to_structure(node.exc) if node.exc else ("None",)
        cause = self._node_to_structure(node.cause) if node.cause else ("None",)
        return (node_type, exc, cause)

    def _handle_assert(self, node: ast.Assert, node_type: str) -> Tuple:
        """
        Handle Assert AST nodes.

        Args:
            node: Assert node
            node_type: String name of node type

        Returns:
            Tuple with node type, test condition, and message
        """
        test = self._node_to_structure(node.test)
        msg = self._node_to_structure(node.msg) if node.msg else ("None",)
        return (node_type, test, msg)

    def _handle_import(self, node: ast.Import, node_type: str) -> Tuple:
        """
        Handle Import AST nodes.

        Args:
            node: Import node
            node_type: String name of node type

        Returns:
            Tuple with node type and imported names
        """
        names = tuple((alias.name, alias.asname) for alias in node.names)
        return (node_type, names)

    def _handle_import_from(self, node: ast.ImportFrom, node_type: str) -> Tuple:
        """
        Handle ImportFrom AST nodes.

        Args:
            node: ImportFrom node
            node_type: String name of node type

        Returns:
            Tuple with node type, module, and imported names
        """
        names = tuple((alias.name, alias.asname) for alias in node.names)
        return (node_type, node.module, names)

    def _handle_simple_stmt(self, node: ast.AST, node_type: str) -> Tuple:
        """
        Handle simple statements with no children: Pass, Break, Continue.

        Args:
            node: Simple statement node
            node_type: String name of node type

        Returns:
            Tuple with only node type
        """
        return (node_type,)

    def _handle_global(self, node: ast.Global, node_type: str) -> Tuple:
        """
        Handle Global AST nodes.

        Args:
            node: Global node
            node_type: String name of node type

        Returns:
            Tuple with node type and global names
        """
        return (node_type, tuple(node.names))

    def _handle_nonlocal(self, node: ast.Nonlocal, node_type: str) -> Tuple:
        """
        Handle Nonlocal AST nodes.

        Args:
            node: Nonlocal node
            node_type: String name of node type

        Returns:
            Tuple with node type and nonlocal names
        """
        return (node_type, tuple(node.names))

    def _handle_await(self, node: ast.Await, node_type: str) -> Tuple:
        """
        Handle Await AST nodes.

        Args:
            node: Await node
            node_type: String name of node type

        Returns:
            Tuple with node type and awaited value
        """
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_yield(self, node: ast.Yield, node_type: str) -> Tuple:
        """
        Handle Yield AST nodes.

        Args:
            node: Yield node
            node_type: String name of node type

        Returns:
            Tuple with node type and yielded value
        """
        value = self._node_to_structure(node.value) if node.value else ("None",)
        return (node_type, value)

    def _handle_yield_from(self, node: ast.YieldFrom, node_type: str) -> Tuple:
        """
        Handle YieldFrom AST nodes.

        Args:
            node: YieldFrom node
            node_type: String name of node type

        Returns:
            Tuple with node type and yielded value
        """
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_formatted_value(self, node: ast.FormattedValue, node_type: str) -> Tuple:
        """
        Handle FormattedValue AST nodes (f-string values).

        Args:
            node: FormattedValue node
            node_type: String name of node type

        Returns:
            Tuple with node type, value, and conversion
        """
        value = self._node_to_structure(node.value)
        return (node_type, value, node.conversion)

    def _handle_joined_str(self, node: ast.JoinedStr, node_type: str) -> Tuple:
        """
        Handle JoinedStr AST nodes (f-strings).

        Args:
            node: JoinedStr node
            node_type: String name of node type

        Returns:
            Tuple with node type and joined values
        """
        values = tuple(self._node_to_structure(v) for v in node.values)
        return (node_type, values)

    def _handle_starred(self, node: ast.Starred, node_type: str) -> Tuple:
        """
        Handle Starred AST nodes (*args).

        Args:
            node: Starred node
            node_type: String name of node type

        Returns:
            Tuple with node type and starred value
        """
        value = self._node_to_structure(node.value)
        return (node_type, value)

    def _handle_named_expr(self, node: ast.NamedExpr, node_type: str) -> Tuple:
        """
        Handle NamedExpr AST nodes (walrus operator :=).

        Args:
            node: NamedExpr node
            node_type: String name of node type

        Returns:
            Tuple with node type, target, and value
        """
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

    def _count_features(
        self, node: ast.AST, features: Dict[str, Any], depth: int
    ) -> None:
        """
        Recursively count features in an AST node.

        Args:
            node: AST node to analyze
            features: Dictionary to accumulate feature counts
            depth: Current recursion depth
        """
        features["node_count"] += 1
        features["depth"] = max(features["depth"], depth)
        features["node_types"].add(type(node).__name__)

        # Count specific node types
        if isinstance(node, (ast.Expr, ast.BinOp, ast.UnaryOp, ast.Compare)):
            features["expression_count"] += 1
        if isinstance(node, (ast.If, ast.Try, ast.ExceptHandler)):
            features["control_flow_count"] += 1
        if isinstance(node, (ast.For, ast.While)):
            features["loop_count"] += 1
        if isinstance(node, ast.Call):
            features["function_call_count"] += 1
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            features["assignment_count"] += 1
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            features["statement_count"] += 1

        # Track operator types
        if isinstance(node, ast.BinOp):
            features["operator_types"].add(type(node.op).__name__)
        if isinstance(node, ast.Compare):
            for op in node.ops:
                features["operator_types"].add(type(op).__name__)
        if isinstance(node, ast.BoolOp):
            features["operator_types"].add(type(node.op).__name__)
        if isinstance(node, ast.UnaryOp):
            features["operator_types"].add(type(node.op).__name__)

        # Recurse into children
        for child in ast.iter_child_nodes(node):
            self._count_features(child, features, depth + 1)


class SemanticHasher:
    """
    Generates semantic fingerprints based on data and control flow.

    Used for Type 4 clone detection where code is functionally equivalent
    but structurally different.
    """

    def __init__(self):
        """Initialize semantic hasher with AST hasher dependency."""
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
        elif isinstance(child, _FUNCTION_DEF_TYPES):  # Issue #380
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


# =============================================================================
# Fuzzy Matching and Similarity
# =============================================================================


class SimilarityCalculator:
    """
    Calculates similarity between code fragments.

    Uses multiple metrics:
    - Jaccard similarity for sets
    - Levenshtein distance for sequences
    - Structural similarity for AST features
    """

    def __init__(self):
        """Initialize similarity calculator with AST hasher for comparisons."""
        self.ast_hasher = ASTHasher()

    def calculate_similarity(
        self,
        fragment1: CodeFragment,
        fragment2: CodeFragment,
    ) -> float:
        """
        Calculate overall similarity between two code fragments.

        Returns a score between 0.0 (no similarity) and 1.0 (identical).
        """
        if fragment1.ast_node is None or fragment2.ast_node is None:
            # Fall back to text-based similarity
            return self._text_similarity(
                fragment1.source_code, fragment2.source_code
            )

        # Calculate multiple similarity metrics
        structural_sim = self._structural_similarity(
            fragment1.ast_node, fragment2.ast_node
        )
        token_sim = self._token_similarity(
            fragment1.source_code, fragment2.source_code
        )
        feature_sim = self._feature_similarity(
            fragment1.ast_node, fragment2.ast_node
        )

        # Weighted average
        weights = {"structural": 0.5, "token": 0.3, "feature": 0.2}
        similarity = (
            weights["structural"] * structural_sim
            + weights["token"] * token_sim
            + weights["feature"] * feature_sim
        )

        return min(1.0, max(0.0, similarity))

    def _structural_similarity(self, node1: ast.AST, node2: ast.AST) -> float:
        """
        Calculate similarity based on AST structure.

        Args:
            node1: First AST node
            node2: Second AST node

        Returns:
            Similarity score between 0.0 and 1.0
        """
        features1 = self.ast_hasher.extract_features(node1)
        features2 = self.ast_hasher.extract_features(node2)

        # Compare node counts
        node_count_sim = 1.0 - abs(
            features1["node_count"] - features2["node_count"]
        ) / max(features1["node_count"], features2["node_count"], 1)

        # Compare node type sets
        types1 = set(features1["node_types"])
        types2 = set(features2["node_types"])
        node_type_sim = self._jaccard_similarity(types1, types2)

        # Compare operator types
        ops1 = set(features1["operator_types"])
        ops2 = set(features2["operator_types"])
        op_sim = self._jaccard_similarity(ops1, ops2) if ops1 or ops2 else 1.0

        return (node_count_sim + node_type_sim + op_sim) / 3

    def _token_similarity(self, code1: str, code2: str) -> float:
        """
        Calculate similarity based on token sequences.

        Args:
            code1: First code string
            code2: Second code string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        tokens1 = self._tokenize(code1)
        tokens2 = self._tokenize(code2)

        if not tokens1 or not tokens2:
            return 0.0

        # Use longest common subsequence ratio
        lcs_length = self._lcs_length(tokens1, tokens2)
        max_length = max(len(tokens1), len(tokens2))

        return lcs_length / max_length if max_length > 0 else 0.0

    def _feature_similarity(self, node1: ast.AST, node2: ast.AST) -> float:
        """
        Calculate similarity based on extracted features.

        Args:
            node1: First AST node
            node2: Second AST node

        Returns:
            Similarity score between 0.0 and 1.0
        """
        features1 = self.ast_hasher.extract_features(node1)
        features2 = self.ast_hasher.extract_features(node2)

        # Compare numeric features
        numeric_keys = [
            "node_count",
            "depth",
            "statement_count",
            "expression_count",
            "control_flow_count",
            "loop_count",
            "function_call_count",
            "assignment_count",
        ]

        similarities = []
        for key in numeric_keys:
            val1 = features1.get(key, 0)
            val2 = features2.get(key, 0)
            max_val = max(val1, val2, 1)
            similarities.append(1.0 - abs(val1 - val2) / max_val)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text-based similarity as fallback.

        Args:
            text1: First text string
            text2: Second text string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Normalize whitespace and compare
        normalized1 = " ".join(text1.split())
        normalized2 = " ".join(text2.split())

        if normalized1 == normalized2:
            return 1.0

        # Use character-level LCS
        lcs_length = self._lcs_length(list(normalized1), list(normalized2))
        max_length = max(len(normalized1), len(normalized2))

        return lcs_length / max_length if max_length > 0 else 0.0

    def _tokenize(self, code: str) -> List[str]:
        """
        Tokenize code into meaningful tokens.

        Args:
            code: Source code string

        Returns:
            List of tokens
        """
        # Simple tokenization - split on whitespace and punctuation
        tokens = re.findall(r"[a-zA-Z_]\w*|\d+|[^\s\w]", code)
        return tokens

    def _jaccard_similarity(self, set1: Set, set2: Set) -> float:
        """
        Calculate Jaccard similarity between two sets.

        Args:
            set1: First set
            set2: Second set

        Returns:
            Jaccard similarity coefficient between 0.0 and 1.0
        """
        if not set1 and not set2:
            return 1.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _lcs_length(self, seq1: List, seq2: List) -> int:
        """
        Calculate length of longest common subsequence.

        Args:
            seq1: First sequence
            seq2: Second sequence

        Returns:
            Length of longest common subsequence
        """
        m, n = len(seq1), len(seq2)
        if m == 0 or n == 0:
            return 0

        # Use space-optimized LCS
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i - 1] == seq2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, prev

        return prev[n]


# =============================================================================
# Clone Detector
# =============================================================================


class CloneDetector:
    """
    Main clone detection engine.

    Detects all four types of code clones:
    - Type 1: Exact clones
    - Type 2: Renamed clones
    - Type 3: Near-miss clones
    - Type 4: Semantic clones
    """

    # Minimum fragment size for detection (in lines)
    MIN_FRAGMENT_LINES = 5

    # Similarity thresholds
    TYPE_3_SIMILARITY_THRESHOLD = 0.7  # Minimum for Type 3 clones
    TYPE_4_SIMILARITY_THRESHOLD = 0.6  # Minimum for Type 4 clones

    def __init__(
        self,
        min_fragment_lines: int = 5,
        exclude_dirs: Optional[List[str]] = None,
    ):
        """
        Initialize the clone detector.

        Args:
            min_fragment_lines: Minimum lines for a fragment to be considered
            exclude_dirs: Directories to exclude from analysis
        """
        self.min_fragment_lines = min_fragment_lines
        self.exclude_dirs = exclude_dirs or [
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "archives",
            "archive",
            ".mypy_cache",
        ]

        self.ast_hasher = ASTHasher()
        self.semantic_hasher = SemanticHasher()
        self.similarity_calc = SimilarityCalculator()

        # Storage for fingerprints
        self._structural_fingerprints: Dict[str, List[Fingerprint]] = defaultdict(list)
        self._normalized_fingerprints: Dict[str, List[Fingerprint]] = defaultdict(list)
        self._semantic_fingerprints: Dict[str, List[Fingerprint]] = defaultdict(list)

    def detect_clones(self, directory: str) -> CloneDetectionReport:
        """
        Detect all clones in a directory.

        Args:
            directory: Path to the directory to analyze

        Returns:
            CloneDetectionReport with all findings
        """
        logger.info(f"Starting clone detection in: {directory}")

        # Reset fingerprint storage
        self._structural_fingerprints.clear()
        self._normalized_fingerprints.clear()
        self._semantic_fingerprints.clear()

        # Collect all fragments and generate fingerprints
        fragments: List[CodeFragment] = []
        total_files = 0
        total_lines = 0

        for py_file in self._get_python_files(directory):
            try:
                file_fragments = self._extract_fragments(py_file)
                fragments.extend(file_fragments)
                total_files += 1

                # Count total lines
                with open(py_file, "r", encoding="utf-8") as f:
                    total_lines += len(f.readlines())

            except Exception as e:
                logger.warning(f"Failed to process {py_file}: {e}")

        logger.info(f"Extracted {len(fragments)} fragments from {total_files} files")

        # Generate fingerprints for all fragments
        for fragment in fragments:
            self._generate_fingerprints(fragment)

        # Detect clones of each type
        clone_groups: List[CloneGroup] = []

        # Type 1: Exact clones (from structural fingerprints)
        type1_groups = self._detect_type1_clones()
        clone_groups.extend(type1_groups)

        # Type 2: Renamed clones (from normalized fingerprints)
        type2_groups = self._detect_type2_clones(type1_groups)
        clone_groups.extend(type2_groups)

        # Type 3: Near-miss clones (fuzzy matching)
        type3_groups = self._detect_type3_clones(fragments, type1_groups, type2_groups)
        clone_groups.extend(type3_groups)

        # Type 4: Semantic clones (from semantic fingerprints)
        type4_groups = self._detect_type4_clones(
            fragments, type1_groups, type2_groups, type3_groups
        )
        clone_groups.extend(type4_groups)

        # Add refactoring suggestions
        for group in clone_groups:
            group.refactoring_suggestion = self._generate_refactoring_suggestion(group)
            group.estimated_effort = self._estimate_refactoring_effort(group)

        # Calculate statistics
        total_duplicated_lines = sum(g.total_duplicated_lines for g in clone_groups)
        duplication_percentage = (
            (total_duplicated_lines / total_lines * 100) if total_lines > 0 else 0
        )

        # Calculate distributions
        clone_type_dist = self._calculate_type_distribution(clone_groups)
        severity_dist = self._calculate_severity_distribution(clone_groups)

        # Find top cloned files
        top_cloned_files = self._find_top_cloned_files(clone_groups)

        # Prioritize refactoring
        refactoring_priorities = self._prioritize_refactoring(clone_groups)

        report = CloneDetectionReport(
            scan_path=directory,
            total_files=total_files,
            total_fragments=len(fragments),
            clone_groups=clone_groups,
            clone_type_distribution=clone_type_dist,
            severity_distribution=severity_dist,
            total_duplicated_lines=total_duplicated_lines,
            duplication_percentage=duplication_percentage,
            top_cloned_files=top_cloned_files,
            refactoring_priorities=refactoring_priorities,
        )

        logger.info(
            f"Clone detection complete: {len(clone_groups)} groups, "
            f"{duplication_percentage:.1f}% duplication"
        )

        return report

    def _get_python_files(self, directory: str) -> List[str]:
        """
        Get all Python files in directory, excluding specified patterns.

        Args:
            directory: Root directory to search

        Returns:
            Sorted list of Python file paths
        """
        python_files = []
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            # Check if in excluded directory
            should_exclude = False
            for exclude_dir in self.exclude_dirs:
                if exclude_dir in py_file.parts:
                    should_exclude = True
                    break

            if not should_exclude:
                python_files.append(str(py_file))

        return sorted(python_files)

    def _create_fragment_from_node(
        self, node: ast.AST, file_path: str, lines: List[str], fragment_type: str
    ) -> Optional[CodeFragment]:
        """
        Create a CodeFragment from an AST node.

        Args:
            node: AST node (FunctionDef, AsyncFunctionDef, or ClassDef)
            file_path: Path to source file
            lines: Source code lines
            fragment_type: Type of fragment (function or class)

        Returns:
            CodeFragment if fragment meets size threshold, None otherwise
        """
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", start_line)
        line_count = end_line - start_line + 1

        if line_count < self.min_fragment_lines:
            return None

        fragment_source = "\n".join(lines[start_line - 1 : end_line])
        return CodeFragment(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            source_code=fragment_source,
            ast_node=node,
            fragment_type=fragment_type,
            entity_name=node.name,
        )

    def _extract_fragments(self, file_path: str) -> List[CodeFragment]:
        """
        Extract code fragments (functions, classes) from a file.

        Args:
            file_path: Path to Python source file

        Returns:
            List of CodeFragment objects
        """
        try:
            return self._extract_fragments_from_file(file_path)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error extracting fragments from {file_path}: {e}")
            return []

    def _extract_fragments_from_file(self, file_path: str) -> List[CodeFragment]:
        """
        Parse file and extract code fragments.

        Args:
            file_path: Path to Python source file

        Returns:
            List of CodeFragment objects
        """
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        lines = source.split("\n")
        tree = ast.parse(source, filename=file_path)

        fragments: List[CodeFragment] = []
        for node in ast.walk(tree):
            fragment = self._maybe_create_fragment(node, file_path, lines)
            if fragment:
                fragments.append(fragment)
        return fragments

    def _maybe_create_fragment(
        self, node: ast.AST, file_path: str, lines: List[str]
    ) -> Optional[CodeFragment]:
        """
        Create a fragment from node if it's a function or class.

        Args:
            node: AST node to check
            file_path: Path to source file
            lines: Source code lines

        Returns:
            CodeFragment if node is function/class and meets threshold, None otherwise
        """
        if isinstance(node, _FUNCTION_DEF_TYPES):  # Issue #380
            return self._create_fragment_from_node(node, file_path, lines, "function")
        if isinstance(node, ast.ClassDef):
            return self._create_fragment_from_node(node, file_path, lines, "class")
        return None

    def _generate_fingerprints(self, fragment: CodeFragment) -> None:
        """
        Generate all types of fingerprints for a fragment.

        Args:
            fragment: CodeFragment to fingerprint
        """
        if fragment.ast_node is None:
            return

        # Structural fingerprint (Type 1)
        structural_hash = self.ast_hasher.hash_structural(fragment.ast_node)
        structural_features = self.ast_hasher.extract_features(fragment.ast_node)
        structural_fp = Fingerprint(
            hash_value=structural_hash,
            fingerprint_type=FingerprintType.AST_STRUCTURAL,
            fragment=fragment,
            structural_features=structural_features,
        )
        self._structural_fingerprints[structural_hash].append(structural_fp)

        # Normalized fingerprint (Type 2)
        normalized_hash = self.ast_hasher.hash_normalized(fragment.ast_node)
        normalized_fp = Fingerprint(
            hash_value=normalized_hash,
            fingerprint_type=FingerprintType.AST_NORMALIZED,
            fragment=fragment,
            structural_features=structural_features,
        )
        self._normalized_fingerprints[normalized_hash].append(normalized_fp)

        # Semantic fingerprint (Type 4)
        semantic_hash = self.semantic_hasher.hash_semantic(fragment.ast_node)
        semantic_fp = Fingerprint(
            hash_value=semantic_hash,
            fingerprint_type=FingerprintType.SEMANTIC,
            fragment=fragment,
            structural_features=structural_features,
        )
        self._semantic_fingerprints[semantic_hash].append(semantic_fp)

    def _detect_type1_clones(self) -> List[CloneGroup]:
        """
        Detect Type 1 (exact) clones.

        Returns:
            List of CloneGroup objects for Type 1 clones
        """
        clone_groups: List[CloneGroup] = []

        for hash_value, fingerprints in self._structural_fingerprints.items():
            if len(fingerprints) >= 2:
                instances = [
                    CloneInstance(
                        fragment=fp.fragment,
                        fingerprint=fp,
                        similarity_score=1.0,
                    )
                    for fp in fingerprints
                ]

                total_lines = sum(i.fragment.line_count for i in instances)
                severity = self._calculate_severity(len(instances), total_lines)

                group = CloneGroup(
                    clone_type=CloneType.TYPE_1,
                    severity=severity,
                    instances=instances,
                    canonical_fingerprint=hash_value,
                    similarity_range=(1.0, 1.0),
                    total_duplicated_lines=total_lines,
                )
                clone_groups.append(group)

        return clone_groups

    def _detect_type2_clones(
        self, type1_groups: List[CloneGroup]
    ) -> List[CloneGroup]:
        """
        Detect Type 2 (renamed) clones, excluding Type 1 clones.

        Args:
            type1_groups: Previously detected Type 1 clone groups

        Returns:
            List of CloneGroup objects for Type 2 clones
        """
        # Get all fragments already in Type 1 groups
        type1_fragments: Set[Tuple[str, int, int]] = set()
        for group in type1_groups:
            for instance in group.instances:
                type1_fragments.add(
                    (
                        instance.fragment.file_path,
                        instance.fragment.start_line,
                        instance.fragment.end_line,
                    )
                )

        clone_groups: List[CloneGroup] = []

        for hash_value, fingerprints in self._normalized_fingerprints.items():
            if len(fingerprints) >= 2:
                # Filter out fragments already in Type 1 groups
                valid_fps = [
                    fp
                    for fp in fingerprints
                    if (
                        fp.fragment.file_path,
                        fp.fragment.start_line,
                        fp.fragment.end_line,
                    )
                    not in type1_fragments
                ]

                # Check if this would be a duplicate of Type 1
                all_in_type1 = all(
                    (
                        fp.fragment.file_path,
                        fp.fragment.start_line,
                        fp.fragment.end_line,
                    )
                    in type1_fragments
                    for fp in fingerprints
                )

                if all_in_type1:
                    continue  # Skip, this is already captured as Type 1

                # Use valid_fps (excluding Type 1 clones) to avoid duplicates
                if len(valid_fps) >= 2:
                    instances = [
                        CloneInstance(
                            fragment=fp.fragment,
                            fingerprint=fp,
                            similarity_score=1.0,
                        )
                        for fp in valid_fps
                    ]

                    total_lines = sum(i.fragment.line_count for i in instances)
                    severity = self._calculate_severity(len(instances), total_lines)

                    group = CloneGroup(
                        clone_type=CloneType.TYPE_2,
                        severity=severity,
                        instances=instances,
                        canonical_fingerprint=hash_value,
                        similarity_range=(1.0, 1.0),
                        total_duplicated_lines=total_lines,
                    )
                    clone_groups.append(group)

        return clone_groups

    def _detect_type3_clones(
        self,
        fragments: List[CodeFragment],
        type1_groups: List[CloneGroup],
        type2_groups: List[CloneGroup],
    ) -> List[CloneGroup]:
        """
        Detect Type 3 (near-miss) clones using fuzzy matching.

        Args:
            fragments: All code fragments
            type1_groups: Previously detected Type 1 clone groups
            type2_groups: Previously detected Type 2 clone groups

        Returns:
            List of CloneGroup objects for Type 3 clones
        """
        # Get fragments already in Type 1 or Type 2 groups
        existing_fragments: Set[Tuple[str, int, int]] = set()
        for group in type1_groups + type2_groups:
            for instance in group.instances:
                existing_fragments.add(
                    (
                        instance.fragment.file_path,
                        instance.fragment.start_line,
                        instance.fragment.end_line,
                    )
                )

        # Filter fragments not already classified
        unclassified = [
            f
            for f in fragments
            if (f.file_path, f.start_line, f.end_line) not in existing_fragments
        ]

        clone_groups: List[CloneGroup] = []
        processed: Set[Tuple[str, int, int]] = set()

        for i, frag1 in enumerate(unclassified):
            if (frag1.file_path, frag1.start_line, frag1.end_line) in processed:
                continue

            similar_fragments: List[Tuple[CodeFragment, float]] = []

            for j, frag2 in enumerate(unclassified):
                if i >= j:
                    continue

                if (frag2.file_path, frag2.start_line, frag2.end_line) in processed:
                    continue

                # Calculate similarity
                similarity = self.similarity_calc.calculate_similarity(frag1, frag2)

                if similarity >= self.TYPE_3_SIMILARITY_THRESHOLD:
                    similar_fragments.append((frag2, similarity))

            if similar_fragments:
                # Create clone group
                instances = [
                    CloneInstance(
                        fragment=frag1,
                        fingerprint=Fingerprint(
                            hash_value="",
                            fingerprint_type=FingerprintType.AST_STRUCTURAL,
                            fragment=frag1,
                        ),
                        similarity_score=1.0,
                    )
                ]

                similarities = [1.0]
                for frag, sim in similar_fragments:
                    instances.append(
                        CloneInstance(
                            fragment=frag,
                            fingerprint=Fingerprint(
                                hash_value="",
                                fingerprint_type=FingerprintType.AST_STRUCTURAL,
                                fragment=frag,
                            ),
                            similarity_score=sim,
                        )
                    )
                    similarities.append(sim)
                    processed.add((frag.file_path, frag.start_line, frag.end_line))

                processed.add((frag1.file_path, frag1.start_line, frag1.end_line))

                total_lines = sum(i.fragment.line_count for i in instances)
                severity = self._calculate_severity(len(instances), total_lines)

                # Generate a hash for this group
                group_hash = hashlib.sha256(
                    f"{frag1.file_path}:{frag1.start_line}".encode()
                ).hexdigest()[:16]

                group = CloneGroup(
                    clone_type=CloneType.TYPE_3,
                    severity=severity,
                    instances=instances,
                    canonical_fingerprint=group_hash,
                    similarity_range=(min(similarities), max(similarities)),
                    total_duplicated_lines=total_lines,
                )
                clone_groups.append(group)

        return clone_groups

    def _detect_type4_clones(
        self,
        fragments: List[CodeFragment],
        type1_groups: List[CloneGroup],
        type2_groups: List[CloneGroup],
        type3_groups: List[CloneGroup],
    ) -> List[CloneGroup]:
        """
        Detect Type 4 (semantic) clones.

        Args:
            fragments: All code fragments
            type1_groups: Previously detected Type 1 clone groups
            type2_groups: Previously detected Type 2 clone groups
            type3_groups: Previously detected Type 3 clone groups

        Returns:
            List of CloneGroup objects for Type 4 clones
        """
        existing_fragments = self._collect_existing_fragments(
            type1_groups + type2_groups + type3_groups
        )

        clone_groups: List[CloneGroup] = []
        for hash_value, fingerprints in self._semantic_fingerprints.items():
            group = self._maybe_create_type4_group(
                hash_value, fingerprints, existing_fragments
            )
            if group:
                clone_groups.append(group)
        return clone_groups

    def _collect_existing_fragments(
        self, groups: List[CloneGroup]
    ) -> Set[Tuple[str, int, int]]:
        """
        Collect fragment identifiers from existing groups.

        Args:
            groups: List of clone groups

        Returns:
            Set of (file_path, start_line, end_line) tuples
        """
        existing: Set[Tuple[str, int, int]] = set()
        for group in groups:
            for instance in group.instances:
                existing.add((
                    instance.fragment.file_path,
                    instance.fragment.start_line,
                    instance.fragment.end_line,
                ))
        return existing

    def _maybe_create_type4_group(
        self,
        hash_value: str,
        fingerprints: List,
        existing_fragments: Set[Tuple[str, int, int]],
    ) -> Optional[CloneGroup]:
        """
        Create a Type 4 clone group if valid.

        Args:
            hash_value: Semantic hash value
            fingerprints: List of fingerprints with same semantic hash
            existing_fragments: Set of already classified fragments

        Returns:
            CloneGroup if valid Type 4 group, None otherwise
        """
        if len(fingerprints) < 2:
            return None
        if self._should_skip_type4_group(fingerprints, existing_fragments):
            return None

        instances = [
            CloneInstance(
                fragment=fp.fragment,
                fingerprint=fp,
                similarity_score=0.8,  # Semantic similarity placeholder
            )
            for fp in fingerprints
        ]
        total_lines = sum(i.fragment.line_count for i in instances)
        severity = self._calculate_severity(len(instances), total_lines)

        return CloneGroup(
            clone_type=CloneType.TYPE_4,
            severity=severity,
            instances=instances,
            canonical_fingerprint=hash_value,
            similarity_range=(0.6, 0.9),
            total_duplicated_lines=total_lines,
        )

    def _should_skip_type4_group(
        self, fingerprints: List, existing_fragments: Set[Tuple[str, int, int]]
    ) -> bool:
        """
        Check if this semantic group should be skipped.

        Args:
            fingerprints: List of fingerprints
            existing_fragments: Set of already classified fragments

        Returns:
            True if group should be skipped, False otherwise
        """
        # Check if all are from same structural group
        structural_hashes = {
            self.ast_hasher.hash_structural(fp.fragment.ast_node)
            for fp in fingerprints
            if fp.fragment.ast_node
        }
        if len(structural_hashes) == 1:
            return True  # Already caught by structural detection

        # Check if all fragments are already classified
        return all(
            (fp.fragment.file_path, fp.fragment.start_line, fp.fragment.end_line)
            in existing_fragments
            for fp in fingerprints
        )

    def _calculate_severity(self, instance_count: int, total_lines: int) -> CloneSeverity:
        """
        Calculate severity based on clone metrics.

        Args:
            instance_count: Number of clone instances
            total_lines: Total duplicated lines across all instances

        Returns:
            CloneSeverity level
        """
        if instance_count >= 7 or total_lines >= 200:
            return CloneSeverity.CRITICAL
        if instance_count >= 5 or total_lines >= 100:
            return CloneSeverity.HIGH
        if instance_count >= 3 or total_lines >= 50:
            return CloneSeverity.MEDIUM
        if instance_count >= 2:
            return CloneSeverity.LOW
        return CloneSeverity.INFO

    def _calculate_type_distribution(
        self, groups: List[CloneGroup]
    ) -> Dict[str, int]:
        """
        Calculate distribution of clone types.

        Args:
            groups: List of clone groups

        Returns:
            Dictionary mapping clone type to count
        """
        dist: Dict[str, int] = {}
        for group in groups:
            key = group.clone_type.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def _calculate_severity_distribution(
        self, groups: List[CloneGroup]
    ) -> Dict[str, int]:
        """
        Calculate distribution of severities.

        Args:
            groups: List of clone groups

        Returns:
            Dictionary mapping severity level to count
        """
        dist: Dict[str, int] = {}
        for group in groups:
            key = group.severity.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def _find_top_cloned_files(
        self, groups: List[CloneGroup], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find files with the most clones.

        Args:
            groups: List of clone groups
            top_n: Number of top files to return

        Returns:
            List of dictionaries with file statistics
        """
        file_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"clone_count": 0, "duplicated_lines": 0}
        )

        for group in groups:
            for instance in group.instances:
                file_path = instance.fragment.file_path
                file_stats[file_path]["clone_count"] += 1
                file_stats[file_path]["duplicated_lines"] += instance.fragment.line_count

        # Sort by clone count
        sorted_files = sorted(
            file_stats.items(),
            key=lambda x: (x[1]["clone_count"], x[1]["duplicated_lines"]),
            reverse=True,
        )[:top_n]

        return [
            {
                "file_path": path,
                "clone_count": stats["clone_count"],
                "duplicated_lines": stats["duplicated_lines"],
            }
            for path, stats in sorted_files
        ]

    def _prioritize_refactoring(
        self, groups: List[CloneGroup], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Prioritize clone groups for refactoring.

        Args:
            groups: List of clone groups
            top_n: Number of top priorities to return

        Returns:
            List of dictionaries with refactoring priorities
        """
        # Score based on severity, instance count, and total lines
        scored_groups = []
        for group in groups:
            severity_scores = {
                CloneSeverity.CRITICAL: 100,
                CloneSeverity.HIGH: 75,
                CloneSeverity.MEDIUM: 50,
                CloneSeverity.LOW: 25,
                CloneSeverity.INFO: 10,
            }
            score = (
                severity_scores[group.severity]
                + len(group.instances) * 10
                + group.total_duplicated_lines
            )
            scored_groups.append((group, score))

        # Sort by score (descending)
        sorted_groups = sorted(scored_groups, key=lambda x: x[1], reverse=True)[:top_n]

        return [
            {
                "clone_type": group.clone_type.value,
                "severity": group.severity.value,
                "instance_count": len(group.instances),
                "total_duplicated_lines": group.total_duplicated_lines,
                "priority_score": score,
                "refactoring_suggestion": group.refactoring_suggestion,
                "estimated_effort": group.estimated_effort,
                "files_affected": list(
                    set(i.fragment.file_path for i in group.instances)
                ),
            }
            for group, score in sorted_groups
        ]

    # Suggestion templates for each clone type
    _REFACTORING_TEMPLATES = {
        CloneType.TYPE_1: (
            "Extract duplicated {fragment_type} into a shared utility function "
            "or module. All {count} copies are identical and can be "
            "replaced with a single implementation."
        ),
        CloneType.TYPE_2: (
            "The {count} {fragment_type} copies differ only in variable "
            "names. Create a parameterized function or use generics to eliminate "
            "duplication while preserving the different naming contexts."
        ),
        CloneType.TYPE_3: (
            "These {count} similar {fragment_type}s share significant "
            "logic. Consider extracting common parts into a base function, "
            "then use composition or inheritance for variations."
        ),
        CloneType.TYPE_4: (
            "These {count} {fragment_type}s achieve the same result "
            "differently. Evaluate which implementation is best and consolidate, "
            "or document why different approaches are needed."
        ),
    }

    def _generate_refactoring_suggestion(self, group: CloneGroup) -> str:
        """
        Generate a refactoring suggestion for a clone group.

        Args:
            group: CloneGroup to generate suggestion for

        Returns:
            Human-readable refactoring suggestion
        """
        template = self._REFACTORING_TEMPLATES.get(group.clone_type)
        if not template:
            return "Review and consider consolidating duplicated code."

        fragment_type = (
            group.instances[0].fragment.fragment_type if group.instances else "code"
        )
        return template.format(count=len(group.instances), fragment_type=fragment_type)

    def _estimate_refactoring_effort(self, group: CloneGroup) -> str:
        """
        Estimate the effort required to refactor a clone group.

        Args:
            group: CloneGroup to estimate effort for

        Returns:
            Effort estimation string
        """
        total_lines = group.total_duplicated_lines
        instance_count = len(group.instances)
        files_affected = len(set(i.fragment.file_path for i in group.instances))

        # Simple effort estimation based on metrics
        if total_lines < 50 and files_affected <= 2:
            effort = "Low (< 1 hour)"
        elif total_lines < 150 and files_affected <= 5:
            effort = "Medium (1-4 hours)"
        elif total_lines < 300 or files_affected <= 10:
            effort = "High (4-8 hours)"
        else:
            effort = "Very High (> 8 hours)"

        return f"{effort} - {instance_count} instances across {files_affected} files"


# =============================================================================
# Convenience Functions
# =============================================================================


def detect_clones(
    directory: str,
    min_fragment_lines: int = 5,
    exclude_dirs: Optional[List[str]] = None,
) -> CloneDetectionReport:
    """
    Detect code clones in a directory.

    Args:
        directory: Path to the directory to analyze
        min_fragment_lines: Minimum lines for fragments
        exclude_dirs: Directories to exclude

    Returns:
        CloneDetectionReport with all findings
    """
    detector = CloneDetector(
        min_fragment_lines=min_fragment_lines,
        exclude_dirs=exclude_dirs,
    )
    return detector.detect_clones(directory)


def get_clone_types() -> List[Dict[str, str]]:
    """Get available clone types with descriptions."""
    return [
        {
            "type": CloneType.TYPE_1.value,
            "name": "Exact Clones",
            "description": "Identical code fragments (ignoring whitespace/comments)",
        },
        {
            "type": CloneType.TYPE_2.value,
            "name": "Renamed Clones",
            "description": "Identical structure with renamed variables/functions",
        },
        {
            "type": CloneType.TYPE_3.value,
            "name": "Near-miss Clones",
            "description": "Similar code with some statements added/removed/modified",
        },
        {
            "type": CloneType.TYPE_4.value,
            "name": "Semantic Clones",
            "description": "Functionally equivalent but structurally different",
        },
    ]


def get_clone_severities() -> List[Dict[str, str]]:
    """Get available severity levels."""
    return [
        {"severity": CloneSeverity.INFO.value, "description": "Informational only"},
        {"severity": CloneSeverity.LOW.value, "description": "Minor duplication (2-3 instances)"},
        {"severity": CloneSeverity.MEDIUM.value, "description": "Should be refactored (4-6 instances)"},
        {"severity": CloneSeverity.HIGH.value, "description": "Significant debt (7+ instances)"},
        {"severity": CloneSeverity.CRITICAL.value, "description": "Urgent refactoring needed"},
    ]


def get_fingerprint_types() -> List[Dict[str, str]]:
    """Get available fingerprint types."""
    return [
        {
            "type": FingerprintType.AST_STRUCTURAL.value,
            "description": "Based on full AST structure",
        },
        {
            "type": FingerprintType.AST_NORMALIZED.value,
            "description": "Normalized identifiers for Type 2 detection",
        },
        {
            "type": FingerprintType.SEMANTIC.value,
            "description": "Based on data/control flow patterns",
        },
        {
            "type": FingerprintType.TOKEN_SEQUENCE.value,
            "description": "Based on token sequences",
        },
    ]
