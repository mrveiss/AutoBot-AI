# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Pattern Analyzer - Main Orchestrator

Issue #208: Combines AST parsing, embeddings, similarity search, and
analysis tools to provide comprehensive code pattern detection.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .complexity_analyzer import ComplexityAnalyzer
from .refactoring_generator import RefactoringSuggestionGenerator
from .regex_detector import RegexPatternDetector
from .storage import store_patterns_batch
from .types import (
    CodeLocation,
    CodePattern,
    DuplicatePattern,
    ModularizationSuggestion,
    PatternAnalysisReport,
    PatternSeverity,
    PatternType,
)

logger = logging.getLogger(__name__)

# Try to import fingerprinting and anti-pattern detection
try:
    from code_intelligence.fingerprinting import CloneDetector

    FINGERPRINTING_AVAILABLE = True
except ImportError:
    FINGERPRINTING_AVAILABLE = False
    logger.warning("Fingerprinting module not available")

try:
    from code_intelligence.anti_pattern_detection import AntiPatternDetector

    ANTI_PATTERN_AVAILABLE = True
except ImportError:
    ANTI_PATTERN_AVAILABLE = False
    logger.warning("Anti-pattern detection module not available")


# Embedding generation (uses existing infrastructure)
try:
    from knowledge.embedding_cache import EmbeddingCache

    EMBEDDING_CACHE_AVAILABLE = True
except ImportError:
    EMBEDDING_CACHE_AVAILABLE = False


