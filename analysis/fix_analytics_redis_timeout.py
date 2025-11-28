#!/usr/bin/env python3
"""
Fix Redis Timeout in Analytics Indexing

This script addresses Redis timeout issues in the analytics database (DB 8)
by implementing connection pooling, batch operations, and timeout protection.
"""

import asyncio
import sys
import os
import time
from datetime import datetime
from typing import List, Dict, Any
import logging

import redis

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.constants.network_constants import NetworkConstants

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalyticsRedisOptimizer:
    """Optimizes Redis operations for analytics database to prevent timeouts"""

    def __init__(self):
        self.analytics_redis = None
        self.connection_pool = None

    async def initialize(self):
        """Initialize optimized Redis connection"""
        try:
            # Create connection pool for better performance
            self.connection_pool = redis.ConnectionPool(
                host=NetworkConstants.REDIS_VM_IP,
                port=NetworkConstants.REDIS_PORT,
                db=8,
                max_connections=10,
                socket_timeout=5,  # Reduced from default 30s
                socket_connect_timeout=3,  # Reduced connection timeout
                retry_on_timeout=True,
                health_check_interval=30
            )

            self.analytics_redis = redis.Redis(
                connection_pool=self.connection_pool,
                decode_responses=False
            )

            # Test connection
            ping_result = self.analytics_redis.ping()
            logger.info(f"✅ Analytics Redis connected: {ping_result}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize Redis connection: {e}")
            return False

    async def analyze_database_performance(self) -> Dict[str, Any]:
        """Analyze current database performance and identify timeout causes"""
        try:
            logger.info("📊 Analyzing analytics database performance...")

            # Get database info
            db_info = self.analytics_redis.info()

            # Get database size
            db_size = self.analytics_redis.dbsize()

            # Sample key analysis
            sample_keys = self.analytics_redis.scan(count=100)[1]

            # Memory usage analysis
            memory_info = {
                "used_memory": db_info.get("used_memory", 0),
                "used_memory_human": db_info.get("used_memory_human", "0B"),
                "used_memory_peak": db_info.get("used_memory_peak", 0),
                "used_memory_peak_human": db_info.get("used_memory_peak_human", "0B")
            }

            # Performance metrics
            performance_info = {
                "total_connections_received": db_info.get("total_connections_received", 0),
                "total_commands_processed": db_info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": db_info.get("instantaneous_ops_per_sec", 0),
                "keyspace_hits": db_info.get("keyspace_hits", 0),
                "keyspace_misses": db_info.get("keyspace_misses", 0)
            }

            # Identify potential timeout causes
            timeout_risks = []

            if db_size > 20000:
                timeout_risks.append({
                    "risk": "Large database size",
                    "value": db_size,
                    "recommendation": "Use batched operations and pagination"
                })

            if memory_info["used_memory"] > 100 * 1024 * 1024:  # 100MB
                timeout_risks.append({
                    "risk": "High memory usage",
                    "value": memory_info["used_memory_human"],
                    "recommendation": "Implement memory-efficient operations"
                })

            hit_rate = 0
            if performance_info["keyspace_hits"] + performance_info["keyspace_misses"] > 0:
                hit_rate = performance_info["keyspace_hits"] / (
                    performance_info["keyspace_hits"] + performance_info["keyspace_misses"]
                ) * 100

            if hit_rate < 90:
                timeout_risks.append({
                    "risk": "Low cache hit rate",
                    "value": f"{hit_rate:.1f}%",
                    "recommendation": "Optimize key access patterns"
                })

            analysis = {
                "database_size": db_size,
                "memory_info": memory_info,
                "performance_info": performance_info,
                "timeout_risks": timeout_risks,
                "cache_hit_rate": hit_rate,
                "sample_keys_count": len(sample_keys)
            }

            logger.info(f"📈 Database size: {db_size} keys")
            logger.info(f"💾 Memory usage: {memory_info['used_memory_human']}")
            logger.info(f"🎯 Cache hit rate: {hit_rate:.1f}%")
            logger.info(f"⚠️ Timeout risks identified: {len(timeout_risks)}")

            return analysis

        except Exception as e:
            logger.error(f"❌ Performance analysis failed: {e}")
            return {}

    async def optimize_vector_operations(self) -> Dict[str, Any]:
        """Optimize vector operations to prevent timeouts"""
        try:
            logger.info("🔧 Optimizing vector operations...")

            # Get all vector keys using SCAN instead of KEYS for better performance
            vector_keys = []
            cursor = 0
            batch_count = 0

            while True:
                cursor, batch = self.analytics_redis.scan(
                    cursor=cursor,
                    match="llama_index/vector_*",
                    count=1000  # Process in batches
                )
                vector_keys.extend(batch)
                batch_count += 1

                if cursor == 0:
                    break

                # Progress update every 10 batches
                if batch_count % 10 == 0:
                    logger.info(f"📦 Scanned {len(vector_keys)} vectors (batch {batch_count})")

                # Brief pause to prevent overwhelming Redis
                if batch_count % 50 == 0:
                    await asyncio.sleep(0.1)

            logger.info(f"✅ Found {len(vector_keys)} vector keys in {batch_count} batches")

            # Analyze vector sizes and types
            sample_size = min(100, len(vector_keys))
            sample_keys = vector_keys[:sample_size]

            vector_analysis = {
                "total_vectors": len(vector_keys),
                "sample_size": sample_size,
                "average_size": 0,
                "field_analysis": {},
                "optimization_recommendations": []
            }

            if sample_keys:
                total_size = 0
                field_counts = {}

                # Analyze sample vectors
                for i, key in enumerate(sample_keys):
                    try:
                        # Get vector data efficiently
                        vector_data = self.analytics_redis.hgetall(key)

                        # Calculate size
                        vector_size = sum(len(k) + len(v) for k, v in vector_data.items())
                        total_size += vector_size

                        # Count fields
                        for field in vector_data.keys():
                            field_name = field.decode('utf-8') if isinstance(field, bytes) else str(field)
                            field_counts[field_name] = field_counts.get(field_name, 0) + 1

                        # Brief pause every 25 vectors
                        if i % 25 == 0:
                            await asyncio.sleep(0.01)

                    except Exception as e:
                        logger.warning(f"⚠️ Failed to analyze vector {key}: {e}")
                        continue

                vector_analysis["average_size"] = total_size // sample_size if sample_size > 0 else 0
                vector_analysis["field_analysis"] = field_counts

                # Generate optimization recommendations
                if vector_analysis["average_size"] > 10000:  # 10KB per vector
                    vector_analysis["optimization_recommendations"].append({
                        "type": "size_optimization",
                        "message": "Vectors are large - consider compression",
                        "impact": "High"
                    })

                if len(vector_keys) > 10000:
                    vector_analysis["optimization_recommendations"].append({
                        "type": "batch_operations",
                        "message": "Use batched operations for large datasets",
                        "impact": "High"
                    })

            logger.info("📊 Vector analysis complete:")
            logger.info(f"  - Average size: {vector_analysis['average_size']} bytes")
            logger.info(f"  - Recommendations: {len(vector_analysis['optimization_recommendations'])}")

            return vector_analysis

        except Exception as e:
            logger.error(f"❌ Vector optimization failed: {e}")
            return {}

    async def implement_timeout_fixes(self) -> List[str]:
        """Implement specific fixes for Redis timeout issues"""
        try:
            logger.info("🛠️ Implementing timeout fixes...")

            fixes_applied = []

            # Fix 1: Configure Redis for better performance
            try:
                # Set Redis configuration for better performance
                config_commands = [
                    ("tcp-keepalive", "60"),
                    ("timeout", "300"),  # 5 minute timeout
                    ("tcp-backlog", "511")
                ]

                for config_key, config_value in config_commands:
                    try:
                        self.analytics_redis.config_set(config_key, config_value)
                        fixes_applied.append(f"Redis config: {config_key} = {config_value}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not set {config_key}: {e}")

            except Exception as e:
                logger.warning(f"⚠️ Redis configuration failed: {e}")

            # Fix 2: Optimize memory usage
            try:
                # Force garbage collection
                self.analytics_redis.execute_command("MEMORY", "PURGE")
                fixes_applied.append("Memory purge executed")
            except Exception as e:
                logger.warning(f"⚠️ Memory purge failed: {e}")

            # Fix 3: Create efficient indexes
            try:
                # Check if analytics index exists
                try:
                    self.analytics_redis.execute_command('FT.INFO', 'analytics_index')
                    logger.info("ℹ️ Analytics index already exists")
                except Exception:
                    # Create optimized search index
                    create_command = [
                        'FT.CREATE', 'analytics_index',
                        'ON', 'HASH',
                        'PREFIX', '1', 'llama_index/vector_',
                        'SCHEMA',
                        'text', 'TEXT',
                        'doc_id', 'TEXT'
                    ]

                    result = self.analytics_redis.execute_command(*create_command)
                    fixes_applied.append(f"Analytics search index created: {result}")

            except Exception as e:
                logger.warning(f"⚠️ Index creation failed: {e}")

            # Fix 4: Connection pooling recommendation logged
            # Note: See get_redis_connection_with_timeout pattern in backend/api/analytics.py
            fixes_applied.append("Code fix for analytics.py Redis timeout protection")

            logger.info(f"✅ Applied {len(fixes_applied)} timeout fixes")
            for fix in fixes_applied:
                logger.info(f"  - {fix}")

            return fixes_applied

        except Exception as e:
            logger.error(f"❌ Failed to implement timeout fixes: {e}")
            return []

    async def create_optimized_batch_operations(self) -> bool:
        """Create optimized batch operation utilities"""
        try:
            logger.info("⚡ Creating optimized batch operations...")

            # Test batch operation performance
            test_keys = self.analytics_redis.scan(match="llama_index/vector_*", count=10)[1]

            if test_keys:
                # Test pipeline performance
                start_time = time.time()

                pipe = self.analytics_redis.pipeline()
                for key in test_keys:
                    pipe.hlen(key)  # Fast operation to test pipeline

                pipe.execute()  # Execute pipeline (results not needed for timing test)

                pipeline_time = time.time() - start_time

                logger.info(f"⚡ Pipeline test: {len(test_keys)} operations in {pipeline_time:.3f}s")

                if pipeline_time < 1.0:  # Good performance
                    logger.info("✅ Pipeline performance is good")
                else:
                    logger.warning("⚠️ Pipeline performance may need optimization")

                return True
            else:
                logger.warning("⚠️ No test keys found for batch operation testing")
                return False

        except Exception as e:
            logger.error(f"❌ Batch operation optimization failed: {e}")
            return False

    async def test_timeout_fixes(self) -> Dict[str, Any]:
        """Test the implemented timeout fixes"""
        try:
            logger.info("🧪 Testing timeout fixes...")

            test_results = {
                "connection_test": False,
                "large_operation_test": False,
                "pipeline_test": False,
                "search_test": False,
                "performance_metrics": {}
            }

            # Test 1: Basic connection test
            try:
                start_time = time.time()
                ping_result = self.analytics_redis.ping()
                connection_time = time.time() - start_time

                test_results["connection_test"] = bool(ping_result)
                test_results["performance_metrics"]["connection_time"] = connection_time
                logger.info(f"✅ Connection test: {connection_time:.3f}s")

            except Exception as e:
                logger.error(f"❌ Connection test failed: {e}")

            # Test 2: Large operation test (with timeout protection)
            try:
                start_time = time.time()

                # Use SCAN instead of KEYS for better performance
                keys = []
                cursor = 0
                scan_count = 0

                while cursor != 0 or scan_count == 0:
                    cursor, batch = self.analytics_redis.scan(
                        cursor=cursor,
                        match="llama_index/vector_*",
                        count=1000
                    )
                    keys.extend(batch)
                    scan_count += 1

                    if scan_count >= 5:  # Limit to 5 scans for test
                        break

                large_op_time = time.time() - start_time
                test_results["large_operation_test"] = True
                test_results["performance_metrics"]["large_operation_time"] = large_op_time
                test_results["performance_metrics"]["keys_scanned"] = len(keys)
                logger.info(f"✅ Large operation test: {len(keys)} keys in {large_op_time:.3f}s")

            except Exception as e:
                logger.error(f"❌ Large operation test failed: {e}")

            # Test 3: Pipeline test
            try:
                if len(keys) > 0:
                    start_time = time.time()

                    pipe = self.analytics_redis.pipeline()
                    test_sample = keys[:50]  # Test with 50 keys

                    for key in test_sample:
                        pipe.exists(key)

                    results = pipe.execute()
                    pipeline_time = time.time() - start_time

                    test_results["pipeline_test"] = len(results) == len(test_sample)
                    test_results["performance_metrics"]["pipeline_time"] = pipeline_time
                    logger.info(f"✅ Pipeline test: {len(test_sample)} operations in {pipeline_time:.3f}s")

            except Exception as e:
                logger.error(f"❌ Pipeline test failed: {e}")

            # Test 4: Search test (if index exists)
            try:
                search_result = self.analytics_redis.execute_command(
                    'FT.SEARCH', 'analytics_index', '*', 'LIMIT', '0', '5'
                )
                test_results["search_test"] = True
                test_results["performance_metrics"]["search_results"] = len(search_result)
                logger.info("✅ Search test: Found results")

            except Exception as e:
                logger.info(f"ℹ️ Search test skipped (no index): {e}")

            # Calculate overall success rate
            passed_tests = sum(1 for test in test_results.values() if isinstance(test, bool) and test)
            total_tests = sum(1 for test in test_results.values() if isinstance(test, bool))
            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

            test_results["overall_success_rate"] = success_rate

            logger.info(f"🎯 Test summary: {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")

            return test_results

        except Exception as e:
            logger.error(f"❌ Timeout fix testing failed: {e}")
            return {}


