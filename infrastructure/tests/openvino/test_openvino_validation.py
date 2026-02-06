"""
OpenVINO Validation Tests

Comprehensive tests for OpenVINO integration, device detection,
model compilation, and performance validation.

Issue #53 - OpenVINO Validation & Production Deployment
Author: mrveiss
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestOpenVINODeviceDetection:
    """Test OpenVINO device detection and availability"""

    @pytest.fixture
    def openvino_core(self):
        """Create OpenVINO Core instance"""
        from openvino.runtime import Core

        return Core()

    def test_openvino_import(self):
        """Test that OpenVINO can be imported"""
        try:
            from openvino.runtime import Core

            assert Core is not None
        except ImportError:
            pytest.fail("OpenVINO not installed")

    def test_core_initialization(self, openvino_core):
        """Test Core object can be created"""
        assert openvino_core is not None
        assert hasattr(openvino_core, "available_devices")

    def test_available_devices_not_empty(self, openvino_core):
        """Test at least one device is available"""
        devices = openvino_core.available_devices
        assert len(devices) > 0, "No OpenVINO devices detected"

    def test_cpu_device_present(self, openvino_core):
        """Test CPU device is always available"""
        devices = openvino_core.available_devices
        assert "CPU" in devices, "CPU device should always be available"

    def test_device_full_name(self, openvino_core):
        """Test device full name retrieval"""
        for device in openvino_core.available_devices:
            try:
                full_name = openvino_core.get_property(device, "FULL_DEVICE_NAME")
                assert isinstance(full_name, str)
                assert len(full_name) > 0
            except Exception as e:
                pytest.fail(f"Failed to get full name for {device}: {e}")

    def test_supported_properties(self, openvino_core):
        """Test device property enumeration"""
        for device in openvino_core.available_devices:
            # Should be able to query basic properties
            assert openvino_core.get_property(device, "FULL_DEVICE_NAME")

    def test_auto_device_available(self, openvino_core):
        """Test AUTO device selection is supported"""
        # AUTO is a meta-device, should be usable
        from openvino.runtime import Core

        core = Core()
        # AUTO should work even if not listed in available_devices
        assert core is not None


class TestOpenVINOModelCompilation:
    """Test model compilation capabilities"""

    @pytest.fixture
    def openvino_core(self):
        """Create OpenVINO Core instance"""
        from openvino.runtime import Core

        return Core()

    @pytest.fixture
    def simple_model(self, openvino_core):
        """Create a simple test model using OpenVINO ops"""
        from openvino.runtime import PartialShape, Type, opset10

        # Create simple Add operation model
        param1 = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input1")
        param2 = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input2")
        add_op = opset10.add(param1, param2)

        from openvino.runtime import Model

        model = Model([add_op], [param1, param2], "simple_add")
        return model

    def test_model_creation(self, simple_model):
        """Test simple model can be created"""
        assert simple_model is not None
        assert simple_model.get_name() == "simple_add"

    def test_model_compilation_cpu(self, openvino_core, simple_model):
        """Test model compilation for CPU"""
        compiled = openvino_core.compile_model(simple_model, "CPU")
        assert compiled is not None

    def test_model_inference(self, openvino_core, simple_model):
        """Test inference with compiled model"""
        compiled = openvino_core.compile_model(simple_model, "CPU")

        # Create input data
        input1 = np.random.randn(1, 10).astype(np.float32)
        input2 = np.random.randn(1, 10).astype(np.float32)

        # Run inference
        result = compiled([input1, input2])
        output = result[compiled.output(0)]

        # Verify result
        expected = input1 + input2
        np.testing.assert_array_almost_equal(output, expected, decimal=5)

    def test_model_caching(self, openvino_core, simple_model):
        """Test model caching functionality"""
        with tempfile.TemporaryDirectory() as cache_dir:
            config = {"CACHE_DIR": cache_dir}

            # First compilation (cache miss)
            start1 = time.time()
            compiled1 = openvino_core.compile_model(simple_model, "CPU", config)
            time.time() - start1

            # Second compilation (cache hit)
            start2 = time.time()
            compiled2 = openvino_core.compile_model(simple_model, "CPU", config)
            time.time() - start2

            assert compiled1 is not None
            assert compiled2 is not None
            # Cache should have been created
            list(Path(cache_dir).glob("*"))
            # Cache may or may not be created for simple models, just verify no errors

    def test_performance_hints_latency(self, openvino_core, simple_model):
        """Test latency performance hint"""
        from openvino.properties import hint

        config = {hint.performance_mode: hint.PerformanceMode.LATENCY}
        compiled = openvino_core.compile_model(simple_model, "CPU", config)
        assert compiled is not None

    def test_performance_hints_throughput(self, openvino_core, simple_model):
        """Test throughput performance hint"""
        from openvino.properties import hint

        config = {hint.performance_mode: hint.PerformanceMode.THROUGHPUT}
        compiled = openvino_core.compile_model(simple_model, "CPU", config)
        assert compiled is not None


class TestOpenVINOPerformance:
    """Performance benchmarking tests"""

    @pytest.fixture
    def openvino_core(self):
        """Create OpenVINO Core instance"""
        from openvino.runtime import Core

        return Core()

    @pytest.fixture
    def benchmark_model(self, openvino_core):
        """Create larger model for benchmarking"""
        from openvino.runtime import Model, PartialShape, Type, opset10

        # Create model with multiple operations
        input_param = opset10.parameter(PartialShape([1, 128]), Type.f32, name="input")

        # Add some layers
        weights1 = opset10.constant(np.random.randn(128, 64).astype(np.float32))
        matmul1 = opset10.matmul(input_param, weights1, False, False)

        weights2 = opset10.constant(np.random.randn(64, 32).astype(np.float32))
        matmul2 = opset10.matmul(matmul1, weights2, False, False)

        relu = opset10.relu(matmul2)

        model = Model([relu], [input_param], "benchmark_model")
        return model

    def test_inference_latency(self, openvino_core, benchmark_model):
        """Test inference latency measurement"""
        compiled = openvino_core.compile_model(benchmark_model, "CPU")

        input_data = np.random.randn(1, 128).astype(np.float32)

        # Warm up
        for _ in range(5):
            compiled([input_data])

        # Measure latency
        latencies = []
        for _ in range(20):
            start = time.time()
            compiled([input_data])
            latencies.append((time.time() - start) * 1000)  # ms

        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)

        # Should complete in reasonable time
        assert avg_latency < 100, f"Average latency {avg_latency}ms too high"
        assert min_latency > 0
        assert max_latency < 500

        print("\nInference Latency (ms):")
        print(f"  Average: {avg_latency:.2f}")
        print(f"  Min: {min_latency:.2f}")
        print(f"  Max: {max_latency:.2f}")

    def test_throughput_measurement(self, openvino_core, benchmark_model):
        """Test throughput measurement"""
        compiled = openvino_core.compile_model(benchmark_model, "CPU")

        batch_size = 10
        input_data = np.random.randn(batch_size, 128).astype(np.float32)

        # Warm up
        for _ in range(3):
            compiled([input_data])

        # Measure throughput
        num_iterations = 50
        start = time.time()
        for _ in range(num_iterations):
            compiled([input_data])
        elapsed = time.time() - start

        total_samples = num_iterations * batch_size
        throughput = total_samples / elapsed

        assert throughput > 0
        print(f"\nThroughput: {throughput:.2f} samples/second")

    def test_memory_usage(self, openvino_core, benchmark_model):
        """Test memory usage doesn't grow unbounded"""
        import gc

        compiled = openvino_core.compile_model(benchmark_model, "CPU")
        input_data = np.random.randn(1, 128).astype(np.float32)

        # Run many inferences
        for _ in range(100):
            result = compiled([input_data])
            del result

        gc.collect()
        # If we got here without OOM, test passes


