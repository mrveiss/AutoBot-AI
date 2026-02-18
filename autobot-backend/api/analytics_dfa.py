# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data Flow Analysis Engine (Issue #234)

Tracks how data flows through the application to identify security issues,
data leaks, and optimization opportunities.

Features:
- Variable tracking across functions
- Def-Use chain analysis
- Taint analysis for security
- Source and sink identification
- Data transformation tracking
- Security vulnerability detection (SQL injection, XSS, etc.)
"""

import ast
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dfa", tags=["data-flow-analysis", "analytics"])


# =============================================================================
# Enums and Data Classes
# =============================================================================


class TaintLevel(str, Enum):
    """Taint levels for data flow tracking."""

    UNTAINTED = "untainted"  # Clean, trusted data
    PARTIALLY_TAINTED = "partially_tainted"  # May contain some tainted data
    TAINTED = "tainted"  # User input, external data
    SANITIZED = "sanitized"  # Was tainted, now sanitized


# Issue #380: Module-level constant for taint level checking
# This tuple is used repeatedly throughout the analysis engine
_TAINTED_LEVELS = (TaintLevel.TAINTED, TaintLevel.PARTIALLY_TAINTED)

# Issue #380: Module-level tuple for constant AST types
_CONSTANT_TYPES = (ast.Constant, ast.Num, ast.Str)


class SourceType(str, Enum):
    """Types of data sources."""

    USER_INPUT = "user_input"  # Direct user input
    EXTERNAL_API = "external_api"  # External API responses
    DATABASE = "database"  # Database queries
    FILE = "file"  # File reads
    ENVIRONMENT = "environment"  # Environment variables
    NETWORK = "network"  # Network data
    PARAMETER = "parameter"  # Function parameters
    CONSTANT = "constant"  # Hardcoded values


class SinkType(str, Enum):
    """Types of data sinks."""

    DATABASE_QUERY = "database_query"  # SQL queries
    FILE_WRITE = "file_write"  # File writes
    NETWORK_SEND = "network_send"  # Network transmission
    SUBPROCESS = "subprocess"  # Shell command execution
    EVAL = "eval"  # Dynamic code execution
    HTML_OUTPUT = "html_output"  # HTML/template rendering
    LOG_OUTPUT = "log_output"  # Logging (potential data leak)
    RETURN_VALUE = "return_value"  # Function return


class VulnerabilityType(str, Enum):
    """Types of security vulnerabilities."""

    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    CODE_INJECTION = "code_injection"
    DATA_EXPOSURE = "data_exposure"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    HARDCODED_SECRET = "hardcoded_secret"  # nosec B105 - vulnerability type enum


class Severity(str, Enum):
    """Vulnerability severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class VariableDefinition:
    """Represents a variable definition (assignment)."""

    name: str
    line: int
    column: int
    scope: str  # Function or module scope
    value_node: Optional[ast.AST] = None
    taint_level: TaintLevel = TaintLevel.UNTAINTED
    source_type: Optional[SourceType] = None


@dataclass
class VariableUse:
    """Represents a variable use (read)."""

    name: str
    line: int
    column: int
    scope: str
    context: str  # Where it's used (call, subscript, etc.)


@dataclass
class DefUseChain:
    """Links definitions to their uses."""

    definition: VariableDefinition
    uses: List[VariableUse] = field(default_factory=list)


@dataclass
class DataFlowEdge:
    """Represents data flow from one variable to another."""

    source_var: str
    source_line: int
    target_var: str
    target_line: int
    transformation: str = "assignment"  # Type of transformation


@dataclass
class TaintedPath:
    """Represents a path of tainted data from source to sink."""

    source: VariableDefinition
    sink_name: str
    sink_line: int
    sink_type: SinkType
    path: List[str]  # Variable names in the path
    taint_propagation: List[Tuple[str, int]]  # (var_name, line) along path


@dataclass
class SecurityVulnerability:
    """Detected security vulnerability."""

    vulnerability_type: VulnerabilityType
    severity: Severity
    line: int
    column: int
    description: str
    tainted_variable: str
    sink_function: str
    recommendation: str
    tainted_path: Optional[TaintedPath] = None


@dataclass
class DataFlowGraph:
    """Complete data flow graph for a function or module."""

    name: str
    definitions: List[VariableDefinition] = field(default_factory=list)
    uses: List[VariableUse] = field(default_factory=list)
    def_use_chains: List[DefUseChain] = field(default_factory=list)
    edges: List[DataFlowEdge] = field(default_factory=list)
    tainted_paths: List[TaintedPath] = field(default_factory=list)
    vulnerabilities: List[SecurityVulnerability] = field(default_factory=list)


# =============================================================================
# Taint Sources and Sinks Configuration
# =============================================================================

