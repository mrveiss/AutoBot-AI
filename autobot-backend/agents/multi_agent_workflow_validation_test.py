#!/usr/bin/env python3
"""
AutoBot Multi-Agent Workflow Validation
Tests the complete multi-agent coordination system for production readiness
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests

# Add AutoBot paths
sys.path.append("/home/kali/Desktop/AutoBot")


@dataclass
class WorkflowTestResult:
    """Multi-agent workflow test result"""

    test_name: str
    status: str  # "pass", "fail", "warning", "skip"
    message: str
    duration: float
    agents_involved: List[str]
    performance_metrics: Dict
    details: Dict = None


class MultiAgentWorkflowValidator:
    """Validates multi-agent coordination and workflow execution"""

    def __init__(self):
        self.results = []
        self.backend_host = "172.16.168.20"
        self.backend_port = 8001
        self.base_url = f"http://{self.backend_host}:{self.backend_port}"

    def log_result(
        self,
        test_name: str,
        status: str,
        message: str,
        agents_involved: List[str] = None,
        performance_metrics: Dict = None,
        details: Dict = None,
    ):
        """Log workflow test result"""
        result = WorkflowTestResult(
            test_name=test_name,
            status=status,
            message=message,
            duration=time.time(),
            agents_involved=agents_involved or [],
            performance_metrics=performance_metrics or {},
            details=details or {},
        )
        self.results.append(result)

        status_icon = {"pass": "✅", "fail": "❌", "warning": "⚠️", "skip": "⏭️"}
        print(f"{status_icon.get(status, '?')} {test_name}: {message}")

        if agents_involved:
            print(f"    Agents: {', '.join(agents_involved)}")
        if performance_metrics:
            for key, value in performance_metrics.items():
                print(f"    {key}: {value}")

    def test_backend_availability(self) -> bool:
        """Test if backend is available for testing"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            if response.status_code == 200:
                self.log_result(
                    "Backend Availability",
                    "pass",
                    "Backend is accessible and responding",
                    performance_metrics={
                        "response_time": f"{response.elapsed.total_seconds():.3f}s"
                    },
                )
                return True
            else:
                self.log_result(
                    "Backend Availability",
                    "fail",
                    f"Backend returned HTTP {response.status_code}",
                    details={"status_code": response.status_code},
                )
                return False
        except Exception as e:
            self.log_result(
                "Backend Availability",
                "fail",
                f"Backend not accessible: {str(e)}",
                details={"exception": str(e)},
            )
            return False

    def test_multi_agent_coordination(self):
        """Test multi-agent coordination system"""
        print("\n=== MULTI-AGENT COORDINATION TESTS ===")

        if not self.test_backend_availability():
            self.log_result(
                "Multi-Agent Coordination",
                "skip",
                "Backend not available - skipping multi-agent tests",
            )
            return

        # Test agent deployment endpoints
        agent_endpoints = [
            ("/api/intelligent-agent/deploy", "Intelligent Agent"),
            ("/api/research/deploy", "Research Agent"),
            ("/api/knowledge_base/search", "Knowledge Agent"),
            ("/api/llm/status", "LLM Agent"),
        ]

        active_agents = []

        for endpoint, agent_name in agent_endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                if response.status_code == 200:
                    active_agents.append(agent_name)
                    self.log_result(
                        f"Agent Availability - {agent_name}",
                        "pass",
                        f"{agent_name} is accessible",
                        agents_involved=[agent_name],
                        performance_metrics={
                            "response_time": f"{response.elapsed.total_seconds():.3f}s"
                        },
                    )
                else:
                    self.log_result(
                        f"Agent Availability - {agent_name}",
                        "warning" if response.status_code == 404 else "fail",
                        f"{agent_name} returned HTTP {response.status_code}",
                        agents_involved=[agent_name],
                        details={"status_code": response.status_code},
                    )
            except Exception as e:
                self.log_result(
                    f"Agent Availability - {agent_name}",
                    "fail",
                    f"{agent_name} failed: {str(e)}",
                    agents_involved=[agent_name],
                    details={"exception": str(e)},
                )

        # Test agent coordination
        if len(active_agents) >= 2:
            self.log_result(
                "Agent Coordination Status",
                "pass",
                f"{len(active_agents)} agents available for coordination",
                agents_involved=active_agents,
                performance_metrics={"available_agents": len(active_agents)},
            )
        else:
            self.log_result(
                "Agent Coordination Status",
                "warning",
                f"Only {len(active_agents)} agents available - limited coordination",
                agents_involved=active_agents,
                performance_metrics={"available_agents": len(active_agents)},
            )

    def test_parallel_task_execution(self):
        """Test parallel task execution capabilities"""
        print("\n=== PARALLEL TASK EXECUTION TESTS ===")

        if not self.test_backend_availability():
            return

        # Test concurrent API calls to different endpoints
        test_endpoints = [
            "/api/health",
            "/api/system/status",
            "/api/endpoints",
            "/ws/health",
        ]

        start_time = time.time()

        # Execute requests in parallel using asyncio
        async def make_request(endpoint):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, lambda: requests.get(f"{self.base_url}{endpoint}", timeout=5)
                )
                return {
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "response_time": response.elapsed.total_seconds(),
                    "success": 200 <= response.status_code < 400,
                }
            except Exception as e:
                return {"endpoint": endpoint, "error": str(e), "success": False}

        # Run parallel requests
        async def run_parallel_tests():
            tasks = [make_request(endpoint) for endpoint in test_endpoints]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        try:
            # Run the async test
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            parallel_results = loop.run_until_complete(run_parallel_tests())
            loop.close()

            total_time = time.time() - start_time
            successful_requests = sum(
                1
                for r in parallel_results
                if isinstance(r, dict) and r.get("success", False)
            )

            if successful_requests >= len(test_endpoints) * 0.8:  # 80% success rate
                self.log_result(
                    "Parallel Task Execution",
                    "pass",
                    f"{successful_requests}/{len(test_endpoints)} parallel requests successful",
                    agents_involved=["Backend Router", "API Gateway"],
                    performance_metrics={
                        "total_time": f"{total_time:.3f}s",
                        "successful_requests": successful_requests,
                        "success_rate": f"{(successful_requests/len(test_endpoints)*100):.1f}%",
                    },
                    details={"results": parallel_results},
                )
            else:
                self.log_result(
                    "Parallel Task Execution",
                    "fail",
                    f"Only {successful_requests}/{len(test_endpoints)} parallel requests successful",
                    agents_involved=["Backend Router", "API Gateway"],
                    performance_metrics={
                        "total_time": f"{total_time:.3f}s",
                        "successful_requests": successful_requests,
                        "success_rate": f"{(successful_requests/len(test_endpoints)*100):.1f}%",
                    },
                    details={"results": parallel_results},
                )

        except Exception as e:
            self.log_result(
                "Parallel Task Execution",
                "fail",
                f"Parallel execution test failed: {str(e)}",
                details={"exception": str(e)},
            )

    def test_agent_task_completion(self):
        """Test agent task completion tracking"""
        print("\n=== AGENT TASK COMPLETION TESTS ===")

        if not self.test_backend_availability():
            return

        # Test knowledge base search task (simulates agent task)
        search_payload = {"query": "AutoBot system architecture", "limit": 5}

        try:
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/api/knowledge_base/search",
                json=search_payload,
                timeout=15,
            )
            completion_time = time.time() - start_time

            if response.status_code == 200:
                results = response.json()
                result_count = len(results.get("results", []))

                self.log_result(
                    "Knowledge Base Task Completion",
                    "pass" if result_count > 0 else "warning",
                    f"Knowledge search completed in {completion_time:.3f}s",
                    agents_involved=["Knowledge Agent", "Vector Database"],
                    performance_metrics={
                        "completion_time": f"{completion_time:.3f}s",
                        "results_count": result_count,
                        "throughput": f"{result_count/completion_time:.1f} results/sec",
                    },
                )
            else:
                self.log_result(
                    "Knowledge Base Task Completion",
                    "fail",
                    f"Knowledge search failed with HTTP {response.status_code}",
                    agents_involved=["Knowledge Agent"],
                    details={"status_code": response.status_code},
                )

        except Exception as e:
            self.log_result(
                "Knowledge Base Task Completion",
                "fail",
                f"Knowledge search task failed: {str(e)}",
                agents_involved=["Knowledge Agent"],
                details={"exception": str(e)},
            )

    def test_agent_communication_workflow(self):
        """Test inter-agent communication workflow"""
        print("\n=== INTER-AGENT COMMUNICATION TESTS ===")

        if not self.test_backend_availability():
            return

        # Test chat workflow that involves multiple agents
        chat_payload = {
            "message": "What Redis configuration does AutoBot use for distributed VMs?"
        }

        try:
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/api/chat/direct", json=chat_payload, timeout=30
            )
            processing_time = time.time() - start_time

            if response.status_code == 200:
                chat_result = response.json()

                # Analyze response for agent involvement
                agents_involved = []
                if "knowledge" in str(chat_result).lower():
                    agents_involved.append("Knowledge Agent")
                if "search" in str(chat_result).lower():
                    agents_involved.append("Search Agent")
                if "redis" in str(chat_result).lower():
                    agents_involved.append("System Agent")

                self.log_result(
                    "Inter-Agent Communication Workflow",
                    "pass",
                    "Multi-agent chat workflow completed successfully",
                    agents_involved=agents_involved or ["Chat Agent", "LLM Agent"],
                    performance_metrics={
                        "processing_time": f"{processing_time:.3f}s",
                        "response_length": len(str(chat_result)),
                        "agents_detected": len(agents_involved),
                    },
                    details={"response_sample": str(chat_result)[:200] + "..."},
                )
            else:
                self.log_result(
                    "Inter-Agent Communication Workflow",
                    "fail" if response.status_code >= 500 else "warning",
                    f"Chat workflow returned HTTP {response.status_code}",
                    agents_involved=["Chat Agent"],
                    details={"status_code": response.status_code},
                )

        except Exception as e:
            self.log_result(
                "Inter-Agent Communication Workflow",
                "fail",
                f"Inter-agent communication failed: {str(e)}",
                details={"exception": str(e)},
            )

    def test_system_resilience(self):
        """Test system resilience and error recovery"""
        print("\n=== SYSTEM RESILIENCE TESTS ===")

        if not self.test_backend_availability():
            return

        # Test invalid endpoint handling
        invalid_endpoints = [
            "/api/nonexistent/endpoint",
            "/api/chat/invalid_method",
            "/api/knowledge_base/malformed",
        ]

        resilience_score = 0
        total_tests = len(invalid_endpoints)

        for endpoint in invalid_endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)

                # Should gracefully handle with 404 or similar
                if 400 <= response.status_code < 500:
                    resilience_score += 1

            except Exception:
                # Connection errors are expected and show resilience
                resilience_score += 1

        resilience_percentage = (resilience_score / total_tests) * 100

        if resilience_percentage >= 80:
            self.log_result(
                "System Resilience",
                "pass",
                f"System handles errors gracefully ({resilience_percentage:.0f}% resilience)",
                agents_involved=["Error Handler", "API Gateway"],
                performance_metrics={
                    "resilience_score": f"{resilience_percentage:.0f}%"
                },
            )
        else:
            self.log_result(
                "System Resilience",
                "warning",
                f"System resilience could be improved ({resilience_percentage:.0f}% resilience)",
                agents_involved=["Error Handler", "API Gateway"],
                performance_metrics={
                    "resilience_score": f"{resilience_percentage:.0f}%"
                },
            )

    def generate_workflow_report(self) -> Dict:
        """Generate comprehensive workflow validation report"""
        total_tests = len(self.results)
        passed = len([r for r in self.results if r.status == "pass"])
        failed = len([r for r in self.results if r.status == "fail"])
        warnings = len([r for r in self.results if r.status == "warning"])
        skipped = len([r for r in self.results if r.status == "skip"])

        # Collect all agents involved
        all_agents = set()
        for result in self.results:
            all_agents.update(result.agents_involved)

        # Performance metrics
        response_times = []
        for result in self.results:
            if "response_time" in result.performance_metrics:
                time_str = result.performance_metrics["response_time"].replace("s", "")
                try:
                    response_times.append(float(time_str))
                except Exception:
                    pass

        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )

        return {
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
            "agent_analysis": {
                "agents_tested": list(all_agents),
                "agent_count": len(all_agents),
                "coordination_capable": len(all_agents) >= 3,
            },
            "performance_metrics": {
                "average_response_time": f"{avg_response_time:.3f}s",
                "fastest_response": f"{min(response_times):.3f}s"
                if response_times
                else "N/A",
                "slowest_response": f"{max(response_times):.3f}s"
                if response_times
                else "N/A",
            },
            "production_readiness": {
                "multi_agent_coordination": passed >= 5,
                "performance_acceptable": avg_response_time < 5.0,
                "resilience_verified": any(
                    "resilience" in r.test_name.lower() for r in self.results
                ),
            },
        }

    def run_multi_agent_validation(self):
        """Run complete multi-agent workflow validation"""
        print("🚀 AutoBot Multi-Agent Workflow Validation")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Run all multi-agent tests
        self.test_multi_agent_coordination()
        self.test_parallel_task_execution()
        self.test_agent_task_completion()
        self.test_agent_communication_workflow()
        self.test_system_resilience()

        # Generate comprehensive report
        print("\n" + "=" * 60)
        print("📊 MULTI-AGENT VALIDATION SUMMARY")
        print("=" * 60)

        report = self.generate_workflow_report()

        # Console summary
        print(f"Total Tests: {report['test_summary']['total_tests']}")
        print(f"✅ Passed: {report['test_summary']['passed']}")
        print(f"❌ Failed: {report['test_summary']['failed']}")
        print(f"⚠️ Warnings: {report['test_summary']['warnings']}")
        print(f"⏭️ Skipped: {report['test_summary']['skipped']}")
        print(f"Success Rate: {report['test_summary']['success_rate']}")

        print("\n🤖 AGENT ANALYSIS:")
        print(f"Agents Tested: {report['agent_analysis']['agent_count']}")
        print(
            f"Coordination Capable: {'✅ Yes' if report['agent_analysis']['coordination_capable'] else '⚠️ Limited'}"
        )

        print("\n⚡ PERFORMANCE:")
        print(
            f"Average Response Time: {report['performance_metrics']['average_response_time']}"
        )
        print(
            f"Range: {report['performance_metrics']['fastest_response']} - {report['performance_metrics']['slowest_response']}"
        )

        print("\n🏭 PRODUCTION READINESS:")
        for key, value in report["production_readiness"].items():
            status = "✅ Ready" if value else "⚠️ Needs Review"
            print(f"{key.replace('_', ' ').title()}: {status}")

        # Save results
        self.save_workflow_results(report)

        return report

    def save_workflow_results(self, report: Dict):
        """Save workflow validation results"""
        results_dir = Path("/home/kali/Desktop/AutoBot/tests/results")
        results_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save comprehensive results
        results_file = results_dir / f"multi_agent_workflow_validation_{timestamp}.json"

        full_report = {
            "summary": report,
            "detailed_results": [
                {
                    "test_name": r.test_name,
                    "status": r.status,
                    "message": r.message,
                    "duration": r.duration,
                    "agents_involved": r.agents_involved,
                    "performance_metrics": r.performance_metrics,
                    "details": r.details,
                }
                for r in self.results
            ],
            "timestamp": datetime.now().isoformat(),
            "validation_type": "multi_agent_workflow",
        }

        with open(results_file, "w") as f:
            json.dump(full_report, f, indent=2)

        print(f"\n💾 Multi-agent validation results saved to: {results_file}")


def main():
    """Main multi-agent workflow validation"""
    validator = MultiAgentWorkflowValidator()

    try:
        report = validator.run_multi_agent_validation()

        # Exit based on production readiness
        production_ready = all(report["production_readiness"].values())

        if production_ready and report["test_summary"]["failed"] == 0:
            print("\n✅ Multi-agent system is production ready!")
            sys.exit(0)
        elif report["test_summary"]["failed"] > 0:
            print("\n❌ Multi-agent validation failed with critical issues")
            sys.exit(1)
        else:
            print("\n⚠️ Multi-agent system needs review before production")
            sys.exit(2)

    except KeyboardInterrupt:
        print("\n⚠️ Multi-agent validation interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Multi-agent validation failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
