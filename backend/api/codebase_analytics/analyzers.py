# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code analysis functions for codebase analytics
"""

import ast
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
from backend.type_defs.common import Metadata

from src.constants.network_constants import NetworkConstants
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)

# Code intelligence analyzers (Issue #268)
try:
    from src.code_intelligence.anti_pattern_detector import AntiPatternDetector
    from src.code_intelligence.performance_analyzer import PerformanceAnalyzer
    from src.code_intelligence.bug_predictor import BugPredictor

    _anti_pattern_detector: Optional[AntiPatternDetector] = None
    _performance_analyzer: Optional[PerformanceAnalyzer] = None
    _bug_predictor: Optional[BugPredictor] = None
    _analyzers_available = True
except ImportError as e:
    logger.warning(f"Code intelligence analyzers not available: {e}")
    _analyzers_available = False
    _anti_pattern_detector = None
    _performance_analyzer = None
    _bug_predictor = None


async def detect_hardcodes_and_debt_with_llm(
    code_snippet: str, file_path: str, language: str = "python"
) -> Dict[str, List[Metadata]]:
    """
    Use LLM to detect semantic hardcodes and technical debt that regex patterns might miss.

    Detects:
    - Obfuscated API keys/secrets
    - Magic numbers that should be constants
    - Configuration values that should be externalized
    - Business logic hardcodes
    - Technical debt patterns (TODO comments, deprecated patterns, code smells)
    - Semantic patterns beyond simple regex

    Returns:
        Dictionary with 'hardcodes' and 'technical_debt' keys
    """
    try:
        llm = LLMInterface()

        prompt = """Analyze this {language} code and identify:
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
{code_snippet[:800]}
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

        messages = [{"role": "user", "content": prompt}]
        response = await llm.chat_completion(messages, llm_type="task")
        result_text = response.content.strip()

        # Extract JSON from response
        if result_text.startswith("{") and result_text.endswith("}"):
            result = json.loads(result_text)
            return result
        else:
            # Try to find JSON object in response
            import re

            json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result

        return {"hardcodes": [], "technical_debt": []}

    except Exception as e:
        logger.debug(f"LLM analysis failed for {file_path}: {e}")
        return {"hardcodes": [], "technical_debt": []}