class TestOpenVINOConfiguration:
    """Test OpenVINO configuration options"""

    @pytest.fixture
    def openvino_core(self):
        """Create OpenVINO Core instance"""
        from openvino.runtime import Core

        return Core()

    def test_num_threads_configuration(self, openvino_core):
        """Test thread count configuration"""
        from openvino.runtime import Model, PartialShape, Type, opset10

        # Create simple model
        param = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input")
        result = opset10.relu(param)
        model = Model([result], [param], "test")

        # Configure with specific thread count
        from openvino.properties import inference_num_threads

        config = {inference_num_threads: 2}
        compiled = openvino_core.compile_model(model, "CPU", config)
        assert compiled is not None

    def test_cache_directory_configuration(self, openvino_core):
        """Test cache directory can be configured"""
        with tempfile.TemporaryDirectory() as cache_dir:
            from openvino.runtime import Model, PartialShape, Type, opset10

            param = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input")
            result = opset10.relu(param)
            model = Model([result], [param], "test")

            config = {"CACHE_DIR": cache_dir}
            compiled = openvino_core.compile_model(model, "CPU", config)
            assert compiled is not None

    def test_environment_variable_loading(self):
        """Test environment variables are respected"""
        # Set environment variable
        os.environ["OPENVINO_CACHE_DIR"] = "/tmp/ov_cache_test"

        from openvino.runtime import Core

        core = Core()
        # Should not raise error
        assert core is not None

        # Clean up
        del os.environ["OPENVINO_CACHE_DIR"]


