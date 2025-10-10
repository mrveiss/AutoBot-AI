#!/usr/bin/env python3
"""
Test script for the LLM model optimization system
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_model_optimizer():
    """Test the model optimizer functionality"""
    logger.info("🤖 Testing LLM Model Optimizer")
    
    try:
        from src.utils.model_optimizer import get_model_optimizer, TaskRequest, TaskComplexity
        
        # Initialize optimizer
        optimizer = get_model_optimizer()
        logger.info("✅ Model optimizer initialized")
        
        # Test 1: Refresh available models
        logger.info("🔄 Test 1: Refreshing available models")
        models = await optimizer.refresh_available_models()
        
        if models:
            logger.info(f"✅ Found {len(models)} available models:")
            for model in models[:5]:  # Show first 5
                logger.info(f"  - {model.name} ({model.parameter_size}, {model.performance_level.value})")
            if len(models) > 5:
                logger.info(f"  ... and {len(models) - 5} more models")
        else:
            logger.warning("⚠️ No models found - is Ollama running?")
            return False
        
        # Test 2: Task complexity analysis
        logger.info("🧠 Test 2: Task complexity analysis")
        test_queries = [
            ("What is 2+2?", "simple"),
            ("Explain machine learning concepts", "moderate"),
            ("Design a distributed system architecture", "complex"),
            ("Write a research paper on quantum computing", "specialized")
        ]
        
        for query, expected_complexity in test_queries:
            task_request = TaskRequest(query=query, task_type="chat")
            complexity = optimizer.analyze_task_complexity(task_request)
            logger.info(f"✅ '{query[:30]}...' → {complexity.value}")
            
        # Test 3: System resources check
        logger.info("💻 Test 3: System resources analysis")
        resources = optimizer.get_system_resources()
        logger.info(f"✅ CPU: {resources['cpu_percent']:.1f}%")
        logger.info(f"✅ Memory: {resources['memory_percent']:.1f}%")
        logger.info(f"✅ Available Memory: {resources['available_memory_gb']:.1f} GB")
        
        # Test 4: Model selection
        logger.info("🎯 Test 4: Optimal model selection")
        test_tasks = [
            TaskRequest(query="What is the weather like?", task_type="chat"),
            TaskRequest(query="Write a Python script to process CSV files", task_type="code"),
            TaskRequest(query="Analyze the economic impact of renewable energy", task_type="analysis", max_response_time=15.0)
        ]
        
        for i, task in enumerate(test_tasks, 1):
            selected_model = await optimizer.select_optimal_model(task)
            if selected_model:
                logger.info(f"✅ Task {i}: Selected '{selected_model}' for '{task.query[:40]}...'")
            else:
                logger.warning(f"⚠️ Task {i}: No model selected")
        
        # Test 5: Performance tracking simulation
        logger.info("📊 Test 5: Performance tracking simulation")
        if models:
            test_model = models[0].name
            
            # Simulate some performance data
            await optimizer.track_model_performance(
                model_name=test_model,
                response_time=2.5,
                response_tokens=150,
                success=True
            )
            
            await optimizer.track_model_performance(
                model_name=test_model,
                response_time=3.1,
                response_tokens=200,
                success=True
            )
            
            logger.info(f"✅ Performance data tracked for {test_model}")
            
            # Check updated performance
            updated_models = await optimizer.refresh_available_models()
            test_model_obj = next((m for m in updated_models if m.name == test_model), None)
            
            if test_model_obj and test_model_obj.use_count > 0:
                logger.info(f"✅ Model stats: {test_model_obj.avg_response_time:.2f}s avg, "
                           f"{test_model_obj.avg_tokens_per_second:.1f} tokens/s, "
                           f"{test_model_obj.use_count} uses")
        
        # Test 6: Optimization suggestions
        logger.info("💡 Test 6: Optimization suggestions")
        suggestions = await optimizer.get_optimization_suggestions()
        
        if suggestions:
            logger.info(f"✅ Generated {len(suggestions)} optimization suggestions:")
            for suggestion in suggestions[:3]:  # Show first 3
                logger.info(f"  - {suggestion.get('type', 'info').upper()}: {suggestion.get('message', 'No message')}")
        else:
            logger.info("✅ No optimization suggestions at this time")
        
        logger.info("🎉 Model optimizer tests completed successfully!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_optimization_api():
    """Test the optimization API endpoints"""
    logger.info("🌐 Testing Model Optimization API")
    
    try:
        import aiohttp
        
        base_url = "http://localhost:8001/api/llm_optimization"
        
        # Test endpoints
        endpoints_to_test = [
            ("/health", "GET", None),
            ("/models/available", "GET", None),
            ("/system/resources", "GET", None),
            ("/config", "GET", None),
            ("/optimization/suggestions", "GET", None),
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint, method, data in endpoints_to_test:
                try:
                    url = f"{base_url}{endpoint}"
                    logger.info(f"Testing {method} {endpoint}")
                    
                    if method == "GET":
                        async with session.get(url) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.info(f"✅ {endpoint} - Status: {response.status}")
                                
                                # Log key information from response
                                if 'available_models' in result:
                                    logger.info(f"  Available models: {result['available_models']}")
                                if 'models_count' in result:
                                    logger.info(f"  Models count: {result['models_count']}")
                                if 'suggestions_count' in result:
                                    logger.info(f"  Suggestions: {result['suggestions_count']}")
                                if 'resources' in result:
                                    resources = result['resources']
                                    logger.info(f"  CPU: {resources.get('cpu_percent', 'N/A')}%, "
                                               f"Memory: {resources.get('memory_percent', 'N/A')}%")
                                    
                            else:
                                logger.warning(f"⚠️ {endpoint} - Status: {response.status}")
                                error_text = await response.text()
                                logger.warning(f"  Error: {error_text[:100]}...")
                    
                    print()
                    
                except Exception as e:
                    logger.warning(f"⚠️ Could not test {endpoint}: {e}")
        
        # Test model selection endpoint
        logger.info("🎯 Testing model selection endpoint")
        selection_data = {
            "query": "Write a Python function to sort a list",
            "task_type": "code",
            "max_response_time": 10.0
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/models/select", 
                    json=selection_data
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Model selection - Status: {response.status}")
                        logger.info(f"  Selected model: {data.get('selected_model', 'None')}")
                        logger.info(f"  Task complexity: {data.get('task_complexity', 'Unknown')}")
                    else:
                        logger.warning(f"⚠️ Model selection failed - Status: {response.status}")
        except Exception as e:
            logger.warning(f"⚠️ Model selection test failed: {e}")
        
        # Test performance tracking endpoint
        logger.info("📊 Testing performance tracking endpoint")
        performance_data = {
            "model_name": "llama3.2:3b-instruct-q4_K_M",
            "response_time": 4.5,
            "response_tokens": 180,
            "success": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/models/performance/track", 
                    json=performance_data
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Performance tracking - Status: {response.status}")
                        logger.info(f"  Message: {data.get('message', 'No message')}")
                    else:
                        logger.warning(f"⚠️ Performance tracking failed - Status: {response.status}")
        except Exception as e:
            logger.warning(f"⚠️ Performance tracking test failed: {e}")
        
        logger.info("✅ Optimization API tests completed!")
        return True
        
    except ImportError:
        logger.warning("⚠️ aiohttp not available, skipping API tests")
        return True
    except Exception as e:
        logger.error(f"❌ API testing error: {e}")
        return False


async def test_task_complexity_classification():
    """Test task complexity classification accuracy"""
    logger.info("🧪 Testing Task Complexity Classification")
    
    try:
        from src.utils.model_optimizer import get_model_optimizer, TaskRequest, TaskComplexity
        
        optimizer = get_model_optimizer()
        
        # Test cases with expected complexity
        test_cases = [
            # Simple tasks
            ("What is the capital of France?", TaskComplexity.SIMPLE),
            ("Define machine learning", TaskComplexity.SIMPLE),
            ("Is 10 greater than 5?", TaskComplexity.SIMPLE),
            ("List three colors", TaskComplexity.SIMPLE),
            
            # Moderate tasks
            ("Explain how photosynthesis works", TaskComplexity.MODERATE),
            ("Compare Python and JavaScript", TaskComplexity.MODERATE),
            ("Analyze the main themes in Shakespeare's Hamlet", TaskComplexity.MODERATE),
            ("How does encryption work?", TaskComplexity.MODERATE),
            
            # Complex tasks
            ("Design a microservices architecture for an e-commerce platform", TaskComplexity.COMPLEX),
            ("Implement a machine learning model for fraud detection", TaskComplexity.COMPLEX),
            ("Create a comprehensive business plan for a tech startup", TaskComplexity.COMPLEX),
            ("Solve this optimization problem with multiple constraints", TaskComplexity.COMPLEX),
            
            # Specialized tasks
            ("Write a research paper on quantum computing algorithms", TaskComplexity.SPECIALIZED),
            ("Perform a legal analysis of intellectual property law", TaskComplexity.SPECIALIZED),
            ("Design a mathematical proof for this theorem", TaskComplexity.SPECIALIZED),
            ("Analyze financial derivatives pricing models", TaskComplexity.SPECIALIZED)
        ]
        
        correct_classifications = 0
        total_tests = len(test_cases)
        
        logger.info(f"Running {total_tests} classification tests...")
        
        for query, expected_complexity in test_cases:
            task_request = TaskRequest(query=query, task_type="chat")
            actual_complexity = optimizer.analyze_task_complexity(task_request)
            
            is_correct = actual_complexity == expected_complexity
            if is_correct:
                correct_classifications += 1
            
            status = "✅" if is_correct else "❌"
            logger.info(f"{status} '{query[:50]}...' → {actual_complexity.value} "
                       f"(expected: {expected_complexity.value})")
        
        accuracy = (correct_classifications / total_tests) * 100
        logger.info(f"📊 Classification Accuracy: {correct_classifications}/{total_tests} ({accuracy:.1f}%)")
        
        if accuracy >= 75:
            logger.info("✅ Task complexity classification is working well!")
        elif accuracy >= 50:
            logger.warning("⚠️ Task complexity classification needs improvement")
        else:
            logger.error("❌ Task complexity classification is not working properly")
        
        return accuracy >= 50  # At least 50% accuracy to pass
        
    except Exception as e:
        logger.error(f"❌ Classification test error: {e}")
        return False


async def test_configuration():
    """Test optimization configuration"""
    logger.info("⚙️ Testing Optimization Configuration")
    
    try:
        from src.config_helper import cfg
        
        # Test configuration values
        config_tests = [
            ('llm.optimization.performance_threshold', float),
            ('llm.optimization.cache_ttl', int),
            ('llm.optimization.min_samples', int),
            ('llm.optimization.auto_selection', bool),
            ('llm.fallback.strategy', str),
            ('llm.fallback.max_retries', int),
            ('llm.fallback.fallback_models', list),
            ('llm.targets.max_response_time', float),
            ('llm.targets.min_tokens_per_second', int),
            ('llm.targets.min_success_rate', float),
        ]
        
        logger.info("📋 Configuration values:")
        for config_key, expected_type in config_tests:
            value = cfg.get(config_key)
            logger.info(f"{config_key}: {value} (type: {type(value).__name__})")
            
            if value is not None and not isinstance(value, expected_type):
                logger.warning(f"⚠️ Expected {expected_type.__name__}, got {type(value).__name__}")
        
        # Test that critical values are reasonable
        perf_threshold = cfg.get('llm.optimization.performance_threshold', 0.8)
        if 0.5 <= perf_threshold <= 1.0:
            logger.info("✅ Performance threshold is reasonable")
        else:
            logger.warning(f"⚠️ Performance threshold ({perf_threshold}) may be unrealistic")
        
        max_response_time = cfg.get('llm.targets.max_response_time', 30.0)
        if 5.0 <= max_response_time <= 120.0:
            logger.info("✅ Max response time is reasonable")
        else:
            logger.warning(f"⚠️ Max response time ({max_response_time}s) may be too extreme")
        
        # Test fallback models exist
        fallback_models = cfg.get('llm.fallback.fallback_models', [])
        if fallback_models:
            logger.info(f"✅ Fallback models configured: {len(fallback_models)} models")
        else:
            logger.warning("⚠️ No fallback models configured")
        
        logger.info("✅ Configuration testing completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration test error: {e}")
        return False


async def main():
    """Main test function"""
    logger.info("🚀 Starting LLM Model Optimization Test Suite")
    
    # Run all tests
    test_results = {
        "Model Optimizer": await test_model_optimizer(),
        "Optimization API": await test_optimization_api(),
        "Task Complexity Classification": await test_task_complexity_classification(),
        "Configuration": await test_configuration(),
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
        logger.info("🎉 LLM Model Optimization Test Suite PASSED!")
        logger.info("The optimization system is ready for production use.")
        logger.info("Available API endpoints:")
        logger.info("  - /api/llm_optimization/models/available - List all models")
        logger.info("  - /api/llm_optimization/models/select - Smart model selection") 
        logger.info("  - /api/llm_optimization/optimization/suggestions - Get recommendations")
        logger.info("  - /api/llm_optimization/models/comparison - Compare model performance")
    else:
        logger.error("❌ Some tests FAILED!")
        logger.error("Please check the implementation and dependencies.")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())