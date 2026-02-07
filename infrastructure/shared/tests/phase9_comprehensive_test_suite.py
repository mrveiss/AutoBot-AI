#!/usr/bin/env python3
"""
AutoBot Phase 9 Comprehensive Testing Suite
===========================================

This comprehensive test suite validates all Phase 9 features including:
1. Multi-Agent Coordination System
2. ConsolidatedChatWorkflow with hot reload
3. Distributed VM Architecture (172.16.168.20-25)
4. Knowledge Base Integration (13,383 vectors)
5. Ollama LLM Integration with NPU acceleration
6. Frontend-Backend Integration (Vue 3 + FastAPI)
7. VNC Desktop Environment (KeX integration)
8. Redis Database Architecture (11-database structure)
9. Performance Optimizations (GPU acceleration)
10. Multi-Modal Processing capabilities

Usage:
    python tests/phase9_comprehensive_test_suite.py [--verbose] [--performance] [--integration]
"""

import argparse
import asyncio
import concurrent.futures
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add AutoBot paths
sys.path.append("/home/kali/Desktop/AutoBot")


@dataclass
class TestResult:
    """Individual test result"""

    test_name: str
    category: str
    status: str  # "PASS", "FAIL", "WARNING", "SKIP"
    message: str
    duration: float
    details: Dict = field(default_factory=dict)
    performance_metrics: Dict = field(default_factory=dict)
    error_info: Optional[str] = None


@dataclass
class TestSuiteConfig:
    """Test suite configuration"""

    backend_host: str = "172.16.168.20"
    backend_port: int = 8001
    frontend_host: str = "172.16.168.21"
    frontend_port: int = 5173
    redis_host: str = "172.16.168.23"
    redis_port: int = 6379
    ai_stack_host: str = "172.16.168.24"
    ai_stack_port: int = 8080
    npu_worker_host: str = "172.16.168.22"
    npu_worker_port: int = 8081
    browser_host: str = "172.16.168.25"
    browser_port: int = 3000
    vnc_host: str = "localhost"
    vnc_port: int = 6080
    ollama_host: str = "127.0.0.1"
    ollama_port: int = 11434
    timeout: int = 30
    performance_iterations: int = 10


