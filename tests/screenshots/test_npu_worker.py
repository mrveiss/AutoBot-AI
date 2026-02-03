#!/usr/bin/env python3
"""
Test NPU Worker Functionality
Validates NPU worker deployment and inference capabilities
"""

import asyncio
import json
import logging
import sys
from typing import Dict, Any

import aiohttp
import structlog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()


class NPUWorkerTester:
    """Test NPU worker functionality"""
    
    def __init__(self, npu_url: str = "http://localhost:8081"):
        self.npu_url = npu_url
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_health(self) -> bool:
        """Test NPU worker health endpoint"""
        try:
            async with self.session.get(f"{self.npu_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("NPU worker health check", data=data)
                    return True
                else:
                    logger.error("NPU worker health check failed", status=response.status)
                    return False
        except Exception as e:
            logger.error("NPU worker health check error", error=str(e))
            return False
    
    async def test_device_detection(self) -> Dict[str, Any]:
        """Test NPU device detection"""
        try:
            async with self.session.get(f"{self.npu_url}/devices") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("NPU device detection", data=data)
                    return data
                else:
                    logger.error("NPU device detection failed", status=response.status)
                    return {}
        except Exception as e:
            logger.error("NPU device detection error", error=str(e))
            return {}
    
    async def test_model_loading(self) -> bool:
        """Test model loading functionality"""
        try:
            # Test model load request
            model_request = {
                "model_id": "test-phi3-mini",
                "model_config": {
                    "model": "microsoft/Phi-3-mini-4k-instruct",
                    "device": "NPU",
                    "precision": "INT8"
                }
            }
            
            async with self.session.post(
                f"{self.npu_url}/models/load",
                json=model_request
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("Model loading test", data=data)
                    return True
                else:
                    logger.error("Model loading failed", status=response.status)
                    return False
        except Exception as e:
            logger.error("Model loading error", error=str(e))
            return False
    
    async def test_inference(self) -> bool:
        """Test inference functionality"""
        try:
            # Test inference request
            inference_request = {
                "model_id": "test-phi3-mini",
                "input_text": "Hello, this is a test inference request",
                "max_tokens": 50,
                "temperature": 0.7
            }
            
            async with self.session.post(
                f"{self.npu_url}/inference",
                json=inference_request
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("Inference test", data=data)
                    return True
                else:
                    logger.error("Inference failed", status=response.status)
                    return False
        except Exception as e:
            logger.error("Inference error", error=str(e))
            return False
    
    async def test_model_status(self) -> Dict[str, Any]:
        """Test model status endpoint"""
        try:
            async with self.session.get(f"{self.npu_url}/models") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("Model status", data=data)
                    return data
                else:
                    logger.error("Model status failed", status=response.status)
                    return {}
        except Exception as e:
            logger.error("Model status error", error=str(e))
            return {}
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all NPU worker tests"""
        results = {}
        
        logger.info("Starting NPU worker tests")
        
        # Test 1: Health check
        results["health"] = await self.test_health()
        
        # Test 2: Device detection  
        device_info = await self.test_device_detection()
        results["device_detection"] = bool(device_info)
        
        # Test 3: Model loading
        results["model_loading"] = await self.test_model_loading()
        
        # Test 4: Model status
        status_info = await self.test_model_status()
        results["model_status"] = bool(status_info)
        
        # Test 5: Inference (only if model loaded)
        if results["model_loading"]:
            results["inference"] = await self.test_inference()
        else:
            results["inference"] = False
        
        logger.info("NPU worker tests completed", results=results)
        return results


async def main():
    """Main test runner"""
    print("🧪 AutoBot NPU Worker Test Suite")
    print("=" * 50)
    
    try:
        async with NPUWorkerTester() as tester:
            results = await tester.run_all_tests()
            
            print("\n📊 Test Results:")
            print("-" * 30)
            
            passed = 0
            total = len(results)
            
            for test_name, passed_test in results.items():
                status = "✅ PASS" if passed_test else "❌ FAIL"
                print(f"{test_name:<20} {status}")
                if passed_test:
                    passed += 1
            
            print(f"\nOverall: {passed}/{total} tests passed")
            
            if passed == total:
                print("🎉 All NPU worker tests passed!")
                return 0
            else:
                print("⚠️  Some NPU worker tests failed")
                return 1
    
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))