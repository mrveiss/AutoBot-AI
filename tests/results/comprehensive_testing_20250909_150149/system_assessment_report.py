#!/usr/bin/env python3
"""
AutoBot System Comprehensive Testing and Analysis
Testing all aspects of the AutoBot application for integrity and performance assessment
"""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests


@dataclass
class TestResult:
    category: str
    name: str
    status: str  # PASS, FAIL, WARNING, TIMEOUT, SKIP
    message: str
    details: Dict[str, Any] = None
    duration: float = 0.0
    severity: str = "INFO"  # CRITICAL, HIGH, MEDIUM, LOW, INFO


class AutoBotSystemTester:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.results: List[TestResult] = []
        self.session = requests.Session()
        self.session.timeout = 8  # Conservative timeout

    def add_result(
        self,
        category: str,
        name: str,
        status: str,
        message: str,
        details: Dict = None,
        duration: float = 0.0,
        severity: str = "INFO",
    ):
        """Add a test result"""
        self.results.append(
            TestResult(
                category=category,
                name=name,
                status=status,
                message=message,
                details=details,
                duration=duration,
                severity=severity,
            )
        )

    def test_with_timeout(self, test_func, timeout: int = 5, *args, **kwargs):
        """Execute test function with timeout protection"""
        start_time = time.time()

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(test_func, *args, **kwargs)
                result = future.result(timeout=timeout)
                duration = time.time() - start_time
                return True, result, duration
        except FutureTimeoutError:
            duration = time.time() - start_time
            return False, f"Timeout after {timeout}s", duration
        except Exception as e:
            duration = time.time() - start_time
            return False, str(e), duration

    def test_api_endpoint(
        self,
        path: str,
        method: str = "GET",
        data: Dict = None,
        expected_status: List[int] = None,
    ) -> Tuple[bool, Dict]:
        """Test a single API endpoint with robust error handling"""
        if expected_status is None:
            expected_status = [200, 201, 202]

        full_url = f"{self.base_url}{path}"

        try:
            if method.upper() == "GET":
                response = self.session.get(full_url)
            elif method.upper() == "POST":
                response = self.session.post(full_url, json=data)
            elif method.upper() == "PUT":
                response = self.session.put(full_url, json=data)
            elif method.upper() == "DELETE":
                response = self.session.delete(full_url)
            else:
                return False, {"error": f"Unsupported method: {method}"}

            success = response.status_code in expected_status

            try:
                response_data = response.json() if response.content else {}
            except Exception:
                response_data = {"raw_response": response.text[:200]}

            return success, {
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds(),
                "response_data": response_data,
                "headers": dict(response.headers),
            }

        except requests.exceptions.Timeout:
            return False, {"error": "Request timeout"}
        except requests.exceptions.ConnectionError:
            return False, {"error": "Connection error"}
        except Exception as e:
            return False, {"error": str(e)}

    def run_core_api_tests(self):
        """Test core API endpoints for basic functionality"""
        print("🔧 Testing Core API Endpoints...")

        # Core endpoints that should always work
        core_endpoints = [
            ("/api/health", "GET", "System Health Check"),
            ("/api/system/status", "GET", "System Status"),
            ("/api/system/info", "GET", "System Information"),
            ("/api/developer/system-info", "GET", "Developer System Info"),
        ]

        for path, method, description in core_endpoints:
            success, result, duration = self.test_with_timeout(
                self.test_api_endpoint, 8, path, method
            )

            if not success:
                self.add_result(
                    "Core API",
                    description,
                    "TIMEOUT",
                    f"Endpoint timed out or failed: {result}",
                    duration=duration,
                    severity="HIGH",
                )
            else:
                endpoint_success, response_data = result
                if endpoint_success:
                    self.add_result(
                        "Core API",
                        description,
                        "PASS",
                        f"Status {response_data['status_code']} in {response_data['response_time']:.3f}s",
                        details=response_data,
                        duration=duration,
                    )
                else:
                    self.add_result(
                        "Core API",
                        description,
                        "FAIL",
                        f"Failed: {response_data.get('error', 'Unknown error')}",
                        details=response_data,
                        duration=duration,
                        severity="MEDIUM",
                    )

    def run_problematic_endpoint_tests(self):
        """Test endpoints that were previously problematic"""
        print("⚠️  Testing Previously Problematic Endpoints...")

        # Endpoints that had issues
        problematic_endpoints = [
            (
                "/api/knowledge_base/search",
                "POST",
                "Knowledge Base Search",
                {"query": "test", "top_k": 3},
            ),
            ("/api/files/stats", "GET", "File Statistics", None),
            ("/api/knowledge_base/detailed_stats", "GET", "KB Detailed Stats", None),
            ("/api/settings/", "GET", "Settings API", None),
            ("/api/validation-dashboard/status", "GET", "Validation Dashboard", None),
            ("/api/monitoring/resources", "GET", "Monitoring Resources", None),
            ("/api/monitoring/services", "GET", "Monitoring Services", None),
        ]

        for path, method, description, data in problematic_endpoints:
            success, result, duration = self.test_with_timeout(
                self.test_api_endpoint,
                10,
                path,
                method,
                data,
                [200, 404, 500],  # Accept various status codes
            )

            if not success:
                self.add_result(
                    "Problematic Endpoints",
                    description,
                    "TIMEOUT",
                    f"Endpoint timed out: {result}",
                    duration=duration,
                    severity="HIGH",
                )
            else:
                endpoint_success, response_data = result
                status_code = response_data.get("status_code", 0)

                if status_code == 200:
                    self.add_result(
                        "Problematic Endpoints",
                        description,
                        "PASS",
                        f"Endpoint working: {status_code}",
                        details=response_data,
                        duration=duration,
                    )
                elif status_code == 404:
                    self.add_result(
                        "Problematic Endpoints",
                        description,
                        "WARNING",
                        f"Endpoint not found: {status_code}",
                        details=response_data,
                        duration=duration,
                        severity="MEDIUM",
                    )
                else:
                    self.add_result(
                        "Problematic Endpoints",
                        description,
                        "FAIL",
                        f"Endpoint error: {status_code}",
                        details=response_data,
                        duration=duration,
                        severity="HIGH",
                    )

    def run_service_integration_tests(self):
        """Test integration between services"""
        print("🔗 Testing Service Integration...")

        # Test Redis integration
        success, result, duration = self.test_with_timeout(
            self.test_api_endpoint, 5, "/api/cache/stats", "GET"
        )

        if success and result[0]:
            self.add_result(
                "Service Integration",
                "Redis Connection",
                "PASS",
                "Redis cache accessible",
                details=result[1],
                duration=duration,
            )
        else:
            self.add_result(
                "Service Integration",
                "Redis Connection",
                "FAIL",
                "Redis cache not accessible",
                details=result[1] if success else {"error": result},
                duration=duration,
                severity="HIGH",
            )

        # Test Ollama integration
        success, result, duration = self.test_with_timeout(
            self.test_api_endpoint, 8, "/api/llm/status", "GET"
        )

        if success and result[0]:
            self.add_result(
                "Service Integration",
                "Ollama LLM Connection",
                "PASS",
                "Ollama service accessible",
                details=result[1],
                duration=duration,
            )
        else:
            self.add_result(
                "Service Integration",
                "Ollama LLM Connection",
                "FAIL",
                "Ollama service not accessible",
                details=result[1] if success else {"error": result},
                duration=duration,
                severity="HIGH",
            )

        # Test Knowledge Base integration
        success, result, duration = self.test_with_timeout(
            self.test_api_endpoint, 10, "/api/knowledge_base/stats", "GET"
        )

        if success and result[0]:
            response_data = result[1].get("response_data", {})
            total_docs = (
                response_data.get("total_documents", 0)
                if isinstance(response_data, dict)
                else 0
            )

            if total_docs > 0:
                self.add_result(
                    "Service Integration",
                    "Knowledge Base",
                    "PASS",
                    f"Knowledge base loaded with {total_docs} documents",
                    details=result[1],
                    duration=duration,
                )
            else:
                self.add_result(
                    "Service Integration",
                    "Knowledge Base",
                    "WARNING",
                    "Knowledge base accessible but no documents found",
                    details=result[1],
                    duration=duration,
                    severity="MEDIUM",
                )
        else:
            self.add_result(
                "Service Integration",
                "Knowledge Base",
                "FAIL",
                "Knowledge base not accessible",
                details=result[1] if success else {"error": result},
                duration=duration,
                severity="HIGH",
            )

    def run_performance_tests(self):
        """Test performance characteristics"""
        print("⚡ Testing Performance...")

        # Response time tests
        performance_endpoints = [
            ("/api/health", "Health endpoint"),
            ("/api/system/status", "System status"),
            ("/api/files/stats", "File statistics"),
        ]

        for endpoint, description in performance_endpoints:
            times = []
            success_count = 0

            for i in range(3):  # Test 3 times for average
                success, result, duration = self.test_with_timeout(
                    self.test_api_endpoint, 5, endpoint, "GET"
                )

                if success and result[0]:
                    times.append(result[1]["response_time"])
                    success_count += 1

            if times:
                avg_time = sum(times) / len(times)
                max_time = max(times)

                if avg_time < 1.0:
                    self.add_result(
                        "Performance",
                        f"{description} Response Time",
                        "PASS",
                        f"Average: {avg_time:.3f}s, Max: {max_time:.3f}s",
                        details={"times": times},
                        duration=sum(times),
                    )
                elif avg_time < 3.0:
                    self.add_result(
                        "Performance",
                        f"{description} Response Time",
                        "WARNING",
                        f"Slow response - Average: {avg_time:.3f}s, Max: {max_time:.3f}s",
                        details={"times": times},
                        duration=sum(times),
                        severity="MEDIUM",
                    )
                else:
                    self.add_result(
                        "Performance",
                        f"{description} Response Time",
                        "FAIL",
                        f"Very slow response - Average: {avg_time:.3f}s, Max: {max_time:.3f}s",
                        details={"times": times},
                        duration=sum(times),
                        severity="HIGH",
                    )
            else:
                self.add_result(
                    "Performance",
                    f"{description} Response Time",
                    "FAIL",
                    "All requests failed",
                    severity="HIGH",
                )

    def check_system_processes(self):
        """Check system processes and services"""
        print("🔍 Checking System Processes...")

        # Check if uvicorn is running
        try:
            result = subprocess.run(
                ["pgrep", "-", "uvicorn"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                self.add_result(
                    "System Processes",
                    "Backend Process",
                    "PASS",
                    f"Backend running with PIDs: {', '.join(pids)}",
                )
            else:
                self.add_result(
                    "System Processes",
                    "Backend Process",
                    "FAIL",
                    "Backend process not found",
                    severity="CRITICAL",
                )
        except Exception as e:
            self.add_result(
                "System Processes",
                "Backend Process",
                "FAIL",
                f"Error checking backend process: {str(e)}",
                severity="HIGH",
            )

        # Check if Ollama is running
        try:
            result = subprocess.run(
                ["pgrep", "-", "ollama"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                self.add_result(
                    "System Processes",
                    "Ollama Process",
                    "PASS",
                    f"Ollama running with PIDs: {', '.join(pids)}",
                )
            else:
                self.add_result(
                    "System Processes",
                    "Ollama Process",
                    "WARNING",
                    "Ollama process not found",
                    severity="MEDIUM",
                )
        except Exception as e:
            self.add_result(
                "System Processes",
                "Ollama Process",
                "WARNING",
                f"Error checking Ollama process: {str(e)}",
                severity="MEDIUM",
            )

    def analyze_frontend_build_warnings(self):
        """Analyze frontend build for Vite warnings"""
        print("🏗️  Analyzing Frontend Build...")

        # Check if frontend directory exists
        frontend_dir = "/home/kali/Desktop/AutoBot/autobot-vue"
        if not os.path.exists(frontend_dir):
            self.add_result(
                "Frontend Build",
                "Directory Check",
                "FAIL",
                "Frontend directory not found",
                severity="HIGH",
            )
            return

        # Check package.json and dependencies
        package_json = os.path.join(frontend_dir, "package.json")
        if os.path.exists(package_json):
            try:
                with open(package_json, "r") as f:
                    package_data = json.load(f)

                # Check for critical dependencies
                deps = package_data.get("dependencies", {})
                dev_deps = package_data.get("devDependencies", {})

                vue_version = deps.get("@vue/compat") or deps.get("vue", "not found")
                vite_version = dev_deps.get("vite", "not found")

                self.add_result(
                    "Frontend Build",
                    "Dependencies Check",
                    "PASS",
                    f"Vue: {vue_version}, Vite: {vite_version}",
                    details={
                        "dependencies": len(deps),
                        "devDependencies": len(dev_deps),
                    },
                )

                # Check for large dependency issues
                if len(deps) > 50:
                    self.add_result(
                        "Frontend Build",
                        "Dependency Count",
                        "WARNING",
                        f"Large number of dependencies: {len(deps)}",
                        severity="MEDIUM",
                    )

            except Exception as e:
                self.add_result(
                    "Frontend Build",
                    "Package.json Analysis",
                    "FAIL",
                    f"Error reading package.json: {str(e)}",
                    severity="MEDIUM",
                )

        # Check for dist directory (build output)
        dist_dir = os.path.join(frontend_dir, "dist")
        if os.path.exists(dist_dir):
            try:
                # Check size of built assets
                total_size = 0
                file_count = 0
                for root, dirs, files in os.walk(dist_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                        file_count += 1

                size_mb = total_size / (1024 * 1024)

                if size_mb < 10:
                    self.add_result(
                        "Frontend Build",
                        "Build Size",
                        "PASS",
                        f"Build size: {size_mb:.1f}MB ({file_count} files)",
                    )
                elif size_mb < 50:
                    self.add_result(
                        "Frontend Build",
                        "Build Size",
                        "WARNING",
                        f"Large build size: {size_mb:.1f}MB ({file_count} files)",
                        severity="MEDIUM",
                    )
                else:
                    self.add_result(
                        "Frontend Build",
                        "Build Size",
                        "FAIL",
                        f"Very large build size: {size_mb:.1f}MB ({file_count} files)",
                        severity="HIGH",
                    )

            except Exception as e:
                self.add_result(
                    "Frontend Build",
                    "Build Size Analysis",
                    "WARNING",
                    f"Error analyzing build size: {str(e)}",
                    severity="LOW",
                )
        else:
            self.add_result(
                "Frontend Build",
                "Build Output",
                "WARNING",
                "No dist directory found - frontend may not be built",
                severity="MEDIUM",
            )

    def run_security_assessment(self):
        """Basic security assessment"""
        print("🛡️  Running Security Assessment...")

        # Check for exposed sensitive endpoints
        sensitive_endpoints = [
            "/api/secrets/",
            "/api/developer/",
            "/api/logs/",
        ]

        for endpoint in sensitive_endpoints:
            success, result, duration = self.test_with_timeout(
                self.test_api_endpoint, 5, endpoint, "GET", None, [200, 401, 403, 404]
            )

            if success:
                status_code = result[1].get("status_code", 0)
                if status_code == 200:
                    self.add_result(
                        "Security",
                        f"Endpoint Access {endpoint}",
                        "WARNING",
                        f"Sensitive endpoint accessible without authentication: {status_code}",
                        severity="MEDIUM",
                    )
                elif status_code in [401, 403]:
                    self.add_result(
                        "Security",
                        f"Endpoint Access {endpoint}",
                        "PASS",
                        f"Sensitive endpoint properly protected: {status_code}",
                    )
                else:
                    self.add_result(
                        "Security",
                        f"Endpoint Access {endpoint}",
                        "PASS",
                        f"Endpoint not accessible: {status_code}",
                    )

    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""

        # Categorize results
        categories = {}
        for result in self.results:
            if result.category not in categories:
                categories[result.category] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "warnings": 0,
                    "timeouts": 0,
                    "results": [],
                }

            cat = categories[result.category]
            cat["total"] += 1
            cat["results"].append(result)

            if result.status == "PASS":
                cat["passed"] += 1
            elif result.status == "FAIL":
                cat["failed"] += 1
            elif result.status == "WARNING":
                cat["warnings"] += 1
            elif result.status == "TIMEOUT":
                cat["timeouts"] += 1

        # Calculate overall statistics
        total_tests = len(self.results)
        total_passed = sum(1 for r in self.results if r.status == "PASS")
        total_failed = sum(1 for r in self.results if r.status == "FAIL")
        total_warnings = sum(1 for r in self.results if r.status == "WARNING")
        total_timeouts = sum(1 for r in self.results if r.status == "TIMEOUT")

        overall_success_rate = (
            (total_passed / total_tests * 100) if total_tests > 0 else 0
        )

        # Count by severity
        critical_issues = sum(1 for r in self.results if r.severity == "CRITICAL")
        high_issues = sum(1 for r in self.results if r.severity == "HIGH")
        medium_issues = sum(1 for r in self.results if r.severity == "MEDIUM")

        return {
            "timestamp": datetime.now().isoformat(),
            "overall_statistics": {
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "warnings": total_warnings,
                "timeouts": total_timeouts,
                "success_rate": overall_success_rate,
            },
            "severity_breakdown": {
                "critical": critical_issues,
                "high": high_issues,
                "medium": medium_issues,
                "low": total_tests - critical_issues - high_issues - medium_issues,
            },
            "category_results": categories,
            "detailed_results": [
                {
                    "category": r.category,
                    "name": r.name,
                    "status": r.status,
                    "message": r.message,
                    "severity": r.severity,
                    "duration": r.duration,
                    "details": r.details,
                }
                for r in self.results
            ],
        }

    def print_summary_report(self, report: Dict[str, Any]):
        """Print a formatted summary report"""
        print("\n" + "=" * 80)
        print("🎯 AUTOBOT COMPREHENSIVE SYSTEM ASSESSMENT REPORT")
        print("=" * 80)

        stats = report["overall_statistics"]
        severity = report["severity_breakdown"]

        print("📊 Overall Test Results:")
        print(f"   Total Tests: {stats['total_tests']}")
        print(f"   Passed: {stats['passed']} ✅")
        print(f"   Failed: {stats['failed']} ❌")
        print(f"   Warnings: {stats['warnings']} ⚠️")
        print(f"   Timeouts: {stats['timeouts']} ⏰")
        print(f"   Success Rate: {stats['success_rate']:.1f}%")

        print("\n🚨 Issue Severity:")
        print(f"   Critical: {severity['critical']} 🔴")
        print(f"   High: {severity['high']} 🟠")
        print(f"   Medium: {severity['medium']} 🟡")
        print(f"   Low: {severity['low']} 🟢")

        print("\n📋 Results by Category:")
        for category, cat_data in report["category_results"].items():
            success_rate = (
                (cat_data["passed"] / cat_data["total"] * 100)
                if cat_data["total"] > 0
                else 0
            )
            status_icon = (
                "✅" if success_rate == 100 else "⚠️" if success_rate >= 80 else "❌"
            )
            print(
                f"   {status_icon} {category}: {success_rate:.1f}% ({cat_data['passed']}/{cat_data['total']})"
            )

            # Show failures
            failures = [
                r for r in cat_data["results"] if r.status in ["FAIL", "TIMEOUT"]
            ]
            if failures:
                for failure in failures[:2]:  # Show first 2 failures
                    severity_icon = {
                        "CRITICAL": "🔴",
                        "HIGH": "🟠",
                        "MEDIUM": "🟡",
                        "LOW": "🟢",
                    }.get(failure.severity, "")
                    print(f"      {severity_icon} {failure.name}: {failure.message}")
                if len(failures) > 2:
                    print(f"      ... and {len(failures) - 2} more issues")

        # Overall assessment
        print("\n🎯 System Health Assessment:")
        if stats["success_rate"] >= 95 and severity["critical"] == 0:
            print("   🟢 EXCELLENT - System is in excellent condition")
        elif stats["success_rate"] >= 85 and severity["critical"] == 0:
            print("   🟡 GOOD - System is working well with minor issues")
        elif stats["success_rate"] >= 70:
            print("   🟠 FAIR - System is functional but needs attention")
        else:
            print(
                "   🔴 POOR - System has significant issues requiring immediate attention"
            )

        # Recommendations
        print("\n💡 Key Recommendations:")
        if severity["critical"] > 0:
            print("   • Address critical issues immediately")
        if stats["timeouts"] > stats["total_tests"] * 0.2:
            print("   • Investigate timeout issues - possible performance problems")
        if stats["failed"] > stats["total_tests"] * 0.1:
            print("   • Review failed endpoints for missing functionality")
        if severity["high"] > 3:
            print("   • High priority issues need resolution for production readiness")


def main():
    """Run comprehensive AutoBot system assessment"""
    print("🚀 Starting AutoBot Comprehensive System Assessment")
    print("=" * 80)

    tester = AutoBotSystemTester()

    # Run all test categories
    test_categories = [
        ("check_system_processes", "Checking system processes..."),
        ("run_core_api_tests", "Testing core API endpoints..."),
        (
            "run_problematic_endpoint_tests",
            "Testing previously problematic endpoints...",
        ),
        ("run_service_integration_tests", "Testing service integration..."),
        ("run_performance_tests", "Running performance tests..."),
        ("analyze_frontend_build_warnings", "Analyzing frontend build..."),
        ("run_security_assessment", "Running security assessment..."),
    ]

    for method_name, description in test_categories:
        print(f"\n{description}")
        try:
            method = getattr(tester, method_name)
            method()
        except Exception as e:
            tester.add_result(
                "System",
                method_name,
                "FAIL",
                f"Test category failed: {str(e)}",
                severity="HIGH",
            )
            print(f"   ❌ Failed: {str(e)}")

    # Generate comprehensive report
    report = tester.generate_comprehensive_report()

    # Print summary
    tester.print_summary_report(report)

    # Save detailed report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save to multiple formats
    results_dir = (
        "/home/kali/Desktop/AutoBot/tests/results/comprehensive_testing_20250909_150149"
    )
    os.makedirs(results_dir, exist_ok=True)

    # JSON report for detailed analysis
    json_file = os.path.join(results_dir, f"system_assessment_report_{timestamp}.json")
    with open(json_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Human-readable report
    text_file = os.path.join(results_dir, f"system_assessment_summary_{timestamp}.txt")
    with open(text_file, "w") as f:
        f.write("AutoBot Comprehensive System Assessment Report\n")
        f.write(f"Generated: {report['timestamp']}\n")
        f.write("=" * 80 + "\n\n")

        stats = report["overall_statistics"]
        f.write(f"Overall Success Rate: {stats['success_rate']:.1f}%\n")
        f.write(f"Total Tests: {stats['total_tests']}\n")
        f.write(
            f"Passed: {stats['passed']}, Failed: {stats['failed']}, Warnings: {stats['warnings']}\n\n"
        )

        f.write("Detailed Results:\n")
        f.write("-" * 50 + "\n")
        for result in report["detailed_results"]:
            f.write(f"[{result['status']}] {result['category']} - {result['name']}\n")
            f.write(f"  {result['message']}\n")
            if result["severity"] != "INFO":
                f.write(f"  Severity: {result['severity']}\n")
            f.write("\n")

    print("\n💾 Detailed reports saved:")
    print(f"   📊 JSON Report: {json_file}")
    print(f"   📄 Summary Report: {text_file}")

    return report


if __name__ == "__main__":
    try:
        report = main()

        # Exit with appropriate code
        stats = report["overall_statistics"]
        severity = report["severity_breakdown"]

        if severity["critical"] > 0:
            sys.exit(3)  # Critical issues
        elif stats["success_rate"] < 80:
            sys.exit(2)  # Major issues
        elif stats["success_rate"] < 95:
            sys.exit(1)  # Minor issues
        else:
            sys.exit(0)  # All good

    except KeyboardInterrupt:
        print("\n⏹️  Assessment interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Assessment failed with error: {str(e)}")
        sys.exit(1)
