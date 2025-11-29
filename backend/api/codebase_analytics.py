# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Real Codebase Analytics API for AutoBot (With Redis Fallback)
Provides comprehensive code analysis with both Redis and in-memory storage
"""

import ast
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from backend.type_defs.common import Metadata
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.constants.network_constants import NetworkConstants
from src.llm_interface import LLMInterface
from src.utils.chromadb_client import get_chromadb_client
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/codebase", tags=["codebase-analytics"])

# In-memory storage fallback when Redis is unavailable
_in_memory_storage = {}

# Global storage for indexing task progress (thread-safe with asyncio)
indexing_tasks: Dict[str, Metadata] = {}

# Store active task references to prevent garbage collection
_active_tasks: Dict[str, asyncio.Task] = {}

# Global lock to prevent concurrent indexing tasks
_indexing_lock = asyncio.Lock()
_current_indexing_task_id: Optional[str] = None


class CodebaseStats(BaseModel):
    total_files: int
    total_lines: int
    python_files: int
    javascript_files: int
    vue_files: int
    other_files: int
    total_functions: int
    total_classes: int
    average_file_size: float
    last_indexed: str


class ProblemItem(BaseModel):
    type: str
    severity: str
    file_path: str
    line_number: Optional[int]
    description: str
    suggestion: str


class HardcodeItem(BaseModel):
    file_path: str
    line_number: int
    type: str  # 'url', 'path', 'ip', 'port', 'api_key', 'string'
    value: str
    context: str


class DeclarationItem(BaseModel):
    name: str
    type: str  # 'function', 'class', 'variable'
    file_path: str
    line_number: int
    usage_count: int
    is_exported: bool
    parameters: Optional[List[str]]


async def get_redis_connection():
    """
    Get Redis connection for codebase analytics using canonical utility

    This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy.
    Uses DB 11 (analytics) for codebase indexing and analysis.
    """
    # Use canonical Redis utility instead of direct instantiation
    from src.utils.redis_client import get_redis_client

    redis_client = get_redis_client(database="analytics")
    if redis_client is None:
        logger.warning(
            "Redis client initialization returned None, using in-memory storage"
        )
        return None

    return redis_client


def get_code_collection():
    """Get ChromaDB client and autobot_code collection"""
    try:
        # Get project root
        project_root = Path(__file__).parent.parent.parent
        chroma_path = project_root / "data" / "chromadb"

        # Create persistent client with telemetry disabled using shared utility
        chroma_client = get_chromadb_client(
            db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
        )

        # Get or create the code collection
        code_collection = chroma_client.get_or_create_collection(
            name="autobot_code",
            metadata={
                "description": (
                    "Codebase analytics: functions, classes, problems, duplicates"
                )
            },
        )

        logger.info(
            f"ChromaDB autobot_code collection ready ({code_collection.count()} items)"
        )
        return code_collection

    except Exception as e:
        logger.error(f"ChromaDB connection failed: {e}")
        return None


class InMemoryStorage:
    """In-memory storage fallback when Redis is unavailable"""

    def __init__(self):
        self.data = {}

    def set(self, key: str, value: str):
        self.data[key] = value

    def get(self, key: str):
        return self.data.get(key)

    def hset(self, key: str, mapping: dict):
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)

    def hgetall(self, key: str):
        return self.data.get(key, {})

    def sadd(self, key: str, value: str):
        if key not in self.data:
            self.data[key] = set()
        self.data[key].add(value)

    def smembers(self, key: str):
        return self.data.get(key, set())

    def scan_iter(self, match: str):
        pass

        pattern = match.replace("*", ".*")
        for key in self.data.keys():
            if re.match(pattern, key):
                yield key

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
        return len(keys)

    def exists(self, key: str):
        return key in self.data


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
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

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

        return {
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "hardcodes": hardcodes,
            "problems": problems,
            "technical_debt": technical_debt,
            "line_count": len(content.splitlines()),
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


async def scan_codebase(
    root_path: Optional[str] = None,
    progress_callback: Optional[callable] = None,
    immediate_store_collection=None,
) -> Metadata:
    """Scan the entire codebase using MCP-like file operations"""
    # Use project-relative path if not specified
    if root_path is None:
        project_root = Path(__file__).parent.parent.parent
        root_path = str(project_root)

    # File extensions to analyze
    PYTHON_EXTENSIONS = {".py"}
    JS_EXTENSIONS = {".js", ".ts"}
    VUE_EXTENSIONS = {".vue"}
    CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".conf"}

    analysis_results = {
        "files": {},
        "stats": {
            "total_files": 0,
            "python_files": 0,
            "javascript_files": 0,
            "vue_files": 0,
            "config_files": 0,
            "other_files": 0,
            "total_lines": 0,
            "total_functions": 0,
            "total_classes": 0,
        },
        "all_functions": [],
        "all_classes": [],
        "all_hardcodes": [],
        "all_problems": [],
    }

    # Directories to skip
    SKIP_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".venv",
        "venv",
        ".DS_Store",
        "logs",
        "temp",
        "archives",  # Exclude archived/old code
    }

    try:
        root_path_obj = Path(root_path)

        # First pass: count total files for progress tracking
        total_files = 0
        if progress_callback:
            for file_path in root_path_obj.rglob("*"):
                if file_path.is_file():
                    if not any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                        total_files += 1

            # Report total files discovered
            await progress_callback(
                operation="Scanning files",
                current=0,
                total=total_files,
                current_file="Initializing...",
            )

        # Walk through all files
        files_processed = 0
        for file_path in root_path_obj.rglob("*"):
            if file_path.is_file():
                # Skip if in excluded directory
                if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                    continue

                extension = file_path.suffix.lower()
                relative_path = str(file_path.relative_to(root_path_obj))

                analysis_results["stats"]["total_files"] += 1
                files_processed += 1

                # Update progress every 10 files or if callback provided
                if progress_callback and files_processed % 10 == 0:
                    await progress_callback(
                        operation="Scanning files",
                        current=files_processed,
                        total=total_files,
                        current_file=relative_path,
                    )

                file_analysis = None

                if extension in PYTHON_EXTENSIONS:
                    analysis_results["stats"]["python_files"] += 1
                    file_analysis = await analyze_python_file(str(file_path))

                elif extension in JS_EXTENSIONS:
                    analysis_results["stats"]["javascript_files"] += 1
                    file_analysis = analyze_javascript_vue_file(str(file_path))

                elif extension in VUE_EXTENSIONS:
                    analysis_results["stats"]["vue_files"] += 1
                    file_analysis = analyze_javascript_vue_file(str(file_path))

                elif extension in CONFIG_EXTENSIONS:
                    analysis_results["stats"]["config_files"] += 1

                else:
                    analysis_results["stats"]["other_files"] += 1

                if file_analysis:
                    analysis_results["files"][relative_path] = file_analysis
                    analysis_results["stats"]["total_lines"] += file_analysis.get(
                        "line_count", 0
                    )
                    analysis_results["stats"]["total_functions"] += len(
                        file_analysis.get("functions", [])
                    )
                    analysis_results["stats"]["total_classes"] += len(
                        file_analysis.get("classes", [])
                    )

                    # Aggregate data
                    for func in file_analysis.get("functions", []):
                        func["file_path"] = relative_path
                        analysis_results["all_functions"].append(func)

                    for cls in file_analysis.get("classes", []):
                        cls["file_path"] = relative_path
                        analysis_results["all_classes"].append(cls)

                    for hardcode in file_analysis.get("hardcodes", []):
                        hardcode["file_path"] = relative_path
                        analysis_results["all_hardcodes"].append(hardcode)

                    for problem in file_analysis.get("problems", []):
                        problem["file_path"] = relative_path
                        analysis_results["all_problems"].append(problem)

                        # Store problem immediately to ChromaDB if collection provided
                        if immediate_store_collection:
                            try:
                                problem_idx = len(analysis_results["all_problems"]) - 1
                                problem_doc = f"""
