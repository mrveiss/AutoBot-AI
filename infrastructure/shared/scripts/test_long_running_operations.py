#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test Script for Long-Running Operations Framework
===============================================

This script demonstrates the comprehensive timeout architecture for AutoBot's
long-running operations with checkpoint/resume capabilities, real-time progress
tracking, and intelligent timeout management.

Run this script to see:
1. Operations that "either finish or fail" rather than timing out prematurely
2. Checkpoint/resume capabilities for robustness
3. Real-time progress tracking for user visibility
4. Operation-specific timeout profiles
5. Background operation support
6. Graceful failure handling

Usage:
    python scripts/test_long_running_operations.py [--demo-type all|indexing|testing|security]
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime

# Add AutoBot paths
sys.path.append("/home/kali/Desktop/AutoBot")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import our framework
try:
    from src.utils.long_running_operations_framework import (
        LongRunningOperationManager,
        OperationPriority,
        OperationStatus,
        OperationType,
        execute_codebase_indexing,
        execute_comprehensive_test_suite,
    )
    from src.utils.timeout_migration_examples import ExistingOperationMigrator

    FRAMEWORK_AVAILABLE = True
except ImportError as e:
    logger.error(f"Long-running operations framework not available: {e}")
    FRAMEWORK_AVAILABLE = False


