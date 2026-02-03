# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Analyzer

Main entry point for anti-pattern detection. Coordinates all detector
modules and provides a unified analysis interface.

Part of Issue #381 - God Class Refactoring
Issue #554 - Added Vector/Redis/LLM infrastructure for semantic analysis
Issue #607 - Uses shared FileListCache and ASTCache for performance
"""

import ast
import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .detectors import (
    BloaterDetector,
    CouplerDetector,
    DispensableDetector,
    NamingDetector,
)
from .models import AnalysisReport, AntiPatternResult
from .types import DEFAULT_IGNORE_PATTERNS, Thresholds

# Issue #554: Import analytics infrastructure for semantic analysis
try:
    from src.code_intelligence.analytics_infrastructure import (
        SIMILARITY_MEDIUM,
        SemanticAnalysisMixin,
    )

    HAS_ANALYTICS_INFRASTRUCTURE = True
except ImportError:
    HAS_ANALYTICS_INFRASTRUCTURE = False
    SemanticAnalysisMixin = object  # Fallback to object if not available

# Issue #607: Import shared caches for performance optimization
try:
    from src.code_intelligence.shared.ast_cache import get_ast_with_content
    from src.code_intelligence.shared.file_cache import (
        get_python_files as get_cached_python_files,
    )

    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = logging.getLogger(__name__)


class AntiPatternDetector(SemanticAnalysisMixin):
    """
    Detects code anti-patterns and smells in Python code.

    Uses AST parsing to analyze code structure and identify common
    anti-patterns that indicate potential code quality issues.

    Issue #554: Now includes optional semantic analysis via ChromaDB/Redis/LLM
    infrastructure for detecting semantically similar anti-patterns.

    This class coordinates multiple specialized detectors:
    - BloaterDetector: God class, long method, deep nesting, etc.
    - CouplerDetector: Circular dependencies, feature envy, message chains
    - DispensableDetector: Dead code, lazy class
    - NamingDetector: Naming issues, magic numbers, complex conditionals
    """

    # Expose thresholds as class attributes for backward compatibility
    GOD_CLASS_METHOD_THRESHOLD = Thresholds.GOD_CLASS_METHOD_THRESHOLD
    GOD_CLASS_LINE_THRESHOLD = Thresholds.GOD_CLASS_LINE_THRESHOLD
    LONG_PARAMETER_THRESHOLD = Thresholds.LONG_PARAMETER_THRESHOLD
    LARGE_FILE_THRESHOLD = Thresholds.LARGE_FILE_THRESHOLD
    DEEP_NESTING_THRESHOLD = Thresholds.DEEP_NESTING_THRESHOLD
    LONG_METHOD_THRESHOLD = Thresholds.LONG_METHOD_THRESHOLD
    MESSAGE_CHAIN_THRESHOLD = Thresholds.MESSAGE_CHAIN_THRESHOLD
    LAZY_CLASS_METHOD_THRESHOLD = Thresholds.LAZY_CLASS_METHOD_THRESHOLD
    COMPLEX_CONDITIONAL_THRESHOLD = Thresholds.COMPLEX_CONDITIONAL_THRESHOLD
    MAGIC_NUMBER_THRESHOLD = Thresholds.MAGIC_NUMBER_THRESHOLD

    def __init__(
        self,
        exclude_dirs: Optional[List[str]] = None,
        detect_circular: bool = True,
        detect_naming: bool = True,
        use_semantic_analysis: bool = False,
        use_cache: bool = True,
        use_shared_cache: bool = True,
    ):
        """
        Initialize anti-pattern detector.

        Args:
            exclude_dirs: Directories to exclude from analysis
            detect_circular: Whether to detect circular dependencies
            detect_naming: Whether to detect naming issues
            use_semantic_analysis: Whether to use LLM-based semantic analysis (Issue #554)
            use_cache: Whether to use Redis caching for results (Issue #554)
            use_shared_cache: Whether to use shared FileListCache/ASTCache (Issue #607)
        """
        self.exclude_dirs = exclude_dirs or DEFAULT_IGNORE_PATTERNS
        self.detect_circular = detect_circular
        self.detect_naming = detect_naming
        self.use_semantic_analysis = (
            use_semantic_analysis and HAS_ANALYTICS_INFRASTRUCTURE
        )
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

        # Initialize specialized detectors
        self._bloater = BloaterDetector()
        self._coupler = CouplerDetector()
        self._dispensable = DispensableDetector()
        self._naming = NamingDetector()

        # State tracking
        self._total_classes = 0
        self._total_functions = 0

        # Issue #554: Initialize analytics infrastructure if semantic analysis enabled
        if self.use_semantic_analysis:
            self._init_infrastructure(
                collection_name="anti_pattern_vectors",
                use_llm=True,
                use_cache=use_cache,
                redis_database="analytics",
            )

    def analyze_directory(self, directory: str) -> AnalysisReport:
        """
        Analyze a directory for anti-patterns.

        Args:
            directory: Path to directory to analyze

        Returns:
            AnalysisReport with all detected anti-patterns
        """
        patterns: List[AntiPatternResult] = []
        self._total_classes = 0
        self._total_functions = 0

        python_files = self._get_python_files(directory)

        # Reset coupler detector's import graph
        self._coupler.reset_import_graph()

        for file_path in python_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()
                    lines = source.split("\n")

                # Check for large file
                result = self._bloater.check_large_file(file_path, len(lines))
                if result:
                    patterns.append(result)

                tree = ast.parse(source, filename=file_path)

                # Collect imports for circular dependency detection
                if self.detect_circular:
                    self._coupler.collect_imports(file_path)

                # Analyze all nodes
                patterns.extend(self._analyze_ast_nodes(tree, file_path, lines))

                # File-level detections
                patterns.extend(self._run_file_level_detections(tree, file_path))

            except SyntaxError as e:
                logger.debug("Syntax error in %s: %s", file_path, e)
            except Exception as e:
                logger.debug("Error analyzing %s: %s", file_path, e)

        # Detect circular dependencies across all files
        if self.detect_circular:
            patterns.extend(self._coupler.detect_circular_dependencies())

        return AnalysisReport(
            scan_path=directory,
            total_files=len(python_files),
            total_classes=self._total_classes,
            total_functions=self._total_functions,
            anti_patterns=patterns,
            summary=self._calculate_summary(patterns),
            severity_distribution=self._calculate_severity_distribution(patterns),
        )

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a single file for anti-patterns.

        Args:
            file_path: Path to the file to analyze

        Returns:
            Dictionary with analysis results

        Issue #607: Uses shared ASTCache when available for performance.
        """
        patterns: List[AntiPatternResult] = []
        classes = 0
        functions = 0

        try:
            # Issue #607: Use shared AST cache if available
            if self.use_shared_cache:
                tree, source = get_ast_with_content(file_path)
                lines = source.split("\n") if source else []
                if tree is None:
                    # Parse failed, but we may still have content for line count
                    return {
                        "file_path": file_path,
                        "lines": len(lines),
                        "classes": 0,
                        "functions": 0,
                        "anti_patterns": [],
                        "summary": {},
                        "error": "Failed to parse AST",
                    }
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()
                    lines = source.split("\n")
                tree = ast.parse(source, filename=file_path)

            # Check for large file
            result = self._bloater.check_large_file(file_path, len(lines))
            if result:
                patterns.append(result)

            # Count and analyze classes/functions
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes += 1
                    patterns.extend(self._analyze_class(node, file_path, lines))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Only count module-level functions
                    parent_is_class = any(
                        isinstance(p, ast.ClassDef)
                        for p in ast.walk(tree)
                        if node in getattr(p, "body", [])
                    )
                    if not parent_is_class:
                        functions += 1
                        patterns.extend(self._analyze_function(node, file_path, lines))

            # File-level detections
            patterns.extend(self._run_file_level_detections(tree, file_path))

        except SyntaxError as e:
            logger.debug("Syntax error in %s: %s", file_path, e)
        except Exception as e:
            logger.debug("Error analyzing %s: %s", file_path, e)

        return {
            "file_path": file_path,
            "lines": len(lines) if "lines" in dir() else 0,
            "classes": classes,
            "functions": functions,
            "anti_patterns": [p.to_dict() for p in patterns],
            "summary": self._calculate_summary(patterns),
        }

    def _analyze_ast_nodes(
        self,
        tree: ast.AST,
        file_path: str,
        lines: List[str],
    ) -> List[AntiPatternResult]:
        """Analyze all AST nodes for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._total_classes += 1
                patterns.extend(self._analyze_class(node, file_path, lines))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._total_functions += 1
                # Module-level functions analyzed separately
                # Class methods are analyzed within _analyze_class

        return patterns

    def _analyze_class(
        self,
        node: ast.ClassDef,
        file_path: str,
        lines: List[str],
    ) -> List[AntiPatternResult]:
        """Analyze a class for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        methods = self._bloater.get_class_methods(node)
        method_count = len(methods)
        class_lines = self._bloater.calculate_class_size(node)

        # God class detection
        god_class_result = self._bloater.check_god_class(
            node, file_path, method_count, class_lines
        )
        if god_class_result:
            patterns.append(god_class_result)

        # Lazy class detection
        patterns.extend(self._dispensable.detect_lazy_class(node, file_path))

        # Naming issues in class
        if self.detect_naming:
            patterns.extend(self._naming.detect_naming_issues(node, file_path))

        # Analyze each method
        for method in methods:
            patterns.extend(self._analyze_function(method, file_path, lines))

        return patterns

    def _analyze_function(
        self,
        node: ast.FunctionDef,
        file_path: str,
        lines: List[str],
    ) -> List[AntiPatternResult]:
        """Analyze a function/method for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        # Bloater detections
        param_count = self._bloater.count_function_params(node)
        result = self._bloater.check_long_parameter_list(node, file_path, param_count)
        if result:
            patterns.append(result)

        result = self._bloater.check_long_method(node, file_path)
        if result:
            patterns.append(result)

        result = self._bloater.check_deep_nesting(node, file_path)
        if result:
            patterns.append(result)

        # Coupler detections
        patterns.extend(self._coupler.detect_message_chains(node, file_path))
        patterns.extend(self._coupler.detect_feature_envy(node, file_path))

        # Naming detections
        if self.detect_naming:
            patterns.extend(self._naming.detect_complex_conditionals(node, file_path))
            patterns.extend(self._naming.detect_single_letter_vars(node, file_path))

        return patterns

    def _run_file_level_detections(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """Run file-level detections."""
        patterns: List[AntiPatternResult] = []

        # Dead code detection
        patterns.extend(self._dispensable.detect_dead_code(tree, file_path))

        # Missing docstrings
        if self.detect_naming:
            patterns.extend(self._naming.detect_missing_docstrings(tree, file_path))
            patterns.extend(self._naming.detect_magic_numbers(tree, file_path))

        # Data clumps
        patterns.extend(self._bloater.detect_data_clumps(tree, file_path))

        return patterns

    def _get_python_files(self, directory: str) -> List[str]:
        """
        Get all Python files in directory, excluding specified patterns.

        Issue #607: Uses shared FileListCache when available for performance.
        Falls back to direct rglob if cache is not available or for custom directories.
        """
        python_files = []
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            should_exclude = False
            for exclude_dir in self.exclude_dirs:
                if exclude_dir in py_file.parts:
                    should_exclude = True
                    break

            if not should_exclude:
                python_files.append(str(py_file))

        return sorted(python_files)

    async def _get_python_files_async(self, directory: str) -> List[str]:
        """
        Get all Python files in directory using async cache.

        Issue #607: Uses shared FileListCache for performance optimization.
        Filters results by exclude_dirs after cache lookup.
        """
        dir_path = Path(directory)

        # Use shared cache if available
        if self.use_shared_cache:
            all_files = await get_cached_python_files(dir_path)
            # Filter by exclude_dirs
            python_files = []
            for py_file in all_files:
                should_exclude = False
                for exclude_dir in self.exclude_dirs:
                    if exclude_dir in py_file.parts:
                        should_exclude = True
                        break
                if not should_exclude:
                    python_files.append(str(py_file))
            return sorted(python_files)

        # Fallback to sync method in thread pool
        return await asyncio.to_thread(self._get_python_files, directory)

    def _calculate_summary(
        self,
        patterns: List[AntiPatternResult],
    ) -> Dict[str, int]:
        """Calculate summary of anti-patterns by type."""
        summary: Dict[str, int] = {}
        for pattern in patterns:
            key = pattern.pattern_type.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _calculate_severity_distribution(
        self,
        patterns: List[AntiPatternResult],
    ) -> Dict[str, int]:
        """Calculate distribution of patterns by severity."""
        dist: Dict[str, int] = {}
        for pattern in patterns:
            key = pattern.severity.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    async def _analyze_directory_with_cache(self, directory: str) -> AnalysisReport:
        """
        Analyze directory using shared caches for performance.

        Issue #607: Uses FileListCache and ASTCache to eliminate redundant
        file traversals and AST parsing.

        Args:
            directory: Path to directory to analyze

        Returns:
            AnalysisReport with all detected anti-patterns
        """
        patterns: List[AntiPatternResult] = []
        self._total_classes = 0
        self._total_functions = 0

        # Use async file list cache
        python_files = await self._get_python_files_async(directory)

        # Reset coupler detector's import graph
        self._coupler.reset_import_graph()

        for file_path in python_files:
            try:
                # Use shared AST cache
                tree, source = get_ast_with_content(file_path)
                if tree is None:
                    logger.debug("Skipping %s: failed to parse AST", file_path)
                    continue

                lines = source.split("\n") if source else []

                # Check for large file
                result = self._bloater.check_large_file(file_path, len(lines))
                if result:
                    patterns.append(result)

                # Collect imports for circular dependency detection
                if self.detect_circular:
                    self._coupler.collect_imports(file_path)

                # Analyze all nodes
                patterns.extend(self._analyze_ast_nodes(tree, file_path, lines))

                # File-level detections
                patterns.extend(self._run_file_level_detections(tree, file_path))

            except Exception as e:
                logger.debug("Error analyzing %s: %s", file_path, e)

        # Detect circular dependencies across all files
        if self.detect_circular:
            patterns.extend(self._coupler.detect_circular_dependencies())

        return AnalysisReport(
            scan_path=directory,
            total_files=len(python_files),
            total_classes=self._total_classes,
            total_functions=self._total_functions,
            anti_patterns=patterns,
            summary=self._calculate_summary(patterns),
            severity_distribution=self._calculate_severity_distribution(patterns),
        )

    # Issue #554: Async semantic analysis methods
    # Issue #607: Enhanced with shared cache support

    async def analyze_directory_async(
        self,
        directory: str,
        find_semantic_duplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyze a directory with optional semantic analysis.

        Issue #554: Async version that supports ChromaDB/Redis/LLM infrastructure.
        Issue #607: Uses shared FileListCache and ASTCache for performance.

        Args:
            directory: Path to directory to analyze
            find_semantic_duplicates: Whether to find semantically similar patterns

        Returns:
            Dictionary with analysis results including semantic matches
        """
        start_time = time.time()

        # Issue #607: Use optimized async analysis when shared cache is available
        if self.use_shared_cache:
            report = await self._analyze_directory_with_cache(directory)
        else:
            # Run standard analysis in thread pool
            report = await asyncio.to_thread(self.analyze_directory, directory)

        result = {
            "report": report.to_dict()
            if hasattr(report, "to_dict")
            else {
                "scan_path": report.scan_path,
                "total_files": report.total_files,
                "total_classes": report.total_classes,
                "total_functions": report.total_functions,
                "anti_patterns": [p.to_dict() for p in report.anti_patterns],
                "summary": report.summary,
                "severity_distribution": report.severity_distribution,
            },
            "semantic_duplicates": [],
            "infrastructure_metrics": {},
        }

        # Run semantic analysis if enabled
        if self.use_semantic_analysis and find_semantic_duplicates:
            semantic_dups = await self._find_semantic_anti_pattern_duplicates(
                report.anti_patterns
            )
            result["semantic_duplicates"] = semantic_dups

            # Add infrastructure metrics
            result["infrastructure_metrics"] = self._get_infrastructure_metrics()

        result["analysis_time_ms"] = (time.time() - start_time) * 1000
        return result

    async def _find_semantic_anti_pattern_duplicates(
        self,
        patterns: List[AntiPatternResult],
    ) -> List[Dict[str, Any]]:
        """
        Find semantically similar anti-patterns using LLM embeddings.

        Issue #554: Uses the generic _find_semantic_duplicates_with_extraction
        helper from SemanticAnalysisMixin to reduce code duplication.

        Args:
            patterns: List of detected anti-patterns

        Returns:
            List of duplicate pairs with similarity scores
        """
        try:
            return await self._find_semantic_duplicates_with_extraction(
                items=patterns,
                code_extractors=["current_code", "code_snippet"],
                metadata_keys={
                    "pattern_type": "pattern_type",
                    "file_path": "file_path",
                    "line_start": "line_start",
                    "description": "description",
                },
                min_similarity=SIMILARITY_MEDIUM
                if HAS_ANALYTICS_INFRASTRUCTURE
                else 0.7,
            )
        except Exception as e:
            logger.warning("Semantic duplicate detection failed: %s", e)
            return []

    async def cache_analysis_results(
        self,
        directory: str,
        report: AnalysisReport,
    ) -> bool:
        """
        Cache analysis results in Redis for faster retrieval.

        Issue #554: Uses Redis caching from analytics infrastructure.

        Args:
            directory: Analyzed directory path
            report: Analysis report to cache

        Returns:
            True if cached successfully
        """
        if not self.use_semantic_analysis:
            return False

        cache_key = self._generate_content_hash(directory)
        report_dict = (
            report.to_dict()
            if hasattr(report, "to_dict")
            else {
                "scan_path": report.scan_path,
                "total_files": report.total_files,
                "anti_patterns": [p.to_dict() for p in report.anti_patterns],
                "summary": report.summary,
            }
        )

        return await self._cache_result(
            key=cache_key,
            result=report_dict,
            prefix="anti_pattern_analysis",
        )

    async def get_cached_analysis(
        self,
        directory: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached analysis results from Redis.

        Issue #554: Retrieves cached results for faster repeat analysis.

        Args:
            directory: Directory path to look up

        Returns:
            Cached analysis results or None if not found
        """
        if not self.use_semantic_analysis:
            return None

        cache_key = self._generate_content_hash(directory)
        return await self._get_cached_result(
            key=cache_key,
            prefix="anti_pattern_analysis",
        )


def analyze_codebase(
    directory: str,
    exclude_dirs: Optional[List[str]] = None,
    detect_circular: bool = True,
    detect_naming: bool = True,
) -> AnalysisReport:
    """
    Convenience function to analyze a codebase for anti-patterns.

    Args:
        directory: Path to directory to analyze
        exclude_dirs: Directories to exclude from analysis
        detect_circular: Whether to detect circular dependencies
        detect_naming: Whether to detect naming issues

    Returns:
        AnalysisReport with all detected anti-patterns
    """
    detector = AntiPatternDetector(
        exclude_dirs=exclude_dirs,
        detect_circular=detect_circular,
        detect_naming=detect_naming,
    )
    return detector.analyze_directory(directory)


async def analyze_codebase_async(
    directory: str,
    exclude_dirs: Optional[List[str]] = None,
    detect_circular: bool = True,
    detect_naming: bool = True,
    use_semantic_analysis: bool = True,
    find_semantic_duplicates: bool = True,
) -> Dict[str, Any]:
    """
    Async convenience function to analyze a codebase with semantic analysis.

    Issue #554: Async version with ChromaDB/Redis/LLM infrastructure support.

    Args:
        directory: Path to directory to analyze
        exclude_dirs: Directories to exclude from analysis
        detect_circular: Whether to detect circular dependencies
        detect_naming: Whether to detect naming issues
        use_semantic_analysis: Whether to use LLM-based semantic analysis
        find_semantic_duplicates: Whether to find semantically similar patterns

    Returns:
        Dictionary with analysis results including semantic matches
    """
    detector = AntiPatternDetector(
        exclude_dirs=exclude_dirs,
        detect_circular=detect_circular,
        detect_naming=detect_naming,
        use_semantic_analysis=use_semantic_analysis,
    )
    return await detector.analyze_directory_async(
        directory,
        find_semantic_duplicates=find_semantic_duplicates,
    )
