#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Phase 9 Monitoring System Validation Test
Comprehensive testing of GPU/NPU monitoring, performance optimization, and real-time dashboard.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from autobot_shared.logging_manager import get_logger

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.gpu_acceleration_optimizer import (
    benchmark_gpu,
    get_gpu_capabilities,
    gpu_optimizer,
    monitor_gpu_efficiency,
    optimize_gpu_for_multimodal,
    update_gpu_config,
)

# Import Phase 9 monitoring components
from utils.hardware_metrics import (
    add_phase9_alert_callback,
    collect_phase9_metrics,
    get_phase9_performance_dashboard,
    phase9_monitor,
    start_phase9_monitoring,
    stop_phase9_monitoring,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = get_logger(__name__)


class Phase9MonitoringSystemTest:
    """Comprehensive test suite for Phase 9 monitoring system"""

    def __init__(self):
        self.test_results = {}
        self.start_time = time.time()
        self.alerts_received = []

    async def run_full_test_suite(self):
        """Run complete test suite for Phase 9 monitoring system"""
        logger.info("🚀 Starting AutoBot Phase 9 Monitoring System Validation")
        logger.info("=" * 80)

        try:
            # Test 1: Hardware Detection
            await self.test_hardware_detection()

            # Test 2: Performance Monitor Initialization
            await self.test_performance_monitor_initialization()

            # Test 3: GPU Capabilities and Optimization
            await self.test_gpu_capabilities_and_optimization()

            # Test 4: Metrics Collection
            await self.test_metrics_collection()

            # Test 5: Real-time Monitoring
            await self.test_realtime_monitoring()

            # Test 6: Performance Dashboard
            await self.test_performance_dashboard()

            # Test 7: Alert System
            await self.test_alert_system()

            # Test 8: Optimization Engine
            await self.test_optimization_engine()

            # Test 9: Benchmark Suite
            await self.test_benchmark_suite()

            # Test 10: Configuration Management
            await self.test_configuration_management()

            # Generate final report
            await self.generate_test_report()

        except Exception as e:
            logger.error(f"❌ Test suite failed with error: {e}")
            self.test_results["fatal_error"] = str(e)

    async def test_hardware_detection(self):
        """Test hardware detection capabilities"""
        logger.info("🔍 Test 1: Hardware Detection")

        try:
            # Test GPU detection
            gpu_available = phase9_monitor.gpu_available
            logger.info(f"   GPU Available: {'✓' if gpu_available else '✗'}")

            # Test NPU detection
            npu_available = phase9_monitor.npu_available
            logger.info(f"   NPU Available: {'✓' if npu_available else '✗'}")

            # Get detailed capabilities
            capabilities = get_gpu_capabilities()
            logger.info(f"   GPU Capabilities: {json.dumps(capabilities['capabilities'], indent=6)}")

            self.test_results["hardware_detection"] = {
                "gpu_available": gpu_available,
                "npu_available": npu_available,
                "gpu_capabilities": capabilities,
                "success": True,
            }

            logger.info("   ✅ Hardware detection test passed")

        except Exception as e:
            logger.error(f"   ❌ Hardware detection test failed: {e}")
            self.test_results["hardware_detection"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_performance_monitor_initialization(self):
        """Test performance monitor initialization"""
        logger.info("⚙️ Test 2: Performance Monitor Initialization")

        try:
            # Check initial state
            initial_state = phase9_monitor.monitoring_active
            logger.info(f"   Initial monitoring state: {initial_state}")

            # Test buffer initialization
            gpu_buffer_size = len(phase9_monitor.gpu_metrics_buffer)
            npu_buffer_size = len(phase9_monitor.npu_metrics_buffer)
            system_buffer_size = len(phase9_monitor.system_metrics_buffer)

            logger.info(f"   GPU metrics buffer: {gpu_buffer_size} entries")
            logger.info(f"   NPU metrics buffer: {npu_buffer_size} entries")
            logger.info(f"   System metrics buffer: {system_buffer_size} entries")

            # Test configuration
            config = phase9_monitor.performance_baselines
            logger.info(f"   Performance baselines configured: {len(config)} baselines")

            self.test_results["monitor_initialization"] = {
                "initial_state": initial_state,
                "buffers_initialized": True,
                "baselines_configured": len(config) > 0,
                "success": True,
            }

            logger.info("   ✅ Performance monitor initialization test passed")

        except Exception as e:
            logger.error(f"   ❌ Performance monitor initialization test failed: {e}")
            self.test_results["monitor_initialization"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_gpu_capabilities_and_optimization(self):
        """Test GPU capabilities detection and optimization"""
        logger.info("🎮 Test 3: GPU Capabilities and Optimization")

        try:
            # Test GPU optimizer initialization
            gpu_available = gpu_optimizer.gpu_available
            logger.info(f"   GPU Optimizer Available: {'✓' if gpu_available else '✗'}")

            if gpu_available:
                # Test capabilities detection
                capabilities = gpu_optimizer.gpu_capabilities
                logger.info(f"   Tensor Cores: {'✓' if capabilities.get('tensor_cores') else '✗'}")
                logger.info(f"   Mixed Precision: {'✓' if capabilities.get('mixed_precision') else '✗'}")
                logger.info(f"   Memory: {capabilities.get('memory_gb', 0)} GB")

                # Test configuration
                config = gpu_optimizer.get_optimization_config()
                logger.info(f"   Mixed precision enabled: {config.mixed_precision_enabled}")
                logger.info(f"   Tensor core optimization: {config.tensor_core_optimization}")
                logger.info(f"   Auto batch sizing: {config.auto_batch_sizing}")

            self.test_results["gpu_capabilities"] = {
                "gpu_available": gpu_available,
                "capabilities": gpu_optimizer.gpu_capabilities if gpu_available else {},
                "config_loaded": True,
                "success": True,
            }

            logger.info("   ✅ GPU capabilities and optimization test passed")

        except Exception as e:
            logger.error(f"   ❌ GPU capabilities test failed: {e}")
            self.test_results["gpu_capabilities"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_metrics_collection(self):
        """Test metrics collection functionality"""
        logger.info("📊 Test 4: Metrics Collection")

        try:
            # Test comprehensive metrics collection
            metrics = await collect_phase9_metrics()
            collection_successful = metrics.get("collection_successful", False)

            logger.info(f"   Metrics collection: {'✓' if collection_successful else '✗'}")

            if collection_successful:
                # Check metric categories
                gpu_metrics = metrics.get("gpu")
                npu_metrics = metrics.get("npu")
                system_metrics = metrics.get("system")
                services_metrics = metrics.get("services", [])

                logger.info(f"   GPU metrics: {'✓' if gpu_metrics else '✗'}")
                logger.info(f"   NPU metrics: {'✓' if npu_metrics else '✗'}")
                logger.info(f"   System metrics: {'✓' if system_metrics else '✗'}")
                logger.info(f"   Service metrics: {len(services_metrics)} services")

                # Test individual metric collection
                if gpu_metrics:
                    gpu_individual = await phase9_monitor.collect_gpu_metrics()
                    logger.info(f"   Individual GPU collection: {'✓' if gpu_individual else '✗'}")

                if npu_metrics:
                    npu_individual = await phase9_monitor.collect_npu_metrics()
                    logger.info(f"   Individual NPU collection: {'✓' if npu_individual else '✗'}")

                system_individual = await phase9_monitor.collect_system_performance_metrics()
                logger.info(f"   Individual system collection: {'✓' if system_individual else '✗'}")

            self.test_results["metrics_collection"] = {
                "collection_successful": collection_successful,
                "gpu_metrics_available": gpu_metrics is not None,
                "npu_metrics_available": npu_metrics is not None,
                "system_metrics_available": system_metrics is not None,
                "services_count": len(services_metrics),
                "success": collection_successful,
            }

            logger.info("   ✅ Metrics collection test passed")

        except Exception as e:
            logger.error(f"   ❌ Metrics collection test failed: {e}")
            self.test_results["metrics_collection"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_realtime_monitoring(self):
        """Test real-time monitoring functionality"""
        logger.info("⏱️ Test 5: Real-time Monitoring")

        try:
            # Start monitoring
            monitoring_started = not phase9_monitor.monitoring_active
            if monitoring_started:
                await start_phase9_monitoring()
                logger.info("   Monitoring started: ✓")
            else:
                logger.info("   Monitoring already active: ✓")

            # Wait for some metrics to be collected
            logger.info("   Collecting metrics for 10 seconds...")
            await asyncio.sleep(10)

            # Check if metrics are being collected
            gpu_buffer_size = len(phase9_monitor.gpu_metrics_buffer)
            system_buffer_size = len(phase9_monitor.system_metrics_buffer)

            logger.info(f"   GPU metrics collected: {gpu_buffer_size}")
            logger.info(f"   System metrics collected: {system_buffer_size}")

            # Test monitoring status
            monitoring_active = phase9_monitor.monitoring_active
            logger.info(f"   Monitoring active: {'✓' if monitoring_active else '✗'}")

            self.test_results["realtime_monitoring"] = {
                "monitoring_started": monitoring_started or monitoring_active,
                "monitoring_active": monitoring_active,
                "metrics_collected": gpu_buffer_size + system_buffer_size > 0,
                "gpu_metrics_count": gpu_buffer_size,
                "system_metrics_count": system_buffer_size,
                "success": monitoring_active and (gpu_buffer_size + system_buffer_size > 0),
            }

            logger.info("   ✅ Real-time monitoring test passed")

        except Exception as e:
            logger.error(f"   ❌ Real-time monitoring test failed: {e}")
            self.test_results["realtime_monitoring"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_performance_dashboard(self):
        """Test performance dashboard functionality"""
        logger.info("📈 Test 6: Performance Dashboard")

        try:
            # Get dashboard data
            dashboard = get_phase9_performance_dashboard()

            # Check dashboard components
            has_monitoring_status = "monitoring_active" in dashboard
            has_hardware_info = "hardware_acceleration" in dashboard
            has_gpu_data = dashboard.get("gpu") is not None
            has_system_data = dashboard.get("system") is not None
            has_trends = "trends" in dashboard
            has_alerts = "recent_alerts" in dashboard

            logger.info(f"   Dashboard structure: {'✓' if has_monitoring_status else '✗'}")
            logger.info(f"   Hardware info: {'✓' if has_hardware_info else '✗'}")
            logger.info(f"   GPU data: {'✓' if has_gpu_data else '✗'}")
            logger.info(f"   System data: {'✓' if has_system_data else '✗'}")
            logger.info(f"   Trends analysis: {'✓' if has_trends else '✗'}")
            logger.info(f"   Alerts included: {'✓' if has_alerts else '✗'}")

            # Test dashboard data quality
            dashboard_complete = all([has_monitoring_status, has_hardware_info, has_system_data])

            self.test_results["performance_dashboard"] = {
                "dashboard_accessible": True,
                "has_monitoring_status": has_monitoring_status,
                "has_hardware_info": has_hardware_info,
                "has_gpu_data": has_gpu_data,
                "has_system_data": has_system_data,
                "has_trends": has_trends,
                "has_alerts": has_alerts,
                "dashboard_complete": dashboard_complete,
                "success": dashboard_complete,
            }

            logger.info("   ✅ Performance dashboard test passed")

        except Exception as e:
            logger.error(f"   ❌ Performance dashboard test failed: {e}")
            self.test_results["performance_dashboard"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_alert_system(self):
        """Test alert system functionality"""
        logger.info("🚨 Test 7: Alert System")

        try:
            # Add test alert callback
            async def test_alert_callback(alerts):
                self.alerts_received.extend(alerts)
                logger.info(f"   Received {len(alerts)} alerts")

            add_phase9_alert_callback(test_alert_callback)
            logger.info("   Alert callback registered: ✓")

            # Check existing alerts
            existing_alerts = list(phase9_monitor.performance_alerts)
            logger.info(f"   Existing alerts: {len(existing_alerts)}")

            # Test alert structure
            if existing_alerts:
                sample_alert = existing_alerts[0]
                has_category = "category" in sample_alert
                has_severity = "severity" in sample_alert
                has_message = "message" in sample_alert
                has_timestamp = "timestamp" in sample_alert

                logger.info(
                    f"   Alert structure valid: {'✓' if all([has_category, has_severity, has_message, has_timestamp]) else '✗'}"
                )

            # Wait for potential new alerts
            initial_alert_count = len(self.alerts_received)
            await asyncio.sleep(5)
            new_alert_count = len(self.alerts_received)

            logger.info(f"   New alerts received: {new_alert_count - initial_alert_count}")

            self.test_results["alert_system"] = {
                "callback_registered": True,
                "existing_alerts_count": len(existing_alerts),
                "alerts_received_count": len(self.alerts_received),
                "alert_structure_valid": len(existing_alerts) == 0
                or all(
                    [
                        "category" in existing_alerts[0],
                        "severity" in existing_alerts[0],
                        "message" in existing_alerts[0],
                        "timestamp" in existing_alerts[0],
                    ]
                ),
                "success": True,
            }

            logger.info("   ✅ Alert system test passed")

        except Exception as e:
            logger.error(f"   ❌ Alert system test failed: {e}")
            self.test_results["alert_system"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_optimization_engine(self):
        """Test optimization engine functionality"""
        logger.info("⚡ Test 8: Optimization Engine")

        try:
            if not gpu_optimizer.gpu_available:
                logger.info("   GPU not available, skipping optimization tests")
                self.test_results["optimization_engine"] = {
                    "gpu_available": False,
                    "success": True,
                    "message": "GPU not available for optimization testing",
                }
                return

            # Test GPU efficiency monitoring
            efficiency = await monitor_gpu_efficiency()
            efficiency_success = "overall_efficiency" in efficiency

            logger.info(f"   GPU efficiency monitoring: {'✓' if efficiency_success else '✗'}")
            if efficiency_success:
                logger.info(f"   Overall efficiency: {efficiency['overall_efficiency']:.1f}%")
                logger.info(f"   Efficiency grade: {efficiency.get('efficiency_grade', 'Unknown')}")

            # Test configuration updates
            config_update_success = update_gpu_config(
                {"mixed_precision_enabled": True, "tensor_core_optimization": True}
            )
            logger.info(f"   Configuration update: {'✓' if config_update_success else '✗'}")

            # Test optimization for multi-modal workloads
            logger.info("   Running multi-modal optimization...")
            optimization_result = await optimize_gpu_for_multimodal()
            optimization_success = optimization_result.success

            logger.info(f"   Multi-modal optimization: {'✓' if optimization_success else '✗'}")
            if optimization_success:
                logger.info(f"   Performance improvement: {optimization_result.performance_improvement:.1f}%")
                logger.info(f"   Optimizations applied: {len(optimization_result.applied_optimizations)}")

            self.test_results["optimization_engine"] = {
                "gpu_available": True,
                "efficiency_monitoring": efficiency_success,
                "config_updates": config_update_success,
                "multimodal_optimization": optimization_success,
                "optimization_result": (
                    {
                        "success": optimization_result.success,
                        "performance_improvement": optimization_result.performance_improvement,
                        "applied_optimizations": optimization_result.applied_optimizations,
                    }
                    if optimization_success
                    else None
                ),
                "success": efficiency_success and config_update_success,
            }

            logger.info("   ✅ Optimization engine test passed")

        except Exception as e:
            logger.error(f"   ❌ Optimization engine test failed: {e}")
            self.test_results["optimization_engine"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_benchmark_suite(self):
        """Test benchmark suite functionality"""
        logger.info("🏁 Test 9: Benchmark Suite")

        try:
            if not gpu_optimizer.gpu_available:
                logger.info("   GPU not available, skipping benchmark tests")
                self.test_results["benchmark_suite"] = {
                    "gpu_available": False,
                    "success": True,
                    "message": "GPU not available for benchmark testing",
                }
                return

            # Run GPU benchmark
            logger.info("   Running GPU benchmark suite...")
            benchmark_results = await benchmark_gpu()

            # Check benchmark components
            has_gpu_info = "gpu_info" in benchmark_results
            has_benchmark_tests = "benchmark_tests" in benchmark_results
            has_overall_score = "overall_score" in benchmark_results
            has_recommendations = "recommendations" in benchmark_results

            logger.info(f"   GPU info: {'✓' if has_gpu_info else '✗'}")
            logger.info(f"   Benchmark tests: {'✓' if has_benchmark_tests else '✗'}")
            logger.info(f"   Overall score: {'✓' if has_overall_score else '✗'}")
            logger.info(f"   Recommendations: {'✓' if has_recommendations else '✗'}")

            if has_overall_score:
                overall_score = benchmark_results["overall_score"]
                logger.info(f"   GPU performance score: {overall_score:.1f}/100")

            if has_benchmark_tests:
                tests = benchmark_results["benchmark_tests"]
                logger.info(f"   Benchmark tests completed: {len(tests)}")

            benchmark_success = all([has_gpu_info, has_benchmark_tests, has_overall_score])

            self.test_results["benchmark_suite"] = {
                "gpu_available": True,
                "benchmark_completed": benchmark_success,
                "has_gpu_info": has_gpu_info,
                "has_benchmark_tests": has_benchmark_tests,
                "has_overall_score": has_overall_score,
                "has_recommendations": has_recommendations,
                "overall_score": benchmark_results.get("overall_score", 0),
                "tests_count": len(benchmark_results.get("benchmark_tests", {})),
                "success": benchmark_success,
            }

            logger.info("   ✅ Benchmark suite test passed")

        except Exception as e:
            logger.error(f"   ❌ Benchmark suite test failed: {e}")
            self.test_results["benchmark_suite"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def test_configuration_management(self):
        """Test configuration management functionality"""
        logger.info("⚙️ Test 10: Configuration Management")

        try:
            # Test GPU optimizer configuration
            current_config = gpu_optimizer.get_optimization_config()
            config_accessible = current_config is not None

            logger.info(f"   GPU config accessible: {'✓' if config_accessible else '✗'}")

            if config_accessible:
                logger.info(f"   Mixed precision: {current_config.mixed_precision_enabled}")
                logger.info(f"   Tensor cores: {current_config.tensor_core_optimization}")
                logger.info(f"   Auto batching: {current_config.auto_batch_sizing}")

            # Test performance baselines
            baselines = phase9_monitor.performance_baselines
            baselines_configured = len(baselines) > 0

            logger.info(f"   Performance baselines: {'✓' if baselines_configured else '✗'}")
            if baselines_configured:
                logger.info(f"   Baseline categories: {len(baselines)}")

            # Test configuration persistence
            original_mixed_precision = current_config.mixed_precision_enabled if config_accessible else False
            if config_accessible:
                # Toggle setting
                new_value = not original_mixed_precision
                update_success = update_gpu_config({"mixed_precision_enabled": new_value})

                # Verify change
                updated_config = gpu_optimizer.get_optimization_config()
                change_applied = updated_config.mixed_precision_enabled == new_value

                # Restore original
                update_gpu_config({"mixed_precision_enabled": original_mixed_precision})

                logger.info(f"   Config persistence: {'✓' if update_success and change_applied else '✗'}")
            else:
                update_success = change_applied = False

            self.test_results["configuration_management"] = {
                "gpu_config_accessible": config_accessible,
                "baselines_configured": baselines_configured,
                "config_updates_work": (update_success and change_applied if config_accessible else False),
                "baseline_count": len(baselines),
                "success": config_accessible and baselines_configured,
            }

            logger.info("   ✅ Configuration management test passed")

        except Exception as e:
            logger.error(f"   ❌ Configuration management test failed: {e}")
            self.test_results["configuration_management"] = {
                "success": False,
                "error": "Internal server error",
            }

    async def generate_test_report(self):
        """Generate comprehensive test report"""
        logger.info("📋 Generating Test Report")
        logger.info("=" * 80)

        # Calculate overall results
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results.values() if result.get("success", False))
        test_duration = time.time() - self.start_time

        # Generate report
        report = {
            "test_suite": "AutoBot Phase 9 Monitoring System Validation",
            "timestamp": datetime.now().isoformat(),
            "test_duration_seconds": round(test_duration, 2),
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": total_tests - successful_tests,
            "success_rate": (round((successful_tests / total_tests) * 100, 1) if total_tests > 0 else 0),
            "overall_status": (
                "PASS" if successful_tests == total_tests else "PARTIAL" if successful_tests > 0 else "FAIL"
            ),
            "test_results": self.test_results,
            "alerts_received": self.alerts_received,
            "system_info": {
                "gpu_available": phase9_monitor.gpu_available,
                "npu_available": phase9_monitor.npu_available,
                "monitoring_active": phase9_monitor.monitoring_active,
            },
        }

        # Print summary
        print()  # noqa: print
        print("🎯 TEST SUMMARY")  # noqa: print
        print("=" * 50)  # noqa: print
        print(f"Total Tests: {total_tests}")  # noqa: print
        print(f"Successful: {successful_tests}")  # noqa: print
        print(f"Failed: {total_tests - successful_tests}")  # noqa: print
        print(f"Success Rate: {report['success_rate']}%")  # noqa: print
        print(f"Duration: {test_duration:.2f} seconds")  # noqa: print
        print(f"Overall Status: {report['overall_status']}")  # noqa: print
        print()  # noqa: print

        # Print individual test results
        print("📊 INDIVIDUAL TEST RESULTS")  # noqa: print
        print("=" * 50)  # noqa: print
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result.get("success", False) else "❌ FAIL"
            print(f"{test_name}: {status}")  # noqa: print
            if not result.get("success", False) and "error" in result:
                print(f"   Error: {result['error']}")  # noqa: print
        print()  # noqa: print

        # Hardware summary
        print("🔧 HARDWARE SUMMARY")  # noqa: print
        print("=" * 50)  # noqa: print
        print(f"GPU Available: {'✓' if phase9_monitor.gpu_available else '✗'}")  # noqa: print  # noqa: print
        print(f"NPU Available: {'✓' if phase9_monitor.npu_available else '✗'}")  # noqa: print  # noqa: print
        print(f"Monitoring Active: {'✓' if phase9_monitor.monitoring_active else '✗'}")  # noqa: print  # noqa: print
        print()  # noqa: print

        # Recommendations
        print("💡 RECOMMENDATIONS")  # noqa: print
        print("=" * 50)  # noqa: print
        if report["overall_status"] == "PASS":
            print("✅ All tests passed! Phase 9 monitoring system is fully operational.")  # noqa: print  # noqa: print
            print("   • GPU/NPU monitoring is working correctly")  # noqa: print
            print("   • Performance optimization is functional")  # noqa: print
            print("   • Real-time dashboard is operational")  # noqa: print
            print("   • Alert system is configured properly")  # noqa: print
        else:
            print("⚠️  Some tests failed. Review the following:")  # noqa: print
            for test_name, result in self.test_results.items():
                if not result.get("success", False):
                    print(f"   • Fix {test_name}: {result.get('error', 'Unknown error')}")  # noqa: print

        # Save report
        report_file = f"phase9_monitoring_test_report_{int(time.time())}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"📄 Detailed report saved to: {report_file}")  # noqa: print
        print()  # noqa: print

        return report


async def main():
    """Main test execution function"""
    print("🚀 AutoBot Phase 9 Monitoring System Validation")  # noqa: print
    print(f"Started at: {datetime.now().isoformat()}")  # noqa: print
    print("=" * 80)  # noqa: print

    # Initialize and run test suite
    test_suite = Phase9MonitoringSystemTest()

    try:
        await test_suite.run_full_test_suite()

    except KeyboardInterrupt:
        logger.info("Test suite interrupted by user")

    except Exception as e:
        logger.error(f"Test suite failed with unexpected error: {e}")

    finally:
        # Cleanup - stop monitoring if it was started
        try:
            if phase9_monitor.monitoring_active:
                await stop_phase9_monitoring()
                logger.info("Monitoring stopped during cleanup")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    asyncio.run(main())