class CodePatternAnalyzer:
    """Main orchestrator for code pattern detection and optimization.

    This analyzer combines:
    - Clone detection (fingerprinting)
    - Anti-pattern detection
    - Regex optimization detection
    - Complexity analysis (radon)
    - Pattern embedding and similarity search (ChromaDB)
    - Refactoring suggestion generation

    Architecture:
        1. Scan codebase for Python files
        2. Run multiple analyzers in parallel
        3. Generate embeddings for detected patterns
        4. Store in ChromaDB for similarity search
        5. Cluster similar patterns
        6. Generate refactoring suggestions
        7. Produce comprehensive report
    """

    # Default exclusions
    DEFAULT_EXCLUDE_DIRS = frozenset(
        {
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "archives",
            ".mypy_cache",
            ".pytest_cache",
            "dist",
            "build",
        }
    )

    def _init_feature_flags(
        self,
        enable_clone_detection: bool,
        enable_anti_pattern_detection: bool,
        enable_regex_detection: bool,
        enable_complexity_analysis: bool,
        enable_embedding_storage: bool,
        similarity_threshold: float,
        exclude_dirs: Optional[Set[str]],
    ) -> None:
        """Initialize feature flags and configuration settings. Issue #620."""
        self.enable_clone_detection = (
            enable_clone_detection and FINGERPRINTING_AVAILABLE
        )
        self.enable_anti_pattern_detection = (
            enable_anti_pattern_detection and ANTI_PATTERN_AVAILABLE
        )
        self.enable_regex_detection = enable_regex_detection
        self.enable_complexity_analysis = enable_complexity_analysis
        self.enable_embedding_storage = enable_embedding_storage
        self.similarity_threshold = similarity_threshold
        self.exclude_dirs = exclude_dirs or self.DEFAULT_EXCLUDE_DIRS

    def _init_sub_analyzers(self, cc_threshold: int, mi_threshold: float) -> None:
        """Initialize sub-analyzer instances based on feature flags. Issue #620."""
        self._clone_detector = (
            CloneDetector(exclude_dirs=list(self.exclude_dirs))
            if self.enable_clone_detection
            else None
        )
        self._anti_pattern_detector = (
            AntiPatternDetector(exclude_dirs=list(self.exclude_dirs))
            if self.enable_anti_pattern_detection
            else None
        )
        self._regex_detector = (
            RegexPatternDetector(exclude_dirs=self.exclude_dirs)
            if self.enable_regex_detection
            else None
        )
        self._complexity_analyzer = (
            ComplexityAnalyzer(
                cc_threshold=cc_threshold,
                mi_threshold=mi_threshold,
                exclude_dirs=self.exclude_dirs,
            )
            if self.enable_complexity_analysis
            else None
        )
        self._refactoring_generator = RefactoringSuggestionGenerator()

    def __init__(
        self,
        enable_clone_detection: bool = True,
        enable_anti_pattern_detection: bool = True,
        enable_regex_detection: bool = True,
        enable_complexity_analysis: bool = True,
        enable_embedding_storage: bool = True,
        similarity_threshold: float = 0.8,
        exclude_dirs: Optional[Set[str]] = None,
        cc_threshold: int = 10,
        mi_threshold: float = 50,
    ):
        """Initialize the code pattern analyzer. Issue #620."""
        self._init_feature_flags(
            enable_clone_detection,
            enable_anti_pattern_detection,
            enable_regex_detection,
            enable_complexity_analysis,
            enable_embedding_storage,
            similarity_threshold,
            exclude_dirs,
        )
        self._init_sub_analyzers(cc_threshold, mi_threshold)

    def _build_analysis_tasks(self, directory: str) -> List:
        """Build list of analysis tasks based on enabled features. Issue #620."""
        tasks = []
        if self.enable_clone_detection:
            tasks.append(self._run_clone_detection(directory))
        if self.enable_regex_detection:
            tasks.append(self._run_regex_detection(directory))
        if self.enable_complexity_analysis:
            tasks.append(self._run_complexity_analysis(directory))
        if self.enable_anti_pattern_detection:
            tasks.append(self._run_anti_pattern_detection(directory))
        return tasks

    async def _execute_and_merge_results(
        self, tasks: List, report: PatternAnalysisReport
    ) -> None:
        """Execute analysis tasks concurrently and merge results. Issue #620."""
        if not tasks:
            return
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error("Analysis task failed: %s", result)
                continue
            self._merge_results(report, result)

    async def analyze_directory(self, directory: str) -> PatternAnalysisReport:
        """Analyze a directory for code patterns.

        Args:
            directory: Path to directory to analyze

        Returns:
            PatternAnalysisReport with all findings
        """
        logger.info("Starting code pattern analysis for: %s", directory)
        start_time = time.time()

        report = PatternAnalysisReport(scan_path=directory)
        file_count, line_count = self._count_files_and_lines(directory)
        report.total_files_analyzed = file_count
        report.total_lines_analyzed = line_count

        tasks = self._build_analysis_tasks(directory)
        await self._execute_and_merge_results(tasks, report)

        if self.enable_embedding_storage:
            await self._store_patterns(report)

        report.analysis_duration_seconds = time.time() - start_time
        report.calculate_metrics()

        logger.info(
            "Pattern analysis complete: %d patterns found in %.2f seconds",
            report.total_patterns,
            report.analysis_duration_seconds,
        )

        return report

    def _count_files_and_lines(self, directory: str) -> tuple:
        """Count Python files and lines in directory.

        Args:
            directory: Path to directory

        Returns:
            Tuple of (file_count, line_count)
        """
        file_count = 0
        line_count = 0
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            if any(exc in py_file.parts for exc in self.exclude_dirs):
                continue

            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    file_count += 1
                    line_count += len(lines)
            except Exception:  # nosec B110 - file read errors ignored
                pass

        return file_count, line_count

    async def _run_clone_detection(self, directory: str) -> Dict[str, Any]:
        """Run clone detection analysis.

        Args:
            directory: Path to directory

        Returns:
            Dictionary with clone detection results
        """
        if not self._clone_detector:
            return {"type": "clone_detection", "patterns": []}

        try:
            # Clone detection is synchronous, run in thread pool
            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(
                None, self._clone_detector.detect_clones, directory
            )

            # Convert to our types
            duplicate_patterns = []
            for group in report.clone_groups:
                duplicate = self._clone_group_to_duplicate(group)
                if duplicate:
                    duplicate_patterns.append(duplicate)

            return {
                "type": "clone_detection",
                "patterns": duplicate_patterns,
                "raw_report": report,
            }

        except Exception as e:
            logger.error("Clone detection failed: %s", e)
            return {"type": "clone_detection", "patterns": [], "error": str(e)}

    async def _run_regex_detection(self, directory: str) -> Dict[str, Any]:
        """Run regex optimization detection.

        Args:
            directory: Path to directory

        Returns:
            Dictionary with regex detection results
        """
        if not self._regex_detector:
            return {"type": "regex_detection", "patterns": []}

        try:
            # Run in thread pool
            loop = asyncio.get_event_loop()
            opportunities = await loop.run_in_executor(
                None, self._regex_detector.detect_in_directory, directory
            )

            return {"type": "regex_detection", "patterns": opportunities}

        except Exception as e:
            logger.error("Regex detection failed: %s", e)
            return {"type": "regex_detection", "patterns": [], "error": str(e)}

    async def _run_complexity_analysis(self, directory: str) -> Dict[str, Any]:
        """Run complexity analysis.

        Args:
            directory: Path to directory

        Returns:
            Dictionary with complexity analysis results
        """
        if not self._complexity_analyzer:
            return {"type": "complexity_analysis", "patterns": [], "modules": []}

        try:
            # Run in thread pool
            loop = asyncio.get_event_loop()
            modules = await loop.run_in_executor(
                None, self._complexity_analyzer.analyze_directory, directory
            )

            # Find hotspots
            hotspots = self._complexity_analyzer.find_hotspots(modules)

            return {
                "type": "complexity_analysis",
                "patterns": hotspots,
                "modules": modules,
            }

        except Exception as e:
            logger.error("Complexity analysis failed: %s", e)
            return {
                "type": "complexity_analysis",
                "patterns": [],
                "modules": [],
                "error": str(e),
            }

    async def _run_anti_pattern_detection(self, directory: str) -> Dict[str, Any]:
        """Run anti-pattern detection.

        Args:
            directory: Path to directory

        Returns:
            Dictionary with anti-pattern detection results
        """
        if not self._anti_pattern_detector:
            return {"type": "anti_pattern_detection", "patterns": []}

        try:
            # Run in thread pool
            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(
                None, self._anti_pattern_detector.analyze_directory, directory
            )

            # Convert to modularization suggestions where appropriate
            modularization = []
            other_patterns = []

            for pattern in report.anti_patterns:
                # Check if pattern suggests modularization
                if self._is_modularization_candidate(pattern):
                    mod_suggestion = self._to_modularization_suggestion(pattern)
                    if mod_suggestion:
                        modularization.append(mod_suggestion)
                else:
                    # Convert to generic CodePattern
                    code_pattern = self._anti_pattern_to_code_pattern(pattern)
                    if code_pattern:
                        other_patterns.append(code_pattern)

            return {
                "type": "anti_pattern_detection",
                "modularization": modularization,
                "other_patterns": other_patterns,
                "raw_report": report,
            }

        except Exception as e:
            logger.error("Anti-pattern detection failed: %s", e)
            return {
                "type": "anti_pattern_detection",
                "modularization": [],
                "other_patterns": [],
                "error": str(e),
            }

    def _merge_results(
        self, report: PatternAnalysisReport, result: Dict[str, Any]
    ) -> None:
        """Merge analysis results into report.

        Args:
            report: Target report to update
            result: Analysis result dictionary
        """
        result_type = result.get("type", "")

        if result_type == "clone_detection":
            report.duplicate_patterns.extend(result.get("patterns", []))

        elif result_type == "regex_detection":
            report.regex_opportunities.extend(result.get("patterns", []))

        elif result_type == "complexity_analysis":
            report.complexity_hotspots.extend(result.get("patterns", []))

        elif result_type == "anti_pattern_detection":
            report.modularization_suggestions.extend(result.get("modularization", []))
            report.other_patterns.extend(result.get("other_patterns", []))

    def _clone_group_to_duplicate(self, group) -> Optional[DuplicatePattern]:
        """Convert CloneGroup to DuplicatePattern.

        Args:
            group: CloneGroup from fingerprinting

        Returns:
            DuplicatePattern or None
        """
        if not group.instances:
            return None

        locations = []
        for instance in group.instances:
            loc = CodeLocation(
                file_path=instance.fragment.file_path,
                start_line=instance.fragment.start_line,
                end_line=instance.fragment.end_line,
                function_name=instance.fragment.entity_name,
            )
            locations.append(loc)

        # Determine severity from clone severity
        severity_map = {
            "critical": PatternSeverity.CRITICAL,
            "high": PatternSeverity.HIGH,
            "medium": PatternSeverity.MEDIUM,
            "low": PatternSeverity.LOW,
            "info": PatternSeverity.INFO,
        }
        severity = severity_map.get(
            group.severity.value.lower(), PatternSeverity.MEDIUM
        )

        # Get canonical code from first instance
        canonical = ""
        if group.instances and group.instances[0].fragment:
            canonical = group.instances[0].fragment.source_code or ""

        return DuplicatePattern(
            pattern_type=PatternType.DUPLICATE_CODE,
            severity=severity,
            description=f"{group.clone_type.value} clone: {len(group.instances)} occurrences",
            locations=locations,
            suggestion=group.refactoring_suggestion or "Extract into shared function",
            confidence=min(group.similarity_range) if group.similarity_range else 0.8,
            similarity_score=min(group.similarity_range)
            if group.similarity_range
            else 1.0,
            canonical_code=canonical,
            code_reduction_potential=group.total_duplicated_lines
            - (group.total_duplicated_lines // len(group.instances)),
        )

    def _is_modularization_candidate(self, pattern) -> bool:
        """Check if anti-pattern suggests modularization.

        Args:
            pattern: AntiPatternResult

        Returns:
            True if pattern suggests modularization
        """
        modularization_types = {
            "god_class",
            "data_clump",
            "feature_envy",
            "long_parameter_list",
        }
        return pattern.pattern_type.value.lower() in modularization_types

    def _to_modularization_suggestion(
        self, pattern
    ) -> Optional[ModularizationSuggestion]:
        """Convert anti-pattern to modularization suggestion.

        Args:
            pattern: AntiPatternResult

        Returns:
            ModularizationSuggestion or None
        """
        severity_map = {
            "critical": PatternSeverity.CRITICAL,
            "high": PatternSeverity.HIGH,
            "medium": PatternSeverity.MEDIUM,
            "low": PatternSeverity.LOW,
            "info": PatternSeverity.INFO,
        }

        location = CodeLocation(
            file_path=pattern.file_path,
            start_line=pattern.line_number,
            end_line=pattern.line_number,
            function_name=pattern.entity_name,
        )

        return ModularizationSuggestion(
            pattern_type=PatternType.MODULARIZATION,
            severity=severity_map.get(
                pattern.severity.value.lower(), PatternSeverity.MEDIUM
            ),
            description=pattern.description,
            locations=[location],
            suggestion=pattern.suggestion,
            confidence=0.7,
            pattern_name=pattern.entity_name or "unnamed_pattern",
            repeated_in_files=[pattern.file_path],
            suggested_module=f"utils/{pattern.entity_name}_handler.py",
            benefits=[
                "Improved separation of concerns",
                "Better testability",
                "Reduced coupling",
            ],
        )

    def _anti_pattern_to_code_pattern(self, pattern) -> Optional[CodePattern]:
        """Convert anti-pattern to generic CodePattern.

        Args:
            pattern: AntiPatternResult

        Returns:
            CodePattern or None
        """
        severity_map = {
            "critical": PatternSeverity.CRITICAL,
            "high": PatternSeverity.HIGH,
            "medium": PatternSeverity.MEDIUM,
            "low": PatternSeverity.LOW,
            "info": PatternSeverity.INFO,
        }

        # Map anti-pattern types to our pattern types
        type_map = {
            "dead_code": PatternType.DEAD_CODE,
            "circular_dependency": PatternType.COUPLING_ISSUE,
            "message_chain": PatternType.COUPLING_ISSUE,
        }

        pattern_type = type_map.get(
            pattern.pattern_type.value.lower(), PatternType.COUPLING_ISSUE
        )

        location = CodeLocation(
            file_path=pattern.file_path,
            start_line=pattern.line_number,
            end_line=pattern.line_number,
            function_name=pattern.entity_name,
        )

        return CodePattern(
            pattern_type=pattern_type,
            severity=severity_map.get(
                pattern.severity.value.lower(), PatternSeverity.MEDIUM
            ),
            description=pattern.description,
            locations=[location],
            suggestion=pattern.suggestion,
            confidence=0.7,
        )

    async def _prepare_duplicate_pattern_for_storage(
        self, dup: DuplicatePattern
    ) -> Optional[Dict[str, Any]]:
        """Prepare a duplicate pattern for ChromaDB storage. Issue #620.

        Args:
            dup: Duplicate pattern to prepare

        Returns:
            Pattern dict ready for storage, or None if no canonical code
        """
        if not dup.canonical_code:
            return None

        return {
            "pattern_type": "duplicate",
            "code_content": dup.canonical_code,
            "embedding": await self._generate_embedding(dup.canonical_code),
            "metadata": {
                "file_path": dup.locations[0].file_path if dup.locations else "",
                "start_line": dup.locations[0].start_line if dup.locations else 0,
                "occurrence_count": dup.occurrence_count,
                "severity": dup.severity.value,
            },
        }

    async def _prepare_regex_pattern_for_storage(
        self, regex_opp: Any
    ) -> Optional[Dict[str, Any]]:
        """Prepare a regex opportunity pattern for ChromaDB storage. Issue #620.

        Args:
            regex_opp: Regex opportunity pattern to prepare

        Returns:
            Pattern dict ready for storage, or None if no current code
        """
        if not regex_opp.current_code:
            return None

        return {
            "pattern_type": "regex_opportunity",
            "code_content": regex_opp.current_code,
            "embedding": await self._generate_embedding(regex_opp.current_code),
            "metadata": {
                "file_path": regex_opp.locations[0].file_path
                if regex_opp.locations
                else "",
                "start_line": regex_opp.locations[0].start_line
                if regex_opp.locations
                else 0,
                "suggested_regex": regex_opp.suggested_regex,
                "severity": regex_opp.severity.value,
            },
        }

    async def _store_patterns(self, report: PatternAnalysisReport) -> None:
        """Store patterns in ChromaDB for similarity search.

        Args:
            report: Report with patterns to store
        """
        if not self.enable_embedding_storage:
            return

        try:
            patterns_to_store = []

            for dup in report.duplicate_patterns:
                pattern = await self._prepare_duplicate_pattern_for_storage(dup)
                if pattern:
                    patterns_to_store.append(pattern)

            for regex_opp in report.regex_opportunities:
                pattern = await self._prepare_regex_pattern_for_storage(regex_opp)
                if pattern:
                    patterns_to_store.append(pattern)

            if patterns_to_store:
                stored_count = await store_patterns_batch(patterns_to_store)
                logger.info("Stored %d patterns in ChromaDB", stored_count)

        except Exception as e:
            logger.error("Failed to store patterns: %s", e)

    async def _generate_embedding(self, code: str) -> List[float]:
        """Generate embedding for code content.

        Args:
            code: Code content to embed

        Returns:
            Embedding vector
        """
        # Use existing embedding infrastructure if available
        if EMBEDDING_CACHE_AVAILABLE:
            try:
                cache = EmbeddingCache()
                embedding = await cache.get_embedding(code)
                if embedding:
                    return embedding
            except Exception:  # nosec B110 - cache miss handled by fallback
                pass

        # Fallback: Simple hash-based pseudo-embedding for testing
        # In production, this should use actual embeddings
        import hashlib

        hash_bytes = hashlib.sha256(code.encode()).digest()
        # Convert to list of floats (768 dimensions to match nomic-embed-text)
        embedding = []
        for i in range(768):
            byte_idx = i % 32
            embedding.append((hash_bytes[byte_idx] - 128) / 128.0)

        return embedding


async def analyze_codebase_patterns(
    directory: str,
    enable_clone_detection: bool = True,
    enable_anti_pattern_detection: bool = True,
    enable_regex_detection: bool = True,
    enable_complexity_analysis: bool = True,
    similarity_threshold: float = 0.8,
) -> PatternAnalysisReport:
    """Convenience function to analyze codebase patterns.

    Args:
        directory: Path to directory to analyze
        enable_clone_detection: Enable clone detection
        enable_anti_pattern_detection: Enable anti-pattern detection
        enable_regex_detection: Enable regex detection
        enable_complexity_analysis: Enable complexity analysis
        similarity_threshold: Threshold for similarity clustering

    Returns:
        PatternAnalysisReport with all findings
    """
    analyzer = CodePatternAnalyzer(
        enable_clone_detection=enable_clone_detection,
        enable_anti_pattern_detection=enable_anti_pattern_detection,
        enable_regex_detection=enable_regex_detection,
        enable_complexity_analysis=enable_complexity_analysis,
        similarity_threshold=similarity_threshold,
    )

    return await analyzer.analyze_directory(directory)
