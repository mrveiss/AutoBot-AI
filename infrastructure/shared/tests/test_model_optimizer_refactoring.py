# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test suite for model_optimizer.py refactoring (Issue #353)
Verifies backward compatibility and Feature Envy fixes
"""

from src.utils.model_optimizer import (
    ModelInfo,
    ModelOptimizer,
    ModelPerformanceLevel,
    ModelPerformanceTracker,
    ModelSelector,
    SystemResourceAnalyzer,
    SystemResources,
    TaskComplexity,
    TaskRequest,
    get_model_optimizer,
)


def test_imports():
    """Test that all classes can be imported (backward compatibility)"""
    assert ModelOptimizer is not None
    assert get_model_optimizer is not None
    assert TaskRequest is not None
    assert ModelInfo is not None
    assert TaskComplexity is not None
    assert ModelPerformanceLevel is not None
    # New classes
    assert SystemResources is not None
    assert SystemResourceAnalyzer is not None
    assert ModelPerformanceTracker is not None
    assert ModelSelector is not None
    print("✅ All imports successful")


def test_system_resources_dataclass():
    """Test SystemResources dataclass with Tell Don't Ask methods"""
    resources = SystemResources(
        cpu_percent=50.0, memory_percent=60.0, available_memory_gb=16.0
    )

    # Test behavior methods
    assert resources.allows_large_models() is True  # Low CPU/memory
    assert resources.get_max_model_size_gb() == float("inf")

    # Test dict conversion (backward compatibility)
    resources_dict = resources.to_dict()
    assert resources_dict["cpu_percent"] == 50.0
    assert resources_dict["memory_percent"] == 60.0
    assert resources_dict["available_memory_gb"] == 16.0

    # Test high load scenario
    high_load = SystemResources(
        cpu_percent=85.0, memory_percent=80.0, available_memory_gb=3.0
    )
    assert high_load.allows_large_models() is False
    assert high_load.get_max_model_size_gb() == 4.0

    print("✅ SystemResources dataclass works correctly")


def test_task_request_analyze_complexity():
    """Test TaskRequest.analyze_complexity() method (Tell Don't Ask)"""
    complexity_keywords = {
        TaskComplexity.SIMPLE: ["what", "define"],
        TaskComplexity.MODERATE: ["analyze", "explain"],
        TaskComplexity.COMPLEX: ["design", "develop"],
        TaskComplexity.SPECIALIZED: ["research paper", "scientific"],
    }

    # Simple query
    simple_task = TaskRequest(query="What is Python?", task_type="chat")
    assert simple_task.analyze_complexity(complexity_keywords) == TaskComplexity.SIMPLE

    # Complex query
    complex_task = TaskRequest(
        query="Design a scalable microservices architecture", task_type="code"
    )
    assert (
        complex_task.analyze_complexity(complexity_keywords) == TaskComplexity.COMPLEX
    )

    # Specialized query
    specialized_task = TaskRequest(
        query="Write a research paper on quantum computing", task_type="writing"
    )
    assert (
        specialized_task.analyze_complexity(complexity_keywords)
        == TaskComplexity.SPECIALIZED
    )

    print("✅ TaskRequest.analyze_complexity() works correctly")


def test_model_info_fits_resource_constraints():
    """Test ModelInfo.fits_resource_constraints() with both dict and SystemResources"""
    model = ModelInfo(
        name="test-model",
        size_gb=6.0,
        parameter_size="7B",
        quantization="Q4",
        family="llama",
        performance_level=ModelPerformanceLevel.STANDARD,
    )

    # Test with SystemResources (new API)
    resources = SystemResources(
        cpu_percent=50.0, memory_percent=60.0, available_memory_gb=10.0
    )
    assert model.fits_resource_constraints(resources) is True

    # Test with dict (backward compatibility)
    resources_dict = {
        "cpu_percent": 50.0,
        "memory_percent": 60.0,
        "available_memory_gb": 10.0,
    }
    assert model.fits_resource_constraints(resources_dict) is True

    # Test resource constraints
    low_resources = SystemResources(
        cpu_percent=85.0, memory_percent=80.0, available_memory_gb=3.0
    )
    assert model.fits_resource_constraints(low_resources) is False

    print("✅ ModelInfo.fits_resource_constraints() backward compatible")


def test_model_optimizer_initialization():
    """Test ModelOptimizer initialization with new components"""
    optimizer = ModelOptimizer()

    # Verify new components are initialized
    assert optimizer._resource_analyzer is not None
    assert isinstance(optimizer._resource_analyzer, SystemResourceAnalyzer)
    assert optimizer._model_selector is not None
    assert isinstance(optimizer._model_selector, ModelSelector)

    # Verify backward compatibility - old attributes still exist
    assert hasattr(optimizer, "complexity_keywords")
    assert hasattr(optimizer, "model_classifications")
    assert hasattr(optimizer, "_models_cache")

    print("✅ ModelOptimizer initializes with new components")