Problem: {problem.get('type', 'unknown')}
Severity: {problem.get('severity', 'medium')}
File: {problem.get('file_path', '')}
Line: {problem.get('line', 0)}
Description: {problem.get('description', '')}
Suggestion: {problem.get('suggestion', '')}
                                """.strip()
                                await asyncio.to_thread(
                                    immediate_store_collection.add,
                                    ids=[f"problem_{problem_idx}_{problem.get('type', 'unknown')}"],
                                    documents=[problem_doc],
                                    metadatas=[{
                                        "type": "problem",
                                        "problem_type": problem.get("type", "unknown"),
                                        "severity": problem.get("severity", "medium"),
                                        "file_path": problem.get("file_path", ""),
                                        "line_number": str(problem.get("line", 0)),
                                        "description": problem.get("description", ""),
                                        "suggestion": problem.get("suggestion", ""),
                                    }],
                                )
                            except Exception as e:
                                logger.debug(f"Failed to store problem immediately: {e}")

        # Calculate average file size
        if analysis_results["stats"]["total_files"] > 0:
            analysis_results["stats"]["average_file_size"] = (
                analysis_results["stats"]["total_lines"]
                / analysis_results["stats"]["total_files"]
            )
        else:
            analysis_results["stats"]["average_file_size"] = 0

        analysis_results["stats"]["last_indexed"] = datetime.now().isoformat()

        return analysis_results

    except Exception as e:
        logger.error(f"Error scanning codebase: {e}")
        raise HTTPException(status_code=500, detail=f"Codebase scan failed: {str(e)}")


async def do_indexing_with_progress(task_id: str, root_path: str):
    """
    Background task: Index codebase with real-time progress updates

    Updates indexing_tasks[task_id] with progress information:
    - status: "running" | "completed" | "failed"
    - progress: {current, total, percent, current_file, operation}
    - result: final results when completed
    - error: error message if failed
    """
    try:
        logger.info(
            f"[Task {task_id}] Starting background codebase indexing for: {root_path}"
        )

        # Initialize task status with enhanced phase and batch tracking
        indexing_tasks[task_id] = {
            "status": "running",
            "progress": {
                "current": 0,
                "total": 0,
                "percent": 0,
                "current_file": "Initializing...",
                "operation": "Starting indexing",
            },
            "phases": {
                "current_phase": "init",
                "phases_completed": [],
                "phase_list": [
                    {"id": "init", "name": "Initialization", "status": "running"},
                    {"id": "scan", "name": "Scanning Files", "status": "pending"},
                    {"id": "prepare", "name": "Preparing Data", "status": "pending"},
                    {"id": "store", "name": "Storing to ChromaDB", "status": "pending"},
                    {"id": "finalize", "name": "Finalizing", "status": "pending"},
                ],
            },
            "batches": {
                "total_batches": 0,
                "completed_batches": 0,
                "current_batch": 0,
                "batch_size": 5000,  # ChromaDB max batch size
                "items_per_batch": [],
            },
            "stats": {
                "files_scanned": 0,
                "problems_found": 0,
                "functions_found": 0,
                "classes_found": 0,
                "items_stored": 0,
            },
            "result": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
        }

        # Helper to update phase status
        def update_phase(phase_id: str, status: str):
            phases = indexing_tasks[task_id]["phases"]
            phases["current_phase"] = phase_id
            for phase in phases["phase_list"]:
                if phase["id"] == phase_id:
                    phase["status"] = status
                    if status == "completed" and phase_id not in phases["phases_completed"]:
                        phases["phases_completed"].append(phase_id)
                    break

        # Helper to update batch info
        def update_batch_info(current_batch: int, total_batches: int, items_in_batch: int = 0):
            batches = indexing_tasks[task_id]["batches"]
            batches["current_batch"] = current_batch
            batches["total_batches"] = total_batches
            if items_in_batch > 0 and current_batch > len(batches["items_per_batch"]):
                batches["items_per_batch"].append(items_in_batch)

        # Helper to update stats
        def update_stats(**kwargs):
            for key, value in kwargs.items():
                if key in indexing_tasks[task_id]["stats"]:
                    indexing_tasks[task_id]["stats"][key] = value

        # Progress callback function
        async def update_progress(
            operation: str, current: int, total: int, current_file: str,
            phase: str = None, batch_info: dict = None
        ):
            percent = int((current / total * 100)) if total > 0 else 0
            indexing_tasks[task_id]["progress"] = {
                "current": current,
                "total": total,
                "percent": percent,
                "current_file": current_file,
                "operation": operation,
            }

            # Update phase if specified
            if phase:
                update_phase(phase, "running")

            # Update batch info if specified
            if batch_info:
                update_batch_info(
                    batch_info.get("current", 0),
                    batch_info.get("total", 0),
                    batch_info.get("items", 0)
                )

            logger.debug(
                f"[Task {task_id}] Progress: {operation} - {current}/{total} ({percent}%)"
            )

        # Get ChromaDB collection FIRST so we can store problems immediately
        update_phase("init", "running")
        await update_progress(
            operation="Preparing ChromaDB",
            current=0,
            total=1,
            current_file="Connecting to ChromaDB...",
            phase="init",
        )

        code_collection = await asyncio.to_thread(get_code_collection)
        storage_type = "chromadb" if code_collection else "memory"

        if code_collection:
            # Clear existing data before scanning
            await update_progress(
                operation="Clearing old ChromaDB data",
                current=0,
                total=1,
                current_file="Removing existing entries...",
                phase="init",
            )

            try:
                existing_data = await asyncio.to_thread(code_collection.get)
                existing_ids = existing_data["ids"]
                if existing_ids:
                    await asyncio.to_thread(code_collection.delete, ids=existing_ids)
                    logger.info(
                        f"[Task {task_id}] Cleared {len(existing_ids)} existing items from ChromaDB"
                    )
            except Exception as e:
                logger.warning(f"[Task {task_id}] Error clearing collection: {e}")

        # Mark init phase as completed, start scan phase
        update_phase("init", "completed")
        update_phase("scan", "running")

        # Scan the codebase with progress tracking
        # Pass collection so problems can be stored immediately as they're found
        analysis_results = await scan_codebase(
            root_path,
            progress_callback=update_progress,
            immediate_store_collection=code_collection,
        )

        # Update stats from scan results
        update_stats(
            files_scanned=analysis_results["stats"]["total_files"],
            problems_found=len(analysis_results["all_problems"]),
            functions_found=len(analysis_results["all_functions"]),
            classes_found=len(analysis_results["all_classes"]),
        )

        # Mark scan phase completed
        update_phase("scan", "completed")

        if code_collection:
            # Start prepare phase
            update_phase("prepare", "running")

            # Problems were already stored during scan, now store functions and classes
            # Prepare batch data for ChromaDB (excluding problems which are already stored)
            batch_ids = []
            batch_documents = []
            batch_metadatas = []

            # Store functions and classes (problems were already stored during scan)
            total_items_to_store = (
                len(analysis_results["all_functions"])
                + len(analysis_results["all_classes"])
                + 1  # stats (problems already stored)
            )
            items_prepared = 0

            await update_progress(
                operation="Preparing functions",
                current=0,
                total=total_items_to_store,
                current_file="Processing functions...",
                phase="prepare",
            )

            for idx, func in enumerate(analysis_results["all_functions"]):
                doc_text = """