# Functions that introduce tainted data
TAINT_SOURCES: Dict[str, Tuple[SourceType, TaintLevel]] = {
    # User input
    "input": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    "raw_input": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    # Web frameworks
    "request.args.get": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    "request.form.get": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    "request.json": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    "request.data": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    "request.files": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    "request.headers": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    "request.cookies": (SourceType.USER_INPUT, TaintLevel.TAINTED),
    # File operations
    "open": (SourceType.FILE, TaintLevel.PARTIALLY_TAINTED),
    "read": (SourceType.FILE, TaintLevel.PARTIALLY_TAINTED),
    "readline": (SourceType.FILE, TaintLevel.PARTIALLY_TAINTED),
    "readlines": (SourceType.FILE, TaintLevel.PARTIALLY_TAINTED),
    # Database
    "fetchone": (SourceType.DATABASE, TaintLevel.PARTIALLY_TAINTED),
    "fetchall": (SourceType.DATABASE, TaintLevel.PARTIALLY_TAINTED),
    "fetchmany": (SourceType.DATABASE, TaintLevel.PARTIALLY_TAINTED),
    # Environment
    "os.environ.get": (SourceType.ENVIRONMENT, TaintLevel.PARTIALLY_TAINTED),
    "os.getenv": (SourceType.ENVIRONMENT, TaintLevel.PARTIALLY_TAINTED),
    # Network
    "socket.recv": (SourceType.NETWORK, TaintLevel.TAINTED),
    "requests.get": (SourceType.EXTERNAL_API, TaintLevel.PARTIALLY_TAINTED),
    "requests.post": (SourceType.EXTERNAL_API, TaintLevel.PARTIALLY_TAINTED),
    "urllib.request.urlopen": (SourceType.EXTERNAL_API, TaintLevel.PARTIALLY_TAINTED),
}

# Functions that are security-sensitive sinks
TAINT_SINKS: Dict[str, Tuple[SinkType, VulnerabilityType, Severity]] = {
    # SQL injection risks
    "execute": (
        SinkType.DATABASE_QUERY,
        VulnerabilityType.SQL_INJECTION,
        Severity.CRITICAL,
    ),
    "executemany": (
        SinkType.DATABASE_QUERY,
        VulnerabilityType.SQL_INJECTION,
        Severity.CRITICAL,
    ),
    "raw": (
        SinkType.DATABASE_QUERY,
        VulnerabilityType.SQL_INJECTION,
        Severity.CRITICAL,
    ),
    # Command injection risks
    "os.system": (
        SinkType.SUBPROCESS,
        VulnerabilityType.COMMAND_INJECTION,
        Severity.CRITICAL,
    ),
    "os.popen": (
        SinkType.SUBPROCESS,
        VulnerabilityType.COMMAND_INJECTION,
        Severity.CRITICAL,
    ),
    "subprocess.call": (
        SinkType.SUBPROCESS,
        VulnerabilityType.COMMAND_INJECTION,
        Severity.HIGH,
    ),
    "subprocess.run": (
        SinkType.SUBPROCESS,
        VulnerabilityType.COMMAND_INJECTION,
        Severity.HIGH,
    ),
    "subprocess.Popen": (
        SinkType.SUBPROCESS,
        VulnerabilityType.COMMAND_INJECTION,
        Severity.HIGH,
    ),
    # Code injection risks
    "eval": (SinkType.EVAL, VulnerabilityType.CODE_INJECTION, Severity.CRITICAL),
    "exec": (SinkType.EVAL, VulnerabilityType.CODE_INJECTION, Severity.CRITICAL),
    "compile": (SinkType.EVAL, VulnerabilityType.CODE_INJECTION, Severity.HIGH),
    # Path traversal risks
    "open": (SinkType.FILE_WRITE, VulnerabilityType.PATH_TRAVERSAL, Severity.HIGH),
    "os.path.join": (
        SinkType.FILE_WRITE,
        VulnerabilityType.PATH_TRAVERSAL,
        Severity.MEDIUM,
    ),
    # XSS risks (web frameworks)
    "render_template_string": (
        SinkType.HTML_OUTPUT,
        VulnerabilityType.XSS,
        Severity.HIGH,
    ),
    "Markup": (SinkType.HTML_OUTPUT, VulnerabilityType.XSS, Severity.MEDIUM),
    # Deserialization risks
    "pickle.loads": (
        SinkType.EVAL,
        VulnerabilityType.INSECURE_DESERIALIZATION,
        Severity.CRITICAL,
    ),
    "yaml.load": (
        SinkType.EVAL,
        VulnerabilityType.INSECURE_DESERIALIZATION,
        Severity.HIGH,
    ),
    "marshal.loads": (
        SinkType.EVAL,
        VulnerabilityType.INSECURE_DESERIALIZATION,
        Severity.HIGH,
    ),
}

# Functions that sanitize tainted data
SANITIZERS: Set[str] = {
    # Escaping
    "escape",
    "html.escape",
    "cgi.escape",
    "markupsafe.escape",
    # Parameterized queries (when used correctly)
    "cursor.execute",  # With parameters
    # Validation
    "int",
    "float",
    "bool",
    "uuid.UUID",
    # Path sanitization
    "os.path.basename",
    "os.path.normpath",
    "pathlib.Path",
}


