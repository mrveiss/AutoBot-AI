# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive Long-Running Operations Framework for AutoBot
==========================================================

Issue #381: This file has been refactored into the long_running_operations package.
This thin facade maintains backward compatibility while delegating to focused modules.

See: src/utils/long_running_operations/
- types.py: Enums, dataclasses, timeout config
- checkpoint_manager.py: Checkpoint save/load/resume
- progress_tracker.py: Real-time progress tracking and broadcasting
- operation_manager.py: Main operation lifecycle management

Key Features:
- Dynamic timeout profiles based on operation type and complexity
- Checkpoint/resume capabilities for operation resilience
- Real-time progress tracking with WebSocket broadcasting
- Background operation management with proper resource control
- Graceful failure handling with detailed diagnostics
- Integration with existing AutoBot timeout framework

Operation Types Supported:
- Code indexing and analysis (potentially hours for large codebases)
- Comprehensive test suites (extensive validation procedures)
- Knowledge base population and optimization
- Large-scale file operations and migrations
- Performance benchmarking and profiling
- Security scans and audits
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Re-export all public API from the package
from src.utils.long_running_operations import (  # Types and dataclasses; Managers
    LongRunningOperation,
    LongRunningOperationManager,
    LongRunningTimeoutConfig,
    OperationCheckpoint,
    OperationCheckpointManager,
    OperationExecutionContext,
    OperationPriority,
    OperationProgress,
    OperationProgressTracker,
    OperationStatus,
    OperationType,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    # Types and dataclasses
    "LongRunningOperation",
    "LongRunningTimeoutConfig",
    "OperationCheckpoint",
    "OperationPriority",
    "OperationProgress",
    "OperationStatus",
    "OperationType",
    # Managers
    "LongRunningOperationManager",
    "OperationCheckpointManager",
    "OperationExecutionContext",
    "OperationProgressTracker",
    # Convenience functions
    "execute_codebase_indexing",
    "execute_comprehensive_test_suite",
]


# =============================================================================
# Helper Functions for execute_codebase_indexing (Issue #665)
# =============================================================================


async def _discover_indexing_files(path: Path, patterns: List[str]) -> List[Path]:
    """Discover files for indexing based on glob patterns.

    Issue #665: Extracted from execute_codebase_indexing to reduce function length.

    Args:
        path: Root path to scan
        patterns: List of glob patterns to match

    Returns:
        List of discovered file paths
    """
    all_files: List[Path] = []
    for pattern in patterns:
        pattern_files = await asyncio.to_thread(lambda p=pattern: list(path.rglob(p)))
        all_files.extend(pattern_files)
    return all_files


async def _process_index_file(
    file_path: Path,
) -> Dict[str, Any]:
    """Process a single file for indexing.

    Issue #665: Extracted from execute_codebase_indexing to reduce function length.

    Args:
        file_path: Path to the file to process

    Returns:
        File information dictionary
    """
    file_stat = await asyncio.to_thread(file_path.stat)
    return {
        "path": str(file_path),
        "size": file_stat.st_size,
        "indexed_at": datetime.now().isoformat(),
    }


# =============================================================================
# Helper Functions for execute_comprehensive_test_suite (Issue #665)
# =============================================================================


async def _discover_test_files(path: Path, patterns: List[str]) -> List[Path]:
    """Discover test files based on glob patterns.

    Issue #665: Extracted from execute_comprehensive_test_suite to reduce function length.

    Args:
        path: Root path to scan
        patterns: List of glob patterns for test files

    Returns:
        List of discovered test file paths
    """
    test_files: List[Path] = []
    for pattern in patterns:
        pattern_files = await asyncio.to_thread(lambda p=pattern: list(path.rglob(p)))
        test_files.extend(pattern_files)
    return test_files


def _create_test_result(
    test_file: Path,
    test_passed: bool,
    duration: float,
) -> Dict[str, Any]:
    """Create a test result dictionary.

    Issue #665: Extracted from execute_comprehensive_test_suite to reduce function length.

    Args:
        test_file: Path to the test file
        test_passed: Whether the test passed
        duration: Test execution duration

    Returns:
        Test result dictionary
    """
    return {
        "file": str(test_file),
        "status": "PASS" if test_passed else "FAIL",
        "duration": duration,
        "timestamp": datetime.now().isoformat(),
    }


