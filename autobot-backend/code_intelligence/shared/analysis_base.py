# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared skeleton for the Python regex+AST code analyzers (Issue #12660).

``code_intelligence.security.SecurityAnalyzer`` and
``code_intelligence.performance_analysis.PerformanceAnalyzer`` independently
reimplemented the same ``__init__``/``analyze_file``/``analyze_directory``/
``analyze_directory_async``/``_regex_analysis``/``_should_exclude``/
``cache_analysis_results``/``get_cached_analysis`` skeleton, differing only in
the AST visitor class, the list of regex ``_check_*`` methods run, and the
semantic-analysis collection/cache names.

This module hosts that skeleton exactly once. Concrete analyzers subclass
``BaseCodeAnalyzer`` and only provide the domain-specific hooks documented on
the class.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

# Issue #554: Import analytics infrastructure for semantic analysis. Guarded
# once here (was duplicated verbatim in both security/analyzer.py and
# performance_analysis/analyzer.py); both re-export these names for backward
# compatibility with existing package __init__ imports.
try:
    from code_intelligence.analytics_infrastructure import (
        SIMILARITY_MEDIUM,
        SemanticAnalysisMixin,
    )

    HAS_ANALYTICS_INFRASTRUCTURE = True
except ImportError:
    HAS_ANALYTICS_INFRASTRUCTURE = False
    SemanticAnalysisMixin = object
    SIMILARITY_MEDIUM = 0.7

# Issue #607: Import shared caches for performance optimization
try:
    from code_intelligence.shared.ast_cache import get_ast_with_content

    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = get_logger(__name__)

# Issue #12660: Default exclusion patterns shared by every analyzer that
# subclasses BaseCodeAnalyzer (verbatim match of the previous per-class
# defaults in security/analyzer.py and performance_analysis/analyzer.py).
DEFAULT_EXCLUDE_PATTERNS: List[str] = [
    "venv",
    "node_modules",
    ".git",
    "__pycache__",
    "*.pyc",
    "test_*",
    "*_test.py",
    "archives",
    "migrations",
]