# =============================================================================
# Data Flow Analyzer
# =============================================================================


class DataFlowAnalyzer(ast.NodeVisitor):
    """Analyzes data flow in Python code."""

    def __init__(self, source_code: str, file_path: str = ""):
        """Initialize data flow analyzer with source code and tracking state."""
        self.source_code = source_code
        self.file_path = file_path
        self.graphs: List[DataFlowGraph] = []

        # Current scope tracking
        self.current_scope: str = "<module>"
        self.current_graph: Optional[DataFlowGraph] = None

        # Variable tracking
        self.definitions: Dict[str, List[VariableDefinition]] = {}
        self.uses: List[VariableUse] = []
        self.taint_map: Dict[str, TaintLevel] = {}  # var_name -> taint level

        # Data flow tracking
        self.edges: List[DataFlowEdge] = []
        self.tainted_paths: List[TaintedPath] = []
        self.vulnerabilities: List[SecurityVulnerability] = []

    def analyze(self) -> List[DataFlowGraph]:
        """Analyze the source code and return data flow graphs."""
        try:
            tree = ast.parse(self.source_code)
            self.visit(tree)
            self._finalize_analysis()
            return self.graphs
        except SyntaxError as e:
            logger.error("Syntax error in %s: %s", self.file_path, e)
            raise

    def _finalize_analysis(self):
        """Finalize analysis and build def-use chains."""
        if self.current_graph:
            self._build_def_use_chains()
            self._propagate_taint()
            self._detect_vulnerabilities()
            self.graphs.append(self.current_graph)

    def _start_scope(self, name: str) -> DataFlowGraph:
        """Start a new scope for analysis."""
        if self.current_graph:
            self._build_def_use_chains()
            self._propagate_taint()
            self._detect_vulnerabilities()
            self.graphs.append(self.current_graph)

        self.current_scope = name
        self.current_graph = DataFlowGraph(name=name)
        self.definitions = {}
        self.uses = []
        self.edges = []
        self.taint_map = {}
        return self.current_graph

    def _add_definition(
        self,
        name: str,
        line: int,
        column: int,
        value_node: Optional[ast.AST] = None,
        taint_level: TaintLevel = TaintLevel.UNTAINTED,
        source_type: Optional[SourceType] = None,
    ):
        """Add a variable definition."""
        definition = VariableDefinition(
            name=name,
            line=line,
            column=column,
            scope=self.current_scope,
            value_node=value_node,
            taint_level=taint_level,
            source_type=source_type,
        )

        if name not in self.definitions:
            self.definitions[name] = []
        self.definitions[name].append(definition)

        if self.current_graph:
            self.current_graph.definitions.append(definition)

        # Track taint level
        self.taint_map[name] = taint_level

    def _add_use(self, name: str, line: int, column: int, context: str = "load"):
        """Add a variable use."""
        use = VariableUse(
            name=name,
            line=line,
            column=column,
            scope=self.current_scope,
            context=context,
        )
        self.uses.append(use)
        if self.current_graph:
            self.current_graph.uses.append(use)

    def _add_edge(
        self,
        source_var: str,
        source_line: int,
        target_var: str,
        target_line: int,
        transformation: str = "assignment",
    ):
        """Add a data flow edge."""
        edge = DataFlowEdge(
            source_var=source_var,
            source_line=source_line,
            target_var=target_var,
            target_line=target_line,
            transformation=transformation,
        )
        self.edges.append(edge)
        if self.current_graph:
            self.current_graph.edges.append(edge)

    def _build_def_use_chains(self):
        """Build def-use chains from definitions and uses.

        Issue #508: Optimized O(n³) → O(n²) by pre-indexing uses by variable name.
        """
        if not self.current_graph:
            return

        # Issue #508: Pre-index uses by variable name - O(n) preprocessing
        # instead of O(n) lookup per definition
        uses_by_name: Dict[str, List] = {}
        for use in self.uses:
            if use.name not in uses_by_name:
                uses_by_name[use.name] = []
            uses_by_name[use.name].append(use)

        for var_name, defs in self.definitions.items():
            # O(1) lookup instead of O(n) scan
            var_uses = uses_by_name.get(var_name, [])
            for definition in defs:
                chain = DefUseChain(definition=definition)

                # Find all uses of this variable after this definition
                for use in var_uses:
                    if use.line >= definition.line:
                        chain.uses.append(use)

                self.current_graph.def_use_chains.append(chain)

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract the full call name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""

    def _check_taint_source(
        self, node: ast.Call
    ) -> Optional[Tuple[SourceType, TaintLevel]]:
        """Check if a call is a taint source."""
        call_name = self._get_call_name(node)

        # Check exact match
        if call_name in TAINT_SOURCES:
            return TAINT_SOURCES[call_name]

        # Check partial match (for method calls)
        for source_name, taint_info in TAINT_SOURCES.items():
            if call_name.endswith(source_name) or source_name in call_name:
                return taint_info

        return None

    def _check_taint_sink(
        self, node: ast.Call
    ) -> Optional[Tuple[SinkType, VulnerabilityType, Severity]]:
        """Check if a call is a taint sink."""
        call_name = self._get_call_name(node)

        # Check exact match
        if call_name in TAINT_SINKS:
            return TAINT_SINKS[call_name]

        # Check partial match
        for sink_name, sink_info in TAINT_SINKS.items():
            if call_name.endswith(sink_name) or sink_name in call_name:
                return sink_info

        return None

    def _is_sanitizer(self, node: ast.Call) -> bool:
        """Check if a call is a sanitizer."""
        call_name = self._get_call_name(node)
        return call_name in SANITIZERS or any(s in call_name for s in SANITIZERS)

    def _taint_from_name(self, node: ast.Name) -> TaintLevel:
        """Get taint from Name node (Issue #315)."""
        return self.taint_map.get(node.id, TaintLevel.UNTAINTED)

    def _taint_from_call(self, node: ast.Call) -> TaintLevel:
        """Get taint from Call node (Issue #315)."""
        taint_info = self._check_taint_source(node)
        if taint_info:
            return taint_info[1]
        if self._is_sanitizer(node):
            return TaintLevel.SANITIZED
        # Propagate taint from arguments
        max_taint = TaintLevel.UNTAINTED
        for arg in node.args:
            arg_taint = self._get_taint_from_expr(arg)
            if arg_taint == TaintLevel.TAINTED:
                return TaintLevel.TAINTED
            if arg_taint == TaintLevel.PARTIALLY_TAINTED:
                max_taint = TaintLevel.PARTIALLY_TAINTED
        return max_taint

    def _taint_from_binop(self, node: ast.BinOp) -> TaintLevel:
        """Get taint from BinOp (Issue #315)."""
        left_taint = self._get_taint_from_expr(node.left)
        right_taint = self._get_taint_from_expr(node.right)
        if TaintLevel.TAINTED in (left_taint, right_taint):
            return TaintLevel.TAINTED
        if TaintLevel.PARTIALLY_TAINTED in (left_taint, right_taint):
            return TaintLevel.PARTIALLY_TAINTED
        return TaintLevel.UNTAINTED

    def _taint_from_joinedstr(self, node: ast.JoinedStr) -> TaintLevel:
        """Get taint from f-string (Issue #315)."""
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                taint = self._get_taint_from_expr(value.value)
                if taint in _TAINTED_LEVELS:
                    return taint
        return TaintLevel.UNTAINTED

    def _get_taint_from_expr(self, node: ast.AST) -> TaintLevel:
        """Determine taint level of an expression (Issue #315 - dispatch table)."""
        # Dispatch table for taint analysis
        taint_handlers = {
            ast.Name: self._taint_from_name,
            ast.Call: self._taint_from_call,
            ast.BinOp: self._taint_from_binop,
            ast.JoinedStr: self._taint_from_joinedstr,
        }

        handler = taint_handlers.get(type(node))
        if handler:
            return handler(node)

        # Constants are untainted - Issue #380: Use module-level constant
        if isinstance(node, _CONSTANT_TYPES):
            return TaintLevel.UNTAINTED

        # Propagate through subscript/attribute
        if isinstance(node, ast.Subscript):
            return self._get_taint_from_expr(node.value)
        if isinstance(node, ast.Attribute):
            return self._get_taint_from_expr(node.value)

        return TaintLevel.UNTAINTED

    def _propagate_taint(self):
        """Propagate taint through data flow edges."""
        changed = True
        iterations = 0
        max_iterations = 100  # Prevent infinite loops

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            for edge in self.edges:
                source_taint = self.taint_map.get(edge.source_var, TaintLevel.UNTAINTED)
                target_taint = self.taint_map.get(edge.target_var, TaintLevel.UNTAINTED)

                # Propagate taint
                if (
                    source_taint == TaintLevel.TAINTED
                    and target_taint != TaintLevel.TAINTED
                ):
                    self.taint_map[edge.target_var] = TaintLevel.TAINTED
                    changed = True
                elif (
                    source_taint == TaintLevel.PARTIALLY_TAINTED
                    and target_taint == TaintLevel.UNTAINTED
                ):
                    self.taint_map[edge.target_var] = TaintLevel.PARTIALLY_TAINTED
                    changed = True

    def _detect_vulnerabilities(self):
        """Detect security vulnerabilities from taint analysis."""
        if not self.current_graph:
            return

        # Check all uses for potential vulnerabilities
        for use in self.uses:
            taint_level = self.taint_map.get(use.name, TaintLevel.UNTAINTED)

            if taint_level in _TAINTED_LEVELS:
                # Check if this use is in a dangerous context
                # This is tracked during visit_Call
                pass

    def _create_vulnerability(
        self,
        vuln_type: VulnerabilityType,
        severity: Severity,
        line: int,
        column: int,
        variable: str,
        sink_function: str,
        taint_level: TaintLevel,
    ) -> SecurityVulnerability:
        """Create a security vulnerability record."""
        recommendations = {
            VulnerabilityType.SQL_INJECTION: "Use parameterized queries or an ORM",
            VulnerabilityType.XSS: "Escape output or use a templating engine with auto-escaping",
            VulnerabilityType.COMMAND_INJECTION: "Use subprocess with list arguments, avoid shell=True",
            VulnerabilityType.PATH_TRAVERSAL: "Validate and sanitize file paths, use os.path.basename",
            VulnerabilityType.CODE_INJECTION: "Never use eval/exec with user input",
            VulnerabilityType.DATA_EXPOSURE: "Sanitize data before logging or exposing",
            VulnerabilityType.INSECURE_DESERIALIZATION: "Use safe serialization formats like JSON",
            VulnerabilityType.HARDCODED_SECRET: "Use environment variables or a secrets manager",
        }

        vuln = SecurityVulnerability(
            vulnerability_type=vuln_type,
            severity=severity,
            line=line,
            column=column,
            description=f"Potentially {taint_level.value} data flows to {sink_function}",
            tainted_variable=variable,
            sink_function=sink_function,
            recommendation=recommendations.get(vuln_type, "Review and sanitize input"),
        )

        self.vulnerabilities.append(vuln)
        if self.current_graph:
            self.current_graph.vulnerabilities.append(vuln)

        return vuln

    # =========================================================================
    # AST Visitor Methods
    # =========================================================================

    def visit_Module(self, node: ast.Module):
        """Visit module level."""
        self._start_scope("<module>")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition."""
        self._start_scope(node.name)

        # Track function parameters as potentially tainted
        for arg in node.args.args:
            arg_name = arg.arg
            self._add_definition(
                name=arg_name,
                line=node.lineno,
                column=node.col_offset,
                taint_level=TaintLevel.PARTIALLY_TAINTED,  # Parameters may be tainted
                source_type=SourceType.PARAMETER,
            )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit async function definition."""
        self._start_scope(f"async_{node.name}")

        for arg in node.args.args:
            self._add_definition(
                name=arg.arg,
                line=node.lineno,
                column=node.col_offset,
                taint_level=TaintLevel.PARTIALLY_TAINTED,
                source_type=SourceType.PARAMETER,
            )

        self.generic_visit(node)

    def _process_assign_target(
        self,
        target: ast.AST,
        node: ast.Assign,
        value_taint: TaintLevel,
        source_type: Optional[SourceType],
    ) -> None:
        """Process a single assignment target. (Issue #315 - extracted)"""
        if isinstance(target, ast.Name):
            self._add_definition(
                name=target.id,
                line=node.lineno,
                column=target.col_offset,
                value_node=node.value,
                taint_level=value_taint,
                source_type=source_type,
            )
            self._extract_edges_from_expr(node.value, target.id, node.lineno)
        elif isinstance(target, ast.Tuple):
            for elt in target.elts:
                if isinstance(elt, ast.Name):
                    self._add_definition(
                        name=elt.id,
                        line=node.lineno,
                        column=elt.col_offset,
                        value_node=node.value,
                        taint_level=value_taint,
                        source_type=source_type,
                    )

    def visit_Assign(self, node: ast.Assign):
        """Visit assignment statement."""
        # Determine taint level of the value
        value_taint = self._get_taint_from_expr(node.value)
        source_type = None

        # Check if value is a taint source
        if isinstance(node.value, ast.Call):
            taint_info = self._check_taint_source(node.value)
            if taint_info:
                source_type, value_taint = taint_info

        # Track each target using helper (Issue #315 - reduced depth)
        for target in node.targets:
            self._process_assign_target(target, node, value_taint, source_type)

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        """Visit annotated assignment."""
        if isinstance(node.target, ast.Name) and node.value:
            value_taint = self._get_taint_from_expr(node.value)
            self._add_definition(
                name=node.target.id,
                line=node.lineno,
                column=node.target.col_offset,
                value_node=node.value,
                taint_level=value_taint,
            )
            self._extract_edges_from_expr(node.value, node.target.id, node.lineno)

        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        """Visit augmented assignment (+=, -=, etc.)."""
        if isinstance(node.target, ast.Name):
            # The target is both used and defined
            self._add_use(
                node.target.id, node.lineno, node.target.col_offset, "augassign"
            )

            value_taint = self._get_taint_from_expr(node.value)
            current_taint = self.taint_map.get(node.target.id, TaintLevel.UNTAINTED)

            # Combine taints (more tainted wins)
            if value_taint == TaintLevel.TAINTED or current_taint == TaintLevel.TAINTED:
                final_taint = TaintLevel.TAINTED
            elif (
                value_taint == TaintLevel.PARTIALLY_TAINTED
                or current_taint == TaintLevel.PARTIALLY_TAINTED
            ):
                final_taint = TaintLevel.PARTIALLY_TAINTED
            else:
                final_taint = TaintLevel.UNTAINTED

            self._add_definition(
                name=node.target.id,
                line=node.lineno,
                column=node.target.col_offset,
                value_node=node.value,
                taint_level=final_taint,
            )

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """Visit name reference."""
        if isinstance(node.ctx, ast.Load):
            self._add_use(node.id, node.lineno, node.col_offset, "load")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Visit function call - check for sinks."""
        call_name = self._get_call_name(node)

        # Check if this is a taint sink
        sink_info = self._check_taint_sink(node)
        if sink_info:
            sink_type, vuln_type, severity = sink_info

            # Check all arguments for tainted data
            for arg in node.args:
                taint_level = self._get_taint_from_expr(arg)

                if taint_level in _TAINTED_LEVELS:
                    # Get variable name if it's a name reference
                    if isinstance(arg, ast.Name):
                        var_name = arg.id
                    else:
                        var_name = "<expression>"

                    self._create_vulnerability(
                        vuln_type=vuln_type,
                        severity=severity,
                        line=node.lineno,
                        column=node.col_offset,
                        variable=var_name,
                        sink_function=call_name,
                        taint_level=taint_level,
                    )

        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        """Visit for loop - track iterator variable."""
        if isinstance(node.target, ast.Name):
            iter_taint = self._get_taint_from_expr(node.iter)
            self._add_definition(
                name=node.target.id,
                line=node.lineno,
                column=node.target.col_offset,
                taint_level=iter_taint,
            )

        self.generic_visit(node)

    def visit_With(self, node: ast.With):
        """Visit with statement - track context variable."""
        for item in node.items:
            if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                context_taint = self._get_taint_from_expr(item.context_expr)
                self._add_definition(
                    name=item.optional_vars.id,
                    line=node.lineno,
                    column=item.optional_vars.col_offset,
                    taint_level=context_taint,
                )

        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        """Visit exception handler - track exception variable."""
        if node.name:
            self._add_definition(
                name=node.name,
                line=node.lineno,
                column=node.col_offset,
                taint_level=TaintLevel.UNTAINTED,  # Exceptions are local
            )

        self.generic_visit(node)

    def _extract_from_name(self, expr: ast.Name, target_var: str, target_line: int):
        """Extract edge from Name node (Issue #315)."""
        self._add_edge(
            source_var=expr.id,
            source_line=expr.lineno if hasattr(expr, "lineno") else target_line,
            target_var=target_var,
            target_line=target_line,
        )

    def _extract_from_binop(self, expr: ast.BinOp, target_var: str, target_line: int):
        """Extract edges from BinOp (Issue #315)."""
        self._extract_edges_from_expr(expr.left, target_var, target_line)
        self._extract_edges_from_expr(expr.right, target_var, target_line)

    def _extract_from_call(self, expr: ast.Call, target_var: str, target_line: int):
        """Extract edges from Call arguments (Issue #315)."""
        for arg in expr.args:
            self._extract_edges_from_expr(arg, target_var, target_line)

    def _extract_from_subscript(
        self, expr: ast.Subscript, target_var: str, target_line: int
    ):
        """Extract edges from Subscript (Issue #315)."""
        self._extract_edges_from_expr(expr.value, target_var, target_line)

    def _extract_from_attribute(
        self, expr: ast.Attribute, target_var: str, target_line: int
    ):
        """Extract edges from Attribute (Issue #315)."""
        self._extract_edges_from_expr(expr.value, target_var, target_line)

    def _extract_from_joinedstr(
        self, expr: ast.JoinedStr, target_var: str, target_line: int
    ):
        """Extract edges from f-string (Issue #315)."""
        for value in expr.values:
            if isinstance(value, ast.FormattedValue):
                self._extract_edges_from_expr(value.value, target_var, target_line)

    def _extract_from_collection(self, expr, target_var: str, target_line: int):
        """Extract edges from List/Tuple/Set (Issue #315)."""
        for elt in expr.elts:
            self._extract_edges_from_expr(elt, target_var, target_line)

    def _extract_from_dict(self, expr: ast.Dict, target_var: str, target_line: int):
        """Extract edges from Dict (Issue #315)."""
        for key in expr.keys:
            if key:
                self._extract_edges_from_expr(key, target_var, target_line)
        for value in expr.values:
            self._extract_edges_from_expr(value, target_var, target_line)

    def _extract_edges_from_expr(
        self, expr: ast.AST, target_var: str, target_line: int
    ):
        """Extract data flow edges from an expression (Issue #315 - dispatch table)."""
        # Dispatch table for expression type handlers
        handlers = {
            ast.Name: self._extract_from_name,
            ast.BinOp: self._extract_from_binop,
            ast.Call: self._extract_from_call,
            ast.Subscript: self._extract_from_subscript,
            ast.Attribute: self._extract_from_attribute,
            ast.JoinedStr: self._extract_from_joinedstr,
            ast.List: self._extract_from_collection,
            ast.Tuple: self._extract_from_collection,
            ast.Set: self._extract_from_collection,
            ast.Dict: self._extract_from_dict,
        }

        handler = handlers.get(type(expr))
        if handler:
            handler(expr, target_var, target_line)


# =============================================================================
# API Models
# =============================================================================


class AnalyzeRequest(BaseModel):
    """Request model for code analysis."""

    source_code: str = Field(..., description="Python source code to analyze")
    file_path: str = Field(default="<unknown>", description="File path for context")


class AnalyzeFileRequest(BaseModel):
    """Request model for file analysis."""

    file_path: str = Field(..., description="Path to Python file to analyze")


class VariableDefResponse(BaseModel):
    """Response model for variable definition."""

    name: str
    line: int
    column: int
    scope: str
    taint_level: str
    source_type: Optional[str]


class VulnerabilityResponse(BaseModel):
    """Response model for vulnerability."""

    vulnerability_type: str
    severity: str
    line: int
    column: int
    description: str
    tainted_variable: str
    sink_function: str
    recommendation: str


class DataFlowResponse(BaseModel):
    """Response model for data flow analysis."""

    name: str
    definitions_count: int
    uses_count: int
    edges_count: int
    vulnerabilities_count: int
    definitions: List[VariableDefResponse]
    vulnerabilities: List[VulnerabilityResponse]


class AnalysisResponse(BaseModel):
    """Response model for complete analysis."""

    file_path: str
    analyzed_at: str
    graphs: List[DataFlowResponse]
    total_definitions: int
    total_uses: int
    total_vulnerabilities: int
    tainted_variables: List[str]


class TaintSummary(BaseModel):
    """Summary of taint analysis."""

    tainted_sources: int
    dangerous_sinks: int
    vulnerabilities_by_type: Dict[str, int]
    vulnerabilities_by_severity: Dict[str, int]
    tainted_variables: List[str]


# =============================================================================
# API Endpoints
# =============================================================================


def _build_analysis_response(
    graphs: List["DataFlowGraph"], file_path: str
) -> AnalysisResponse:
    """Build AnalysisResponse from analyzed graphs (Issue #665: extracted helper)."""
    graph_responses = []
    total_defs = 0
    total_uses = 0
    total_vulns = 0
    all_tainted: Set[str] = set()

    for graph in graphs:
        defs = [
            VariableDefResponse(
                name=d.name,
                line=d.line,
                column=d.column,
                scope=d.scope,
                taint_level=d.taint_level.value,
                source_type=d.source_type.value if d.source_type else None,
            )
            for d in graph.definitions
        ]

        vulns = [
            VulnerabilityResponse(
                vulnerability_type=v.vulnerability_type.value,
                severity=v.severity.value,
                line=v.line,
                column=v.column,
                description=v.description,
                tainted_variable=v.tainted_variable,
                sink_function=v.sink_function,
                recommendation=v.recommendation,
            )
            for v in graph.vulnerabilities
        ]

        graph_responses.append(
            DataFlowResponse(
                name=graph.name,
                definitions_count=len(graph.definitions),
                uses_count=len(graph.uses),
                edges_count=len(graph.edges),
                vulnerabilities_count=len(graph.vulnerabilities),
                definitions=defs,
                vulnerabilities=vulns,
            )
        )

        total_defs += len(graph.definitions)
        total_uses += len(graph.uses)
        total_vulns += len(graph.vulnerabilities)

        for d in graph.definitions:
            if d.taint_level in _TAINTED_LEVELS:
                all_tainted.add(d.name)

    return AnalysisResponse(
        file_path=file_path,
        analyzed_at=datetime.now().isoformat(),
        graphs=graph_responses,
        total_definitions=total_defs,
        total_uses=total_uses,
        total_vulnerabilities=total_vulns,
        tainted_variables=list(all_tainted),
    )


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_code(
    request: AnalyzeRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Analyze Python source code for data flow and security vulnerabilities (Issue #665: uses helper).

    Issue #744: Requires admin authentication.

    Performs:
    - Variable tracking (definitions and uses)
    - Taint analysis (source to sink tracking)
    - Security vulnerability detection
    """
    try:
        analyzer = DataFlowAnalyzer(request.source_code, request.file_path)
        graphs = analyzer.analyze()
        return _build_analysis_response(graphs, request.file_path)

    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Syntax error in code: {str(e)}")
    except Exception as e:
        logger.error("Analysis error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-file", response_model=AnalysisResponse)
async def analyze_file(
    request: AnalyzeFileRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Analyze a Python file for data flow and security vulnerabilities (Issue #665: uses helper).

    Issue #744: Requires admin authentication.
    """
    import aiofiles

    try:
        async with aiofiles.open(request.file_path, "r", encoding="utf-8") as f:
            source_code = await f.read()

        analyzer = DataFlowAnalyzer(source_code, request.file_path)
        graphs = analyzer.analyze()
        return _build_analysis_response(graphs, request.file_path)

    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"File not found: {request.file_path}"
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Syntax error in file: {str(e)}")
    except Exception as e:
        logger.error("File analysis error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vulnerabilities")
async def get_vulnerabilities(
    request: AnalyzeRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Get only security vulnerabilities from code analysis.

    Issue #744: Requires admin authentication.
    """
    try:
        analyzer = DataFlowAnalyzer(request.source_code, request.file_path)
        graphs = analyzer.analyze()

        all_vulns = []
        for graph in graphs:
            for v in graph.vulnerabilities:
                all_vulns.append(
                    {
                        "function": graph.name,
                        "vulnerability_type": v.vulnerability_type.value,
                        "severity": v.severity.value,
                        "line": v.line,
                        "column": v.column,
                        "description": v.description,
                        "tainted_variable": v.tainted_variable,
                        "sink_function": v.sink_function,
                        "recommendation": v.recommendation,
                    }
                )

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        all_vulns.sort(key=lambda v: severity_order.get(v["severity"], 5))

        return {
            "file_path": request.file_path,
            "total_vulnerabilities": len(all_vulns),
            "vulnerabilities": all_vulns,
        }

    except Exception as e:
        logger.error("Vulnerability analysis error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _aggregate_graph_taint_stats(
    graph,
    tainted_vars: set,
    vulns_by_type: Dict[str, int],
    vulns_by_severity: Dict[str, int],
    counts: Dict[str, int],
) -> None:
    """Aggregate taint statistics from a single graph. (Issue #315 - extracted)"""
    for d in graph.definitions:
        if d.taint_level in _TAINTED_LEVELS:
            tainted_vars.add(d.name)
            if d.source_type:
                counts["sources"] += 1

    for v in graph.vulnerabilities:
        counts["sinks"] += 1
        vtype = v.vulnerability_type.value
        vsev = v.severity.value
        vulns_by_type[vtype] = vulns_by_type.get(vtype, 0) + 1
        vulns_by_severity[vsev] = vulns_by_severity.get(vsev, 0) + 1


@router.post("/taint-summary", response_model=TaintSummary)
async def get_taint_summary(
    request: AnalyzeRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Get summary of taint analysis.

    Issue #744: Requires admin authentication.
    """
    try:
        analyzer = DataFlowAnalyzer(request.source_code, request.file_path)
        graphs = analyzer.analyze()

        tainted_vars: set = set()
        vulns_by_type: Dict[str, int] = {}
        vulns_by_severity: Dict[str, int] = {}
        counts = {"sources": 0, "sinks": 0}

        # Aggregate stats using helper (Issue #315 - reduced depth)
        for graph in graphs:
            _aggregate_graph_taint_stats(
                graph, tainted_vars, vulns_by_type, vulns_by_severity, counts
            )

        return TaintSummary(
            tainted_sources=counts["sources"],
            dangerous_sinks=counts["sinks"],
            vulnerabilities_by_type=vulns_by_type,
            vulnerabilities_by_severity=vulns_by_severity,
            tainted_variables=list(tainted_vars),
        )

    except Exception as e:
        logger.error("Taint summary error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
async def list_taint_sources(admin_check: bool = Depends(check_admin_permission)):
    """
    List all recognized taint sources.

    Issue #744: Requires admin authentication.
    """
    return {
        "sources": [
            {
                "name": name,
                "source_type": info[0].value,
                "taint_level": info[1].value,
            }
            for name, info in TAINT_SOURCES.items()
        ]
    }


@router.get("/sinks")
async def list_taint_sinks(admin_check: bool = Depends(check_admin_permission)):
    """
    List all recognized security-sensitive sinks.

    Issue #744: Requires admin authentication.
    """
    return {
        "sinks": [
            {
                "name": name,
                "sink_type": info[0].value,
                "vulnerability_type": info[1].value,
                "severity": info[2].value,
            }
            for name, info in TAINT_SINKS.items()
        ]
    }


@router.get("/sanitizers")
async def list_sanitizers(admin_check: bool = Depends(check_admin_permission)):
    """
    List all recognized sanitizer functions.

    Issue #744: Requires admin authentication.
    """
    return {"sanitizers": sorted(SANITIZERS)}


@router.get("/health")
async def health_check(admin_check: bool = Depends(check_admin_permission)):
    """
    Health check endpoint.

    Issue #744: Requires admin authentication.
    """
    return {
        "status": "healthy",
        "service": "data-flow-analysis",
        "features": [
            "variable_tracking",
            "def_use_chains",
            "taint_analysis",
            "vulnerability_detection",
        ],
    }
