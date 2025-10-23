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
from typing import Any, Callable, Dict, List, Optional

from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PATH

# Add AutoBot paths
sys.path.append(str(PATH.PROJECT_ROOT))

from .long_running_operations_framework import (
    LongRunningOperationManager,
    OperationExecutionContext,
    OperationPriority,
    OperationType,
)
from .operation_timeout_integration import (
    long_running_operation,
    operation_integration_manager,
)

logger = logging.getLogger(__name__)


class ExistingOperationMigrator:
    """
    Utility class to help migrate existing operations to the long-running framework
    """

    def __init__(self, manager: LongRunningOperationManager):
        self.manager = manager

    async def migrate_knowledge_base_indexing(self):
        """
        Migrate existing knowledge base indexing operation

        BEFORE (problematic):
        - Simple 30-second timeout
        - No progress tracking
        - No checkpoint/resume
        - Lost work on timeout

        AFTER (robust):
        - Dynamic timeout based on codebase size
        - Real-time progress tracking
        - Checkpoint every 100 files
        - Resume capability
        """

        # Example of existing problematic code:
        # try:
        #     result = await asyncio.wait_for(
        #         index_all_files(),
        #         timeout=30.0  # Too short for large codebases!
        #     )
        # except asyncio.TimeoutError:
        #     return {"error": "Indexing timed out"}  # Work lost!

        async def enhanced_indexing_operation(context: OperationExecutionContext):
            """Enhanced indexing with proper progress tracking and checkpoints"""

            codebase_path = Path(PATH.PROJECT_ROOT)
            file_patterns = ["*.py", "*.js", "*.vue", "*.ts", "*.jsx", "*.tsx"]

            # Count files first for accurate progress
            all_files = []
            for pattern in file_patterns:
                all_files.extend(codebase_path.rglob(pattern))

            total_files = len(all_files)
            await context.update_progress("File discovery", 0, total_files)

            # Check if resuming from checkpoint
            if context.should_resume():
                checkpoint_data = context.get_resume_data()
                processed_files = checkpoint_data.intermediate_results.get(
                    "processed_files", []
                )
                start_index = len(processed_files)
                logger.info(f"Resuming indexing from file {start_index}")
            else:
                processed_files = []
                start_index = 0

            indexed_files = []

            try:
                for i, file_path in enumerate(all_files[start_index:], start_index):
                    try:
                        # Process file with proper error handling
                        file_info = await self._process_file_for_indexing(file_path)
                        indexed_files.append(file_info)

                        # Update progress
                        await context.update_progress(
                            f"Indexing {file_path.name}",
                            i + 1,
                            total_files,
                            {
                                "files_per_second": len(indexed_files)
                                / max(
                                    1,
                                    (
                                        datetime.now() - context.operation.started_at
                                    ).total_seconds(),
                                ),
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
                            logger.info(f"Checkpoint saved at file {i + 1}")

                    except Exception as e:
                        logger.warning(f"Failed to process {file_path}: {e}")
                        # Continue processing other files

                return {
                    "total_files_processed": len(indexed_files),
                    "files": indexed_files,
                    "completed_at": datetime.now().isoformat(),
                    "resumed_from_checkpoint": context.should_resume(),
                }

            except Exception as e:
                # Save checkpoint before failing
                await context.save_checkpoint(
                    {
                        "processed_files": processed_files + indexed_files,
                        "error": str(e),
                    },
                    "error_recovery",
                )
                raise

        # Create and execute the enhanced operation
        operation_id = await self.manager.create_operation(
            operation_type=OperationType.CODEBASE_INDEXING,
            name="Enhanced Knowledge Base Indexing",
            description="Migrate from simple timeout to checkpoint-based indexing",
            operation_function=enhanced_indexing_operation,
            priority=OperationPriority.NORMAL,
            estimated_items=len(list(Path(PATH.PROJECT_ROOT).rglob("*.py"))),
            execute_immediately=False,
        )

        logger.info(f"Migrated knowledge base indexing operation: {operation_id}")
        return operation_id

    async def migrate_comprehensive_test_suite(self):
        """
        Migrate comprehensive test suite to long-running framework

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

        async def enhanced_test_suite_operation(context: OperationExecutionContext):
            """Enhanced test suite with checkpoint/resume and parallel execution"""

            test_path = Path(f"{PATH.PROJECT_ROOT}/tests")
            test_patterns = ["test_*.py", "*_test.py"]

            # Discover all test files
            test_files = []
            for pattern in test_patterns:
                test_files.extend(test_path.rglob(pattern))

            total_tests = len(test_files)
            await context.update_progress("Test discovery", 0, total_tests)

            # Check if resuming
            if context.should_resume():
                checkpoint_data = context.get_resume_data()
                completed_tests = checkpoint_data.intermediate_results.get(
                    "completed_tests", []
                )
                failed_tests = checkpoint_data.intermediate_results.get(
                    "failed_tests", []
                )
                start_index = len(completed_tests) + len(failed_tests)
                logger.info(f"Resuming test suite from test {start_index}")
            else:
                completed_tests = []
                failed_tests = []
                start_index = 0

            # Run tests with proper resource management
            import concurrent.futures
            import subprocess

            # Limit concurrent test execution
            max_concurrent = min(4, len(test_files))

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_concurrent
            ) as executor:
                for i, test_file in enumerate(test_files[start_index:], start_index):
                    try:
                        await context.update_progress(
                            f"Running {test_file.name}",
                            i,
                            total_tests,
                            {
                                "passed": len(completed_tests),
                                "failed": len(failed_tests),
                                "current_test": str(test_file),
                            },
                            f"Test {i + 1} of {total_tests}: {test_file.name}",
                        )

                        # Run test with timeout
                        future = executor.submit(self._run_single_test, test_file)
                        test_result = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: future.result(timeout=300)
                        )

                        if test_result["status"] == "PASS":
                            completed_tests.append(test_result)
                        else:
                            failed_tests.append(test_result)

                        # Checkpoint every 10 tests
                        if (i + 1) % 10 == 0:
                            await context.save_checkpoint(
                                {
                                    "completed_tests": completed_tests,
                                    "failed_tests": failed_tests,
                                },
                                f"test_{i + 1}",
                            )

                    except Exception as e:
                        logger.warning(f"Test {test_file} failed with error: {e}")
                        failed_tests.append(
                            {
                                "file": str(test_file),
                                "status": "ERROR",
                                "error": str(e),
                                "duration": 0,
                            }
                        )

            # Calculate final results
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
                "resumed_from_checkpoint": context.should_resume(),
            }

        operation_id = await self.manager.create_operation(
            operation_type=OperationType.COMPREHENSIVE_TEST_SUITE,
            name="Enhanced Comprehensive Test Suite",
            description="Migrate from fixed timeout to dynamic checkpoint-based testing",
            operation_function=enhanced_test_suite_operation,
            priority=OperationPriority.HIGH,
            estimated_items=len(
                list(Path(f"{PATH.PROJECT_ROOT}/tests").rglob("test_*.py"))
            ),
            execute_immediately=False,
        )

        logger.info(f"Migrated comprehensive test suite operation: {operation_id}")
        return operation_id

    async def migrate_security_scan_operation(self):
        """
        Migrate security scanning operation

        BEFORE:
        - 5-minute timeout regardless of codebase size
        - No progress visibility
        - Complete re-scan on timeout
        - No incremental scanning

        AFTER:
        - Dynamic timeout based on files to scan
        - Real-time scan progress with file details
        - Resume from last scanned file
        - Incremental scanning with vulnerability tracking
        """

        async def enhanced_security_scan_operation(context: OperationExecutionContext):
            """Enhanced security scan with checkpointing and progress tracking"""

            scan_paths = [Path(PATH.PROJECT_ROOT)]
            scan_types = ["vulnerability", "dependency", "secrets"]

            # Collect files to scan
            files_to_scan = []
            for scan_path in scan_paths:
                if scan_path.exists():
                    # Include various file types for security scanning
                    patterns = [
                        "*.py",
                        "*.js",
                        "*.json",
                        "*.yaml",
                        "*.yml",
                        "*.env",
                        "*.conf",
                        "*.config",
                    ]
                    for pattern in patterns:
                        files_to_scan.extend(scan_path.rglob(pattern))

            total_files = len(files_to_scan)
            await context.update_progress(
                "File discovery for security scan", 0, total_files
            )

            # Check if resuming
            if context.should_resume():
                checkpoint_data = context.get_resume_data()
                scan_results = checkpoint_data.intermediate_results.get(
                    "scan_results", []
                )
                start_index = len(scan_results)
                logger.info(f"Resuming security scan from file {start_index}")
            else:
                scan_results = []
                start_index = 0

            # Perform security scanning
            vulnerability_count = 0

            for i, file_path in enumerate(files_to_scan[start_index:], start_index):
                try:
                    await context.update_progress(
                        f"Scanning {file_path.name}",
                        i + 1,
                        total_files,
                        {
                            "vulnerabilities_found": vulnerability_count,
                            "current_file": str(file_path),
                            "scan_types": scan_types,
                        },
                        f"Scanned {i + 1} of {total_files} files",
                    )

                    # Simulate security scanning
                    file_scan_result = await self._scan_file_for_security(
                        file_path, scan_types
                    )
                    scan_results.append(file_scan_result)

                    if file_scan_result.get("vulnerabilities"):
                        vulnerability_count += len(file_scan_result["vulnerabilities"])

                    # Checkpoint every 50 files
                    if (i + 1) % 50 == 0:
                        await context.save_checkpoint(
                            {"scan_results": scan_results}, f"file_{i + 1}"
                        )

                except Exception as e:
                    logger.warning(f"Failed to scan {file_path}: {e}")

            # Generate summary
            total_vulnerabilities = sum(
                len(result.get("vulnerabilities", [])) for result in scan_results
            )

            return {
                "total_files_scanned": len(scan_results),
                "total_vulnerabilities": total_vulnerabilities,
                "scan_results": scan_results,
                "scan_types": scan_types,
                "completed_at": datetime.now().isoformat(),
                "resumed_from_checkpoint": context.should_resume(),
            }

        operation_id = await self.manager.create_operation(
            operation_type=OperationType.SECURITY_SCAN,
            name="Enhanced Security Scan",
            description="Migrate from fixed timeout to dynamic checkpoint-based security scanning",
            operation_function=enhanced_security_scan_operation,
            priority=OperationPriority.HIGH,
            estimated_items=1000,  # Estimate based on typical codebase
            execute_immediately=False,
        )

        logger.info(f"Migrated security scan operation: {operation_id}")
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
        import subprocess
        import time

        start_time = time.time()

        try:
            # Run pytest on single file
            result = subprocess.run(
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

    async def _scan_file_for_security(
        self, file_path: Path, scan_types: List[str]
    ) -> Dict[str, Any]:
        """Scan a single file for security issues (placeholder implementation)"""
        await asyncio.sleep(0.02)  # Simulate scan time

        vulnerabilities = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            # Simple pattern matching for demonstration
            if "vulnerability" in scan_types:
                # Check for common vulnerability patterns
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

            if "secrets" in scan_types:
                # Check for secret patterns
                import re

                if re.search(
                    r"[A-Za-z0-9]{20,}", content
                ):  # Long strings that might be secrets
                    vulnerabilities.append(
                        {
                            "type": "potential_secret",
                            "severity": "medium",
                            "description": "Long string detected, might be a secret",
                        }
                    )

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


# Decorator-based migration helpers
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
        async def wrapper(*args, **kwargs):
            # Extract progress callback if provided
            progress_callback = kwargs.pop("progress_callback", None)

            async def enhanced_operation(context: OperationExecutionContext):
                """Enhanced operation with progress tracking"""

                # If original function expects progress callback, provide it
                if (
                    progress_callback
                    or "progress_callback" in func.__code__.co_varnames
                ):

                    async def progress_wrapper(step, processed, total=None, **metrics):
                        await context.update_progress(step, processed, total, metrics)

                    kwargs["progress_callback"] = progress_wrapper

                # Execute original function
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return await asyncio.to_thread(func, *args, **kwargs)

            # Calculate estimated items if not provided
            items = estimated_items
            if items is None and args:
                # Try to estimate based on first argument (often a path or list)
                first_arg = args[0]
                if isinstance(first_arg, (list, tuple)):
                    items = len(first_arg)
                elif isinstance(first_arg, (str, Path)):
                    try:
                        path = Path(first_arg)
                        if path.is_dir():
                            items = len(list(path.rglob("*")))
                        else:
                            items = 1
                    except:
                        items = 1
                else:
                    items = 1

            # Create and execute operation
            if (
                operation_integration_manager
                and operation_integration_manager.operation_manager
            ):
                operation_id = await operation_integration_manager.operation_manager.create_operation(
                    operation_type=operation_type,
                    name=f"Migrated: {func.__name__}",
                    description=f"Auto-migrated operation from {func.__module__}.{func.__name__}",
                    operation_function=enhanced_operation,
                    priority=priority,
                    estimated_items=items or 1,
                    execute_immediately=True,
                )

                # Wait for completion and return result
                while True:
                    operation = (
                        operation_integration_manager.operation_manager.get_operation(
                            operation_id
                        )
                    )
                    if operation.status.value in [
                        "completed",
                        "failed",
                        "timeout",
                        "cancelled",
                    ]:
                        if operation.result is not None:
                            return operation.result
                        elif operation.error_info:
                            raise Exception(operation.error_info)
                        else:
                            return {"status": operation.status.value}

                    await asyncio.sleep(1)
            else:
                # Fallback to direct execution
                return await enhanced_operation(None)

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

            print(f"Migrated operations:")
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
