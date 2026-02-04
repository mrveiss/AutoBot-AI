# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration Examples for Existing Timeout-Sensitive Operations
===========================================================

This module provides concrete examples of how to migrate existing AutoBot
operations that currently use simple timeouts to the new long-running
operations framework with checkpoint/resume capabilities.

Examples include:
- Knowledge base indexing operations
- Comprehensive test suites
- Code analysis operations
- Security scans
- Performance profiling
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.constants.path_constants import PATH

# Add AutoBot paths
sys.path.append(str(PATH.PROJECT_ROOT))

from .long_running_operations_framework import (
    LongRunningOperationManager,
    OperationExecutionContext,
    OperationPriority,
    OperationType,
)
from .operation_timeout_integration import operation_integration_manager

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for sequence type checks
_SEQUENCE_TYPES = (list, tuple)

# Issue #380: Module-level tuple for path-like type checks
_PATH_TYPES = (str, Path)


# =============================================================================
# Helper Functions for migrate_knowledge_base_indexing (Issue #665)
# =============================================================================


def _collect_indexing_files(codebase_path: Path) -> List[Path]:
    """Collect files to index from codebase.

    Issue #665: Extracted from migrate_knowledge_base_indexing to reduce function length.

    Args:
        codebase_path: Path to codebase root directory

    Returns:
        List of file paths to index
    """
    file_patterns = ["*.py", "*.js", "*.vue", "*.ts", "*.jsx", "*.tsx"]
    all_files = []
    for pattern in file_patterns:
        all_files.extend(codebase_path.rglob(pattern))
    return all_files


async def _get_indexing_resume_state(
    context: "OperationExecutionContext",
) -> tuple[List[Dict[str, Any]], int]:
    """Get resume state for indexing operation.

    Issue #665: Extracted from migrate_knowledge_base_indexing to reduce function length.

    Args:
        context: Operation execution context

    Returns:
        Tuple of (processed_files, start_index)
    """
    if context.should_resume():
        checkpoint_data = context.get_resume_data()
        processed_files = checkpoint_data.intermediate_results.get(
            "processed_files", []
        )
        start_index = len(processed_files)
        logger.info("Resuming indexing from file %s", start_index)
    else:
        processed_files = []
        start_index = 0
    return processed_files, start_index


async def _process_and_checkpoint_files(
    context: "OperationExecutionContext",
    all_files: List[Path],
    total_files: int,
    start_index: int,
    processed_files: List[Dict[str, Any]],
    file_processor,
) -> List[Dict[str, Any]]:
    """Process files with progress tracking and checkpointing.

    Issue #665: Extracted from migrate_knowledge_base_indexing to reduce function length.

    Args:
        context: Operation execution context
        all_files: List of all files to process
        total_files: Total number of files
        start_index: Index to start processing from
        processed_files: Previously processed files (if resuming)
        file_processor: Callable to process individual files

    Returns:
        List of newly indexed file information
    """
    indexed_files = []

    for i, file_path in enumerate(all_files[start_index:], start_index):
        try:
            file_info = await file_processor(file_path)
            indexed_files.append(file_info)

            # Update progress
            elapsed = (datetime.now() - context.operation.started_at).total_seconds()
            await context.update_progress(
                f"Indexing {file_path.name}",
                i + 1,
                total_files,
                {
                    "files_per_second": len(indexed_files) / max(1, elapsed),
                    "current_file": str(file_path),
                },
                f"Processed {i + 1} of {total_files} files",
            )

            # Checkpoint every 100 files
            if (i + 1) % 100 == 0:
                await context.save_checkpoint(
                    {"processed_files": processed_files + indexed_files},
                    f"file_{i + 1}",
                )
                logger.info("Checkpoint saved at file %s", i + 1)

        except Exception as e:
            logger.warning("Failed to process %s: %s", file_path, e)

    return indexed_files


def _build_indexing_result(
    indexed_files: List[Dict[str, Any]],
    resumed: bool,
) -> Dict[str, Any]:
    """Build final result for indexing operation.

    Issue #665: Extracted from migrate_knowledge_base_indexing to reduce function length.

    Args:
        indexed_files: List of indexed file information
        resumed: Whether operation was resumed from checkpoint

    Returns:
        Final result dictionary
    """
    return {
        "total_files_processed": len(indexed_files),
        "files": indexed_files,
        "completed_at": datetime.now().isoformat(),
        "resumed_from_checkpoint": resumed,
    }


