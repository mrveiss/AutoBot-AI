# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Control Flow Graph Analyzer API (Issue #233)

Analyzes control flow to detect:
- Unreachable code
- Infinite loops
- Complex conditionals
- Path complexity (cyclomatic complexity)

Provides CFG construction, visualization exports, and comprehensive analysis.
"""

import ast
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cfg", tags=["control-flow", "analytics"])

# Issue #380: Module-level tuples for AST type checking
_EXIT_STMT_TYPES = (ast.Return, ast.Raise)
_BREAK_CONTINUE_TYPES = (ast.Break, ast.Continue)
_CONDITION_TYPES = (ast.Compare, ast.BoolOp)


# ============================================================================
# Enums and Constants
# ============================================================================


class NodeType(str, Enum):
    """Types of CFG nodes."""

    ENTRY = "entry"
    EXIT = "exit"
    STATEMENT = "statement"
    CONDITION = "condition"
    LOOP_HEADER = "loop_header"
    LOOP_BODY = "loop_body"
    TRY_BLOCK = "try_block"
    EXCEPT_HANDLER = "except_handler"
    FINALLY_BLOCK = "finally_block"
    FUNCTION_DEF = "function_def"
    CLASS_DEF = "class_def"
    RETURN = "return"
    RAISE = "raise"
    BREAK = "break"
    CONTINUE = "continue"
    PASS = "pass"


class EdgeType(str, Enum):
    """Types of CFG edges."""

    SEQUENTIAL = "sequential"
    TRUE_BRANCH = "true_branch"
    FALSE_BRANCH = "false_branch"
    LOOP_BACK = "loop_back"
    BREAK_OUT = "break_out"
    CONTINUE_BACK = "continue_back"
    EXCEPTION = "exception"
    FINALLY = "finally"
    RETURN_EDGE = "return_edge"


class IssueSeverity(str, Enum):
    """Severity levels for detected issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueType(str, Enum):
    """Types of control flow issues."""

    UNREACHABLE_CODE = "unreachable_code"
    INFINITE_LOOP = "infinite_loop"
    POTENTIAL_INFINITE_LOOP = "potential_infinite_loop"
    DEAD_BRANCH = "dead_branch"
    COMPLEX_CONDITION = "complex_condition"
    HIGH_CYCLOMATIC_COMPLEXITY = "high_cyclomatic_complexity"
    DEEP_NESTING = "deep_nesting"
    MISSING_RETURN = "missing_return"
    EMPTY_EXCEPT = "empty_except"
    BARE_EXCEPT = "bare_except"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class CFGNode:
    """A node in the Control Flow Graph."""

    id: str
    node_type: NodeType
    line_start: int
    line_end: int
    code_snippet: str = ""
    ast_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_snippet": self.code_snippet[:100] if self.code_snippet else "",
            "ast_type": self.ast_type,
            "metadata": self.metadata,
        }


