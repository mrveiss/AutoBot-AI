#!/usr/bin/env python3
"""
Quick AutoBot Infrastructure Assessment
P0 Critical Task - Week 1 System Validation

Streamlined version that runs essential tests and generates executive summary.
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path
import logging

# Add test modules to path
test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, test_dir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QuickInfrastructureAssessment:
    """Quick assessment of AutoBot distributed infrastructure"""

    def __init__(self):
        self.test_start_time = datetime.now()
        self.results = {}

    def run_assessment(self):
        """Run quick infrastructure assessment"""
        logger.info("="*80)
        logger.info("AUTOBOT QUICK INFRASTRUCTURE ASSESSMENT")
        logger.info("P0 Critical Task - Week 1 System Validation")
        logger.info("="*80)

        try:
            # Phase 1: VM Connectivity
            logger.info("\n📡 TESTING VM CONNECTIVITY")
            connectivity_results = self._test_vm_connectivity()
            self.results['connectivity'] = connectivity_results

            # Phase 2: Service Health
            logger.info("\n🔗 TESTING SERVICE HEALTH")
            service_results = self._test_service_health()
            self.results['services'] = service_results

            # Phase 3: API Functionality
            logger.info("\n🖥️ TESTING API FUNCTIONALITY")
            api_results = self._test_api_functionality()
            self.results['apis'] = api_results

            # Phase 4: Generate Assessment
            logger.info("\n📊 GENERATING ASSESSMENT REPORT")
            assessment = self._generate_assessment()

            return assessment

        except Exception as e:
            logger.error(f"Assessment failed: {e}")
            raise

    def _test_vm_connectivity(self):
        """Test basic VM connectivity"""
        from connectivity.vm_connectivity_test import VMConnectivityTest

        connectivity_test = VMConnectivityTest()
        results = connectivity_test.generate_connectivity_report()

        summary = results['connectivity_summary']
        logger.info(f"✓ VM Connectivity: {summary['working_vms']}/{summary['total_vms']} VMs operational ({summary['connectivity_health_percentage']:.1f}%)")

        return results

    def _test_service_health(self):
        """Test individual service health"""
        services = {
            'main_backend': 'http://172.16.168.20:8001',
            'vm1_frontend': 'http://172.16.168.21:5173',
            'vm2_npu': 'http://172.16.168.22:8081',
            'vm3_redis': '172.16.168.23:6379',
            'vm4_ai': 'http://172.16.168.24:8080',
            'vm5_browser': 'http://172.16.168.25:3000'
        }

        service_results = {}
        working_services = 0

        for service_name, service_url in services.items():
            if service_name == 'vm3_redis':
                # Test Redis separately
                redis_status = self._test_redis_service()
                service_results[service_name] = redis_status
                if redis_status['working']:
                    working_services += 1
            else:
                # Test HTTP services
                http_status = self._test_http_service(service_url)
                service_results[service_name] = http_status
                if http_status['working']:
                    working_services += 1

        service_health_percentage = (working_services / len(services)) * 100
        logger.info(f"✓ Service Health: {working_services}/{len(services)} services operational ({service_health_percentage:.1f}%)")

        return {
            'individual_services': service_results,
            'working_services': working_services,
            'total_services': len(services),
            'health_percentage': service_health_percentage
        }

    def _test_http_service(self, url):
        """Test HTTP service availability"""
        import requests

        try:
            response = requests.get(f"{url}/health", timeout=5)
            working = 200 <= response.status_code < 400
            return {
                'working': working,
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds()
            }
        except Exception as e:
            try:
                # Try base URL if /health fails
                response = requests.get(url, timeout=5)
                working = 200 <= response.status_code < 400
                return {
                    'working': working,
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'note': 'Base URL responded, /health endpoint not available'
                }
            except:
                return {
                    'working': False,
                    'error': str(e)
                }

    def _test_redis_service(self):
        """Test Redis service"""
        try:
            import redis
            client = redis.Redis(host='172.16.168.23', port=6379, socket_timeout=5)
            client.ping()
            return {
                'working': True,
                'service': 'Redis',
                'response_time': 0.1  # Approximate
            }
        except Exception as e:
            return {
                'working': False,
                'error': str(e)
            }

    def _test_api_functionality(self):
        """Test key API endpoints"""
        backend_url = "http://172.16.168.20:8001"

        # Key endpoints to test
        endpoints = [
            '/api/health',
            '/api/knowledge_base/stats/basic',
            '/api/knowledge_base/categories'
        ]

        api_results = {}
        working_apis = 0

        for endpoint in endpoints:
            try:
                import requests
                response = requests.get(f"{backend_url}{endpoint}", timeout=10)

                working = 200 <= response.status_code < 400
                api_results[endpoint] = {
                    'working': working,
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'has_data': len(response.content) > 0
                }

                if working:
                    working_apis += 1

            except Exception as e:
                api_results[endpoint] = {
                    'working': False,
                    'error': str(e)
                }

        api_health_percentage = (working_apis / len(endpoints)) * 100 if endpoints else 0
        logger.info(f"✓ API Functionality: {working_apis}/{len(endpoints)} endpoints working ({api_health_percentage:.1f}%)")

        return {
            'endpoints': api_results,
            'working_apis': working_apis,
            'total_apis': len(endpoints),
            'health_percentage': api_health_percentage
        }

    def _generate_assessment(self):
        """Generate comprehensive assessment"""
        end_time = datetime.now()
        test_duration = (end_time - self.test_start_time).total_seconds()

        # Extract metrics
        connectivity = self.results['connectivity']['connectivity_summary']
        services = self.results['services']
        apis = self.results['apis']

        # Calculate overall health score
        connectivity_score = connectivity['connectivity_health_percentage']
        service_score = services['health_percentage']
        api_score = apis['health_percentage']

        # Weighted average (connectivity 30%, services 40%, APIs 30%)
        overall_health_score = (
            connectivity_score * 0.3 +
            service_score * 0.4 +
            api_score * 0.3
        )

        # Determine status
        if overall_health_score >= 80:
            health_status = 'HEALTHY'
            health_grade = 'A' if overall_health_score >= 90 else 'B'
        elif overall_health_score >= 60:
            health_status = 'DEGRADED'
            health_grade = 'C'
        else:
            health_status = 'CRITICAL'
            health_grade = 'F'

        # Identify critical issues
        critical_issues = []

        # Connectivity issues
        connectivity_issues = self.results['connectivity'].get('critical_issues', [])
        for issue in connectivity_issues:
            critical_issues.append({
                'type': 'connectivity',
                'component': issue['vm'],
                'issue': issue['issue']
            })

        # Service issues
        for service_name, service_data in services['individual_services'].items():
            if not service_data['working']:
                critical_issues.append({
                    'type': 'service',
                    'component': service_name,
                    'issue': 'Service not responding'
                })

        # API issues
        for endpoint, endpoint_data in apis['endpoints'].items():
            if not endpoint_data['working']:
                critical_issues.append({
                    'type': 'api',
                    'component': endpoint,
                    'issue': 'API endpoint not working'
                })

        # Working features
        working_features = []

        # Working VMs
        overall_vm_status = self.results['connectivity'].get('overall_vm_status', {})
        for vm_name, is_working in overall_vm_status.items():
            if is_working:
                working_features.append(f"{vm_name} connectivity")

        # Working services
        for service_name, service_data in services['individual_services'].items():
            if service_data['working']:
                working_features.append(f"{service_name} service")

        # Working APIs
        for endpoint, endpoint_data in apis['endpoints'].items():
            if endpoint_data['working']:
                working_features.append(f"{endpoint} API")

        # Week 1 P0 Assessment
        week1_criteria = {
            'infrastructure_operational': overall_health_score >= 70,
            'core_services_working': len(working_features) >= 8,
            'no_critical_blockers': len(critical_issues) <= 2,
            'basic_functionality': api_score >= 60
        }

        week1_completion = (sum(week1_criteria.values()) / len(week1_criteria)) * 100

        if week1_completion >= 75:
            week1_status = 'ON_TRACK'
        elif week1_completion >= 50:
            week1_status = 'AT_RISK'
        else:
            week1_status = 'BEHIND'

        # Generate assessment report
        assessment = {
            'assessment_overview': {
                'date': self.test_start_time.isoformat(),
                'duration_seconds': test_duration,
                'infrastructure': 'AutoBot Distributed 5-VM System'
            },
            'key_metrics': {
                'overall_health_score': round(overall_health_score, 1),
                'health_status': health_status,
                'health_grade': health_grade,
                'vm_connectivity': f"{connectivity['working_vms']}/{connectivity['total_vms']} ({connectivity_score:.1f}%)",
                'service_health': f"{services['working_services']}/{services['total_services']} ({service_score:.1f}%)",
                'api_functionality': f"{apis['working_apis']}/{apis['total_apis']} ({api_score:.1f}%)"
            },
            'critical_issues': critical_issues,
            'working_features': working_features,
            'week_1_assessment': {
                'status': week1_status,
                'completion_percentage': round(week1_completion, 1),
                'criteria_met': week1_criteria
            },
            'immediate_actions': self._get_immediate_actions(critical_issues),
            'detailed_results': self.results
        }

        # Save assessment
        self._save_assessment(assessment)

        return assessment

    def _get_immediate_actions(self, critical_issues):
        """Get immediate actions based on critical issues"""
        actions = []

        connectivity_issues = [i for i in critical_issues if i['type'] == 'connectivity']
        service_issues = [i for i in critical_issues if i['type'] == 'service']
        api_issues = [i for i in critical_issues if i['type'] == 'api']

        if connectivity_issues:
            actions.append(f"Fix VM connectivity issues: {', '.join([i['component'] for i in connectivity_issues[:3]])}")

        if service_issues:
            actions.append(f"Restart failed services: {', '.join([i['component'] for i in service_issues[:3]])}")

        if api_issues:
            actions.append(f"Investigate API failures: {', '.join([i['component'] for i in api_issues[:3]])}")

        if not actions:
            actions.append("System is operational - proceed with Week 2 objectives")

        return actions

    def _save_assessment(self, assessment):
        """Save assessment to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(test_dir, 'results')
        os.makedirs(results_dir, exist_ok=True)

        # Save JSON
        json_path = os.path.join(results_dir, f"quick_infrastructure_assessment_{timestamp}.json")
        with open(json_path, 'w') as f:
            json.dump(assessment, f, indent=2, default=str)

        # Save text summary
        text_path = os.path.join(results_dir, f"quick_assessment_summary_{timestamp}.txt")
        with open(text_path, 'w') as f:
            f.write("AUTOBOT INFRASTRUCTURE QUICK ASSESSMENT\n")
            f.write("=" * 50 + "\n\n")

            overview = assessment['assessment_overview']
            f.write(f"Assessment Date: {overview['date']}\n")
            f.write(f"Test Duration: {overview['duration_seconds']:.1f} seconds\n")
            f.write(f"Infrastructure: {overview['infrastructure']}\n\n")

            metrics = assessment['key_metrics']
            f.write("OVERALL HEALTH:\n")
            f.write(f"• Health Score: {metrics['overall_health_score']}%\n")
            f.write(f"• Health Grade: {metrics['health_grade']}\n")
            f.write(f"• Status: {metrics['health_status']}\n\n")

            f.write("COMPONENT STATUS:\n")
            f.write(f"• VM Connectivity: {metrics['vm_connectivity']}\n")
            f.write(f"• Service Health: {metrics['service_health']}\n")
            f.write(f"• API Functionality: {metrics['api_functionality']}\n\n")

            critical = assessment['critical_issues']
            f.write(f"CRITICAL ISSUES ({len(critical)}):\n")
            for issue in critical[:5]:  # Top 5
                f.write(f"• {issue['component']}: {issue['issue']}\n")
            f.write("\n")

            working = assessment['working_features']
            f.write(f"WORKING FEATURES ({len(working)}):\n")
            for feature in working[:10]:  # Top 10
                f.write(f"• {feature}\n")
            f.write("\n")

            week1 = assessment['week_1_assessment']
            f.write("WEEK 1 P0 STATUS:\n")
            f.write(f"• Status: {week1['status']}\n")
            f.write(f"• Completion: {week1['completion_percentage']:.1f}%\n\n")

            actions = assessment['immediate_actions']
            f.write("IMMEDIATE ACTIONS:\n")
            for i, action in enumerate(actions, 1):
                f.write(f"{i}. {action}\n")

        logger.info(f"Assessment saved to: {json_path}")
        logger.info(f"Summary saved to: {text_path}")

