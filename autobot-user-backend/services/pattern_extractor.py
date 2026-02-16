# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern Extractor Service (Issue #903)

Extracts code patterns from AutoBot codebase for ML training and completion.
"""

import ast
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class PatternExtractor:
    """
    Extract completion patterns from codebase.

    Analyzes Python and TypeScript/Vue code to identify common patterns:
    - Function signatures and implementations
    - Error handling patterns
    - API usage patterns
    - Framework-specific patterns (FastAPI, Vue composables)
    """

    def __init__(self, base_path: str = "/home/kali/Desktop/AutoBot"):
        self.base_path = Path(base_path)
        self.redis_client = get_redis_client(async_client=False, database="main")
        self.patterns: Dict[str, List[Dict]] = defaultdict(list)

    def extract_from_codebase(
        self, languages: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Extract patterns from entire codebase.

        Args:
            languages: List of languages to extract (python, typescript, vue)
                      If None, extracts all supported languages.

        Returns:
            Dictionary of patterns grouped by type
        """
        languages = languages or ["python", "typescript", "vue"]
        self.patterns = defaultdict(list)

        if "python" in languages:
            self._extract_python_patterns()

        if "typescript" in languages or "vue" in languages:
            self._extract_typescript_vue_patterns()

        logger.info(
            f"Extracted {sum(len(p) for p in self.patterns.values())} "
            f"patterns across {len(self.patterns)} categories"
        )
        return dict(self.patterns)

    def _extract_python_patterns(self) -> None:
        """Extract patterns from Python files."""
        python_dirs = [
            self.base_path / "autobot-user-backend",
            self.base_path / "autobot-slm-backend",
            self.base_path / "autobot-shared",
        ]

        for base_dir in python_dirs:
            if not base_dir.exists():
                continue

            for py_file in base_dir.rglob("*.py"):
                # Skip test files, migrations, and venv
                if any(
                    skip in str(py_file)
                    for skip in ["test", "venv", "migrations", "__pycache__"]
                ):
                    continue

                try:
                    self._analyze_python_file(py_file)
                except Exception as e:
                    logger.debug(f"Failed to analyze {py_file}: {e}")

    def _analyze_python_file(self, file_path: Path) -> None:
        """Analyze a single Python file for patterns."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        # Extract function patterns
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function_pattern(node, file_path, content)

            # Extract try/except patterns
            if isinstance(node, ast.Try):
                self._extract_error_handling_pattern(node, file_path)

            # Extract API usage patterns (FastAPI routes)
            if isinstance(node, ast.FunctionDef):
                self._extract_api_pattern(node, file_path, content)

    def _extract_function_pattern(
        self, node: ast.FunctionDef, file_path: Path, content: str
    ) -> None:
        """Extract function signature and common implementation patterns."""
        # Get function signature
        args = []
        for arg in node.args.args:
            annotation = (
                ast.unparse(arg.annotation) if arg.annotation else "Any"
            )
            args.append(f"{arg.arg}: {annotation}")

        return_annotation = (
            ast.unparse(node.returns) if node.returns else "Any"
        )

        signature = f"def {node.name}({', '.join(args)}) -> {return_annotation}"

        # Get function body
        body_lines = ast.get_source_segment(content, node)
        if not body_lines or len(body_lines) > 500:  # Skip very long functions
            return

        # Determine category
        category = self._categorize_function(node, file_path)

        # Build context
        context = {
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "docstring": ast.get_docstring(node),
            "imports": [],  # Would need full file analysis
        }

        pattern = {
            "pattern_type": "function",
            "language": "python",
            "category": category,
            "signature": signature,
            "body": body_lines,
            "file_path": str(file_path.relative_to(self.base_path)),
            "line_number": node.lineno,
            "context": context,
        }

        self.patterns["function"].append(pattern)

    def _extract_error_handling_pattern(
        self, node: ast.Try, file_path: Path
    ) -> None:
        """Extract try/except error handling patterns."""
        for handler in node.handlers:
            exception_type = (
                ast.unparse(handler.type) if handler.type else "Exception"
            )
            handler_name = handler.name or "_"

            # Get handler body (simplified)
            handler_body = (
                ast.unparse(handler.body[0])
                if handler.body
                else "pass"
            )

            pattern = {
                "pattern_type": "error_handling",
                "language": "python",
                "category": exception_type,
                "signature": f"except {exception_type} as {handler_name}",
                "body": handler_body,
                "file_path": str(file_path.relative_to(self.base_path)),
                "line_number": handler.lineno,
                "context": {"exception_type": exception_type},
            }

            self.patterns["error_handling"].append(pattern)

    def _extract_api_pattern(
        self, node: ast.FunctionDef, file_path: Path, content: str
    ) -> None:
        """Extract FastAPI route patterns."""
        # Check if function is a FastAPI route
        route_decorators = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func_name = ast.unparse(decorator.func)
                if any(
                    method in func_name
                    for method in ["get", "post", "put", "delete", "patch"]
                ):
                    route_decorators.append(ast.unparse(decorator))

        if not route_decorators:
            return

        # This is a FastAPI route
        body_lines = ast.get_source_segment(content, node)
        if not body_lines:
            return

        pattern = {
            "pattern_type": "api_route",
            "language": "python",
            "category": "fastapi",
            "signature": f"@{route_decorators[0]}\ndef {node.name}",
            "body": body_lines,
            "file_path": str(file_path.relative_to(self.base_path)),
            "line_number": node.lineno,
            "context": {
                "decorators": route_decorators,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            },
        }

        self.patterns["api_route"].append(pattern)

    def _categorize_function(
        self, node: ast.FunctionDef, file_path: Path
    ) -> str:
        """Categorize function based on name, decorators, and file path."""
        func_name = node.name.lower()
        file_str = str(file_path).lower()

        # Framework-specific patterns
        if "redis" in file_str or "redis" in func_name:
            return "redis"
        if "fastapi" in file_str or any(
            d for d in node.decorator_list if "router" in ast.unparse(d).lower()
        ):
            return "fastapi"
        if "pydantic" in file_str or "BaseModel" in ast.unparse(node):
            return "pydantic"

        # General patterns
        if func_name.startswith("test_"):
            return "test"
        if func_name.startswith("_"):
            return "private"
        if "async" in func_name or isinstance(node, ast.AsyncFunctionDef):
            return "async"

        return "general"

    def _extract_typescript_vue_patterns(self) -> None:
        """Extract patterns from TypeScript and Vue files."""
        frontend_dirs = [
            self.base_path / "autobot-user-frontend" / "src",
            self.base_path / "autobot-slm-frontend" / "src",
        ]

        for base_dir in frontend_dirs:
            if not base_dir.exists():
                continue

            # TypeScript files
            for ts_file in base_dir.rglob("*.ts"):
                if "node_modules" in str(ts_file):
                    continue
                try:
                    self._analyze_typescript_file(ts_file)
                except Exception as e:
                    logger.debug(f"Failed to analyze {ts_file}: {e}")

            # Vue files
            for vue_file in base_dir.rglob("*.vue"):
                try:
                    self._analyze_vue_file(vue_file)
                except Exception as e:
                    logger.debug(f"Failed to analyze {vue_file}: {e}")

    def _analyze_typescript_file(self, file_path: Path) -> None:
        """Analyze TypeScript file using regex patterns."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract composable functions
        composable_pattern = r"export\s+function\s+(use[A-Z]\w+)\s*\([^)]*\)\s*:\s*(\{[^}]+\})"
        for match in re.finditer(composable_pattern, content):
            func_name, return_type = match.groups()
            pattern = {
                "pattern_type": "composable",
                "language": "typescript",
                "category": "vue_composable",
                "signature": f"export function {func_name}",
                "body": match.group(0)[:200],  # First 200 chars
                "file_path": str(file_path.relative_to(self.base_path)),
                "line_number": content[: match.start()].count("\n") + 1,
                "context": {"return_type": return_type},
            }
            self.patterns["composable"].append(pattern)

        # Extract interface patterns
        interface_pattern = r"export\s+interface\s+(\w+)\s*\{([^}]+)\}"
        for match in re.finditer(interface_pattern, content, re.MULTILINE):
            interface_name, body = match.groups()
            pattern = {
                "pattern_type": "interface",
                "language": "typescript",
                "category": "typescript",
                "signature": f"export interface {interface_name}",
                "body": match.group(0),
                "file_path": str(file_path.relative_to(self.base_path)),
                "line_number": content[: match.start()].count("\n") + 1,
                "context": {},
            }
            self.patterns["interface"].append(pattern)

    def _analyze_vue_file(self, file_path: Path) -> None:
        """Analyze Vue file for component patterns."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract script setup section
        script_pattern = r"<script\s+setup\s+lang=[\"']ts[\"']>(.*?)</script>"
        match = re.search(script_pattern, content, re.DOTALL)
        if not match:
            return

        script_content = match.group(1)

        # Extract props definitions
        props_pattern = r"const\s+props\s*=\s*defineProps<(.+?)>\(\)"
        props_match = re.search(props_pattern, script_content, re.DOTALL)
        if props_match:
            pattern = {
                "pattern_type": "vue_props",
                "language": "vue",
                "category": "vue_component",
                "signature": "defineProps",
                "body": props_match.group(0),
                "file_path": str(file_path.relative_to(self.base_path)),
                "line_number": 1,
                "context": {},
            }
            self.patterns["vue_props"].append(pattern)

    def cache_hot_patterns(self, top_n: int = 100) -> None:
        """Cache most frequent patterns to Redis for fast lookup."""
        for pattern_type, patterns in self.patterns.items():
            # Sort by frequency and take top N
            sorted_patterns = sorted(
                patterns, key=lambda p: p.get("frequency", 1), reverse=True
            )[:top_n]

            # Cache to Redis
            redis_key = f"hot_patterns:{pattern_type}"
            self.redis_client.set(
                redis_key,
                json.dumps(sorted_patterns),
                ex=86400,  # 24 hour TTL
            )

        logger.info(f"Cached top {top_n} patterns for {len(self.patterns)} types")

    def get_statistics(self) -> Dict[str, int]:
        """Get extraction statistics."""
        return {
            pattern_type: len(patterns)
            for pattern_type, patterns in self.patterns.items()
        }