Function: {func['name']}
File: {func.get('file_path', 'unknown')}
Line: {func.get('line', 0)}
Parameters: {', '.join(func.get('args', []))}
Docstring: {func.get('docstring', 'No documentation')}
                """.strip()

                batch_ids.append(f"function_{idx}_{func['name']}")
                batch_documents.append(doc_text)
                batch_metadatas.append(
                    {
                        "type": "function",
                        "name": func["name"],
                        "file_path": func.get("file_path", ""),
                        "start_line": str(func.get("line", 0)),
                        "parameters": ",".join(func.get("args", [])),
                        "language": (
                            "python"
                            if func.get("file_path", "").endswith(".py")
                            else "javascript"
                        ),
                    }
                )

                items_prepared += 1
                if items_prepared % 100 == 0:
                    await update_progress(
                        operation="Storing functions",
                        current=items_prepared,
                        total=total_items_to_store,
                        current_file=f"Function {idx+1}/{len(analysis_results['all_functions'])}",
                    )

            # Store classes
            await update_progress(
                operation="Storing classes",
                current=items_prepared,
                total=total_items_to_store,
                current_file="Processing classes...",
            )

            for idx, cls in enumerate(analysis_results["all_classes"]):
                doc_text = """
Class: {cls['name']}
File: {cls.get('file_path', 'unknown')}
Line: {cls.get('line', 0)}
Methods: {', '.join(cls.get('methods', []))}
Docstring: {cls.get('docstring', 'No documentation')}
                """.strip()

                batch_ids.append(f"class_{idx}_{cls['name']}")
                batch_documents.append(doc_text)
                batch_metadatas.append(
                    {
                        "type": "class",
                        "name": cls["name"],
                        "file_path": cls.get("file_path", ""),
                        "start_line": str(cls.get("line", 0)),
                        "methods": ",".join(cls.get("methods", [])),
                        "language": "python",
                    }
                )

                items_prepared += 1
                if items_prepared % 50 == 0:
                    await update_progress(
                        operation="Storing classes",
                        current=items_prepared,
                        total=total_items_to_store,
                        current_file=f"Class {idx+1}/{len(analysis_results['all_classes'])}",
                    )

            # NOTE: Problems were already stored immediately during scan phase
            # No need to store them again here

            # Store stats as a special document
            stats_doc = """