@dataclass
class CFGEdge:
    """An edge in the Control Flow Graph."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    condition: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source_id,
            "target": self.target_id,
            "edge_type": self.edge_type.value,
            "condition": self.condition,
            "metadata": self.metadata,
        }


@dataclass
class CFGIssue:
    """A detected control flow issue."""

    issue_type: IssueType
    severity: IssueSeverity
    line_start: int
    line_end: int
    message: str
    suggestion: str
    code_snippet: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "message": self.message,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet[:200] if self.code_snippet else "",
            "metadata": self.metadata,
        }


@dataclass
class ControlFlowGraph:
    """Complete Control Flow Graph representation."""

    function_name: str
    file_path: str
    nodes: List[CFGNode] = field(default_factory=list)
    edges: List[CFGEdge] = field(default_factory=list)
    entry_node_id: Optional[str] = None
    exit_node_ids: List[str] = field(default_factory=list)
    issues: List[CFGIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "function_name": self.function_name,
            "file_path": self.file_path,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "entry_node_id": self.entry_node_id,
            "exit_node_ids": self.exit_node_ids,
            "issues": [i.to_dict() for i in self.issues],
            "metrics": self.metrics,
        }


# ============================================================================
# CFG Builder
# ============================================================================


class CFGBuilder(ast.NodeVisitor):
    """Builds Control Flow Graphs from Python AST."""

    def __init__(self, source_code: str, file_path: str = ""):
        """Initialize CFG builder with source code and file context."""
        self.source_code = source_code
        self.source_lines = source_code.split("\n")
        self.file_path = file_path
        self.graphs: List[ControlFlowGraph] = []
        self._current_graph: Optional[ControlFlowGraph] = None
        self._node_counter = 0
        self._current_node_id: Optional[str] = None
        self._loop_stack: List[Tuple[str, str]] = []  # (header_id, exit_id)
        self._try_stack: List[str] = []

    def _generate_node_id(self) -> str:
        """Generate a unique node ID."""
        self._node_counter += 1
        return f"node_{self._node_counter}"

    def _get_source_segment(self, node: ast.AST) -> str:
        """Extract source code for an AST node."""
        try:
            start_line = node.lineno - 1
            end_line = getattr(node, "end_lineno", node.lineno)
            if start_line < len(self.source_lines) and end_line <= len(self.source_lines):
                return "\n".join(self.source_lines[start_line:end_line])
        except Exception as e:
            logger.debug("Failed to extract code snippet from AST node: %s", e)
        return ""

    def _add_node(
        self,
        node_type: NodeType,
        ast_node: ast.AST,
        code_snippet: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CFGNode:
        """Add a node to the current graph."""
        node_id = self._generate_node_id()
        line_start = getattr(ast_node, "lineno", 0)
        line_end = getattr(ast_node, "end_lineno", line_start)

        if not code_snippet:
            code_snippet = self._get_source_segment(ast_node)

        cfg_node = CFGNode(
            id=node_id,
            node_type=node_type,
            line_start=line_start,
            line_end=line_end,
            code_snippet=code_snippet,
            ast_type=type(ast_node).__name__,
            metadata=metadata or {},
        )

        if self._current_graph:
            self._current_graph.nodes.append(cfg_node)

        return cfg_node

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        condition: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CFGEdge:
        """Add an edge to the current graph."""
        edge = CFGEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            condition=condition,
            metadata=metadata or {},
        )

        if self._current_graph:
            self._current_graph.edges.append(edge)

        return edge

    def build(self) -> List[ControlFlowGraph]:
        """Build CFGs for all functions in the source code."""
        try:
            tree = ast.parse(self.source_code)
            self.visit(tree)
        except SyntaxError as e:
            logger.error("Syntax error parsing source: %s", e)

        return self.graphs

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Build CFG for a function definition."""
        self._build_function_cfg(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Build CFG for an async function definition."""
        self._build_function_cfg(node, is_async=True)

    def _build_function_cfg(
        self, node: ast.FunctionDef, is_async: bool = False
    ) -> None:
        """Build CFG for a function."""
        # Create new graph
        self._current_graph = ControlFlowGraph(
            function_name=node.name,
            file_path=self.file_path,
        )
        self._node_counter = 0
        self._loop_stack = []
        self._try_stack = []

        # Create entry node
        entry_node = self._add_node(
            NodeType.ENTRY,
            node,
            f"def {node.name}(...)",
            {"is_async": is_async, "args": [arg.arg for arg in node.args.args]},
        )
        self._current_graph.entry_node_id = entry_node.id
        self._current_node_id = entry_node.id

        # Process function body
        exit_nodes = self._process_block(node.body)

        # Create exit node if needed
        exit_node = self._add_node(NodeType.EXIT, node, "# function exit")
        self._current_graph.exit_node_ids.append(exit_node.id)

        # Connect dangling exit nodes
        for exit_id in exit_nodes:
            self._add_edge(exit_id, exit_node.id, EdgeType.SEQUENTIAL)

        # Calculate metrics
        self._calculate_metrics()

        # Detect issues
        self._detect_issues(node)

        self.graphs.append(self._current_graph)
        self._current_graph = None

    def _process_block(self, stmts: List[ast.stmt]) -> List[str]:
        """Process a block of statements, return exit node IDs."""
        if not stmts:
            return [self._current_node_id] if self._current_node_id else []

        exit_nodes: List[str] = []
        unreachable_start = None

        for i, stmt in enumerate(stmts):
            # Check for unreachable code
            if unreachable_start is not None:
                # Mark remaining statements as unreachable
                issue = CFGIssue(
                    issue_type=IssueType.UNREACHABLE_CODE,
                    severity=IssueSeverity.MEDIUM,
                    line_start=stmt.lineno,
                    line_end=getattr(stmt, "end_lineno", stmt.lineno),
                    message="Unreachable code detected after control flow statement",
                    suggestion="Remove unreachable code or restructure logic",
                    code_snippet=self._get_source_segment(stmt),
                )
                if self._current_graph:
                    self._current_graph.issues.append(issue)
                continue

            # Process statement
            stmt_exits = self._process_statement(stmt)

            # Check if this terminates control flow
            if isinstance(stmt, _EXIT_STMT_TYPES):  # Issue #380
                unreachable_start = stmt.lineno
                exit_nodes.extend(stmt_exits)
            elif isinstance(stmt, _BREAK_CONTINUE_TYPES):  # Issue #380
                unreachable_start = stmt.lineno
                # Don't add to exit_nodes - these are handled specially
            else:
                # Update current node for next iteration
                if stmt_exits:
                    self._current_node_id = stmt_exits[-1]

        if unreachable_start is None and self._current_node_id:
            exit_nodes.append(self._current_node_id)

        return exit_nodes

    def _process_simple_statement(self, stmt: ast.stmt) -> List[str]:
        """Process a simple (non-control-flow) statement (Issue #315)."""
        node = self._add_node(NodeType.STATEMENT, stmt)
        if self._current_node_id:
            self._add_edge(self._current_node_id, node.id, EdgeType.SEQUENTIAL)
        self._current_node_id = node.id
        return [node.id]

    def _process_nested_function(self, stmt: ast.stmt) -> List[str]:
        """Process a nested function definition (Issue #315)."""
        self._build_function_cfg(stmt, isinstance(stmt, ast.AsyncFunctionDef))
        return [self._current_node_id] if self._current_node_id else []

    def _process_statement(self, stmt: ast.stmt) -> List[str]:
        """Process a single statement, return exit node IDs (Issue #315 - dispatch table)."""
        # Statement type to handler dispatch table
        stmt_handlers = {
            ast.If: self._process_if,
            ast.For: self._process_for,
            ast.AsyncFor: self._process_for,
            ast.While: self._process_while,
            ast.Try: self._process_try,
            ast.With: self._process_with,
            ast.Return: self._process_return,
            ast.Raise: self._process_raise,
            ast.Break: self._process_break,
            ast.Continue: self._process_continue,
            ast.FunctionDef: self._process_nested_function,
            ast.AsyncFunctionDef: self._process_nested_function,
        }

        # O(1) lookup for statement handler
        handler = stmt_handlers.get(type(stmt))
        if handler:
            return handler(stmt)

        # Default: simple statement
        return self._process_simple_statement(stmt)

    def _process_if(self, stmt: ast.If) -> List[str]:
        """Process an if statement."""
        # Create condition node
        cond_node = self._add_node(
            NodeType.CONDITION,
            stmt,
            f"if {ast.unparse(stmt.test) if hasattr(ast, 'unparse') else '...'}:",
            {"condition": ast.dump(stmt.test)},
        )

        if self._current_node_id:
            self._add_edge(self._current_node_id, cond_node.id, EdgeType.SEQUENTIAL)

        exit_nodes: List[str] = []

        # Process true branch
        self._current_node_id = cond_node.id
        true_dummy = self._add_node(NodeType.STATEMENT, stmt, "# then branch")
        self._add_edge(cond_node.id, true_dummy.id, EdgeType.TRUE_BRANCH, "True")
        self._current_node_id = true_dummy.id
        true_exits = self._process_block(stmt.body)
        exit_nodes.extend(true_exits)

        # Process false branch (else/elif)
        if stmt.orelse:
            self._current_node_id = cond_node.id
            false_dummy = self._add_node(NodeType.STATEMENT, stmt, "# else branch")
            self._add_edge(cond_node.id, false_dummy.id, EdgeType.FALSE_BRANCH, "False")
            self._current_node_id = false_dummy.id
            false_exits = self._process_block(stmt.orelse)
            exit_nodes.extend(false_exits)
        else:
            # No else - condition node is an exit
            exit_nodes.append(cond_node.id)

        return exit_nodes

    def _process_for(self, stmt: ast.For) -> List[str]:
        """Process a for loop."""
        # Create loop header
        target = ast.unparse(stmt.target) if hasattr(ast, "unparse") else "..."
        iter_expr = ast.unparse(stmt.iter) if hasattr(ast, "unparse") else "..."
        header = self._add_node(
            NodeType.LOOP_HEADER,
            stmt,
            f"for {target} in {iter_expr}:",
        )

        if self._current_node_id:
            self._add_edge(self._current_node_id, header.id, EdgeType.SEQUENTIAL)

        # Create exit placeholder
        exit_id = self._generate_node_id()

        # Push loop context
        self._loop_stack.append((header.id, exit_id))

        # Process loop body
        self._current_node_id = header.id
        body_dummy = self._add_node(NodeType.LOOP_BODY, stmt, "# loop body")
        self._add_edge(header.id, body_dummy.id, EdgeType.TRUE_BRANCH, "next item")
        self._current_node_id = body_dummy.id
        body_exits = self._process_block(stmt.body)

        # Add back edges
        for exit_node in body_exits:
            self._add_edge(exit_node, header.id, EdgeType.LOOP_BACK)

        # Pop loop context
        self._loop_stack.pop()

        # Create actual exit node
        exit_node = CFGNode(
            id=exit_id,
            node_type=NodeType.STATEMENT,
            line_start=stmt.lineno,
            line_end=getattr(stmt, "end_lineno", stmt.lineno),
            code_snippet="# loop exit",
            ast_type="ForExit",
        )
        if self._current_graph:
            self._current_graph.nodes.append(exit_node)

        self._add_edge(header.id, exit_id, EdgeType.FALSE_BRANCH, "exhausted")

        # Process else clause
        if stmt.orelse:
            self._current_node_id = exit_id
            else_exits = self._process_block(stmt.orelse)
            return else_exits

        return [exit_id]

    def _process_while(self, stmt: ast.While) -> List[str]:
        """Process a while loop."""
        # Create loop header (condition)
        cond_expr = ast.unparse(stmt.test) if hasattr(ast, "unparse") else "..."
        header = self._add_node(
            NodeType.LOOP_HEADER,
            stmt,
            f"while {cond_expr}:",
            {"condition": cond_expr},
        )

        if self._current_node_id:
            self._add_edge(self._current_node_id, header.id, EdgeType.SEQUENTIAL)

        # Check for infinite loop patterns
        self._check_infinite_loop(stmt, header)

        # Create exit placeholder
        exit_id = self._generate_node_id()

        # Push loop context
        self._loop_stack.append((header.id, exit_id))

        # Process loop body
        self._current_node_id = header.id
        body_dummy = self._add_node(NodeType.LOOP_BODY, stmt, "# loop body")
        self._add_edge(header.id, body_dummy.id, EdgeType.TRUE_BRANCH, "condition true")
        self._current_node_id = body_dummy.id
        body_exits = self._process_block(stmt.body)

        # Add back edges
        for exit_node in body_exits:
            self._add_edge(exit_node, header.id, EdgeType.LOOP_BACK)

        # Pop loop context
        self._loop_stack.pop()

        # Create actual exit node
        exit_node = CFGNode(
            id=exit_id,
            node_type=NodeType.STATEMENT,
            line_start=stmt.lineno,
            line_end=getattr(stmt, "end_lineno", stmt.lineno),
            code_snippet="# loop exit",
            ast_type="WhileExit",
        )
        if self._current_graph:
            self._current_graph.nodes.append(exit_node)

        self._add_edge(header.id, exit_id, EdgeType.FALSE_BRANCH, "condition false")

        # Process else clause
        if stmt.orelse:
            self._current_node_id = exit_id
            else_exits = self._process_block(stmt.orelse)
            return else_exits

        return [exit_id]

    def _check_infinite_loop(self, stmt: ast.While, header: CFGNode) -> None:
        """Check for potential infinite loop patterns."""
        if self._current_graph is None:
            return

        # Check for while True without break
        if isinstance(stmt.test, ast.Constant) and stmt.test.value is True:
            # Check if body contains break
            has_break = any(
                isinstance(node, ast.Break) for node in ast.walk(ast.Module(body=stmt.body, type_ignores=[]))
            )
            if not has_break:
                issue = CFGIssue(
                    issue_type=IssueType.INFINITE_LOOP,
                    severity=IssueSeverity.CRITICAL,
                    line_start=stmt.lineno,
                    line_end=getattr(stmt, "end_lineno", stmt.lineno),
                    message="Infinite loop: 'while True' without break statement",
                    suggestion="Add a break condition or restructure the loop",
                    code_snippet=self._get_source_segment(stmt),
                )
                self._current_graph.issues.append(issue)
            else:
                # Has break but still potentially infinite
                issue = CFGIssue(
                    issue_type=IssueType.POTENTIAL_INFINITE_LOOP,
                    severity=IssueSeverity.LOW,
                    line_start=stmt.lineno,
                    line_end=getattr(stmt, "end_lineno", stmt.lineno),
                    message="Potential infinite loop: 'while True' with break",
                    suggestion="Verify break condition is always reachable",
                    code_snippet=self._get_source_segment(stmt),
                )
                self._current_graph.issues.append(issue)

        # Check for while loop without variable modification
        elif isinstance(stmt.test, _CONDITION_TYPES):  # Issue #380
            # Get variables in condition
            condition_vars = self._get_names_in_expr(stmt.test)
            # Check if any are modified in body
            modified_vars = self._get_modified_names(stmt.body)

            if condition_vars and not condition_vars.intersection(modified_vars):
                issue = CFGIssue(
                    issue_type=IssueType.POTENTIAL_INFINITE_LOOP,
                    severity=IssueSeverity.HIGH,
                    line_start=stmt.lineno,
                    line_end=getattr(stmt, "end_lineno", stmt.lineno),
                    message="Potential infinite loop: condition variables not modified in body",
                    suggestion=f"Variables {condition_vars} are not modified in loop body",
                    code_snippet=self._get_source_segment(stmt),
                )
                self._current_graph.issues.append(issue)

    def _get_names_in_expr(self, node: ast.expr) -> Set[str]:
        """Get all variable names used in an expression."""
        names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
        return names

    def _extract_names_from_assign(self, node: ast.Assign) -> Set[str]:
        """Extract modified names from assignment (Issue #315)."""
        return {t.id for t in node.targets if isinstance(t, ast.Name)}

    def _extract_name_from_target(self, target: ast.expr) -> Set[str]:
        """Extract name from assignment target if it's a Name node (Issue #315)."""
        return {target.id} if isinstance(target, ast.Name) else set()

    def _extract_modified_names_from_node(self, node: ast.AST) -> Set[str]:
        """Extract modified names from a single AST node. (Issue #315 - extracted)"""
        if isinstance(node, ast.Assign):
            return self._extract_names_from_assign(node)
        if isinstance(node, ast.AugAssign):
            return self._extract_name_from_target(node.target)
        if isinstance(node, ast.AnnAssign) and node.value:
            return self._extract_name_from_target(node.target)
        return set()

    def _get_modified_names(self, stmts: List[ast.stmt]) -> Set[str]:
        """Get all variable names modified in a block (Issue #315 - refactored)."""
        names: Set[str] = set()
        for stmt in stmts:
            for node in ast.walk(stmt):
                names.update(self._extract_modified_names_from_node(node))
        return names

    def _create_except_issue(
        self, handler: ast.ExceptHandler, issue_type: IssueType, message: str, suggestion: str
    ) -> CFGIssue:
        """
        Create a CFGIssue for an exception handler.

        Issue #665: Extracted from _process_try for clarity.
        """
        return CFGIssue(
            issue_type=issue_type,
            severity=IssueSeverity.MEDIUM,
            line_start=handler.lineno,
            line_end=getattr(handler, "end_lineno", handler.lineno),
            message=message,
            suggestion=suggestion,
            code_snippet=self._get_source_segment(handler),
        )

    def _check_exception_handler_issues(self, handler: ast.ExceptHandler) -> None:
        """
        Check exception handler for bare except or empty except issues.

        Issue #665: Extracted from _process_try for clarity.
        """
        if handler.type is None:
            issue = self._create_except_issue(
                handler,
                IssueType.BARE_EXCEPT,
                "Bare except clause catches all exceptions including SystemExit",
                "Specify exception types or use 'except Exception:'",
            )
            if self._current_graph:
                self._current_graph.issues.append(issue)

        if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
            issue = self._create_except_issue(
                handler,
                IssueType.EMPTY_EXCEPT,
                "Empty except block silently swallows exceptions",
                "Log the exception or handle it appropriately",
            )
            if self._current_graph:
                self._current_graph.issues.append(issue)

    def _process_try(self, stmt: ast.Try) -> List[str]:
        """
        Process a try statement.

        Issue #665: Refactored to use helper methods for issue detection.
        """
        try_node = self._add_node(NodeType.TRY_BLOCK, stmt, "try:")

        if self._current_node_id:
            self._add_edge(self._current_node_id, try_node.id, EdgeType.SEQUENTIAL)

        self._try_stack.append(try_node.id)
        exit_nodes: List[str] = []

        # Process try body
        self._current_node_id = try_node.id
        try_exits = self._process_block(stmt.body)
        exit_nodes.extend(try_exits)

        # Issue #665: Process except handlers using helper for issue checks
        for handler in stmt.handlers:
            handler_node = self._add_node(
                NodeType.EXCEPT_HANDLER,
                handler,
                f"except {handler.type.id if handler.type and hasattr(handler.type, 'id') else 'Exception'}:",
            )
            self._add_edge(try_node.id, handler_node.id, EdgeType.EXCEPTION)
            self._check_exception_handler_issues(handler)

            self._current_node_id = handler_node.id
            handler_exits = self._process_block(handler.body)
            exit_nodes.extend(handler_exits)

        # Process else clause
        if stmt.orelse:
            for try_exit in try_exits:
                else_node = self._add_node(NodeType.STATEMENT, stmt, "# else clause")
                self._add_edge(try_exit, else_node.id, EdgeType.SEQUENTIAL)
                self._current_node_id = else_node.id
                else_exits = self._process_block(stmt.orelse)
                exit_nodes.extend(else_exits)

        # Process finally clause
        if stmt.finalbody:
            finally_node = self._add_node(NodeType.FINALLY_BLOCK, stmt, "finally:")
            for exit_id in exit_nodes:
                self._add_edge(exit_id, finally_node.id, EdgeType.FINALLY)
            self._current_node_id = finally_node.id
            finally_exits = self._process_block(stmt.finalbody)
            exit_nodes = finally_exits

        self._try_stack.pop()
        return exit_nodes

    def _process_with(self, stmt: ast.With) -> List[str]:
        """Process a with statement."""
        items_str = ", ".join(
            ast.unparse(item.context_expr) if hasattr(ast, "unparse") else "..."
            for item in stmt.items
        )
        with_node = self._add_node(NodeType.STATEMENT, stmt, f"with {items_str}:")

        if self._current_node_id:
            self._add_edge(self._current_node_id, with_node.id, EdgeType.SEQUENTIAL)

        self._current_node_id = with_node.id
        return self._process_block(stmt.body)

    def _process_return(self, stmt: ast.Return) -> List[str]:
        """Process a return statement."""
        ret_node = self._add_node(NodeType.RETURN, stmt)

        if self._current_node_id:
            self._add_edge(self._current_node_id, ret_node.id, EdgeType.SEQUENTIAL)

        # Connect to function exit
        if self._current_graph and self._current_graph.exit_node_ids:
            self._add_edge(
                ret_node.id,
                self._current_graph.exit_node_ids[0],
                EdgeType.RETURN_EDGE,
            )

        return [ret_node.id]

    def _process_raise(self, stmt: ast.Raise) -> List[str]:
        """Process a raise statement."""
        raise_node = self._add_node(NodeType.RAISE, stmt)

        if self._current_node_id:
            self._add_edge(self._current_node_id, raise_node.id, EdgeType.SEQUENTIAL)

        # If in try block, connect to handlers
        if self._try_stack:
            self._add_edge(raise_node.id, self._try_stack[-1], EdgeType.EXCEPTION)

        return [raise_node.id]

    def _process_break(self, stmt: ast.Break) -> List[str]:
        """Process a break statement."""
        break_node = self._add_node(NodeType.BREAK, stmt)

        if self._current_node_id:
            self._add_edge(self._current_node_id, break_node.id, EdgeType.SEQUENTIAL)

        # Connect to loop exit
        if self._loop_stack:
            _, exit_id = self._loop_stack[-1]
            self._add_edge(break_node.id, exit_id, EdgeType.BREAK_OUT)

        return []  # Break terminates normal flow

    def _process_continue(self, stmt: ast.Continue) -> List[str]:
        """Process a continue statement."""
        cont_node = self._add_node(NodeType.CONTINUE, stmt)

        if self._current_node_id:
            self._add_edge(self._current_node_id, cont_node.id, EdgeType.SEQUENTIAL)

        # Connect back to loop header
        if self._loop_stack:
            header_id, _ = self._loop_stack[-1]
            self._add_edge(cont_node.id, header_id, EdgeType.CONTINUE_BACK)

        return []  # Continue terminates normal flow

    def _check_high_complexity(self, graph: "ControlFlowGraph", complexity: int) -> None:
        """
        Check and add issue for high cyclomatic complexity.

        Issue #665: Extracted from _calculate_metrics for clarity.
        """
        if complexity > 10:
            severity = IssueSeverity.CRITICAL if complexity > 20 else IssueSeverity.HIGH
            issue = CFGIssue(
                issue_type=IssueType.HIGH_CYCLOMATIC_COMPLEXITY,
                severity=severity,
                line_start=graph.nodes[0].line_start if graph.nodes else 1,
                line_end=graph.nodes[-1].line_end if graph.nodes else 1,
                message=f"High cyclomatic complexity: {complexity}",
                suggestion="Consider breaking function into smaller functions",
                metadata={"complexity": complexity},
            )
            graph.issues.append(issue)

    def _check_deep_nesting(self, graph: "ControlFlowGraph", max_depth: int) -> None:
        """
        Check and add issue for deep nesting.

        Issue #665: Extracted from _calculate_metrics for clarity.
        """
        if max_depth > 4:
            severity = IssueSeverity.HIGH if max_depth > 6 else IssueSeverity.MEDIUM
            issue = CFGIssue(
                issue_type=IssueType.DEEP_NESTING,
                severity=severity,
                line_start=graph.nodes[0].line_start if graph.nodes else 1,
                line_end=graph.nodes[-1].line_end if graph.nodes else 1,
                message=f"Deep nesting detected: {max_depth} levels",
                suggestion="Consider early returns or extracting nested logic",
                metadata={"depth": max_depth},
            )
            graph.issues.append(issue)

    def _calculate_metrics(self) -> None:
        """
        Calculate CFG metrics.

        Issue #665: Refactored to use helper methods for issue checks.
        """
        if not self._current_graph:
            return

        graph = self._current_graph

        # Cyclomatic complexity: E - N + 2P
        num_edges = len(graph.edges)
        num_nodes = len(graph.nodes)
        cyclomatic_complexity = num_edges - num_nodes + 2

        # Count decision and loop nodes
        decision_points = sum(
            1 for node in graph.nodes if node.node_type == NodeType.CONDITION
        )
        loop_count = sum(
            1 for node in graph.nodes if node.node_type == NodeType.LOOP_HEADER
        )
        max_depth = self._calculate_nesting_depth()

        graph.metrics = {
            "cyclomatic_complexity": cyclomatic_complexity,
            "node_count": num_nodes,
            "edge_count": num_edges,
            "decision_points": decision_points,
            "loop_count": loop_count,
            "max_nesting_depth": max_depth,
            "complexity_rating": self._rate_complexity(cyclomatic_complexity),
        }

        # Issue #665: Use extracted helper methods for issue detection
        self._check_high_complexity(graph, cyclomatic_complexity)
        self._check_deep_nesting(graph, max_depth)

    def _calculate_nesting_depth(self) -> int:
        """Calculate maximum nesting depth."""
        if not self._current_graph:
            return 0

        # Use BFS to find max depth
        max_depth = 0
        entry_id = self._current_graph.entry_node_id
        if not entry_id:
            return 0

        # Build adjacency list
        adj: Dict[str, List[str]] = {}
        for edge in self._current_graph.edges:
            if edge.source_id not in adj:
                adj[edge.source_id] = []
            adj[edge.source_id].append(edge.target_id)

        # BFS with depth tracking
        from collections import deque

        visited: Set[str] = set()
        queue: deque = deque([(entry_id, 0)])

        while queue:
            node_id, depth = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            max_depth = max(max_depth, depth)

            for neighbor in adj.get(node_id, []):
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))

        return max_depth

    def _rate_complexity(self, complexity: int) -> str:
        """Rate complexity level."""
        if complexity <= 5:
            return "low"
        elif complexity <= 10:
            return "moderate"
        elif complexity <= 20:
            return "high"
        else:
            return "very_high"

    def _detect_issues(self, func_node: ast.AST) -> None:
        """Detect additional control flow issues."""
        if not self._current_graph:
            return

        # Check for missing return in non-void function
        self._check_missing_return(func_node)

    def _check_missing_return(self, func_node: ast.AST) -> None:
        """Check if function might be missing return statements."""
        if not self._current_graph:
            return

        # Count return nodes
        return_nodes = [n for n in self._current_graph.nodes if n.node_type == NodeType.RETURN]

        if not return_nodes:
            # No explicit returns - might be intentional for void functions
            return

        # Check if all paths have returns
        # This is a simplified check - full analysis would require path enumeration
        exit_nodes = self._current_graph.exit_node_ids

        # Check edges to exit
        edges_to_exit = [
            e
            for e in self._current_graph.edges
            if e.target_id in exit_nodes and e.edge_type != EdgeType.RETURN_EDGE
        ]

        if edges_to_exit:
            # Some paths reach exit without return
            issue = CFGIssue(
                issue_type=IssueType.MISSING_RETURN,
                severity=IssueSeverity.MEDIUM,
                line_start=func_node.lineno,
                line_end=getattr(func_node, "end_lineno", func_node.lineno),
                message="Not all code paths return a value",
                suggestion="Ensure all branches have explicit return statements",
            )
            self._current_graph.issues.append(issue)