def detect_race_conditions(tree: ast.AST, content: str, file_path: str) -> List[Dict]:
    """
    Detect potential race conditions in Python code.

    Checks for:
    1. Global mutable state without locks
    2. Async shared state modifications
    3. Thread-unsafe singleton patterns
    4. Unprotected shared dictionary/list access
    5. Missing async locks for shared resources
    """
    problems = []
    lines = content.split("\n")

    # Track global variables and their types
    global_vars = {}
    global_mutables = set()  # Global mutable objects (dict, list, set)
    lock_protected_vars = set()  # Variables protected by locks
    has_async_lock_import = False
    has_threading_lock_import = False

    # First pass: identify imports and global state
    for node in ast.walk(tree):
        # Check for lock imports
        if isinstance(node, ast.ImportFrom):
            if node.module == "asyncio":
                for alias in node.names:
                    if alias.name in ("Lock", "Semaphore", "Event", "Condition"):
                        has_async_lock_import = True
            elif node.module == "threading":
                for alias in node.names:
                    if alias.name in ("Lock", "RLock", "Semaphore", "Event", "Condition"):
                        has_threading_lock_import = True

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("asyncio", "threading"):
                    has_async_lock_import = True
                    has_threading_lock_import = True

    # Second pass: find global assignments at module level
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    global_vars[var_name] = node.lineno

                    # Check if it's a mutable type
                    if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                        global_mutables.add(var_name)
                    elif isinstance(node.value, ast.Call):
                        # Check for dict(), list(), set(), defaultdict(), etc.
                        func_name = ""
                        if isinstance(node.value.func, ast.Name):
                            func_name = node.value.func.id
                        elif isinstance(node.value.func, ast.Attribute):
                            func_name = node.value.func.attr

                        if func_name in ("dict", "list", "set", "defaultdict", "OrderedDict",
                                        "Counter", "deque"):
                            global_mutables.add(var_name)

        elif isinstance(node, ast.AnnAssign) and node.target:
            if isinstance(node.target, ast.Name):
                var_name = node.target.id
                global_vars[var_name] = node.lineno

                # Check annotation for Dict, List, Set types
                if node.annotation:
                    ann_str = ast.unparse(node.annotation) if hasattr(ast, 'unparse') else ""
                    if any(t in ann_str for t in ("Dict", "List", "Set", "dict", "list", "set")):
                        global_mutables.add(var_name)

                if node.value and isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                    global_mutables.add(var_name)

    # Third pass: find modifications to global state in functions
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            func_name = node.name

            # Check for 'global' keyword usage
            global_declarations = set()
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Global):
                    global_declarations.update(stmt.names)

            # Check if function modifies global mutable state
            for stmt in ast.walk(node):
                # Check for subscript assignment (dict[key] = value, list[i] = value)
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Subscript):
                            if isinstance(target.value, ast.Name):
                                var_name = target.value.id
                                if var_name in global_mutables or var_name in global_declarations:
                                    # Check if this is inside a lock context
                                    if var_name not in lock_protected_vars:
                                        problems.append({
                                            "type": "race_condition",
                                            "severity": "high",
                                            "line": stmt.lineno,
                                            "description": (
                                                f"Unprotected modification of global '{var_name}' "
                                                f"in {'async ' if is_async else ''}function '{func_name}'"
                                            ),
                                            "suggestion": (
                                                f"Use {'asyncio.Lock()' if is_async else 'threading.Lock()'} "
                                                f"to protect concurrent access to '{var_name}'"
                                            ),
                                        })

                # Check for method calls on global mutables (.append, .update, .pop, etc.)
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if isinstance(call.func, ast.Attribute):
                        if isinstance(call.func.value, ast.Name):
                            var_name = call.func.value.id
                            method_name = call.func.attr
                            mutating_methods = {
                                "append", "extend", "insert", "remove", "pop", "clear",
                                "update", "setdefault", "add", "discard", "difference_update",
                                "intersection_update", "symmetric_difference_update"
                            }
                            if (var_name in global_mutables or var_name in global_declarations) \
                                    and method_name in mutating_methods:
                                if var_name not in lock_protected_vars:
                                    problems.append({
                                        "type": "race_condition",
                                        "severity": "high",
                                        "line": stmt.lineno,
                                        "description": (
                                            f"Unprotected '{method_name}()' on global '{var_name}' "
                                            f"in {'async ' if is_async else ''}function '{func_name}'"
                                        ),
                                        "suggestion": (
                                            f"Use {'asyncio.Lock()' if is_async else 'threading.Lock()'} "
                                            f"to protect concurrent modifications"
                                        ),
                                    })

    # Fourth pass: detect thread-unsafe singleton patterns
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Look for lazy initialization pattern without locks
            # Example: if _instance is None: _instance = SomeClass()
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.If):
                    # Check for "if var is None" pattern
                    if isinstance(stmt.test, ast.Compare):
                        if len(stmt.test.ops) == 1 and isinstance(stmt.test.ops[0], ast.Is):
                            if isinstance(stmt.test.left, ast.Name):
                                var_name = stmt.test.left.id
                                if var_name.startswith("_") and var_name in global_vars:
                                    # Check if body assigns to this variable
                                    for body_stmt in stmt.body:
                                        if isinstance(body_stmt, ast.Assign):
                                            for target in body_stmt.targets:
                                                if isinstance(target, ast.Name) and target.id == var_name:
                                                    problems.append({
                                                        "type": "race_condition",
                                                        "severity": "high",
                                                        "line": stmt.lineno,
                                                        "description": (
                                                            f"Thread-unsafe lazy initialization of '{var_name}' - "
                                                            f"multiple threads may create multiple instances"
                                                        ),
                                                        "suggestion": (
                                                            "Use a lock or implement proper double-checked locking pattern"
                                                        ),
                                                    })

    # Fifth pass: detect async functions modifying shared state without await
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            # Check for shared state modifications that should use async primitives
            uses_global = False
            has_await_in_critical = False

            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Global):
                    uses_global = True

            if uses_global and not has_async_lock_import:
                problems.append({
                    "type": "race_condition",
                    "severity": "medium",
                    "line": node.lineno,
                    "description": (
                        f"Async function '{node.name}' uses global state but no asyncio.Lock imported"
                    ),
                    "suggestion": (
                        "Consider using asyncio.Lock() to protect shared state in async context"
                    ),
                })

    # Sixth pass: detect read-modify-write patterns
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)

            for stmt in ast.walk(node):
                # Check for augmented assignment on globals (x += 1, dict[k] += 1)
                if isinstance(stmt, ast.AugAssign):
                    target = stmt.target
                    var_name = None

                    if isinstance(target, ast.Name):
                        var_name = target.id
                    elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                        var_name = target.value.id

                    if var_name and var_name in global_vars:
                        problems.append({
                            "type": "race_condition",
                            "severity": "high",
                            "line": stmt.lineno,
                            "description": (
                                f"Read-modify-write on global '{var_name}' is not atomic - "
                                f"can cause lost updates under concurrency"
                            ),
                            "suggestion": (
                                "Use atomic operations or protect with a lock"
                            ),
                        })

    # Seventh pass: detect shared file handles without locks
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.With):
                    for item in stmt.items:
                        if isinstance(item.context_expr, ast.Call):
                            call = item.context_expr
                            if isinstance(call.func, ast.Name) and call.func.id == "open":
                                # Check if writing to a file that might be shared
                                if len(call.args) >= 2:
                                    mode_arg = call.args[1]
                                    if isinstance(mode_arg, ast.Constant) and "w" in str(mode_arg.value):
                                        problems.append({
                                            "type": "race_condition",
                                            "severity": "medium",
                                            "line": stmt.lineno,
                                            "description": (
                                                "File opened for writing without explicit locking - "
                                                "concurrent writes may corrupt data"
                                            ),
                                            "suggestion": (
                                                "Use file locking (fcntl.flock) or a separate lock for file access"
                                            ),
                                        })

    return problems