class BaseCodeAnalyzer(SemanticAnalysisMixin):
    """Shared scan/cache skeleton for regex+AST Python code analyzers.

    Subclasses MUST override:
        - ``AST_VISITOR_CLASS``: the ``ast.NodeVisitor`` subclass instantiated
          by :meth:`analyze_file`.
        - ``SEMANTIC_COLLECTION_NAME``: vector-store collection name passed to
          ``_init_infrastructure`` when semantic analysis is enabled.
        - ``CACHE_PREFIX``: Redis cache-key prefix used by
          :meth:`cache_analysis_results` / :meth:`get_cached_analysis`.
        - :meth:`_get_checkers`: ordered list of bound ``_check_*`` methods
          run by :meth:`_regex_analysis`.
        - :meth:`_find_semantic_duplicates`: domain-specific semantic
          duplicate-finder (each domain uses different ``metadata_keys``).

    Subclasses are expected to still own ``get_summary``/``generate_report``/
    ``_generate_markdown_report`` — those are genuine per-domain analysis
    specifics (field names, scoring), not skeleton.
    """

    AST_VISITOR_CLASS: type | None = None
    SEMANTIC_COLLECTION_NAME: str = ""
    CACHE_PREFIX: str = ""

    def __init__(
        self,
        project_root: str | None = None,
        exclude_patterns: List[str] | None = None,
        use_semantic_analysis: bool = False,
        use_cache: bool = True,
        use_shared_cache: bool = True,
    ):
        """Initialize the analyzer with project root and exclusion patterns."""
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.exclude_patterns = exclude_patterns or list(DEFAULT_EXCLUDE_PATTERNS)
        self.results: List[Any] = []
        self.total_files_scanned: int = 0
        self.use_semantic_analysis = use_semantic_analysis and HAS_ANALYTICS_INFRASTRUCTURE
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

        if self.use_semantic_analysis:
            self._init_infrastructure(
                collection_name=self.SEMANTIC_COLLECTION_NAME,
                use_llm=True,
                use_cache=use_cache,
                redis_database="analytics",
            )

    def analyze_file(self, file_path: str) -> List[Any]:
        """Analyze a single file for this analyzer's domain-specific findings."""
        findings: List[Any] = []
        path = Path(file_path)

        if not path.exists() or not path.suffix == ".py":
            return findings

        try:
            if self.use_shared_cache:
                tree, content = get_ast_with_content(file_path)
                lines = content.split("\n") if content else []
            else:
                content = path.read_text(encoding="utf-8")
                lines = content.split("\n")
                try:
                    tree = ast.parse(content)
                except SyntaxError:
                    tree = None

            if tree is not None:
                visitor = self.AST_VISITOR_CLASS(str(path), lines)
                visitor.visit(tree)
                findings.extend(visitor.findings)
            else:
                logger.warning("Syntax error in %s, skipping AST analysis", file_path)

            if content:
                findings.extend(self._regex_analysis(str(path), content, lines))

        except Exception as e:
            logger.error("Error analyzing %s: %s", file_path, e)

        return findings

    def _get_checkers(self) -> List[Callable[[str, str, List[str]], List[Any]]]:
        """Hook: ordered bound ``_check_*`` methods run by :meth:`_regex_analysis`."""
        raise NotImplementedError

    def _regex_analysis(self, file_path: str, content: str, lines: List[str]) -> List[Any]:
        """Run this analyzer's regex-based checkers and collect findings."""
        findings: List[Any] = []
        for checker in self._get_checkers():
            findings.extend(checker(file_path, content, lines))
        return findings

    def analyze_directory(self, directory: str | None = None) -> List[Any]:
        """Analyze all Python files in a directory."""
        target = Path(directory) if directory else self.project_root
        self.results = []
        self.total_files_scanned = 0

        for py_file in target.rglob("*.py"):
            if self._should_exclude(py_file):
                continue

            self.total_files_scanned += 1
            findings = self.analyze_file(str(py_file))
            self.results.extend(findings)

        return self.results

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        path_str = str(path)
        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        return False

    async def _find_semantic_duplicates(self, items: List[Any]) -> List[Dict[str, Any]]:
        """Hook: domain-specific semantic duplicate-finder (``metadata_keys`` differ)."""
        raise NotImplementedError

    async def analyze_directory_async(
        self,
        directory: str | None = None,
        find_semantic_duplicates: bool = True,
    ) -> Dict[str, Any]:
        """Analyze a directory with optional semantic analysis."""
        start_time = time.time()
        results = self.analyze_directory(directory)

        result: Dict[str, Any] = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
            "semantic_duplicates": [],
            "infrastructure_metrics": {},
        }

        if self.use_semantic_analysis and find_semantic_duplicates:
            semantic_dups = await self._find_semantic_duplicates(results)
            result["semantic_duplicates"] = semantic_dups
            result["infrastructure_metrics"] = self._get_infrastructure_metrics()

        result["analysis_time_ms"] = (time.time() - start_time) * 1000
        return result

    async def cache_analysis_results(self, directory: str, results: List[Any]) -> bool:
        """Cache analysis results in Redis for faster retrieval."""
        if not self.use_semantic_analysis:
            return False

        cache_key = self._generate_content_hash(directory)
        results_dict = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
        }

        return await self._cache_result(
            key=cache_key,
            result=results_dict,
            prefix=self.CACHE_PREFIX,
        )

    async def get_cached_analysis(self, directory: str) -> Dict[str, Any] | None:
        """Get cached analysis results from Redis."""
        if not self.use_semantic_analysis:
            return None

        cache_key = self._generate_content_hash(directory)
        return await self._get_cached_result(
            key=cache_key,
            prefix=self.CACHE_PREFIX,
        )
