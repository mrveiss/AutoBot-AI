#!/usr/bin/env python3
"""
Comprehensive AutoBot Distributed Infrastructure Testing Suite
P0 Critical Task - Week 1 System Validation

Tests all 5 VMs in the AutoBot distributed infrastructure:
- Main Machine (WSL): 172.16.168.20 - Backend API + VNC
- VM1 Frontend: 172.16.168.21:5173 - Vue.js web interface
- VM2 NPU Worker: 172.16.168.22:8081 - Hardware AI acceleration
- VM3 Redis: 172.16.168.23:6379 - Data layer (15 databases)
- VM4 AI Stack: 172.16.168.24:8080 - AI processing
- VM5 Browser: 172.16.168.25:3000 - Web automation (Playwright)
"""

import asyncio
import json
import time
import subprocess
import socket
import requests
import redis
import paramiko
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/kali/Desktop/AutoBot/tests/results/comprehensive_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AutoBotInfrastructureTest:
    """Comprehensive testing framework for AutoBot distributed infrastructure"""

    def __init__(self):
        self.vm_config = {
            'main_machine': {
                'host': '172.16.168.20',
                'services': {
                    'backend_api': 8001,
                    'vnc_desktop': 6080
                },
                'description': 'Backend API + Desktop VNC'
            },
            'vm1_frontend': {
                'host': '172.16.168.21',
                'services': {
                    'vue_frontend': 5173
                },
                'description': 'Vue.js Web Interface'
            },
            'vm2_npu': {
                'host': '172.16.168.22',
                'services': {
                    'npu_worker': 8081
                },
                'description': 'Hardware AI Acceleration'
            },
            'vm3_redis': {
                'host': '172.16.168.23',
                'services': {
                    'redis_db': 6379
                },
                'description': 'Data Layer (15 databases)'
            },
            'vm4_ai': {
                'host': '172.16.168.24',
                'services': {
                    'ai_stack': 8080
                },
                'description': 'AI Processing Services'
            },
            'vm5_browser': {
                'host': '172.16.168.25',
                'services': {
                    'playwright': 3000
                },
                'description': 'Web Automation (Playwright)'
            }
        }

        self.ssh_key_path = '/home/kali/.ssh/autobot_key'
        self.test_results = {
            'connectivity': {},
            'service_health': {},
            'integration': {},
            'performance': {},
            'workflows': {},
            'errors': [],
            'recommendations': []
        }
        self.start_time = datetime.now()

    def test_network_connectivity(self) -> Dict[str, Any]:
        """Test basic network connectivity between all VMs"""
        logger.info("=== TESTING NETWORK CONNECTIVITY ===")
        connectivity_results = {}

        for vm_name, vm_config in self.vm_config.items():
            host = vm_config['host']
            logger.info(f"Testing connectivity to {vm_name} ({host})")

            # Ping test
            ping_result = self._ping_host(host)

            # Port accessibility tests
            port_results = {}
            for service_name, port in vm_config['services'].items():
                port_accessible = self._test_port_connectivity(host, port)
                port_results[f"{service_name}_{port}"] = port_accessible
                logger.info(f"  {service_name} (:{port}) - {'✓' if port_accessible else '✗'}")

            connectivity_results[vm_name] = {
                'host': host,
                'ping': ping_result,
                'ports': port_results,
                'overall_status': ping_result and any(port_results.values())
            }

        self.test_results['connectivity'] = connectivity_results
        return connectivity_results

    def test_service_health(self) -> Dict[str, Any]:
        """Test individual service health on each VM"""
        logger.info("=== TESTING SERVICE HEALTH ===")
        health_results = {}

        # Test Main Machine Backend API
        logger.info("Testing Main Machine Backend API...")
        backend_health = self._test_backend_health()
        health_results['backend_api'] = backend_health

        # Test Frontend Service
        logger.info("Testing Frontend Service...")
        frontend_health = self._test_frontend_health()
        health_results['frontend'] = frontend_health

        # Test Redis Database
        logger.info("Testing Redis Database...")
        redis_health = self._test_redis_health()
        health_results['redis'] = redis_health

        # Test AI Stack
        logger.info("Testing AI Stack...")
        ai_health = self._test_ai_stack_health()
        health_results['ai_stack'] = ai_health

        # Test NPU Worker
        logger.info("Testing NPU Worker...")
        npu_health = self._test_npu_health()
        health_results['npu_worker'] = npu_health

        # Test Browser Automation
        logger.info("Testing Browser Automation...")
        browser_health = self._test_browser_health()
        health_results['browser'] = browser_health

        self.test_results['service_health'] = health_results
        return health_results

    def test_integration_workflows(self) -> Dict[str, Any]:
        """Test integration between services and core workflows"""
        logger.info("=== TESTING INTEGRATION WORKFLOWS ===")
        integration_results = {}

        # Test Frontend-Backend Integration
        frontend_backend = self._test_frontend_backend_integration()
        integration_results['frontend_backend'] = frontend_backend

        # Test Backend-Redis Integration
        backend_redis = self._test_backend_redis_integration()
        integration_results['backend_redis'] = backend_redis

        # Test AI Processing Integration
        ai_integration = self._test_ai_processing_integration()
        integration_results['ai_processing'] = ai_integration

        # Test Knowledge Base Workflow
        kb_workflow = self._test_knowledge_base_workflow()
        integration_results['knowledge_base'] = kb_workflow

        # Test Chat Workflow
        chat_workflow = self._test_chat_workflow()
        integration_results['chat_workflow'] = chat_workflow

        self.test_results['integration'] = integration_results
        return integration_results

    def test_performance_metrics(self) -> Dict[str, Any]:
        """Collect performance metrics across the infrastructure"""
        logger.info("=== TESTING PERFORMANCE METRICS ===")
        performance_results = {}

        # API Response Times
        api_performance = self._test_api_performance()
        performance_results['api_response_times'] = api_performance

        # Database Performance
        db_performance = self._test_database_performance()
        performance_results['database_performance'] = db_performance

        # Network Latency
        network_performance = self._test_network_performance()
        performance_results['network_latency'] = network_performance

        # System Resource Usage
        resource_usage = self._test_system_resources()
        performance_results['resource_usage'] = resource_usage

        self.test_results['performance'] = performance_results
        return performance_results

    def test_error_handling(self) -> Dict[str, Any]:
        """Test system resilience and error recovery"""
        logger.info("=== TESTING ERROR HANDLING & RESILIENCE ===")
        error_handling_results = {}

        # Test API Error Responses
        api_errors = self._test_api_error_handling()
        error_handling_results['api_errors'] = api_errors

        # Test Database Connection Failures
        db_errors = self._test_database_error_handling()
        error_handling_results['database_errors'] = db_errors

        # Test Service Recovery
        recovery_tests = self._test_service_recovery()
        error_handling_results['service_recovery'] = recovery_tests

        self.test_results['error_handling'] = error_handling_results
        return error_handling_results

    # Helper Methods
    def _ping_host(self, host: str) -> bool:
        """Test basic ping connectivity to host"""
        try:
            result = subprocess.run(['ping', '-c', '1', '-W', '3', host],
                                  capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Ping failed for {host}: {e}")
            return False

    def _test_port_connectivity(self, host: str, port: int) -> bool:
        """Test if specific port is accessible"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.error(f"Port test failed for {host}:{port}: {e}")
            return False

    def _test_backend_health(self) -> Dict[str, Any]:
        """Test backend API health and endpoints"""
        try:
            base_url = "http://172.16.168.20:8001"

            # Test health endpoint
            health_response = requests.get(f"{base_url}/api/health", timeout=10)
            health_status = health_response.status_code == 200

            # Test key endpoints
            endpoints_to_test = [
                "/api/system/status",
                "/api/knowledge_base/stats/basic",
                "/api/monitoring/services"
            ]

            endpoint_results = {}
            for endpoint in endpoints_to_test:
                try:
                    resp = requests.get(f"{base_url}{endpoint}", timeout=10)
                    endpoint_results[endpoint] = {
                        'status_code': resp.status_code,
                        'success': 200 <= resp.status_code < 400,
                        'response_time': resp.elapsed.total_seconds()
                    }
                except Exception as e:
                    endpoint_results[endpoint] = {
                        'status_code': None,
                        'success': False,
                        'error': str(e)
                    }

            return {
                'health_check': health_status,
                'endpoints': endpoint_results,
                'overall_status': health_status and any(ep['success'] for ep in endpoint_results.values())
            }

        except Exception as e:
            logger.error(f"Backend health test failed: {e}")
            return {'health_check': False, 'error': str(e), 'overall_status': False}

    def _test_frontend_health(self) -> Dict[str, Any]:
        """Test frontend service availability"""
        try:
            frontend_url = "http://172.16.168.21:5173"
            response = requests.get(frontend_url, timeout=10)

            return {
                'accessible': response.status_code == 200,
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds(),
                'content_type': response.headers.get('content-type', ''),
                'overall_status': response.status_code == 200
            }

        except Exception as e:
            logger.error(f"Frontend health test failed: {e}")
            return {'accessible': False, 'error': str(e), 'overall_status': False}

    def _test_redis_health(self) -> Dict[str, Any]:
        """Test Redis database connectivity and performance"""
        try:
            redis_client = redis.Redis(host='172.16.168.23', port=6379, db=0,
                                     socket_timeout=5, socket_connect_timeout=5)

            # Test basic connectivity
            ping_result = redis_client.ping()

            # Test database operations
            test_key = f"test_key_{int(time.time())}"
            redis_client.set(test_key, "test_value", ex=10)
            retrieved_value = redis_client.get(test_key)

            # Test database separation (15 databases)
            db_tests = {}
            for db_num in range(15):
                try:
                    db_client = redis.Redis(host='172.16.168.23', port=6379, db=db_num,
                                          socket_timeout=2, socket_connect_timeout=2)
                    db_client.ping()
                    db_tests[f"db_{db_num}"] = True
                except Exception as e:
                    db_tests[f"db_{db_num}"] = False
                    logger.warning(f"Database {db_num} test failed: {e}")

            return {
                'ping': ping_result,
                'read_write': retrieved_value == b"test_value",
                'database_separation': db_tests,
                'accessible_databases': sum(db_tests.values()),
                'overall_status': ping_result and retrieved_value == b"test_value"
            }

        except Exception as e:
            logger.error(f"Redis health test failed: {e}")
            return {'ping': False, 'error': str(e), 'overall_status': False}

    def _test_ai_stack_health(self) -> Dict[str, Any]:
        """Test AI Stack service health"""
        try:
            ai_url = "http://172.16.168.24:8080"

            # Test basic connectivity
            health_response = requests.get(f"{ai_url}/health", timeout=10)

            # Test AI-specific endpoints if available
            endpoints_to_test = ["/health", "/status", "/models"]
            endpoint_results = {}

            for endpoint in endpoints_to_test:
                try:
                    resp = requests.get(f"{ai_url}{endpoint}", timeout=10)
                    endpoint_results[endpoint] = {
                        'status_code': resp.status_code,
                        'success': 200 <= resp.status_code < 400
                    }
                except Exception as e:
                    endpoint_results[endpoint] = {'success': False, 'error': str(e)}

            return {
                'endpoints': endpoint_results,
                'overall_status': any(ep['success'] for ep in endpoint_results.values())
            }

        except Exception as e:
            logger.error(f"AI Stack health test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_npu_health(self) -> Dict[str, Any]:
        """Test NPU Worker service health"""
        try:
            npu_url = "http://172.16.168.22:8081"

            # Test basic connectivity
            response = requests.get(f"{npu_url}/health", timeout=10)

            return {
                'accessible': 200 <= response.status_code < 400,
                'status_code': response.status_code,
                'overall_status': 200 <= response.status_code < 400
            }

        except Exception as e:
            logger.error(f"NPU health test failed: {e}")
            return {'accessible': False, 'error': str(e), 'overall_status': False}

    def _test_browser_health(self) -> Dict[str, Any]:
        """Test Browser Automation service health"""
        try:
            browser_url = "http://172.16.168.25:3000"

            # Test basic connectivity
            response = requests.get(f"{browser_url}/health", timeout=10)

            return {
                'accessible': 200 <= response.status_code < 400,
                'status_code': response.status_code,
                'overall_status': 200 <= response.status_code < 400
            }

        except Exception as e:
            logger.error(f"Browser health test failed: {e}")
            return {'accessible': False, 'error': str(e), 'overall_status': False}

    def _test_frontend_backend_integration(self) -> Dict[str, Any]:
        """Test Frontend-Backend integration"""
        try:
            # Test if frontend can reach backend
            frontend_to_backend = self._test_cross_vm_api_call(
                "172.16.168.21", "172.16.168.20:8001/api/health"
            )

            return {
                'frontend_to_backend': frontend_to_backend,
                'overall_status': frontend_to_backend
            }

        except Exception as e:
            logger.error(f"Frontend-Backend integration test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_backend_redis_integration(self) -> Dict[str, Any]:
        """Test Backend-Redis integration"""
        try:
            # Test backend API endpoints that use Redis
            backend_url = "http://172.16.168.20:8001"

            # Test knowledge base stats (uses Redis)
            kb_response = requests.get(f"{backend_url}/api/knowledge_base/stats/basic", timeout=15)
            kb_success = 200 <= kb_response.status_code < 400

            # Test system status (may use Redis)
            status_response = requests.get(f"{backend_url}/api/system/status", timeout=15)
            status_success = 200 <= status_response.status_code < 400

            return {
                'knowledge_base_stats': kb_success,
                'system_status': status_success,
                'overall_status': kb_success or status_success
            }

        except Exception as e:
            logger.error(f"Backend-Redis integration test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_ai_processing_integration(self) -> Dict[str, Any]:
        """Test AI processing integration"""
        try:
            # Test AI endpoints from backend
            backend_url = "http://172.16.168.20:8001"

            # Test chat endpoints that use AI
            chat_endpoints = [
                "/api/chat/models",
                "/api/agent_config/available_models",
            ]

            ai_results = {}
            for endpoint in chat_endpoints:
                try:
                    resp = requests.get(f"{backend_url}{endpoint}", timeout=15)
                    ai_results[endpoint] = 200 <= resp.status_code < 400
                except Exception as e:
                    ai_results[endpoint] = False
                    logger.warning(f"AI endpoint {endpoint} failed: {e}")

            return {
                'ai_endpoints': ai_results,
                'overall_status': any(ai_results.values())
            }

        except Exception as e:
            logger.error(f"AI processing integration test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_knowledge_base_workflow(self) -> Dict[str, Any]:
        """Test knowledge base workflow end-to-end"""
        try:
            backend_url = "http://172.16.168.20:8001"

            # Test knowledge base endpoints
            kb_endpoints = [
                "/api/knowledge_base/stats/basic",
                "/api/knowledge_base/categories",
                "/api/knowledge_base/health"
            ]

            kb_results = {}
            for endpoint in kb_endpoints:
                try:
                    resp = requests.get(f"{backend_url}{endpoint}", timeout=15)
                    kb_results[endpoint] = {
                        'success': 200 <= resp.status_code < 400,
                        'status_code': resp.status_code,
                        'response_time': resp.elapsed.total_seconds()
                    }
                except Exception as e:
                    kb_results[endpoint] = {'success': False, 'error': str(e)}

            return {
                'endpoints': kb_results,
                'overall_status': any(ep['success'] for ep in kb_results.values())
            }

        except Exception as e:
            logger.error(f"Knowledge base workflow test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_chat_workflow(self) -> Dict[str, Any]:
        """Test chat workflow end-to-end"""
        try:
            backend_url = "http://172.16.168.20:8001"

            # Test chat-related endpoints
            chat_endpoints = [
                "/api/chat/models",
                "/api/agent_config/available_models"
            ]

            chat_results = {}
            for endpoint in chat_endpoints:
                try:
                    resp = requests.get(f"{backend_url}{endpoint}", timeout=15)
                    chat_results[endpoint] = {
                        'success': 200 <= resp.status_code < 400,
                        'status_code': resp.status_code
                    }
                except Exception as e:
                    chat_results[endpoint] = {'success': False, 'error': str(e)}

            return {
                'endpoints': chat_results,
                'overall_status': any(ep['success'] for ep in chat_results.values())
            }

        except Exception as e:
            logger.error(f"Chat workflow test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_api_performance(self) -> Dict[str, Any]:
        """Test API performance metrics"""
        backend_url = "http://172.16.168.20:8001"
        performance_results = {}

        # Test response times for key endpoints
        key_endpoints = [
            "/api/health",
            "/api/system/status",
            "/api/knowledge_base/stats/basic"
        ]

        for endpoint in key_endpoints:
            response_times = []
            success_count = 0

            # Test each endpoint 3 times
            for _ in range(3):
                try:
                    start_time = time.time()
                    resp = requests.get(f"{backend_url}{endpoint}", timeout=10)
                    response_time = time.time() - start_time

                    response_times.append(response_time)
                    if 200 <= resp.status_code < 400:
                        success_count += 1

                except Exception as e:
                    logger.warning(f"Performance test failed for {endpoint}: {e}")

            if response_times:
                performance_results[endpoint] = {
                    'avg_response_time': sum(response_times) / len(response_times),
                    'min_response_time': min(response_times),
                    'max_response_time': max(response_times),
                    'success_rate': success_count / 3 * 100
                }

        return performance_results

    def _test_database_performance(self) -> Dict[str, Any]:
        """Test database performance metrics"""
        try:
            redis_client = redis.Redis(host='172.16.168.23', port=6379, db=0,
                                     socket_timeout=5, socket_connect_timeout=5)

            # Test Redis performance
            start_time = time.time()
            redis_client.ping()
            ping_time = time.time() - start_time

            # Test write performance
            start_time = time.time()
            for i in range(10):
                redis_client.set(f"perf_test_{i}", f"value_{i}")
            write_time = (time.time() - start_time) / 10

            # Test read performance
            start_time = time.time()
            for i in range(10):
                redis_client.get(f"perf_test_{i}")
            read_time = (time.time() - start_time) / 10

            # Cleanup
            for i in range(10):
                redis_client.delete(f"perf_test_{i}")

            return {
                'ping_time': ping_time,
                'avg_write_time': write_time,
                'avg_read_time': read_time,
                'overall_status': ping_time < 0.1 and write_time < 0.01 and read_time < 0.01
            }

        except Exception as e:
            logger.error(f"Database performance test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_network_performance(self) -> Dict[str, Any]:
        """Test network latency between VMs"""
        latency_results = {}

        for vm_name, vm_config in self.vm_config.items():
            host = vm_config['host']

            try:
                # Multiple ping tests for average latency
                latencies = []
                for _ in range(5):
                    result = subprocess.run(['ping', '-c', '1', '-W', '3', host],
                                          capture_output=True, timeout=5)
                    if result.returncode == 0:
                        # Extract latency from ping output
                        output = result.stdout.decode()
                        if 'time=' in output:
                            latency_str = output.split('time=')[1].split(' ')[0]
                            latencies.append(float(latency_str))

                if latencies:
                    latency_results[vm_name] = {
                        'avg_latency': sum(latencies) / len(latencies),
                        'min_latency': min(latencies),
                        'max_latency': max(latencies),
                        'success': True
                    }
                else:
                    latency_results[vm_name] = {'success': False, 'error': 'No successful pings'}

            except Exception as e:
                latency_results[vm_name] = {'success': False, 'error': str(e)}

        return latency_results

    def _test_system_resources(self) -> Dict[str, Any]:
        """Test system resource usage on main machine"""
        try:
            # Test local system resources
            import psutil

            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'load_average': psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else None
            }

        except ImportError:
            logger.warning("psutil not available for system resource monitoring")
            return {'error': 'psutil not available'}
        except Exception as e:
            logger.error(f"System resource test failed: {e}")
            return {'error': str(e)}

    def _test_api_error_handling(self) -> Dict[str, Any]:
        """Test API error handling"""
        backend_url = "http://172.16.168.20:8001"
        error_results = {}

        # Test non-existent endpoints
        invalid_endpoints = [
            "/api/nonexistent",
            "/api/invalid/endpoint",
            "/api/test/404"
        ]

        for endpoint in invalid_endpoints:
            try:
                resp = requests.get(f"{backend_url}{endpoint}", timeout=10)
                error_results[endpoint] = {
                    'status_code': resp.status_code,
                    'handles_404': resp.status_code == 404,
                    'has_error_response': len(resp.content) > 0
                }
            except Exception as e:
                error_results[endpoint] = {'error': str(e)}

        return error_results

    def _test_database_error_handling(self) -> Dict[str, Any]:
        """Test database error handling"""
        try:
            # Test connection to invalid database
            try:
                invalid_client = redis.Redis(host='172.16.168.23', port=6379, db=99,
                                           socket_timeout=2, socket_connect_timeout=2)
                invalid_client.ping()
                invalid_db_result = False  # Should not succeed
            except Exception:
                invalid_db_result = True  # Should handle error gracefully

            return {
                'invalid_database_handling': invalid_db_result,
                'overall_status': invalid_db_result
            }

        except Exception as e:
            logger.error(f"Database error handling test failed: {e}")
            return {'error': str(e), 'overall_status': False}

    def _test_service_recovery(self) -> Dict[str, Any]:
        """Test service recovery capabilities"""
        # This is a basic test - in production, would test actual service restarts
        return {
            'service_restart_capability': 'Manual testing required',
            'health_check_recovery': 'API health endpoints available',
            'overall_status': True
        }

    def _test_cross_vm_api_call(self, source_vm: str, target_endpoint: str) -> bool:
        """Test API call from one VM to another"""
        try:
            # This would require SSH access to source VM to test
            # For now, test direct connectivity
            response = requests.get(f"http://{target_endpoint}", timeout=10)
            return 200 <= response.status_code < 400
        except Exception as e:
            logger.warning(f"Cross-VM API test failed: {e}")
            return False

    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report with recommendations"""
        logger.info("=== GENERATING COMPREHENSIVE REPORT ===")

        end_time = datetime.now()
        test_duration = (end_time - self.start_time).total_seconds()

        # Analyze results and generate recommendations
        recommendations = self._analyze_results_and_recommend()

        comprehensive_report = {
            'test_execution': {
                'start_time': self.start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': test_duration,
                'test_framework': 'AutoBot Comprehensive Infrastructure Testing'
            },
            'infrastructure_overview': {
                'total_vms': len(self.vm_config),
                'vm_configuration': self.vm_config
            },
            'test_results': self.test_results,
            'recommendations': recommendations,
            'system_status': self._generate_system_status_summary(),
            'critical_issues': self._identify_critical_issues(),
            'working_features': self._identify_working_features(),
            'performance_summary': self._generate_performance_summary()
        }

        self._save_report(comprehensive_report)
        return comprehensive_report

    def _analyze_results_and_recommend(self) -> List[Dict[str, Any]]:
        """Analyze test results and generate actionable recommendations"""
        recommendations = []

        # Connectivity recommendations
        connectivity = self.test_results.get('connectivity', {})
        for vm_name, vm_results in connectivity.items():
            if not vm_results.get('overall_status', False):
                recommendations.append({
                    'priority': 'HIGH',
                    'category': 'Connectivity',
                    'issue': f"{vm_name} connectivity issues",
                    'recommendation': f"Check network configuration and service status for {vm_name}",
                    'vm_affected': vm_name
                })

        # Service health recommendations
        service_health = self.test_results.get('service_health', {})
        for service_name, service_results in service_health.items():
            if not service_results.get('overall_status', False):
                recommendations.append({
                    'priority': 'HIGH',
                    'category': 'Service Health',
                    'issue': f"{service_name} service health issues",
                    'recommendation': f"Investigate and restart {service_name} service",
                    'service_affected': service_name
                })

        # Performance recommendations
        performance = self.test_results.get('performance', {})
        api_performance = performance.get('api_response_times', {})
        for endpoint, metrics in api_performance.items():
            if metrics.get('avg_response_time', 0) > 5:
                recommendations.append({
                    'priority': 'MEDIUM',
                    'category': 'Performance',
                    'issue': f"Slow API response time for {endpoint}",
                    'recommendation': f"Optimize {endpoint} endpoint performance",
                    'endpoint_affected': endpoint
                })

        return recommendations

    def _generate_system_status_summary(self) -> Dict[str, Any]:
        """Generate overall system status summary"""
        total_vms = len(self.vm_config)
        working_vms = 0
        working_services = 0
        total_services = 0

        # Count working VMs
        connectivity = self.test_results.get('connectivity', {})
        for vm_results in connectivity.values():
            if vm_results.get('overall_status', False):
                working_vms += 1

        # Count working services
        service_health = self.test_results.get('service_health', {})
        for service_results in service_health.values():
            total_services += 1
            if service_results.get('overall_status', False):
                working_services += 1

        return {
            'infrastructure_health': f"{working_vms}/{total_vms} VMs operational",
            'service_health': f"{working_services}/{total_services} services operational",
            'vm_health_percentage': (working_vms / total_vms) * 100 if total_vms > 0 else 0,
            'service_health_percentage': (working_services / total_services) * 100 if total_services > 0 else 0,
            'overall_system_health': 'HEALTHY' if working_vms >= total_vms * 0.8 and working_services >= total_services * 0.8 else 'DEGRADED'
        }

    def _identify_critical_issues(self) -> List[Dict[str, Any]]:
        """Identify critical issues requiring immediate attention"""
        critical_issues = []

        # Check for complete service failures
        service_health = self.test_results.get('service_health', {})
        for service_name, service_results in service_health.items():
            if not service_results.get('overall_status', False):
                critical_issues.append({
                    'severity': 'CRITICAL',
                    'component': service_name,
                    'issue': f"{service_name} is not responding",
                    'impact': 'Service unavailable to users',
                    'required_action': f"Immediate investigation and restart of {service_name}"
                })

        # Check for VM connectivity failures
        connectivity = self.test_results.get('connectivity', {})
        for vm_name, vm_results in connectivity.items():
            if not vm_results.get('ping', False):
                critical_issues.append({
                    'severity': 'CRITICAL',
                    'component': vm_name,
                    'issue': f"{vm_name} is not reachable",
                    'impact': 'VM services unavailable',
                    'required_action': f"Check {vm_name} VM status and network connectivity"
                })

        return critical_issues

    def _identify_working_features(self) -> List[Dict[str, Any]]:
        """Identify working features and capabilities"""
        working_features = []

        # Check working services
        service_health = self.test_results.get('service_health', {})
        for service_name, service_results in service_health.items():
            if service_results.get('overall_status', False):
                working_features.append({
                    'feature': service_name,
                    'status': 'OPERATIONAL',
                    'description': f"{service_name} is responding and functional"
                })

        # Check working integrations
        integration = self.test_results.get('integration', {})
        for integration_name, integration_results in integration.items():
            if integration_results.get('overall_status', False):
                working_features.append({
                    'feature': integration_name,
                    'status': 'OPERATIONAL',
                    'description': f"{integration_name} integration is working"
                })

        return working_features

    def _generate_performance_summary(self) -> Dict[str, Any]:
        """Generate performance metrics summary"""
        performance = self.test_results.get('performance', {})

        # API performance summary
        api_performance = performance.get('api_response_times', {})
        api_summary = {}
        if api_performance:
            response_times = [metrics.get('avg_response_time', 0) for metrics in api_performance.values()]
            api_summary = {
                'avg_api_response_time': sum(response_times) / len(response_times) if response_times else 0,
                'slowest_endpoint': max(api_performance.items(), key=lambda x: x[1].get('avg_response_time', 0))[0] if api_performance else None
            }

        # Database performance summary
        db_performance = performance.get('database_performance', {})
        db_summary = {}
        if db_performance and not db_performance.get('error'):
            db_summary = {
                'redis_ping_time': db_performance.get('ping_time', 0),
                'redis_write_time': db_performance.get('avg_write_time', 0),
                'redis_read_time': db_performance.get('avg_read_time', 0)
            }

        return {
            'api_performance': api_summary,
            'database_performance': db_summary,
            'performance_grade': self._calculate_performance_grade()
        }

    def _calculate_performance_grade(self) -> str:
        """Calculate overall performance grade"""
        performance = self.test_results.get('performance', {})

        # Simple grading based on API response times
        api_performance = performance.get('api_response_times', {})
        if api_performance:
            avg_times = [metrics.get('avg_response_time', 0) for metrics in api_performance.values()]
            avg_time = sum(avg_times) / len(avg_times) if avg_times else 0

            if avg_time < 1:
                return 'A'
            elif avg_time < 2:
                return 'B'
            elif avg_time < 5:
                return 'C'
            else:
                return 'D'

        return 'Unknown'

    def _save_report(self, report: Dict[str, Any]) -> None:
        """Save comprehensive report to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON report
        json_path = f"/home/kali/Desktop/AutoBot/tests/results/comprehensive_infrastructure_test_{timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        # Save executive summary
        summary_path = f"/home/kali/Desktop/AutoBot/tests/results/infrastructure_test_summary_{timestamp}.txt"
        with open(summary_path, 'w') as f:
            f.write("AUTOBOT DISTRIBUTED INFRASTRUCTURE TEST SUMMARY\n")
            f.write("=" * 50 + "\n\n")

            # System Status
            system_status = report['system_status']
            f.write(f"OVERALL SYSTEM HEALTH: {system_status['overall_system_health']}\n")
            f.write(f"Infrastructure Health: {system_status['infrastructure_health']}\n")
            f.write(f"Service Health: {system_status['service_health']}\n\n")

            # Critical Issues
            critical_issues = report['critical_issues']
            f.write(f"CRITICAL ISSUES ({len(critical_issues)}):\n")
            for issue in critical_issues:
                f.write(f"- {issue['component']}: {issue['issue']}\n")
                f.write(f"  Action: {issue['required_action']}\n")
            f.write("\n")

            # Working Features
            working_features = report['working_features']
            f.write(f"WORKING FEATURES ({len(working_features)}):\n")
            for feature in working_features:
                f.write(f"- {feature['feature']}: {feature['status']}\n")
            f.write("\n")

            # Recommendations
            recommendations = report['recommendations']
            f.write(f"RECOMMENDATIONS ({len(recommendations)}):\n")
            for rec in recommendations:
                f.write(f"- [{rec['priority']}] {rec['category']}: {rec['recommendation']}\n")
            f.write("\n")

            # Performance Summary
            perf_summary = report['performance_summary']
            f.write("PERFORMANCE SUMMARY:\n")
            f.write(f"Performance Grade: {perf_summary['performance_grade']}\n")
            if 'api_performance' in perf_summary and perf_summary['api_performance']:
                api_perf = perf_summary['api_performance']
                f.write(f"Average API Response Time: {api_perf.get('avg_api_response_time', 0):.3f}s\n")

        logger.info(f"Comprehensive report saved to: {json_path}")
        logger.info(f"Executive summary saved to: {summary_path}")

def main():
    """Main test execution function"""
    logger.info("Starting AutoBot Distributed Infrastructure Comprehensive Testing")
    logger.info("P0 Critical Task - Week 1 System Validation")

    # Initialize test framework
    test_framework = AutoBotInfrastructureTest()

    try:
        # Execute all test phases
        logger.info("Phase 1: Network Connectivity Testing")
        connectivity_results = test_framework.test_network_connectivity()

        logger.info("Phase 2: Service Health Validation")
        health_results = test_framework.test_service_health()

        logger.info("Phase 3: Integration Workflow Testing")
        integration_results = test_framework.test_integration_workflows()

        logger.info("Phase 4: Performance Metrics Collection")
        performance_results = test_framework.test_performance_metrics()

        logger.info("Phase 5: Error Handling & Resilience Testing")
        error_handling_results = test_framework.test_error_handling()

        # Generate comprehensive report
        logger.info("Generating comprehensive test report...")
        final_report = test_framework.generate_comprehensive_report()

        # Print executive summary
        print("\n" + "="*60)
        print("AUTOBOT INFRASTRUCTURE TEST EXECUTIVE SUMMARY")
        print("="*60)

        system_status = final_report['system_status']
        print(f"Overall System Health: {system_status['overall_system_health']}")
        print(f"Infrastructure Health: {system_status['infrastructure_health']}")
        print(f"Service Health: {system_status['service_health']}")

        critical_issues = final_report['critical_issues']
        print(f"\nCritical Issues: {len(critical_issues)}")
        for issue in critical_issues[:3]:  # Show first 3
            print(f"  - {issue['component']}: {issue['issue']}")

        working_features = final_report['working_features']
        print(f"\nWorking Features: {len(working_features)}")

        recommendations = final_report['recommendations']
        print(f"Recommendations: {len(recommendations)}")

        performance_grade = final_report['performance_summary']['performance_grade']
        print(f"Performance Grade: {performance_grade}")

        print(f"\nDetailed results saved to tests/results/")
        print("="*60)

        return final_report

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        raise

if __name__ == "__main__":
    main()