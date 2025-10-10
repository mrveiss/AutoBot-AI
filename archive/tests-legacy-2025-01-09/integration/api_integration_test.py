#!/usr/bin/env python3
"""
API Integration Test Suite for AutoBot Distributed Infrastructure
Tests API endpoints across all services and cross-service integrations
"""

import asyncio
import aiohttp
import requests
import json
import time
from typing import Dict, List, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class APIIntegrationTest:
    """Test API integrations across AutoBot distributed services"""

    def __init__(self):
        self.services = {
            'backend': {
                'base_url': 'http://172.16.168.20:8001',
                'endpoints': [
                    '/api/health',
                    '/api/system/status',
                    '/api/knowledge_base/stats/basic',
                    '/api/knowledge_base/categories',
                    '/api/knowledge_base/health',
                    '/api/monitoring/services',
                    '/api/chat/models',
                    '/api/agent_config/available_models',
                    '/api/registry/services',
                    '/api/settings/backend'
                ]
            },
            'frontend': {
                'base_url': 'http://172.16.168.21:5173',
                'endpoints': [
                    '/',  # Main app
                    '/api/health'  # If frontend has health endpoint
                ]
            },
            'npu_worker': {
                'base_url': 'http://172.16.168.22:8081',
                'endpoints': [
                    '/health',
                    '/status',
                    '/capabilities'
                ]
            },
            'ai_stack': {
                'base_url': 'http://172.16.168.24:8080',
                'endpoints': [
                    '/health',
                    '/status',
                    '/models',
                    '/api/v1/models'
                ]
            },
            'browser': {
                'base_url': 'http://172.16.168.25:3000',
                'endpoints': [
                    '/health',
                    '/status'
                ]
            }
        }

        self.timeout = 15
        self.test_results = {}

    async def test_individual_apis(self) -> Dict[str, Any]:
        """Test individual API endpoints on each service"""
        logger.info("Testing individual API endpoints...")
        results = {}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            for service_name, service_config in self.services.items():
                logger.info(f"Testing {service_name} API endpoints...")
                service_results = {}

                for endpoint in service_config['endpoints']:
                    url = f"{service_config['base_url']}{endpoint}"
                    endpoint_result = await self._test_endpoint(session, url, endpoint)
                    service_results[endpoint] = endpoint_result

                    status = "✓" if endpoint_result['success'] else "✗"
                    logger.info(f"  {endpoint}: {status} ({endpoint_result.get('status_code', 'N/A')})")

                results[service_name] = {
                    'base_url': service_config['base_url'],
                    'endpoints': service_results,
                    'working_endpoints': sum(1 for ep in service_results.values() if ep['success']),
                    'total_endpoints': len(service_results),
                    'service_health': any(ep['success'] for ep in service_results.values())
                }

        return results

    async def _test_endpoint(self, session: aiohttp.ClientSession, url: str, endpoint: str) -> Dict[str, Any]:
        """Test individual API endpoint"""
        try:
            start_time = time.time()
            async with session.get(url) as response:
                response_time = time.time() - start_time
                content = await response.text()

                return {
                    'success': 200 <= response.status < 400,
                    'status_code': response.status,
                    'response_time': response_time,
                    'content_length': len(content),
                    'content_type': response.headers.get('content-type', ''),
                    'has_content': len(content) > 0
                }

        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'Timeout',
                'response_time': self.timeout
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'response_time': 0
            }

    def test_backend_api_comprehensive(self) -> Dict[str, Any]:
        """Comprehensive test of backend API endpoints"""
        logger.info("Running comprehensive backend API tests...")
        backend_url = self.services['backend']['base_url']
        results = {}

        # Critical endpoint tests
        critical_endpoints = [
            '/api/health',
            '/api/system/status',
            '/api/knowledge_base/stats/basic'
        ]

        for endpoint in critical_endpoints:
            url = f"{backend_url}{endpoint}"
            result = self._test_endpoint_sync(url)
            results[endpoint] = result

            if result['success']:
                logger.info(f"✓ {endpoint} - {result['status_code']} ({result['response_time']:.3f}s)")

                # Additional validation for specific endpoints
                if endpoint == '/api/knowledge_base/stats/basic':
                    self._validate_kb_stats_response(result, url)
                elif endpoint == '/api/system/status':
                    self._validate_system_status_response(result, url)
            else:
                logger.error(f"✗ {endpoint} - {result.get('error', 'Unknown error')}")

        return results

    def _test_endpoint_sync(self, url: str) -> Dict[str, Any]:
        """Synchronous endpoint test"""
        try:
            start_time = time.time()
            response = requests.get(url, timeout=self.timeout)
            response_time = time.time() - start_time

            return {
                'success': 200 <= response.status_code < 400,
                'status_code': response.status_code,
                'response_time': response_time,
                'content_length': len(response.content),
                'content_type': response.headers.get('content-type', ''),
                'response_data': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            }

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Timeout', 'response_time': self.timeout}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Connection Error', 'response_time': 0}
        except Exception as e:
            return {'success': False, 'error': str(e), 'response_time': 0}

    def _validate_kb_stats_response(self, result: Dict[str, Any], url: str) -> None:
        """Validate knowledge base stats response structure"""
        if result['success'] and 'response_data' in result:
            try:
                data = result['response_data']
                expected_keys = ['total_documents', 'total_chunks', 'total_facts']

                for key in expected_keys:
                    if key in data:
                        logger.info(f"    KB {key}: {data[key]}")
                    else:
                        logger.warning(f"    Missing expected key: {key}")

                result['kb_validation'] = {
                    'has_expected_structure': all(key in data for key in expected_keys),
                    'data_present': bool(data.get('total_documents', 0))
                }

            except Exception as e:
                logger.error(f"    KB stats validation failed: {e}")
                result['kb_validation'] = {'has_expected_structure': False, 'error': str(e)}

    def _validate_system_status_response(self, result: Dict[str, Any], url: str) -> None:
        """Validate system status response structure"""
        if result['success'] and 'response_data' in result:
            try:
                data = result['response_data']

                if 'services' in data:
                    logger.info(f"    System services: {list(data['services'].keys())}")

                if 'system' in data:
                    system_info = data['system']
                    logger.info(f"    System metrics available: {list(system_info.keys())}")

                result['system_validation'] = {
                    'has_services': 'services' in data,
                    'has_system_metrics': 'system' in data
                }

            except Exception as e:
                logger.error(f"    System status validation failed: {e}")
                result['system_validation'] = {'has_services': False, 'error': str(e)}

    def test_cross_service_integration(self) -> Dict[str, Any]:
        """Test cross-service integrations"""
        logger.info("Testing cross-service integrations...")
        integration_results = {}

        # Test Frontend -> Backend communication
        frontend_backend = self._test_frontend_backend_integration()
        integration_results['frontend_backend'] = frontend_backend

        # Test Backend -> Redis communication
        backend_redis = self._test_backend_redis_integration()
        integration_results['backend_redis'] = backend_redis

        # Test Backend -> AI Stack communication
        backend_ai = self._test_backend_ai_integration()
        integration_results['backend_ai'] = backend_ai

        # Test Knowledge Base workflow
        kb_workflow = self._test_knowledge_base_workflow()
        integration_results['knowledge_base_workflow'] = kb_workflow

        return integration_results

    def _test_frontend_backend_integration(self) -> Dict[str, Any]:
        """Test frontend to backend API integration"""
        logger.info("Testing Frontend -> Backend integration...")

        # Test if backend APIs are accessible from frontend perspective
        backend_apis = [
            '/api/health',
            '/api/system/status',
            '/api/knowledge_base/stats/basic'
        ]

        backend_url = self.services['backend']['base_url']
        results = {}

        for api in backend_apis:
            url = f"{backend_url}{api}"
            result = self._test_endpoint_sync(url)
            results[api] = result['success']

        integration_health = sum(results.values()) / len(results) if results else 0

        return {
            'api_accessibility': results,
            'integration_health': integration_health,
            'status': 'WORKING' if integration_health >= 0.5 else 'FAILING'
        }

    def _test_backend_redis_integration(self) -> Dict[str, Any]:
        """Test backend to Redis integration"""
        logger.info("Testing Backend -> Redis integration...")

        # Test backend endpoints that depend on Redis
        redis_dependent_endpoints = [
            '/api/knowledge_base/stats/basic',
            '/api/knowledge_base/categories',
            '/api/system/status'
        ]

        backend_url = self.services['backend']['base_url']
        results = {}

        for endpoint in redis_dependent_endpoints:
            url = f"{backend_url}{endpoint}"
            result = self._test_endpoint_sync(url)
            results[endpoint] = {
                'accessible': result['success'],
                'response_time': result.get('response_time', 0),
                'has_data': bool(result.get('response_data')) if result['success'] else False
            }

        # Calculate integration health
        working_endpoints = sum(1 for ep in results.values() if ep['accessible'])
        integration_health = working_endpoints / len(results) if results else 0

        return {
            'endpoint_results': results,
            'integration_health': integration_health,
            'status': 'WORKING' if integration_health >= 0.5 else 'FAILING',
            'avg_response_time': sum(ep['response_time'] for ep in results.values()) / len(results) if results else 0
        }

    def _test_backend_ai_integration(self) -> Dict[str, Any]:
        """Test backend to AI stack integration"""
        logger.info("Testing Backend -> AI Stack integration...")

        # Test AI-related endpoints
        ai_endpoints = [
            '/api/chat/models',
            '/api/agent_config/available_models'
        ]

        backend_url = self.services['backend']['base_url']
        results = {}

        for endpoint in ai_endpoints:
            url = f"{backend_url}{endpoint}"
            result = self._test_endpoint_sync(url)
            results[endpoint] = {
                'accessible': result['success'],
                'response_time': result.get('response_time', 0),
                'has_model_data': self._check_model_data(result.get('response_data'))
            }

        integration_health = sum(1 for ep in results.values() if ep['accessible']) / len(results) if results else 0

        return {
            'endpoint_results': results,
            'integration_health': integration_health,
            'status': 'WORKING' if integration_health >= 0.3 else 'FAILING'  # Lower threshold for AI endpoints
        }

    def _check_model_data(self, response_data: Any) -> bool:
        """Check if response contains model data"""
        if not response_data:
            return False

        if isinstance(response_data, dict):
            # Look for model-related keys
            model_keys = ['models', 'available_models', 'model_list']
            return any(key in response_data for key in model_keys)

        if isinstance(response_data, list):
            return len(response_data) > 0

        return False

    def _test_knowledge_base_workflow(self) -> Dict[str, Any]:
        """Test complete knowledge base workflow"""
        logger.info("Testing Knowledge Base workflow...")

        backend_url = self.services['backend']['base_url']
        workflow_steps = [
            ('/api/knowledge_base/health', 'KB Health Check'),
            ('/api/knowledge_base/stats/basic', 'KB Stats'),
            ('/api/knowledge_base/categories', 'KB Categories')
        ]

        results = {}
        workflow_success = True

        for endpoint, step_name in workflow_steps:
            url = f"{backend_url}{endpoint}"
            result = self._test_endpoint_sync(url)

            step_success = result['success']
            results[step_name] = {
                'endpoint': endpoint,
                'success': step_success,
                'response_time': result.get('response_time', 0),
                'status_code': result.get('status_code')
            }

            if not step_success:
                workflow_success = False

            status = "✓" if step_success else "✗"
            logger.info(f"  {step_name}: {status}")

        return {
            'workflow_steps': results,
            'overall_success': workflow_success,
            'working_steps': sum(1 for step in results.values() if step['success']),
            'total_steps': len(results)
        }

    def test_api_performance(self) -> Dict[str, Any]:
        """Test API performance across services"""
        logger.info("Testing API performance...")

        performance_results = {}

        # Test backend API performance
        backend_performance = self._test_service_performance('backend')
        performance_results['backend'] = backend_performance

        # Test other services
        for service_name in ['npu_worker', 'ai_stack', 'browser']:
            service_performance = self._test_service_performance(service_name)
            performance_results[service_name] = service_performance

        return performance_results

    def _test_service_performance(self, service_name: str) -> Dict[str, Any]:
        """Test performance of a specific service"""
        if service_name not in self.services:
            return {'error': f'Service {service_name} not configured'}

        service_config = self.services[service_name]
        base_url = service_config['base_url']

        # Test primary endpoint (usually health or first endpoint)
        primary_endpoint = service_config['endpoints'][0]
        url = f"{base_url}{primary_endpoint}"

        # Run multiple performance tests
        response_times = []
        success_count = 0

        for i in range(5):  # 5 performance test runs
            result = self._test_endpoint_sync(url)
            if result['success']:
                response_times.append(result['response_time'])
                success_count += 1

        if response_times:
            return {
                'avg_response_time': sum(response_times) / len(response_times),
                'min_response_time': min(response_times),
                'max_response_time': max(response_times),
                'success_rate': (success_count / 5) * 100,
                'performance_grade': self._calculate_performance_grade(sum(response_times) / len(response_times))
            }
        else:
            return {
                'avg_response_time': 0,
                'success_rate': 0,
                'performance_grade': 'F',
                'error': 'No successful requests'
            }

    def _calculate_performance_grade(self, avg_response_time: float) -> str:
        """Calculate performance grade based on response time"""
        if avg_response_time < 0.5:
            return 'A'
        elif avg_response_time < 1.0:
            return 'B'
        elif avg_response_time < 2.0:
            return 'C'
        elif avg_response_time < 5.0:
            return 'D'
        else:
            return 'F'

    async def run_comprehensive_api_tests(self) -> Dict[str, Any]:
        """Run all API integration tests"""
        logger.info("Running comprehensive API integration tests...")

        # Test individual APIs
        individual_results = await self.test_individual_apis()

        # Test backend API comprehensively
        backend_results = self.test_backend_api_comprehensive()

        # Test cross-service integrations
        integration_results = self.test_cross_service_integration()

        # Test API performance
        performance_results = self.test_api_performance()

        # Compile comprehensive report
        report = {
            'individual_apis': individual_results,
            'backend_comprehensive': backend_results,
            'cross_service_integration': integration_results,
            'api_performance': performance_results,
            'summary': self._generate_api_test_summary(individual_results, integration_results, performance_results)
        }

        return report

    def _generate_api_test_summary(self, individual_results: Dict[str, Any],
                                 integration_results: Dict[str, Any],
                                 performance_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate API test summary"""

        # Calculate overall API health
        total_services = len(individual_results)
        working_services = sum(1 for service in individual_results.values() if service['service_health'])
        api_health_percentage = (working_services / total_services) * 100 if total_services > 0 else 0

        # Calculate integration health
        integration_health = sum(1 for integration in integration_results.values()
                               if integration.get('status') == 'WORKING')
        total_integrations = len(integration_results)
        integration_health_percentage = (integration_health / total_integrations) * 100 if total_integrations > 0 else 0

        # Calculate performance summary
        performance_grades = []
        for service_perf in performance_results.values():
            if 'performance_grade' in service_perf:
                performance_grades.append(service_perf['performance_grade'])

        return {
            'total_services_tested': total_services,
            'working_services': working_services,
            'api_health_percentage': api_health_percentage,
            'integration_health_percentage': integration_health_percentage,
            'overall_api_status': 'HEALTHY' if api_health_percentage >= 70 else 'DEGRADED',
            'overall_integration_status': 'HEALTHY' if integration_health_percentage >= 70 else 'DEGRADED',
            'performance_summary': {
                'services_tested': len(performance_grades),
                'performance_grades': performance_grades
            }
        }

def main():
    """Main API integration test execution"""
    api_test = APIIntegrationTest()

    # Run comprehensive tests
    report = asyncio.run(api_test.run_comprehensive_api_tests())

    # Print summary
    print("\n" + "="*60)
    print("API INTEGRATION TEST SUMMARY")
    print("="*60)

    summary = report['summary']
    print(f"Total Services Tested: {summary['total_services_tested']}")
    print(f"Working Services: {summary['working_services']}")
    print(f"API Health: {summary['api_health_percentage']:.1f}%")
    print(f"Integration Health: {summary['integration_health_percentage']:.1f}%")
    print(f"Overall API Status: {summary['overall_api_status']}")
    print(f"Overall Integration Status: {summary['overall_integration_status']}")

    # Performance summary
    perf_summary = summary['performance_summary']
    if perf_summary['performance_grades']:
        print(f"Performance Grades: {', '.join(perf_summary['performance_grades'])}")

    print(f"\nDetailed API test results available in test logs.")
    print("="*60)

    return report

if __name__ == "__main__":
    main()