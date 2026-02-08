"""
Performance benchmarks for AutoBot system components
Tests performance characteristics, resource usage, and scalability
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import psutil
import pytest
from src.enhanced_memory_manager import EnhancedMemoryManager
from src.multimodal_processor import (
    ModalityType,
    MultiModalInput,
    ProcessingIntent,
    UnifiedMultiModalProcessor,
)
from src.utils.config_manager import ConfigManager

from backend.services.config_service import ConfigService


class TestSystemPerformanceBenchmarks:
    """Performance benchmarks for system components"""

    def measure_execution_time(self, func, *args, **kwargs):
        """Measure function execution time"""
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        return (
            result,
            (end_time - start_time) * 1000,
        )  # Return result and time in milliseconds

    async def measure_async_execution_time(self, coro):
        """Measure async function execution time"""
        start_time = time.time()
        result = await coro
        end_time = time.time()
        return (
            result,
            (end_time - start_time) * 1000,
        )  # Return result and time in milliseconds

    def measure_memory_usage(self, func, *args, **kwargs):
        """Measure memory usage during function execution"""
        process = psutil.Process()

        # Get initial memory usage
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Execute function
        result = func(*args, **kwargs)

        # Get final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = final_memory - initial_memory

        return result, memory_delta

    def test_config_manager_performance(self):
        """Test configuration manager performance"""
        config_manager = ConfigManager()

        # Test single config access performance
        _, access_time = self.measure_execution_time(
            config_manager.get, "llm.orchestrator_llm"
        )
        assert access_time < 1.0, f"Config access too slow: {access_time}ms"

        # Test bulk config access performance
        def bulk_access():
            results = []
            for i in range(100):
                results.append(config_manager.get(f"test.key.{i}", f"default_{i}"))
            return results

        _, bulk_time = self.measure_execution_time(bulk_access)
        assert bulk_time < 50.0, f"Bulk config access too slow: {bulk_time}ms"

        # Test section retrieval performance
        _, section_time = self.measure_execution_time(
            config_manager.get_section, "multimodal"
        )
        assert section_time < 2.0, f"Section retrieval too slow: {section_time}ms"

    def test_config_service_caching_performance(self):
        """Test config service caching performance"""
        config_service = ConfigService()

        # First call should be slower (no cache)
        _, first_call_time = self.measure_execution_time(
            config_service.get_all_settings
        )

        # Second call should be faster (cached)
        _, cached_call_time = self.measure_execution_time(
            config_service.get_all_settings
        )

        # Cached call should be at least 50% faster
        assert (
            cached_call_time < first_call_time * 0.5
        ), f"Caching not effective: first={first_call_time}ms, cached={cached_call_time}ms"

        # Cached calls should be very fast
        assert (
            cached_call_time < 5.0
        ), f"Cached config access too slow: {cached_call_time}ms"

    @pytest.mark.asyncio
    async def test_multimodal_processor_performance(self):
        """Test multi-modal processor performance"""
        processor = UnifiedMultiModalProcessor()

        # Test single processing performance
        test_input = MultiModalInput(
            input_id="perf_test_001",
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            data="Test processing performance",
        )

        # Mock the context processor for consistent timing
        with patch.object(
            processor.context_processor, "process", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = Mock(
                success=True,
                confidence=0.8,
                processing_time=0.1,
                result_data={"decision": "test"},
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                result_id="test",
            )

            result, processing_time = await self.measure_async_execution_time(
                processor.process(test_input)
            )

            assert (
                processing_time < 100.0
            ), f"Single processing too slow: {processing_time}ms"
            assert result.success is True

    @pytest.mark.asyncio
    async def test_concurrent_processing_performance(self):
        """Test concurrent processing performance"""
        processor = UnifiedMultiModalProcessor()

        # Create multiple test inputs
        inputs = [
            MultiModalInput(
                input_id=f"concurrent_test_{i}",
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                data=f"Concurrent test {i}",
            )
            for i in range(10)
        ]

        # Mock processors for consistent results
        with patch.object(
            processor.context_processor, "process", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = Mock(
                success=True,
                confidence=0.8,
                processing_time=0.05,
                result_data={"decision": "test"},
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                result_id="test",
            )

            # Process all inputs concurrently
            start_time = time.time()
            tasks = [processor.process(inp) for inp in inputs]
            results = await asyncio.gather(*tasks)
            end_time = time.time()

            total_time = (end_time - start_time) * 1000  # Convert to ms

            # Concurrent processing should be faster than sequential
            assert total_time < 500.0, f"Concurrent processing too slow: {total_time}ms"
            assert len(results) == 10
            assert all(r.success for r in results)

    def test_memory_manager_performance(self):
        """Test memory manager performance"""
        memory_manager = EnhancedMemoryManager()

        # Test memory usage during task storage
        def store_multiple_tasks():
            for i in range(50):
                asyncio.run(
                    memory_manager.store_task(
                        task_id=f"perf_task_{i}",
                        task_type="performance_test",
                        description=f"Performance test task {i}",
                        status="completed",
                        priority=memory_manager.TaskPriority.MEDIUM,
                        subtasks=[],
                        context={"test": f"data_{i}"},
                        execution_details={"result": f"success_{i}"},
                    )
                )

        _, memory_usage = self.measure_memory_usage(store_multiple_tasks)

        # Memory usage should be reasonable (less than 50MB for 50 tasks)
        assert memory_usage < 50.0, f"Memory usage too high: {memory_usage}MB"

    def test_config_validation_performance(self):
        """Test configuration validation performance"""
        config_manager = ConfigManager()

        # Test validation performance
        _, validation_time = self.measure_execution_time(config_manager.validate_config)

        assert (
            validation_time < 10.0
        ), f"Config validation too slow: {validation_time}ms"

        # Test multiple validations (should be consistent)
        validation_times = []
        for _ in range(5):
            _, time_taken = self.measure_execution_time(config_manager.validate_config)
            validation_times.append(time_taken)

        avg_validation_time = sum(validation_times) / len(validation_times)
        assert (
            avg_validation_time < 15.0
        ), f"Average validation time too slow: {avg_validation_time}ms"

    def test_environment_variable_parsing_performance(self):
        """Test environment variable parsing performance"""
        config_manager = ConfigManager()

        # Test parsing different value types
        test_values = [
            ("true", bool),
            ("false", bool),
            ("12345", int),
            ("3.14159", float),
            ("item1,item2,item3", list),
            ("simple_string", str),
        ]

        total_parse_time = 0
        for value, expected_type in test_values:
            _, parse_time = self.measure_execution_time(
                config_manager._parse_env_value, value
            )
            total_parse_time += parse_time

            # Each parse should be very fast
            assert (
                parse_time < 1.0
            ), f"Environment value parsing too slow: {parse_time}ms for {value}"

        # Total parsing time should be minimal
        assert (
            total_parse_time < 5.0
        ), f"Total parsing time too slow: {total_parse_time}ms"

    @pytest.mark.asyncio
    async def test_system_startup_performance(self):
        """Test system component startup performance"""
        # Test config manager startup
        start_time = time.time()
        ConfigManager()
        config_startup_time = (time.time() - start_time) * 1000

        assert (
            config_startup_time < 100.0
        ), f"Config manager startup too slow: {config_startup_time}ms"

        # Test multimodal processor startup
        start_time = time.time()
        UnifiedMultiModalProcessor()
        processor_startup_time = (time.time() - start_time) * 1000

        assert (
            processor_startup_time < 500.0
        ), f"Multimodal processor startup too slow: {processor_startup_time}ms"

        # Test memory manager startup
        start_time = time.time()
        EnhancedMemoryManager()
        memory_startup_time = (time.time() - start_time) * 1000

        assert (
            memory_startup_time < 200.0
        ), f"Memory manager startup too slow: {memory_startup_time}ms"

    def test_configuration_file_loading_performance(self):
        """Test configuration file loading performance"""
        import tempfile

        import yaml

        # Create a large test configuration file
        large_config = {
            "section_"
            + str(i): {
                "subsection_"
                + str(j): {"value_" + str(k): f"data_{i}_{j}_{k}" for k in range(10)}
                for j in range(10)
            }
            for i in range(20)
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(large_config, f)
            config_file = f.name

        try:
            # Test loading performance
            _, load_time = self.measure_execution_time(
                ConfigManager, config_file=config_file
            )

            assert (
                load_time < 1000.0
            ), f"Large config file loading too slow: {load_time}ms"

        finally:
            import os

            os.unlink(config_file)

    def test_statistics_tracking_performance(self):
        """Test performance statistics tracking overhead"""
        processor = UnifiedMultiModalProcessor()

        # Create mock results for statistics
        mock_results = [
            Mock(
                success=True,
                modality_type=ModalityType.TEXT,
                processing_time=0.1 + (i * 0.01),
            )
            for i in range(100)
        ]

        # Test stats update performance
        start_time = time.time()
        for result in mock_results:
            processor._update_stats(result)
        stats_time = (time.time() - start_time) * 1000

        # Stats tracking should have minimal overhead
        assert (
            stats_time < 10.0
        ), f"Statistics tracking too slow: {stats_time}ms for 100 updates"

        # Verify stats are correct
        stats = processor.get_stats()
        assert stats["total_processed"] == 100
        assert stats["successful_processed"] == 100
        assert stats["failed_processed"] == 0

    def test_config_get_performance_with_deep_nesting(self):
        """Test configuration access performance with deeply nested keys"""
        config_manager = ConfigManager()

        # Set deeply nested configuration
        config_manager.set("level1.level2.level3.level4.level5.deep_value", "test_data")

        # Test deep access performance
        _, deep_access_time = self.measure_execution_time(
            config_manager.get, "level1.level2.level3.level4.level5.deep_value"
        )

        assert (
            deep_access_time < 5.0
        ), f"Deep config access too slow: {deep_access_time}ms"

        # Test bulk deep access
        def bulk_deep_access():
            results = []
            for i in range(50):
                key = f"level1.level2.level3.level4.level5.value_{i}"
                results.append(config_manager.get(key, f"default_{i}"))
            return results

        _, bulk_deep_time = self.measure_execution_time(bulk_deep_access)
        assert bulk_deep_time < 25.0, f"Bulk deep access too slow: {bulk_deep_time}ms"


class TestScalabilityBenchmarks:
    """Test system scalability characteristics"""

    def test_config_scalability_with_many_keys(self):
        """Test config manager scalability with many configuration keys"""
        config_manager = ConfigManager()

        # Add many configuration keys
        num_keys = 1000
        start_time = time.time()

        for i in range(num_keys):
            config_manager.set(f"scale_test.section_{i // 100}.key_{i}", f"value_{i}")

        set_time = (time.time() - start_time) * 1000

        # Setting 1000 keys should be reasonable
        assert set_time < 500.0, f"Setting {num_keys} keys too slow: {set_time}ms"

        # Test retrieval performance with many keys
        start_time = time.time()
        for i in range(0, num_keys, 10):  # Test every 10th key
            value = config_manager.get(f"scale_test.section_{i // 100}.key_{i}")
            assert value == f"value_{i}"

        get_time = (time.time() - start_time) * 1000
        assert (
            get_time < 100.0
        ), f"Getting keys with many configs too slow: {get_time}ms"

    @pytest.mark.asyncio
    async def test_multimodal_processor_scalability(self):
        """Test multi-modal processor scalability with many concurrent requests"""
        processor = UnifiedMultiModalProcessor()

        # Create many test inputs
        num_inputs = 50
        inputs = [
            MultiModalInput(
                input_id=f"scale_test_{i}",
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                data=f"Scale test {i}",
            )
            for i in range(num_inputs)
        ]

        # Mock processor for consistent results
        with patch.object(
            processor.context_processor, "process", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = Mock(
                success=True,
                confidence=0.8,
                processing_time=0.02,
                result_data={"decision": "test"},
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                result_id="test",
            )

            # Process all inputs concurrently
            start_time = time.time()
            tasks = [processor.process(inp) for inp in inputs]
            results = await asyncio.gather(*tasks)
            total_time = (time.time() - start_time) * 1000

            # Should handle many concurrent requests efficiently
            assert (
                total_time < 2000.0
            ), f"Scaling to {num_inputs} requests too slow: {total_time}ms"
            assert len(results) == num_inputs
            assert all(r.success for r in results)

    def test_memory_usage_stability(self):
        """Test memory usage stability under load"""
        import gc

        config_manager = ConfigManager()
        process = psutil.Process()

        # Get baseline memory
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024

        # Perform many operations
        for iteration in range(10):
            # Add many configs
            for i in range(100):
                config_manager.set(f"memory_test.iter_{iteration}.key_{i}", f"data_{i}")

            # Get many configs
            for i in range(100):
                config_manager.get(f"memory_test.iter_{iteration}.key_{i}")

            # Get sections
            for i in range(10):
                config_manager.get_section(f"memory_test.iter_{iteration}")

        # Check final memory
        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory

        # Memory growth should be reasonable (less than 100MB)
        assert memory_growth < 100.0, f"Excessive memory growth: {memory_growth}MB"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
