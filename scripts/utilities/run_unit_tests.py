#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Run unit tests for the security modules and generate a summary report
"""

import subprocess
import sys
import os
from pathlib import Path


def _parse_pytest_output(output: str) -> dict:
    """
    Parse pytest output to extract pass/fail counts.

    Issue #281: Extracted from run_tests to reduce function length.

    Args:
        output: Pytest stdout output.

    Returns:
        Dictionary with 'passed', 'failed', and 'status' keys.
    """
    output_lines = output.split('\n')
    summary_line = [line for line in output_lines if 'passed' in line and 'failed' in line]

    if summary_line:
        summary = summary_line[0]
        passed = 0
        failed = 0

        if " passed" in summary:
            passed_part = summary.split(" passed")[0]
            if " " in passed_part:
                passed = int(passed_part.split()[-1])
            else:
                passed = int(passed_part)

        if " failed" in summary:
            failed_part = summary.split(" failed")[0]
            if " " in failed_part:
                failed = int(failed_part.split()[-1])
            else:
                failed = int(failed_part)

        return {
            "passed": passed,
            "failed": failed,
            "status": "✅" if failed == 0 else "❌"
        }

    # Try to count from verbose output
    passed_count = len([line for line in output_lines if "PASSED" in line])
    failed_count = len([line for line in output_lines if "FAILED" in line])

    if passed_count > 0 or failed_count > 0:
        return {
            "passed": passed_count,
            "failed": failed_count,
            "status": "✅" if failed_count == 0 else "❌"
        }

    return {
        "passed": 0,
        "failed": 0,
        "status": "⚠️ ",
        "error": "No tests found or parsing failed"
    }


def _print_test_summary(results: dict, test_files: list, total_tests: int,
                        total_passed: int, total_failed: int) -> None:
    """
    Print test execution summary.

    Issue #281: Extracted from run_tests to reduce function length.
    """
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)

    for test_file, result in results.items():
        status = result["status"]
        if "passed" in result and "failed" in result:
            print(f"{status} {os.path.basename(test_file):40} {result['passed']} passed, {result['failed']} failed")
        else:
            error = result.get("error", "Unknown issue")
            print(f"{status} {os.path.basename(test_file):40} {error}")

    print("\n" + "-" * 60)

    if total_tests > 0:
        success_rate = (total_passed / total_tests) * 100
        print(f"📈 Overall Results: {total_passed}/{total_tests} tests passed ({success_rate:.1f}%)")

        if total_failed == 0:
            print("🎉 All tests passed! Security implementation is solid.")
        else:
            print(f"⚠️  {total_failed} tests need attention.")
    else:
        print("⚠️  No test results to analyze.")

    print("\n💡 To run individual test files:")
    for test_file in test_files:
        print(f"   python -m pytest {test_file} -v")


def run_tests():
    """
    Run unit tests and generate summary.

    Issue #281: Extracted result parsing to _parse_pytest_output() and
    summary printing to _print_test_summary() to reduce function length
    from 137 to ~55 lines.
    """
    print("🧪 Running Unit Tests for Security Modules")
    print("=" * 60)

    # Test files to run
    test_files = [
        "tests/test_secure_command_executor.py",
        "tests/test_enhanced_security_layer.py",
        "tests/test_security_api.py",
        "tests/test_secure_terminal_websocket.py"
    ]

    results = {}
    total_tests = 0
    total_passed = 0
    total_failed = 0

    for test_file in test_files:
        if not Path(test_file).exists():
            print(f"⚠️  Test file not found: {test_file}")
            continue

        print(f"\n📋 Running {test_file}...")

        try:
            # Run pytest for this file
            result = subprocess.run([
                sys.executable, "-m", "pytest", test_file,
                "-v", "--tb=short", "-q"
            ], capture_output=True, text=True, timeout=60)

            # Issue #281: Use extracted helper for parsing
            parsed = _parse_pytest_output(result.stdout)
            results[test_file] = parsed

            passed = parsed.get("passed", 0)
            failed = parsed.get("failed", 0)
            total_tests += passed + failed
            total_passed += passed
            total_failed += failed

            if "error" in parsed:
                print("   ⚠️  Could not parse test results")
            else:
                print(f"   {parsed['status']} {passed} passed, {failed} failed")

            if result.returncode != 0 and failed == 0:
                print(f"   ⚠️  Test execution had issues (return code: {result.returncode})")
                if result.stderr:
                    print(f"   Error: {result.stderr[:200]}...")

        except subprocess.TimeoutExpired:
            print("   ⏰ Test timed out")
            results[test_file] = {"status": "⏰", "error": "Timeout"}
        except Exception as e:
            print(f"   ❌ Test execution failed: {e}")
            results[test_file] = {"status": "❌", "error": str(e)}

    # Issue #281: Use extracted helper for summary
    _print_test_summary(results, test_files, total_tests, total_passed, total_failed)

    return total_failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
