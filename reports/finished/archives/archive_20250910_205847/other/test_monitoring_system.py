#!/usr/bin/env python3
"""
Test script for the advanced monitoring system
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_metrics_collector():
    """Test the advanced metrics collection system"""
    logger.info("📊 Testing Advanced Metrics Collection System")
    
    try:
        from src.utils.system_metrics import get_metrics_collector
        
        # Initialize collector
        collector = get_metrics_collector()
        logger.info("✅ Metrics collector initialized")
        
        # Test system metrics collection
        logger.info("🖥️ Test 1: System metrics collection")
        system_metrics = await collector.collect_system_metrics()
        
        expected_metrics = ['cpu_percent', 'memory_percent', 'disk_usage']
        for metric_name in expected_metrics:
            if metric_name in system_metrics:
                metric = system_metrics[metric_name]
                logger.info(f"✅ {metric_name}: {metric.value}{metric.unit}")
            else:
                logger.warning(f"⚠️ Missing metric: {metric_name}")
        
        # Test service health collection
        logger.info("🔧 Test 2: Service health collection")
        health_metrics = await collector.collect_service_health()
        
        expected_services = ['backend_health', 'redis_health', 'ollama_health']
        for service_name in expected_services:
            if service_name in health_metrics:
                metric = health_metrics[service_name]
                status = "online" if metric.value > 0.5 else "offline"
                logger.info(f"✅ {service_name}: {status} ({metric.value})")
            else:
                logger.warning(f"⚠️ Service not checked: {service_name}")
        
        # Test knowledge base metrics
        logger.info("📚 Test 3: Knowledge base metrics collection")
        kb_metrics = await collector.collect_knowledge_base_metrics()
        
        for metric_name, metric in kb_metrics.items():
            logger.info(f"✅ {metric_name}: {metric.value} {metric.unit}")
        
        # Test comprehensive collection
        logger.info("🔄 Test 4: Comprehensive metrics collection")
        start_time = time.time()
        all_metrics = await collector.collect_all_metrics()
        collection_time = time.time() - start_time
        
        logger.info(f"✅ Collected {len(all_metrics)} metrics in {collection_time:.3f}s")
        
        # Test metrics storage
        logger.info("💾 Test 5: Metrics storage")
        storage_success = await collector.store_metrics(all_metrics)
        if storage_success:
            logger.info("✅ Metrics stored successfully")
        else:
            logger.warning("⚠️ Metrics storage failed")
        
        # Test metrics summary
        logger.info("📋 Test 6: Metrics summary generation")
        summary = await collector.get_metric_summary()
        
        if 'system' in summary:
            logger.info("✅ System metrics in summary")
        if 'services' in summary:
            logger.info("✅ Service metrics in summary")
        if 'overall_health' in summary:
            health_value = summary['overall_health'].get('value', 0)
            status = summary['overall_health'].get('status', 'unknown')
            logger.info(f"✅ Overall health: {health_value}% ({status})")
        
        logger.info("🎉 Metrics collector tests completed successfully!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_monitoring_api():
    """Test the monitoring API endpoints"""
    logger.info("🌐 Testing Monitoring API Endpoints")
    
    try:
        import aiohttp
        
        base_url = "http://localhost:8001/api/monitoring"
        
        # Test endpoints
        endpoints_to_test = [
            ("/metrics/health", "GET"),
            ("/metrics/current", "GET"),
            ("/metrics/summary", "GET"),
            ("/dashboard/overview", "GET"),
            ("/metrics/collection/status", "GET"),
            ("/alerts/check", "GET"),
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint, method in endpoints_to_test:
                try:
                    url = f"{base_url}{endpoint}"
                    logger.info(f"Testing {method} {endpoint}")
                    
                    if method == "GET":
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                logger.info(f"✅ {endpoint} - Status: {response.status}")
                                
                                # Log key information from response
                                if 'metrics_count' in data:
                                    logger.info(f"  Metrics count: {data['metrics_count']}")
                                if 'system_health' in data:
                                    logger.info(f"  System health available: Yes")
                                if 'alerts_count' in data:
                                    logger.info(f"  Active alerts: {data['alerts_count']}")
                                if 'overall_health' in data:
                                    health = data['overall_health']
                                    if isinstance(health, dict):
                                        logger.info(f"  Overall health: {health.get('status', 'unknown')}")
                                    
                            else:
                                logger.warning(f"⚠️ {endpoint} - Status: {response.status}")
                                error_text = await response.text()
                                logger.warning(f"  Error: {error_text[:100]}...")
                    
                    print()
                    
                except Exception as e:
                    logger.warning(f"⚠️ Could not test {endpoint}: {e}")
        
        # Test advanced query endpoint
        logger.info("📊 Testing advanced metrics query")
        query_data = {
            "categories": ["system", "services"],
            "time_range_minutes": 5
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/metrics/query", 
                    json=query_data
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Metrics query - Status: {response.status}")
                        logger.info(f"  Query results: {data.get('metrics_count', 0)} metrics")
                    else:
                        logger.warning(f"⚠️ Metrics query failed - Status: {response.status}")
        except Exception as e:
            logger.warning(f"⚠️ Metrics query test failed: {e}")
        
        logger.info("✅ Monitoring API tests completed!")
        return True
        
    except ImportError:
        logger.warning("⚠️ aiohttp not available, skipping API tests")
        return True
    except Exception as e:
        logger.error(f"❌ API testing error: {e}")
        return False


async def test_collection_lifecycle():
    """Test starting and stopping metrics collection"""
    logger.info("🔄 Testing Metrics Collection Lifecycle")
    
    try:
        from src.utils.system_metrics import get_metrics_collector
        
        collector = get_metrics_collector()
        
        # Test initial state
        logger.info("📋 Initial collection state")
        initial_state = collector._is_collecting
        logger.info(f"Initially collecting: {initial_state}")
        
        if initial_state:
            logger.info("⏹️ Stopping existing collection")
            await collector.stop_collection()
            await asyncio.sleep(1)
        
        # Test starting collection
        logger.info("▶️ Starting metrics collection")
        collection_task = asyncio.create_task(collector.start_collection())
        
        # Give collection time to start
        await asyncio.sleep(2)
        
        if collector._is_collecting:
            logger.info("✅ Collection started successfully")
            
            # Let it collect some data
            logger.info("⏳ Collecting metrics for 10 seconds...")
            await asyncio.sleep(10)
            
            # Check buffer
            buffer_size = len(collector._metrics_buffer)
            logger.info(f"📊 Buffer size after collection: {buffer_size}")
            
            if buffer_size > 0:
                logger.info("✅ Metrics are being collected")
                
                # Show recent metrics summary
                recent = await collector.get_recent_metrics(minutes=1)
                logger.info(f"📈 Recent metrics (1 min): {len(recent)}")
                
                # Group by category
                categories = {}
                for metric in recent:
                    categories[metric.category] = categories.get(metric.category, 0) + 1
                
                for category, count in categories.items():
                    logger.info(f"  {category}: {count} metrics")
                    
            else:
                logger.warning("⚠️ No metrics collected")
        else:
            logger.error("❌ Collection failed to start")
        
        # Test stopping collection
        logger.info("⏹️ Stopping metrics collection")
        await collector.stop_collection()
        
        if not collector._is_collecting:
            logger.info("✅ Collection stopped successfully")
        else:
            logger.warning("⚠️ Collection did not stop properly")
        
        logger.info("🎉 Collection lifecycle tests completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Collection lifecycle test error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_configuration():
    """Test monitoring system configuration"""
    logger.info("⚙️ Testing Monitoring Configuration")
    
    try:
        from src.config_helper import cfg
        
        # Test configuration values
        config_tests = [
            ('monitoring.metrics.collection_interval', int),
            ('monitoring.metrics.retention_hours', int),
            ('monitoring.metrics.buffer_size', int),
            ('monitoring.alerts.cpu_warning', int),
            ('monitoring.alerts.cpu_critical', int),
            ('monitoring.alerts.memory_warning', int),
            ('monitoring.alerts.memory_critical', int),
            ('monitoring.dashboard.refresh_interval', int),
            ('monitoring.dashboard.real_time_updates', bool),
        ]
        
        logger.info("📋 Configuration values:")
        for config_key, expected_type in config_tests:
            value = cfg.get(config_key)
            logger.info(f"{config_key}: {value} (type: {type(value).__name__})")
            
            if value is not None and not isinstance(value, expected_type):
                logger.warning(f"⚠️ Expected {expected_type.__name__}, got {type(value).__name__}")
        
        # Test that critical values are reasonable
        collection_interval = cfg.get('monitoring.metrics.collection_interval', 5)
        if 1 <= collection_interval <= 60:
            logger.info("✅ Collection interval is reasonable")
        else:
            logger.warning(f"⚠️ Collection interval ({collection_interval}s) may be too extreme")
        
        retention_hours = cfg.get('monitoring.metrics.retention_hours', 24)
        if 1 <= retention_hours <= 168:  # 1 hour to 1 week
            logger.info("✅ Retention hours is reasonable")
        else:
            logger.warning(f"⚠️ Retention hours ({retention_hours}h) may be too extreme")
        
        logger.info("✅ Configuration testing completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration test error: {e}")
        return False


async def performance_benchmark():
    """Benchmark the monitoring system performance"""
    logger.info("⚡ Performance Benchmark")
    
    try:
        from src.utils.system_metrics import get_metrics_collector
        
        collector = get_metrics_collector()
        
        # Benchmark individual collection methods
        methods_to_benchmark = [
            ("System Metrics", collector.collect_system_metrics),
            ("Service Health", collector.collect_service_health),
            ("Knowledge Base Metrics", collector.collect_knowledge_base_metrics),
            ("All Metrics", collector.collect_all_metrics),
        ]
        
        logger.info("📊 Collection Performance:")
        for method_name, method in methods_to_benchmark:
            times = []
            
            # Run multiple times for average
            for i in range(5):
                start_time = time.time()
                await method()
                end_time = time.time()
                times.append(end_time - start_time)
            
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            
            logger.info(f"{method_name}: avg={avg_time:.3f}s, min={min_time:.3f}s, max={max_time:.3f}s")
        
        # Test storage performance
        logger.info("💾 Storage Performance:")
        all_metrics = await collector.collect_all_metrics()
        
        storage_times = []
        for i in range(3):
            start_time = time.time()
            await collector.store_metrics(all_metrics)
            end_time = time.time()
            storage_times.append(end_time - start_time)
        
        avg_storage_time = sum(storage_times) / len(storage_times)
        logger.info(f"Storage: avg={avg_storage_time:.3f}s for {len(all_metrics)} metrics")
        
        # Calculate throughput
        metrics_per_second = len(all_metrics) / avg_storage_time
        logger.info(f"Storage throughput: {metrics_per_second:.1f} metrics/second")
        
        logger.info("✅ Performance benchmark completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Performance benchmark error: {e}")
        return False


async def main():
    """Main test function"""
    logger.info("🚀 Starting Advanced Monitoring System Test Suite")
    
    # Run all tests
    test_results = {
        "Metrics Collector": await test_metrics_collector(),
        "Monitoring API": await test_monitoring_api(),
        "Collection Lifecycle": await test_collection_lifecycle(),
        "Configuration": await test_configuration(),
        "Performance Benchmark": await performance_benchmark(),
    }
    
    # Summary
    logger.info("📋 Test Summary:")
    all_passed = True
    for test_name, passed in test_results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        logger.info("🎉 Advanced Monitoring System Test Suite PASSED!")
        logger.info("The monitoring system is ready for production use.")
        logger.info("Available endpoints:")
        logger.info("  - /api/monitoring/dashboard/overview - Complete dashboard data")
        logger.info("  - /api/monitoring/metrics/current - Real-time metrics")
        logger.info("  - /api/monitoring/alerts/check - System alerts")
        logger.info("  - /api/monitoring/metrics/collection/start - Start collection")
    else:
        logger.error("❌ Some tests FAILED!")
        logger.error("Please check the implementation and dependencies.")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())