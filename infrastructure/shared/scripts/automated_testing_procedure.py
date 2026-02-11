#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Automated Testing Procedure Framework
Implements comprehensive testing across the entire AutoBot codebase
"""

import asyncio
import importlib
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Test result data structure"""

    name: str
    status: str  # PASS, FAIL, SKIP, ERROR
    duration: float
    message: str = ""
    details: Optional[Dict] = None


class AutomatedTestingSuite:
    """Comprehensive automated testing framework"""

    def __init__(self, project_root: str = None):
        """Initialize testing suite with project root and results containers."""
        self.project_root = Path(
            project_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.results = {
            "summary": {},
            "unit_tests": [],
            "integration_tests": [],
            "performance_tests": [],
            "security_tests": [],
            "code_quality_tests": [],
            "api_tests": [],
        }
        # Import configuration from centralized source
        from config import API_BASE_URL

        self.backend_url = API_BASE_URL

    def run_unit_tests(self) -> List[TestResult]:
        """Run Python unit tests"""
        logger.info("Running unit tests...")

        unit_results = []
        test_dirs = ["tests/", "src/", "backend/"]

        for test_dir in test_dirs:
            test_path = self.project_root / test_dir
            if not test_path.exists():
                continue

            logger.info("  Scanning %s for unit tests...", test_dir)

            # Find test files
            test_files = list(test_path.rglob("test_*.py"))
            test_files.extend(list(test_path.rglob("*_test.py")))

            for test_file in test_files:
                result = self._run_single_test_file(test_file)
                unit_results.append(result)

        self.results["unit_tests"] = [r.__dict__ for r in unit_results]
        return unit_results

    def _run_single_test_file(self, test_file: Path) -> TestResult:
        """Run a single test file"""
        start_time = time.time()

        try:
            # Run pytest on the file with non-interactive environment
            env = os.environ.copy()
            env["CI"] = "1"  # Set CI environment variable
            env["PYTEST_CURRENT_TEST"] = str(test_file)

            cmd = [
                sys.executable,
                "-m",
                "pytest",
                str(test_file),
                "-v",
                "--tb=short",
                "--no-header",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                stdin=subprocess.DEVNULL,  # Prevent hanging on input
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                return TestResult(
                    name=f"Unit: {test_file.name}",
                    status="PASS",
                    duration=duration,
                    message="All tests passed",
                )
            else:
                return TestResult(
                    name=f"Unit: {test_file.name}",
                    status="FAIL",
                    duration=duration,
                    message=result.stderr[:200] if result.stderr else "Tests failed",
                )

        except subprocess.TimeoutExpired:
            return TestResult(
                name=f"Unit: {test_file.name}",
                status="ERROR",
                duration=60.0,
                message="Test timeout (>60s)",
            )
        except Exception as e:
            return TestResult(
                name=f"Unit: {test_file.name}",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e),
            )

    def run_integration_tests(self) -> List[TestResult]:
        """Run integration tests"""
        logger.info("🔗 Running integration tests...")

        integration_results = []

        # Test 1: Backend startup
        result = self._test_backend_startup()
        integration_results.append(result)

        # Test 2: Database connections
        result = self._test_database_connections()
        integration_results.append(result)

        # Test 3: Module imports
        result = self._test_module_imports()
        integration_results.append(result)

        # Test 4: Configuration loading
        result = self._test_configuration_loading()
        integration_results.append(result)

        self.results["integration_tests"] = [r.__dict__ for r in integration_results]
        return integration_results

    def _test_backend_startup(self) -> TestResult:
        """Test backend can start successfully"""
        start_time = time.time()

        try:
            from backend.app_factory import create_app

            create_app()

            duration = time.time() - start_time
            return TestResult(
                name="Integration: Backend Startup",
                status="PASS",
                duration=duration,
                message="Backend started successfully",
            )

        except Exception as e:
            return TestResult(
                name="Integration: Backend Startup",
                status="FAIL",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    def _test_database_connections(self) -> TestResult:
        """Test database connections"""
        start_time = time.time()

        try:
            # Test SQLite connections
            import sqlite3

            db_files = [
                "data/knowledge_base.db",
                "data/memory_system.db",
                "data/project_state.db",
            ]

            connection_count = 0
            for db_file in db_files:
                if os.path.exists(db_file):
                    conn = sqlite3.connect(db_file)
                    conn.execute("SELECT 1")
                    conn.close()
                    connection_count += 1

            duration = time.time() - start_time
            return TestResult(
                name="Integration: Database Connections",
                status="PASS",
                duration=duration,
                message=f"Connected to {connection_count} databases",
            )

        except Exception as e:
            return TestResult(
                name="Integration: Database Connections",
                status="FAIL",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    def _test_module_imports(self) -> TestResult:
        """Test critical module imports"""
        start_time = time.time()

        critical_modules = [
            "src.orchestrator",
            "src.llm_interface",
            "src.knowledge_base",
            "backend.app_factory",
            "src.config",
        ]

        import_failures = []

        for module in critical_modules:
            try:
                importlib.import_module(module)
            except Exception as e:
                import_failures.append(f"{module}: {str(e)[:50]}")

        duration = time.time() - start_time

        if not import_failures:
            return TestResult(
                name="Integration: Module Imports",
                status="PASS",
                duration=duration,
                message=f"All {len(critical_modules)} critical modules imported",
            )
        else:
            return TestResult(
                name="Integration: Module Imports",
                status="FAIL",
                duration=duration,
                message=f"Failed imports: {'; '.join(import_failures)}",
            )

    def _test_configuration_loading(self) -> TestResult:
        """Test configuration loading"""
        start_time = time.time()

        try:
            from config import global_config_manager

            # Test basic config access
            global_config_manager.get("backend", {})
            global_config_manager.get("memory", {})

            duration = time.time() - start_time
            return TestResult(
                name="Integration: Configuration Loading",
                status="PASS",
                duration=duration,
                message="Configuration loaded successfully",
            )

        except Exception as e:
            return TestResult(
                name="Integration: Configuration Loading",
                status="FAIL",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    async def run_api_tests(self) -> List[TestResult]:
        """Run API endpoint tests"""
        logger.info("🌐 Running API tests...")

        api_results = []

        # Critical API endpoints to test
        endpoints = [
            ("/api/system/health", "Health Check"),
            ("/api/project/status", "Project Status"),
            ("/api/system/status", "System Status"),
            ("/api/system/models", "Available Models"),
            ("/api/llm/status", "LLM Status"),
            ("/api/redis/status", "Redis Status"),
        ]

        for endpoint, description in endpoints:
            result = await self._test_api_endpoint(endpoint, description)
            api_results.append(result)

        self.results["api_tests"] = [r.__dict__ for r in api_results]
        return api_results

    async def _test_api_endpoint(self, endpoint: str, description: str) -> TestResult:
        """Test a single API endpoint (Issue #359: use async HTTP)"""
        start_time = time.time()

        try:
            url = f"{self.backend_url}{endpoint}"
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    await response.text()  # Consume response
                    duration = time.time() - start_time

                    if response.status == 200:
                        return TestResult(
                            name=f"API: {description}",
                            status="PASS",
                            duration=duration,
                            message=f"HTTP 200 ({duration*1000:.0f}ms)",
                        )
                    else:
                        return TestResult(
                            name=f"API: {description}",
                            status="FAIL",
                            duration=duration,
                            message=f"HTTP {response.status}",
                        )

        except aiohttp.ClientConnectorError:
            return TestResult(
                name=f"API: {description}",
                status="SKIP",
                duration=time.time() - start_time,
                message="Backend not running",
            )
        except Exception as e:
            return TestResult(
                name=f"API: {description}",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e)[:100],
            )

    def run_performance_tests(self) -> List[TestResult]:
        """Run performance tests"""
        logger.info("⚡ Running performance tests...")

        perf_results = []

        # Test 1: Import speed
        result = self._test_import_performance()
        perf_results.append(result)

        # Test 2: Configuration loading speed
        result = self._test_config_performance()
        perf_results.append(result)

        self.results["performance_tests"] = [r.__dict__ for r in perf_results]
        return perf_results

    def _test_import_performance(self) -> TestResult:
        """Test module import performance"""
        start_time = time.time()

        try:
            # Import heavy modules and measure time
            heavy_modules = ["src.orchestrator", "backend.app_factory"]

            import_times = {}
            for module in heavy_modules:
                module_start = time.time()
                importlib.import_module(module)
                import_times[module] = time.time() - module_start

            total_duration = time.time() - start_time
            max_import = max(import_times.values())

            status = "PASS" if max_import < 5.0 else "FAIL"

            return TestResult(
                name="Performance: Import Speed",
                status=status,
                duration=total_duration,
                message=f"Max import time: {max_import:.2f}s",
                details=import_times,
            )

        except Exception as e:
            return TestResult(
                name="Performance: Import Speed",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    def _test_config_performance(self) -> TestResult:
        """Test configuration loading performance"""
        start_time = time.time()

        try:
            from config import global_config_manager

            # Measure config access time
            for _ in range(100):
                global_config_manager.get("backend", {})
                global_config_manager.get("memory", {})
                global_config_manager.get("llm_config", {})

            duration = time.time() - start_time
            avg_time = duration / 100

            status = "PASS" if avg_time < 0.01 else "FAIL"

            return TestResult(
                name="Performance: Config Access",
                status=status,
                duration=duration,
                message=f"Average access time: {avg_time*1000:.2f}ms",
            )

        except Exception as e:
            return TestResult(
                name="Performance: Config Access",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    def run_security_tests(self) -> List[TestResult]:
        """Run security tests"""
        logger.info("🔒 Running security tests...")

        security_results = []

        # Test 1: Command validator
        result = self._test_command_validator()
        security_results.append(result)

        # Test 2: File upload security
        result = self._test_file_upload_security()
        security_results.append(result)

        self.results["security_tests"] = [r.__dict__ for r in security_results]
        return security_results

    def _test_command_validator(self) -> TestResult:
        """Test command validation security"""
        start_time = time.time()

        try:
            from security.command_validator import get_command_validator

            validator = get_command_validator()

            # Test safe command
            safe_result = validator.validate_command_request(
                "show me system information"
            )

            # Test dangerous command
            danger_result = validator.validate_command_request("run rm -rf /")

            duration = time.time() - start_time

            # Check if safe command passes and dangerous command is blocked
            safe_passes = safe_result and safe_result.get("type") == "system_info"
            danger_blocked = danger_result and danger_result.get("type") == "blocked"

            if safe_passes and danger_blocked:
                return TestResult(
                    name="Security: Command Validator",
                    status="PASS",
                    duration=duration,
                    message="Safe commands allowed, dangerous commands blocked",
                )
            else:
                return TestResult(
                    name="Security: Command Validator",
                    status="FAIL",
                    duration=duration,
                    message=f"Safe: {safe_passes}, Blocked: {danger_blocked}",
                )

        except Exception as e:
            return TestResult(
                name="Security: Command Validator",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    def _test_file_upload_security(self) -> TestResult:
        """Test file upload security validation"""
        start_time = time.time()

        try:
            # Test if file upload validation exists
            from backend.api.files import is_safe_file

            # Test safe files
            safe_files = ["document.pd", "image.jpg", "text.txt"]

            # Test dangerous files
            dangerous_files = ["script.exe", "virus.bat", "../../../etc/passwd"]

            safe_results = [is_safe_file(f) for f in safe_files]
            danger_results = [is_safe_file(f) for f in dangerous_files]

            duration = time.time() - start_time

            safe_pass = all(safe_results)
            danger_blocked = not any(danger_results)

            if safe_pass and danger_blocked:
                return TestResult(
                    name="Security: File Upload Validation",
                    status="PASS",
                    duration=duration,
                    message="Safe files allowed, dangerous files blocked",
                )
            else:
                return TestResult(
                    name="Security: File Upload Validation",
                    status="FAIL",
                    duration=duration,
                    message=f"Safe: {safe_pass}, Blocked: {danger_blocked}",
                )

        except Exception as e:
            return TestResult(
                name="Security: File Upload Validation",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    def run_code_quality_tests(self) -> List[TestResult]:
        """Run code quality tests"""
        logger.info("✨ Running code quality tests...")

        quality_results = []

        # Test 1: Flake8 linting
        result = self._test_flake8_compliance()
        quality_results.append(result)

        # Test 2: Import structure
        result = self._test_import_structure()
        quality_results.append(result)

        self.results["code_quality_tests"] = [r.__dict__ for r in quality_results]
        return quality_results

    def _test_flake8_compliance(self) -> TestResult:
        """Test flake8 linting compliance"""
        start_time = time.time()

        try:
            cmd = [
                "flake8",
                "src/",
                "backend/",
                "--max-line-length=88",
                "--extend-ignore=E203,W503",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            duration = time.time() - start_time

            if result.returncode == 0:
                return TestResult(
                    name="Quality: Flake8 Compliance",
                    status="PASS",
                    duration=duration,
                    message="No linting errors found",
                )
            else:
                error_count = (
                    len(result.stdout.strip().split("\n"))
                    if result.stdout.strip()
                    else 0
                )
                return TestResult(
                    name="Quality: Flake8 Compliance",
                    status="FAIL",
                    duration=duration,
                    message=f"{error_count} linting errors found",
                )

        except Exception as e:
            return TestResult(
                name="Quality: Flake8 Compliance",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    def _test_import_structure(self) -> TestResult:
        """Test import structure and dependencies"""
        start_time = time.time()

        try:
            # Check for circular imports by trying to import all modules
            modules_to_check = [
                "src.orchestrator",
                "src.llm_interface",
                "src.knowledge_base",
                "backend.app_factory",
            ]

            import_failures = []
            for module in modules_to_check:
                try:
                    importlib.import_module(module)
                except ImportError as e:
                    import_failures.append(f"{module}: {str(e)}")

            duration = time.time() - start_time

            if not import_failures:
                return TestResult(
                    name="Quality: Import Structure",
                    status="PASS",
                    duration=duration,
                    message="No circular imports detected",
                )
            else:
                return TestResult(
                    name="Quality: Import Structure",
                    status="FAIL",
                    duration=duration,
                    message=f"Import issues: {len(import_failures)}",
                )

        except Exception as e:
            return TestResult(
                name="Quality: Import Structure",
                status="ERROR",
                duration=time.time() - start_time,
                message=str(e)[:200],
            )

    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run all test suites"""
        logger.info("🚀 Starting comprehensive testing procedure...")
        logger.info("=" * 60)

        start_time = time.time()

        # Run all test suites
        unit_results = self.run_unit_tests()
        integration_results = self.run_integration_tests()
        api_results = await self.run_api_tests()
        performance_results = self.run_performance_tests()
        security_results = self.run_security_tests()
        quality_results = self.run_code_quality_tests()

        total_duration = time.time() - start_time

        # Compile summary
        all_results = (
            unit_results
            + integration_results
            + api_results
            + performance_results
            + security_results
            + quality_results
        )

        summary = {
            "total_tests": len(all_results),
            "passed": len([r for r in all_results if r.status == "PASS"]),
            "failed": len([r for r in all_results if r.status == "FAIL"]),
            "errors": len([r for r in all_results if r.status == "ERROR"]),
            "skipped": len([r for r in all_results if r.status == "SKIP"]),
            "total_duration": total_duration,
        }

        self.results["summary"] = summary

        logger.info("\n" + "=" * 60)
        logger.info("📊 TESTING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total tests: {summary['total_tests']}")
        logger.info(f"✅ Passed: {summary['passed']}")
        logger.error(f"❌ Failed: {summary['failed']}")
        logger.error(f"🔥 Errors: {summary['errors']}")
        logger.info(f"⏭️  Skipped: {summary['skipped']}")
        logger.info(f"⏱️  Duration: {summary['total_duration']:.2f}s")

        success_rate = (
            (summary["passed"] / summary["total_tests"]) * 100
            if summary["total_tests"] > 0
            else 0
        )
        logger.info(f"📈 Success rate: {success_rate:.1f}%")

        return self.results

    def save_results(self, output_file: str = None):
        """Save test results to file"""
        if output_file is None:
            output_file = f"reports/test_results_{int(time.time())}.json"

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        logger.info(f"\n📁 Test results saved to: {output_file}")


async def main():
    """Main testing execution"""
    tester = AutomatedTestingSuite()
    results = await tester.run_comprehensive_tests()

    # Save results
    tester.save_results()

    # Print failed tests details
    failed_tests = []
    for category in [
        "unit_tests",
        "integration_tests",
        "api_tests",
        "performance_tests",
        "security_tests",
        "code_quality_tests",
    ]:
        for test in results.get(category, []):
            if test["status"] in ["FAIL", "ERROR"]:
                failed_tests.append(test)

    if failed_tests:
        logger.info("\n" + "=" * 60)
        logger.error("❌ FAILED TESTS DETAILS")
        logger.info("=" * 60)
        for test in failed_tests[:10]:  # Show first 10 failures
            logger.info(f"• {test['name']}: {test['message']}")


if __name__ == "__main__":
    asyncio.run(main())