# =============================================================================
# Helper Functions for migrate_security_scan_operation (Issue #665)
# =============================================================================


def _collect_security_scan_files(scan_paths: List[Path]) -> List[Path]:
    """Collect files to scan for security issues.

    Issue #665: Extracted from migrate_security_scan_operation to reduce function length.

    Args:
        scan_paths: List of paths to scan

    Returns:
        List of file paths to scan
    """
    files_to_scan = []
    patterns = [
        "*.py",
        "*.js",
        "*.json",
        "*.yaml",
        "*.yml",
        "*.env",
        "*.con",
        "*.config",
    ]
    for scan_path in scan_paths:
        if scan_path.exists():
            for pattern in patterns:
                files_to_scan.extend(scan_path.rglob(pattern))
    return files_to_scan


async def _get_security_scan_resume_state(
    context: "OperationExecutionContext",
) -> tuple[List[Dict[str, Any]], int]:
    """Get resume state for security scan operation.

    Issue #665: Extracted from migrate_security_scan_operation to reduce function length.

    Args:
        context: Operation execution context

    Returns:
        Tuple of (scan_results, start_index)
    """
    if context.should_resume():
        checkpoint_data = context.get_resume_data()
        scan_results = checkpoint_data.intermediate_results.get("scan_results", [])
        start_index = len(scan_results)
        logger.info("Resuming security scan from file %s", start_index)
    else:
        scan_results = []
        start_index = 0
    return scan_results, start_index


def _build_security_scan_result(
    scan_results: List[Dict[str, Any]],
    scan_types: List[str],
    resumed: bool,
) -> Dict[str, Any]:
    """Build final result for security scan operation.

    Issue #665: Extracted from migrate_security_scan_operation to reduce function length.

    Args:
        scan_results: List of scan results
        scan_types: Types of scans performed
        resumed: Whether operation was resumed from checkpoint

    Returns:
        Final result dictionary
    """
    total_vulnerabilities = sum(
        len(result.get("vulnerabilities", [])) for result in scan_results
    )
    return {
        "total_files_scanned": len(scan_results),
        "total_vulnerabilities": total_vulnerabilities,
        "scan_results": scan_results,
        "scan_types": scan_types,
        "completed_at": datetime.now().isoformat(),
        "resumed_from_checkpoint": resumed,
    }


async def _update_security_scan_progress(
    context: "OperationExecutionContext",
    file_path: Path,
    index: int,
    total_files: int,
    vulnerability_count: int,
    scan_types: List[str],
) -> None:
    """Update progress for security scan operation.

    Issue #620: Extracted from _process_security_scan_files to reduce function length. Issue #620.
    """
    await context.update_progress(
        f"Scanning {file_path.name}",
        index + 1,
        total_files,
        {
            "vulnerabilities_found": vulnerability_count,
            "current_file": str(file_path),
            "scan_types": scan_types,
        },
        f"Scanned {index + 1} of {total_files} files",
    )


async def _save_security_scan_checkpoint(
    context: "OperationExecutionContext",
    index: int,
    scan_results: List[Dict[str, Any]],
    checkpoint_interval: int = 50,
) -> None:
    """Save checkpoint for security scan if at interval.

    Issue #620: Extracted from _process_security_scan_files to reduce function length. Issue #620.
    """
    if (index + 1) % checkpoint_interval == 0:
        await context.save_checkpoint(
            {"scan_results": scan_results}, f"file_{index + 1}"
        )