class LongRunningOperationsDemo:
    """Demonstration of the long-running operations framework"""

    def __init__(self):
        """Initialize demo with empty manager and migrator references."""
        self.manager = None
        self.migrator = None

    async def initialize(self):
        """Initialize the demo"""
        if not FRAMEWORK_AVAILABLE:
            raise RuntimeError("Framework not available")

        # Initialize operation manager
        self.manager = LongRunningOperationManager()
        await self.manager.start_background_processor()

        # Initialize migrator
        self.migrator = ExistingOperationMigrator(self.manager)

        logger.info("Long-running operations demo initialized")

    async def shutdown(self):
        """Shutdown the demo"""
        if self.manager:
            await self.manager.stop_background_processor()

    async def demo_codebase_indexing(self):
        """
        Demonstrate codebase indexing with intelligent timeouts

        This shows how a previously problematic operation with a 30-second
        timeout becomes robust with dynamic timeouts, checkpointing, and
        progress tracking.
        """
        print("\n" + "=" * 60)
        print("DEMO: Codebase Indexing with Intelligent Timeouts")
        print("=" * 60)

        print(
            """
        BEFORE (Problematic):
        - Fixed 30-second timeout regardless of codebase size
        - No progress visibility
        - Complete re-indexing required on timeout
        - Work lost on failure

        AFTER (Robust):
        - Dynamic timeout based on estimated file count
        - Real-time progress tracking with file details
        - Checkpoint every 100 files processed
        - Resume from checkpoint on failure/timeout
        """
        )

        # Start enhanced indexing operation
        operation_id = await self.migrator.migrate_knowledge_base_indexing()

        print(f"\nStarted enhanced codebase indexing: {operation_id}")
        print("Monitoring progress...")

        # Monitor operation progress
        await self._monitor_operation(operation_id, "Codebase Indexing")

        return operation_id

    async def demo_comprehensive_testing(self):
        """
        Demonstrate comprehensive test suite with checkpoint/resume

        Shows how test suites that previously had fixed timeouts now
        adapt to the actual number of tests and can resume from
        the last completed test.
        """
        print("\n" + "=" * 60)
        print("DEMO: Comprehensive Test Suite with Checkpoint/Resume")
        print("=" * 60)

        print(
            """
        BEFORE (Problematic):
        - Fixed 10-minute timeout regardless of test count
        - No visibility into which tests are running
        - Complete re-run required on timeout
        - No parallel execution control

        AFTER (Robust):
        - Dynamic timeout based on estimated test count
        - Real-time test progress and results
        - Resume from last completed test
        - Parallel execution with resource management
        """
        )

        # Start enhanced test suite
        operation_id = await self.migrator.migrate_comprehensive_test_suite()

        print(f"\nStarted enhanced test suite: {operation_id}")
        print("Monitoring test progress...")

        # Monitor operation progress
        await self._monitor_operation(operation_id, "Test Suite")

        return operation_id

    async def demo_security_scanning(self):
        """
        Demonstrate security scanning with incremental progress

        Shows how security scans adapt to codebase size and can
        resume from the last scanned file.
        """
        print("\n" + "=" * 60)
        print("DEMO: Security Scanning with Incremental Progress")
        print("=" * 60)

        print(
            """
        BEFORE (Problematic):
        - Fixed 5-minute timeout regardless of codebase size
        - No progress visibility
        - Complete re-scan required on timeout
        - No incremental scanning

        AFTER (Robust):
        - Dynamic timeout based on files to scan
        - Real-time scan progress with vulnerability tracking
        - Resume from last scanned file
        - Incremental scanning with result aggregation
        """
        )

        # Start enhanced security scan
        operation_id = await self.migrator.migrate_security_scan_operation()

        print(f"\nStarted enhanced security scan: {operation_id}")
        print("Monitoring scan progress...")

        # Monitor operation progress
        await self._monitor_operation(operation_id, "Security Scan")

        return operation_id

    async def demo_checkpoint_resume(self):
        """
        Demonstrate checkpoint and resume capabilities

        This shows how operations can be interrupted and resumed
        from the exact point where they left off.
        """
        print("\n" + "=" * 60)
        print("DEMO: Checkpoint and Resume Capabilities")
        print("=" * 60)

        print("Creating a long-running operation that we'll interrupt...")

        # Create a long operation that we can interrupt
        async def interruptible_operation(context):
            """Operation designed to be interrupted and resumed"""

            total_items = 200

            # Check if resuming
            if context.should_resume():
                checkpoint_data = context.get_resume_data()
                start_item = checkpoint_data.processed_items
                processed_data = checkpoint_data.intermediate_results.get(
                    "processed_data", []
                )
                logger.info(f"Resuming from item {start_item}")
            else:
                start_item = 0
                processed_data = []

            for i in range(start_item, total_items):
                # Simulate work
                await asyncio.sleep(0.1)

                processed_data.append(f"item_{i}")

                await context.update_progress(
                    f"Processing item {i}",
                    i + 1,
                    total_items,
                    {"items_per_second": (i + 1) / 10},  # Rough calculation
                    f"Processed {i + 1} of {total_items} items",
                )

                # Save checkpoint every 20 items
                if (i + 1) % 20 == 0:
                    await context.save_checkpoint(
                        {"processed_data": processed_data}, f"item_{i + 1}"
                    )

                # Simulate an interruption at item 50
                if i == 50:
                    logger.info("Simulating interruption at item 50...")
                    raise Exception("Simulated interruption for demo")

            return {"total_processed": len(processed_data), "data": processed_data}

        # Start the operation
        operation_id = await self.manager.create_operation(
            operation_type=OperationType.CODE_ANALYSIS,
            name="Interruptible Demo Operation",
            description="Operation that will be interrupted and resumed",
            operation_function=interruptible_operation,
            priority=OperationPriority.NORMAL,
            estimated_items=200,
            execute_immediately=True,
        )

        print(f"Started interruptible operation: {operation_id}")

        # Wait for it to fail
        while True:
            operation = self.manager.get_operation(operation_id)
            if operation.status in [OperationStatus.FAILED, OperationStatus.COMPLETED]:
                break
            await asyncio.sleep(1)

        if operation.status == OperationStatus.FAILED:
            print(f"Operation failed as expected: {operation.error_info}")

            # Find the latest checkpoint
            checkpoints = await self.manager.checkpoint_manager.list_checkpoints(
                operation_id
            )
            if checkpoints:
                latest_checkpoint = checkpoints[-1]
                print(
                    f"Found checkpoint at {latest_checkpoint.progress_percentage:.1f}% progress"
                )

                # Resume from checkpoint
                print("Resuming operation from checkpoint...")
                new_operation_id = await self.manager.resume_operation(
                    latest_checkpoint.checkpoint_id
                )

                print(f"Resumed as new operation: {new_operation_id}")

                # Monitor the resumed operation
                await self._monitor_operation(new_operation_id, "Resumed Operation")

                return new_operation_id
            else:
                print("No checkpoints found!")
        else:
            print("Operation completed without interruption")

        return operation_id

    async def demo_concurrent_operations(self):
        """
        Demonstrate concurrent operation management

        Shows how the framework manages multiple long-running operations
        concurrently with proper resource control.
        """
        print("\n" + "=" * 60)
        print("DEMO: Concurrent Operation Management")
        print("=" * 60)

        print("Starting multiple operations concurrently...")

        # Start multiple operations
        operations = []

        # Quick indexing operation
        indexing_op = await execute_codebase_indexing(
            "/home/kali/Desktop/AutoBot/src/utils", self.manager, ["*.py"]
        )
        operations.append(("Indexing", indexing_op))

        # Test suite operation
        test_op = await execute_comprehensive_test_suite(
            "/home/kali/Desktop/AutoBot/tests/unit", self.manager, ["test_*.py"]
        )
        operations.append(("Testing", test_op))

        # Simple analysis operation
        async def analysis_operation(context):
            """Run iterative analysis steps with progress tracking."""
            for i in range(50):
                await asyncio.sleep(0.05)
                await context.update_progress(f"Analyzing step {i}", i + 1, 50)
            return {"analysis_complete": True}

        analysis_op = await self.manager.create_operation(
            operation_type=OperationType.CODE_ANALYSIS,
            name="Code Analysis Demo",
            description="Simple analysis operation",
            operation_function=analysis_operation,
            priority=OperationPriority.LOW,
            estimated_items=50,
            execute_immediately=False,
        )
        operations.append(("Analysis", analysis_op))

        print(f"Started {len(operations)} concurrent operations:")
        for name, op_id in operations:
            print(f"  - {name}: {op_id}")

        # Monitor all operations
        print("\nMonitoring concurrent operations...")

        while True:
            all_completed = True
            status_line = []

            for name, op_id in operations:
                operation = self.manager.get_operation(op_id)
                status_line.append(
                    f"{name}: {operation.progress.progress_percentage:.1f}%"
                )

                if operation.status not in [
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                ]:
                    all_completed = False

            print(f"\rProgress - {' | '.join(status_line)}", end="", flush=True)

            if all_completed:
                break

            await asyncio.sleep(2)

        print("\nAll concurrent operations completed!")

        # Show final results
        for name, op_id in operations:
            operation = self.manager.get_operation(op_id)
            print(f"{name}: {operation.status.value}")

        return operations

    async def _monitor_operation(self, operation_id: str, operation_name: str):
        """Monitor operation progress and display updates"""

        last_progress = -1
        start_time = datetime.now()

        while True:
            operation = self.manager.get_operation(operation_id)

            if operation.progress.progress_percentage != last_progress:
                elapsed = (datetime.now() - start_time).total_seconds()

                print(
                    f"\r{operation_name}: {operation.progress.progress_percentage:.1f}% "
                    f"({operation.progress.processed_items}/{operation.progress.total_items}) "
                    f"- {operation.progress.current_step} "
                    f"[{elapsed:.1f}s elapsed]",
                    end="",
                    flush=True,
                )

                last_progress = operation.progress.progress_percentage

            if operation.status in [
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.TIMEOUT,
                OperationStatus.CANCELLED,
            ]:
                break

            await asyncio.sleep(0.5)

        print()  # New line

        elapsed = (datetime.now() - start_time).total_seconds()

        if operation.status == OperationStatus.COMPLETED:
            print(f"✅ {operation_name} completed successfully in {elapsed:.1f}s")
            if operation.result:
                # Show key metrics from result
                result = operation.result
                if isinstance(result, dict):
                    for key, value in result.items():
                        if key in [
                            "total_files_processed",
                            "total_tests",
                            "passed",
                            "failed",
                            "total_vulnerabilities",
                            "success_rate",
                        ]:
                            print(f"   {key}: {value}")
        else:
            print(f"❌ {operation_name} failed: {operation.status.value}")
            if operation.error_info:
                print(f"   Error: {operation.error_info}")

    async def run_demo(self, demo_type: str = "all"):
        """Run the specified demonstration"""

        print("AutoBot Long-Running Operations Framework Demo")
        print("=" * 50)
        print(f"Framework available: {FRAMEWORK_AVAILABLE}")

        if not FRAMEWORK_AVAILABLE:
            print("Framework not available - please check imports")
            return

        await self.initialize()

        try:
            if demo_type in ["all", "indexing"]:
                await self.demo_codebase_indexing()

            if demo_type in ["all", "testing"]:
                await self.demo_comprehensive_testing()

            if demo_type in ["all", "security"]:
                await self.demo_security_scanning()

            if demo_type in ["all", "checkpoint"]:
                await self.demo_checkpoint_resume()

            if demo_type in ["all", "concurrent"]:
                await self.demo_concurrent_operations()

            print("\n" + "=" * 60)
            print("DEMONSTRATION COMPLETE")
            print("=" * 60)
            print(
                """
            Key Benefits Demonstrated:

            1. ✅ INTELLIGENT TIMEOUTS
               - Dynamic timeouts based on operation complexity
               - No more premature timeouts for large operations
               - Operations "either finish or fail" gracefully

            2. ✅ CHECKPOINT/RESUME CAPABILITIES
               - Automatic checkpointing during long operations
               - Resume from exact point of interruption
               - No lost work on failures or timeouts

            3. ✅ REAL-TIME PROGRESS TRACKING
               - Live progress updates with detailed status
               - Performance metrics and time estimates
               - WebSocket support for UI integration

            4. ✅ BACKGROUND OPERATION MANAGEMENT
               - Concurrent operation execution with resource control
               - Priority-based scheduling
               - Proper cleanup and resource management

            5. ✅ OPERATION-SPECIFIC HANDLERS
               - Specialized handling for different operation types
               - Context-aware timeout and checkpoint strategies
               - Easy migration from existing timeout patterns

            The framework transforms unreliable timeout-prone operations
            into robust, resumable, and user-friendly experiences.
            """
            )

        finally:
            await self.shutdown()


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Long-Running Operations Framework Demo"
    )
    parser.add_argument(
        "--demo-type",
        choices=["all", "indexing", "testing", "security", "checkpoint", "concurrent"],
        default="all",
        help="Type of demonstration to run",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    demo = LongRunningOperationsDemo()
    await demo.run_demo(args.demo_type)


if __name__ == "__main__":
    asyncio.run(main())
