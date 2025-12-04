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
        return hash((self.file_path, self.start_line, self.end_line))

    def __eq__(self, other: object) -> bool:
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
        """Get a preview of the source code."""
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
        """Get or create a placeholder for an identifier."""
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
        """Normalize variable names."""
        new_name = self._get_placeholder(node.id, "VAR")
        return ast.Name(id=new_name, ctx=node.ctx)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Normalize function names (but preserve structure)."""
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
        """Normalize async function names."""
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
        """Normalize function arguments."""
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
        """Normalize constants (but preserve type information)."""
        # Keep type but normalize value for string/number comparisons
        if isinstance(node.value, str):
            return ast.Constant(value="$STRING$")
        elif isinstance(node.value, (int, float)):
            return ast.Constant(value=0)  # Normalize numbers
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        """Normalize argument names."""
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
        """Hash an AST node with optional normalization."""
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
        """Convert AST node to a hashable structure tuple."""
        if node is None:
            return ("None",)

        node_type = type(node).__name__

        # Handle different node types
        if isinstance(node, ast.Constant):
            return (node_type, type(node.value).__name__)
        elif isinstance(node, ast.Name):
            return (node_type, node.id, type(node.ctx).__name__)
        elif isinstance(node, ast.FunctionDef):
            args_tuple = self._args_to_structure(node.args)
            body_tuple = tuple(self._node_to_structure(n) for n in node.body)
            return (node_type, node.name, args_tuple, body_tuple)
        elif isinstance(node, ast.AsyncFunctionDef):
            args_tuple = self._args_to_structure(node.args)
            body_tuple = tuple(self._node_to_structure(n) for n in node.body)
            return ("AsyncFunctionDef", node.name, args_tuple, body_tuple)
        elif isinstance(node, ast.ClassDef):
            body_tuple = tuple(self._node_to_structure(n) for n in node.body)
            bases_tuple = tuple(self._node_to_structure(b) for b in node.bases)
            return (node_type, node.name, bases_tuple, body_tuple)
        elif isinstance(node, ast.BinOp):
            left = self._node_to_structure(node.left)
            right = self._node_to_structure(node.right)
            op = type(node.op).__name__
            return (node_type, op, left, right)
        elif isinstance(node, ast.Compare):
            left = self._node_to_structure(node.left)
            ops = tuple(type(op).__name__ for op in node.ops)
            comparators = tuple(
                self._node_to_structure(c) for c in node.comparators
            )
            return (node_type, left, ops, comparators)
        elif isinstance(node, ast.Call):
            func = self._node_to_structure(node.func)
            args = tuple(self._node_to_structure(a) for a in node.args)
            return (node_type, func, args)
        elif isinstance(node, ast.Attribute):
            value = self._node_to_structure(node.value)
            return (node_type, value, node.attr)
        elif isinstance(node, ast.If):
            test = self._node_to_structure(node.test)
            body = tuple(self._node_to_structure(n) for n in node.body)
            orelse = tuple(self._node_to_structure(n) for n in node.orelse)
            return (node_type, test, body, orelse)
        elif isinstance(node, ast.For):
            target = self._node_to_structure(node.target)
            iter_node = self._node_to_structure(node.iter)
            body = tuple(self._node_to_structure(n) for n in node.body)
            return (node_type, target, iter_node, body)
        elif isinstance(node, ast.While):
            test = self._node_to_structure(node.test)
            body = tuple(self._node_to_structure(n) for n in node.body)
            return (node_type, test, body)
        elif isinstance(node, ast.Return):
            value = (
                self._node_to_structure(node.value)
                if node.value
                else ("None",)
            )
            return (node_type, value)
        elif isinstance(node, ast.Assign):
            targets = tuple(self._node_to_structure(t) for t in node.targets)
            value = self._node_to_structure(node.value)
            return (node_type, targets, value)
        elif isinstance(node, ast.AugAssign):
            target = self._node_to_structure(node.target)
            op = type(node.op).__name__
            value = self._node_to_structure(node.value)
            return (node_type, target, op, value)
        elif isinstance(node, ast.Expr):
            value = self._node_to_structure(node.value)
            return (node_type, value)
        elif isinstance(node, ast.Try):
            body = tuple(self._node_to_structure(n) for n in node.body)
            handlers = tuple(self._node_to_structure(h) for h in node.handlers)
            orelse = tuple(self._node_to_structure(n) for n in node.orelse)
            finalbody = tuple(self._node_to_structure(n) for n in node.finalbody)
            return (node_type, body, handlers, orelse, finalbody)
        elif isinstance(node, ast.ExceptHandler):
            handler_type = (
                self._node_to_structure(node.type) if node.type else ("None",)
            )
            body = tuple(self._node_to_structure(n) for n in node.body)
            return (node_type, handler_type, node.name, body)
        elif isinstance(node, ast.With):
            items = tuple(self._node_to_structure(i) for i in node.items)
            body = tuple(self._node_to_structure(n) for n in node.body)
            return (node_type, items, body)
        elif isinstance(node, ast.withitem):
            context = self._node_to_structure(node.context_expr)
            optional_vars = (
                self._node_to_structure(node.optional_vars)
                if node.optional_vars
                else ("None",)
            )
            return ("withitem", context, optional_vars)
        elif isinstance(node, ast.List):
            elts = tuple(self._node_to_structure(e) for e in node.elts)
            return (node_type, elts)
        elif isinstance(node, ast.Dict):
            keys = tuple(
                self._node_to_structure(k) if k else ("None",) for k in node.keys
            )
            values = tuple(self._node_to_structure(v) for v in node.values)
            return (node_type, keys, values)
        elif isinstance(node, ast.Tuple):
            elts = tuple(self._node_to_structure(e) for e in node.elts)
            return (node_type, elts)
        elif isinstance(node, ast.Set):
            elts = tuple(self._node_to_structure(e) for e in node.elts)
            return (node_type, elts)
        elif isinstance(node, ast.ListComp):
            elt = self._node_to_structure(node.elt)
            generators = tuple(
                self._node_to_structure(g) for g in node.generators
            )
            return (node_type, elt, generators)
        elif isinstance(node, ast.comprehension):
            target = self._node_to_structure(node.target)
            iter_node = self._node_to_structure(node.iter)
            ifs = tuple(self._node_to_structure(i) for i in node.ifs)
            return ("comprehension", target, iter_node, ifs, node.is_async)
        elif isinstance(node, ast.Lambda):
            args = self._args_to_structure(node.args)
            body = self._node_to_structure(node.body)
            return (node_type, args, body)
        elif isinstance(node, ast.UnaryOp):
            op = type(node.op).__name__
            operand = self._node_to_structure(node.operand)
            return (node_type, op, operand)
        elif isinstance(node, ast.BoolOp):
            op = type(node.op).__name__
            values = tuple(self._node_to_structure(v) for v in node.values)
            return (node_type, op, values)
        elif isinstance(node, ast.IfExp):
            test = self._node_to_structure(node.test)
            body = self._node_to_structure(node.body)
            orelse = self._node_to_structure(node.orelse)
            return (node_type, test, body, orelse)
        elif isinstance(node, ast.Subscript):
            value = self._node_to_structure(node.value)
            slice_node = self._node_to_structure(node.slice)
            return (node_type, value, slice_node)
        elif isinstance(node, ast.Slice):
            lower = (
                self._node_to_structure(node.lower)
                if node.lower
                else ("None",)
            )
            upper = (
                self._node_to_structure(node.upper)
                if node.upper
                else ("None",)
            )
            step = (
                self._node_to_structure(node.step)
                if node.step
                else ("None",)
            )
            return (node_type, lower, upper, step)
        elif isinstance(node, ast.Raise):
            exc = (
                self._node_to_structure(node.exc)
                if node.exc
                else ("None",)
            )
            cause = (
                self._node_to_structure(node.cause)
                if node.cause
                else ("None",)
            )
            return (node_type, exc, cause)
        elif isinstance(node, ast.Assert):
            test = self._node_to_structure(node.test)
            msg = (
                self._node_to_structure(node.msg)
                if node.msg
                else ("None",)
            )
            return (node_type, test, msg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = tuple((alias.name, alias.asname) for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                return (node_type, node.module, names)
            return (node_type, names)
        elif isinstance(node, ast.Pass):
            return (node_type,)
        elif isinstance(node, ast.Break):
            return (node_type,)
        elif isinstance(node, ast.Continue):
            return (node_type,)
        elif isinstance(node, ast.Global):
            return (node_type, tuple(node.names))
        elif isinstance(node, ast.Nonlocal):
            return (node_type, tuple(node.names))
        elif isinstance(node, ast.Await):
            value = self._node_to_structure(node.value)
            return (node_type, value)
        elif isinstance(node, ast.Yield):
            value = (
                self._node_to_structure(node.value)
                if node.value
                else ("None",)
            )
            return (node_type, value)
        elif isinstance(node, ast.YieldFrom):
            value = self._node_to_structure(node.value)
            return (node_type, value)
        elif isinstance(node, ast.FormattedValue):
            value = self._node_to_structure(node.value)
            return (node_type, value, node.conversion)
        elif isinstance(node, ast.JoinedStr):
            values = tuple(self._node_to_structure(v) for v in node.values)
            return (node_type, values)
        elif isinstance(node, ast.Starred):
            value = self._node_to_structure(node.value)
            return (node_type, value)
        elif isinstance(node, ast.NamedExpr):
            target = self._node_to_structure(node.target)
            value = self._node_to_structure(node.value)
            return (node_type, target, value)
        else:
            # Fallback for any other node types
            children = []
            for child in ast.iter_child_nodes(node):
                children.append(self._node_to_structure(child))
            return (node_type, tuple(children))

    def _args_to_structure(self, args: ast.arguments) -> Tuple:
        """Convert arguments to a hashable structure."""
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
        """Recursively count features in an AST node."""
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
        """Extract semantic features from an AST node."""
        return {
            "input_variables": self._find_inputs(node),
            "output_variables": self._find_outputs(node),
            "control_flow_pattern": self._extract_control_flow(node),
            "operation_sequence": self._extract_operations(node),
            "call_graph": self._extract_calls(node),
        }

    def _find_inputs(self, node: ast.AST) -> List[str]:
        """Find variables that are read but not defined in the node."""
        defined: Set[str] = set()
        used: Set[str] = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                if isinstance(child.ctx, ast.Store):
                    defined.add(child.id)
                elif isinstance(child.ctx, ast.Load):
                    used.add(child.id)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in child.args.args:
                    defined.add(arg.arg)

        inputs = used - defined
        # Remove built-in names
        builtins_to_remove = {
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
            "True",
            "False",
            "None",
        }
        inputs -= builtins_to_remove
        return sorted(inputs)

    def _find_outputs(self, node: ast.AST) -> List[str]:
        """Find variables that are defined/modified in the node."""
        outputs: Set[str] = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                outputs.add(child.id)
            elif isinstance(child, ast.Return) and child.value:
                outputs.add("$RETURN$")

        return sorted(outputs)

    def _extract_control_flow(self, node: ast.AST) -> List[str]:
        """Extract control flow pattern as a sequence of control structures."""
        pattern: List[str] = []

        for child in ast.walk(node):
            if isinstance(child, ast.If):
                pattern.append("IF")
            elif isinstance(child, ast.For):
                pattern.append("FOR")
            elif isinstance(child, ast.While):
                pattern.append("WHILE")
            elif isinstance(child, ast.Try):
                pattern.append("TRY")
            elif isinstance(child, ast.With):
                pattern.append("WITH")
            elif isinstance(child, ast.Return):
                pattern.append("RETURN")
            elif isinstance(child, ast.Raise):
                pattern.append("RAISE")
            elif isinstance(child, ast.Break):
                pattern.append("BREAK")
            elif isinstance(child, ast.Continue):
                pattern.append("CONTINUE")

        return pattern

    def _extract_operations(self, node: ast.AST) -> List[str]:
        """Extract sequence of operations/operators used."""
        operations: List[str] = []

        for child in ast.walk(node):
            if isinstance(child, ast.BinOp):
                operations.append(f"BINOP:{type(child.op).__name__}")
            elif isinstance(child, ast.UnaryOp):
                operations.append(f"UNARYOP:{type(child.op).__name__}")
            elif isinstance(child, ast.Compare):
                for op in child.ops:
                    operations.append(f"COMPARE:{type(op).__name__}")
            elif isinstance(child, ast.BoolOp):
                operations.append(f"BOOLOP:{type(child.op).__name__}")
            elif isinstance(child, ast.AugAssign):
                operations.append(f"AUGASSIGN:{type(child.op).__name__}")

        return operations

    def _extract_calls(self, node: ast.AST) -> List[str]:
        """Extract function calls made within the node."""
        calls: List[str] = []

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(f"*.{child.func.attr}")

        return calls


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
        """Calculate similarity based on AST structure."""
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
        """Calculate similarity based on token sequences."""
        tokens1 = self._tokenize(code1)
        tokens2 = self._tokenize(code2)

        if not tokens1 or not tokens2:
            return 0.0

        # Use longest common subsequence ratio
        lcs_length = self._lcs_length(tokens1, tokens2)
        max_length = max(len(tokens1), len(tokens2))

        return lcs_length / max_length if max_length > 0 else 0.0

    def _feature_similarity(self, node1: ast.AST, node2: ast.AST) -> float:
        """Calculate similarity based on extracted features."""
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
        """Calculate text-based similarity as fallback."""
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
        """Tokenize code into meaningful tokens."""
        # Simple tokenization - split on whitespace and punctuation
        tokens = re.findall(r"[a-zA-Z_]\w*|\d+|[^\s\w]", code)
        return tokens

    def _jaccard_similarity(self, set1: Set, set2: Set) -> float:
        """Calculate Jaccard similarity between two sets."""
        if not set1 and not set2:
            return 1.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _lcs_length(self, seq1: List, seq2: List) -> int:
        """Calculate length of longest common subsequence."""
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
        """Get all Python files in directory, excluding specified patterns."""
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
        """Create a CodeFragment from an AST node (Issue #335 - extracted helper)."""
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
        """Extract code fragments (functions, classes) from a file."""
        fragments: List[CodeFragment] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
                lines = source.split("\n")

            tree = ast.parse(source, filename=file_path)

            for node in ast.walk(tree):
                # Extract functions
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fragment = self._create_fragment_from_node(
                        node, file_path, lines, "function"
                    )
                    if fragment:
                        fragments.append(fragment)

                # Extract classes
                elif isinstance(node, ast.ClassDef):
                    fragment = self._create_fragment_from_node(
                        node, file_path, lines, "class"
                    )
                    if fragment:
                        fragments.append(fragment)

        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error extracting fragments from {file_path}: {e}")

        return fragments

    def _generate_fingerprints(self, fragment: CodeFragment) -> None:
        """Generate all types of fingerprints for a fragment."""
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
        """Detect Type 1 (exact) clones."""
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
        """Detect Type 2 (renamed) clones, excluding Type 1 clones."""
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
        """Detect Type 3 (near-miss) clones using fuzzy matching."""
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
        """Detect Type 4 (semantic) clones."""
        # Get fragments already classified
        existing_fragments: Set[Tuple[str, int, int]] = set()
        for group in type1_groups + type2_groups + type3_groups:
            for instance in group.instances:
                existing_fragments.add(
                    (
                        instance.fragment.file_path,
                        instance.fragment.start_line,
                        instance.fragment.end_line,
                    )
                )

        clone_groups: List[CloneGroup] = []

        for hash_value, fingerprints in self._semantic_fingerprints.items():
            if len(fingerprints) >= 2:
                # Check if all are from same structural group
                structural_hashes = set()
                for fp in fingerprints:
                    if fp.fragment.ast_node:
                        structural_hashes.add(
                            self.ast_hasher.hash_structural(fp.fragment.ast_node)
                        )

                # Skip if they're all structurally identical (already caught)
                if len(structural_hashes) == 1:
                    continue

                # Check if all fragments are already classified
                all_classified = all(
                    (
                        fp.fragment.file_path,
                        fp.fragment.start_line,
                        fp.fragment.end_line,
                    )
                    in existing_fragments
                    for fp in fingerprints
                )

                if all_classified:
                    continue

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

                group = CloneGroup(
                    clone_type=CloneType.TYPE_4,
                    severity=severity,
                    instances=instances,
                    canonical_fingerprint=hash_value,
                    similarity_range=(0.6, 0.9),
                    total_duplicated_lines=total_lines,
                )
                clone_groups.append(group)

        return clone_groups

    def _calculate_severity(self, instance_count: int, total_lines: int) -> CloneSeverity:
        """Calculate severity based on clone metrics."""
        # Consider both instance count and total duplicated lines
        if instance_count >= 7 or total_lines >= 200:
            return CloneSeverity.CRITICAL
        elif instance_count >= 5 or total_lines >= 100:
            return CloneSeverity.HIGH
        elif instance_count >= 3 or total_lines >= 50:
            return CloneSeverity.MEDIUM
        elif instance_count >= 2:
            return CloneSeverity.LOW
        return CloneSeverity.INFO

    def _calculate_type_distribution(
        self, groups: List[CloneGroup]
    ) -> Dict[str, int]:
        """Calculate distribution of clone types."""
        dist: Dict[str, int] = {}
        for group in groups:
            key = group.clone_type.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def _calculate_severity_distribution(
        self, groups: List[CloneGroup]
    ) -> Dict[str, int]:
        """Calculate distribution of severities."""
        dist: Dict[str, int] = {}
        for group in groups:
            key = group.severity.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def _find_top_cloned_files(
        self, groups: List[CloneGroup], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """Find files with the most clones."""
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
        """Prioritize clone groups for refactoring."""
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

    def _generate_refactoring_suggestion(self, group: CloneGroup) -> str:
        """Generate a refactoring suggestion for a clone group."""
        clone_type = group.clone_type
        instance_count = len(group.instances)
        fragment_type = group.instances[0].fragment.fragment_type if group.instances else "code"

        if clone_type == CloneType.TYPE_1:
            return (
                f"Extract duplicated {fragment_type} into a shared utility function "
                f"or module. All {instance_count} copies are identical and can be "
                f"replaced with a single implementation."
            )
        elif clone_type == CloneType.TYPE_2:
            return (
                f"The {instance_count} {fragment_type} copies differ only in variable "
                f"names. Create a parameterized function or use generics to eliminate "
                f"duplication while preserving the different naming contexts."
            )
        elif clone_type == CloneType.TYPE_3:
            return (
                f"These {instance_count} similar {fragment_type}s share significant "
                f"logic. Consider extracting common parts into a base function, "
                f"then use composition or inheritance for variations."
            )
        elif clone_type == CloneType.TYPE_4:
            return (
                f"These {instance_count} {fragment_type}s achieve the same result "
                f"differently. Evaluate which implementation is best and consolidate, "
                f"or document why different approaches are needed."
            )

        return "Review and consider consolidating duplicated code."

    def _estimate_refactoring_effort(self, group: CloneGroup) -> str:
        """Estimate the effort required to refactor a clone group."""
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