class Phase9TestSuite:
    """Main test suite for AutoBot Phase 9 features"""

    def __init__(self, config: TestSuiteConfig = None):
        self.config = config or TestSuiteConfig()
        self.results: List[TestResult] = []
        self.start_time = time.time()
        self.session = requests.Session()
        self.session.timeout = self.config.timeout

        # Create results directory
        self.results_dir = Path("/home/kali/Desktop/AutoBot/tests/results")
        self.results_dir.mkdir(exist_ok=True)

        # Test execution timestamp
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def log_result(
        self,
        test_name: str,
        category: str,
        status: str,
        message: str,
        duration: float = 0,
        details: Dict = None,
        performance_metrics: Dict = None,
        error_info: str = None,
    ):
        """Log test result"""
        result = TestResult(
            test_name=test_name,
            category=category,
            status=status,
            message=message,
            duration=duration,
            details=details or {},
            performance_metrics=performance_metrics or {},
            error_info=error_info,
        )
        self.results.append(result)

        # Log to console
        status_emoji = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️", "SKIP": "⏭️"}
        logger.info(
            f"{status_emoji.get(status, '?')} [{category}] {test_name}: {message}"
        )

        if error_info and status == "FAIL":
            logger.error(f"Error details: {error_info}")

    async def test_distributed_vm_architecture(self):
        """Test 1: Distributed VM Architecture Connectivity"""
        logger.info("🌐 Testing Distributed VM Architecture...")

        services = [
            (
                "Backend API",
                self.config.backend_host,
                self.config.backend_port,
                "/api/health",
            ),
            ("Frontend", self.config.frontend_host, self.config.frontend_port, "/"),
            ("Redis", self.config.redis_host, self.config.redis_port, None),
            (
                "AI Stack",
                self.config.ai_stack_host,
                self.config.ai_stack_port,
                "/health",
            ),
            (
                "NPU Worker",
                self.config.npu_worker_host,
                self.config.npu_worker_port,
                "/health",
            ),
            (
                "Browser Service",
                self.config.browser_host,
                self.config.browser_port,
                "/health",
            ),
        ]

        connectivity_results = {}

        for service_name, host, port, endpoint in services:
            start_time = time.time()
            try:
                if service_name == "Redis":
                    # Test Redis connectivity
                    import redis.asyncio as aioredis

                    client = aioredis.Redis(host=host, port=port, socket_timeout=5)
                    await client.ping()
                    await client.aclose()
                    status = "PASS"
                    message = "Redis connection successful"
                else:
                    # Test HTTP services
                    url = f"http://{host}:{port}{endpoint or ''}"
                    response = self.session.get(url, timeout=10)

                    if response.status_code == 200:
                        status = "PASS"
                        message = f"Service accessible (HTTP {response.status_code})"
                    else:
                        status = "WARNING"
                        message = f"Service responding with HTTP {response.status_code}"

                duration = time.time() - start_time
                connectivity_results[service_name] = {
                    "status": status,
                    "response_time": duration,
                    "details": message,
                }

            except Exception as e:
                duration = time.time() - start_time
                status = "FAIL"
                message = f"Connection failed: {str(e)}"
                connectivity_results[service_name] = {
                    "status": status,
                    "response_time": duration,
                    "error": str(e),
                }

            self.log_result(
                f"VM Connectivity - {service_name}",
                "Infrastructure",
                status,
                message,
                duration,
                details={"host": host, "port": port, "endpoint": endpoint},
            )

        # Overall architecture health
        passing_services = sum(
            1 for r in connectivity_results.values() if r["status"] == "PASS"
        )
        total_services = len(services)

        if passing_services == total_services:
            status = "PASS"
            message = f"All {total_services} services accessible"
        elif passing_services >= total_services * 0.8:
            status = "WARNING"
            message = f"{passing_services}/{total_services} services accessible (80%+ threshold met)"
        else:
            status = "FAIL"
            message = f"Only {passing_services}/{total_services} services accessible"

        self.log_result(
            "Distributed VM Architecture Health",
            "Infrastructure",
            status,
            message,
            details=connectivity_results,
        )

    async def test_backend_api_comprehensive(self):
        """Test 2: Backend API Comprehensive Validation"""
        logger.info("🔧 Testing Backend API Comprehensive...")

        base_url = f"http://{self.config.backend_host}:{self.config.backend_port}"

        # Critical API endpoints to test
        critical_endpoints = [
            ("GET", "/api/health", "Health Check"),
            ("GET", "/api/system/status", "System Status"),
            ("GET", "/api/knowledge_base/stats/basic", "Knowledge Base Stats"),
            ("GET", "/api/monitoring/services", "Service Monitoring"),
            ("GET", "/api/config/status", "Configuration Status"),
            ("GET", "/api/ollama/models", "Ollama Models"),
            ("GET", "/api/redis/status", "Redis Status"),
        ]

        api_results = {}

        for method, endpoint, description in critical_endpoints:
            start_time = time.time()
            try:
                url = f"{base_url}{endpoint}"
                response = self.session.request(method, url, timeout=15)
                duration = time.time() - start_time

                if response.status_code == 200:
                    try:
                        data = response.json()
                        status = "PASS"
                        message = f"{description} successful"
                        details = {
                            "data_keys": list(data.keys())
                            if isinstance(data, dict)
                            else "non-dict"
                        }
                    except json.JSONDecodeError:
                        status = "WARNING"
                        message = f"{description} returned non-JSON response"
                        details = {"content_length": len(response.text)}
                else:
                    status = "FAIL"
                    message = f"{description} failed (HTTP {response.status_code})"
                    details = {"status_code": response.status_code}

                api_results[endpoint] = {
                    "status": status,
                    "response_time": duration,
                    "status_code": response.status_code,
                }

            except Exception as e:
                duration = time.time() - start_time
                status = "FAIL"
                message = f"{description} error: {str(e)}"
                details = {"error": str(e)}
                api_results[endpoint] = {
                    "status": "FAIL",
                    "response_time": duration,
                    "error": str(e),
                }

            self.log_result(
                f"API Endpoint - {description}",
                "Backend API",
                status,
                message,
                duration,
                details=details,
            )

        # Test API performance under load
        await self._test_api_performance(base_url)

    async def _test_api_performance(self, base_url: str):
        """Test API performance under concurrent load"""
        logger.info("⚡ Testing API Performance...")

        async def single_request():
            try:
                start_time = time.time()
                response = self.session.get(f"{base_url}/api/health", timeout=5)
                duration = time.time() - start_time
                return {"success": response.status_code == 200, "duration": duration}
            except Exception as e:
                return {"success": False, "duration": float("inf"), "error": str(e)}

        # Concurrent request test
        concurrent_requests = 20
        [single_request() for _ in range(concurrent_requests)]

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(asyncio.run, single_request())
                for _ in range(concurrent_requests)
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        total_duration = time.time() - start_time

        successful_requests = sum(1 for r in results if r["success"])
        avg_response_time = sum(r["duration"] for r in results if r["success"]) / max(
            successful_requests, 1
        )

        if successful_requests >= concurrent_requests * 0.9:
            status = "PASS"
            message = f"High load performance acceptable ({successful_requests}/{concurrent_requests} successful)"
        elif successful_requests >= concurrent_requests * 0.7:
            status = "WARNING"
            message = f"Moderate performance under load ({successful_requests}/{concurrent_requests} successful)"
        else:
            status = "FAIL"
            message = f"Poor performance under load ({successful_requests}/{concurrent_requests} successful)"

        self.log_result(
            "API Performance Under Load",
            "Performance",
            status,
            message,
            total_duration,
            performance_metrics={
                "concurrent_requests": concurrent_requests,
                "successful_requests": successful_requests,
                "avg_response_time": avg_response_time,
                "total_duration": total_duration,
                "requests_per_second": concurrent_requests / total_duration,
            },
        )

    async def test_consolidated_chat_workflow(self):
        """Test 3: ConsolidatedChatWorkflow System"""
        logger.info("💬 Testing ConsolidatedChatWorkflow...")

        base_url = f"http://{self.config.backend_host}:{self.config.backend_port}"

        # Test chat workflow components
        test_messages = [
            {
                "message": "What is AutoBot?",
                "expected_type": "GENERAL_QUERY",
                "description": "General query about AutoBot",
            },
            {
                "message": "List files in the current directory",
                "expected_type": "TERMINAL_TASK",
                "description": "Terminal command request",
            },
            {
                "message": "How do I configure Redis database?",
                "expected_type": "SYSTEM_TASK",
                "description": "System configuration query",
            },
        ]

        workflow_results = {}

        for i, test_case in enumerate(test_messages):
            start_time = time.time()
            try:
                # Create a test chat session
                chat_response = self.session.post(
                    f"{base_url}/api/chats",
                    json={"title": f"Test Chat {i+1}"},
                    timeout=10,
                )

                if chat_response.status_code != 201:
                    raise Exception(
                        f"Failed to create chat: {chat_response.status_code}"
                    )

                chat_data = chat_response.json()
                chat_id = chat_data["id"]

                # Send message through workflow
                message_response = self.session.post(
                    f"{base_url}/api/chats/{chat_id}/message",
                    json={"message": test_case["message"]},
                    timeout=30,
                )

                duration = time.time() - start_time

                if message_response.status_code == 200:
                    response_data = message_response.json()

                    # Validate response structure
                    required_fields = ["response", "message_type", "processing_time"]
                    missing_fields = [
                        f for f in required_fields if f not in response_data
                    ]

                    if not missing_fields:
                        status = "PASS"
                        message = f"Workflow processed {test_case['description']} successfully"
                        details = {
                            "message_type": response_data.get("message_type"),
                            "processing_time": response_data.get("processing_time"),
                            "response_length": len(response_data.get("response", "")),
                        }
                    else:
                        status = "WARNING"
                        message = f"Response missing fields: {missing_fields}"
                        details = {"missing_fields": missing_fields}
                else:
                    status = "FAIL"
                    message = f"Workflow failed (HTTP {message_response.status_code})"
                    details = {"status_code": message_response.status_code}

                workflow_results[test_case["description"]] = {
                    "status": status,
                    "duration": duration,
                    "details": details,
                }

            except Exception as e:
                duration = time.time() - start_time
                status = "FAIL"
                message = f"Workflow error: {str(e)}"
                workflow_results[test_case["description"]] = {
                    "status": "FAIL",
                    "duration": duration,
                    "error": str(e),
                }

            self.log_result(
                f"Chat Workflow - {test_case['description']}",
                "Chat Workflow",
                status,
                message,
                duration,
                details=workflow_results[test_case["description"]].get("details", {}),
            )

    async def test_knowledge_base_integration(self):
        """Test 4: Knowledge Base Integration (13,383 vectors)"""
        logger.info("📚 Testing Knowledge Base Integration...")

        base_url = f"http://{self.config.backend_host}:{self.config.backend_port}"

        # Test knowledge base statistics
        start_time = time.time()
        try:
            stats_response = self.session.get(
                f"{base_url}/api/knowledge_base/stats/basic", timeout=15
            )
            duration = time.time() - start_time

            if stats_response.status_code == 200:
                stats_data = stats_response.json()

                # Validate knowledge base statistics
                total_documents = stats_data.get("total_documents", 0)
                total_chunks = stats_data.get("total_chunks", 0)

                if total_documents >= 3000:  # Expecting ~3,278 documents
                    status = "PASS"
                    message = f"Knowledge base loaded with {total_documents} documents"
                elif total_documents >= 1000:
                    status = "WARNING"
                    message = (
                        f"Knowledge base partially loaded ({total_documents} documents)"
                    )
                else:
                    status = "FAIL"
                    message = (
                        f"Knowledge base poorly populated ({total_documents} documents)"
                    )

                details = {
                    "total_documents": total_documents,
                    "total_chunks": total_chunks,
                    "expected_documents": 3278,
                }
            else:
                status = "FAIL"
                message = (
                    f"Knowledge base stats failed (HTTP {stats_response.status_code})"
                )
                details = {"status_code": stats_response.status_code}

        except Exception as e:
            duration = time.time() - start_time
            status = "FAIL"
            message = f"Knowledge base stats error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "Knowledge Base Statistics",
            "Knowledge Base",
            status,
            message,
            duration,
            details=details,
        )

        # Test knowledge base search functionality
        await self._test_knowledge_search(base_url)

    async def _test_knowledge_search(self, base_url: str):
        """Test knowledge base search functionality"""
        search_queries = [
            "Redis configuration",
            "Docker setup",
            "AutoBot architecture",
            "Backend API endpoints",
            "Frontend Vue components",
        ]

        for query in search_queries:
            start_time = time.time()
            try:
                search_response = self.session.post(
                    f"{base_url}/api/knowledge_base/search",
                    json={"query": query, "limit": 5},
                    timeout=15,
                )
                duration = time.time() - start_time

                if search_response.status_code == 200:
                    search_data = search_response.json()
                    results = search_data.get("results", [])

                    if len(results) >= 3:
                        status = "PASS"
                        message = f"Search returned {len(results)} relevant results"
                    elif len(results) >= 1:
                        status = "WARNING"
                        message = f"Search returned {len(results)} results (limited)"
                    else:
                        status = "FAIL"
                        message = "Search returned no results"

                    details = {
                        "query": query,
                        "result_count": len(results),
                        "avg_score": sum(r.get("score", 0) for r in results)
                        / max(len(results), 1),
                    }
                else:
                    status = "FAIL"
                    message = f"Search failed (HTTP {search_response.status_code})"
                    details = {
                        "query": query,
                        "status_code": search_response.status_code,
                    }

            except Exception as e:
                duration = time.time() - start_time
                status = "FAIL"
                message = f"Search error: {str(e)}"
                details = {"query": query, "error": str(e)}

            self.log_result(
                f"Knowledge Search - '{query}'",
                "Knowledge Base",
                status,
                message,
                duration,
                details=details,
            )

    async def test_ollama_llm_integration(self):
        """Test 5: Ollama LLM Integration with NPU Acceleration"""
        logger.info("🤖 Testing Ollama LLM Integration...")

        # Test Ollama service connectivity
        ollama_url = f"http://{self.config.ollama_host}:{self.config.ollama_port}"

        start_time = time.time()
        try:
            # Test Ollama health
            health_response = self.session.get(f"{ollama_url}/api/tags", timeout=15)
            duration = time.time() - start_time

            if health_response.status_code == 200:
                models_data = health_response.json()
                available_models = models_data.get("models", [])

                if len(available_models) > 0:
                    status = "PASS"
                    message = f"Ollama accessible with {len(available_models)} models"
                    details = {
                        "model_count": len(available_models),
                        "models": [
                            m.get("name", "unknown") for m in available_models[:5]
                        ],
                    }
                else:
                    status = "WARNING"
                    message = "Ollama accessible but no models loaded"
                    details = {"model_count": 0}
            else:
                status = "FAIL"
                message = (
                    f"Ollama health check failed (HTTP {health_response.status_code})"
                )
                details = {"status_code": health_response.status_code}

        except Exception as e:
            duration = time.time() - start_time
            status = "FAIL"
            message = f"Ollama connectivity error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "Ollama Service Connectivity",
            "LLM Integration",
            status,
            message,
            duration,
            details=details,
        )

        # Test LLM generation through backend API
        await self._test_llm_generation()

    async def _test_llm_generation(self):
        """Test LLM generation through backend API"""
        backend_url = f"http://{self.config.backend_host}:{self.config.backend_port}"

        test_prompts = [
            "What is 2+2?",
            "Explain what AutoBot is in one sentence.",
            "List three common Linux commands.",
        ]

        for prompt in test_prompts:
            start_time = time.time()
            try:
                # Test through backend LLM endpoint
                llm_response = self.session.post(
                    f"{backend_url}/api/llm/generate",
                    json={
                        "prompt": prompt,
                        "model": "llama3.2:1b-instruct-q4_K_M",
                        "max_tokens": 100,
                    },
                    timeout=30,
                )
                duration = time.time() - start_time

                if llm_response.status_code == 200:
                    response_data = llm_response.json()
                    generated_text = response_data.get("response", "")

                    if len(generated_text.strip()) > 10:
                        status = "PASS"
                        message = f"LLM generated {len(generated_text)} characters"
                        performance_metrics = {
                            "response_time": duration,
                            "tokens_per_second": len(generated_text.split()) / duration,
                            "characters_generated": len(generated_text),
                        }
                    else:
                        status = "WARNING"
                        message = "LLM generated very short response"
                        performance_metrics = {"response_time": duration}
                else:
                    status = "FAIL"
                    message = f"LLM generation failed (HTTP {llm_response.status_code})"
                    performance_metrics = {"response_time": duration}

            except Exception as e:
                duration = time.time() - start_time
                status = "FAIL"
                message = f"LLM generation error: {str(e)}"
                performance_metrics = {"response_time": duration}

            self.log_result(
                f"LLM Generation - '{prompt[:30]}...'",
                "LLM Integration",
                status,
                message,
                duration,
                performance_metrics=performance_metrics,
            )

    async def test_frontend_backend_integration(self):
        """Test 6: Frontend-Backend Integration"""
        logger.info("🌐 Testing Frontend-Backend Integration...")

        frontend_url = f"http://{self.config.frontend_host}:{self.config.frontend_port}"
        _backend_url = f"http://{self.config.backend_host}:{self.config.backend_port}"

        # Test frontend accessibility
        start_time = time.time()
        try:
            frontend_response = self.session.get(frontend_url, timeout=15)
            duration = time.time() - start_time

            if frontend_response.status_code == 200:
                status = "PASS"
                message = "Frontend accessible"
                details = {"status_code": frontend_response.status_code}
            else:
                status = "FAIL"
                message = (
                    f"Frontend inaccessible (HTTP {frontend_response.status_code})"
                )
                details = {"status_code": frontend_response.status_code}

        except Exception as e:
            duration = time.time() - start_time
            status = "FAIL"
            message = f"Frontend connectivity error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "Frontend Accessibility",
            "Frontend Integration",
            status,
            message,
            duration,
            details=details,
        )

        # Test WebSocket connectivity
        await self._test_websocket_connection()

    async def _test_websocket_connection(self):
        """Test WebSocket connectivity"""
        ws_url = f"ws://{self.config.backend_host}:{self.config.backend_port}/ws"

        start_time = time.time()
        try:
            async with websockets.connect(ws_url, timeout=10) as websocket:
                # Send test message
                test_message = {"type": "ping", "data": "test"}
                await websocket.send(json.dumps(test_message))

                # Wait for response
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                duration = time.time() - start_time

                if response:
                    status = "PASS"
                    message = "WebSocket connection successful"
                    details = {
                        "response_received": True,
                        "response_length": len(response),
                    }
                else:
                    status = "WARNING"
                    message = "WebSocket connected but no response"
                    details = {"response_received": False}

        except Exception as e:
            duration = time.time() - start_time
            status = "FAIL"
            message = f"WebSocket connection error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "WebSocket Connectivity",
            "Frontend Integration",
            status,
            message,
            duration,
            details=details,
        )

    async def test_vnc_desktop_environment(self):
        """Test 7: VNC Desktop Environment (KeX integration)"""
        logger.info("🖥️ Testing VNC Desktop Environment...")

        vnc_url = f"http://{self.config.vnc_host}:{self.config.vnc_port}"

        start_time = time.time()
        try:
            # Test VNC web interface accessibility
            vnc_response = self.session.get(f"{vnc_url}/vnc.html", timeout=15)
            duration = time.time() - start_time

            if vnc_response.status_code == 200:
                content = vnc_response.text

                # Check for noVNC indicators
                if "noVNC" in content or "vnc" in content.lower():
                    status = "PASS"
                    message = "VNC desktop interface accessible"
                    details = {"has_novnc": "noVNC" in content}
                else:
                    status = "WARNING"
                    message = "VNC accessible but content unclear"
                    details = {"content_length": len(content)}
            else:
                status = "FAIL"
                message = (
                    f"VNC interface inaccessible (HTTP {vnc_response.status_code})"
                )
                details = {"status_code": vnc_response.status_code}

        except Exception as e:
            duration = time.time() - start_time
            status = "FAIL"
            message = f"VNC connectivity error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "VNC Desktop Interface",
            "Desktop Environment",
            status,
            message,
            duration,
            details=details,
        )

        # Test VNC server process
        await self._test_vnc_server_process()

    async def _test_vnc_server_process(self):
        """Test VNC server process status"""
        start_time = time.time()
        try:
            # Check if VNC/KeX processes are running
            result = subprocess.run(
                ["pgrep", "-", "vnc|kex"], capture_output=True, text=True, timeout=5
            )
            duration = time.time() - start_time

            if result.returncode == 0 and result.stdout.strip():
                processes = result.stdout.strip().split("\n")
                status = "PASS"
                message = f"VNC/KeX processes running ({len(processes)} processes)"
                details = {"process_count": len(processes)}
            else:
                status = "WARNING"
                message = "No VNC/KeX processes detected"
                details = {"process_count": 0}

        except Exception as e:
            duration = time.time() - start_time
            status = "FAIL"
            message = f"VNC process check error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "VNC Server Process",
            "Desktop Environment",
            status,
            message,
            duration,
            details=details,
        )

    async def test_redis_database_architecture(self):
        """Test 8: Redis Database Architecture (11-database structure)"""
        logger.info("💾 Testing Redis Database Architecture...")

        try:
            import redis.asyncio as aioredis

            client = aioredis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                socket_timeout=10,
            )

            # Test basic connectivity
            start_time = time.time()
            await client.ping()
            duration = time.time() - start_time

            self.log_result(
                "Redis Basic Connectivity",
                "Database Architecture",
                "PASS",
                "Redis server responding to ping",
                duration,
            )

            # Test database structure
            database_results = {}
            for db_num in range(11):  # Test databases 0-10
                try:
                    db_client = aioredis.Redis(
                        host=self.config.redis_host,
                        port=self.config.redis_port,
                        db=db_num,
                        socket_timeout=5,
                    )

                    # Get database info
                    info = await db_client.info("keyspace")
                    key_count = 0

                    if f"db{db_num}" in info:
                        # Parse key count from info
                        db_info = info[f"db{db_num}"]
                        if "keys" in db_info:
                            key_count = db_info["keys"]

                    database_results[f"db{db_num}"] = {
                        "accessible": True,
                        "key_count": key_count,
                    }

                    await db_client.aclose()

                except Exception as e:
                    database_results[f"db{db_num}"] = {
                        "accessible": False,
                        "error": str(e),
                    }

            # Evaluate database architecture
            accessible_dbs = sum(
                1 for db in database_results.values() if db["accessible"]
            )
            total_keys = sum(
                db.get("key_count", 0)
                for db in database_results.values()
                if db["accessible"]
            )

            if accessible_dbs >= 10:
                status = "PASS"
                message = f"Redis database architecture healthy ({accessible_dbs}/11 databases accessible)"
            elif accessible_dbs >= 8:
                status = "WARNING"
                message = f"Most databases accessible ({accessible_dbs}/11)"
            else:
                status = "FAIL"
                message = f"Limited database access ({accessible_dbs}/11)"

            self.log_result(
                "Redis Database Structure",
                "Database Architecture",
                status,
                message,
                details={
                    "accessible_databases": accessible_dbs,
                    "total_keys": total_keys,
                    "database_details": database_results,
                },
            )

            await client.aclose()

        except Exception as e:
            self.log_result(
                "Redis Database Architecture",
                "Database Architecture",
                "FAIL",
                f"Redis connection error: {str(e)}",
                error_info=str(e),
            )

    async def test_performance_optimizations(self):
        """Test 9: Performance Optimizations (GPU acceleration)"""
        logger.info("⚡ Testing Performance Optimizations...")

        # Test GPU availability
        start_time = time.time()
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.used,memory.total",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            duration = time.time() - start_time

            if result.returncode == 0 and result.stdout.strip():
                gpu_info = result.stdout.strip().split("\n")[0]
                status = "PASS"
                message = f"GPU detected: {gpu_info.split(',')[0].strip()}"
                details = {"gpu_info": gpu_info}
            else:
                status = "WARNING"
                message = "No GPU detected or nvidia-smi unavailable"
                details = {"gpu_available": False}

        except Exception as e:
            duration = time.time() - start_time
            status = "WARNING"
            message = f"GPU detection error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "GPU Acceleration Detection",
            "Performance",
            status,
            message,
            duration,
            details=details,
        )

        # Test NPU worker if available
        await self._test_npu_worker()

    async def _test_npu_worker(self):
        """Test NPU worker service"""
        npu_url = f"http://{self.config.npu_worker_host}:{self.config.npu_worker_port}"

        start_time = time.time()
        try:
            npu_response = self.session.get(f"{npu_url}/health", timeout=10)
            duration = time.time() - start_time

            if npu_response.status_code == 200:
                status = "PASS"
                message = "NPU worker service accessible"
                details = {"status_code": npu_response.status_code}
            else:
                status = "WARNING"
                message = f"NPU worker not accessible (HTTP {npu_response.status_code})"
                details = {"status_code": npu_response.status_code}

        except Exception as e:
            duration = time.time() - start_time
            status = "WARNING"
            message = f"NPU worker connectivity error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "NPU Worker Service",
            "Performance",
            status,
            message,
            duration,
            details=details,
        )

    async def test_multi_modal_processing(self):
        """Test 10: Multi-Modal Processing Capabilities"""
        logger.info("🎭 Testing Multi-Modal Processing...")

        backend_url = f"http://{self.config.backend_host}:{self.config.backend_port}"

        # Test text processing (already covered in chat workflow)
        # Test image processing capability
        start_time = time.time()
        try:
            # Check if multimodal endpoints are available
            multimodal_response = self.session.get(
                f"{backend_url}/api/multimodal/capabilities", timeout=10
            )
            duration = time.time() - start_time

            if multimodal_response.status_code == 200:
                capabilities = multimodal_response.json()

                supported_modalities = capabilities.get("supported_modalities", [])
                if len(supported_modalities) >= 2:
                    status = "PASS"
                    message = f"Multi-modal capabilities available: {', '.join(supported_modalities)}"
                elif len(supported_modalities) == 1:
                    status = "WARNING"
                    message = f"Limited modalities: {', '.join(supported_modalities)}"
                else:
                    status = "FAIL"
                    message = "No multi-modal capabilities detected"

                details = {"supported_modalities": supported_modalities}
            else:
                status = "WARNING"
                message = "Multi-modal capabilities endpoint not available"
                details = {"status_code": multimodal_response.status_code}

        except Exception as e:
            duration = time.time() - start_time
            status = "WARNING"
            message = f"Multi-modal detection error: {str(e)}"
            details = {"error": str(e)}

        self.log_result(
            "Multi-Modal Capabilities",
            "Multi-Modal Processing",
            status,
            message,
            duration,
            details=details,
        )

    async def run_comprehensive_test_suite(
        self, include_performance: bool = False, include_integration: bool = True
    ):
        """Run the complete Phase 9 test suite"""
        logger.info("🚀 Starting AutoBot Phase 9 Comprehensive Test Suite")
        logger.info(f"Test execution timestamp: {self.timestamp}")

        # Test execution order (critical to least critical)
        test_methods = [
            self.test_distributed_vm_architecture,
            self.test_backend_api_comprehensive,
            self.test_redis_database_architecture,
            self.test_ollama_llm_integration,
            self.test_knowledge_base_integration,
            self.test_consolidated_chat_workflow,
            self.test_frontend_backend_integration,
            self.test_vnc_desktop_environment,
            self.test_performance_optimizations,
            self.test_multi_modal_processing,
        ]

        if not include_integration:
            # Skip integration-heavy tests
            test_methods = test_methods[:6]  # Core functionality only

        # Execute tests
        for test_method in test_methods:
            try:
                await test_method()
            except Exception as e:
                logger.error(
                    f"Test method {test_method.__name__} failed with error: {e}"
                )
                self.log_result(
                    test_method.__name__,
                    "Test Framework",
                    "FAIL",
                    f"Test execution error: {str(e)}",
                    error_info=str(e),
                )

        # Generate test report
        await self._generate_test_report()

    async def _generate_test_report(self):
        """Generate comprehensive test report"""
        total_duration = time.time() - self.start_time

        # Calculate summary statistics
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.status == "PASS")
        failed_tests = sum(1 for r in self.results if r.status == "FAIL")
        warning_tests = sum(1 for r in self.results if r.status == "WARNING")
        skipped_tests = sum(1 for r in self.results if r.status == "SKIP")

        # Calculate pass rate
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        # Generate overall status
        if pass_rate >= 90:
            overall_status = "EXCELLENT"
        elif pass_rate >= 80:
            overall_status = "GOOD"
        elif pass_rate >= 70:
            overall_status = "ACCEPTABLE"
        else:
            overall_status = "NEEDS_ATTENTION"

        # Create detailed report
        report = {
            "test_execution": {
                "timestamp": self.timestamp,
                "total_duration": total_duration,
                "autobot_phase": "Phase 9",
                "test_suite_version": "1.0.0",
            },
            "summary": {
                "overall_status": overall_status,
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "warnings": warning_tests,
                "skipped": skipped_tests,
                "pass_rate": pass_rate,
            },
            "test_results": [
                {
                    "test_name": r.test_name,
                    "category": r.category,
                    "status": r.status,
                    "message": r.message,
                    "duration": r.duration,
                    "details": r.details,
                    "performance_metrics": r.performance_metrics,
                    "error_info": r.error_info,
                }
                for r in self.results
            ],
            "category_summary": self._generate_category_summary(),
            "recommendations": self._generate_recommendations(),
        }

        # Save report to file
        report_file = (
            self.results_dir / f"phase9_comprehensive_test_report_{self.timestamp}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        # Save human-readable summary
        summary_file = self.results_dir / f"phase9_test_summary_{self.timestamp}.txt"
        with open(summary_file, "w") as f:
            f.write("AutoBot Phase 9 Comprehensive Test Report\n")
            f.write(f"{'='*50}\n\n")
            f.write(f"Test Execution: {self.timestamp}\n")
            f.write(f"Total Duration: {total_duration:.2f} seconds\n")
            f.write(f"Overall Status: {overall_status}\n\n")
            f.write("Summary:\n")
            f.write(f"  Total Tests: {total_tests}\n")
            f.write(f"  Passed: {passed_tests} ({pass_rate:.1f}%)\n")
            f.write(f"  Failed: {failed_tests}\n")
            f.write(f"  Warnings: {warning_tests}\n")
            f.write(f"  Skipped: {skipped_tests}\n\n")

            # Failed tests details
            if failed_tests > 0:
                f.write("Failed Tests:\n")
                for r in self.results:
                    if r.status == "FAIL":
                        f.write(f"  ❌ {r.test_name}: {r.message}\n")
                f.write("\n")

            # Warning tests details
            if warning_tests > 0:
                f.write("Warning Tests:\n")
                for r in self.results:
                    if r.status == "WARNING":
                        f.write(f"  ⚠️ {r.test_name}: {r.message}\n")
                f.write("\n")

        # Console summary
        logger.info("\n🎯 Test Suite Complete!")
        logger.info(f"Overall Status: {overall_status}")
        logger.info(f"Pass Rate: {pass_rate:.1f}% ({passed_tests}/{total_tests})")
        logger.info(f"Duration: {total_duration:.2f} seconds")
        logger.info(f"Report saved to: {report_file}")
        logger.info(f"Summary saved to: {summary_file}")

    def _generate_category_summary(self) -> Dict:
        """Generate summary by test category"""
        categories = {}
        for result in self.results:
            category = result.category
            if category not in categories:
                categories[category] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "warnings": 0,
                    "skipped": 0,
                }

            categories[category]["total"] += 1
            if result.status == "PASS":
                categories[category]["passed"] += 1
            elif result.status == "FAIL":
                categories[category]["failed"] += 1
            elif result.status == "WARNING":
                categories[category]["warnings"] += 1
            elif result.status == "SKIP":
                categories[category]["skipped"] += 1

        # Calculate pass rates for each category
        for category, stats in categories.items():
            if stats["total"] > 0:
                stats["pass_rate"] = (stats["passed"] / stats["total"]) * 100
            else:
                stats["pass_rate"] = 0

        return categories

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []

        # Check for critical failures
        critical_failures = [
            r
            for r in self.results
            if r.status == "FAIL"
            and r.category in ["Infrastructure", "Backend API", "Database Architecture"]
        ]

        if critical_failures:
            recommendations.append(
                "🚨 CRITICAL: Address infrastructure failures before proceeding with development"
            )

        # Check for performance issues
        performance_warnings = [
            r
            for r in self.results
            if r.status in ["FAIL", "WARNING"] and r.category == "Performance"
        ]

        if performance_warnings:
            recommendations.append(
                "⚡ Consider performance optimization for GPU/NPU acceleration"
            )

        # Check for integration issues
        integration_issues = [
            r
            for r in self.results
            if r.status in ["FAIL", "WARNING"] and "Integration" in r.category
        ]

        if integration_issues:
            recommendations.append(
                "🔗 Review frontend-backend integration and WebSocket connectivity"
            )

        # Check overall health
        pass_rate = (
            sum(1 for r in self.results if r.status == "PASS") / len(self.results)
        ) * 100

        if pass_rate >= 95:
            recommendations.append(
                "✅ System health excellent - ready for production use"
            )
        elif pass_rate >= 85:
            recommendations.append("✅ System health good - minor issues to address")
        elif pass_rate >= 75:
            recommendations.append(
                "⚠️ System health acceptable - address warnings before production"
            )
        else:
            recommendations.append(
                "❌ System health poor - significant issues require immediate attention"
            )

        return recommendations


async def main():
    """Main entry point for test suite"""
    parser = argparse.ArgumentParser(
        description="AutoBot Phase 9 Comprehensive Test Suite"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--performance", action="store_true", help="Include performance tests"
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        default=True,
        help="Include integration tests",
    )
    parser.add_argument("--config", type=str, help="Path to custom test configuration")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load custom configuration if provided
    config = TestSuiteConfig()
    if args.config:
        with open(args.config, "r") as f:
            config_data = json.load(f)
            for key, value in config_data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

    # Create and run test suite
    test_suite = Phase9TestSuite(config)
    await test_suite.run_comprehensive_test_suite(
        include_performance=args.performance, include_integration=args.integration
    )


if __name__ == "__main__":
    asyncio.run(main())
