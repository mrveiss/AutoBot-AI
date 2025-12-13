#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# Converted to logger.info() for pre-commit compliance
"""
AutoBot Monitoring Dashboard
Provides quick status overview and health metrics for the codebase
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class AutoBotMonitor:
    """Monitoring dashboard for AutoBot system health"""

    def __init__(self):
        """Initialize monitoring dashboard with project root path."""
        self.project_root = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def get_system_overview(self):
        """Get high-level system status"""
        logger.info("AUTOBOT SYSTEM MONITORING DASHBOARD")
        logger.info("=" * 60)
        logger.info("Generated: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        logger.info("Project Root: %s", self.project_root)

    def check_recent_analysis(self):
        """Check for recent profiling analysis"""
        logger.info("RECENT ANALYSIS STATUS")
        logger.info("-" * 30)

        analysis_files = list(self.project_root.glob("reports/codebase_analysis_*.json"))

        if analysis_files:
            latest_analysis = max(analysis_files, key=os.path.getctime)
            age = datetime.now() - datetime.fromtimestamp(os.path.getctime(latest_analysis))

            if age < timedelta(days=1):
                status = "FRESH"
            elif age < timedelta(days=7):
                status = "RECENT"
            else:
                status = "STALE"

            logger.info("Latest Analysis: %s", latest_analysis.name)
            logger.info("Age: %d days, %d hours", age.days, age.seconds // 3600)
            logger.info("Status: %s", status)

            # Load and display key metrics
            try:
                with open(latest_analysis, encoding='utf-8') as f:
                    data = json.load(f)

                static = data.get("static_analysis", {})
                hotspots = data.get("performance_hotspots", {})

                logger.info("Functions Analyzed: %d", len(static.get('function_definitions', {})))
                logger.info("High Complexity: %d", len(hotspots.get('high_complexity_functions', [])))
                logger.info("Duplicates: %d", len(hotspots.get('duplicate_code', [])))
                logger.info("Recommendations: %d", len(data.get('recommendations', [])))

            except Exception as e:
                logger.error("Could not read analysis data: %s", e)
        else:
            logger.warning("No analysis files found")
            logger.info("Run: python scripts/comprehensive_code_profiler.py")

    def check_api_performance(self):
        """Quick API performance check"""
        logger.info("API PERFORMANCE STATUS")
        logger.info("-" * 30)

        try:
            result = subprocess.run([
                sys.executable, "scripts/profile_api_endpoints.py"
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                # Parse results for quick summary
                lines = result.stdout.split('\n')
                fast_endpoints = len([line for line in lines if 'FAST' in line])
                good_endpoints = len([line for line in lines if 'GOOD' in line])
                slow_endpoints = len([line for line in lines if 'SLOW' in line or 'VERY SLOW' in line])

                logger.info("Fast Endpoints: %d", fast_endpoints)
                logger.info("Good Endpoints: %d", good_endpoints)
                logger.info("Slow Endpoints: %d", slow_endpoints)

                if slow_endpoints > 0:
                    logger.warning("Some endpoints need optimization")
                else:
                    logger.info("All endpoints performing well")
            else:
                logger.warning("Backend not running - cannot test APIs")

        except subprocess.TimeoutExpired:
            logger.warning("API test timeout - backend may be slow")
        except Exception as e:
            logger.error("API test error: %s", e)

    def check_security_status(self):
        """Check security systems status"""
        logger.info("SECURITY STATUS")
        logger.info("-" * 30)

        security_checks = [
            ("Command Validator", "src/security/command_validator.py"),
            ("Allowed Commands Config", "config/allowed_commands.json"),
            ("File Upload Security", "backend/api/files.py"),
        ]

        all_secure = True
        for name, path in security_checks:
            if Path(path).exists():
                logger.info("%s: Present", name)
            else:
                logger.warning("%s: Missing", name)
                all_secure = False

        # Test command validator if available
        try:
            from src.security.command_validator import get_command_validator
            validator = get_command_validator()

            # Quick functionality test
            safe_test = validator.validate_command_request("show system info")
            danger_test = validator.validate_command_request("run rm -rf /")

            if (safe_test and safe_test.get("type") == "system_info"
                    and danger_test and danger_test.get("type") == "blocked"):
                logger.info("Command Validator: Functional")
            else:
                logger.warning("Command Validator: Issues detected")
                all_secure = False

        except Exception as e:
            logger.warning("Command Validator: Cannot test (%s)", e)

        if all_secure:
            logger.info("Overall Security: GOOD")
        else:
            logger.warning("Overall Security: NEEDS ATTENTION")

    def check_testing_capabilities(self):
        """Check testing infrastructure status"""
        logger.info("TESTING INFRASTRUCTURE")
        logger.info("-" * 30)

        test_scripts = [
            ("Codebase Profiler", "scripts/comprehensive_code_profiler.py"),
            ("Automated Testing", "scripts/automated_testing_procedure.py"),
            ("API Performance", "scripts/profile_api_endpoints.py"),
            ("Backend Profiler", "scripts/profile_backend.py"),
        ]

        available_tests = 0
        for name, path in test_scripts:
            if Path(path).exists():
                logger.info("%s: Available", name)
                available_tests += 1
            else:
                logger.warning("%s: Missing", name)

        coverage_pct = available_tests / len(test_scripts) * 100
        logger.info("Test Coverage: %d/%d (%.0f%%)", available_tests, len(test_scripts), coverage_pct)

        if available_tests == len(test_scripts):
            logger.info("Testing Infrastructure: COMPLETE")
        else:
            logger.warning("Testing Infrastructure: INCOMPLETE")

    def provide_recommendations(self):
        """Provide actionable recommendations"""
        logger.info("RECOMMENDATIONS")
        logger.info("-" * 30)

        # Check if analysis is recent
        analysis_files = list(self.project_root.glob("reports/codebase_analysis_*.json"))
        if not analysis_files:
            logger.info("Run codebase profiling: python scripts/comprehensive_code_profiler.py")
        else:
            latest = max(analysis_files, key=os.path.getctime)
            age = datetime.now() - datetime.fromtimestamp(os.path.getctime(latest))
            if age > timedelta(days=7):
                logger.info("Update profiling analysis (>7 days old)")

        # Check for common issues
        try:
            # Check if backend is running
            result = subprocess.run([
                "curl", "-s", "ServiceURLs.BACKEND_LOCAL/api/system/health"
            ], capture_output=True, timeout=5)

            if result.returncode != 0:
                logger.info("Start backend for full monitoring: ./run_agent.sh --test-mode")
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            logger.info("Start backend for API testing: ./run_agent.sh --test-mode")

        # Check for required tools
        tools = ["flake8", "pytest"]
        for tool in tools:
            try:
                subprocess.run([tool, "--version"], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.info("Install %s: pip install %s", tool, tool)

        logger.info("Regular maintenance: Run weekly profiling and testing")
        logger.info("Focus areas: Check optimization_roadmap.md for priorities")

    def run_dashboard(self):
        """Run complete monitoring dashboard"""
        self.get_system_overview()
        self.check_recent_analysis()
        self.check_api_performance()
        self.check_security_status()
        self.check_testing_capabilities()
        self.provide_recommendations()

        logger.info("MONITORING COMPLETE")
        logger.info("=" * 60)
        logger.info("For detailed analysis, run:")
        logger.info("  python scripts/comprehensive_code_profiler.py")
        logger.info("  python scripts/automated_testing_procedure.py")
        logger.info("  python scripts/profile_api_endpoints.py")


def main():
    """Main monitoring execution"""
    monitor = AutoBotMonitor()
    monitor.run_dashboard()


if __name__ == "__main__":
    main()
