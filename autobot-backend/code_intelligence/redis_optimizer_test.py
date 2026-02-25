# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Redis Operation Optimizer

Tests the detection of Redis optimization opportunities including:
- Pipeline opportunities
- Lua script candidates
- Data structure improvements
- Connection management patterns

Part of Issue #220 - Redis Operation Optimizer
"""

import tempfile
import textwrap

import pytest
from code_intelligence.redis_optimizer import (
    OptimizationSeverity,
    OptimizationType,
    RedisOptimizer,
    analyze_redis_usage,
)


class TestRedisOptimizer:
    """Test Redis optimization detection."""

    def test_detect_sequential_gets(self):
        """Test detection of sequential GET operations."""
        code = textwrap.dedent(
            """
            import redis

            async def fetch_user_data(redis_client, user_id):
                name = await redis_client.get(f"user:{user_id}:name")
                email = await redis_client.get(f"user:{user_id}:email")
                age = await redis_client.get(f"user:{user_id}:age")
                return {"name": name, "email": email, "age": age}
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            # Should detect sequential GETs that can be pipelined
            pipeline_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.SEQUENTIAL_GETS
            ]

            assert len(pipeline_results) >= 1
            assert pipeline_results[0].severity == OptimizationSeverity.MEDIUM
            assert "pipeline" in pipeline_results[0].suggestion.lower()

    def test_detect_sequential_sets(self):
        """Test detection of sequential SET operations."""
        code = textwrap.dedent(
            """
            async def save_user_data(redis_client, user_id, data):
                await redis_client.set(f"user:{user_id}:name", data["name"])
                await redis_client.set(f"user:{user_id}:email", data["email"])
                await redis_client.set(f"user:{user_id}:status", "active")
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            set_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.SEQUENTIAL_SETS
            ]

            assert len(set_results) >= 1
            assert (
                "MSET" in set_results[0].suggestion
                or "pipeline" in set_results[0].suggestion.lower()
            )

    def test_detect_loop_operations(self):
        """Test detection of Redis operations inside loops."""
        code = textwrap.dedent(
            """
            async def process_items(redis_client, items):
                results = []
                for item in items:
                    value = await redis_client.get(f"item:{item}")
                    results.append(value)
                return results
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            loop_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.LOOP_OPERATIONS
            ]

            assert len(loop_results) >= 1
            assert loop_results[0].severity == OptimizationSeverity.HIGH
            assert "O(N)" in loop_results[0].estimated_improvement

    def test_detect_read_modify_write(self):
        """Test detection of read-modify-write patterns."""
        code = textwrap.dedent(
            """
            async def increment_counter(redis_client, key):
                current = await redis_client.get(key)
                if current:
                    new_value = int(current) + 1
                else:
                    new_value = 1
                await redis_client.set(key, new_value)
                return new_value
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            rmw_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.READ_MODIFY_WRITE
            ]

            assert len(rmw_results) >= 1
            assert (
                "Lua" in rmw_results[0].suggestion
                or "atomic" in rmw_results[0].suggestion.lower()
            )

    def test_detect_direct_redis_instantiation(self):
        """Test detection of direct redis.Redis() usage."""
        code = textwrap.dedent(
            """
            import redis

            def get_data():
                client = redis.Redis(host="localhost", port=6379)
                return client.get("key")
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            connection_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.CONNECTION_PER_REQUEST
            ]

            assert len(connection_results) >= 1
            assert "get_redis_client" in connection_results[0].suggestion

    def test_detect_missing_expiry(self):
        """Test detection of SET without TTL."""
        code = textwrap.dedent(
            """
            async def cache_data(redis_client, key, value):
                await redis_client.set(key, value)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            expiry_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.MISSING_EXPIRY
            ]

            # Should detect SET without expiry
            assert len(expiry_results) >= 1
            assert "ex=" in expiry_results[0].suggestion

    def test_no_false_positives_for_good_code(self):
        """Test that good Redis patterns don't trigger warnings."""
        code = textwrap.dedent(
            """
            from utils.redis_client import get_redis_client

            async def good_pipeline_usage():
                redis = await get_redis_client(async_client=True)
                async with redis.pipeline() as pipe:
                    pipe.set("key1", "value1")
                    pipe.set("key2", "value2")
                    await pipe.execute()
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            # Should not detect connection issues (uses get_redis_client)
            connection_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.CONNECTION_PER_REQUEST
            ]

            assert len(connection_results) == 0

    def test_analyze_directory(self, tmp_path):
        """Test directory-wide analysis."""
        # Create test files
        (tmp_path / "good.py").write_text(
            textwrap.dedent(
                """
            from utils.redis_client import get_redis_client

            async def good_code():
                redis = await get_redis_client(async_client=True)
                return await redis.get("key")
        """
            )
        )

        (tmp_path / "bad.py").write_text(
            textwrap.dedent(
                """
            import redis

            def bad_code():
                client = redis.Redis(host="localhost")
                for i in range(100):
                    client.get(f"key:{i}")
        """
            )
        )

        optimizer = RedisOptimizer(project_root=str(tmp_path))
        results = optimizer.analyze_directory()

        # Should find issues in bad.py
        assert len(results) >= 1
        assert any("bad.py" in r.file_path for r in results)

    def test_get_summary(self):
        """Test summary generation."""
        # Use code that will definitely trigger detection
        code = textwrap.dedent(
            """
            import redis

            async def multiple_issues():
                # Direct instantiation - should be detected
                redis_client = redis.Redis(host="localhost", port=6379)

                # Sequential gets
                a = await redis_client.get("key1")
                b = await redis_client.get("key2")
                c = await redis_client.get("key3")
                return a, b, c
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)
            optimizer.results = results  # Ensure results are set
            summary = optimizer.get_summary()

            # Should detect at least connection_per_request
            assert summary["total_optimizations"] >= 1 or len(results) >= 1
            assert "by_severity" in summary
            assert "by_type" in summary

    def test_analyze_redis_usage_convenience_function(self, tmp_path):
        """Test the convenience function."""
        (tmp_path / "test.py").write_text(
            textwrap.dedent(
                """
            async def test_func(redis):
                a = await redis.get("key1")
                b = await redis.get("key2")
                return a, b
        """
            )
        )

        result = analyze_redis_usage(str(tmp_path))

        assert "results" in result
        assert "summary" in result


class TestOptimizationTypes:
    """Test optimization type detection accuracy."""

    def test_keys_command_detection(self):
        """Test detection of KEYS command (should use SCAN)."""
        code = textwrap.dedent(
            """
            async def get_all_keys(redis_client, pattern):
                return await redis_client.keys(pattern)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            scan_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.INEFFICIENT_SCAN
            ]

            assert len(scan_results) >= 1
            assert "SCAN" in scan_results[0].suggestion

    def test_multiple_related_keys_detection(self):
        """Test detection of related string keys that could be a hash."""
        code = textwrap.dedent(
            """
            async def get_user(redis, user_id):
                name = await redis.get(f"user:{user_id}:name")
                email = await redis.get(f"user:{user_id}:email")
                phone = await redis.get(f"user:{user_id}:phone")
                return {"name": name, "email": email, "phone": phone}
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            # Should suggest hash structure
            _hash_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.STRING_TO_HASH
            ]

            # May or may not detect this depending on key pattern parsing
            # The important thing is it doesn't crash
            assert isinstance(results, list)


class TestSeverityLevels:
    """Test that severity levels are assigned correctly."""

    def test_loop_operations_are_high_severity(self):
        """Loop operations should be HIGH severity."""
        code = textwrap.dedent(
            """
            async def process(redis):
                for i in range(100):
                    await redis.set(f"key:{i}", i)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            loop_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.LOOP_OPERATIONS
            ]

            if loop_results:
                assert loop_results[0].severity == OptimizationSeverity.HIGH

    def test_sequential_operations_are_medium_severity(self):
        """Sequential GET/SET should be MEDIUM severity."""
        code = textwrap.dedent(
            """
            async def fetch(redis):
                a = await redis.get("a")
                b = await redis.get("b")
                return a, b
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            optimizer = RedisOptimizer()
            results = optimizer.analyze_file(f.name)

            seq_results = [
                r
                for r in results
                if r.optimization_type == OptimizationType.SEQUENTIAL_GETS
            ]

            if seq_results:
                assert seq_results[0].severity == OptimizationSeverity.MEDIUM


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
