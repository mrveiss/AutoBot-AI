#!/usr/bin/env python3
"""
Comprehensive AutoBot Infrastructure Test Execution Script
P0 Critical Task - Week 1 System Validation

Executes all infrastructure tests across the 5-VM distributed system
and generates comprehensive reports for stakeholders.
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

# Import test modules
from distributed_infrastructure.comprehensive_system_test import AutoBotInfrastructureTest
from connectivity.vm_connectivity_test import VMConnectivityTest
from integration.api_integration_test import APIIntegrationTest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(test_dir, 'results', 'test_execution.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ComprehensiveTestExecutor:
    """Executes all AutoBot infrastructure tests and generates consolidated reports"""

    def __init__(self):
        self.test_start_time = datetime.now()
        self.test_results = {}
        self.executive_summary = {}
        self.test_dir = test_dir

    def run_all_tests(self) -> dict:
        """Execute all comprehensive infrastructure tests"""
        logger.info("="*80)
        logger.info("STARTING AUTOBOT COMPREHENSIVE INFRASTRUCTURE TESTING")
        logger.info("P0 Critical Task - Week 1 System Validation")
        logger.info("="*80)

        try:
            # Phase 1: VM Connectivity Testing
            logger.info("\n📡 PHASE 1: VM CONNECTIVITY TESTING")
            connectivity_results = self._run_connectivity_tests()
            self.test_results['connectivity'] = connectivity_results

            # Phase 2: API Integration Testing
            logger.info("\n🔗 PHASE 2: API INTEGRATION TESTING")
            api_results = self._run_api_integration_tests()
            self.test_results['api_integration'] = api_results

            # Phase 3: Comprehensive System Testing
            logger.info("\n🖥️ PHASE 3: COMPREHENSIVE SYSTEM TESTING")
            system_results = self._run_comprehensive_system_tests()
            self.test_results['comprehensive_system'] = system_results

            # Phase 4: Generate Consolidated Report
            logger.info("\n📊 PHASE 4: GENERATING CONSOLIDATED REPORTS")
            consolidated_report = self._generate_consolidated_report()

            # Phase 5: Generate Executive Summary
            logger.info("\n📋 PHASE 5: GENERATING EXECUTIVE SUMMARY")
            executive_summary = self._generate_executive_summary()
            self.executive_summary = executive_summary

            logger.info("\n✅ ALL TESTS COMPLETED SUCCESSFULLY")
            return {
                'consolidated_report': consolidated_report,
                'executive_summary': executive_summary,
                'detailed_results': self.test_results
            }

        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            raise

    def _run_connectivity_tests(self) -> dict:
        """Run VM connectivity tests"""
        logger.info("Executing VM connectivity tests...")

        try:
            connectivity_test = VMConnectivityTest()
            results = connectivity_test.generate_connectivity_report()

            # Log key findings
            summary = results['connectivity_summary']
            logger.info(f"✓ Connectivity Test Complete: {summary['working_vms']}/{summary['total_vms']} VMs operational")

            if results['critical_issues']:
                logger.warning(f"⚠️ Found {len(results['critical_issues'])} connectivity issues")
                for issue in results['critical_issues'][:3]:  # Log first 3 issues
                    logger.warning(f"  - {issue['vm']}: {issue['issue']}")

            return results

        except Exception as e:
            logger.error(f"Connectivity tests failed: {e}")
            return {'error': str(e), 'test_status': 'FAILED'}

    def _run_api_integration_tests(self) -> dict:
        """Run API integration tests"""
        logger.info("Executing API integration tests...")

        try:
            api_test = APIIntegrationTest()
            results = asyncio.run(api_test.run_comprehensive_api_tests())

            # Log key findings
            summary = results['summary']
            logger.info(f"✓ API Integration Test Complete: {summary['working_services']}/{summary['total_services_tested']} services operational")
            logger.info(f"  API Health: {summary['api_health_percentage']:.1f}%")
            logger.info(f"  Integration Health: {summary['integration_health_percentage']:.1f}%")

            return results

        except Exception as e:
            logger.error(f"API integration tests failed: {e}")
            return {'error': str(e), 'test_status': 'FAILED'}

    def _run_comprehensive_system_tests(self) -> dict:
        """Run comprehensive system tests"""
        logger.info("Executing comprehensive system tests...")

        try:
            system_test = AutoBotInfrastructureTest()

            # Run all test phases
            connectivity_results = system_test.test_network_connectivity()
            logger.info("  ✓ Network connectivity tests completed")

            health_results = system_test.test_service_health()
            logger.info("  ✓ Service health tests completed")

            integration_results = system_test.test_integration_workflows()
            logger.info("  ✓ Integration workflow tests completed")

            performance_results = system_test.test_performance_metrics()
            logger.info("  ✓ Performance metrics collected")

            error_handling_results = system_test.test_error_handling()
            logger.info("  ✓ Error handling tests completed")

            # Generate final report
            final_report = system_test.generate_comprehensive_report()

            # Log system status
            system_status = final_report['system_status']
            logger.info(f"✓ Comprehensive System Test Complete: {system_status['overall_system_health']}")
            logger.info(f"  Infrastructure Health: {system_status['infrastructure_health']}")
            logger.info(f"  Service Health: {system_status['service_health']}")

            return final_report

        except Exception as e:
            logger.error(f"Comprehensive system tests failed: {e}")
            return {'error': str(e), 'test_status': 'FAILED'}

    def _generate_consolidated_report(self) -> dict:
        """Generate consolidated report from all test results"""
        logger.info("Generating consolidated infrastructure report...")

        end_time = datetime.now()
        test_duration = (end_time - self.test_start_time).total_seconds()

        # Extract key metrics from all tests
        connectivity_metrics = self._extract_connectivity_metrics()
        api_metrics = self._extract_api_metrics()
        system_metrics = self._extract_system_metrics()

        # Generate overall health assessment
        overall_health = self._calculate_overall_health(connectivity_metrics, api_metrics, system_metrics)

        consolidated_report = {
            'test_execution_info': {
                'test_start_time': self.test_start_time.isoformat(),
                'test_end_time': end_time.isoformat(),
                'total_duration_seconds': test_duration,
                'test_framework_version': 'AutoBot Infrastructure Test Suite v1.0'
            },
            'infrastructure_overview': {
                'total_vms': 6,  # Including main machine
                'distributed_services': 5,
                'vm_architecture': 'Distributed Multi-Service'
            },
            'consolidated_metrics': {
                'connectivity': connectivity_metrics,
                'api_integration': api_metrics,
                'system_health': system_metrics,
                'overall_health': overall_health
            },
            'critical_findings': self._identify_critical_findings(),
            'working_features': self._identify_all_working_features(),
            'performance_summary': self._generate_performance_overview(),
            'recommendations': self._generate_consolidated_recommendations()
        }

        # Save consolidated report
        self._save_consolidated_report(consolidated_report)

        return consolidated_report

    def _extract_connectivity_metrics(self) -> dict:
        """Extract connectivity metrics from test results"""
        connectivity_results = self.test_results.get('connectivity', {})

        if 'error' in connectivity_results:
            return {'status': 'ERROR', 'error': connectivity_results['error']}

        connectivity_summary = connectivity_results.get('connectivity_summary', {})

        return {
            'total_vms_tested': connectivity_summary.get('total_vms', 0),
            'working_vms': connectivity_summary.get('working_vms', 0),
            'connectivity_health_percentage': connectivity_summary.get('connectivity_health_percentage', 0),
            'status': connectivity_summary.get('status', 'UNKNOWN'),
            'critical_connectivity_issues': len(connectivity_results.get('critical_issues', []))
        }

    def _extract_api_metrics(self) -> dict:
        """Extract API metrics from test results"""
        api_results = self.test_results.get('api_integration', {})

        if 'error' in api_results:
            return {'status': 'ERROR', 'error': api_results['error']}

        api_summary = api_results.get('summary', {})

        return {
            'total_services_tested': api_summary.get('total_services_tested', 0),
            'working_services': api_summary.get('working_services', 0),
            'api_health_percentage': api_summary.get('api_health_percentage', 0),
            'integration_health_percentage': api_summary.get('integration_health_percentage', 0),
            'overall_api_status': api_summary.get('overall_api_status', 'UNKNOWN'),
            'overall_integration_status': api_summary.get('overall_integration_status', 'UNKNOWN')
        }

    def _extract_system_metrics(self) -> dict:
        """Extract system metrics from comprehensive test results"""
        system_results = self.test_results.get('comprehensive_system', {})

        if 'error' in system_results:
            return {'status': 'ERROR', 'error': system_results['error']}

        system_status = system_results.get('system_status', {})

        return {
            'overall_system_health': system_status.get('overall_system_health', 'UNKNOWN'),
            'vm_health_percentage': system_status.get('vm_health_percentage', 0),
            'service_health_percentage': system_status.get('service_health_percentage', 0),
            'critical_issues_count': len(system_results.get('critical_issues', [])),
            'working_features_count': len(system_results.get('working_features', []))
        }

    def _calculate_overall_health(self, connectivity_metrics: dict, api_metrics: dict, system_metrics: dict) -> dict:
        """Calculate overall infrastructure health"""

        # Calculate weighted health score
        connectivity_weight = 0.3
        api_weight = 0.4
        system_weight = 0.3

        connectivity_score = connectivity_metrics.get('connectivity_health_percentage', 0) / 100
        api_score = api_metrics.get('api_health_percentage', 0) / 100
        system_score = system_metrics.get('service_health_percentage', 0) / 100

        weighted_health_score = (
            connectivity_score * connectivity_weight +
            api_score * api_weight +
            system_score * system_weight
        ) * 100

        # Determine overall status
        if weighted_health_score >= 80:
            overall_status = 'HEALTHY'
        elif weighted_health_score >= 60:
            overall_status = 'DEGRADED'
        else:
            overall_status = 'CRITICAL'

        return {
            'weighted_health_score': weighted_health_score,
            'overall_status': overall_status,
            'health_breakdown': {
                'connectivity': connectivity_score * 100,
                'api_integration': api_score * 100,
                'system_services': system_score * 100
            },
            'health_grade': self._calculate_health_grade(weighted_health_score)
        }

    def _calculate_health_grade(self, health_score: float) -> str:
        """Calculate health grade based on score"""
        if health_score >= 90:
            return 'A+'
        elif health_score >= 80:
            return 'A'
        elif health_score >= 70:
            return 'B'
        elif health_score >= 60:
            return 'C'
        elif health_score >= 50:
            return 'D'
        else:
            return 'F'

    def _identify_critical_findings(self) -> list:
        """Identify critical findings across all tests"""
        critical_findings = []

        # Extract critical issues from connectivity tests
        connectivity_results = self.test_results.get('connectivity', {})
        for issue in connectivity_results.get('critical_issues', []):
            critical_findings.append({
                'source': 'connectivity',
                'severity': 'HIGH',
                'component': issue['vm'],
                'issue': issue['issue'],
                'details': f"VM {issue['vm']} ({issue['ip']}) connectivity failure"
            })

        # Extract critical issues from system tests
        system_results = self.test_results.get('comprehensive_system', {})
        for issue in system_results.get('critical_issues', []):
            critical_findings.append({
                'source': 'system',
                'severity': issue.get('severity', 'HIGH'),
                'component': issue['component'],
                'issue': issue['issue'],
                'details': issue.get('required_action', 'Investigation required')
            })

        # Extract API integration issues
        api_results = self.test_results.get('api_integration', {})
        api_summary = api_results.get('summary', {})
        if api_summary.get('overall_api_status') == 'DEGRADED':
            critical_findings.append({
                'source': 'api_integration',
                'severity': 'MEDIUM',
                'component': 'API Services',
                'issue': 'API service degradation detected',
                'details': f"API health at {api_summary.get('api_health_percentage', 0):.1f}%"
            })

        return critical_findings

    def _identify_all_working_features(self) -> list:
        """Identify all working features across tests"""
        working_features = []

        # Extract working features from system tests
        system_results = self.test_results.get('comprehensive_system', {})
        for feature in system_results.get('working_features', []):
            working_features.append({
                'source': 'system',
                'feature': feature['feature'],
                'status': feature['status'],
                'description': feature['description']
            })

        # Extract working APIs
        api_results = self.test_results.get('api_integration', {})
        individual_apis = api_results.get('individual_apis', {})
        for service_name, service_data in individual_apis.items():
            if service_data.get('service_health', False):
                working_features.append({
                    'source': 'api_integration',
                    'feature': f"{service_name}_api",
                    'status': 'OPERATIONAL',
                    'description': f"{service_name} API service is responding ({service_data.get('working_endpoints', 0)}/{service_data.get('total_endpoints', 0)} endpoints)"
                })

        # Extract working connectivity
        connectivity_results = self.test_results.get('connectivity', {})
        overall_vm_status = connectivity_results.get('overall_vm_status', {})
        for vm_name, is_working in overall_vm_status.items():
            if is_working:
                working_features.append({
                    'source': 'connectivity',
                    'feature': f"{vm_name}_connectivity",
                    'status': 'OPERATIONAL',
                    'description': f"{vm_name} network connectivity is working"
                })

        return working_features

    def _generate_performance_overview(self) -> dict:
        """Generate performance overview from all tests"""
        performance_data = {}

        # Extract API performance data
        api_results = self.test_results.get('api_integration', {})
        api_performance = api_results.get('api_performance', {})

        if api_performance:
            response_times = []
            performance_grades = []

            for service_name, service_perf in api_performance.items():
                if 'avg_response_time' in service_perf:
                    response_times.append(service_perf['avg_response_time'])
                if 'performance_grade' in service_perf:
                    performance_grades.append(service_perf['performance_grade'])

            if response_times:
                performance_data['api_performance'] = {
                    'avg_response_time': sum(response_times) / len(response_times),
                    'fastest_service': min(response_times),
                    'slowest_service': max(response_times),
                    'performance_grades': performance_grades
                }

        # Extract system performance data
        system_results = self.test_results.get('comprehensive_system', {})
        system_performance = system_results.get('performance_summary', {})

        if system_performance:
            performance_data['system_performance'] = {
                'performance_grade': system_performance.get('performance_grade', 'Unknown'),
                'database_performance': system_performance.get('database_performance', {}),
                'api_performance': system_performance.get('api_performance', {})
            }

        return performance_data

    def _generate_consolidated_recommendations(self) -> list:
        """Generate consolidated recommendations from all tests"""
        recommendations = []

        # Extract recommendations from system tests
        system_results = self.test_results.get('comprehensive_system', {})
        for rec in system_results.get('recommendations', []):
            recommendations.append({
                'source': 'system_test',
                'priority': rec.get('priority', 'MEDIUM'),
                'category': rec.get('category', 'General'),
                'recommendation': rec.get('recommendation', ''),
                'component': rec.get('vm_affected', rec.get('service_affected', rec.get('endpoint_affected', 'Unknown')))
            })

        # Add connectivity-based recommendations
        connectivity_results = self.test_results.get('connectivity', {})
        for issue in connectivity_results.get('critical_issues', []):
            recommendations.append({
                'source': 'connectivity_test',
                'priority': 'HIGH',
                'category': 'Infrastructure',
                'recommendation': f"Investigate and restore connectivity to {issue['vm']}",
                'component': issue['vm']
            })

        # Add API-based recommendations
        api_results = self.test_results.get('api_integration', {})
        api_summary = api_results.get('summary', {})

        if api_summary.get('api_health_percentage', 100) < 80:
            recommendations.append({
                'source': 'api_integration_test',
                'priority': 'HIGH',
                'category': 'API Services',
                'recommendation': f"Investigate API service health issues (currently at {api_summary.get('api_health_percentage', 0):.1f}%)",
                'component': 'API Infrastructure'
            })

        if api_summary.get('integration_health_percentage', 100) < 70:
            recommendations.append({
                'source': 'api_integration_test',
                'priority': 'HIGH',
                'category': 'Integration',
                'recommendation': f"Fix cross-service integration issues (currently at {api_summary.get('integration_health_percentage', 0):.1f}%)",
                'component': 'Service Integration'
            })

        return recommendations

    def _save_consolidated_report(self, report: dict) -> None:
        """Save consolidated report to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(self.test_dir, 'results')
        os.makedirs(results_dir, exist_ok=True)

        report_path = os.path.join(results_dir, f"comprehensive_infrastructure_assessment_{timestamp}.json")

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Consolidated report saved to: {report_path}")

    def _generate_executive_summary(self) -> dict:
        """Generate executive summary for stakeholders"""
        logger.info("Generating executive summary for stakeholders...")

        connectivity_metrics = self._extract_connectivity_metrics()
        api_metrics = self._extract_api_metrics()
        system_metrics = self._extract_system_metrics()

        # Calculate key KPIs
        overall_health = self._calculate_overall_health(connectivity_metrics, api_metrics, system_metrics)
        critical_findings = self._identify_critical_findings()
        working_features = self._identify_all_working_features()

        executive_summary = {
            'assessment_overview': {
                'assessment_date': self.test_start_time.isoformat(),
                'infrastructure_type': 'Distributed 5-VM AutoBot System',
                'assessment_scope': 'Complete Infrastructure Validation',
                'test_duration_minutes': round((datetime.now() - self.test_start_time).total_seconds() / 60, 1)
            },
            'key_findings': {
                'overall_infrastructure_health': overall_health['overall_status'],
                'health_score': round(overall_health['weighted_health_score'], 1),
                'health_grade': overall_health['health_grade'],
                'critical_issues_count': len(critical_findings),
                'working_features_count': len(working_features)
            },
            'infrastructure_status': {
                'vm_connectivity': f"{connectivity_metrics.get('working_vms', 0)}/{connectivity_metrics.get('total_vms_tested', 0)} VMs operational",
                'api_services': f"{api_metrics.get('working_services', 0)}/{api_metrics.get('total_services_tested', 0)} services operational",
                'system_health': system_metrics.get('overall_system_health', 'UNKNOWN'),
                'performance_grade': system_metrics.get('service_health_percentage', 0)
            },
            'immediate_actions_required': self._get_immediate_actions(critical_findings),
            'system_readiness': self._assess_system_readiness(overall_health, critical_findings),
            'week_1_completion_status': self._assess_week_1_completion(overall_health, working_features, critical_findings)
        }

        # Save executive summary
        self._save_executive_summary(executive_summary)

        return executive_summary

    def _get_immediate_actions(self, critical_findings: list) -> list:
        """Get list of immediate actions required"""
        immediate_actions = []

        high_priority_findings = [f for f in critical_findings if f.get('severity') == 'HIGH']

        for finding in high_priority_findings[:5]:  # Top 5 critical issues
            immediate_actions.append(f"Fix {finding['component']}: {finding['issue']}")

        if not immediate_actions:
            immediate_actions.append("No critical issues requiring immediate action")

        return immediate_actions

    def _assess_system_readiness(self, overall_health: dict, critical_findings: list) -> dict:
        """Assess system readiness for production use"""
        health_score = overall_health['weighted_health_score']
        critical_count = len([f for f in critical_findings if f.get('severity') == 'HIGH'])

        if health_score >= 80 and critical_count == 0:
            readiness_status = 'READY'
            readiness_description = 'System is ready for production use'
        elif health_score >= 70 and critical_count <= 2:
            readiness_status = 'MOSTLY_READY'
            readiness_description = 'System is mostly ready with minor issues to address'
        elif health_score >= 50:
            readiness_status = 'NEEDS_WORK'
            readiness_description = 'System needs significant work before production ready'
        else:
            readiness_status = 'NOT_READY'
            readiness_description = 'System requires major fixes before production use'

        return {
            'status': readiness_status,
            'description': readiness_description,
            'health_score': health_score,
            'critical_issues': critical_count,
            'estimated_fix_time': self._estimate_fix_time(critical_count, health_score)
        }

    def _estimate_fix_time(self, critical_count: int, health_score: float) -> str:
        """Estimate time to fix critical issues"""
        if critical_count == 0 and health_score >= 80:
            return "No fixes required"
        elif critical_count <= 2 and health_score >= 70:
            return "1-2 days"
        elif critical_count <= 5 and health_score >= 50:
            return "3-5 days"
        else:
            return "1-2 weeks"

    def _assess_week_1_completion(self, overall_health: dict, working_features: list, critical_findings: list) -> dict:
        """Assess Week 1 P0 completion status"""
        health_score = overall_health['weighted_health_score']
        working_count = len(working_features)
        critical_count = len([f for f in critical_findings if f.get('severity') == 'HIGH'])

        # Week 1 P0 criteria assessment
        criteria_met = {
            'infrastructure_operational': health_score >= 70,
            'core_services_working': working_count >= 10,
            'no_critical_blockers': critical_count <= 1,
            'basic_workflows_functional': health_score >= 60
        }

        completion_percentage = (sum(criteria_met.values()) / len(criteria_met)) * 100

        if completion_percentage >= 75:
            completion_status = 'ON_TRACK'
            completion_description = 'Week 1 P0 objectives are on track for completion'
        elif completion_percentage >= 50:
            completion_status = 'AT_RISK'
            completion_description = 'Week 1 P0 objectives are at risk but achievable'
        else:
            completion_status = 'BEHIND'
            completion_description = 'Week 1 P0 objectives require immediate attention'

        return {
            'status': completion_status,
            'description': completion_description,
            'completion_percentage': completion_percentage,
            'criteria_assessment': criteria_met,
            'next_steps': self._get_week_1_next_steps(criteria_met, critical_findings)
        }

    def _get_week_1_next_steps(self, criteria_met: dict, critical_findings: list) -> list:
        """Get next steps for Week 1 completion"""
        next_steps = []

        if not criteria_met['infrastructure_operational']:
            next_steps.append("Fix infrastructure connectivity and service health issues")

        if not criteria_met['core_services_working']:
            next_steps.append("Restore core service functionality and API endpoints")

        if not criteria_met['no_critical_blockers']:
            high_priority = [f for f in critical_findings if f.get('severity') == 'HIGH']
            next_steps.append(f"Address {len(high_priority)} critical blocking issues")

        if not criteria_met['basic_workflows_functional']:
            next_steps.append("Fix basic user workflows and system integrations")

        if not next_steps:
            next_steps.append("System is ready - proceed with Week 2 objectives")

        return next_steps

    def _save_executive_summary(self, summary: dict) -> None:
        """Save executive summary to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(self.test_dir, 'results')
        os.makedirs(results_dir, exist_ok=True)

        summary_path = os.path.join(results_dir, f"executive_summary_{timestamp}.json")

        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        # Also save as readable text file
        text_summary_path = os.path.join(results_dir, f"executive_summary_{timestamp}.txt")
        with open(text_summary_path, 'w') as f:
            f.write("AUTOBOT INFRASTRUCTURE ASSESSMENT - EXECUTIVE SUMMARY\n")
            f.write("=" * 70 + "\n\n")

            overview = summary['assessment_overview']
            f.write(f"Assessment Date: {overview['assessment_date']}\n")
            f.write(f"Infrastructure: {overview['infrastructure_type']}\n")
            f.write(f"Test Duration: {overview['test_duration_minutes']} minutes\n\n")

            findings = summary['key_findings']
            f.write("KEY FINDINGS:\n")
            f.write(f"• Overall Health: {findings['overall_infrastructure_health']}\n")
            f.write(f"• Health Score: {findings['health_score']}% (Grade: {findings['health_grade']})\n")
            f.write(f"• Critical Issues: {findings['critical_issues_count']}\n")
            f.write(f"• Working Features: {findings['working_features_count']}\n\n")

            status = summary['infrastructure_status']
            f.write("INFRASTRUCTURE STATUS:\n")
            f.write(f"• VM Connectivity: {status['vm_connectivity']}\n")
            f.write(f"• API Services: {status['api_services']}\n")
            f.write(f"• System Health: {status['system_health']}\n\n")

            actions = summary['immediate_actions_required']
            f.write("IMMEDIATE ACTIONS REQUIRED:\n")
            for i, action in enumerate(actions, 1):
                f.write(f"{i}. {action}\n")
            f.write("\n")

            readiness = summary['system_readiness']
            f.write("SYSTEM READINESS:\n")
            f.write(f"• Status: {readiness['status']}\n")
            f.write(f"• Description: {readiness['description']}\n")
            f.write(f"• Estimated Fix Time: {readiness['estimated_fix_time']}\n\n")

            week1 = summary['week_1_completion_status']
            f.write("WEEK 1 P0 COMPLETION STATUS:\n")
            f.write(f"• Status: {week1['status']}\n")
            f.write(f"• Completion: {week1['completion_percentage']:.1f}%\n")
            f.write(f"• Description: {week1['description']}\n\n")

            f.write("NEXT STEPS:\n")
            for i, step in enumerate(week1['next_steps'], 1):
                f.write(f"{i}. {step}\n")

        logger.info(f"Executive summary saved to: {summary_path}")
        logger.info(f"Executive summary (text) saved to: {text_summary_path}")

def main():
    """Main execution function"""
    print("="*80)
    print("AUTOBOT COMPREHENSIVE INFRASTRUCTURE TESTING")
    print("P0 Critical Task - Week 1 System Validation")
    print("="*80)

    try:
        # Initialize test executor
        test_executor = ComprehensiveTestExecutor()

        # Run all comprehensive tests
        all_results = test_executor.run_all_tests()

        # Print final summary
        print("\n" + "="*80)
        print("FINAL ASSESSMENT SUMMARY")
        print("="*80)

        executive_summary = all_results['executive_summary']
        key_findings = executive_summary['key_findings']
        week_1_status = executive_summary['week_1_completion_status']

        print(f"Overall Infrastructure Health: {key_findings['overall_infrastructure_health']}")
        print(f"Health Score: {key_findings['health_score']}% (Grade: {key_findings['health_grade']})")
        print(f"Critical Issues: {key_findings['critical_issues_count']}")
        print(f"Working Features: {key_findings['working_features_count']}")
        print(f"Week 1 P0 Status: {week_1_status['status']} ({week_1_status['completion_percentage']:.1f}%)")

        print(f"\nImmediate Actions Required:")
        for i, action in enumerate(executive_summary['immediate_actions_required'][:3], 1):
            print(f"  {i}. {action}")

        print(f"\nDetailed reports saved to: tests/results/")
        print("="*80)

        return all_results

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        print(f"\n❌ TEST EXECUTION FAILED: {e}")
        return None

if __name__ == "__main__":
    main()
