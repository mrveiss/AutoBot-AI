#!/usr/bin/env python3
"""
AutoBot Phase 9 Comprehensive System Validation
Comprehensive testing and validation suite for production readiness
"""

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Add AutoBot paths
sys.path.append("/home/kali/Desktop/AutoBot")


@dataclass
class TestResult:
    """Test result container"""

    test_name: str
    status: str  # "pass", "fail", "warning", "skip"
    message: str
    duration: float
    details: Optional[Dict] = None
    timestamp: Optional[str] = None


class AutoBotSystemValidator:
    """Comprehensive AutoBot system validation"""

    def __init__(self):
        self.results = []
        self.start_time = time.time()
        self.backend_host = "172.16.168.20"
        self.backend_port = 8001
        self.frontend_host = "172.16.168.21"
        self.frontend_port = 5173
        self.redis_host = "172.16.168.23"
        self.redis_port = 6379

    def log_result(
        self, test_name: str, status: str, message: str, details: Optional[Dict] = None
    ):
        """Log a test result"""
        result = TestResult(
            test_name=test_name,
            status=status,
            message=message,
            duration=time.time() - self.start_time,
            details=details or {},
            timestamp=datetime.now().isoformat(),
        )
        self.results.append(result)

        # Console output
        status_icon = {"pass": "✅", "fail": "❌", "warning": "⚠️", "skip": "⏭️"}
        print(f"{status_icon.get(status, '?')} {test_name}: {message}")
        if details:
            for key, value in details.items():
                print(f"    {key}: {value}")

    def check_port_connectivity(
        self, host: str, port: int, service_name: str, timeout: int = 3
    ) -> bool:
        """Check if a port is accessible"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                self.log_result(
                    f"Port Connectivity - {service_name}",
                    "pass",
                    f"{host}:{port} is accessible",
                    {"host": host, "port": port, "response_time": f"< {timeout}s"},
                )
                return True
            else:
                self.log_result(
                    f"Port Connectivity - {service_name}",
                    "fail",
                    f"{host}:{port} is not accessible",
                    {"host": host, "port": port, "error_code": result},
                )
                return False
        except Exception as e:
            self.log_result(
                f"Port Connectivity - {service_name}",
                "fail",
                f"Connection test failed: {str(e)}",
                {"host": host, "port": port, "exception": str(e)},
            )
            return False

    def test_infrastructure_connectivity(self):
        """Test distributed VM infrastructure connectivity"""
        print("\n=== INFRASTRUCTURE CONNECTIVITY TESTS ===")

        services = [
            (self.backend_host, self.backend_port, "Backend API"),
            (self.redis_host, self.redis_port, "Redis Database"),
            (self.frontend_host, self.frontend_port, "Frontend Server"),
            ("172.16.168.22", 8081, "NPU Worker"),
            ("172.16.168.24", 8080, "AI Stack"),
            ("172.16.168.25", 3000, "Browser Service"),
        ]

        connectivity_results = []
        for host, port, name in services:
            is_connected = self.check_port_connectivity(host, port, name)
            connectivity_results.append((name, is_connected))

        # Summary
        connected_count = sum(1 for _, connected in connectivity_results if connected)
        total_count = len(connectivity_results)

        if connected_count == total_count:
            self.log_result(
                "Infrastructure Summary",
                "pass",
                f"All {total_count} services accessible",
                {"connected": connected_count, "total": total_count},
            )
        elif connected_count > total_count // 2:
            self.log_result(
                "Infrastructure Summary",
                "warning",
                f"{connected_count}/{total_count} services accessible",
                {"connected": connected_count, "total": total_count},
            )
        else:
            self.log_result(
                "Infrastructure Summary",
                "fail",
                f"Only {connected_count}/{total_count} services accessible",
                {"connected": connected_count, "total": total_count},
            )

    def test_api_endpoints(self):
        """Test critical API endpoints"""
        print("\n=== API ENDPOINT VALIDATION ===")

        base_url = f"http://{self.backend_host}:{self.backend_port}"

        # Check if backend is running first
        if not self.check_port_connectivity(
            self.backend_host, self.backend_port, "Backend API"
        ):
            self.log_result(
                "API Endpoint Tests",
                "skip",
                "Backend not accessible - skipping API tests",
                {"base_url": base_url},
            )
            return

        endpoints = [
            ("/api/health", "Health Check"),
            ("/api/endpoints", "Router Registry"),
            ("/api/knowledge_base/stats/basic", "Knowledge Base Stats"),
            ("/api/llm/status", "LLM Status"),
            ("/api/system/status", "System Status"),
            ("/ws/health", "WebSocket Health"),
            ("/api/chat/health", "Chat Health"),  # Known issue
        ]

        for endpoint, description in endpoints:
            self.test_single_endpoint(base_url + endpoint, description)

    def test_single_endpoint(self, url: str, description: str, timeout: int = 5):
        """Test a single API endpoint"""
        try:
            import requests

            start_time = time.time()
            response = requests.get(url, timeout=timeout)
            duration = time.time() - start_time

            if response.status_code == 200:
                self.log_result(
                    f"API Endpoint - {description}",
                    "pass",
                    f"HTTP {response.status_code} - Response time: {duration:.2f}s",
                    {
                        "url": url,
                        "status_code": response.status_code,
                        "response_time": f"{duration:.2f}s",
                        "content_length": len(response.text),
                    },
                )
            elif response.status_code == 404:
                self.log_result(
                    f"API Endpoint - {description}",
                    "warning",
                    f"HTTP {response.status_code} - Endpoint not found",
                    {
                        "url": url,
                        "status_code": response.status_code,
                        "response_time": f"{duration:.2f}s",
                    },
                )
            else:
                self.log_result(
                    f"API Endpoint - {description}",
                    "fail",
                    f"HTTP {response.status_code} - Unexpected response",
                    {
                        "url": url,
                        "status_code": response.status_code,
                        "response_time": f"{duration:.2f}s",
                    },
                )

        except requests.exceptions.Timeout:
            self.log_result(
                f"API Endpoint - {description}",
                "fail",
                f"Request timed out after {timeout}s",
                {"url": url, "timeout": timeout},
            )
        except requests.exceptions.ConnectionError:
            self.log_result(
                f"API Endpoint - {description}",
                "fail",
                "Connection refused - service unavailable",
                {"url": url},
            )
        except Exception as e:
            self.log_result(
                f"API Endpoint - {description}",
                "fail",
                f"Request failed: {str(e)}",
                {"url": url, "exception": str(e)},
            )

    def test_router_registry(self):
        """Test router registry and loading"""
        print("\n=== ROUTER REGISTRY VALIDATION ===")

        try:
            from backend.api.registry import registry

            enabled = registry.get_enabled_routers()
            disabled = {
                k: v
                for k, v in registry.routers.items()
                if v.status.value == "disabled"
            }
            lazy_load = {
                k: v
                for k, v in registry.routers.items()
                if v.status.value == "lazy_load"
            }

            self.log_result(
                "Router Registry - Enabled",
                "pass",
                f"{len(enabled)} routers enabled",
                {"count": len(enabled), "routers": list(enabled.keys())},
            )

            if disabled:
                self.log_result(
                    "Router Registry - Disabled",
                    "warning",
                    f"{len(disabled)} routers disabled",
                    {"count": len(disabled), "routers": list(disabled.keys())},
                )

            if lazy_load:
                self.log_result(
                    "Router Registry - Lazy Load",
                    "pass",
                    f"{len(lazy_load)} routers set for lazy loading",
                    {"count": len(lazy_load), "routers": list(lazy_load.keys())},
                )

            # Check for missing chat health endpoint
            if "chat" in enabled:
                chat_config = enabled["chat"]
                self.log_result(
                    "Chat Router Configuration",
                    "pass",
                    f"Chat router loaded with prefix {chat_config.prefix}",
                    {"prefix": chat_config.prefix, "tags": chat_config.tags},
                )
            else:
                self.log_result(
                    "Chat Router Configuration",
                    "fail",
                    "Chat router not found in enabled routers",
                    {"available_routers": list(enabled.keys())},
                )

        except ImportError as e:
            self.log_result(
                "Router Registry Analysis",
                "fail",
                f"Cannot import router registry: {str(e)}",
                {"exception": str(e)},
            )
        except Exception as e:
            self.log_result(
                "Router Registry Analysis",
                "fail",
                f"Registry analysis failed: {str(e)}",
                {"exception": str(e)},
            )

    def test_knowledge_base_functionality(self):
        """Test knowledge base functionality"""
        print("\n=== KNOWLEDGE BASE VALIDATION ===")

        # Check if backend is accessible
        if not self.check_port_connectivity(
            self.backend_host, self.backend_port, "Backend API", timeout=2
        ):
            self.log_result(
                "Knowledge Base Tests",
                "skip",
                "Backend not accessible - skipping knowledge base tests",
            )
            return

        try:
            import requests

            # Test stats endpoint
            stats_url = f"http://{self.backend_host}:{self.backend_port}/api/knowledge_base/stats/basic"
            response = requests.get(stats_url, timeout=10)

            if response.status_code == 200:
                stats = response.json()
                self.log_result(
                    "Knowledge Base Stats",
                    "pass",
                    f"Retrieved knowledge base statistics",
                    {
                        "total_documents": stats.get("total_documents", 0),
                        "total_chunks": stats.get("total_chunks", 0),
                        "total_facts": stats.get("total_facts", 0),
                    },
                )

                # Validate knowledge base has data
                doc_count = stats.get("total_documents", 0)
                if doc_count > 1000:
                    self.log_result(
                        "Knowledge Base Content",
                        "pass",
                        f"Knowledge base contains {doc_count} documents",
                        {"document_count": doc_count},
                    )
                elif doc_count > 0:
                    self.log_result(
                        "Knowledge Base Content",
                        "warning",
                        f"Knowledge base has limited content: {doc_count} documents",
                        {"document_count": doc_count},
                    )
                else:
                    self.log_result(
                        "Knowledge Base Content",
                        "fail",
                        "Knowledge base appears to be empty",
                        {"document_count": doc_count},
                    )
            else:
                self.log_result(
                    "Knowledge Base Stats",
                    "fail",
                    f"Stats endpoint returned HTTP {response.status_code}",
                    {"status_code": response.status_code},
                )

            # Test search functionality
            search_url = f"http://{self.backend_host}:{self.backend_port}/api/knowledge_base/search"
            search_payload = {"query": "Redis configuration", "limit": 3}

            response = requests.post(search_url, json=search_payload, timeout=10)

            if response.status_code == 200:
                search_results = response.json()
                results_count = len(search_results.get("results", []))
                self.log_result(
                    "Knowledge Base Search",
                    "pass" if results_count > 0 else "warning",
                    f"Search returned {results_count} results",
                    {"query": "Redis configuration", "results_count": results_count},
                )
            else:
                self.log_result(
                    "Knowledge Base Search",
                    "fail",
                    f"Search endpoint returned HTTP {response.status_code}",
                    {"status_code": response.status_code},
                )

        except requests.exceptions.Timeout:
            self.log_result(
                "Knowledge Base Tests",
                "fail",
                "Request timed out - knowledge base may be initializing",
                {"timeout": "10s"},
            )
        except Exception as e:
            self.log_result(
                "Knowledge Base Tests",
                "fail",
                f"Knowledge base test failed: {str(e)}",
                {"exception": str(e)},
            )

    def test_llm_integration(self):
        """Test LLM integration and model availability"""
        print("\n=== LLM INTEGRATION VALIDATION ===")

        # Check if backend is accessible
        if not self.check_port_connectivity(
            self.backend_host, self.backend_port, "Backend API", timeout=2
        ):
            self.log_result(
                "LLM Integration Tests",
                "skip",
                "Backend not accessible - skipping LLM tests",
            )
            return

        try:
            import requests

            # Test LLM status
            status_url = (
                f"http://{self.backend_host}:{self.backend_port}/api/llm/status"
            )
            response = requests.get(status_url, timeout=10)

            if response.status_code == 200:
                llm_status = response.json()
                self.log_result(
                    "LLM Status Check",
                    "pass",
                    "LLM status endpoint accessible",
                    {"response": llm_status},
                )

                # Check Ollama connectivity
                if "ollama" in llm_status:
                    ollama_status = llm_status["ollama"].get("status", "unknown")
                    if ollama_status == "connected":
                        self.log_result(
                            "Ollama Connection",
                            "pass",
                            "Ollama LLM service connected",
                            {"status": ollama_status},
                        )
                    else:
                        self.log_result(
                            "Ollama Connection",
                            "warning",
                            f"Ollama status: {ollama_status}",
                            {"status": ollama_status},
                        )
            else:
                self.log_result(
                    "LLM Status Check",
                    "fail",
                    f"LLM status endpoint returned HTTP {response.status_code}",
                    {"status_code": response.status_code},
                )

            # Test model availability
            models_url = (
                f"http://{self.backend_host}:{self.backend_port}/api/llm/models"
            )
            response = requests.get(models_url, timeout=10)

            if response.status_code == 200:
                models_data = response.json()
                model_count = len(models_data.get("models", []))
                self.log_result(
                    "LLM Models Available",
                    "pass" if model_count > 0 else "warning",
                    f"{model_count} models available",
                    {"model_count": model_count},
                )
            else:
                self.log_result(
                    "LLM Models Available",
                    "warning",
                    f"Models endpoint returned HTTP {response.status_code}",
                    {"status_code": response.status_code},
                )

        except Exception as e:
            self.log_result(
                "LLM Integration Tests",
                "fail",
                f"LLM integration test failed: {str(e)}",
                {"exception": str(e)},
            )

    def test_system_resources(self):
        """Test system resources and performance"""
        print("\n=== SYSTEM RESOURCE VALIDATION ===")

        try:
            # CPU usage
            result = subprocess.run(["top", "-bn1"], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split("\n")
                cpu_line = next((line for line in lines if "Cpu" in line), None)
                mem_line = next(
                    (line for line in lines if "Mem" in line or "KiB Mem" in line), None
                )

                if cpu_line:
                    self.log_result(
                        "System CPU Usage",
                        "pass",
                        "CPU information retrieved",
                        {"cpu_info": cpu_line.strip()},
                    )

                if mem_line:
                    self.log_result(
                        "System Memory Usage",
                        "pass",
                        "Memory information retrieved",
                        {"memory_info": mem_line.strip()},
                    )

            # Disk usage
            disk_result = subprocess.run(
                ["df", "-h", "/"], capture_output=True, text=True
            )
            if disk_result.returncode == 0:
                disk_lines = disk_result.stdout.strip().split("\n")
                if len(disk_lines) > 1:
                    disk_info = disk_lines[1]
                    self.log_result(
                        "System Disk Usage",
                        "pass",
                        "Disk information retrieved",
                        {"disk_info": disk_info.strip()},
                    )

        except Exception as e:
            self.log_result(
                "System Resource Check",
                "warning",
                f"Resource check failed: {str(e)}",
                {"exception": str(e)},
            )

    def test_docker_services(self):
        """Test Docker services status"""
        print("\n=== DOCKER SERVICES VALIDATION ===")

        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--format",
                    "table {{.Names}}\t{{.Status}}\t{{.Image}}",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                container_lines = result.stdout.strip().split("\n")[1:]  # Skip header
                if container_lines:
                    self.log_result(
                        "Docker Services Status",
                        "pass",
                        f"{len(container_lines)} containers running",
                        {"container_count": len(container_lines)},
                    )

                    # Check for AutoBot-specific containers
                    autobot_containers = [
                        line for line in container_lines if "autobot" in line.lower()
                    ]
                    if autobot_containers:
                        self.log_result(
                            "AutoBot Docker Containers",
                            "pass",
                            f"{len(autobot_containers)} AutoBot containers found",
                            {"autobot_containers": len(autobot_containers)},
                        )
                    else:
                        self.log_result(
                            "AutoBot Docker Containers",
                            "warning",
                            "No AutoBot containers found running",
                            {"total_containers": len(container_lines)},
                        )
                else:
                    self.log_result(
                        "Docker Services Status",
                        "warning",
                        "No containers currently running",
                        {"container_count": 0},
                    )
            else:
                self.log_result(
                    "Docker Services Status",
                    "fail",
                    f"Docker command failed with exit code {result.returncode}",
                    {"exit_code": result.returncode, "error": result.stderr.strip()},
                )

        except FileNotFoundError:
            self.log_result(
                "Docker Services Status",
                "skip",
                "Docker not installed or not in PATH",
                {"reason": "docker command not found"},
            )
        except Exception as e:
            self.log_result(
                "Docker Services Status",
                "fail",
                f"Docker check failed: {str(e)}",
                {"exception": str(e)},
            )

    def generate_summary_report(self) -> Dict:
        """Generate comprehensive summary report"""
        total_tests = len(self.results)
        passed = len([r for r in self.results if r.status == "pass"])
        failed = len([r for r in self.results if r.status == "fail"])
        warnings = len([r for r in self.results if r.status == "warning"])
        skipped = len([r for r in self.results if r.status == "skip"])

        total_duration = time.time() - self.start_time

        summary = {
            "test_summary": {
                "total_tests": total_tests,
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
                "skipped": skipped,
                "success_rate": f"{(passed/total_tests*100):.1f}%"
                if total_tests > 0
                else "0%",
            },
            "execution_info": {
                "total_duration": f"{total_duration:.2f}s",
                "timestamp": datetime.now().isoformat(),
                "hostname": os.uname().nodename,
            },
            "critical_issues": [
                r.test_name for r in self.results if r.status == "fail"
            ],
            "warnings": [r.test_name for r in self.results if r.status == "warning"],
        }

        return summary

    def run_comprehensive_validation(self):
        """Run complete system validation suite"""
        print("🚀 AutoBot Phase 9 Comprehensive System Validation")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Run all test categories
        self.test_infrastructure_connectivity()
        self.test_api_endpoints()
        self.test_router_registry()
        self.test_knowledge_base_functionality()
        self.test_llm_integration()
        self.test_system_resources()
        self.test_docker_services()

        # Generate summary
        print("\n" + "=" * 60)
        print("📊 VALIDATION SUMMARY")
        print("=" * 60)

        summary = self.generate_summary_report()

        # Console summary
        print(f"Total Tests: {summary['test_summary']['total_tests']}")
        print(f"✅ Passed: {summary['test_summary']['passed']}")
        print(f"❌ Failed: {summary['test_summary']['failed']}")
        print(f"⚠️ Warnings: {summary['test_summary']['warnings']}")
        print(f"⏭️ Skipped: {summary['test_summary']['skipped']}")
        print(f"Success Rate: {summary['test_summary']['success_rate']}")
        print(f"Duration: {summary['execution_info']['total_duration']}")

        if summary["critical_issues"]:
            print(f"\n❌ CRITICAL ISSUES:")
            for issue in summary["critical_issues"]:
                print(f"  - {issue}")

        if summary["warnings"]:
            print(f"\n⚠️ WARNINGS:")
            for warning in summary["warnings"]:
                print(f"  - {warning}")

        # Save detailed results
        self.save_results(summary)

        return summary

    def save_results(self, summary: Dict):
        """Save detailed test results to file"""
        results_dir = Path("/home/kali/Desktop/AutoBot/tests/results")
        results_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON report
        json_file = results_dir / f"system_validation_{timestamp}.json"
        full_report = {
            "summary": summary,
            "detailed_results": [
                {
                    "test_name": r.test_name,
                    "status": r.status,
                    "message": r.message,
                    "duration": r.duration,
                    "details": r.details,
                    "timestamp": r.timestamp,
                }
                for r in self.results
            ],
        }

        with open(json_file, "w") as f:
            json.dump(full_report, f, indent=2)

        print(f"\n💾 Detailed results saved to: {json_file}")

        # Save summary report
        summary_file = results_dir / f"validation_summary_{timestamp}.txt"
        with open(summary_file, "w") as f:
            f.write("AutoBot Phase 9 System Validation Summary\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Timestamp: {summary['execution_info']['timestamp']}\n")
            f.write(f"Hostname: {summary['execution_info']['hostname']}\n")
            f.write(f"Duration: {summary['execution_info']['total_duration']}\n\n")

            f.write("TEST RESULTS:\n")
            f.write(f"  Total: {summary['test_summary']['total_tests']}\n")
            f.write(f"  Passed: {summary['test_summary']['passed']}\n")
            f.write(f"  Failed: {summary['test_summary']['failed']}\n")
            f.write(f"  Warnings: {summary['test_summary']['warnings']}\n")
            f.write(f"  Skipped: {summary['test_summary']['skipped']}\n")
            f.write(f"  Success Rate: {summary['test_summary']['success_rate']}\n\n")

            if summary["critical_issues"]:
                f.write("CRITICAL ISSUES:\n")
                for issue in summary["critical_issues"]:
                    f.write(f"  - {issue}\n")
                f.write("\n")

            if summary["warnings"]:
                f.write("WARNINGS:\n")
                for warning in summary["warnings"]:
                    f.write(f"  - {warning}\n")

        print(f"📋 Summary report saved to: {summary_file}")


def main():
    """Main validation execution"""
    validator = AutoBotSystemValidator()

    try:
        summary = validator.run_comprehensive_validation()

        # Exit code based on results
        if summary["test_summary"]["failed"] > 0:
            print(
                f"\n❌ Validation completed with {summary['test_summary']['failed']} critical issues"
            )
            sys.exit(1)
        elif summary["test_summary"]["warnings"] > 0:
            print(
                f"\n⚠️ Validation completed with {summary['test_summary']['warnings']} warnings"
            )
            sys.exit(2)
        else:
            print(f"\n✅ All validation tests passed successfully!")
            sys.exit(0)

    except KeyboardInterrupt:
        print(f"\n⚠️ Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Validation failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
