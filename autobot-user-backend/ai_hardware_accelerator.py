#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot AI Hardware Accelerator
Intelligent routing and optimization for NPU/GPU/CPU semantic processing
"""

import asyncio
import io
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import aiohttp
import numpy as np
import torch
import torch.nn.functional as F
from config import cfg
from PIL import Image

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.redis_client import get_redis_client

# Import centralized components
from backend.constants.model_constants import model_config
from backend.constants.threshold_constants import (
    HardwareAcceleratorConfig,
    ResourceThresholds,
    TimingConstants,
)

# Import transformers models for multi-modal embeddings
try:
    import librosa
    from transformers import CLIPModel, CLIPProcessor, Wav2Vec2Model, Wav2Vec2Processor

    MULTIMODAL_MODELS_AVAILABLE = True
except ImportError:
    MULTIMODAL_MODELS_AVAILABLE = False

logger = get_llm_logger("ai_hardware_accelerator")


def _get_gpu_metrics_with_pynvml() -> Optional[Dict[str, Any]]:
    """Get GPU metrics using pynvml (Issue #315 - extracted to reduce nesting)."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

        return {
            "utilization_percent": utilization.gpu,
            "temperature_c": pynvml.nvmlDeviceGetTemperature(
                handle, pynvml.NVML_TEMPERATURE_GPU
            ),
            "power_usage_w": pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0,
            "available_memory_mb": pynvml.nvmlDeviceGetMemoryInfo(handle).free
            / 1024
            / 1024,
        }
    except ImportError:
        return None
    except Exception:
        return None


async def _try_fallback_processing(
    task: "ProcessingTask",
    fallback_device: "HardwareDevice",
    process_on_gpu: callable,
    process_on_cpu: callable,
) -> Optional[Dict[str, Any]]:
    """Try processing on fallback device (Issue #315 - extracted to reduce nesting)."""
    try:
        if fallback_device.value == "gpu":
            return await process_on_gpu(task)
        return await process_on_cpu(task)
    except Exception as fallback_error:
        logger.error("❌ Fallback also failed: %s", fallback_error)
        return None


class HardwareDevice(Enum):
    """Available hardware devices for AI processing."""

    NPU = "npu"  # Intel NPU for lightweight tasks
    GPU = "gpu"  # RTX 4070 for heavy compute
    CPU = "cpu"  # CPU fallback


class TaskComplexity(Enum):
    """Task complexity levels for hardware routing."""

    LIGHTWEIGHT = "lightweight"  # < 1s, small models
    MODERATE = "moderate"  # 1-5s, medium models
    HEAVY = "heavy"  # > 5s, large models


@dataclass
class HardwareMetrics:
    """Hardware performance metrics."""

    device: HardwareDevice
    utilization_percent: float
    temperature_c: float
    power_usage_w: float
    available_memory_mb: float
    last_updated: datetime


@dataclass
class ProcessingTask:
    """AI processing task definition."""

    task_id: str
    task_type: str
    input_data: Dict[str, Any]
    complexity: TaskComplexity
    priority: int = 1
    timeout_seconds: int = 30
    preferred_device: Optional[HardwareDevice] = None


@dataclass
class ProcessingResult:
    """AI processing result."""

    task_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    device_used: Optional[HardwareDevice] = None
    processing_time_ms: float = 0.0
    device_metrics: Optional[HardwareMetrics] = None


class AIHardwareAccelerator:
    """
    Intelligent AI hardware accelerator for AutoBot.

    Optimally routes AI tasks to Intel NPU, RTX 4070 GPU, or CPU
    based on task complexity, hardware availability, and performance requirements.
    """

    def __init__(self):
        """Initialize AI hardware accelerator with NPU/GPU/CPU routing config."""
        self.redis_client = None
        self.device_metrics = {}
        self.task_history = []
        import os

        npu_worker_host = os.getenv("AUTOBOT_NPU_WORKER_HOST")
        npu_worker_port = os.getenv("AUTOBOT_NPU_WORKER_PORT")
        if not npu_worker_host or not npu_worker_port:
            raise ValueError(
                "NPU Worker configuration missing: AUTOBOT_NPU_WORKER_HOST and "
                "AUTOBOT_NPU_WORKER_PORT environment variables must be set"
            )
        self.npu_worker_url = cfg.get(
            "npu_worker.url", f"http://{npu_worker_host}:{npu_worker_port}"
        )
        self.routing_strategy = cfg.get("ai_acceleration.routing_strategy", "optimal")

        # Performance thresholds for device selection (Issue #376 - use named constants)
        self.thresholds = {
            "npu_max_model_size_mb": HardwareAcceleratorConfig.NPU_MAX_MODEL_SIZE_MB,
            "npu_max_response_time_s": HardwareAcceleratorConfig.NPU_MAX_RESPONSE_TIME_S,
            "gpu_utilization_threshold": ResourceThresholds.GPU_BUSY_THRESHOLD,
            "cpu_fallback_timeout_s": TimingConstants.STANDARD_DELAY,
        }

        # Device availability tracking
        self.device_status = {
            HardwareDevice.NPU: {"available": False, "last_check": None},
            HardwareDevice.GPU: {"available": False, "last_check": None},
            HardwareDevice.CPU: {"available": True, "last_check": datetime.now()},
        }

        # Multi-modal models
        self.clip_model = None
        self.clip_processor = None
        self.wav2vec_model = None
        self.wav2vec_processor = None

        # Projection matrices for unified embedding space (Issue #376 - use named constant)
        self.text_projection = None
        self.image_projection = None
        self.audio_projection = None
        self.unified_dim = HardwareAcceleratorConfig.UNIFIED_EMBEDDING_DIM

    async def initialize(self):
        """Initialize the AI hardware accelerator."""
        logger.info("🚀 Initializing AI Hardware Accelerator")

        # Initialize Redis client
        try:
            self.redis_client = await get_redis_client("main")
            if self.redis_client:
                logger.info("✅ Connected to Redis for task coordination")
        except Exception as e:
            logger.warning("⚠️ Redis connection failed: %s", e)

        # Check hardware availability
        await self._check_hardware_availability()

        # Initialize multi-modal models if GPU is available
        if self.device_status[HardwareDevice.GPU]["available"]:
            await self._initialize_multimodal_models()

        # Start monitoring loop
        asyncio.create_task(self._hardware_monitoring_loop())

        logger.info("✅ AI Hardware Accelerator initialized")

    async def _check_hardware_availability(self):
        """Check availability of all hardware devices."""
        # Check NPU Worker
        await self._check_npu_availability()

        # Check GPU
        await self._check_gpu_availability()

        # CPU is always available
        self.device_status[HardwareDevice.CPU]["available"] = True
        self.device_status[HardwareDevice.CPU]["last_check"] = datetime.now()

    async def _check_npu_availability(self):
        """Check NPU Worker availability."""
        try:
            # Use singleton HTTP client for connection pooling
            http_client = get_http_client()
            async with await http_client.get(
                f"{self.npu_worker_url}/health", timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    health_data = await response.json()
                    npu_available = health_data.get("npu_available", False)

                    self.device_status[HardwareDevice.NPU]["available"] = npu_available
                    self.device_status[HardwareDevice.NPU][
                        "last_check"
                    ] = datetime.now()

                    if npu_available:
                        logger.info("✅ NPU Worker available and ready")
                        await self._update_npu_metrics(health_data)
                    else:
                        logger.warning(
                            "⚠️ NPU Worker connected but NPU hardware unavailable"
                        )
                else:
                    logger.warning(
                        f"⚠️ NPU Worker health check failed: {response.status}"
                    )
                    self.device_status[HardwareDevice.NPU]["available"] = False
        except Exception as e:
            logger.warning("⚠️ NPU Worker connection failed: %s", e)
            self.device_status[HardwareDevice.NPU]["available"] = False

    async def _check_gpu_availability(self):
        """Check GPU availability (Issue #315 - refactored to reduce nesting)."""
        self.device_status[HardwareDevice.GPU]["last_check"] = datetime.now()

        if not torch.cuda.is_available() or torch.cuda.device_count() == 0:
            self.device_status[HardwareDevice.GPU]["available"] = False
            return

        try:
            # Try to get detailed metrics via pynvml
            gpu_metrics = _get_gpu_metrics_with_pynvml()
            if gpu_metrics:
                self.device_metrics[HardwareDevice.GPU] = HardwareMetrics(
                    device=HardwareDevice.GPU,
                    utilization_percent=gpu_metrics["utilization_percent"],
                    temperature_c=gpu_metrics["temperature_c"],
                    power_usage_w=gpu_metrics["power_usage_w"],
                    available_memory_mb=gpu_metrics["available_memory_mb"],
                    last_updated=datetime.now(),
                )
                logger.info("✅ GPU available: %s", torch.cuda.get_device_name(0))
            else:
                # pynvml not available, assume GPU is available with basic detection
                logger.info("✅ GPU available (basic detection)")

            self.device_status[HardwareDevice.GPU]["available"] = True
        except Exception as e:
            logger.warning("⚠️ GPU availability check failed: %s", e)
            self.device_status[HardwareDevice.GPU]["available"] = False

    async def _update_npu_metrics(self, health_data: Dict[str, Any]):
        """Update NPU metrics from health data."""
        # Estimate NPU utilization from loaded models and task count (Issue #376)
        loaded_models = len(health_data.get("loaded_models", []))
        utilization = min(
            loaded_models * HardwareAcceleratorConfig.NPU_UTILIZATION_PER_MODEL, 100.0
        )  # Rough estimation

        power_delta = (
            HardwareAcceleratorConfig.NPU_MAX_POWER_W
            - HardwareAcceleratorConfig.NPU_BASE_POWER_W
        )
        self.device_metrics[HardwareDevice.NPU] = HardwareMetrics(
            device=HardwareDevice.NPU,
            utilization_percent=utilization,
            temperature_c=HardwareAcceleratorConfig.NPU_BASE_TEMPERATURE_C
            + (
                utilization * HardwareAcceleratorConfig.NPU_TEMP_UTILIZATION_FACTOR
            ),  # Estimated
            power_usage_w=HardwareAcceleratorConfig.NPU_BASE_POWER_W
            + (utilization / 100.0 * power_delta),  # 2-10W range
            available_memory_mb=HardwareAcceleratorConfig.NPU_MEMORY_MB,
            last_updated=datetime.now(),
        )

    async def _hardware_monitoring_loop(self):
        """Monitor hardware status periodically."""
        while True:
            try:
                await asyncio.sleep(HardwareAcceleratorConfig.HARDWARE_CHECK_INTERVAL_S)
                await self._check_hardware_availability()
            except Exception as e:
                logger.error("❌ Hardware monitoring error: %s", e)

    def _classify_by_threshold(
        self, value: int, light_threshold: int, mod_threshold: int
    ) -> TaskComplexity:
        """Classify by value thresholds (Issue #315 - extracted helper)."""
        if value < light_threshold:
            return TaskComplexity.LIGHTWEIGHT
        if value < mod_threshold:
            return TaskComplexity.MODERATE
        return TaskComplexity.HEAVY

    def _classify_task_complexity(self, task: ProcessingTask) -> TaskComplexity:
        """Classify task complexity for optimal device routing (Issue #315 - refactored depth 5 to 2)."""
        task_type = task.task_type
        input_data = task.input_data

        if task_type == "embedding_generation":
            text_length = len(input_data.get("text", ""))
            return self._classify_by_threshold(
                text_length,
                HardwareAcceleratorConfig.TEXT_LIGHTWEIGHT_LENGTH,
                HardwareAcceleratorConfig.TEXT_MODERATE_LENGTH,
            )

        if task_type == "semantic_search":
            num_documents = input_data.get("num_documents", 0)
            return self._classify_by_threshold(
                num_documents,
                HardwareAcceleratorConfig.DOC_LIGHTWEIGHT_COUNT,
                HardwareAcceleratorConfig.DOC_MODERATE_COUNT,
            )

        if task_type == "chat_inference":
            model_size = input_data.get(
                "model_size_mb", model_config.MODEL_SIZE_LIGHTWEIGHT_THRESHOLD_MB
            )
            return self._classify_by_threshold(
                model_size,
                model_config.MODEL_SIZE_LIGHTWEIGHT_THRESHOLD_MB,
                model_config.MODEL_SIZE_MODERATE_THRESHOLD_MB,
            )

        return TaskComplexity.MODERATE  # Conservative default

    def _is_device_under_threshold(
        self, device: HardwareDevice, threshold: float
    ) -> bool:
        """
        Check if a device's utilization is under the specified threshold.

        Args:
            device: Hardware device to check
            threshold: Utilization threshold percentage

        Returns:
            True if device is available and under threshold. Issue #620.
        """
        if not self.device_status[device]["available"]:
            return False
        metrics = self.device_metrics.get(device)
        return not metrics or metrics.utilization_percent < threshold

    def _route_lightweight_task(self) -> HardwareDevice:
        """
        Select optimal device for lightweight tasks (NPU preferred for power efficiency).

        Returns:
            Selected hardware device for lightweight task. Issue #620.
        """
        if self._is_device_under_threshold(
            HardwareDevice.NPU, ResourceThresholds.NPU_BUSY_THRESHOLD
        ):
            return HardwareDevice.NPU

        if self._is_device_under_threshold(
            HardwareDevice.GPU, ResourceThresholds.GPU_MODERATE_THRESHOLD
        ):
            return HardwareDevice.GPU

        return HardwareDevice.CPU

    def _route_moderate_task(self) -> HardwareDevice:
        """
        Select optimal device for moderate tasks (GPU preferred for performance).

        Returns:
            Selected hardware device for moderate task. Issue #620.
        """
        if self._is_device_under_threshold(
            HardwareDevice.GPU, ResourceThresholds.GPU_BUSY_THRESHOLD
        ):
            return HardwareDevice.GPU

        if self._is_device_under_threshold(
            HardwareDevice.NPU, ResourceThresholds.NPU_AVAILABLE_THRESHOLD
        ):
            return HardwareDevice.NPU

        return HardwareDevice.CPU

    def _route_heavy_task(self) -> HardwareDevice:
        """
        Select optimal device for heavy tasks (GPU only, CPU fallback).

        Returns:
            Selected hardware device for heavy task. Issue #620.
        """
        if self.device_status[HardwareDevice.GPU]["available"]:
            return HardwareDevice.GPU
        return HardwareDevice.CPU

    def _select_optimal_device(self, task: ProcessingTask) -> HardwareDevice:
        """Select optimal device for task processing."""
        complexity = self._classify_task_complexity(task)

        # Honor preferred device if specified and available
        if (
            task.preferred_device
            and self.device_status[task.preferred_device]["available"]
        ):
            return task.preferred_device

        # Intelligent routing based on complexity and availability
        if complexity == TaskComplexity.LIGHTWEIGHT:
            return self._route_lightweight_task()
        elif complexity == TaskComplexity.MODERATE:
            return self._route_moderate_task()
        else:  # HEAVY tasks
            return self._route_heavy_task()

    async def process_task(self, task: ProcessingTask) -> ProcessingResult:
        """Process an AI task using optimal hardware (Issue #315 - refactored)."""
        start_time = time.time()
        selected_device = self._select_optimal_device(task)
        logger.info("🎯 Processing task %s on %s", task.task_id, selected_device.value)

        try:
            result = await self._route_to_processor(task, selected_device)
            return self._create_success_result(
                task, selected_device, result, start_time
            )
        except Exception as e:
            logger.error(
                "❌ Task %s failed on %s: %s", task.task_id, selected_device.value, e
            )
            return await self._handle_task_failure(task, selected_device, e, start_time)

    async def _route_to_processor(
        self, task: ProcessingTask, device: HardwareDevice
    ) -> Dict[str, Any]:
        """Route task to appropriate processor (Issue #315 - extracted)."""
        if device == HardwareDevice.NPU:
            return await self._process_on_npu(task)
        if device == HardwareDevice.GPU:
            return await self._process_on_gpu(task)
        return await self._process_on_cpu(task)

    def _create_success_result(
        self,
        task: ProcessingTask,
        device: HardwareDevice,
        result: Any,
        start_time: float,
    ) -> ProcessingResult:
        """Create successful processing result (Issue #315 - extracted)."""
        processing_time = (time.time() - start_time) * 1000
        return ProcessingResult(
            task_id=task.task_id,
            success=True,
            result=result,
            device_used=device,
            processing_time_ms=processing_time,
            device_metrics=self.device_metrics.get(device),
        )

    async def _handle_task_failure(
        self,
        task: ProcessingTask,
        selected_device: HardwareDevice,
        error: Exception,
        start_time: float,
    ) -> ProcessingResult:
        """Handle task failure with fallback (Issue #315 - extracted)."""
        fallback_device = self._get_fallback_device(selected_device)

        if fallback_device and fallback_device != selected_device:
            logger.info("🔄 Retrying task %s on %s", task.task_id, fallback_device.value)
            fallback_result = await _try_fallback_processing(
                task, fallback_device, self._process_on_gpu, self._process_on_cpu
            )
            if fallback_result is not None:
                return self._create_success_result(
                    task, fallback_device, fallback_result, start_time
                )

        processing_time = (time.time() - start_time) * 1000
        return ProcessingResult(
            task_id=task.task_id,
            success=False,
            error=str(error),
            device_used=selected_device,
            processing_time_ms=processing_time,
        )

    def _get_fallback_device(
        self, primary_device: HardwareDevice
    ) -> Optional[HardwareDevice]:
        """Get fallback device for failed processing."""
        if primary_device == HardwareDevice.NPU:
            if self.device_status[HardwareDevice.GPU]["available"]:
                return HardwareDevice.GPU
            return HardwareDevice.CPU
        elif primary_device == HardwareDevice.GPU:
            return HardwareDevice.CPU
        else:
            return None

    async def _process_on_npu(self, task: ProcessingTask) -> Dict[str, Any]:
        """Process task on NPU Worker."""
        request_data = {
            "task_type": task.task_type,
            "model_name": self._get_optimal_npu_model(task),
            "input_data": task.input_data,
            "priority": task.priority,
            "timeout_seconds": task.timeout_seconds,
        }

        # Use singleton HTTP client for connection pooling
        http_client = get_http_client()
        async with await http_client.post(
            f"{self.npu_worker_url}/inference",
            json=request_data,
            timeout=aiohttp.ClientTimeout(total=task.timeout_seconds),
        ) as response:
            if response.status == 200:
                result_data = await response.json()
                if result_data.get("status") == "completed":
                    return result_data.get("result", {})
                else:
                    raise Exception(
                        f"NPU processing failed: {result_data.get('error')}"
                    )
            else:
                raise Exception(f"NPU Worker HTTP error: {response.status}")

    def _get_optimal_npu_model(self, task: ProcessingTask) -> str:
        """Get optimal NPU model for task."""
        task_type = task.task_type

        if task_type == "embedding_generation":
            return "nomic-embed-text"
        elif task_type == "chat_inference":
            return cfg.get_default_llm_model()
        elif task_type == "text_classification":
            return "text-classification-model"
        else:
            return cfg.get_default_llm_model()  # Default

    async def _process_on_gpu(self, task: ProcessingTask) -> Dict[str, Any]:
        """Process task on GPU using existing AutoBot GPU infrastructure."""
        # This would integrate with existing GPU processing (semantic_chunker, etc.)
        # For now, simulate GPU processing

        if task.task_type == "embedding_generation":
            return await self._gpu_embedding_generation(task.input_data)
        elif task.task_type == "semantic_search":
            return await self._gpu_semantic_search(task.input_data)
        else:
            # Fallback to CPU for unsupported GPU tasks
            return await self._process_on_cpu(task)

    def _initialize_clip_model(self, device: torch.device) -> None:
        """
        Initialize CLIP model and processor for image embeddings.

        Loads openai/clip-vit-base-patch32 with appropriate dtype. Issue #620.
        """
        self.clip_processor = CLIPProcessor.from_pretrained(
            "openai/clip-vit-base-patch32"
        )
        self.clip_model = CLIPModel.from_pretrained(
            "openai/clip-vit-base-patch32",
            torch_dtype=(torch.float16 if torch.cuda.is_available() else torch.float32),
        ).to(device)
        self.clip_model.eval()

    def _initialize_wav2vec_model(self, device: torch.device) -> None:
        """
        Initialize Wav2Vec2 model and processor for audio embeddings.

        Loads facebook/wav2vec2-base-960h with appropriate dtype. Issue #620.
        """
        self.wav2vec_processor = Wav2Vec2Processor.from_pretrained(
            "facebook/wav2vec2-base-960h"
        )
        self.wav2vec_model = Wav2Vec2Model.from_pretrained(
            "facebook/wav2vec2-base-960h",
            torch_dtype=(torch.float16 if torch.cuda.is_available() else torch.float32),
        ).to(device)
        self.wav2vec_model.eval()

    def _initialize_projection_matrices(self, device: torch.device) -> None:
        """
        Initialize projection matrices for unified embedding space.

        Creates linear projections for text (384), image (512), and audio (768)
        dimensions to unified space. Issue #620.
        """
        self.text_projection = torch.nn.Linear(
            HardwareAcceleratorConfig.MINILM_OUTPUT_DIM, self.unified_dim
        ).to(device)
        self.image_projection = torch.nn.Linear(
            HardwareAcceleratorConfig.CLIP_OUTPUT_DIM, self.unified_dim
        ).to(device)
        self.audio_projection = torch.nn.Linear(
            HardwareAcceleratorConfig.WAV2VEC_OUTPUT_DIM, self.unified_dim
        ).to(device)

    async def _initialize_multimodal_models(self):
        """Initialize multi-modal models for embeddings."""
        if not MULTIMODAL_MODELS_AVAILABLE:
            logger.warning(
                "Multi-modal models not available. Install transformers library."
            )
            return

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Initializing multi-modal models on %s", device)

        try:
            self._initialize_clip_model(device)
            self._initialize_wav2vec_model(device)
            self._initialize_projection_matrices(device)
            logger.info("Multi-modal models initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize multi-modal models: %s", e)

    async def _generate_text_embedding(
        self, content: Any, device: torch.device
    ) -> np.ndarray:
        """Generate text embedding (Issue #315)."""
        from utils.semantic_chunker import get_semantic_chunker

        chunker = get_semantic_chunker()
        await chunker._initialize_model()

        sentences = [content] if isinstance(content, str) else content
        embeddings = await chunker._compute_sentence_embeddings_async(sentences)
        raw_embedding = (
            embeddings[0]
            if len(embeddings) > 0
            else np.zeros(HardwareAcceleratorConfig.MINILM_OUTPUT_DIM)
        )

        if self.text_projection:
            with torch.no_grad():
                emb_tensor = torch.tensor(raw_embedding, dtype=torch.float32).to(device)
                unified_embedding = self.text_projection(emb_tensor)
                unified_embedding = F.normalize(unified_embedding, p=2, dim=-1)
                return unified_embedding.cpu().numpy()
        return raw_embedding

    def _generate_image_embedding(
        self, content: Any, device: torch.device
    ) -> np.ndarray:
        """Generate image embedding using CLIP (Issue #315)."""
        if isinstance(content, bytes):
            image = Image.open(io.BytesIO(content)).convert("RGB")
        elif isinstance(content, str):
            image = Image.open(content).convert("RGB")
        else:
            image = content

        with torch.no_grad():
            inputs = self.clip_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}

            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    image_features = self.clip_model.get_image_features(**inputs)
            else:
                image_features = self.clip_model.get_image_features(**inputs)

            if self.image_projection:
                unified_embedding = self.image_projection(image_features.squeeze())
                unified_embedding = F.normalize(unified_embedding, p=2, dim=-1)
                return unified_embedding.cpu().numpy()
            return image_features.cpu().numpy().squeeze()

    def _generate_audio_embedding(
        self, content: Any, device: torch.device
    ) -> np.ndarray:
        """Generate audio embedding using Wav2Vec2 (Issue #315)."""
        if isinstance(content, bytes):
            audio_array = np.frombuffer(content, dtype=np.float32)
        elif isinstance(content, str):
            audio_array, _ = librosa.load(content, sr=16000)
        else:
            audio_array = content

        with torch.no_grad():
            inputs = self.wav2vec_processor(
                audio_array, sampling_rate=16000, return_tensors="pt"
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}

            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    features = self.wav2vec_model(**inputs).last_hidden_state
            else:
                features = self.wav2vec_model(**inputs).last_hidden_state

            audio_embedding = torch.mean(features, dim=1).squeeze()

            if self.audio_projection:
                unified_embedding = self.audio_projection(audio_embedding)
                unified_embedding = F.normalize(unified_embedding, p=2, dim=-1)
                return unified_embedding.cpu().numpy()
            return audio_embedding.cpu().numpy()

    async def _gpu_embedding_generation(
        self, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate embeddings using GPU acceleration (Issue #315 - dispatch table)."""
        modality = input_data.get("modality", "text")
        content = input_data.get("content") or input_data.get("text", "")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        try:
            # Dispatch table for modality handlers (Issue #315)
            if modality == "text":
                final_embedding = await self._generate_text_embedding(content, device)
            elif modality == "image" and self.clip_model:
                final_embedding = self._generate_image_embedding(content, device)
            elif modality == "audio" and self.wav2vec_model:
                final_embedding = self._generate_audio_embedding(content, device)
            else:
                raise ValueError(f"Unsupported modality: {modality}")

            # Clear GPU cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            return {
                "embeddings": final_embedding.tolist(),
                "modality": modality,
                "device": "GPU",
                "dimension": len(final_embedding),
                "unified_space": True,
            }

        except Exception as e:
            logger.error("GPU embedding generation failed: %s", e)
            return {
                "embeddings": np.zeros(self.unified_dim).tolist(),
                "modality": modality,
                "device": "GPU",
                "dimension": self.unified_dim,
                "error": str(e),
            }

    async def _gpu_semantic_search(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform semantic search using GPU acceleration."""
        # This would integrate with the existing knowledge base search
        # For now, return a placeholder result
        return {
            "search_results": [],
            "total_results": 0,
            "search_time_ms": 0,
            "device": "GPU",
        }

    async def _process_on_cpu(self, task: ProcessingTask) -> Dict[str, Any]:
        """Process task on CPU (fallback)."""
        # Basic CPU processing fallback
        await asyncio.sleep(0.1)  # Simulate processing

        return {
            "result": f"CPU processed task {task.task_type}",
            "device": "CPU",
            "fallback": True,
        }

    async def get_hardware_status(self) -> Dict[str, Any]:
        """Get comprehensive hardware status."""
        return {
            "devices": {
                device.value: {
                    "available": status["available"],
                    "last_check": (
                        status["last_check"].isoformat()
                        if status["last_check"]
                        else None
                    ),
                    "metrics": (
                        self.device_metrics.get(device).__dict__
                        if device in self.device_metrics
                        else None
                    ),
                }
                for device, status in self.device_status.items()
            },
            "routing_strategy": self.routing_strategy,
            "thresholds": self.thresholds,
            "task_history_count": len(self.task_history),
        }

    async def optimize_performance(self) -> Dict[str, Any]:
        """Analyze and optimize performance based on task history."""
        if len(self.task_history) < 10:
            return {"message": "Insufficient data for optimization"}

        # Analyze task performance by device
        device_performance = {}
        for result in self.task_history[-100:]:  # Last 100 tasks
            device = result.device_used
            if device not in device_performance:
                device_performance[device] = {
                    "count": 0,
                    "avg_time": 0,
                    "success_rate": 0,
                }

            device_performance[device]["count"] += 1
            device_performance[device]["avg_time"] += result.processing_time_ms
            if result.success:
                device_performance[device]["success_rate"] += 1

        # Calculate averages
        for device, perf in device_performance.items():
            if perf["count"] > 0:
                perf["avg_time"] /= perf["count"]
                perf["success_rate"] = (perf["success_rate"] / perf["count"]) * 100

        return {
            "performance_analysis": device_performance,
            "recommendations": self._generate_optimization_recommendations(
                device_performance
            ),
        }

    def _generate_optimization_recommendations(self, performance: Dict) -> List[str]:
        """Generate optimization recommendations based on performance data."""
        recommendations = []

        # Analyze NPU performance
        if HardwareDevice.NPU in performance:
            npu_perf = performance[HardwareDevice.NPU]
            if npu_perf["success_rate"] < 90:
                recommendations.append(
                    "NPU success rate is low - check NPU Worker stability"
                )
            if npu_perf["avg_time"] > 2000:
                recommendations.append(
                    "NPU response times are high - consider model optimization"
                )
        else:
            recommendations.append(
                "NPU not being utilized - verify NPU Worker connection"
            )

        # Analyze GPU performance
        if HardwareDevice.GPU in performance:
            gpu_perf = performance[HardwareDevice.GPU]
            if gpu_perf["avg_time"] > 5000:
                recommendations.append(
                    "GPU response times are high - check GPU utilization"
                )

        return recommendations


# Global instance (thread-safe)
import asyncio as _asyncio_lock

_ai_accelerator = None
_ai_accelerator_lock = _asyncio_lock.Lock()


async def get_ai_accelerator() -> AIHardwareAccelerator:
    """Get the global AI hardware accelerator instance (thread-safe)."""
    global _ai_accelerator
    if _ai_accelerator is None:
        async with _ai_accelerator_lock:
            # Double-check after acquiring lock
            if _ai_accelerator is None:
                _ai_accelerator = AIHardwareAccelerator()
                await _ai_accelerator.initialize()
    return _ai_accelerator


# Convenience functions for common tasks
async def accelerated_embedding_generation(
    content: Union[str, bytes, np.ndarray],
    modality: str = "text",
    preferred_device: Optional[HardwareDevice] = None,
) -> np.ndarray:
    """
    Generate embeddings using optimal hardware acceleration.

    Args:
        content: Input content (text string, image bytes/path, audio array/path)
        modality: Type of input ('text', 'image', 'audio')
        preferred_device: Preferred hardware device for processing

    Returns:
        np.ndarray: Unified embedding vector (512 dimensions)
    """
    accelerator = await get_ai_accelerator()

    task = ProcessingTask(
        task_id=f"embedding_{modality}_{int(time.time()*1000)}",
        task_type="embedding_generation",
        input_data={
            "content": content,
            "modality": modality,
            "text": content if modality == "text" else None,  # Backward compatibility
        },
        complexity=(
            TaskComplexity.LIGHTWEIGHT
            if modality == "text"
            else TaskComplexity.MODERATE
        ),
        preferred_device=preferred_device,
    )

    result = await accelerator.process_task(task)

    if result.success and "embeddings" in result.result:
        return np.array(result.result["embeddings"])
    else:
        raise Exception(f"Embedding generation failed for {modality}: {result.error}")


async def compute_cross_modal_similarity(
    embedding1: np.ndarray, embedding2: np.ndarray
) -> float:
    """
    Compute cosine similarity between embeddings from different modalities.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        float: Cosine similarity score between -1 and 1
    """
    # Normalize vectors
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    # Compute cosine similarity
    similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
    return float(similarity)


async def accelerated_semantic_search(
    query: str,
    documents: List[str],
    top_k: int = 10,
    preferred_device: Optional[HardwareDevice] = None,
) -> List[Dict[str, Any]]:
    """Perform semantic search using optimal hardware acceleration."""
    accelerator = await get_ai_accelerator()

    # Determine complexity based on document count
    if len(documents) < 100:
        complexity = TaskComplexity.LIGHTWEIGHT
    elif len(documents) < 1000:
        complexity = TaskComplexity.MODERATE
    else:
        complexity = TaskComplexity.HEAVY

    task = ProcessingTask(
        task_id=f"search_{int(time.time()*1000)}",
        task_type="semantic_search",
        input_data={
            "query": query,
            "documents": documents,
            "top_k": top_k,
            "num_documents": len(documents),
        },
        complexity=complexity,
        preferred_device=preferred_device,
    )

    result = await accelerator.process_task(task)

    if result.success:
        return result.result.get("search_results", [])
    else:
        raise Exception(f"Semantic search failed: {result.error}")
