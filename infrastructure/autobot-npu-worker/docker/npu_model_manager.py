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
            else:
                logger.warning("No NPU devices detected - falling back to CPU")

        except Exception as e:
            logger.error(f"Failed to initialize OpenVINO: {e}")

    def get_optimal_device(self) -> str:
        """Get the optimal device for inference"""
        if self.npu_available:
            return "NPU"
        elif self.core and "GPU" in self.core.available_devices:
            return "GPU"
        else:
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
