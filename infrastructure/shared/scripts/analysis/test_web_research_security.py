#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script for AutoBot Web Research Security Components

Tests the comprehensive security implementation including:
- Domain security validation
- Input validation and sanitization
- Secure web research integration
- Configuration loading and validation

Run this script to verify security components work correctly before enabling
web research in production.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from security.domain_security import DomainSecurityConfig, DomainSecurityManager
from security.input_validator import WebResearchInputValidator
from security.secure_web_research import SecureWebResearch

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WebResearchSecurityTester:
    """Comprehensive security testing for web research components"""

    def __init__(self):
        self.test_results = {
            "overall_status": "unknown",
            "tests_passed": 0,
            "tests_failed": 0,
            "test_details": {},
            "timestamp": time.time(),
        }

    async def run_all_tests(self) -> dict:
        """Run all security tests"""
        logger.info("Starting comprehensive web research security tests")

        try:
            # Test 1: Domain Security Manager
            await self._test_domain_security()

            # Test 2: Input Validator
            await self._test_input_validator()

            # Test 3: Secure Web Research Integration
            await self._test_secure_web_research()

            # Test 4: Configuration Loading
            await self._test_configuration()

            # Test 5: Malicious Input Detection
            await self._test_malicious_detection()

            # Test 6: Performance Tests
            await self._test_performance()

            # Determine overall status
            if self.test_results["tests_failed"] == 0:
                self.test_results["overall_status"] = "PASSED"
            elif self.test_results["tests_passed"] > self.test_results["tests_failed"]:
                self.test_results["overall_status"] = "MOSTLY_PASSED"
            else:
                self.test_results["overall_status"] = "FAILED"

            return self.test_results

        except Exception as e:
            logger.error(f"Critical error during testing: {e}")
            self.test_results["overall_status"] = "ERROR"
            self.test_results["error"] = str(e)
            return self.test_results

    async def _test_domain_security(self):
        """Test domain security validation"""
        test_name = "domain_security"
        logger.info("Testing domain security manager")

        test_details = {"passed": 0, "failed": 0, "subtests": {}}

        try:
            # Initialize domain security with test config
            config = DomainSecurityConfig()
            async with DomainSecurityManager(config) as domain_manager:
                # Test 1: Safe domain (should pass)
                safe_result = await domain_manager.validate_domain_safety(
                    "https://github.com/example/repo"
                )
                if safe_result["safe"]:
                    test_details["subtests"]["safe_domain"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "safe_domain"
                    ] = f"FAILED - {safe_result['reason']}"
                    test_details["failed"] += 1

                # Test 2: Malicious domain pattern (should block)
                malicious_result = await domain_manager.validate_domain_safety(
                    "https://malware.com/payload"
                )
                if not malicious_result["safe"]:
                    test_details["subtests"]["malicious_domain"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "malicious_domain"
                    ] = "FAILED - Did not block malicious domain"
                    test_details["failed"] += 1

                # Test 3: Private IP blocking
                private_result = await domain_manager.validate_domain_safety(
                    "http://192.168.1.1/admin"
                )
                if not private_result["safe"]:
                    test_details["subtests"]["private_ip_blocking"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "private_ip_blocking"
                    ] = "FAILED - Did not block private IP"
                    test_details["failed"] += 1

                # Test 4: Invalid URL handling
                invalid_result = await domain_manager.validate_domain_safety(
                    "not-a-url"
                )
                if not invalid_result["safe"]:
                    test_details["subtests"]["invalid_url"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "invalid_url"
                    ] = "FAILED - Did not reject invalid URL"
                    test_details["failed"] += 1

                # Test 5: Statistics retrieval
                stats = domain_manager.get_security_stats()
                if isinstance(stats, dict) and "cache_entries" in stats:
                    test_details["subtests"]["statistics"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "statistics"
                    ] = "FAILED - Invalid statistics format"
                    test_details["failed"] += 1

            # Update overall test results
            if test_details["failed"] == 0:
                self.test_results["tests_passed"] += 1
                test_details["status"] = "PASSED"
            else:
                self.test_results["tests_failed"] += 1
                test_details["status"] = "FAILED"

        except Exception as e:
            logger.error(f"Domain security test error: {e}")
            test_details["status"] = "ERROR"
            test_details["error"] = str(e)
            self.test_results["tests_failed"] += 1

        self.test_results["test_details"][test_name] = test_details

    async def _test_input_validator(self):
        """Test input validation and sanitization"""
        test_name = "input_validator"
        logger.info("Testing input validator")

        test_details = {"passed": 0, "failed": 0, "subtests": {}}

        try:
            validator = WebResearchInputValidator()

            # Test 1: Safe query (should pass)
            safe_query = "How to secure Python applications"
            safe_result = validator.validate_research_query(safe_query)
            if safe_result["safe"] and safe_result["risk_level"] == "low":
                test_details["subtests"]["safe_query"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "safe_query"
                ] = f"FAILED - {safe_result.get('threats_detected', [])}"
                test_details["failed"] += 1

            # Test 2: Script injection (should block)
            malicious_query = "<script>alert('xss')</script> how to hack"
            malicious_result = validator.validate_research_query(malicious_query)
            if not malicious_result["safe"]:
                test_details["subtests"]["script_injection"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "script_injection"
                ] = "FAILED - Did not detect script injection"
                test_details["failed"] += 1

            # Test 3: SQL injection patterns (should block)
            sql_query = "'; DROP TABLE users; --"
            sql_result = validator.validate_research_query(sql_query)
            if not sql_result["safe"]:
                test_details["subtests"]["sql_injection"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "sql_injection"
                ] = "FAILED - Did not detect SQL injection"
                test_details["failed"] += 1

            # Test 4: Suspicious keywords (should warn)
            suspicious_query = "how to exploit buffer overflow vulnerability"
            suspicious_result = validator.validate_research_query(suspicious_query)
            if not suspicious_result["safe"] or suspicious_result["risk_level"] in [
                "medium",
                "high",
            ]:
                test_details["subtests"]["suspicious_keywords"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "suspicious_keywords"
                ] = "FAILED - Did not detect suspicious keywords"
                test_details["failed"] += 1

            # Test 5: URL validation
            valid_url = "https://github.com/example/repo"
            url_result = validator.validate_url(valid_url)
            if url_result["safe"]:
                test_details["subtests"]["url_validation"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "url_validation"
                ] = f"FAILED - {url_result.get('threats_detected', [])}"
                test_details["failed"] += 1

            # Test 6: Content sanitization
            malicious_content = '<script>alert("xss")</script><p>Normal content</p>'
            content_result = validator.sanitize_web_content(malicious_content)
            if "script" not in content_result["sanitized_content"].lower():
                test_details["subtests"]["content_sanitization"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "content_sanitization"
                ] = "FAILED - Did not sanitize malicious content"
                test_details["failed"] += 1

            # Update overall test results
            if test_details["failed"] == 0:
                self.test_results["tests_passed"] += 1
                test_details["status"] = "PASSED"
            else:
                self.test_results["tests_failed"] += 1
                test_details["status"] = "FAILED"

        except Exception as e:
            logger.error(f"Input validator test error: {e}")
            test_details["status"] = "ERROR"
            test_details["error"] = str(e)
            self.test_results["tests_failed"] += 1

        self.test_results["test_details"][test_name] = test_details

    async def _test_secure_web_research(self):
        """Test secure web research integration"""
        test_name = "secure_web_research"
        logger.info("Testing secure web research integration")

        test_details = {"passed": 0, "failed": 0, "subtests": {}}

        try:
            async with SecureWebResearch() as secure_research:
                # Test 1: Query validation
                test_query = "Python web security best practices"
                query_result = await secure_research.validate_research_query(test_query)
                if query_result["safe"]:
                    test_details["subtests"]["query_validation"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "query_validation"
                    ] = f"FAILED - {query_result.get('threats_detected', [])}"
                    test_details["failed"] += 1

                # Test 2: Domain safety check
                test_url = "https://github.com"
                domain_result = await secure_research.check_domain_safety(test_url)
                if domain_result["safe"]:
                    test_details["subtests"]["domain_safety"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "domain_safety"
                    ] = f"FAILED - {domain_result.get('reason', 'unknown')}"
                    test_details["failed"] += 1

                # Test 3: Security statistics
                stats = secure_research.get_security_statistics()
                if isinstance(stats, dict) and "security_stats" in stats:
                    test_details["subtests"]["statistics"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "statistics"
                    ] = "FAILED - Invalid statistics format"
                    test_details["failed"] += 1

                # Test 4: Security component testing
                component_test = await secure_research.test_security_components()
                if component_test["overall_status"] == "passed":
                    test_details["subtests"]["component_tests"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "component_tests"
                    ] = f"FAILED - {component_test.get('overall_status', 'unknown')}"
                    test_details["failed"] += 1

            # Update overall test results
            if test_details["failed"] == 0:
                self.test_results["tests_passed"] += 1
                test_details["status"] = "PASSED"
            else:
                self.test_results["tests_failed"] += 1
                test_details["status"] = "FAILED"

        except Exception as e:
            logger.error(f"Secure web research test error: {e}")
            test_details["status"] = "ERROR"
            test_details["error"] = str(e)
            self.test_results["tests_failed"] += 1

        self.test_results["test_details"][test_name] = test_details

    async def _test_configuration(self):
        """Test configuration loading and validation"""
        test_name = "configuration"
        logger.info("Testing configuration loading")

        test_details = {"passed": 0, "failed": 0, "subtests": {}}

        try:
            # Test 1: Domain security config loading
            config = DomainSecurityConfig()
            if config.config and "domain_security" in config.config:
                test_details["subtests"]["domain_config"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "domain_config"
                ] = "FAILED - Could not load domain security config"
                test_details["failed"] += 1

            # Test 2: Settings validation
            settings_file = Path("config/settings.json")
            if settings_file.exists():
                with open(settings_file) as f:
                    settings = json.load(f)

                if settings.get("web_research", {}).get("enabled"):
                    test_details["subtests"]["web_research_enabled"] = "PASSED"
                    test_details["passed"] += 1
                else:
                    test_details["subtests"][
                        "web_research_enabled"
                    ] = "FAILED - Web research not enabled in settings"
                    test_details["failed"] += 1
            else:
                test_details["subtests"][
                    "web_research_enabled"
                ] = "FAILED - Settings file not found"
                test_details["failed"] += 1

            # Update overall test results
            if test_details["failed"] == 0:
                self.test_results["tests_passed"] += 1
                test_details["status"] = "PASSED"
            else:
                self.test_results["tests_failed"] += 1
                test_details["status"] = "FAILED"

        except Exception as e:
            logger.error(f"Configuration test error: {e}")
            test_details["status"] = "ERROR"
            test_details["error"] = str(e)
            self.test_results["tests_failed"] += 1

        self.test_results["test_details"][test_name] = test_details

    async def _test_malicious_detection(self):
        """Test detection of various malicious inputs"""
        test_name = "malicious_detection"
        logger.info("Testing malicious input detection")

        test_details = {"passed": 0, "failed": 0, "subtests": {}}

        try:
            validator = WebResearchInputValidator()

            # Test cases: [query, should_be_blocked, test_name]
            test_cases = [
                ("javascript:alert('xss')", True, "javascript_protocol"),
                ("how to create malware", True, "malware_query"),
                (
                    "data:text/html,<script>alert(1)</script>",
                    True,
                    "data_uri_injection",
                ),
                ("' OR '1'='1", True, "sql_injection_basic"),
                ("$(rm -rf /)", True, "command_injection"),
                ("python programming tutorial", False, "legitimate_query"),
                ("../../../etc/passwd", True, "path_traversal"),
                ("{%raw%}{{7*7}}{%endraw%}", True, "template_injection"),
                ("how to secure databases", False, "security_topic"),
                ("onload=alert(1)", True, "event_handler"),
            ]

            for query, should_block, test_case_name in test_cases:
                result = validator.validate_research_query(query)

                if should_block:
                    # Should be blocked
                    if not result["safe"]:
                        test_details["subtests"][test_case_name] = "PASSED"
                        test_details["passed"] += 1
                    else:
                        test_details["subtests"][
                            test_case_name
                        ] = "FAILED - Did not block malicious input"
                        test_details["failed"] += 1
                else:
                    # Should be allowed
                    if result["safe"]:
                        test_details["subtests"][test_case_name] = "PASSED"
                        test_details["passed"] += 1
                    else:
                        test_details["subtests"][
                            test_case_name
                        ] = f"FAILED - Incorrectly blocked: {result.get('threats_detected', [])}"
                        test_details["failed"] += 1

            # Update overall test results
            if test_details["failed"] == 0:
                self.test_results["tests_passed"] += 1
                test_details["status"] = "PASSED"
            else:
                self.test_results["tests_failed"] += 1
                test_details["status"] = "FAILED"

        except Exception as e:
            logger.error(f"Malicious detection test error: {e}")
            test_details["status"] = "ERROR"
            test_details["error"] = str(e)
            self.test_results["tests_failed"] += 1

        self.test_results["test_details"][test_name] = test_details

    async def _test_performance(self):
        """Test performance of security components"""
        test_name = "performance"
        logger.info("Testing security component performance")

        test_details = {"passed": 0, "failed": 0, "subtests": {}, "metrics": {}}

        try:
            validator = WebResearchInputValidator()

            # Test 1: Query validation performance
            test_query = "How to optimize Python web applications for security"

            start_time = time.time()
            for _ in range(100):  # 100 iterations
                validator.validate_research_query(test_query)
            end_time = time.time()

            avg_time = (end_time - start_time) / 100
            test_details["metrics"]["avg_query_validation_ms"] = round(
                avg_time * 1000, 2
            )

            if avg_time < 0.01:  # Less than 10ms per query
                test_details["subtests"]["query_validation_performance"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "query_validation_performance"
                ] = f"FAILED - Too slow: {avg_time:.3f}s"
                test_details["failed"] += 1

            # Test 2: URL validation performance
            test_url = "https://github.com/example/repository"

            start_time = time.time()
            for _ in range(50):  # 50 iterations
                validator.validate_url(test_url)
            end_time = time.time()

            avg_url_time = (end_time - start_time) / 50
            test_details["metrics"]["avg_url_validation_ms"] = round(
                avg_url_time * 1000, 2
            )

            if avg_url_time < 0.005:  # Less than 5ms per URL
                test_details["subtests"]["url_validation_performance"] = "PASSED"
                test_details["passed"] += 1
            else:
                test_details["subtests"][
                    "url_validation_performance"
                ] = f"FAILED - Too slow: {avg_url_time:.3f}s"
                test_details["failed"] += 1

            # Update overall test results
            if test_details["failed"] == 0:
                self.test_results["tests_passed"] += 1
                test_details["status"] = "PASSED"
            else:
                self.test_results["tests_failed"] += 1
                test_details["status"] = "FAILED"

        except Exception as e:
            logger.error(f"Performance test error: {e}")
            test_details["status"] = "ERROR"
            test_details["error"] = str(e)
            self.test_results["tests_failed"] += 1

        self.test_results["test_details"][test_name] = test_details

    def print_results(self):
        """Print formatted test results"""
        logger.info("\n" + "=" * 80)
        logger.info("AUTOBOT WEB RESEARCH SECURITY TEST RESULTS")
        logger.info("=" * 80)

        status_color = {
            "PASSED": "\033[92m",  # Green
            "MOSTLY_PASSED": "\033[93m",  # Yellow
            "FAILED": "\033[91m",  # Red
            "ERROR": "\033[91m",  # Red
            "unknown": "\033[90m",  # Gray
        }
        reset_color = "\033[0m"

        overall_status = self.test_results["overall_status"]
        color = status_color.get(overall_status, "")

        logger.info(f"Overall Status: {color}{overall_status}{reset_color}")
        logger.info(f"Tests Passed: {self.test_results['tests_passed']}")
        logger.error(f"Tests Failed: {self.test_results['tests_failed']}")
        print(
            f"Total Tests: {self.test_results['tests_passed'] + self.test_results['tests_failed']}"
        )

        logger.info("\nDetailed Results:")
        logger.info("-" * 40)

        for test_name, details in self.test_results["test_details"].items():
            status = details.get("status", "unknown")
            color = status_color.get(status, "")
            logger.info(f"\n{test_name.upper()}: {color}{status}{reset_color}")

            if "subtests" in details:
                for subtest, result in details["subtests"].items():
                    result_status = "PASSED" if result == "PASSED" else "FAILED"
                    subtest_color = status_color.get(result_status, "")
                    logger.info(f"  └─ {subtest}: {subtest_color}{result}{reset_color}")

            if "metrics" in details:
                logger.info("  Metrics:")
                for metric, value in details["metrics"].items():
                    logger.info(f"    └─ {metric}: {value}")

            if "error" in details:
                logger.error(f"  Error: {details['error']}")

        logger.info("\n" + "=" * 80)

        if overall_status == "PASSED":
            logger.info("🛡️  ALL SECURITY TESTS PASSED - Web research can be safely enabled")
        elif overall_status == "MOSTLY_PASSED":
            print(
                "⚠️  MOST TESTS PASSED - Review failed tests before enabling web research"
            )
        else:
            print(
                "❌ SECURITY TESTS FAILED - DO NOT enable web research until issues are resolved"
            )

        logger.info("=" * 80)


async def main():
    """Main test execution"""
    logger.info("AutoBot Web Research Security Test Suite")
    logger.info("Testing comprehensive security implementation...")

    tester = WebResearchSecurityTester()
    results = await tester.run_all_tests()

    # Print results
    tester.print_results()

    # Save results to file
    results_file = Path("test_results_web_research_security.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"\nDetailed results saved to: {results_file}")

    # Exit with appropriate code
    if results["overall_status"] in ["PASSED", "MOSTLY_PASSED"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