async def _process_security_scan_files(
    context: "OperationExecutionContext",
    files_to_scan: List[Path],
    total_files: int,
    scan_types: List[str],
    scan_results: List[Dict[str, Any]],
    start_index: int,
    file_scanner,
) -> tuple[List[Dict[str, Any]], int]:
    """Process files for security scanning with progress and checkpointing.

    Issue #620: Refactored using Extract Method pattern. Issue #620.

    Args:
        context: Operation execution context.
        files_to_scan: List of files to scan.
        total_files: Total number of files.
        scan_types: Types of scans to perform.
        scan_results: Accumulated scan results.
        start_index: Index to start scanning from.
        file_scanner: Callable to scan individual files.

    Returns:
        Tuple of (scan_results, vulnerability_count).
    """
    vulnerability_count = 0

    for i, file_path in enumerate(files_to_scan[start_index:], start_index):
        try:
            await _update_security_scan_progress(
                context, file_path, i, total_files, vulnerability_count, scan_types
            )
            file_scan_result = await file_scanner(file_path, scan_types)
            scan_results.append(file_scan_result)

            if file_scan_result.get("vulnerabilities"):
                vulnerability_count += len(file_scan_result["vulnerabilities"])

            await _save_security_scan_checkpoint(context, i, scan_results)
        except Exception as e:
            logger.warning("Failed to scan %s: %s", file_path, e)

    return scan_results, vulnerability_count