def test_model_optimizer_backward_compatibility_methods():
    """Test that old ModelOptimizer methods still work (backward compatibility)"""
    optimizer = ModelOptimizer()

    # Test get_system_resources() returns dict (backward compatibility)
    resources = optimizer.get_system_resources()
    assert isinstance(resources, dict)
    assert "cpu_percent" in resources
    assert "memory_percent" in resources
    assert "available_memory_gb" in resources

    # Test analyze_task_complexity() works
    task = TaskRequest(query="What is Python?", task_type="chat")
    complexity = optimizer.analyze_task_complexity(task)
    assert isinstance(complexity, TaskComplexity)

    print("✅ ModelOptimizer backward compatibility methods work")


def test_model_optimizer_delegation():
    """Test that ModelOptimizer properly delegates to new components"""
    optimizer = ModelOptimizer()

    # Create test models
    model1 = ModelInfo(
        name="small-model",
        size_gb=2.0,
        parameter_size="1B",
        quantization="Q4",
        family="llama",
        performance_level=ModelPerformanceLevel.LIGHTWEIGHT,
    )
    model2 = ModelInfo(
        name="large-model",
        size_gb=10.0,
        parameter_size="13B",
        quantization="Q4",
        family="llama",
        performance_level=ModelPerformanceLevel.ADVANCED,
    )

    models = [model1, model2]

    # Test filter_by_complexity delegation
    filtered = optimizer._filter_models_by_complexity(TaskComplexity.COMPLEX, models)
    assert len(filtered) == 1  # Only advanced model
    assert filtered[0].name == "large-model"

    # Test filter_by_resources delegation (dict API)
    resources_dict = {
        "cpu_percent": 85.0,
        "memory_percent": 80.0,
        "available_memory_gb": 3.0,
    }
    filtered = optimizer._filter_models_by_resources(models, resources_dict)
    assert len(filtered) == 1  # Only small model fits
    assert filtered[0].name == "small-model"

    print("✅ ModelOptimizer delegation to new components works")


def test_global_optimizer_singleton():
    """Test that get_model_optimizer() returns singleton instance"""
    optimizer1 = get_model_optimizer()
    optimizer2 = get_model_optimizer()

    assert optimizer1 is optimizer2  # Same instance
    assert isinstance(optimizer1, ModelOptimizer)

    print("✅ Global optimizer singleton works")


def test_model_selector_methods():
    """Test ModelSelector class methods"""
    selector = ModelSelector(min_samples=5)

    # Create test models
    lightweight = ModelInfo(
        name="lightweight",
        size_gb=1.0,
        parameter_size="1B",
        quantization="Q4",
        family="llama",
        performance_level=ModelPerformanceLevel.LIGHTWEIGHT,
    )
    standard = ModelInfo(
        name="standard",
        size_gb=4.0,
        parameter_size="7B",
        quantization="Q4",
        family="llama",
        performance_level=ModelPerformanceLevel.STANDARD,
    )
    advanced = ModelInfo(
        name="advanced",
        size_gb=10.0,
        parameter_size="13B",
        quantization="Q4",
        family="llama",
        performance_level=ModelPerformanceLevel.ADVANCED,
    )

    models = [lightweight, standard, advanced]

    # Test filter_by_complexity
    filtered = selector.filter_by_complexity(models, TaskComplexity.COMPLEX)
    assert len(filtered) == 1  # Only advanced
    assert filtered[0].name == "advanced"

    # Test filter_by_resources
    resources = SystemResources(
        cpu_percent=50.0, memory_percent=60.0, available_memory_gb=6.0
    )
    filtered = selector.filter_by_resources(models, resources)
    assert len(filtered) == 2  # Lightweight and standard fit
    assert "advanced" not in [m.name for m in filtered]

    # Test rank_by_performance
    task = TaskRequest(query="Explain Python", task_type="chat")
    ranked = selector.rank_by_performance(models, task)
    assert len(ranked) == 3
    # Should be ranked by score (descending)

    print("✅ ModelSelector methods work correctly")


if __name__ == "__main__":
    print("\n=== Running Model Optimizer Refactoring Tests (Issue #353) ===\n")

    test_imports()
    test_system_resources_dataclass()
    test_task_request_analyze_complexity()
    test_model_info_fits_resource_constraints()
    test_model_optimizer_initialization()
    test_model_optimizer_backward_compatibility_methods()
    test_model_optimizer_delegation()
    test_global_optimizer_singleton()
    test_model_selector_methods()

    print(
        "\n✅ All tests passed! Feature Envy refactoring successful with full backward compatibility."
    )