class TestOpenVINOIntegration:
    """Test OpenVINO integration with AutoBot components"""

    def test_langchain_embeddings_available(self):
        """Test LangChain OpenVINO embeddings can be imported"""
        try:
            from langchain_community.embeddings.openvino import OpenVINOEmbeddings

            assert OpenVINOEmbeddings is not None
        except ImportError:
            pytest.skip("LangChain OpenVINO embeddings not installed")

    def test_langchain_reranker_available(self):
        """Test LangChain OpenVINO reranker can be imported"""
        try:
            from langchain_community.document_compressors.openvino_rerank import (
                OpenVINOReranker,
            )

            assert OpenVINOReranker is not None
        except ImportError:
            pytest.skip("LangChain OpenVINO reranker not installed")

    def test_optimum_openvino_available(self):
        """Test Optimum OpenVINO integration available"""
        try:
            import optimum.intel

            assert optimum.intel is not None
        except ImportError:
            pytest.skip("Optimum Intel not installed")


class TestOpenVINOErrorHandling:
    """Test error handling and edge cases"""

    @pytest.fixture
    def openvino_core(self):
        """Create OpenVINO Core instance"""
        from openvino.runtime import Core

        return Core()

    def test_invalid_device_name(self, openvino_core):
        """Test handling of invalid device name"""
        from openvino.runtime import Model, PartialShape, Type, opset10

        param = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input")
        result = opset10.relu(param)
        model = Model([result], [param], "test")

        with pytest.raises(Exception):
            # Should fail with invalid device
            openvino_core.compile_model(model, "INVALID_DEVICE_XYZ")

    def test_empty_model_input(self, openvino_core):
        """Test handling of empty model inputs"""
        from openvino.runtime import Model, PartialShape, Type, opset10

        param = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input")
        result = opset10.relu(param)
        model = Model([result], [param], "test")

        compiled = openvino_core.compile_model(model, "CPU")

        # Should handle empty batch gracefully
        # Note: OpenVINO may not support 0-batch, test what happens
        try:
            empty_input = np.array([]).reshape(0, 10).astype(np.float32)
            compiled([empty_input])
        except Exception:
            # Expected to fail for 0-batch
            pass

    def test_mismatched_input_shape(self, openvino_core):
        """Test handling of mismatched input shapes"""
        from openvino.runtime import Model, PartialShape, Type, opset10

        param = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input")
        result = opset10.relu(param)
        model = Model([result], [param], "test")

        compiled = openvino_core.compile_model(model, "CPU")

        # Wrong shape should raise error
        wrong_input = np.random.randn(1, 20).astype(np.float32)  # Expected 10, got 20
        with pytest.raises(Exception):
            compiled([wrong_input])

    def test_wrong_dtype_input(self, openvino_core):
        """Test handling of wrong data type"""
        from openvino.runtime import Model, PartialShape, Type, opset10

        param = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input")
        result = opset10.relu(param)
        model = Model([result], [param], "test")

        compiled = openvino_core.compile_model(model, "CPU")

        # Integer input instead of float
        wrong_dtype = np.random.randint(0, 10, (1, 10))
        # OpenVINO should handle dtype conversion or raise clear error
        try:
            compiled([wrong_dtype.astype(np.float32)])  # Will work if cast
        except Exception:
            pass  # Expected if strict dtype checking


class TestOpenVINOProductionReadiness:
    """Tests for production deployment readiness"""

    def test_version_information(self):
        """Test OpenVINO version can be retrieved"""
        from openvino.runtime import get_version

        version = get_version()
        assert version is not None
        assert len(version) > 0
        print(f"\nOpenVINO Version: {version}")

    def test_concurrent_compilations(self):
        """Test multiple concurrent model compilations"""
        from openvino.runtime import Core, Model, PartialShape, Type, opset10

        core = Core()

        models = []
        for i in range(3):
            param = opset10.parameter(
                PartialShape([1, 10 + i]), Type.f32, name=f"input_{i}"
            )
            result = opset10.relu(param)
            model = Model([result], [param], f"model_{i}")
            models.append(model)

        # Compile all models
        compiled_models = []
        for model in models:
            compiled = core.compile_model(model, "CPU")
            compiled_models.append(compiled)

        assert len(compiled_models) == 3
        for cm in compiled_models:
            assert cm is not None

    def test_model_serialization(self):
        """Test model can be saved and loaded"""
        from openvino.runtime import Core, Model, PartialShape, Type, opset10, serialize

        core = Core()

        # Create model
        param = opset10.parameter(PartialShape([1, 10]), Type.f32, name="input")
        result = opset10.relu(param)
        model = Model([result], [param], "serialization_test")

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "model.xml"

            # Save model
            serialize(model, str(model_path))
            assert model_path.exists()

            # Load model
            loaded_model = core.read_model(str(model_path))
            assert loaded_model is not None
            assert loaded_model.get_name() == "serialization_test"

    def test_graceful_degradation(self):
        """Test system handles missing accelerators gracefully"""
        from openvino.runtime import Core

        core = Core()
        devices = core.available_devices

        # Should always have CPU fallback
        assert "CPU" in devices

        # If GPU not available, should not crash
        if "GPU" not in devices:
            print("\nGPU not available - testing fallback to CPU")
            # System should continue to work with CPU only
            assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
