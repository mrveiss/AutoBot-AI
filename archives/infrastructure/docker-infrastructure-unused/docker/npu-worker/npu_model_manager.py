"""
NPU Model Manager
Manages AI models optimized for Intel NPU acceleration
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

try:
    from openvino.runtime import Core

    OPENVINO_AVAILABLE = True
except ImportError:
    OPENVINO_AVAILABLE = False

logger = logging.getLogger(__name__)


class NPUModelManager:
    """Manages models optimized for Intel NPU"""

    def __init__(self, model_cache_dir: str = "/app/models"):
        self.model_cache_dir = Path(model_cache_dir)
        self.model_cache_dir.mkdir(exist_ok=True)

        self.loaded_models = {}
        self.core = None
        self.npu_available = False
        self.gpu_devices = []
        self.device_pool = []  # Pool of available devices for parallel inference

        # Initialize OpenVINO
        self._initialize_openvino()

    def _initialize_openvino(self):
        """Initialize OpenVINO and check NPU availability"""
        if not OPENVINO_AVAILABLE:
            logger.error("OpenVINO not available - NPU acceleration disabled")
            return

        try:
            self.core = Core()
            available_devices = self.core.available_devices
            logger.info(f"Available OpenVINO devices: {available_devices}")

            # Check for NPU devices
            npu_devices = [d for d in available_devices if "NPU" in d]
            if npu_devices:
                self.npu_available = True
                logger.info(f"NPU devices available: {npu_devices}")
                self.device_pool.extend(npu_devices)

            # Check for GPU devices
            self.gpu_devices = [d for d in available_devices if "GPU" in d]
            if self.gpu_devices:
                logger.info(f"GPU devices available: {self.gpu_devices}")
                self.device_pool.extend(self.gpu_devices)

            # Add CPU as fallback
            cpu_devices = [d for d in available_devices if "CPU" in d]
            if cpu_devices:
                self.device_pool.extend(cpu_devices)

            if not self.device_pool:
                logger.warning("No accelerated devices found, using CPU")
                self.device_pool = ["CPU"]

            logger.info(f"Device pool for parallel inference: {self.device_pool}")

        except Exception as e:
            logger.error(f"Failed to initialize OpenVINO: {e}")

    def get_optimal_device(self) -> str:
        """Get the optimal device for inference"""
        if not self.core:
            return "CPU"

        available_devices = self.core.available_devices
        logger.info(f"Checking device priority from: {available_devices}")

        # Priority: NPU > GPU > CPU
        if self.npu_available:
            logger.info("Using NPU device for optimal performance")
            return "NPU"
        elif any("GPU" in device for device in available_devices):
            gpu_device = next(
                (device for device in available_devices if "GPU" in device), None
            )
            logger.info(f"Using GPU device: {gpu_device}")
            return "GPU"
        elif any("CUDA" in device for device in available_devices):
            cuda_device = next(
                (device for device in available_devices if "CUDA" in device), None
            )
            logger.info(f"Using CUDA GPU device: {cuda_device}")
            return "GPU"
        else:
            logger.info("Falling back to CPU device")
            return "CPU"

    async def load_model(self, model_id: str, model_config: Dict[str, Any]) -> bool:
        """Load a model for NPU inference"""
        try:
            if model_id in self.loaded_models:
                logger.info(f"Model {model_id} already loaded")
                return True

            # For now, simulate model loading for NPU
            # In a real implementation, this would:
            # 1. Download HuggingFace model
            # 2. Convert to OpenVINO IR format
            # 3. Compile for NPU device
            # 4. Cache the compiled model

            device = self.get_optimal_device()
            logger.info(f"Loading model {model_id} on device: {device}")

            # Simulate loading time
            await asyncio.sleep(1)

            self.loaded_models[model_id] = {
                "config": model_config,
                "device": device,
                "loaded_at": asyncio.get_event_loop().time(),
                "inference_count": 0,
            }

            logger.info(f"Successfully loaded model {model_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return False

    async def unload_model(self, model_id: str) -> bool:
        """Unload a model to free memory"""
        try:
            if model_id in self.loaded_models:
                del self.loaded_models[model_id]
                logger.info(f"Unloaded model {model_id}")
                return True
            else:
                logger.warning(f"Model {model_id} not loaded")
                return False
        except Exception as e:
            logger.error(f"Failed to unload model {model_id}: {e}")
            return False

    async def inference(
        self, model_id: str, input_text: str, **kwargs
    ) -> Dict[str, Any]:
        """Run inference on NPU"""
        try:
            if model_id not in self.loaded_models:
                logger.error(f"Model {model_id} not loaded")
                return {"error": f"Model {model_id} not loaded"}

            model_info = self.loaded_models[model_id]
            model_info["inference_count"] += 1

            # Simulate NPU inference
            # In a real implementation, this would:
            # 1. Tokenize input text
            # 2. Run inference on NPU
            # 3. Decode output tokens
            # 4. Return results with performance metrics

            device = model_info["device"]
            logger.debug(f"Running inference on {device} for model {model_id}")

            # Simulate inference time (NPU should be faster)
            inference_time = 0.1 if device == "NPU" else 0.3
            await asyncio.sleep(inference_time)

            # Simulate response
            response_text = f"NPU inference response for: {input_text[:50]}..."

            return {
                "model_id": model_id,
                "device": device,
                "response": response_text,
                "inference_time_ms": inference_time * 1000,
                "inference_count": model_info["inference_count"],
            }

        except Exception as e:
            logger.error(f"Inference failed for model {model_id}: {e}")
            return {"error": str(e)}

    def get_model_status(self) -> Dict[str, Any]:
        """Get status of all loaded models"""
        return {
            "npu_available": self.npu_available,
            "optimal_device": self.get_optimal_device(),
            "loaded_models": {
                model_id: {
                    "device": info["device"],
                    "inference_count": info["inference_count"],
                    "loaded_at": info["loaded_at"],
                }
                for model_id, info in self.loaded_models.items()
            },
            "available_devices": self.core.available_devices if self.core else [],
        }

    async def cleanup(self):
        """Cleanup all models and resources"""
        for model_id in list(self.loaded_models.keys()):
            await self.unload_model(model_id)
        logger.info("NPU Model Manager cleaned up")

    def get_all_devices(self) -> list:
        """Get all available devices for parallel processing"""
        return self.device_pool.copy()

    async def load_model_multi_device(
        self, model_id: str, model_config: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Load model on multiple devices for parallel inference"""
        results = {}

        for device in self.device_pool:
            device_model_id = f"{model_id}_{device}"
            try:
                logger.info(f"Loading model {model_id} on device: {device}")

                # Simulate loading on specific device
                await asyncio.sleep(0.5)

                self.loaded_models[device_model_id] = {
                    "config": model_config,
                    "device": device,
                    "loaded_at": asyncio.get_event_loop().time(),
                    "inference_count": 0,
                    "base_model_id": model_id,
                }

                results[device] = True
                logger.info(f"Successfully loaded model {model_id} on {device}")

            except Exception as e:
                logger.error(f"Failed to load model {model_id} on {device}: {e}")
                results[device] = False

        return results

    async def parallel_inference(
        self, model_id: str, input_texts: list, devices: list = None
    ) -> Dict[str, Any]:
        """Run inference on multiple devices in parallel"""
        if devices is None:
            devices = self.device_pool

        # Distribute inputs across devices
        device_count = len(devices)
        input_count = len(input_texts)
        inputs_per_device = (input_count + device_count - 1) // device_count

        tasks = []
        for i, device in enumerate(devices):
            start_idx = i * inputs_per_device
            end_idx = min((i + 1) * inputs_per_device, input_count)
            device_inputs = input_texts[start_idx:end_idx]

            if device_inputs:
                device_model_id = f"{model_id}_{device}"
                for text in device_inputs:
                    task = self.inference(device_model_id, text)
                    tasks.append((device, task))

        # Run all inferences in parallel using asyncio.gather
        results = []
        if tasks:
            # Execute all tasks concurrently
            task_results = await asyncio.gather(
                *[task for _, task in tasks], return_exceptions=True
            )

            # Process results with device information
            for (device, _), result in zip(tasks, task_results):
                if isinstance(result, Exception):
                    logger.error(f"Parallel inference failed on {device}: {result}")
                    results.append({"error": str(result), "device": device})
                else:
                    result["device"] = device
                    results.append(result)

        return {
            "model_id": model_id,
            "total_inputs": input_count,
            "devices_used": devices,
            "results": results,
            "parallel_execution": True,
        }

    async def benchmark_parallel_vs_sequential(
        self, model_id: str, input_texts: list, devices: list = None
    ) -> Dict[str, Any]:
        """Benchmark parallel vs sequential inference"""
        import time

        if devices is None:
            devices = self.device_pool[:2]  # Use up to 2 devices for benchmark

        # Sequential execution
        start_sequential = time.time()
        sequential_results = []
        for text in input_texts:
            result = await self.inference(f"{model_id}_{devices[0]}", text)
            sequential_results.append(result)
        sequential_time = time.time() - start_sequential

        # Parallel execution
        start_parallel = time.time()
        await self.parallel_inference(model_id, input_texts, devices)
        parallel_time = time.time() - start_parallel

        speedup = sequential_time / parallel_time if parallel_time > 0 else 0

        return {
            "sequential_time_ms": sequential_time * 1000,
            "parallel_time_ms": parallel_time * 1000,
            "speedup": f"{speedup:.2f}x",
            "devices_used": devices,
            "input_count": len(input_texts),
            "efficiency": f"{(speedup / len(devices)) * 100:.1f}%",
        }