class ExistingOperationMigrator:
    """Utility class to help migrate existing operations to the long-running framework."""

    def __init__(self, manager: LongRunningOperationManager):
        """Initialize migrator with operation manager instance."""
        self.manager = manager

    async def _create_indexing_operation_function(self):
        """Create the enhanced indexing operation function.

        Issue #620: Extracted from migrate_knowledge_base_indexing to reduce function length. Issue #620.

        Returns:
            Async function for enhanced indexing operation.
        """

        async def enhanced_indexing_operation(context: OperationExecutionContext):
            """Enhanced indexing with proper progress tracking and checkpoints."""
            codebase_path = Path(PATH.PROJECT_ROOT)

            # Collect files using helper (Issue #665)
            all_files = _collect_indexing_files(codebase_path)
            total_files = len(all_files)
            await context.update_progress("File discovery", 0, total_files)

            # Get resume state using helper (Issue #665)
            processed_files, start_index = await _get_indexing_resume_state(context)
            indexed_files = []

            try:
                # Process files using helper (Issue #665)
                indexed_files = await _process_and_checkpoint_files(
                    context,
                    all_files,
                    total_files,
                    start_index,
                    processed_files,
                    self._process_file_for_indexing,
                )
                # Build result using helper (Issue #665)
                return _build_indexing_result(indexed_files, context.should_resume())
            except Exception as e:
                await context.save_checkpoint(
                    {
                        "processed_files": processed_files + indexed_files,
                        "error": str(e),
                    },
                    "error_recovery",
                )
                raise

        return enhanced_indexing_operation

    async def migrate_knowledge_base_indexing(self):
        """Migrate existing knowledge base indexing operation.

        Issue #620: Refactored using Extract Method pattern.

        BEFORE: Simple 30-second timeout, no progress/checkpoint, lost work on timeout.
        AFTER: Dynamic timeout, real-time progress, checkpoint every 100 files, resume capability.
        """
        enhanced_indexing_operation = await self._create_indexing_operation_function()

        operation_id = await self.manager.create_operation(
            operation_type=OperationType.CODEBASE_INDEXING,
            name="Enhanced Knowledge Base Indexing",
            description="Migrate from simple timeout to checkpoint-based indexing",
            operation_function=enhanced_indexing_operation,
            priority=OperationPriority.NORMAL,
            estimated_items=len(list(Path(PATH.PROJECT_ROOT).rglob("*.py"))),
            execute_immediately=False,
        )

        logger.info("Migrated knowledge base indexing operation: %s", operation_id)
        return operation_id

    async def migrate_comprehensive_test_suite(self):
        """
        Migrate comprehensive test suite to long-running framework.

        Issue #665: Refactored to delegate to phase-specific helper methods.
        Issue #620: Further refactored using Extract Method pattern.

        BEFORE:
        - Fixed 10-minute timeout regardless of test count
        - No visibility into which tests are running
        - No ability to resume failed test runs
        - Complete re-run required on timeout

        AFTER:
        - Dynamic timeout based on test count
        - Real-time test progress and results
        - Resume from last completed test
        - Parallel execution with resource management
        """
        operation_id = await self.manager.create_operation(
            operation_type=OperationType.COMPREHENSIVE_TEST_SUITE,
            name="Enhanced Comprehensive Test Suite",
            description="Migrate from fixed timeout to dynamic checkpoint-based testing",
            operation_function=self._enhanced_test_suite_operation,
            priority=OperationPriority.HIGH,
            estimated_items=len(
                list(Path(f"{PATH.PROJECT_ROOT}/tests").rglob("test_*.py"))
            ),
            execute_immediately=False,
        )

        logger.info("Migrated comprehensive test suite operation: %s", operation_id)
        return operation_id

    async def _enhanced_test_suite_operation(
        self, context: OperationExecutionContext
    ) -> Dict[str, Any]:
        """
        Enhanced test suite with checkpoint/resume and parallel execution.

        Issue #620: Extracted from migrate_comprehensive_test_suite to reduce
        function length using Extract Method pattern. Issue #620.
        """
        # Setup phase: discover tests
        test_files = self._discover_test_files()
        total_tests = len(test_files)
        await context.update_progress("Test discovery", 0, total_tests)

        # Resume phase: check for checkpoint data
        completed_tests, failed_tests, start_index = self._get_resume_state(context)

        # Execution phase: run tests with resource management
        completed_tests, failed_tests = await self._execute_tests(
            context,
            test_files,
            total_tests,
            completed_tests,
            failed_tests,
            start_index,
        )

        # Validation phase: calculate and return results
        return self._calculate_test_results(
            total_tests, completed_tests, failed_tests, context.should_resume()
        )

    def _discover_test_files(self) -> List[Path]:
        """Discover all test files in the tests directory.

        Issue #665: Extracted from migrate_comprehensive_test_suite to reduce function length.

        Returns:
            List of Path objects pointing to test files.
        """
        test_path = Path(f"{PATH.PROJECT_ROOT}/tests")
        test_patterns = ["test_*.py", "*_test.py"]

        test_files = []
        for pattern in test_patterns:
            test_files.extend(test_path.rglob(pattern))
        return test_files

    def _get_resume_state(
        self, context: OperationExecutionContext
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        """Get resume state from checkpoint if resuming.

        Issue #665: Extracted from migrate_comprehensive_test_suite to reduce function length.

        Args:
            context: The operation execution context.

        Returns:
            Tuple of (completed_tests, failed_tests, start_index).
        """
        if context.should_resume():
            checkpoint_data = context.get_resume_data()
            completed_tests = checkpoint_data.intermediate_results.get(
                "completed_tests", []
            )
            failed_tests = checkpoint_data.intermediate_results.get("failed_tests", [])
            start_index = len(completed_tests) + len(failed_tests)
            logger.info("Resuming test suite from test %s", start_index)
        else:
            completed_tests = []
            failed_tests = []
            start_index = 0
        return completed_tests, failed_tests, start_index

    async def _execute_tests(
        self,
        context: OperationExecutionContext,
        test_files: List[Path],
        total_tests: int,
        completed_tests: List[Dict[str, Any]],
        failed_tests: List[Dict[str, Any]],
        start_index: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Execute tests with resource management and checkpointing.

        Issue #665: Extracted from migrate_comprehensive_test_suite.
        Issue #620: Refactored using Extract Method pattern. Issue #620.
        """
        import concurrent.futures

        max_concurrent = min(4, len(test_files))

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent
        ) as executor:
            for i, test_file in enumerate(test_files[start_index:], start_index):
                try:
                    await self._update_test_progress(
                        context,
                        test_file,
                        i,
                        total_tests,
                        completed_tests,
                        failed_tests,
                    )
                    test_result = await self._run_test_with_executor(
                        executor, test_file
                    )

                    if test_result["status"] == "PASS":
                        completed_tests.append(test_result)
                    else:
                        failed_tests.append(test_result)

                    if (i + 1) % 10 == 0:
                        await context.save_checkpoint(
                            {
                                "completed_tests": completed_tests,
                                "failed_tests": failed_tests,
                            },
                            f"test_{i + 1}",
                        )
                except Exception as e:
                    failed_tests.append(self._record_test_error(test_file, e))

        return completed_tests, failed_tests

    def _calculate_test_results(
        self,
        total_tests: int,
        completed_tests: List[Dict[str, Any]],
        failed_tests: List[Dict[str, Any]],
        resumed_from_checkpoint: bool,
    ) -> Dict[str, Any]:
        """Calculate final test results.

        Issue #665: Extracted from migrate_comprehensive_test_suite to reduce function length.

        Args:
            total_tests: Total number of tests.
            completed_tests: List of completed test results.
            failed_tests: List of failed test results.
            resumed_from_checkpoint: Whether operation was resumed.

        Returns:
            Dictionary containing final test results.
        """
        total_passed = len(completed_tests)
        total_failed = len(failed_tests)
        success_rate = (total_passed / total_tests) * 100 if total_tests > 0 else 0

        return {
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "success_rate": success_rate,
            "completed_tests": completed_tests,
            "failed_tests": failed_tests,
            "resumed_from_checkpoint": resumed_from_checkpoint,
        }

    async def _update_test_progress(
        self,
        context: OperationExecutionContext,
        test_file: Path,
        index: int,
        total_tests: int,
        completed_tests: List[Dict[str, Any]],
        failed_tests: List[Dict[str, Any]],
    ) -> None:
        """Update progress for current test execution.

        Issue #620: Extracted from _execute_tests to reduce function length. Issue #620.

        Args:
            context: The operation execution context.
            test_file: Current test file being executed.
            index: Current test index.
            total_tests: Total number of tests.
            completed_tests: List of completed test results.
            failed_tests: List of failed test results.
        """
        await context.update_progress(
            f"Running {test_file.name}",
            index,
            total_tests,
            {
                "passed": len(completed_tests),
                "failed": len(failed_tests),
                "current_test": str(test_file),
            },
            f"Test {index + 1} of {total_tests}: {test_file.name}",
        )

    async def _run_test_with_executor(
        self,
        executor,
        test_file: Path,
    ) -> Dict[str, Any]:
        """Run a single test using the thread pool executor.

        Issue #620: Extracted from _execute_tests to reduce function length. Issue #620.

        Args:
            executor: ThreadPoolExecutor instance.
            test_file: Test file to execute.

        Returns:
            Test result dictionary.
        """
        future = executor.submit(self._run_single_test, test_file)
        test_result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: future.result(timeout=300)
        )
        return test_result

    def _record_test_error(
        self,
        test_file: Path,
        error: Exception,
    ) -> Dict[str, Any]:
        """Record a test execution error.

        Issue #620: Extracted from _execute_tests to reduce function length. Issue #620.

        Args:
            test_file: Test file that failed.
            error: Exception that occurred.

        Returns:
            Error result dictionary.
        """
        logger.warning("Test %s failed with error: %s", test_file, error)
        return {
            "file": str(test_file),
            "status": "ERROR",
            "error": str(error),
            "duration": 0,
        }

    async def migrate_security_scan_operation(self):
        """Migrate security scanning operation.

        Issue #620: Refactored using Extract Method pattern. Issue #620.

        BEFORE: 5-minute timeout, no progress visibility, complete re-scan on timeout.
        AFTER: Dynamic timeout, real-time progress, resume capability, incremental scanning.
        """

        async def enhanced_security_scan_operation(context: OperationExecutionContext):
            """Enhanced security scan with checkpointing and progress tracking."""
            scan_paths = [Path(PATH.PROJECT_ROOT)]
            scan_types = ["vulnerability", "dependency", "secrets"]

            files_to_scan = _collect_security_scan_files(scan_paths)
            total_files = len(files_to_scan)
            await context.update_progress(
                "File discovery for security scan", 0, total_files
            )

            scan_results, start_index = await _get_security_scan_resume_state(context)
            scan_results, _ = await _process_security_scan_files(
                context,
                files_to_scan,
                total_files,
                scan_types,
                scan_results,
                start_index,
                self._scan_file_for_security,
            )

            return _build_security_scan_result(
                scan_results, scan_types, context.should_resume()
            )

        operation_id = await self.manager.create_operation(
            operation_type=OperationType.SECURITY_SCAN,
            name="Enhanced Security Scan",
            description="Migrate from fixed timeout to dynamic checkpoint-based security scanning",
            operation_function=enhanced_security_scan_operation,
            priority=OperationPriority.HIGH,
            estimated_items=1000,
            execute_immediately=False,
        )

        logger.info("Migrated security scan operation: %s", operation_id)
        return operation_id

    async def _process_file_for_indexing(self, file_path: Path) -> Dict[str, Any]:
        """Process a single file for indexing (placeholder implementation)"""
        await asyncio.sleep(0.01)  # Simulate processing time

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return {
                "path": str(file_path),
                "size": len(content),
                "lines": len(content.splitlines()),
                "extension": file_path.suffix,
                "indexed_at": datetime.now().isoformat(),
                "content_hash": hash(content) % 1000000,  # Simple hash for example
            }
        except Exception as e:
            return {
                "path": str(file_path),
                "error": str(e),
                "indexed_at": datetime.now().isoformat(),
            }

    def _run_single_test(self, test_file: Path) -> Dict[str, Any]:
        """Run a single test file (placeholder implementation)"""
        import subprocess  # nosec B404 - controlled pytest execution
        import time

        start_time = time.time()

        try:
            # Run pytest on single file
            result = subprocess.run(  # nosec B607 - pytest runner
                ["python", "-m", "pytest", str(test_file), "-v"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per test
                cwd=str(PATH.PROJECT_ROOT),
            )

            duration = time.time() - start_time

            return {
                "file": str(test_file),
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "duration": duration,
                "output": result.stdout,
                "errors": result.stderr,
                "exit_code": result.returncode,
                "timestamp": datetime.now().isoformat(),
            }

        except subprocess.TimeoutExpired:
            return {
                "file": str(test_file),
                "status": "TIMEOUT",
                "duration": time.time() - start_time,
                "error": "Test timed out after 5 minutes",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "file": str(test_file),
                "status": "ERROR",
                "duration": time.time() - start_time,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _check_vulnerability_patterns(
        self, content: str, vulnerabilities: List[Dict[str, Any]]
    ) -> None:
        """Check for common vulnerability patterns in file content. Issue #620."""
        if "password" in content.lower() and "=" in content:
            vulnerabilities.append(
                {
                    "type": "hardcoded_credential",
                    "severity": "high",
                    "description": "Potential hardcoded password detected",
                }
            )

        if "api_key" in content.lower() and "=" in content:
            vulnerabilities.append(
                {
                    "type": "hardcoded_api_key",
                    "severity": "high",
                    "description": "Potential hardcoded API key detected",
                }
            )

    def _check_secret_patterns(
        self, content: str, vulnerabilities: List[Dict[str, Any]]
    ) -> None:
        """Check for potential secret patterns in file content. Issue #620."""
        import re

        if re.search(r"[A-Za-z0-9]{20,}", content):
            vulnerabilities.append(
                {
                    "type": "potential_secret",
                    "severity": "medium",
                    "description": "Long string detected, might be a secret",
                }
            )

    async def _scan_file_for_security(
        self, file_path: Path, scan_types: List[str]
    ) -> Dict[str, Any]:
        """Scan a single file for security issues (placeholder implementation)"""
        await asyncio.sleep(0.02)  # Simulate scan time

        vulnerabilities: List[Dict[str, Any]] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            if "vulnerability" in scan_types:
                self._check_vulnerability_patterns(content, vulnerabilities)

            if "secrets" in scan_types:
                self._check_secret_patterns(content, vulnerabilities)

            return {
                "file": str(file_path),
                "vulnerabilities": vulnerabilities,
                "scan_types": scan_types,
                "scanned_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "file": str(file_path),
                "error": str(e),
                "scanned_at": datetime.now().isoformat(),
            }


# Issue #315 - Extracted helper functions to reduce nesting depth


def _estimate_items_from_arg(arg: Any) -> int:
    """Estimate item count from first argument (Issue #315 - extracted helper)."""
    if isinstance(arg, _SEQUENCE_TYPES):  # Issue #380
        return len(arg)
    if isinstance(arg, _PATH_TYPES):  # Issue #380
        try:
            path = Path(arg)
            if path.is_dir():
                return len(list(path.rglob("*")))
            return 1
        except Exception:
            return 1
    return 1


def _get_estimated_items(estimated_items: Optional[int], args: tuple) -> int:
    """Calculate estimated items for operation (Issue #315 - extracted helper)."""
    if estimated_items is not None:
        return estimated_items
    if args:
        return _estimate_items_from_arg(args[0])
    return 1


async def _wait_for_operation_completion(operation_id: str) -> Any:
    """Wait for operation to complete and return result (Issue #315 - extracted helper)."""
    terminal_states = {"completed", "failed", "timeout", "cancelled"}
    while True:
        operation = operation_integration_manager.operation_manager.get_operation(
            operation_id
        )
        if operation.status.value in terminal_states:
            if operation.result is not None:
                return operation.result
            if operation.error_info:
                raise Exception(operation.error_info)
            return {"status": operation.status.value}
        await asyncio.sleep(1)


def _create_progress_wrapper(context: OperationExecutionContext):
    """Create progress callback wrapper for context (Issue #315 - extracted helper)."""

    async def progress_wrapper(step, processed, total=None, **metrics):
        """Wrap progress updates for timeout context."""
        await context.update_progress(step, processed, total, metrics)

    return progress_wrapper


# Decorator-based migration helpers
def _create_enhanced_operation(func, args, kwargs, progress_callback):
    """
    Create enhanced operation callable with progress tracking.

    Wraps the original function to inject progress callbacks and handle
    both sync and async functions appropriately. Issue #620.
    """

    async def enhanced_operation(context: OperationExecutionContext):
        """Enhanced operation with progress tracking."""
        # Inject progress callback if function expects it
        if progress_callback or "progress_callback" in func.__code__.co_varnames:
            kwargs["progress_callback"] = _create_progress_wrapper(context)

        # Execute original function
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return await asyncio.to_thread(func, *args, **kwargs)

    return enhanced_operation


async def _execute_via_operation_manager(
    enhanced_operation, operation_type, func, priority, items
):
    """
    Execute operation through the operation manager.

    Creates and tracks the operation, then waits for completion. Issue #620.
    """
    operation_id = await operation_integration_manager.operation_manager.create_operation(
        operation_type=operation_type,
        name=f"Migrated: {func.__name__}",
        description=f"Auto-migrated operation from {func.__module__}.{func.__name__}",
        operation_function=enhanced_operation,
        priority=priority,
        estimated_items=items,
        execute_immediately=True,
    )
    return await _wait_for_operation_completion(operation_id)


def migrate_timeout_operation(
    operation_type: OperationType,
    estimated_items: Optional[int] = None,
    priority: OperationPriority = OperationPriority.NORMAL,
):
    """
    Decorator to automatically migrate existing timeout-sensitive functions
    to the long-running operations framework
    """

    def decorator(func):
        """Wrap function with long-running operation tracking."""

        async def wrapper(*args, **kwargs):
            """Execute operation with enhanced progress and timeout handling."""
            progress_callback = kwargs.pop("progress_callback", None)
            enhanced_op = _create_enhanced_operation(
                func, args, kwargs, progress_callback
            )
            items = _get_estimated_items(estimated_items, args)

            # Execute with operation manager if available
            if (
                operation_integration_manager
                and operation_integration_manager.operation_manager
            ):
                return await _execute_via_operation_manager(
                    enhanced_op, operation_type, func, priority, items
                )

            # Fallback to direct execution
            return await enhanced_op(None)

        return wrapper

    return decorator


# Example usage
if __name__ == "__main__":

    async def demonstration():
        """Demonstrate the migration capabilities"""

        # Initialize the operation manager
        if operation_integration_manager:
            await operation_integration_manager.initialize()

            migrator = ExistingOperationMigrator(
                operation_integration_manager.operation_manager
            )

            # Migrate existing operations
            indexing_op = await migrator.migrate_knowledge_base_indexing()
            test_op = await migrator.migrate_comprehensive_test_suite()
            security_op = await migrator.migrate_security_scan_operation()

            print("Migrated operations:")
            print(f"  - Indexing: {indexing_op}")
            print(f"  - Testing: {test_op}")
            print(f"  - Security: {security_op}")

            # Example of decorator-based migration
            @migrate_timeout_operation(OperationType.CODE_ANALYSIS, estimated_items=100)
            async def analyze_codebase(path: str, patterns: List[str]):
                """Example function that gets automatically migrated"""
                # Original implementation would go here
                await asyncio.sleep(2)  # Simulate work
                return {"analyzed_files": 100, "path": path, "patterns": patterns}

            # Call the migrated function
            result = await analyze_codebase(f"{PATH.PROJECT_ROOT}/src", ["*.py"])
            print(f"Analysis result: {result}")

            await operation_integration_manager.shutdown()
        else:
            print("Operation integration manager not available")

    # Run demonstration
    asyncio.run(demonstration())