# ============================================================================
# API Models
# ============================================================================


class AnalyzeRequest(BaseModel):
    """Request to analyze source code."""

    source_code: str = Field(..., description="Python source code to analyze")
    file_path: str = Field(default="", description="Optional file path for context")


class AnalyzeFileRequest(BaseModel):
    """Request to analyze a file."""

    file_path: str = Field(..., description="Path to Python file")


class CFGResponse(BaseModel):
    """Response containing CFG analysis."""

    success: bool
    graphs: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    analysis_time_ms: float


# ============================================================================
# API Endpoints
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_cfg",
    error_code_prefix="CFG",
)
@router.post("/analyze")
async def analyze_control_flow(request: AnalyzeRequest) -> JSONResponse:
    """
    Analyze control flow in Python source code.

    Builds Control Flow Graphs and detects issues like:
    - Unreachable code
    - Infinite loops
    - High cyclomatic complexity
    - Deep nesting
    """
    start_time = time.time()

    try:
        builder = CFGBuilder(request.source_code, request.file_path)
        graphs = builder.build()

        # Aggregate issues
        all_issues = []
        for graph in graphs:
            for issue in graph.issues:
                issue_dict = issue.to_dict()
                issue_dict["function"] = graph.function_name
                all_issues.append(issue_dict)

        # Calculate summary
        summary = {
            "functions_analyzed": len(graphs),
            "total_nodes": sum(len(g.nodes) for g in graphs),
            "total_edges": sum(len(g.edges) for g in graphs),
            "total_issues": len(all_issues),
            "issues_by_severity": {
                "critical": sum(1 for i in all_issues if i["severity"] == "critical"),
                "high": sum(1 for i in all_issues if i["severity"] == "high"),
                "medium": sum(1 for i in all_issues if i["severity"] == "medium"),
                "low": sum(1 for i in all_issues if i["severity"] == "low"),
            },
            "avg_cyclomatic_complexity": (
                sum(g.metrics.get("cyclomatic_complexity", 0) for g in graphs) / len(graphs)
                if graphs
                else 0
            ),
        }

        analysis_time = (time.time() - start_time) * 1000

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "graphs": [g.to_dict() for g in graphs],
                "summary": summary,
                "issues": all_issues,
                "analysis_time_ms": round(analysis_time, 2),
            },
        )

    except SyntaxError as e:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Syntax error in source code: {e}",
                "graphs": [],
                "summary": {},
                "issues": [],
                "analysis_time_ms": (time.time() - start_time) * 1000,
            },
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_cfg_file",
    error_code_prefix="CFG",
)
@router.post("/analyze-file")
async def analyze_file_control_flow(request: AnalyzeFileRequest) -> JSONResponse:
    """Analyze control flow in a Python file."""
    file_path = Path(request.file_path)

    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(file_path.exists):
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")

    if not file_path.suffix == ".py":
        raise HTTPException(status_code=400, detail="Only Python files are supported")

    try:
        # Issue #358 - avoid blocking
        source_code = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

    analyze_request = AnalyzeRequest(source_code=source_code, file_path=str(file_path))
    return await analyze_control_flow(analyze_request)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_cfg_dot",
    error_code_prefix="CFG",
)
@router.post("/export/dot")
async def export_cfg_dot(request: AnalyzeRequest) -> JSONResponse:
    """
    Export CFG in DOT format for visualization with Graphviz.
    """
    builder = CFGBuilder(request.source_code, request.file_path)
    graphs = builder.build()

    dot_outputs = []

    for graph in graphs:
        dot_lines = [f'digraph "{graph.function_name}" {{']
        dot_lines.append('  rankdir=TB;')
        dot_lines.append('  node [shape=box, style=filled];')

        # Add nodes with colors based on type
        node_colors = {
            NodeType.ENTRY: "#90EE90",  # Light green
            NodeType.EXIT: "#FFB6C1",  # Light pink
            NodeType.CONDITION: "#87CEEB",  # Sky blue
            NodeType.LOOP_HEADER: "#DDA0DD",  # Plum
            NodeType.RETURN: "#FFDAB9",  # Peach
            NodeType.RAISE: "#FF6347",  # Tomato
        }

        for node in graph.nodes:
            color = node_colors.get(node.node_type, "#FFFFFF")
            label = node.code_snippet.replace('"', '\\"')[:50]
            dot_lines.append(
                f'  "{node.id}" [label="{label}", fillcolor="{color}"];'
            )

        # Add edges with labels
        edge_styles = {
            EdgeType.TRUE_BRANCH: "color=green",
            EdgeType.FALSE_BRANCH: "color=red",
            EdgeType.LOOP_BACK: "style=dashed, color=blue",
            EdgeType.EXCEPTION: "style=dotted, color=orange",
        }

        for edge in graph.edges:
            style = edge_styles.get(edge.edge_type, "")
            label = edge.condition if edge.condition else ""
            dot_lines.append(
                f'  "{edge.source_id}" -> "{edge.target_id}" [{style}, label="{label}"];'
            )

        dot_lines.append("}")
        dot_outputs.append(
            {"function_name": graph.function_name, "dot": "\n".join(dot_lines)}
        )

    return JSONResponse(
        status_code=200,
        content={"success": True, "dot_graphs": dot_outputs},
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_complexity_metrics",
    error_code_prefix="CFG",
)
@router.post("/complexity")
async def get_complexity_metrics(request: AnalyzeRequest) -> JSONResponse:
    """
    Get complexity metrics for all functions in source code.
    """
    builder = CFGBuilder(request.source_code, request.file_path)
    graphs = builder.build()

    metrics = []
    for graph in graphs:
        metrics.append(
            {
                "function_name": graph.function_name,
                "cyclomatic_complexity": graph.metrics.get("cyclomatic_complexity", 0),
                "complexity_rating": graph.metrics.get("complexity_rating", "unknown"),
                "node_count": graph.metrics.get("node_count", 0),
                "edge_count": graph.metrics.get("edge_count", 0),
                "decision_points": graph.metrics.get("decision_points", 0),
                "loop_count": graph.metrics.get("loop_count", 0),
                "max_nesting_depth": graph.metrics.get("max_nesting_depth", 0),
            }
        )

    # Sort by complexity
    metrics.sort(key=lambda m: m["cyclomatic_complexity"], reverse=True)

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "metrics": metrics,
            "summary": {
                "total_functions": len(metrics),
                "avg_complexity": (
                    sum(m["cyclomatic_complexity"] for m in metrics) / len(metrics)
                    if metrics
                    else 0
                ),
                "max_complexity": max(
                    (m["cyclomatic_complexity"] for m in metrics), default=0
                ),
                "high_complexity_count": sum(
                    1 for m in metrics if m["cyclomatic_complexity"] > 10
                ),
            },
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_unreachable",
    error_code_prefix="CFG",
)
@router.post("/unreachable")
async def detect_unreachable_code(request: AnalyzeRequest) -> JSONResponse:
    """
    Detect unreachable code in source.
    """
    builder = CFGBuilder(request.source_code, request.file_path)
    graphs = builder.build()

    unreachable_issues = []
    for graph in graphs:
        for issue in graph.issues:
            if issue.issue_type == IssueType.UNREACHABLE_CODE:
                issue_dict = issue.to_dict()
                issue_dict["function"] = graph.function_name
                unreachable_issues.append(issue_dict)

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "unreachable_code": unreachable_issues,
            "count": len(unreachable_issues),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_infinite_loops",
    error_code_prefix="CFG",
)
@router.post("/infinite-loops")
async def detect_infinite_loops(request: AnalyzeRequest) -> JSONResponse:
    """
    Detect potential infinite loops in source.
    """
    builder = CFGBuilder(request.source_code, request.file_path)
    graphs = builder.build()

    loop_issues = []
    for graph in graphs:
        for issue in graph.issues:
            if issue.issue_type in (
                IssueType.INFINITE_LOOP,
                IssueType.POTENTIAL_INFINITE_LOOP,
            ):
                issue_dict = issue.to_dict()
                issue_dict["function"] = graph.function_name
                loop_issues.append(issue_dict)

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "loop_issues": loop_issues,
            "definite_infinite": sum(
                1 for i in loop_issues if i["issue_type"] == "infinite_loop"
            ),
            "potential_infinite": sum(
                1 for i in loop_issues if i["issue_type"] == "potential_infinite_loop"
            ),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cfg_health",
    error_code_prefix="CFG",
)
@router.get("/health")
async def cfg_health() -> JSONResponse:
    """Health check for CFG analyzer."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "cfg_analyzer",
            "capabilities": [
                "cfg_construction",
                "unreachable_code_detection",
                "infinite_loop_detection",
                "complexity_analysis",
                "dot_export",
            ],
        },
    )