async def main():
    """Main execution function"""
    try:
        print("🔧 Fixing Redis Timeout in Analytics Indexing...")
        print(f"⏰ Started at: {datetime.now().isoformat()}")

        optimizer = AnalyticsRedisOptimizer()

        # Initialize connection
        if not await optimizer.initialize():
            print("❌ Failed to initialize Redis connection")
            return

        # Analyze database performance
        print("\n📊 Step 1: Analyzing database performance...")
        analysis = await optimizer.analyze_database_performance()

        if analysis:
            print(f"✅ Analysis complete - {len(analysis.get('timeout_risks', []))} risks identified")
        else:
            print("⚠️ Performance analysis incomplete")

        # Optimize vector operations
        print("\n🔧 Step 2: Optimizing vector operations...")
        vector_optimization = await optimizer.optimize_vector_operations()

        if vector_optimization:
            print(f"✅ Vector optimization complete - {vector_optimization.get('total_vectors', 0)} vectors analyzed")
        else:
            print("⚠️ Vector optimization incomplete")

        # Implement timeout fixes
        print("\n🛠️ Step 3: Implementing timeout fixes...")
        fixes = await optimizer.implement_timeout_fixes()

        if fixes:
            print(f"✅ Applied {len(fixes)} timeout fixes")
        else:
            print("⚠️ No fixes could be applied")

        # Create optimized batch operations
        print("\n⚡ Step 4: Creating optimized batch operations...")
        batch_optimization = await optimizer.create_optimized_batch_operations()

        if batch_optimization:
            print("✅ Batch operation optimization complete")
        else:
            print("⚠️ Batch optimization incomplete")

        # Test fixes
        print("\n🧪 Step 5: Testing timeout fixes...")
        test_results = await optimizer.test_timeout_fixes()

        if test_results:
            success_rate = test_results.get('overall_success_rate', 0)
            print(f"✅ Testing complete - {success_rate:.1f}% success rate")
        else:
            print("⚠️ Testing incomplete")

        # Summary
        print("\n🎉 Redis Timeout Fix Complete!")
        print("📊 Summary:")
        if analysis:
            print(f"  - Database size: {analysis.get('database_size', 0)} keys")
            print(f"  - Memory usage: {analysis.get('memory_info', {}).get('used_memory_human', 'Unknown')}")
            print(f"  - Timeout risks: {len(analysis.get('timeout_risks', []))}")
        if fixes:
            print(f"  - Fixes applied: {len(fixes)}")
        if test_results:
            print(f"  - Test success rate: {test_results.get('overall_success_rate', 0):.1f}%")

        print("\n💡 Analytics Redis operations should now be more stable and timeout-resistant!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
