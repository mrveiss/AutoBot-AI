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
    root_path: Optional[str] = None, progress_callback: Optional[callable] = None
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

        # Initialize task status
        indexing_tasks[task_id] = {
            "status": "running",
            "progress": {
                "current": 0,
                "total": 0,
                "percent": 0,
                "current_file": "Initializing...",
                "operation": "Starting indexing",
            },
            "result": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
        }

        # Progress callback function
        async def update_progress(
            operation: str, current: int, total: int, current_file: str
        ):
            percent = int((current / total * 100)) if total > 0 else 0
            indexing_tasks[task_id]["progress"] = {
                "current": current,
                "total": total,
                "percent": percent,
                "current_file": current_file,
                "operation": operation,
            }
            logger.debug(
                f"[Task {task_id}] Progress: {operation} - {current}/{total} ({percent}%)"
            )

        # Scan the codebase with progress tracking
        analysis_results = await scan_codebase(
            root_path, progress_callback=update_progress
        )

        # Update progress for ChromaDB storage phase
        await update_progress(
            operation="Preparing ChromaDB storage",
            current=0,
            total=1,
            current_file="Connecting to ChromaDB...",
        )

        # Store in ChromaDB (run in thread to avoid blocking event loop)
        code_collection = await asyncio.to_thread(get_code_collection)

        if code_collection:
            storage_type = "chromadb"

            # Clear existing data in collection
            await update_progress(
                operation="Clearing old ChromaDB data",
                current=0,
                total=1,
                current_file="Removing existing entries...",
            )

            try:
                # Run blocking ChromaDB operations in thread pool
                existing_data = await asyncio.to_thread(code_collection.get)
                existing_ids = existing_data["ids"]
                if existing_ids:
                    await asyncio.to_thread(code_collection.delete, ids=existing_ids)
                    logger.info(
                        f"[Task {task_id}] Cleared {len(existing_ids)} existing items from ChromaDB"
                    )
            except Exception as e:
                logger.warning(f"[Task {task_id}] Error clearing collection: {e}")

            # Prepare batch data for ChromaDB
            batch_ids = []
            batch_documents = []
            batch_metadatas = []

            # Store functions
            total_items_to_store = (
                len(analysis_results["all_functions"])
                + len(analysis_results["all_classes"])
                + len(analysis_results["all_problems"])
                + 1  # stats
            )
            items_prepared = 0

            await update_progress(
                operation="Storing functions",
                current=0,
                total=total_items_to_store,
                current_file="Processing functions...",
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

            # Store problems
            await update_progress(
                operation="Storing problems",
                current=items_prepared,
                total=total_items_to_store,
                current_file="Processing code problems...",
            )

            for idx, problem in enumerate(analysis_results["all_problems"]):
                doc_text = """
Problem: {problem.get('type', 'unknown')}
Severity: {problem.get('severity', 'unknown')}
File: {problem.get('file_path', 'unknown')}
Line: {problem.get('line', 0)}
Description: {problem.get('description', 'No description')}
Suggestion: {problem.get('suggestion', 'No suggestion')}
                """.strip()

                batch_ids.append(f"problem_{idx}")
                batch_documents.append(doc_text)
                batch_metadatas.append(
                    {
                        "type": "problem",
                        "problem_type": problem.get("type", ""),
                        "severity": problem.get("severity", ""),
                        "file_path": problem.get("file_path", ""),
                        "line_number": str(problem.get("line", 0)),
                        "description": problem.get("description", ""),
                        "suggestion": problem.get("suggestion", ""),
                    }
                )

                items_prepared += 1
                if items_prepared % 50 == 0:
                    await update_progress(
                        operation="Storing problems",
                        current=items_prepared,
                        total=total_items_to_store,
                        current_file=f"Problem {idx+1}/{len(analysis_results['all_problems'])}",
                    )

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

            # Add all to ChromaDB in batches (ChromaDB has max batch size limit)
            if batch_ids:
                BATCH_SIZE = (
                    5000  # ChromaDB max batch size is ~5461, use 5000 for safety
                )
                total_items = len(batch_ids)
                items_stored = 0

                await update_progress(
                    operation="Writing to ChromaDB",
                    current=0,
                    total=total_items,
                    current_file="Batch storage in progress...",
                )

                for i in range(0, total_items, BATCH_SIZE):
                    batch_slice_ids = batch_ids[i : i + BATCH_SIZE]
                    batch_slice_docs = batch_documents[i : i + BATCH_SIZE]
                    batch_slice_metas = batch_metadatas[i : i + BATCH_SIZE]

                    # Run blocking ChromaDB add in thread pool
                    await asyncio.to_thread(
                        code_collection.add,
                        ids=batch_slice_ids,
                        documents=batch_slice_docs,
                        metadatas=batch_slice_metas,
                    )
                    items_stored += len(batch_slice_ids)

                    batch_num = i // BATCH_SIZE + 1
                    total_batches = (total_items + BATCH_SIZE - 1) // BATCH_SIZE
                    await update_progress(
                        operation="Writing to ChromaDB",
                        current=items_stored,
                        total=total_items,
                        current_file=f"Batch {batch_num}/{total_batches}"
                    )

                    logger.info(
                        f"[Task {task_id}] Stored batch {batch_num}: "
                        f"{len(batch_slice_ids)} items ({items_stored}/{total_items})"
                    )

                logger.info(
                    f"[Task {task_id}] ✅ Stored total of {items_stored} items in ChromaDB"
                )
        else:
            storage_type = "failed"
            raise Exception("ChromaDB connection failed")

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
    """
    logger.info("✅ ENTRY: index_codebase endpoint called!")
    # Always use project root
    project_root = Path(__file__).parent.parent.parent
    root_path = str(project_root)
    logger.info(f"📁 project_root = {root_path}")

    # Generate unique task ID
    task_id = str(uuid.uuid4())
    logger.info(f"🆔 Generated task_id = {task_id}")

    # Add async background task using asyncio and store reference
    logger.info("🔄 About to create_task")
    task = asyncio.create_task(do_indexing_with_progress(task_id, root_path))
    logger.info(f"✅ Task created: {task}")
    _active_tasks[task_id] = task
    logger.info("💾 Task stored in _active_tasks")

    # Clean up task reference when done
    def cleanup_task(t):
        _active_tasks.pop(task_id, None)

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