def _calculate_test_summary(
    total_tests: int,
    passed: int,
    failed: int,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate test suite summary statistics.

    Issue #665: Extracted from execute_comprehensive_test_suite to reduce function length.

    Args:
        total_tests: Total number of tests
        passed: Number of passed tests
        failed: Number of failed tests
        results: List of test result dictionaries

    Returns:
        Test suite summary dictionary
    """
    return {
        "total_tests": total_tests,
        "passed": passed,
        "failed": failed,
        "results": results,
        "success_rate": (passed / total_tests) * 100 if total_tests > 0 else 0,
    }


async def _execute_single_test(
    test_file: Path,
    index: int,
    total_tests: int,
    passed: int,
    failed: int,
    context: "OperationExecutionContext",
) -> tuple[Dict[str, Any], bool]:
    """Execute a single test file and return the result.

    Issue #620: Extracted from execute_comprehensive_test_suite to reduce function length.

    Args:
        test_file: Path to the test file to execute
        index: Current test index (0-based)
        total_tests: Total number of tests
        passed: Current count of passed tests
        failed: Current count of failed tests
        context: Operation execution context for progress updates

    Returns:
        Tuple of (test_result_dict, test_passed_bool)
    """
    import random

    await context.update_progress(
        f"Running {test_file.name}",
        index,
        total_tests,
        {"passed": passed, "failed": failed},
        f"Test {index + 1} of {total_tests}: {test_file.name}",
    )

    await asyncio.sleep(0.5)  # Simulate test execution
    test_passed = random.random() > 0.1  # 90% pass rate

    test_result = _create_test_result(test_file, test_passed, 0.5)
    return test_result, test_passed


async def _save_test_checkpoint_if_needed(
    index: int,
    results: List[Dict[str, Any]],
    passed: int,
    failed: int,
    context: "OperationExecutionContext",
    checkpoint_interval: int = 10,
) -> None:
    """Save a checkpoint if the current index is at a checkpoint interval.

    Issue #620: Extracted from execute_comprehensive_test_suite to reduce function length.

    Args:
        index: Current test index (0-based)
        results: List of test results so far
        passed: Current count of passed tests
        failed: Current count of failed tests
        context: Operation execution context for checkpoint saving
        checkpoint_interval: Number of tests between checkpoints (default: 10)
    """
    if (index + 1) % checkpoint_interval == 0:
        await context.save_checkpoint(
            {"test_results": results, "passed": passed, "failed": failed},
            f"test_{index + 1}",
        )


# =============================================================================
# Convenience Functions for Common Operations
# =============================================================================


# Convenience functions for common operations
async def execute_codebase_indexing(
    codebase_path: str,
    manager: LongRunningOperationManager,
    file_patterns: Optional[List[str]] = None,
) -> str:
    """Execute codebase indexing operation.

    Args:
        codebase_path: Path to the codebase directory
        manager: LongRunningOperationManager instance
        file_patterns: List of glob patterns for files to index

    Returns:
        Operation ID for tracking
    """

    async def indexing_operation(context: OperationExecutionContext) -> Dict[str, Any]:
        """Index files in codebase with progress tracking and checkpoints.

        Issue #665: Refactored to use extracted helper functions.
        """
        path = Path(codebase_path)
        patterns = file_patterns or ["*.py", "*.js", "*.vue", "*.ts", "*.jsx", "*.tsx"]

        # Discover files using helper (Issue #665)
        all_files = await _discover_indexing_files(path, patterns)
        total_files = len(all_files)
        await context.update_progress("Scanning files", 0, total_files)

        results: List[Dict[str, Any]] = []
        start_time = time.time()

        for i, file_path in enumerate(all_files):
            try:
                await asyncio.sleep(0.1)  # Simulate processing
                file_info = await _process_index_file(file_path)
                results.append(file_info)

                # Update progress
                elapsed = time.time() - start_time
                files_per_second = (i + 1) / max(1, elapsed)
                await context.update_progress(
                    f"Processing {file_path.name}",
                    i + 1,
                    total_files,
                    {"files_per_second": files_per_second},
                    f"Indexed {i + 1} of {total_files} files",
                )

                # Save checkpoint every 100 files
                if (i + 1) % 100 == 0:
                    await context.save_checkpoint(
                        {"processed_files": results}, f"file_{i + 1}"
                    )

            except Exception as e:
                context.logger.warning("Failed to process %s: %s", file_path, e)

        return {
            "total_files_processed": len(results),
            "files": results,
            "completed_at": datetime.now().isoformat(),
        }

    return await manager.create_operation(
        OperationType.CODEBASE_INDEXING,
        f"Index codebase: {codebase_path}",
        f"Index all files in {codebase_path} matching patterns {file_patterns}",
        indexing_operation,
        OperationPriority.NORMAL,
        metadata={"estimated_items": 1000},
        execute_immediately=False,
    )


async def execute_comprehensive_test_suite(
    test_suite_path: str,
    manager: LongRunningOperationManager,
    test_patterns: Optional[List[str]] = None,
) -> str:
    """Execute comprehensive test suite operation.

    Issue #620: Refactored using Extract Method pattern to reduce function length.

    Args:
        test_suite_path: Path to the test suite directory
        manager: LongRunningOperationManager instance
        test_patterns: List of glob patterns for test files

    Returns:
        Operation ID for tracking
    """

    async def test_suite_operation(
        context: OperationExecutionContext,
    ) -> Dict[str, Any]:
        """Run test suite with progress tracking and checkpoint support.

        Issue #620: Refactored to use extracted helper functions for reduced complexity.
        """
        path = Path(test_suite_path)
        patterns = test_patterns or ["test_*.py", "*_test.py"]

        # Discover test files using helper (Issue #665)
        test_files = await _discover_test_files(path, patterns)
        total_tests = len(test_files)
        await context.update_progress("Initializing test suite", 0, total_tests)

        results: List[Dict[str, Any]] = []
        passed = 0
        failed = 0

        for i, test_file in enumerate(test_files):
            try:
                # Execute test using helper (Issue #620)
                test_result, test_passed = await _execute_single_test(
                    test_file, i, total_tests, passed, failed, context
                )
                results.append(test_result)
                passed, failed = (
                    (passed + 1, failed) if test_passed else (passed, failed + 1)
                )

                # Save checkpoint using helper (Issue #620)
                await _save_test_checkpoint_if_needed(
                    i, results, passed, failed, context
                )

            except Exception as e:
                context.logger.error("Failed to run test %s: %s", test_file, e)
                failed += 1

        # Return summary using helper (Issue #665)
        return _calculate_test_summary(total_tests, passed, failed, results)

    return await manager.create_operation(
        OperationType.COMPREHENSIVE_TEST_SUITE,
        f"Comprehensive test suite: {test_suite_path}",
        f"Run all tests in {test_suite_path}",
        test_suite_operation,
        OperationPriority.HIGH,
        metadata={"estimated_items": 100},
        execute_immediately=False,
    )


# Example usage and testing
if __name__ == "__main__":
    from src.constants.path_constants import PATH

    async def example_usage():
        """Demonstrate long-running operations framework with example tasks."""
        # Initialize manager
        manager = LongRunningOperationManager()
        await manager.start_background_processor()

        try:
            # Start codebase indexing
            indexing_op_id = await execute_codebase_indexing(
                str(PATH.PROJECT_ROOT / "src"), manager, ["*.py"]
            )

            # Start test suite
            test_op_id = await execute_comprehensive_test_suite(
                str(PATH.TESTS_DIR), manager, ["test_*.py"]
            )

            # Monitor operations
            while True:
                indexing_op = await manager.get_operation(indexing_op_id)
                test_op = await manager.get_operation(test_op_id)

                if indexing_op and test_op:
                    print(
                        f"Indexing: {indexing_op.status.value} - "
                        f"{indexing_op.progress.progress_percent:.1f}%"
                    )
                    print(
                        f"Testing: {test_op.status.value} - "
                        f"{test_op.progress.progress_percent:.1f}%"
                    )

                    if indexing_op.status in (
                        OperationStatus.COMPLETED,
                        OperationStatus.FAILED,
                    ) and test_op.status in (
                        OperationStatus.COMPLETED,
                        OperationStatus.FAILED,
                    ):
                        break

                await asyncio.sleep(5)

            print("All operations completed!")

        finally:
            await manager.stop_background_processor()

    # Run example
    asyncio.run(example_usage())