async def analyze_python_file(file_path: str, use_llm: bool = False) -> Metadata:
    """Analyze a Python file for functions, classes, and potential issues"""
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        tree = ast.parse(content)

        functions = []
        classes = []
        imports = []
        hardcodes = []
        problems = []
        technical_debt = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "args": [arg.arg for arg in node.args.args],
                        "docstring": ast.get_docstring(node),
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                    }
                )

                # Check for long functions
                if hasattr(node, "end_lineno") and node.end_lineno:
                    func_length = node.end_lineno - node.lineno
                    if func_length > 50:
                        problems.append(
                            {
                                "type": "long_function",
                                "severity": "medium",
                                "line": node.lineno,
                                "description": (
                                    f"Function '{node.name}' is {func_length} lines long"
                                ),
                                "suggestion": (
                                    "Consider breaking into smaller functions"
                                ),
                            }
                        )

            elif isinstance(node, ast.ClassDef):
                classes.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [
                            n.name for n in node.body if isinstance(n, ast.FunctionDef)
                        ],
                        "docstring": ast.get_docstring(node),
                    }
                )

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                else:
                    imports.append(node.module or "")

        # Check content for hardcoded values using regex (more reliable than AST for this)
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            # Look for IP addresses
            ip_matches = re.findall(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", line)
            for ip in ip_matches:
                if (
                    ip.startswith(NetworkConstants.VM_IP_PREFIX)
                    or ip.startswith("127.0.0.")
                    or ip.startswith("192.168.")
                ):
                    hardcodes.append(
                        {"type": "ip", "value": ip, "line": i, "context": line.strip()}
                    )

            # Look for URLs
            url_matches = re.findall(r'[\'"`](https?://[^\'"` ]+)[\'"`]', line)
            for url in url_matches:
                hardcodes.append(
                    {"type": "url", "value": url, "line": i, "context": line.strip()}
                )

            # Look for port numbers
            port_matches = re.findall(r"\b(80[0-9][0-9]|[1-9][0-9]{3,4})\b", line)
            for port in port_matches:
                if port in [
                    str(NetworkConstants.BACKEND_PORT),
                    str(NetworkConstants.AI_STACK_PORT),
                    str(NetworkConstants.REDIS_PORT),
                    str(NetworkConstants.OLLAMA_PORT),
                    str(NetworkConstants.FRONTEND_PORT),
                    str(NetworkConstants.BROWSER_SERVICE_PORT),
                ]:
                    hardcodes.append(
                        {
                            "type": "port",
                            "value": port,
                            "line": i,
                            "context": line.strip(),
                        }
                    )

            # Issue #272: Detect technical debt markers (TODO, FIXME, HACK, XXX)
            debt_patterns = [
                (r"#\s*TODO[:\s](.+)$", "todo", "low"),
                (r"#\s*FIXME[:\s](.+)$", "fixme", "medium"),
                (r"#\s*HACK[:\s](.+)$", "hack", "high"),
                (r"#\s*XXX[:\s](.+)$", "xxx", "medium"),
                (r"#\s*BUG[:\s](.+)$", "bug", "high"),
                (r"#\s*DEPRECATED[:\s](.+)$", "deprecated", "medium"),
            ]
            for pattern, debt_type, severity in debt_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    description = match.group(1).strip() if match.group(1) else ""
                    technical_debt.append({
                        "type": debt_type,
                        "severity": severity,
                        "line": i,
                        "description": description[:200],  # Limit description length
                        "file_path": file_path,
                    })
                    # Also add to problems for visibility in reports
                    problems.append({
                        "type": f"technical_debt_{debt_type}",
                        "severity": severity,
                        "line": i,
                        "description": f"{debt_type.upper()}: {description[:100]}",
                        "suggestion": f"Address this {debt_type.upper()} comment",
                    })

        # Use LLM for semantic analysis if enabled
        if use_llm:
            try:
                llm_results = await detect_hardcodes_and_debt_with_llm(
                    content, file_path, language="python"
                )

                # Merge LLM hardcodes with regex hardcodes (avoid duplicates)
                existing_hardcode_values = {h.get("value") for h in hardcodes}
                for llm_hardcode in llm_results.get("hardcodes", []):
                    if llm_hardcode.get("value") not in existing_hardcode_values:
                        hardcodes.append(llm_hardcode)

                # Add technical debt from LLM
                technical_debt.extend(llm_results.get("technical_debt", []))

            except Exception as e:
                logger.debug(f"LLM analysis skipped for {file_path}: {e}")

        # Detect race conditions and concurrency issues
        try:
            race_condition_problems = detect_race_conditions(tree, content, file_path)
            problems.extend(race_condition_problems)
        except Exception as e:
            logger.debug(f"Race condition detection skipped for {file_path}: {e}")

        # Issue #268: Integrated code intelligence analyzers
        if _analyzers_available:
            # Anti-pattern detection (Issue #269)
            try:
                global _anti_pattern_detector
                if _anti_pattern_detector is None:
                    _anti_pattern_detector = AntiPatternDetector()
                anti_pattern_result = _anti_pattern_detector.analyze_file(file_path)
                for pattern in anti_pattern_result.get("patterns", []):
                    problems.append({
                        "type": f"code_smell_{pattern.pattern_type.value}",
                        "severity": pattern.severity.value,
                        "line": pattern.line_number,
                        "description": pattern.description,
                        "suggestion": pattern.suggestion,
                    })
            except Exception as e:
                logger.debug(f"Anti-pattern detection skipped for {file_path}: {e}")

            # Performance analysis (Issue #270)
            try:
                global _performance_analyzer
                if _performance_analyzer is None:
                    _performance_analyzer = PerformanceAnalyzer()
                perf_issues = _performance_analyzer.analyze_file(file_path)
                for issue in perf_issues:
                    problems.append({
                        "type": f"performance_{issue.issue_type.value}",
                        "severity": issue.severity.value,
                        "line": issue.line_start,
                        "description": issue.description,
                        "suggestion": issue.recommendation,
                    })
            except Exception as e:
                logger.debug(f"Performance analysis skipped for {file_path}: {e}")

            # Bug prediction (Issue #273)
            try:
                global _bug_predictor
                if _bug_predictor is None:
                    project_root = Path(file_path).parent
                    while project_root.parent != project_root:
                        if (project_root / ".git").exists():
                            break
                        project_root = project_root.parent
                    _bug_predictor = BugPredictor(str(project_root))

                risk_assessment = _bug_predictor.analyze_file(file_path)
                if risk_assessment.overall_risk >= 70:  # High risk threshold
                    problems.append({
                        "type": "bug_prediction_high_risk",
                        "severity": "high" if risk_assessment.overall_risk >= 85 else "medium",
                        "line": 1,
                        "description": (
                            f"High bug risk score: {risk_assessment.overall_risk:.0f}/100. "
                            f"Risk level: {risk_assessment.risk_level.value}"
                        ),
                        "suggestion": "; ".join(risk_assessment.recommendations[:3])
                            if risk_assessment.recommendations else "Review code complexity",
                    })
            except Exception as e:
                logger.debug(f"Bug prediction skipped for {file_path}: {e}")

        return {
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "hardcodes": hardcodes,
            "problems": problems,
            "technical_debt": technical_debt,
            "line_count": len(content.splitlines()),
        }

    except OSError as e:
        logger.error(f"Failed to read Python file {file_path}: {e}")
        return {
            "functions": [],
            "classes": [],
            "imports": [],
            "hardcodes": [],
            "problems": [],
            "technical_debt": [],
            "line_count": 0,
        }
    except Exception as e:
        logger.error(f"Error analyzing Python file {file_path}: {e}")
        return {
            "functions": [],
            "classes": [],
            "imports": [],
            "hardcodes": [],
            "problems": [
                {
                    "type": "parse_error",
                    "severity": "high",
                    "line": 1,
                    "description": f"Failed to parse file: {str(e)}",
                    "suggestion": "Check syntax errors",
                }
            ],
            "technical_debt": [],
            "line_count": 0,
        }


def analyze_javascript_vue_file(file_path: str) -> Metadata:
    """Analyze JavaScript/Vue file for functions and hardcodes"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.splitlines()
        functions = []
        hardcodes = []
        problems = []

        # Simple regex-based analysis for JS/Vue
        function_pattern = re.compile(
            r"(?:function\s+(\w+)|(\w+)\s*[:=]\s*(?:async\s+)?function|"
            r"\b(\w+)\s*\(.*?\)\s*\{|const\s+(\w+)\s*=\s*\(.*?\)\s*=>)"
        )
        url_pattern = re.compile(r'[\'"`](https?://[^\'"` ]+)[\'"`]')
        api_pattern = re.compile(r'[\'"`](/api/[^\'"` ]+)[\'"`]')
        ip_pattern = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")

        for i, line in enumerate(lines, 1):
            # Find functions
            func_matches = function_pattern.findall(line)
            for match in func_matches:
                func_name = next(name for name in match if name)
                if func_name and not func_name.startswith("_"):
                    functions.append({"name": func_name, "line": i, "type": "function"})

            # Find URLs
            url_matches = url_pattern.findall(line)
            for url in url_matches:
                hardcodes.append(
                    {"type": "url", "value": url, "line": i, "context": line.strip()}
                )

            # Find API paths
            api_matches = api_pattern.findall(line)
            for api_path in api_matches:
                hardcodes.append(
                    {
                        "type": "api_path",
                        "value": api_path,
                        "line": i,
                        "context": line.strip(),
                    }
                )

            # Find IP addresses
            ip_matches = ip_pattern.findall(line)
            for ip in ip_matches:
                if (
                    ip.startswith(NetworkConstants.VM_IP_PREFIX)
                    or ip.startswith("127.0.0.")
                    or ip.startswith("192.168.")
                ):
                    hardcodes.append(
                        {"type": "ip", "value": ip, "line": i, "context": line.strip()}
                    )

            # Check for console.log (potential debugging leftover)
            if "console.log" in line and not line.strip().startswith("//"):
                problems.append(
                    {
                        "type": "debug_code",
                        "severity": "low",
                        "line": i,
                        "description": "console.log statement found",
                        "suggestion": "Remove debug statements before production",
                    }
                )

        return {
            "functions": functions,
            "classes": [],
            "imports": [],
            "hardcodes": hardcodes,
            "problems": problems,
            "line_count": len(lines),
        }

    except Exception as e:
        logger.error(f"Error analyzing JS/Vue file {file_path}: {e}")
        return {
            "functions": [],
            "classes": [],
            "imports": [],
            "hardcodes": [],
            "problems": [],
            "line_count": 0,
        }