def main():
    """Main execution function"""
    try:
        assessment = QuickInfrastructureAssessment()
        results = assessment.run_assessment()

        # Print summary
        print("\n" + "="*80)
        print("AUTOBOT INFRASTRUCTURE ASSESSMENT SUMMARY")
        print("="*80)

        metrics = results['key_metrics']
        week1 = results['week_1_assessment']

        print(f"Overall Health: {metrics['health_status']} ({metrics['overall_health_score']}%, Grade: {metrics['health_grade']})")
        print(f"VM Connectivity: {metrics['vm_connectivity']}")
        print(f"Service Health: {metrics['service_health']}")
        print(f"API Functionality: {metrics['api_functionality']}")
        print(f"Week 1 P0 Status: {week1['status']} ({week1['completion_percentage']:.1f}%)")

        print(f"\nCritical Issues: {len(results['critical_issues'])}")
        print(f"Working Features: {len(results['working_features'])}")

        print(f"\nImmediate Actions:")
        for i, action in enumerate(results['immediate_actions'], 1):
            print(f"  {i}. {action}")

        print(f"\nDetailed results saved to: tests/results/")
        print("="*80)

        return results

    except Exception as e:
        print(f"\n❌ ASSESSMENT FAILED: {e}")
        logger.error(f"Assessment failed: {e}")
        return None

if __name__ == "__main__":
    main()