Codebase Statistics:
Total Files: {analysis_results['stats']['total_files']}
Total Lines: {analysis_results['stats']['total_lines']}
Python Files: {analysis_results['stats']['python_files']}
JavaScript Files: {analysis_results['stats']['javascript_files']}
Vue Files: {analysis_results['stats']['vue_files']}
Total Functions: {analysis_results['stats']['total_functions']}
Total Classes: {analysis_results['stats']['total_classes']}
Last Indexed: {analysis_results['stats']['last_indexed']}
            """.strip()

            batch_ids.append("codebase_stats")
            batch_documents.append(stats_doc)
            batch_metadatas.append(
                {
                    "type": "stats",
                    **{k: str(v) for k, v in analysis_results["stats"].items()},
                }
            )

            items_prepared += 1

            # Mark prepare phase completed
            update_phase("prepare", "completed")

            # Add all to ChromaDB in batches (ChromaDB has max batch size limit)
            if batch_ids:
                # Start store phase
                update_phase("store", "running")

                BATCH_SIZE = (
                    5000  # ChromaDB max batch size is ~5461, use 5000 for safety
                )
                total_items = len(batch_ids)
                items_stored = 0
                total_batches = (total_items + BATCH_SIZE - 1) // BATCH_SIZE

                # Initialize batch tracking
                update_batch_info(0, total_batches, 0)

                await update_progress(
                    operation="Writing to ChromaDB",
                    current=0,
                    total=total_items,
                    current_file="Batch storage in progress...",
                    phase="store",
                    batch_info={"current": 0, "total": total_batches, "items": 0}
                )

                for i in range(0, total_items, BATCH_SIZE):
                    batch_slice_ids = batch_ids[i : i + BATCH_SIZE]
                    batch_slice_docs = batch_documents[i : i + BATCH_SIZE]
                    batch_slice_metas = batch_metadatas[i : i + BATCH_SIZE]
                    batch_num = i // BATCH_SIZE + 1

                    # Run blocking ChromaDB add in thread pool
                    await asyncio.to_thread(
                        code_collection.add,
                        ids=batch_slice_ids,
                        documents=batch_slice_docs,
                        metadatas=batch_slice_metas,
                    )
                    items_stored += len(batch_slice_ids)

                    # Update batch tracking with completed batch info
                    indexing_tasks[task_id]["batches"]["completed_batches"] = batch_num

                    await update_progress(
                        operation="Writing to ChromaDB",
                        current=items_stored,
                        total=total_items,
                        current_file=f"Batch {batch_num}/{total_batches}",
                        phase="store",
                        batch_info={"current": batch_num, "total": total_batches, "items": len(batch_slice_ids)}
                    )

                    # Update items stored stats
                    update_stats(items_stored=items_stored)

                    logger.info(
                        f"[Task {task_id}] Stored batch {batch_num}/{total_batches}: "
                        f"{len(batch_slice_ids)} items ({items_stored}/{total_items})"
                    )

                # Mark store phase completed
                update_phase("store", "completed")

                logger.info(
                    f"[Task {task_id}] ✅ Stored total of {items_stored} items in ChromaDB"
                )
        else:
            storage_type = "failed"
            raise Exception("ChromaDB connection failed")

        # Mark finalize phase
        update_phase("finalize", "running")

        # Mark task as completed
        indexing_tasks[task_id]["status"] = "completed"
        total_files = analysis_results['stats']['total_files']
        indexing_tasks[task_id]["result"] = {
            "status": "success",
            "message": f"Indexed {total_files} files using {storage_type} storage",
            "stats": analysis_results["stats"],
            "storage_type": storage_type,
            "timestamp": datetime.now().isoformat(),
        }
        indexing_tasks[task_id]["completed_at"] = datetime.now().isoformat()

        # Mark finalize phase as completed
        update_phase("finalize", "completed")

        logger.info(f"[Task {task_id}] ✅ Indexing completed successfully")

    except Exception as e:
        logger.error(f"[Task {task_id}] ❌ Indexing failed: {e}", exc_info=True)
        indexing_tasks[task_id]["status"] = "failed"
        indexing_tasks[task_id]["error"] = str(e)
        indexing_tasks[task_id]["failed_at"] = datetime.now().isoformat()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="index_codebase",
    error_code_prefix="CODEBASE",
)
@router.post("/index")
async def index_codebase():
    """
    Start background indexing of the AutoBot codebase

    Returns immediately with a task_id that can be used to poll progress
    via GET /api/analytics/codebase/index/status/{task_id}

    Only one indexing task can run at a time - subsequent requests will
    return the existing task's ID if one is already running.
    """
    global _current_indexing_task_id

    logger.info("✅ ENTRY: index_codebase endpoint called!")

    # Check if there's already an indexing task running
    if _current_indexing_task_id is not None:
        existing_task = _active_tasks.get(_current_indexing_task_id)
        if existing_task and not existing_task.done():
            logger.info(
                f"🔒 Indexing already in progress: {_current_indexing_task_id}"
            )
            return JSONResponse(
                {
                    "task_id": _current_indexing_task_id,
                    "status": "already_running",
                    "message": (
                        "Indexing is already in progress. Poll "
                        f"/api/analytics/codebase/index/status/{_current_indexing_task_id} "
                        "for progress."
                    ),
                }
            )

    # Always use project root
    project_root = Path(__file__).parent.parent.parent
    root_path = str(project_root)
    logger.info(f"📁 project_root = {root_path}")

    # Generate unique task ID
    task_id = str(uuid.uuid4())
    logger.info(f"🆔 Generated task_id = {task_id}")

    # Set the current indexing task
    _current_indexing_task_id = task_id

    # Add async background task using asyncio and store reference
    logger.info("🔄 About to create_task")
    task = asyncio.create_task(do_indexing_with_progress(task_id, root_path))
    logger.info(f"✅ Task created: {task}")
    _active_tasks[task_id] = task
    logger.info("💾 Task stored in _active_tasks")

    # Clean up task reference when done
    def cleanup_task(t):
        global _current_indexing_task_id
        _active_tasks.pop(task_id, None)
        if _current_indexing_task_id == task_id:
            _current_indexing_task_id = None
        logger.info(f"🧹 Task {task_id} cleaned up")

    task.add_done_callback(cleanup_task)
    logger.info("🧹 Cleanup callback added")

    logger.info("📤 About to return JSONResponse")
    return JSONResponse(
        {
            "task_id": task_id,
            "status": "started",
            "message": (
                "Indexing started in background. Poll "
                "/api/analytics/codebase/index/status/{task_id} for progress."
            ),
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_indexing_status",
    error_code_prefix="CODEBASE",
)
@router.get("/index/status/{task_id}")
async def get_indexing_status(task_id: str):
    """
    Get the status of a background indexing task

    Returns:
    - task_id: The unique task identifier
    - status: "running" | "completed" | "failed" | "not_found"
    - progress: {current, total, percent, current_file, operation} (if running)
    - result: Final indexing results (if completed)
    - error: Error message (if failed)
    """
    if task_id not in indexing_tasks:
        return JSONResponse(
            status_code=404,
            content={
                "task_id": task_id,
                "status": "not_found",
                "error": "Task not found. It may have expired or never existed.",
            },
        )

    task_data = indexing_tasks[task_id]

    response = {
        "task_id": task_id,
        "status": task_data["status"],
        "progress": task_data.get("progress"),
        "result": task_data.get("result"),
        "error": task_data.get("error"),
        "started_at": task_data.get("started_at"),
        "completed_at": task_data.get("completed_at"),
        "failed_at": task_data.get("failed_at"),
    }

    return JSONResponse(response)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_indexing_job",
    error_code_prefix="CODEBASE",
)
@router.get("/index/current")
async def get_current_indexing_job():
    """
    Get the status of the currently running indexing job (if any)

    Returns:
    - has_active_job: Whether an indexing job is currently running
    - task_id: The current job's task ID (if running)
    - status: Current job status
    - progress: Current progress details
    """
    global _current_indexing_task_id

    if _current_indexing_task_id is None:
        return JSONResponse({
            "has_active_job": False,
            "task_id": None,
            "status": "idle",
            "message": "No indexing job is currently running",
        })

    # Check if task is still running
    existing_task = _active_tasks.get(_current_indexing_task_id)
    if existing_task is None or existing_task.done():
        # Task finished or was cleaned up
        task_data = indexing_tasks.get(_current_indexing_task_id, {})
        return JSONResponse({
            "has_active_job": False,
            "task_id": _current_indexing_task_id,
            "status": task_data.get("status", "unknown"),
            "result": task_data.get("result"),
            "error": task_data.get("error"),
            "message": "Last indexing job has completed",
        })

    # Task is still running
    task_data = indexing_tasks.get(_current_indexing_task_id, {})
    return JSONResponse({
        "has_active_job": True,
        "task_id": _current_indexing_task_id,
        "status": task_data.get("status", "running"),
        "progress": task_data.get("progress"),
        "phases": task_data.get("phases"),
        "batches": task_data.get("batches"),
        "stats": task_data.get("stats"),
        "started_at": task_data.get("started_at"),
        "message": "Indexing job is in progress",
    })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_indexing_job",
    error_code_prefix="CODEBASE",
)
@router.post("/index/cancel")
async def cancel_indexing_job():
    """
    Cancel the currently running indexing job

    Returns:
    - success: Whether the cancellation was successful
    - task_id: The cancelled job's task ID
    - message: Status message
    """
    global _current_indexing_task_id

    if _current_indexing_task_id is None:
        return JSONResponse({
            "success": False,
            "task_id": None,
            "message": "No indexing job is currently running",
        })

    task_id = _current_indexing_task_id
    existing_task = _active_tasks.get(task_id)

    if existing_task is None or existing_task.done():
        return JSONResponse({
            "success": False,
            "task_id": task_id,
            "message": "Indexing job has already completed or was not found",
        })

    # Cancel the task
    try:
        existing_task.cancel()
        logger.info(f"🛑 Cancelled indexing task: {task_id}")

        # Update task status
        if task_id in indexing_tasks:
            indexing_tasks[task_id]["status"] = "cancelled"
            indexing_tasks[task_id]["error"] = "Cancelled by user"
            indexing_tasks[task_id]["failed_at"] = datetime.now().isoformat()

        # Clear current task
        _current_indexing_task_id = None
        _active_tasks.pop(task_id, None)

        return JSONResponse({
            "success": True,
            "task_id": task_id,
            "message": "Indexing job cancelled successfully",
        })

    except Exception as e:
        logger.error(f"Failed to cancel task {task_id}: {e}")
        return JSONResponse({
            "success": False,
            "task_id": task_id,
            "message": f"Failed to cancel job: {str(e)}",
        })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_stats",
    error_code_prefix="CODEBASE",
)
@router.get("/stats")
async def get_codebase_stats():
    """Get real codebase statistics from storage"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    if code_collection:
        try:
            # Query ChromaDB for stats
            results = code_collection.get(ids=["codebase_stats"], include=["metadatas"])

            if results.get("metadatas") and len(results["metadatas"]) > 0:
                stats_metadata = results["metadatas"][0]

                # Extract stats from metadata
                stats = {}
                numeric_fields = [
                    "total_files",
                    "python_files",
                    "javascript_files",
                    "vue_files",
                    "config_files",
                    "other_files",
                    "total_lines",
                    "total_functions",
                    "total_classes",
                ]

                for field in numeric_fields:
                    if field in stats_metadata:
                        stats[field] = int(stats_metadata[field])

                if "average_file_size" in stats_metadata:
                    stats["average_file_size"] = float(
                        stats_metadata["average_file_size"]
                    )

                timestamp = stats_metadata.get("last_indexed", "Never")
                storage_type = "chromadb"

                return JSONResponse(
                    {
                        "status": "success",
                        "stats": stats,
                        "last_indexed": timestamp,
                        "storage_type": storage_type,
                    }
                )
            else:
                return JSONResponse(
                    {
                        "status": "no_data",
                        "message": "No codebase data found. Run indexing first.",
                        "stats": None,
                    }
                )

        except Exception as chroma_error:
            logger.warning(f"ChromaDB stats query failed: {chroma_error}")
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "stats": None,
                }
            )
    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "ChromaDB connection failed.",
                "stats": None,
            }
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardcoded_values",
    error_code_prefix="CODEBASE",
)
@router.get("/hardcodes")
async def get_hardcoded_values(hardcode_type: Optional[str] = None):
    """Get real hardcoded values found in the codebase"""
    redis_client = await get_redis_connection()

    all_hardcodes = []

    if redis_client:
        if hardcode_type:
            hardcodes_data = redis_client.get(f"codebase:hardcodes:{hardcode_type}")
            if hardcodes_data:
                all_hardcodes = json.loads(hardcodes_data)
        else:
            for key in redis_client.scan_iter(match="codebase:hardcodes:*"):
                hardcodes_data = redis_client.get(key)
                if hardcodes_data:
                    all_hardcodes.extend(json.loads(hardcodes_data))
        storage_type = "redis"
    else:
        if not _in_memory_storage:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "hardcodes": [],
                }
            )

        storage = _in_memory_storage
        if hardcode_type:
            hardcodes_data = storage.get(f"codebase:hardcodes:{hardcode_type}")
            if hardcodes_data:
                all_hardcodes = json.loads(hardcodes_data)
        else:
            for key in storage.scan_iter("codebase:hardcodes:*"):
                hardcodes_data = storage.get(key)
                if hardcodes_data:
                    all_hardcodes.extend(json.loads(hardcodes_data))
        storage_type = "memory"

    # Sort by file and line number
    all_hardcodes.sort(key=lambda x: (x.get("file_path", ""), x.get("line", 0)))

    return JSONResponse(
        {
            "status": "success",
            "hardcodes": all_hardcodes,
            "total_count": len(all_hardcodes),
            "hardcode_types": list(
                set(h.get("type", "unknown") for h in all_hardcodes)
            ),
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_problems",
    error_code_prefix="CODEBASE",
)
@router.get("/problems")
async def get_codebase_problems(problem_type: Optional[str] = None):
    """Get real code problems detected during analysis"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_problems = []

    if code_collection:
        try:
            # Query ChromaDB for problems
            where_filter = {"type": "problem"}
            if problem_type:
                where_filter["problem_type"] = problem_type

            results = code_collection.get(where=where_filter, include=["metadatas"])

            # Extract problems from metadata
            for metadata in results.get("metadatas", []):
                all_problems.append(
                    {
                        "type": metadata.get("problem_type", ""),
                        "severity": metadata.get("severity", ""),
                        "file_path": metadata.get("file_path", ""),
                        "line_number": (
                            int(metadata.get("line_number", 0))
                            if metadata.get("line_number")
                            else None
                        ),
                        "description": metadata.get("description", ""),
                        "suggestion": metadata.get("suggestion", ""),
                    }
                )

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_problems)} problems from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, falling back to Redis"
            ),
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        redis_client = await get_redis_connection()

        if redis_client:
            if problem_type:
                problems_data = redis_client.get(f"codebase:problems:{problem_type}")
                if problems_data:
                    all_problems = json.loads(problems_data)
            else:
                for key in redis_client.scan_iter(match="codebase:problems:*"):
                    problems_data = redis_client.get(key)
                    if problems_data:
                        all_problems.extend(json.loads(problems_data))
            storage_type = "redis"
        else:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "problems": [],
                }
            )

    # Sort by severity (high, medium, low)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    all_problems.sort(
        key=lambda x: (
            severity_order.get(x.get("severity", "low"), 3),
            x.get("file_path", ""),
        )
    )

    return JSONResponse(
        {
            "status": "success",
            "problems": all_problems,
            "total_count": len(all_problems),
            "problem_types": list(set(p.get("type", "unknown") for p in all_problems)),
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chart_data",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/charts")
async def get_chart_data():
    """
    Get aggregated data for analytics charts.

    Returns data structures optimized for ApexCharts:
    - problem_types: Pie chart data for problem type distribution
    - severity_counts: Bar chart data for severity levels
    - race_conditions: Donut chart data for race condition categories
    - top_files: Horizontal bar chart for files with most problems
    - summary: Overall summary statistics
    """
    code_collection = get_code_collection()

    # Initialize aggregation containers
    problem_types: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    race_conditions: Dict[str, int] = {}
    file_problems: Dict[str, int] = {}
    total_problems = 0

    if code_collection:
        try:
            # Query all problems from ChromaDB
            results = code_collection.get(
                where={"type": "problem"}, include=["metadatas"]
            )

            for metadata in results.get("metadatas", []):
                total_problems += 1

                # Aggregate by problem type
                ptype = metadata.get("problem_type", "unknown")
                problem_types[ptype] = problem_types.get(ptype, 0) + 1

                # Aggregate by severity
                severity = metadata.get("severity", "low")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

                # Aggregate race conditions separately
                if "race" in ptype.lower() or "thread" in ptype.lower():
                    race_conditions[ptype] = race_conditions.get(ptype, 0) + 1

                # Count problems per file
                file_path = metadata.get("file_path", "unknown")
                file_problems[file_path] = file_problems.get(file_path, 0) + 1

            storage_type = "chromadb"
            logger.info(f"Aggregated chart data for {total_problems} problems")

        except Exception as chroma_error:
            logger.warning(f"ChromaDB query failed: {chroma_error}")
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        redis_client = await get_redis_connection()

        if redis_client:
            try:
                for key in redis_client.scan_iter(match="codebase:problems:*"):
                    problems_data = redis_client.get(key)
                    if problems_data:
                        problems = json.loads(problems_data)
                        for problem in problems:
                            total_problems += 1

                            ptype = problem.get("type", "unknown")
                            problem_types[ptype] = problem_types.get(ptype, 0) + 1

                            severity = problem.get("severity", "low")
                            severity_counts[severity] = (
                                severity_counts.get(severity, 0) + 1
                            )

                            if "race" in ptype.lower() or "thread" in ptype.lower():
                                race_conditions[ptype] = (
                                    race_conditions.get(ptype, 0) + 1
                                )

                            file_path = problem.get("file_path", "unknown")
                            file_problems[file_path] = (
                                file_problems.get(file_path, 0) + 1
                            )

                storage_type = "redis"
            except Exception as redis_error:
                logger.error(f"Redis query failed: {redis_error}")
                return JSONResponse(
                    {
                        "status": "error",
                        "message": "Failed to retrieve chart data",
                        "error": str(redis_error),
                    },
                    status_code=500,
                )
        else:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "chart_data": None,
                }
            )

    # Convert to chart-friendly format

    # Problem types for pie chart (sorted by count descending)
    problem_types_data = [
        {"type": ptype, "count": count}
        for ptype, count in sorted(
            problem_types.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Severity for bar chart (ordered by severity level)
    severity_order = ["high", "medium", "low", "info", "hint"]
    severity_data = []
    for sev in severity_order:
        if sev in severity_counts:
            severity_data.append({"severity": sev, "count": severity_counts[sev]})
    # Add any unlisted severities
    for sev, count in severity_counts.items():
        if sev not in severity_order:
            severity_data.append({"severity": sev, "count": count})

    # Race conditions for donut chart
    race_conditions_data = [
        {"category": cat, "count": count}
        for cat, count in sorted(
            race_conditions.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Top files for horizontal bar chart (top 15)
    top_files_data = [
        {"file": file_path, "count": count}
        for file_path, count in sorted(
            file_problems.items(), key=lambda x: x[1], reverse=True
        )[:15]
    ]

    return JSONResponse(
        {
            "status": "success",
            "chart_data": {
                "problem_types": problem_types_data,
                "severity_counts": severity_data,
                "race_conditions": race_conditions_data,
                "top_files": top_files_data,
                "summary": {
                    "total_problems": total_problems,
                    "unique_problem_types": len(problem_types),
                    "files_with_problems": len(file_problems),
                    "race_condition_count": sum(race_conditions.values()),
                },
            },
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dependencies",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/dependencies")
async def get_dependencies():
    """
    Get file dependency analysis showing imports and module relationships.

    Returns:
    - modules: List of all modules/files in the codebase
    - imports: Import relationships (which file imports what)
    - dependency_graph: Graph structure for visualization
    - circular_dependencies: Detected circular import issues
    - external_dependencies: Third-party package dependencies
    """
    code_collection = get_code_collection()

    # Data structures
    modules: Dict[str, Dict] = {}  # file_path -> module info
    import_relationships: List[Dict] = []  # source -> target relationships
    external_deps: Dict[str, int] = {}  # external package -> usage count
    circular_deps: List[List[str]] = []

    if code_collection:
        try:
            # Query all Python files from ChromaDB
            # Get functions and classes to understand module structure
            results = code_collection.get(
                where={"type": {"$in": ["function", "class"]}}, include=["metadatas"]
            )

            # Build module map from stored data
            seen_files = set()
            for metadata in results.get("metadatas", []):
                file_path = metadata.get("file_path", "")
                if file_path and file_path not in seen_files:
                    seen_files.add(file_path)
                    modules[file_path] = {
                        "path": file_path,
                        "name": Path(file_path).stem,
                        "package": str(Path(file_path).parent),
                        "functions": 0,
                        "classes": 0,
                        "imports": [],
                    }

                if file_path in modules:
                    if metadata.get("type") == "function":
                        modules[file_path]["functions"] += 1
                    elif metadata.get("type") == "class":
                        modules[file_path]["classes"] += 1

            storage_type = "chromadb"
            logger.info(f"Found {len(modules)} modules in ChromaDB")

        except Exception as chroma_error:
            logger.warning(f"ChromaDB query failed: {chroma_error}")
            code_collection = None

    # Fallback: scan the actual filesystem for more detailed import analysis
    # This gives us actual import statements
    project_root = Path("/home/kali/Desktop/AutoBot")
    python_files = list(project_root.rglob("*.py"))

    # Filter out unwanted directories
    excluded_dirs = {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "archive",
        "dist",
        "build",
    }
    python_files = [
        f
        for f in python_files
        if not any(excluded in f.parts for excluded in excluded_dirs)
    ]

    # Analyze imports from each file
    stdlib_modules = {
        "os",
        "sys",
        "re",
        "json",
        "time",
        "datetime",
        "logging",
        "asyncio",
        "pathlib",
        "typing",
        "collections",
        "functools",
        "itertools",
        "subprocess",
        "threading",
        "multiprocessing",
        "uuid",
        "hashlib",
        "base64",
        "io",
        "contextlib",
        "abc",
        "dataclasses",
        "enum",
        "copy",
        "math",
        "random",
        "socket",
        "http",
        "urllib",
        "traceback",
        "inspect",
        "ast",
        "shutil",
        "tempfile",
        "warnings",
        "signal",
    }

    for py_file in python_files[:500]:  # Limit to 500 files for performance
        try:
            rel_path = str(py_file.relative_to(project_root))
            if rel_path not in modules:
                modules[rel_path] = {
                    "path": rel_path,
                    "name": py_file.stem,
                    "package": str(py_file.parent.relative_to(project_root)),
                    "functions": 0,
                    "classes": 0,
                    "imports": [],
                }

            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            file_imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split(".")[0]
                        file_imports.append(module_name)
                        if module_name not in stdlib_modules:
                            external_deps[module_name] = (
                                external_deps.get(module_name, 0) + 1
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module.split(".")[0]
                        file_imports.append(node.module)
                        if module_name not in stdlib_modules:
                            external_deps[module_name] = (
                                external_deps.get(module_name, 0) + 1
                            )

            modules[rel_path]["imports"] = list(set(file_imports))

            # Create import relationships for graph
            for imp in file_imports:
                import_relationships.append(
                    {"source": rel_path, "target": imp, "type": "import"}
                )

        except Exception as e:
            logger.debug(f"Could not analyze {py_file}: {e}")
            continue

    # Detect circular dependencies (simplified check)
    import_map = {}
    for rel in import_relationships:
        source = rel["source"]
        target = rel["target"]
        if source not in import_map:
            import_map[source] = set()
        import_map[source].add(target)

    # Check for simple circular imports (A imports B, B imports A)
    for source, targets in import_map.items():
        for target in targets:
            # Check if target imports source (simple cycle)
            for other_source, other_targets in import_map.items():
                if target in other_source and source in other_targets:
                    cycle = sorted([source, other_source])
                    if cycle not in circular_deps:
                        circular_deps.append(cycle)

    # Build graph structure for visualization
    nodes = []
    edges = []

    for path, info in modules.items():
        nodes.append(
            {
                "id": path,
                "name": info["name"],
                "package": info["package"],
                "type": "module",
                "functions": info["functions"],
                "classes": info["classes"],
                "import_count": len(info["imports"]),
            }
        )

    for rel in import_relationships:
        edges.append({"from": rel["source"], "to": rel["target"], "type": rel["type"]})

    # Sort external dependencies by usage
    sorted_external = [
        {"package": pkg, "usage_count": count}
        for pkg, count in sorted(external_deps.items(), key=lambda x: x[1], reverse=True)
    ]

    return JSONResponse(
        {
            "status": "success",
            "dependency_data": {
                "modules": list(modules.values()),
                "import_relationships": import_relationships[:1000],  # Limit for UI
                "graph": {"nodes": nodes[:500], "edges": edges[:2000]},
                "circular_dependencies": circular_deps,
                "external_dependencies": sorted_external[:50],
                "summary": {
                    "total_modules": len(modules),
                    "total_import_relationships": len(import_relationships),
                    "circular_dependency_count": len(circular_deps),
                    "external_dependency_count": len(external_deps),
                },
            },
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_tree",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/import-tree")
async def get_import_tree():
    """
    Get bidirectional file import relationships for tree visualization.

    Returns for each file:
    - imports: What this file imports (modules/files)
    - imported_by: What files import this file

    This enables bidirectional navigation in the import tree UI.
    """
    project_root = Path("/home/kali/Desktop/AutoBot")
    python_files = list(project_root.rglob("*.py"))

    # Filter out unwanted directories
    excluded_dirs = {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "archive",
        "dist",
        "build",
    }
    python_files = [
        f
        for f in python_files
        if not any(excluded in f.parts for excluded in excluded_dirs)
    ]

    # Standard library modules (to mark as external)
    stdlib_modules = {
        "os", "sys", "re", "json", "time", "datetime", "logging", "asyncio",
        "pathlib", "typing", "collections", "functools", "itertools", "subprocess",
        "threading", "multiprocessing", "uuid", "hashlib", "base64", "io",
        "contextlib", "abc", "dataclasses", "enum", "copy", "math", "random",
        "socket", "http", "urllib", "traceback", "inspect", "ast", "shutil",
        "tempfile", "warnings", "signal", "argparse", "pickle", "csv", "sqlite3",
        "email", "html", "xml", "struct", "array", "queue", "heapq", "bisect",
        "weakref", "types", "operator", "string", "textwrap", "codecs",
    }

    # Data structures
    file_imports: Dict[str, List[Dict]] = {}  # file -> list of imports
    file_imported_by: Dict[str, List[Dict]] = {}  # file -> list of importers
    module_to_file: Dict[str, str] = {}  # module path -> file path

    # First pass: Build module to file mapping
    for py_file in python_files[:500]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            # Convert file path to module path (e.g., src/utils/redis_client.py -> src.utils.redis_client)
            module_path = rel_path.replace("/", ".").replace(".py", "")
            module_to_file[module_path] = rel_path

            # Also map shorter versions (utils.redis_client, redis_client)
            parts = module_path.split(".")
            for i in range(len(parts)):
                short_module = ".".join(parts[i:])
                if short_module not in module_to_file:
                    module_to_file[short_module] = rel_path
        except Exception:
            continue

    # Second pass: Analyze imports
    for py_file in python_files[:500]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            file_imports[rel_path] = []

            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                import_info = None

                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name
                        base_module = module_name.split(".")[0]
                        is_external = base_module in stdlib_modules or base_module not in ["src", "backend", "autobot"]
                        target_file = module_to_file.get(module_name)

                        import_info = {
                            "module": module_name,
                            "file": target_file,
                            "is_external": is_external and target_file is None,
                        }
                        file_imports[rel_path].append(import_info)

                        # Track imported_by relationship for internal files
                        if target_file and target_file != rel_path:
                            if target_file not in file_imported_by:
                                file_imported_by[target_file] = []
                            file_imported_by[target_file].append({
                                "file": rel_path,
                                "module": module_name,
                            })

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module
                        base_module = module_name.split(".")[0]
                        is_external = base_module in stdlib_modules or base_module not in ["src", "backend", "autobot"]
                        target_file = module_to_file.get(module_name)

                        import_info = {
                            "module": module_name,
                            "file": target_file,
                            "is_external": is_external and target_file is None,
                        }
                        file_imports[rel_path].append(import_info)

                        # Track imported_by relationship for internal files
                        if target_file and target_file != rel_path:
                            if target_file not in file_imported_by:
                                file_imported_by[target_file] = []
                            file_imported_by[target_file].append({
                                "file": rel_path,
                                "module": module_name,
                            })

        except Exception as e:
            logger.debug(f"Could not analyze {py_file}: {e}")
            continue

    # Build result with bidirectional relationships
    import_tree = []
    all_files = set(file_imports.keys()) | set(file_imported_by.keys())

    for file_path in sorted(all_files):
        # Deduplicate imports
        imports = file_imports.get(file_path, [])
        seen_modules = set()
        unique_imports = []
        for imp in imports:
            if imp["module"] not in seen_modules:
                seen_modules.add(imp["module"])
                unique_imports.append(imp)

        import_tree.append({
            "path": file_path,
            "imports": unique_imports,
            "imported_by": file_imported_by.get(file_path, []),
        })

    # Sort by connectivity (most connected files first)
    import_tree.sort(
        key=lambda x: len(x["imports"]) + len(x["imported_by"]),
        reverse=True
    )

    return JSONResponse({
        "status": "success",
        "import_tree": import_tree,
        "summary": {
            "total_files": len(import_tree),
            "total_import_relationships": sum(len(f["imports"]) for f in import_tree),
            "most_imported_files": [
                {"file": f["path"], "count": len(f["imported_by"])}
                for f in sorted(import_tree, key=lambda x: len(x["imported_by"]), reverse=True)[:10]
            ],
            "most_importing_files": [
                {"file": f["path"], "count": len(f["imports"])}
                for f in sorted(import_tree, key=lambda x: len(x["imports"]), reverse=True)[:10]
            ],
        },
    })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_call_graph",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/call-graph")
async def get_call_graph():
    """
    Get function call graph for visualization.

    Analyzes Python files to extract:
    - Function definitions (nodes)
    - Function calls within functions (edges)
    - Call depth and frequency metrics

    Returns data suitable for network/graph visualization.
    """
    project_root = Path("/home/kali/Desktop/AutoBot")
    python_files = list(project_root.rglob("*.py"))

    # Filter out unwanted directories
    excluded_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "env", ".env", "archive", "dist", "build",
    }
    python_files = [
        f for f in python_files
        if not any(excluded in f.parts for excluded in excluded_dirs)
    ]

    # Data structures
    functions: Dict[str, Dict] = {}  # function_id -> function info
    call_edges: List[Dict] = []  # caller -> callee relationships
    builtin_funcs = {
        "print", "len", "range", "str", "int", "float", "list", "dict", "set",
        "tuple", "bool", "type", "isinstance", "hasattr", "getattr", "setattr",
        "open", "sorted", "enumerate", "zip", "map", "filter", "any", "all",
        "min", "max", "sum", "abs", "round", "format", "input", "super",
    }

    class FunctionCallVisitor(ast.NodeVisitor):
        """AST visitor to extract function definitions and calls."""

        def __init__(self, file_path: str, module_path: str):
            self.file_path = file_path
            self.module_path = module_path
            self.current_class = None
            self.current_function = None
            self.function_stack = []

        def visit_ClassDef(self, node):
            old_class = self.current_class
            self.current_class = node.name
            self.generic_visit(node)
            self.current_class = old_class

        def visit_FunctionDef(self, node):
            self._process_function(node)

        def visit_AsyncFunctionDef(self, node):
            self._process_function(node)

        def _process_function(self, node):
            # Build function ID
            if self.current_class:
                func_id = f"{self.module_path}.{self.current_class}.{node.name}"
                full_name = f"{self.current_class}.{node.name}"
            else:
                func_id = f"{self.module_path}.{node.name}"
                full_name = node.name

            # Store function info
            functions[func_id] = {
                "id": func_id,
                "name": node.name,
                "full_name": full_name,
                "file": self.file_path,
                "module": self.module_path,
                "class": self.current_class,
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "args": len(node.args.args),
                "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
            }

            # Track calls within this function
            old_function = self.current_function
            self.current_function = func_id
            self.function_stack.append(func_id)
            self.generic_visit(node)
            self.function_stack.pop() if self.function_stack else None
            self.current_function = old_function

        def _get_decorator_name(self, decorator):
            if isinstance(decorator, ast.Name):
                return decorator.id
            elif isinstance(decorator, ast.Attribute):
                return decorator.attr
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    return decorator.func.id
                elif isinstance(decorator.func, ast.Attribute):
                    return decorator.func.attr
            return "unknown"

        def visit_Call(self, node):
            if not self.current_function:
                self.generic_visit(node)
                return

            callee_name = None

            # Get the function being called
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name and callee_name not in builtin_funcs:
                # Look for matching function in our registry
                callee_id = None

                # Try module-level function
                possible_id = f"{self.module_path}.{callee_name}"
                if possible_id in functions:
                    callee_id = possible_id

                # Try class method if in a class
                if not callee_id and self.current_class:
                    possible_id = f"{self.module_path}.{self.current_class}.{callee_name}"
                    if possible_id in functions:
                        callee_id = possible_id

                # Create edge even if callee not fully resolved
                call_edges.append({
                    "from": self.current_function,
                    "to": callee_id or callee_name,
                    "to_name": callee_name,
                    "resolved": callee_id is not None,
                    "line": node.lineno,
                })

            self.generic_visit(node)

    # Analyze files (limit for performance)
    for py_file in python_files[:300]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            module_path = rel_path.replace("/", ".").replace(".py", "")

            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            visitor = FunctionCallVisitor(rel_path, module_path)
            visitor.visit(tree)

        except Exception as e:
            logger.debug(f"Could not analyze {py_file}: {e}")
            continue

    # Build graph nodes (only functions with connections)
    connected_funcs = set()
    for edge in call_edges:
        connected_funcs.add(edge["from"])
        if edge["resolved"]:
            connected_funcs.add(edge["to"])

    nodes = []
    for func_id, info in functions.items():
        if func_id in connected_funcs:
            nodes.append({
                "id": func_id,
                "name": info["name"],
                "full_name": info["full_name"],
                "module": info["module"],
                "class": info["class"],
                "file": info["file"],
                "line": info["line"],
                "is_async": info["is_async"],
            })

    # Count call frequency
    call_counts = {}
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        call_counts[key] = call_counts.get(key, 0) + 1

    # Deduplicate edges with count
    unique_edges = []
    seen_edges = set()
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append({
                "from": edge["from"],
                "to": edge["to"],
                "to_name": edge["to_name"],
                "resolved": edge["resolved"],
                "count": call_counts[key],
            })

    # Calculate metrics
    outgoing_calls = {}
    incoming_calls = {}
    for edge in unique_edges:
        outgoing_calls[edge["from"]] = outgoing_calls.get(edge["from"], 0) + edge["count"]
        if edge["resolved"]:
            incoming_calls[edge["to"]] = incoming_calls.get(edge["to"], 0) + edge["count"]

    # Top callers and callees
    top_callers = sorted(
        [{"function": k, "calls": v} for k, v in outgoing_calls.items()],
        key=lambda x: x["calls"], reverse=True
    )[:10]

    top_called = sorted(
        [{"function": k, "calls": v} for k, v in incoming_calls.items()],
        key=lambda x: x["calls"], reverse=True
    )[:10]

    return JSONResponse({
        "status": "success",
        "call_graph": {
            "nodes": nodes[:500],  # Limit for UI performance
            "edges": unique_edges[:2000],
        },
        "summary": {
            "total_functions": len(functions),
            "connected_functions": len(nodes),
            "total_call_relationships": len(unique_edges),
            "resolved_calls": len([e for e in unique_edges if e["resolved"]]),
            "unresolved_calls": len([e for e in unique_edges if not e["resolved"]]),
            "top_callers": top_callers,
            "most_called": top_called,
        },
    })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_declarations",
    error_code_prefix="CODEBASE",
)
@router.get("/declarations")
async def get_code_declarations(declaration_type: Optional[str] = None):
    """Get code declarations (functions, classes, variables) detected during analysis"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_declarations = []

    if code_collection:
        try:
            # Query ChromaDB for functions and classes
            where_filter = {"type": {"$in": ["function", "class"]}}

            results = code_collection.get(where=where_filter, include=["metadatas"])

            # Extract declarations from metadata
            for metadata in results.get("metadatas", []):
                decl = {
                    "name": metadata.get("name", ""),
                    "type": metadata.get("type", ""),
                    "file_path": metadata.get("file_path", ""),
                    "line_number": (
                        int(metadata.get("start_line", 0))
                        if metadata.get("start_line")
                        else 0
                    ),
                    "usage_count": 1,  # Default, can be calculated later
                    "is_exported": True,  # Default
                    "parameters": (
                        metadata.get("parameters", "").split(",")
                        if metadata.get("parameters")
                        else []
                    ),
                }
                all_declarations.append(decl)

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_declarations)} declarations from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, returning empty declarations"
            )
            # Declarations don't exist in old Redis structure, so just return empty
            storage_type = "chromadb"

    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "declarations": [],
            }
        )

    # Count by type
    functions = sum(1 for d in all_declarations if d.get("type") == "function")
    classes = sum(1 for d in all_declarations if d.get("type") == "class")
    variables = sum(1 for d in all_declarations if d.get("type") == "variable")

    # Sort by usage count (most used first)
    all_declarations.sort(key=lambda x: x.get("usage_count", 0), reverse=True)

    return JSONResponse(
        {
            "status": "success",
            "declarations": all_declarations,
            "total_count": len(all_declarations),
            "functions": functions,
            "classes": classes,
            "variables": variables,
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_duplicate_code",
    error_code_prefix="CODEBASE",
)
@router.get("/duplicates")
async def get_duplicate_code():
    """Get duplicate code detected during analysis (using semantic similarity in ChromaDB)"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_duplicates = []

    if code_collection:
        try:
            # Query ChromaDB for duplicate markers
            # Note: Duplicates will be detected via semantic similarity when we regenerate
            results = code_collection.get(
                where={"type": "duplicate"}, include=["metadatas"]
            )

            # Extract duplicates from metadata
            for metadata in results.get("metadatas", []):
                duplicate = {
                    "code_snippet": metadata.get("code_snippet", ""),
                    "files": (
                        metadata.get("files", "").split(",")
                        if metadata.get("files")
                        else []
                    ),
                    "similarity_score": (
                        float(metadata.get("similarity_score", 0.0))
                        if metadata.get("similarity_score")
                        else 0.0
                    ),
                    "line_numbers": metadata.get("line_numbers", ""),
                }
                all_duplicates.append(duplicate)

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_duplicates)} duplicates from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, returning empty duplicates"
            )
            # Duplicates don't exist yet, will be generated during reindexing
            storage_type = "chromadb"

    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "duplicates": [],
            }
        )

    # Sort by number of files affected (most duplicated first)
    all_duplicates.sort(key=lambda x: len(x.get("files", [])), reverse=True)

    return JSONResponse(
        {
            "status": "success",
            "duplicates": all_duplicates,
            "total_count": len(all_duplicates),
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_codebase_cache",
    error_code_prefix="CODEBASE",
)
@router.delete("/cache")
async def clear_codebase_cache():
    """Clear codebase analysis cache from storage"""
    redis_client = await get_redis_connection()

    if redis_client:
        # Get all codebase keys
        keys_to_delete = []
        for key in redis_client.scan_iter(match="codebase:*"):
            keys_to_delete.append(key)

        if keys_to_delete:
            redis_client.delete(*keys_to_delete)

        storage_type = "redis"
    else:
        # Clear in-memory storage
        if _in_memory_storage:
            keys_to_delete = []
            for key in _in_memory_storage.scan_iter("codebase:*"):
                keys_to_delete.append(key)

            _in_memory_storage.delete(*keys_to_delete)
            deleted_count = len(keys_to_delete)
        else:
            deleted_count = 0

        storage_type = "memory"

    return JSONResponse(
        {
            "status": "success",
            "message": (
                f"Cleared {len(keys_to_delete) if redis_client else deleted_count} "
                f"cache entries from {storage_type}"
            ),
            "deleted_keys": len(keys_to_delete) if redis_client else deleted_count,
            "storage_type": storage_type,
        }
    )
