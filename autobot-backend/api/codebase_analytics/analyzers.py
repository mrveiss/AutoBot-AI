# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code analysis functions for codebase analytics
"""

import ast
import asyncio
import json
import logging
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import aiofiles
from backend.constants.network_constants import NetworkConstants
from backend.type_defs.common import Metadata
from llm_interface import LLMInterface

logger = logging.getLogger(__name__)

# Code intelligence analyzers (Issue #268)
# Issue #662: Thread-safe locks for analyzer singletons
_analyzers_lock = threading.Lock()

try:
    from code_intelligence.anti_pattern_detector import AntiPatternDetector
    from code_intelligence.bug_predictor import BugPredictor
    from code_intelligence.performance_analyzer import PerformanceAnalyzer

    _anti_pattern_detector: Optional[AntiPatternDetector] = None
    _performance_analyzer: Optional[PerformanceAnalyzer] = None
    _bug_predictor: Optional[BugPredictor] = None
    _analyzers_available = True
except ImportError as e:
    logger.warning("Code intelligence analyzers not available: %s", e)
    _analyzers_available = False
    _anti_pattern_detector = None
    _performance_analyzer = None
    _bug_predictor = None


# =============================================================================
# Race Condition Detection Helper Functions (Issue #298 - Reduce Deep Nesting)
# =============================================================================


# Issue #315: Lock import patterns
_ASYNCIO_LOCK_NAMES = frozenset(("Lock", "Semaphore", "Event", "Condition"))
_THREADING_LOCK_NAMES = frozenset(("Lock", "RLock", "Semaphore", "Event", "Condition"))

# Issue #380: Module-level tuple for function definition AST nodes
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_IMPORT_TYPES = (ast.Import, ast.ImportFrom)

# Issue #380: Module-level tuple for mutable type annotation checking
_MUTABLE_TYPE_ANNOTATIONS = ("Dict", "List", "Set", "dict", "list", "set")

# Issue #380: Pre-compiled regex patterns for hardcode detection
_IP_ADDRESS_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
_URL_IN_QUOTES_RE = re.compile(r'[\'"`](https?://[^\'"` ]+)[\'"`]')
_PORT_NUMBER_RE = re.compile(r"\b(80[0-9][0-9]|[1-9][0-9]{3,4})\b")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Issue #398: Pre-compiled regex patterns for JS/Vue analysis
_JS_FUNCTION_RE = re.compile(
    r"(?:function\s+(\w+)|(\w+)\s*[:=]\s*(?:async\s+)?function|"
    r"\b(\w+)\s*\(.*?\)\s*\{|const\s+(\w+)\s*=\s*\(.*?\)\s*=>)"
)
_JS_API_PATH_RE = re.compile(r'[\'"`](/api/[^\'"` ]+)[\'"`]')

# Issue #380: Module-level frozensets for file operation safety patterns
_LOG_INDICATORS = frozenset({"log", "logs", ".log", "logging", "debug", "trace"})
# nosec B108 - These are string patterns for detection, not actual temp directory usage
_TEMP_INDICATORS = frozenset(
    {"tmp", "temp", "tempfile", "temporary", "/tmp/"}
)  # nosec B108
_SAFE_FILE_TYPES = frozenset(
    {
        ".pid",
        ".lock",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".md",
        ".txt",
        ".csv",
        ".html",
        ".xml",
    }
)

# Issue #380: Module-level tuple for collection AST types
_COLLECTION_AST_TYPES = (ast.Dict, ast.List, ast.Set)

# Issue #380: Module-level tuple for local IP prefixes
_LOCAL_IP_PREFIXES = ("127.0.0.", "192.168.")

# Issue #380: Module-level tuple for definition types (functions + classes)
_DEFINITION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

# Issue #398: LLM prompt template for hardcode/debt detection
_LLM_HARDCODE_DEBT_PROMPT = """Analyze this {language} code and identify:
1. **Hardcoded values** that should be externalized
2. **Technical debt** patterns

HARDCODES to find:
- API keys, tokens, secrets (even if obfuscated)
- IP addresses, URLs, endpoints
- Magic numbers (numeric constants without clear meaning)
- Configuration values (timeouts, limits, thresholds)
- File paths, database names
- Business logic constants

TECHNICAL DEBT to find:
- TODO/FIXME/HACK comments indicating incomplete work
- Deprecated patterns or anti-patterns
- Code duplication or copy-paste code
- Overly complex functions (cognitive complexity)
- Missing error handling
- Temporary workarounds or commented-out code
- Hard-to-maintain patterns

Code snippet (from {file_path}):
```{language}
{code_snippet}
```

Return ONLY valid JSON with this EXACT format:
{{
  "hardcodes": [
    {{"type": "api_key|ip|url|magic_number|config|path", "value": "val",
      "line": 0, "reason": "explanation", "severity": "high|medium|low"}}
  ],
  "technical_debt": [
    {{"type": "todo|deprecated|duplication|complexity|error_handling",
      "line": 0, "description": "what's wrong", "impact": "high|medium|low",
      "suggestion": "how to fix"}}
  ]
}}

