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

from utils.io_executor import get_analytics_executor

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

    # Batch size for per-file analysis (tunable)
    BATCH_SIZE = 50
    # Per-analyzer timeout in seconds
    ANALYZER_TIMEOUT = 300  # 5 minutes per analyzer per batch

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

    def collect_python_files(self, directory: str) -> List[str]:
        """Collect all Python files excluding configured directories.

        Returns:
            Sorted list of absolute file paths.
        """
        files = []
        dir_path = Path(directory)
        for py_file in dir_path.rglob("*.py"):
            if any(exc in py_file.parts for exc in self.exclude_dirs):
                continue
            files.append(str(py_file))
        return sorted(files)

    async def _run_batch_regex(self, file_paths: List[str]) -> List:
        """Run regex detection on a batch of files."""
        if not self._regex_detector:
            return []
        loop = asyncio.get_event_loop()
        executor = get_analytics_executor()
        results = []
        for fp in file_paths:
            try:
                opps = await loop.run_in_executor(
                    executor, self._regex_detector.detect_in_file, fp
                )
                results.extend(opps)
            except Exception as e:
                logger.debug("Regex detection failed for %s: %s", fp, e)
        return results

    async def _run_batch_complexity(self, file_paths: List[str]) -> List:
        """Run complexity analysis on a batch of files."""
        if not self._complexity_analyzer:
            return []
        loop = asyncio.get_event_loop()
        executor = get_analytics_executor()
        modules = []
        for fp in file_paths:
            try:
                module = await loop.run_in_executor(
                    executor, self._complexity_analyzer.analyze_file, fp
                )
                modules.append(module)
            except Exception as e:
                logger.debug("Complexity analysis failed for %s: %s", fp, e)
        return modules

    async def _run_batch_anti_pattern(self, file_paths: List[str]) -> Dict[str, List]:
        """Run anti-pattern detection on a batch of files."""
        if not self._anti_pattern_detector:
            return {"modularization": [], "other_patterns": []}
        loop = asyncio.get_event_loop()
        executor = get_analytics_executor()
        modularization: List = []
        other_patterns: List = []
        for fp in file_paths:
            try:
                file_result = await loop.run_in_executor(
                    executor,
                    self._anti_pattern_detector.analyze_file,
                    fp,
                )
                for pattern in file_result.get("anti_patterns", []):
                    if self._is_modularization_candidate(pattern):
                        mod = self._to_modularization_suggestion(pattern)
                        if mod:
                            modularization.append(mod)
                    else:
                        cp = self._anti_pattern_to_code_pattern(pattern)
                        if cp:
                            other_patterns.append(cp)
            except Exception as e:
                logger.debug("Anti-pattern detection failed for %s: %s", fp, e)
        return {"modularization": modularization, "other_patterns": other_patterns}

    async def analyze_directory(
        self,
        directory: str,
        progress_callback: Optional[Any] = None,
        checkpoint_callback: Optional[Any] = None,
        resume_from: Optional[Dict[str, Any]] = None,
    ) -> PatternAnalysisReport:
        """Analyze a directory for code patterns using batched processing.

        Processes files in batches of BATCH_SIZE (50) with progress
        reporting and optional checkpointing for resume capability.

        Args:
            directory: Path to directory to analyze.
            progress_callback: async callable(step, progress) for UI updates.
            checkpoint_callback: async callable(phase, batch_idx, partial)
                to save intermediate results for resume.
            resume_from: Checkpoint dict to resume from (keys: phase,
                batch_idx, partial_results).

        Returns:
            PatternAnalysisReport with all findings.
        """
        logger.info("Starting batched code pattern analysis for: %s", directory)
        start_time = time.time()

        async def _report(step: str, pct: float) -> None:
            if progress_callback:
                await progress_callback(step, pct)

        # Phase 1: Collect files
        await _report("Scanning files...", 2.0)
        all_files = await asyncio.to_thread(self.collect_python_files, directory)
        file_count = len(all_files)
        line_count = await asyncio.to_thread(self._count_lines_for_files, all_files)

        report = PatternAnalysisReport(scan_path=directory)
        report.total_files_analyzed = file_count
        report.total_lines_analyzed = line_count

        if file_count == 0:
            await _report("No Python files found", 100.0)
            return report

        # Split into batches
        batches = [
            all_files[i : i + self.BATCH_SIZE]
            for i in range(0, file_count, self.BATCH_SIZE)
        ]
        total_batches = len(batches)
        await _report(
            f"Found {file_count} files ({line_count} lines) "
            f"— {total_batches} batches of {self.BATCH_SIZE}",
            5.0,
        )

        start_batch = self._apply_resume_checkpoint(report, resume_from, total_batches)

        # Phase 2: Per-file analysis in batches (5% → 75%)
        await self._process_file_batches(
            batches,
            start_batch,
            report,
            _report,
            checkpoint_callback,
            file_count,
        )

        # Phase 3: Clone detection (75% → 85%) — full directory, with timeout
        if self.enable_clone_detection:
            await _report("Running clone detection...", 75.0)
            try:
                clone_result = await asyncio.wait_for(
                    self._run_clone_detection(directory),
                    timeout=self.ANALYZER_TIMEOUT,
                )
                self._merge_results(report, clone_result)
            except asyncio.TimeoutError:
                logger.warning(
                    "Clone detection timed out after %ds, skipping",
                    self.ANALYZER_TIMEOUT,
                )
            except Exception as e:
                logger.error("Clone detection failed: %s", e)

        # Phase 4: Store in ChromaDB (85% → 95%)
        if self.enable_embedding_storage:
            await _report("Storing patterns in ChromaDB...", 85.0)
            await self._store_patterns(report)

        # Phase 5: Finalize
        await _report("Finalizing report...", 95.0)
        report.analysis_duration_seconds = time.time() - start_time
        report.calculate_metrics()

        logger.info(
            "Pattern analysis complete: %d patterns found in %.2f seconds "
            "(%d batches of %d files)",
            report.total_patterns,
            report.analysis_duration_seconds,
            total_batches,
            self.BATCH_SIZE,
        )

        return report

    def _apply_resume_checkpoint(
        self,
        report: PatternAnalysisReport,
        resume_from: Optional[Dict[str, Any]],
        total_batches: int,
    ) -> int:
        """Restore partial results from a checkpoint and return start batch.

        Args:
            report: Report to populate with checkpoint data.
            resume_from: Checkpoint dict or None.
            total_batches: Total number of batches for logging.

        Returns:
            Batch index to resume from (0 if no checkpoint).
        """
        if not resume_from:
            return 0
        start_batch = resume_from.get("batch_idx", 0)
        partial = resume_from.get("partial_results", {})
        report.regex_opportunities.extend(partial.get("regex", []))
        report.complexity_hotspots.extend(partial.get("complexity", []))
        report.modularization_suggestions.extend(partial.get("modularization", []))
        report.other_patterns.extend(partial.get("other_patterns", []))
        logger.info("Resuming from batch %d/%d", start_batch, total_batches)
        return start_batch

    async def _process_file_batches(
        self,
        batches: List[List[str]],
        start_batch: int,
        report: PatternAnalysisReport,
        progress_fn: Any,
        checkpoint_callback: Optional[Any],
        file_count: int,
    ) -> None:
        """Run per-file analyzers in batches with checkpointing.

        Processes batches from start_batch, merging results into report.
        Computes complexity hotspots after all batches complete.

        Args:
            batches: File path batches.
            start_batch: Index to start from (for resume).
            report: Report to accumulate results into.
            progress_fn: async callable(step, pct) for progress.
            checkpoint_callback: Optional checkpoint saver.
            file_count: Total files for checkpoint metadata.
        """
        total_batches = len(batches)
        batch_progress_range = 70.0  # 5% to 75%
        all_complexity_modules: List = []

        for idx in range(start_batch, total_batches):
            batch = batches[idx]
            batch_pct = 5.0 + (batch_progress_range * (idx / total_batches))
            await progress_fn(
                f"Batch {idx + 1}/{total_batches}: " f"analyzing {len(batch)} files...",
                batch_pct,
            )

            try:
                regex_results, complexity_modules, ap_results = await asyncio.wait_for(
                    asyncio.gather(
                        self._run_batch_regex(batch),
                        self._run_batch_complexity(batch),
                        self._run_batch_anti_pattern(batch),
                    ),
                    timeout=self.ANALYZER_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Batch %d/%d timed out after %ds, skipping",
                    idx + 1,
                    total_batches,
                    self.ANALYZER_TIMEOUT,
                )
                continue

            report.regex_opportunities.extend(regex_results)
            all_complexity_modules.extend(complexity_modules)
            report.modularization_suggestions.extend(
                ap_results.get("modularization", [])
            )
            report.other_patterns.extend(ap_results.get("other_patterns", []))

            if checkpoint_callback:
                hotspots = self._get_incremental_hotspots(all_complexity_modules)
                await self._save_batch_checkpoint(
                    checkpoint_callback,
                    report,
                    hotspots,
                    idx,
                    file_count,
                )

        # Post-process: final complexity hotspots
        if self._complexity_analyzer and all_complexity_modules:
            hotspots = self._complexity_analyzer.find_hotspots(all_complexity_modules)
            report.complexity_hotspots.extend(hotspots)

    def _get_incremental_hotspots(self, all_complexity_modules: List) -> List:
        """Compute hotspots from accumulated complexity modules."""
        if self._complexity_analyzer and all_complexity_modules:
            return self._complexity_analyzer.find_hotspots(all_complexity_modules)
        return []

    async def _save_batch_checkpoint(
        self,
        callback: Any,
        report: PatternAnalysisReport,
        hotspots: List,
        batch_idx: int,
        file_count: int,
    ) -> None:
        """Serialize and save a checkpoint after a batch completes."""

        def _serialize(items: List) -> List:
            return [i.to_dict() if hasattr(i, "to_dict") else str(i) for i in items]

        await callback(
            "batched_analysis",
            batch_idx + 1,
            {
                "regex": _serialize(report.regex_opportunities),
                "complexity": _serialize(hotspots),
                "modularization": _serialize(report.modularization_suggestions),
                "other_patterns": _serialize(report.other_patterns),
                "files_processed": min((batch_idx + 1) * self.BATCH_SIZE, file_count),
                "total_files": file_count,
            },
        )

    def _count_lines_for_files(self, file_paths: List[str]) -> int:
        """Count total lines across a list of files.

        Args:
            file_paths: List of file paths to count.

        Returns:
            Total line count.
        """
        total = 0
        for fp in file_paths:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    total += sum(1 for _ in f)
            except Exception:
                pass
        return total

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
                logger.debug("Suppressed exception in try block", exc_info=True)

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
            # Issue #1233: Use dedicated analytics executor
            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(
                get_analytics_executor(),
                self._clone_detector.detect_clones,
                directory,
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
            # Issue #1233: Use dedicated analytics executor
            loop = asyncio.get_event_loop()
            opportunities = await loop.run_in_executor(
                get_analytics_executor(),
                self._regex_detector.detect_in_directory,
                directory,
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
            # Issue #1233: Use dedicated analytics executor
            loop = asyncio.get_event_loop()
            modules = await loop.run_in_executor(
                get_analytics_executor(),
                self._complexity_analyzer.analyze_directory,
                directory,
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
            # Issue #1233: Use dedicated analytics executor
            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(
                get_analytics_executor(),
                self._anti_pattern_detector.analyze_directory,
                directory,
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
            similarity_score=(
                min(group.similarity_range) if group.similarity_range else 1.0
            ),
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
                "file_path": (
                    regex_opp.locations[0].file_path if regex_opp.locations else ""
                ),
                "start_line": (
                    regex_opp.locations[0].start_line if regex_opp.locations else 0
                ),
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
                logger.debug("Suppressed exception in try block", exc_info=True)

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