If none found, return: {{"hardcodes": [], "technical_debt": []}}
IMPORTANT: Return ONLY the JSON object, no other text."""


def _check_import_from_lock(node: ast.ImportFrom) -> Tuple[bool, bool]:
    """Check ImportFrom node for lock imports. (Issue #315 - extracted)"""
    names = {alias.name for alias in node.names}
    has_async = node.module == "asyncio" and bool(names & _ASYNCIO_LOCK_NAMES)
    has_threading = node.module == "threading" and bool(names & _THREADING_LOCK_NAMES)
    return has_async, has_threading


def _check_lock_imports(node: ast.AST) -> Tuple[bool, bool]:
    """
    Check if an AST node imports async or threading locks.

    Args:
        node: AST node to check

    Returns:
        Tuple of (has_async_lock, has_threading_lock)
    """
    if isinstance(node, ast.ImportFrom):
        return _check_import_from_lock(node)

    if isinstance(node, ast.Import):
        names = {alias.name for alias in node.names}
        has_both = bool(names & {"asyncio", "threading"})
        return has_both, has_both

    return False, False


def _is_mutable_constructor(value: ast.AST) -> bool:
    """
    Check if an AST value node creates a mutable type (dict, list, set).

    Args:
        value: AST node representing the assigned value

    Returns:
        True if the value creates a mutable type
    """
    if isinstance(
        value, _COLLECTION_AST_TYPES
    ):  # Issue #380: Use module-level constant
        return True

    if not isinstance(value, ast.Call):
        return False

    func_name = ""
    if isinstance(value.func, ast.Name):
        func_name = value.func.id
    elif isinstance(value.func, ast.Attribute):
        func_name = value.func.attr

    mutable_constructors = (
        "dict",
        "list",
        "set",
        "defaultdict",
        "OrderedDict",
        "Counter",
        "deque",
    )
    return func_name in mutable_constructors


def _process_assign_node(
    node: ast.Assign, global_vars: Dict[str, int], global_mutables: Set[str]
) -> None:
    """Process Assign node for global state extraction. (Issue #315 - extracted)"""
    for target in node.targets:
        if isinstance(target, ast.Name):
            global_vars[target.id] = node.lineno
            if _is_mutable_constructor(node.value):
                global_mutables.add(target.id)


def _process_ann_assign_node(
    node: ast.AnnAssign, global_vars: Dict[str, int], global_mutables: Set[str]
) -> None:
    """Process AnnAssign node for global state extraction. (Issue #315 - extracted)"""
    if not node.target or not isinstance(node.target, ast.Name):
        return
    var_name = node.target.id
    global_vars[var_name] = node.lineno

    # Check annotation for Dict, List, Set types
    if node.annotation:
        ann_str = ast.unparse(node.annotation) if hasattr(ast, "unparse") else ""
        if any(t in ann_str for t in _MUTABLE_TYPE_ANNOTATIONS):
            global_mutables.add(var_name)

    if node.value and isinstance(node.value, _COLLECTION_AST_TYPES):  # Issue #380
        global_mutables.add(var_name)


def _extract_global_state(tree: ast.AST) -> Tuple[Dict[str, int], Set[str]]:
    """
    Extract global variables and identify which are mutable from module-level assignments.

    Args:
        tree: Parsed AST tree

    Returns:
        Tuple of (global_vars dict mapping name to line number, set of mutable var names)
    """
    global_vars: Dict[str, int] = {}
    global_mutables: Set[str] = set()

    # Use extracted helpers (Issue #315 - reduced depth)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            _process_assign_node(node, global_vars, global_mutables)
        elif isinstance(node, ast.AnnAssign) and node.target:
            _process_ann_assign_node(node, global_vars, global_mutables)

    return global_vars, global_mutables


def _create_race_condition_problem(
    lineno: int,
    description: str,
    suggestion: str,
    severity: str = "high",
) -> Dict:
    """Create a standardized race condition problem dictionary."""
    return {
        "type": "race_condition",
        "severity": severity,
        "line": lineno,
        "description": description,
        "suggestion": suggestion,
    }


def _check_subscript_modification(
    stmt: ast.Assign,
    global_mutables: Set[str],
    global_declarations: Set[str],
    lock_protected_vars: Set[str],
    is_async: bool,
    func_name: str,
) -> Optional[Dict]:
    """
    Check for unprotected subscript assignments to global mutables.

    Example: global_dict[key] = value (without lock protection)
    """
    for target in stmt.targets:
        if not isinstance(target, ast.Subscript):
            continue
        if not isinstance(target.value, ast.Name):
            continue

        var_name = target.value.id
        is_global = var_name in global_mutables or var_name in global_declarations
        if not is_global or var_name in lock_protected_vars:
            continue

        lock_type = "asyncio.Lock()" if is_async else "threading.Lock()"
        async_prefix = "async " if is_async else ""
        return _create_race_condition_problem(
            lineno=stmt.lineno,
            description=(
                f"Unprotected modification of global '{var_name}' "
                f"in {async_prefix}function '{func_name}'"
            ),
            suggestion=f"Use {lock_type} to protect concurrent access to '{var_name}'",
        )
    return None


def _check_mutating_method_call(
    stmt: ast.Expr,
    global_mutables: Set[str],
    global_declarations: Set[str],
    lock_protected_vars: Set[str],
    is_async: bool,
    func_name: str,
) -> Optional[Dict]:
    """
    Check for unprotected mutating method calls on global mutables.

    Example: global_list.append(item) (without lock protection)
    """
    if not isinstance(stmt.value, ast.Call):
        return None

    call = stmt.value
    if not isinstance(call.func, ast.Attribute):
        return None
    if not isinstance(call.func.value, ast.Name):
        return None

    var_name = call.func.value.id
    method_name = call.func.attr

    mutating_methods = {
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "clear",
        "update",
        "setdefault",
        "add",
        "discard",
        "difference_update",
        "intersection_update",
        "symmetric_difference_update",
    }

    is_global = var_name in global_mutables or var_name in global_declarations
    if not is_global or method_name not in mutating_methods:
        return None
    if var_name in lock_protected_vars:
        return None

    lock_type = "asyncio.Lock()" if is_async else "threading.Lock()"
    async_prefix = "async " if is_async else ""
    return _create_race_condition_problem(
        lineno=stmt.lineno,
        description=(
            f"Unprotected '{method_name}()' on global '{var_name}' "
            f"in {async_prefix}function '{func_name}'"
        ),
        suggestion=f"Use {lock_type} to protect concurrent modifications",
    )


def _check_lazy_init_pattern(
    stmt: ast.If,
    global_vars: Dict[str, int],
) -> Optional[Dict]:
    """
    Check for thread-unsafe lazy initialization patterns.

    Example: if _instance is None: _instance = SomeClass()
    """
    if not isinstance(stmt.test, ast.Compare):
        return None
    if len(stmt.test.ops) != 1 or not isinstance(stmt.test.ops[0], ast.Is):
        return None
    if not isinstance(stmt.test.left, ast.Name):
        return None

    var_name = stmt.test.left.id
    if not var_name.startswith("_") or var_name not in global_vars:
        return None

    # Check if body assigns to this variable
    for body_stmt in stmt.body:
        if not isinstance(body_stmt, ast.Assign):
            continue
        for target in body_stmt.targets:
            if isinstance(target, ast.Name) and target.id == var_name:
                return _create_race_condition_problem(
                    lineno=stmt.lineno,
                    description=(
                        f"Thread-unsafe lazy initialization of '{var_name}' - "
                        f"multiple threads may create multiple instances"
                    ),
                    suggestion="Use a lock or implement proper double-checked locking pattern",
                )
    return None


# Issue #620: Module-level sets for safe file write context detection
_SAFE_FILE_WRITE_CONTEXTS = frozenset(
    {
        "scripts/",
        "test",
        "setup",
        "init",
        "install",
        "deploy",
        "archive",
        "backup",
        "migration",
        "fixture",
        "mock",
    }
)

_SAFE_FUNC_NAME_INDICATORS = frozenset(
    {
        "init",
        "setup",
        "configure",
        "install",
        "migrate",
        "backup",
        "export",
        "save_config",
        "write_config",
        "dump",
        "serialize",
    }
)


def _is_safe_target_file(target_file: str) -> bool:
    """
    Check if target file name indicates a safe write context.

    Checks for log files, temp files, and common non-concurrent file types.
    Issue #620.
    """
    # Safe pattern 1: Log files (typically single-writer or properly managed)
    if any(ind in target_file for ind in _LOG_INDICATORS):
        return True
    # Safe pattern 2: Temp files (typically unique names)
    if any(ind in target_file for ind in _TEMP_INDICATORS):
        return True
    # Safe pattern 3: Common non-concurrent file types
    if any(target_file.endswith(ext) for ext in _SAFE_FILE_TYPES):
        return True
    return False


def _is_safe_file_path_context(file_path: str) -> bool:
    """
    Check if source file path indicates a safe write context.

    Checks for scripts, tests, setup, and other non-concurrent contexts.
    Issue #620.
    """
    file_path_lower = file_path.lower()
    return any(ctx in file_path_lower for ctx in _SAFE_FILE_WRITE_CONTEXTS)


def _is_safe_function_name(func_name: str) -> bool:
    """
    Check if function name indicates a safe write context.

    Checks for init, setup, configure, and other non-concurrent function names.
    Issue #620.
    """
    func_name_lower = func_name.lower()
    return any(safe in func_name_lower for safe in _SAFE_FUNC_NAME_INDICATORS)


def _is_safe_file_write_context(
    target_file: str,
    mode_str: str,
    file_path: str,
    func_name: str,
) -> bool:
    """
    Check if a file write operation is in a safe context that doesn't need locking.

    Issue #281: Extracted helper to reduce complexity in _check_file_write_without_lock.
    Issue #378: Consolidated safe pattern checks.
    Issue #620: Refactored to use extracted helper functions.

    Args:
        target_file: The file being written to (lowercased)
        mode_str: File open mode string
        file_path: Source file path containing the code
        func_name: Name of the function containing the write

    Returns:
        True if the write is in a safe context, False otherwise
    """
    # Check target file name patterns
    if _is_safe_target_file(target_file):
        return True
    # Append mode is generally safer
    if "a" in mode_str:
        return True
    # Check source file path context
    if _is_safe_file_path_context(file_path):
        return True
    # Check function name context
    if _is_safe_function_name(func_name):
        return True
    return False


def _check_file_write_without_lock(
    stmt: ast.With, file_path: str = "", func_name: str = ""
) -> Optional[Dict]:
    """
    Check for file writes without explicit locking.

    Issue #378: Refined to reduce false positives for common safe patterns:
    - Log files (typically single-writer or append-only)
    - Config/temp files with unique names
    - Files in non-concurrent contexts (scripts, tests, init)
    - Append mode (safer than write mode)

    Example: with open(path, 'w', encoding="utf-8") as f: ... (without file lock)
    """
    for item in stmt.items:
        if not isinstance(item.context_expr, ast.Call):
            continue

        call = item.context_expr
        if not isinstance(call.func, ast.Name) or call.func.id != "open":
            continue
        if len(call.args) < 2:
            continue

        mode_arg = call.args[1]
        if not isinstance(mode_arg, ast.Constant):
            continue
        mode_str = str(mode_arg.value)
        if "w" not in mode_str:
            continue

        # Issue #378: Check for safe patterns that don't need locking
        # Get the file path argument if it's a constant or has a name
        file_arg = call.args[0] if call.args else None
        target_file = ""
        if isinstance(file_arg, ast.Constant):
            target_file = str(file_arg.value).lower()
        elif isinstance(file_arg, ast.Name):
            target_file = file_arg.id.lower()

        # Issue #281: Use extracted helper for all safe pattern checks
        if _is_safe_file_write_context(target_file, mode_str, file_path, func_name):
            return None

        # This is a potentially risky file write - flag it
        return _create_race_condition_problem(
            lineno=stmt.lineno,
            description=(
                "File opened for writing without explicit locking - "
                "concurrent writes may corrupt data"
            ),
            suggestion="Use file locking (fcntl.flock) or a separate lock for file access",
            severity="medium",
        )
    return None


def _find_global_declarations(func_node: ast.AST) -> Set[str]:
    """
    Find all global keyword declarations within a function.

    Issue #620.
    """
    declarations: Set[str] = set()
    for stmt in ast.walk(func_node):
        if isinstance(stmt, ast.Global):
            declarations.update(stmt.names)
    return declarations


def _check_statement_for_global_modification(
    stmt: ast.AST,
    global_mutables: Set[str],
    global_declarations: Set[str],
    lock_protected_vars: Set[str],
    is_async: bool,
    func_name: str,
) -> Optional[Dict]:
    """
    Check a single statement for unprotected global modifications.

    Issue #620.
    """
    if isinstance(stmt, ast.Assign):
        return _check_subscript_modification(
            stmt,
            global_mutables,
            global_declarations,
            lock_protected_vars,
            is_async,
            func_name,
        )
    if isinstance(stmt, ast.Expr):
        return _check_mutating_method_call(
            stmt,
            global_mutables,
            global_declarations,
            lock_protected_vars,
            is_async,
            func_name,
        )
    return None


def _detect_global_state_modifications(
    func_node: ast.AST,
    global_vars: Dict[str, int],
    global_mutables: Set[str],
    lock_protected_vars: Set[str],
) -> List[Dict]:
    """
    Detect modifications to global state within a function.

    Issue #620: Refactored with extracted helper functions.
    """
    problems = []
    is_async = isinstance(func_node, ast.AsyncFunctionDef)
    func_name = func_node.name
    global_declarations = _find_global_declarations(func_node)

    for stmt in ast.walk(func_node):
        problem = _check_statement_for_global_modification(
            stmt,
            global_mutables,
            global_declarations,
            lock_protected_vars,
            is_async,
            func_name,
        )
        if problem:
            problems.append(problem)

    return problems


def _detect_singleton_patterns(
    func_node: ast.AST,
    global_vars: Dict[str, int],
) -> List[Dict]:
    """
    Detect thread-unsafe singleton/lazy initialization patterns.

    Args:
        func_node: Function AST node
        global_vars: Dict of global variable names to line numbers

    Returns:
        List of race condition problems found
    """
    problems = []
    for stmt in ast.walk(func_node):
        if isinstance(stmt, ast.If):
            problem = _check_lazy_init_pattern(stmt, global_vars)
            if problem:
                problems.append(problem)
    return problems


def _detect_augmented_assignment_issues(
    func_node: ast.AST,
    global_vars: Dict[str, int],
) -> List[Dict]:
    """
    Detect read-modify-write patterns on global variables.

    Example: counter += 1 (not atomic)
    """
    problems = []

    for stmt in ast.walk(func_node):
        if not isinstance(stmt, ast.AugAssign):
            continue

        target = stmt.target
        var_name = None

        if isinstance(target, ast.Name):
            var_name = target.id
        elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
            var_name = target.value.id

        if var_name and var_name in global_vars:
            problems.append(
                _create_race_condition_problem(
                    lineno=stmt.lineno,
                    description=(
                        f"Read-modify-write on global '{var_name}' is not atomic - "
                        f"can cause lost updates under concurrency"
                    ),
                    suggestion="Use atomic operations or protect with a lock",
                )
            )

    return problems


def _detect_file_handle_issues(func_node: ast.AST, file_path: str = "") -> List[Dict]:
    """Detect shared file handles without locks.

    Issue #378: Now passes file_path and func_name for context-aware detection.
    """
    problems = []
    func_name = getattr(func_node, "name", "")
    for stmt in ast.walk(func_node):
        if isinstance(stmt, ast.With):
            problem = _check_file_write_without_lock(stmt, file_path, func_name)
            if problem:
                problems.append(problem)
    return problems


# =============================================================================
# End of Race Condition Helper Functions
# =============================================================================


# =============================================================================
# Python File Analysis Helper Functions (Issue #298 - Reduce Deep Nesting)
# =============================================================================


def _extract_function_info(node: ast.FunctionDef) -> Dict:
    """Extract function information from AST node."""
    return {
        "name": node.name,
        "line": node.lineno,
        "args": [arg.arg for arg in node.args.args],
        "docstring": ast.get_docstring(node),
        "is_async": isinstance(node, ast.AsyncFunctionDef),
    }


def _check_long_function(node: ast.FunctionDef) -> Optional[Dict]:
    """Check if function exceeds 50 lines and return problem if so."""
    if not hasattr(node, "end_lineno") or not node.end_lineno:
        return None

    func_length = node.end_lineno - node.lineno
    if func_length <= 50:
        return None

    return {
        "type": "long_function",
        "severity": "medium",
        "line": node.lineno,
        "description": f"Function '{node.name}' is {func_length} lines long",
        "suggestion": "Consider breaking into smaller functions",
    }


def _extract_class_info(node: ast.ClassDef) -> Dict:
    """Extract class information from AST node."""
    return {
        "name": node.name,
        "line": node.lineno,
        "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)],
        "docstring": ast.get_docstring(node),
    }


def _check_hardcoded_ip(ip: str, line_num: int, line_content: str) -> Optional[Dict]:
    """Check if IP address is a known infrastructure IP."""
    # Issue #380: Use module-level constant for local IP prefixes
    if not (
        ip.startswith(NetworkConstants.VM_IP_PREFIX)
        or ip.startswith(_LOCAL_IP_PREFIXES)
    ):
        return None

    return {
        "type": "ip",
        "value": ip,
        "line": line_num,
        "context": line_content.strip(),
    }


def _check_hardcoded_port(
    port: str, line_num: int, line_content: str
) -> Optional[Dict]:
    """Check if port is a known infrastructure port."""
    known_ports = [
        str(NetworkConstants.BACKEND_PORT),
        str(NetworkConstants.AI_STACK_PORT),
        str(NetworkConstants.REDIS_PORT),
        str(NetworkConstants.OLLAMA_PORT),
        str(NetworkConstants.FRONTEND_PORT),
        str(NetworkConstants.BROWSER_SERVICE_PORT),
    ]

    if port not in known_ports:
        return None

    return {
        "type": "port",
        "value": port,
        "line": line_num,
        "context": line_content.strip(),
    }


def _detect_hardcodes_in_line(line_num: int, line: str) -> List[Dict]:
    """Detect hardcoded values in a single line of code."""
    hardcodes = []

    # Check for IP addresses
    ip_matches = _IP_ADDRESS_RE.findall(line)
    for ip in ip_matches:
        result = _check_hardcoded_ip(ip, line_num, line)
        if result:
            hardcodes.append(result)

    # Check for URLs
    url_matches = _URL_IN_QUOTES_RE.findall(line)
    for url in url_matches:
        hardcodes.append(
            {"type": "url", "value": url, "line": line_num, "context": line.strip()}
        )

    # Check for ports
    port_matches = _PORT_NUMBER_RE.findall(line)
    for port in port_matches:
        result = _check_hardcoded_port(port, line_num, line)
        if result:
            hardcodes.append(result)

    return hardcodes


def _detect_technical_debt_in_line(
    line_num: int, line: str, file_path: str
) -> Tuple[List[Dict], List[Dict]]:
    """Detect technical debt markers in a line. Returns (debt_items, problem_items)."""
    debt_patterns = [
        # Require colon after keyword to avoid false positives (Issue #617)
        # e.g., "# TODO: fix this" matches, but "# Todo list" does not
        (r"#\s*TODO:\s*(.+)$", "todo", "low"),
        (r"#\s*FIXME:\s*(.+)$", "fixme", "medium"),
        (r"#\s*HACK:\s*(.+)$", "hack", "high"),
        (r"#\s*XXX:\s*(.+)$", "xxx", "medium"),
        (r"#\s*BUG:\s*(.+)$", "bug", "high"),
        (r"#\s*DEPRECATED:\s*(.+)$", "deprecated", "medium"),
    ]

    debt_items = []
    problem_items = []

    for pattern, debt_type, severity in debt_patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if not match:
            continue

        description = match.group(1).strip() if match.group(1) else ""

        debt_items.append(
            {
                "type": debt_type,
                "severity": severity,
                "line": line_num,
                "description": description[:200],
                "file_path": file_path,
            }
        )

        problem_items.append(
            {
                "type": f"technical_debt_{debt_type}",
                "severity": severity,
                "line": line_num,
                "description": f"{debt_type.upper()}: {description[:100]}",
                "suggestion": f"Address this {debt_type.upper()} comment",
            }
        )

    return debt_items, problem_items


def _run_anti_pattern_analysis(file_path: str) -> List[Dict]:
    """Run anti-pattern detection (Issue #398: extracted, Issue #662: thread-safe)."""
    global _anti_pattern_detector

    problems = []
    try:
        if _anti_pattern_detector is None:
            with _analyzers_lock:
                # Double-check after acquiring lock
                if _anti_pattern_detector is None:
                    _anti_pattern_detector = AntiPatternDetector()
        result = _anti_pattern_detector.analyze_file(file_path)
        for pattern in result.get("patterns", []):
            problems.append(
                {
                    "type": f"code_smell_{pattern.pattern_type.value}",
                    "severity": pattern.severity.value,
                    "line": pattern.line_number,
                    "description": pattern.description,
                    "suggestion": pattern.suggestion,
                }
            )
    except Exception as e:
        logger.debug("Anti-pattern detection skipped for %s: %s", file_path, e)
    return problems


def _run_performance_analysis(file_path: str) -> List[Dict]:
    """Run performance analysis (Issue #398: extracted, Issue #662: thread-safe)."""
    global _performance_analyzer

    problems = []
    try:
        if _performance_analyzer is None:
            with _analyzers_lock:
                # Double-check after acquiring lock
                if _performance_analyzer is None:
                    _performance_analyzer = PerformanceAnalyzer()
        perf_issues = _performance_analyzer.analyze_file(file_path)
        for issue in perf_issues:
            problems.append(
                {
                    "type": f"performance_{issue.issue_type.value}",
                    "severity": issue.severity.value,
                    "line": issue.line_start,
                    "description": issue.description,
                    "suggestion": issue.recommendation,
                }
            )
    except Exception as e:
        logger.debug("Performance analysis skipped for %s: %s", file_path, e)
    return problems


def _run_bug_prediction(file_path: str) -> List[Dict]:
    """Run bug prediction analysis (Issue #398: extracted, Issue #662: thread-safe)."""
    global _bug_predictor

    problems = []
    try:
        if _bug_predictor is None:
            with _analyzers_lock:
                # Double-check after acquiring lock
                if _bug_predictor is None:
                    project_root = Path(file_path).parent
                    while project_root.parent != project_root:
                        if (project_root / ".git").exists():
                            break
                        project_root = project_root.parent
                    _bug_predictor = BugPredictor(str(project_root))

        risk_assessment = _bug_predictor.analyze_file(file_path)
        if risk_assessment.overall_risk >= 70:
            severity = "high" if risk_assessment.overall_risk >= 85 else "medium"
            suggestion = (
                "; ".join(risk_assessment.recommendations[:3])
                if risk_assessment.recommendations
                else "Review code complexity"
            )
            problems.append(
                {
                    "type": "bug_prediction_high_risk",
                    "severity": severity,
                    "line": 1,
                    "description": (
                        f"High bug risk score: {risk_assessment.overall_risk:.0f}/100. "
                        f"Risk level: {risk_assessment.risk_level.value}"
                    ),
                    "suggestion": suggestion,
                }
            )
    except Exception as e:
        logger.debug("Bug prediction skipped for %s: %s", file_path, e)
    return problems


def _run_code_intelligence_analyzers(file_path: str) -> List[Dict]:
    """Run code intelligence analyzers (Issue #398: refactored)."""
    if not _analyzers_available:
        return []

    problems = []
    problems.extend(_run_anti_pattern_analysis(file_path))
    problems.extend(_run_performance_analysis(file_path))
    problems.extend(_run_bug_prediction(file_path))
    return problems


def _create_empty_analysis_result() -> Metadata:
    """Create an empty analysis result for error cases."""
    return {
        "functions": [],
        "classes": [],
        "imports": [],
        "hardcodes": [],
        "problems": [],
        "technical_debt": [],
        "line_count": 0,
        "code_lines": 0,
        "comment_lines": 0,
        "docstring_lines": 0,
        "blank_lines": 0,
    }


def _extract_docstring_lines(first_stmt: ast.AST) -> Set[int]:
    """Extract line numbers for a docstring statement (Issue #315: extracted helper)."""
    if not isinstance(first_stmt, ast.Expr):
        return set()
    if not isinstance(first_stmt.value, ast.Constant):
        return set()
    if not isinstance(first_stmt.value.value, str):
        return set()
    end_line = first_stmt.end_lineno or first_stmt.lineno
    return set(range(first_stmt.lineno, end_line + 1))


def _find_all_docstring_lines(tree: ast.AST) -> Set[int]:
    """Find all docstring line numbers in AST (Issue #315: extracted helper)."""
    docstring_lines: Set[int] = set()

    for node in ast.walk(tree):
        # Check module-level docstring
        if isinstance(node, ast.Module) and node.body:
            docstring_lines.update(_extract_docstring_lines(node.body[0]))

        # Check function/class docstrings
        if isinstance(node, _DEFINITION_TYPES) and node.body:  # Issue #380
            docstring_lines.update(_extract_docstring_lines(node.body[0]))

    return docstring_lines


def _count_python_line_types(content: str, tree: ast.AST) -> Dict[str, int]:
    """
    Count different line types in Python code (Issue #368).
    Issue #315: Refactored with extracted helpers to reduce nesting.

    Distinguishes between:
    - code_lines: Lines containing executable code
    - comment_lines: Lines that are pure comments (# ...)
    - docstring_lines: Lines inside docstrings
    - blank_lines: Empty or whitespace-only lines

    Args:
        content: Full file content as string
        tree: Parsed AST tree

    Returns:
        Dict with line_count, code_lines, comment_lines, docstring_lines, blank_lines
    """
    lines = content.splitlines()
    total_lines = len(lines)

    docstring_line_numbers = _find_all_docstring_lines(tree)

    blank_lines = 0
    comment_lines = 0
    docstring_lines = len(docstring_line_numbers)

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip if this line is part of a docstring
        if i in docstring_line_numbers:
            continue

        # Check for blank lines
        if not stripped:
            blank_lines += 1
            continue

        # Check for pure comment lines (not inline comments)
        if stripped.startswith("#"):
            comment_lines += 1

    # Code lines = total - comments - docstrings - blanks
    code_lines = total_lines - comment_lines - docstring_lines - blank_lines

    return {
        "line_count": total_lines,
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "docstring_lines": docstring_lines,
        "blank_lines": blank_lines,
    }


def _classify_js_line(stripped: str, in_multiline_comment: bool) -> Tuple[str, bool]:
    """
    Classify a single JS/Vue line and track multiline comment state.

    Returns:
        Tuple of (line_type, new_multiline_state) where line_type is
        'blank', 'comment', or 'code'.
    Issue #620.
    """
    # Check for blank lines
    if not stripped:
        return "blank", in_multiline_comment

    # Handle multi-line comments /* */
    if in_multiline_comment:
        new_state = "*/" not in stripped
        return "comment", new_state

    # Check for start of multi-line comment
    if stripped.startswith("/*"):
        new_state = "*/" not in stripped
        return "comment", new_state

    # Check for single-line comments
    if stripped.startswith("//"):
        return "comment", False

    # Check for HTML comments in Vue files
    if stripped.startswith("<!--"):
        return "comment", False

    return "code", False


def _count_js_vue_line_types(content: str) -> Dict[str, int]:
    """
    Count different line types in JavaScript/Vue code (Issue #368).
    Issue #620: Refactored with extracted helper function.

    Args:
        content: Full file content as string

    Returns:
        Dict with line_count, code_lines, comment_lines, docstring_lines, blank_lines
    """
    lines = content.splitlines()
    total_lines = len(lines)

    blank_lines = 0
    comment_lines = 0
    in_multiline_comment = False

    for line in lines:
        stripped = line.strip()
        line_type, in_multiline_comment = _classify_js_line(
            stripped, in_multiline_comment
        )
        if line_type == "blank":
            blank_lines += 1
        elif line_type == "comment":
            comment_lines += 1

    code_lines = total_lines - comment_lines - blank_lines

    return {
        "line_count": total_lines,
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "docstring_lines": 0,  # JS doesn't have docstrings
        "blank_lines": blank_lines,
    }


async def _merge_llm_results(
    hardcodes: List[Dict],
    technical_debt: List[Dict],
    content: str,
    file_path: str,
) -> None:
    """Merge LLM analysis results into existing hardcodes and technical debt lists."""
    try:
        llm_results = await detect_hardcodes_and_debt_with_llm(
            content, file_path, language="python"
        )

        # Merge LLM hardcodes (avoid duplicates)
        existing_values = {h.get("value") for h in hardcodes}
        for llm_hardcode in llm_results.get("hardcodes", []):
            if llm_hardcode.get("value") not in existing_values:
                hardcodes.append(llm_hardcode)

        # Add technical debt from LLM
        technical_debt.extend(llm_results.get("technical_debt", []))

    except Exception as e:
        logger.debug("LLM analysis skipped for %s: %s", file_path, e)


def _extract_imports_from_node(node: ast.AST) -> List[str]:
    """Extract import names from an import AST node."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        return [node.module or ""]
    return []


def _analyze_ast_nodes(
    tree: ast.AST,
) -> Tuple[List[Dict], List[Dict], List[str], List[Dict]]:
    """
    Walk AST and extract functions, classes, imports, and long function problems.

    Returns:
        Tuple of (functions, classes, imports, problems)
    """
    functions = []
    classes = []
    imports = []
    problems = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append(_extract_function_info(node))
            long_func_problem = _check_long_function(node)
            if long_func_problem:
                problems.append(long_func_problem)

        elif isinstance(node, ast.ClassDef):
            classes.append(_extract_class_info(node))

        elif isinstance(node, _IMPORT_TYPES):  # Issue #380
            imports.extend(_extract_imports_from_node(node))

    return functions, classes, imports, problems


def _analyze_content_lines(
    content: str, file_path: str
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Analyze content line-by-line for hardcodes and technical debt.

    Returns:
        Tuple of (hardcodes, technical_debt, problems)
    """
    hardcodes = []
    technical_debt = []
    problems = []

    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        # Detect hardcoded values
        hardcodes.extend(_detect_hardcodes_in_line(i, line))

        # Detect technical debt
        debt_items, problem_items = _detect_technical_debt_in_line(i, line, file_path)
        technical_debt.extend(debt_items)
        problems.extend(problem_items)

    return hardcodes, technical_debt, problems


# =============================================================================
# End of Python File Analysis Helper Functions
# =============================================================================


def _parse_llm_json_response(result_text: str) -> Optional[Dict]:
    """Parse JSON from LLM response text (Issue #398: extracted)."""
    if result_text.startswith("{") and result_text.endswith("}"):
        return json.loads(result_text)
    # Try to find JSON object in response
    json_match = _JSON_OBJECT_RE.search(result_text)
    if json_match:
        return json.loads(json_match.group())
    return None


async def detect_hardcodes_and_debt_with_llm(
    code_snippet: str, file_path: str, language: str = "python"
) -> Dict[str, List[Metadata]]:
    """
    Use LLM to detect semantic hardcodes and technical debt (Issue #398: refactored).

    Returns:
        Dictionary with 'hardcodes' and 'technical_debt' keys
    """
    empty_result: Dict[str, List[Metadata]] = {"hardcodes": [], "technical_debt": []}
    try:
        llm = LLMInterface()
        prompt = _LLM_HARDCODE_DEBT_PROMPT.format(
            language=language, file_path=file_path, code_snippet=code_snippet[:800]
        )
        messages = [{"role": "user", "content": prompt}]
        response = await llm.chat_completion(messages, llm_type="task")
        result = _parse_llm_json_response(response.content.strip())
        return result if result else empty_result
    except Exception as e:
        logger.debug("LLM analysis failed for %s: %s", file_path, e)
        return empty_result


def _check_async_global_state_issue(
    node: ast.AsyncFunctionDef, has_async_lock_import: bool
) -> Optional[Dict]:
    """
    Check if async function uses global state without lock import.

    Issue #620.
    """
    uses_global = any(isinstance(stmt, ast.Global) for stmt in ast.walk(node))
    if uses_global and not has_async_lock_import:
        return _create_race_condition_problem(
            lineno=node.lineno,
            description=(
                f"Async function '{node.name}' uses global state "
                f"but no asyncio.Lock imported"
            ),
            suggestion=(
                "Consider using asyncio.Lock() to protect shared state in async context"
            ),
            severity="medium",
        )
    return None


def _analyze_function_for_race_conditions(
    node: ast.AST,
    global_vars: Dict[str, int],
    global_mutables: Set[str],
    lock_protected_vars: Set[str],
    has_async_lock_import: bool,
    file_path: str,
) -> List[Dict]:
    """
    Analyze a single function for race condition issues.

    Issue #620.
    """
    problems = []

    # Check for global state modifications
    problems.extend(
        _detect_global_state_modifications(
            node, global_vars, global_mutables, lock_protected_vars
        )
    )

    # Check for thread-unsafe singleton patterns
    problems.extend(_detect_singleton_patterns(node, global_vars))

    # Check for async functions modifying shared state
    if isinstance(node, ast.AsyncFunctionDef):
        async_problem = _check_async_global_state_issue(node, has_async_lock_import)
        if async_problem:
            problems.append(async_problem)

    # Check for read-modify-write patterns
    problems.extend(_detect_augmented_assignment_issues(node, global_vars))

    # Check for shared file handles
    problems.extend(_detect_file_handle_issues(node, file_path))

    return problems


def detect_race_conditions(tree: ast.AST, content: str, file_path: str) -> List[Dict]:
    """
    Detect potential race conditions in Python code.

    Refactored for Issue #298 and Issue #620.
    """
    problems: List[Dict] = []
    lock_protected_vars: Set[str] = set()
    has_async_lock_import = False

    # Pass 1: Check for lock imports
    for node in ast.walk(tree):
        async_lock, _ = _check_lock_imports(node)
        has_async_lock_import = has_async_lock_import or async_lock

    # Pass 2: Extract global state
    global_vars, global_mutables = _extract_global_state(tree)

    # Pass 3: Analyze functions for race conditions
    for node in ast.walk(tree):
        if isinstance(node, _FUNCTION_DEF_TYPES):
            problems.extend(
                _analyze_function_for_race_conditions(
                    node,
                    global_vars,
                    global_mutables,
                    lock_protected_vars,
                    has_async_lock_import,
                    file_path,
                )
            )

    return problems


async def analyze_python_file(file_path: str, use_llm: bool = False) -> Metadata:
    """
    Analyze a Python file for functions, classes, and potential issues.

    Refactored for Issue #298 - reduced nesting from 9 to 3 levels max.
    Issue #620 - further refactored with extracted helper functions.
    """
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        tree = ast.parse(content)
        return await _run_analysis_phases(file_path, content, tree, use_llm)

    except OSError as e:
        logger.error("Failed to read Python file %s: %s", file_path, e)
        return _create_empty_analysis_result()

    except Exception as e:
        logger.error("Error analyzing Python file %s: %s", file_path, e)
        return _create_parse_error_result(str(e))


def _extract_js_functions(line: str, line_num: int) -> List[Dict]:
    """Extract function definitions from a JS/Vue line (Issue #398: extracted)."""
    functions = []
    for match in _JS_FUNCTION_RE.findall(line):
        func_name = next((name for name in match if name), None)
        if func_name and not func_name.startswith("_"):
            functions.append({"name": func_name, "line": line_num, "type": "function"})
    return functions


def _extract_js_hardcodes(line: str, line_num: int) -> List[Dict]:
    """Extract hardcoded values from a JS/Vue line (Issue #398: extracted)."""
    hardcodes = []
    context = line.strip()
    # URLs
    for url in _URL_IN_QUOTES_RE.findall(line):
        hardcodes.append(
            {"type": "url", "value": url, "line": line_num, "context": context}
        )
    # API paths
    for api_path in _JS_API_PATH_RE.findall(line):
        hardcodes.append(
            {
                "type": "api_path",
                "value": api_path,
                "line": line_num,
                "context": context,
            }
        )
    # IP addresses (only VM/local IPs)
    for ip in _IP_ADDRESS_RE.findall(line):
        if ip.startswith(NetworkConstants.VM_IP_PREFIX) or ip.startswith(
            _LOCAL_IP_PREFIXES
        ):
            hardcodes.append(
                {"type": "ip", "value": ip, "line": line_num, "context": context}
            )
    return hardcodes


def _check_js_console_log(line: str, line_num: int) -> Optional[Dict]:
    """Check for console.log debugging statements (Issue #398: extracted)."""
    if "console.log" in line and not line.strip().startswith("//"):
        return {
            "type": "debug_code",
            "severity": "low",
            "line": line_num,
            "description": "console.log statement found",
            "suggestion": "Remove debug statements before production",
        }
    return None


def _create_empty_js_analysis_result() -> Metadata:
    """Create empty JS/Vue analysis result (Issue #398: extracted)."""
    return {
        "functions": [],
        "classes": [],
        "imports": [],
        "hardcodes": [],
        "problems": [],
        "line_count": 0,
        "code_lines": 0,
        "comment_lines": 0,
        "docstring_lines": 0,
        "blank_lines": 0,
    }


def _create_parse_error_result(error_msg: str) -> Metadata:
    """
    Create analysis result with parse error problem.

    Issue #620.
    """
    result = _create_empty_analysis_result()
    result["problems"] = [
        {
            "type": "parse_error",
            "severity": "high",
            "line": 1,
            "description": f"Failed to parse file: {error_msg}",
            "suggestion": "Check syntax errors",
        }
    ]
    return result


async def _run_analysis_phases(
    file_path: str, content: str, tree: ast.AST, use_llm: bool
) -> Metadata:
    """
    Execute all analysis phases on parsed Python content.

    Issue #620.
    """
    # Phase 1: AST analysis (functions, classes, imports, long function problems)
    functions, classes, imports, problems = _analyze_ast_nodes(tree)

    # Phase 2: Line-by-line content analysis (hardcodes, technical debt)
    hardcodes, technical_debt, line_problems = _analyze_content_lines(
        content, file_path
    )
    problems.extend(line_problems)

    # Phase 3: LLM semantic analysis (optional)
    if use_llm:
        await _merge_llm_results(hardcodes, technical_debt, content, file_path)

    # Phase 4: Race condition detection
    try:
        race_problems = detect_race_conditions(tree, content, file_path)
        problems.extend(race_problems)
    except Exception as e:
        logger.debug("Race condition detection skipped for %s: %s", file_path, e)

    # Phase 5: Code intelligence analyzers
    # Issue #711: Run in thread pool to prevent event loop blocking.
    code_intel_problems = await asyncio.to_thread(
        _run_code_intelligence_analyzers, file_path
    )
    problems.extend(code_intel_problems)

    # Phase 6: Count line types (Issue #368)
    line_counts = _count_python_line_types(content, tree)

    return {
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "hardcodes": hardcodes,
        "problems": problems,
        "technical_debt": technical_debt,
        **line_counts,
    }


def analyze_javascript_vue_file(file_path: str) -> Metadata:
    """Analyze JavaScript/Vue file for functions and hardcodes (Issue #398: refactored)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        functions, hardcodes, problems = [], [], []
        for i, line in enumerate(content.splitlines(), 1):
            functions.extend(_extract_js_functions(line, i))
            hardcodes.extend(_extract_js_hardcodes(line, i))
            if problem := _check_js_console_log(line, i):
                problems.append(problem)

        line_counts = _count_js_vue_line_types(content)
        return {
            "functions": functions,
            "classes": [],
            "imports": [],
            "hardcodes": hardcodes,
            "problems": problems,
            **line_counts,
        }
    except Exception as e:
        logger.error("Error analyzing JS/Vue file %s: %s", file_path, e)
        return _create_empty_js_analysis_result()


def analyze_documentation_file(file_path: str) -> Metadata:
    """
    Analyze a documentation file (Markdown, RST, etc.) for line counts (Issue #367).

    Documentation files don't have code/comments/docstrings in the programming sense,
    so we count content lines vs blank lines.

    Returns:
        Dict with documentation_lines (content) and blank_lines
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.splitlines()
        total_lines = len(lines)

        blank_lines = 0
        for line in lines:
            if not line.strip():
                blank_lines += 1

        # For documentation, all non-blank lines are "documentation lines"
        documentation_lines = total_lines - blank_lines

        return {
            "line_count": total_lines,
            "documentation_lines": documentation_lines,
            "blank_lines": blank_lines,
            "is_documentation": True,
        }

    except Exception as e:
        logger.error("Error analyzing documentation file %s: %s", file_path, e)
        return {
            "line_count": 0,
            "documentation_lines": 0,
            "blank_lines": 0,
            "is_documentation": True,
        }
