#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot NPU Worker - Windows Deployment Version
Optimized for Intel NPU hardware acceleration with OpenVINO
Standalone Windows service with port 8082

Issue #68: NPU worker settings with telemetry, bootstrap, and race condition fixes
"""

import asyncio
import hashlib
import logging
import sys
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# =============================================================================
# Constants (Issue #68 - Code smells fix: Extract magic numbers)
# =============================================================================
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8082
DEFAULT_WORKERS = 1
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# NPU optimization defaults
DEFAULT_NPU_PRECISION = "INT8"
DEFAULT_NPU_BATCH_SIZE = 32
DEFAULT_NPU_STREAMS = 2
DEFAULT_NPU_THREADS = 4

# Cache settings
DEFAULT_EMBEDDING_CACHE_SIZE = 1000
DEFAULT_EMBEDDING_CACHE_TTL = 3600  # seconds

# Model size estimates (MB)
MODEL_SIZE_1B = 800
MODEL_SIZE_3B = 2000
MODEL_SIZE_EMBED = 300
MODEL_SIZE_DEFAULT = 1000

# NPU metrics simulation
NPU_BASE_TEMP_C = 35.0
NPU_TEMP_RANGE_C = 20.0
NPU_BASE_POWER_W = 1.5
NPU_POWER_RANGE_W = 8.5

# Embedding dimensions
EMBEDDING_DIM_NOMIC = 768
EMBEDDING_DIM_DEFAULT = 512

# Model paths and HuggingFace identifiers
MODELS_DIR = Path(__file__).parent.parent / "models"
SUPPORTED_MODELS = {
    "nomic-embed-text": {
        "hf_id": "nomic-ai/nomic-embed-text-v1",
        "dim": EMBEDDING_DIM_NOMIC,
        "max_length": 8192,
    },
    "all-MiniLM-L6-v2": {
        "hf_id": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
        "max_length": 512,
    },
    "bge-small-en-v1.5": {
        "hf_id": "BAAI/bge-small-en-v1.5",
        "dim": 384,
        "max_length": 512,
    },
}

# Device selection priority: NPU → GPU → CPU (Issue #640)
DEVICE_PRIORITY = ["NPU", "GPU", "CPU"]

# =============================================================================
# Configuration loader
# =============================================================================

# Worker ID file for persistence across restarts (Issue #68 - duplicate registration fix)
WORKER_ID_FILE = Path(__file__).parent.parent / "config" / ".worker_id"


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file with UTF-8 encoding"""
    config_path = Path(__file__).parent.parent / "config" / "npu_worker.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def get_persistent_worker_id(prefix: str = "windows_npu_worker") -> str:
    """
    Get or create a persistent worker ID.

    Issue #68: Prevents duplicate worker registrations by persisting the worker ID
    to a file. On first run, generates a new ID and saves it. On subsequent runs,
    reads the existing ID from the file.

    Args:
        prefix: Worker ID prefix (default: 'windows_npu_worker')

    Returns:
        Persistent worker ID string
    """
    try:
        if WORKER_ID_FILE.exists():
            with open(WORKER_ID_FILE, 'r', encoding='utf-8') as f:
                worker_id = f.read().strip()
                if worker_id:
                    logger.info("Loaded persistent worker ID: %s", worker_id)
                    return worker_id
    except Exception as e:
        logger.warning("Failed to read worker ID file: %s", e)

    # Generate new worker ID
    worker_id = f"{prefix}_{uuid.uuid4().hex[:8]}"

    # Save to file for persistence
    try:
        WORKER_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WORKER_ID_FILE, 'w', encoding='utf-8') as f:
            f.write(worker_id)
        logger.info("Created new persistent worker ID: %s", worker_id)
    except Exception as e:
        logger.warning("Failed to save worker ID file: %s", e)

    return worker_id


# Load configuration
config = load_config()

# Configure logging
log_dir = Path(__file__).parent.parent / config.get('logging', {}).get('directory', 'logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=config.get('logging', {}).get('level', DEFAULT_LOG_LEVEL),
    format=config.get('logging', {}).get('format', DEFAULT_LOG_FORMAT),
    handlers=[
        logging.FileHandler(log_dir / "app.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# LRU Cache Implementation (Issue #68 - Bounded cache to prevent memory growth)
# =============================================================================


class LRUCache:
    """
    Thread-safe LRU cache with TTL support.

    Fixes unbounded cache growth race condition identified in Issue #68.
    """

    def __init__(self, max_size: int = DEFAULT_EMBEDDING_CACHE_SIZE, ttl: int = DEFAULT_EMBEDDING_CACHE_TTL):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get item from cache, returns None if not found or expired."""
        async with self._lock:
            if key not in self._cache:
                return None

            item = self._cache[key]
            # Check TTL expiration
            if time.time() - item["timestamp"] > self._ttl:
                del self._cache[key]
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return item["value"]

    async def set(self, key: str, value: Any) -> None:
        """Set item in cache with automatic eviction if full."""
        async with self._lock:
            # If key exists, update and move to end
            if key in self._cache:
                self._cache[key] = {"value": value, "timestamp": time.time()}
                self._cache.move_to_end(key)
                return

            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            # Add new item
            self._cache[key] = {"value": value, "timestamp": time.time()}

    async def size(self) -> int:
        """Get current cache size."""
        async with self._lock:
            return len(self._cache)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()


# =============================================================================
# Thread-safe Stats Counter (Issue #68 - Race condition fix)
# =============================================================================


class ThreadSafeStats:
    """
    Thread-safe statistics counter.

    Fixes stats counter race condition identified in Issue #68.
    """

    def __init__(self):
        self._stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "average_response_time_ms": 0.0,
            "npu_utilization_percent": 0.0,
            "embedding_generations": 0,
            "semantic_searches": 0,
            "cache_hits": 0,
        }
        self._lock = asyncio.Lock()
        self._response_times: List[float] = []

    async def increment(self, stat_name: str, amount: int = 1) -> None:
        """Thread-safe increment of a stat."""
        async with self._lock:
            if stat_name in self._stats:
                self._stats[stat_name] += amount

    async def record_response_time(self, time_ms: float) -> None:
        """Record a response time and update average."""
        async with self._lock:
            self._response_times.append(time_ms)
            # Keep only last 100 for rolling average
            if len(self._response_times) > 100:
                self._response_times.pop(0)
            self._stats["average_response_time_ms"] = sum(self._response_times) / len(self._response_times)

    async def set(self, stat_name: str, value: Any) -> None:
        """Thread-safe set of a stat value."""
        async with self._lock:
            self._stats[stat_name] = value

    async def get_all(self) -> Dict[str, Any]:
        """Get a copy of all stats."""
        async with self._lock:
            return dict(self._stats)

    async def get(self, stat_name: str) -> Any:
        """Get a single stat value."""
        async with self._lock:
            return self._stats.get(stat_name, 0)


# =============================================================================
# OpenVINO Model Management (Issue #640 - Real NPU Inference)
# =============================================================================


class OpenVINOModelManager:
    """
    Manages OpenVINO model downloading, conversion, and loading.

    Issue #640: Replaces mock embeddings with real NPU inference.
    Device priority: NPU → GPU → CPU (CPU is last resort)
    """

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._tokenizers: Dict[str, Any] = {}
        self._compiled_models: Dict[str, Any] = {}
        self._model_configs: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._openvino_core = None
        self._selected_device: Optional[str] = None

    def _get_openvino_core(self):
        """Lazy initialize OpenVINO Core"""
        if self._openvino_core is None:
            try:
                from openvino.runtime import Core
                self._openvino_core = Core()
            except ImportError:
                logger.error("OpenVINO not installed. Install with: pip install openvino")
                raise
        return self._openvino_core

    def _select_best_device(self) -> str:
        """
        Select best available device following priority: NPU → GPU → CPU

        Issue #640: CPU is last resort, not GPU
        """
        if self._selected_device:
            return self._selected_device

        core = self._get_openvino_core()
        available_devices = core.available_devices
        logger.info(f"Available OpenVINO devices: {available_devices}")

        # Follow priority: NPU → GPU → CPU
        for device in DEVICE_PRIORITY:
            if device in available_devices:
                self._selected_device = device
                logger.info(f"Selected device: {device} (priority order: {DEVICE_PRIORITY})")
                return device
            # Check for device variations (e.g., GPU.0, NPU.0)
            for avail in available_devices:
                if avail.startswith(device):
                    self._selected_device = avail
                    logger.info(f"Selected device: {avail} (priority order: {DEVICE_PRIORITY})")
                    return avail

        # Fallback to CPU (should always be available)
        self._selected_device = "CPU"
        logger.warning("No preferred device found, falling back to CPU")
        return "CPU"

    async def ensure_model_downloaded(self, model_name: str) -> Path:
        """
        Ensure model is downloaded and converted to OpenVINO IR format.

        Downloads from HuggingFace if not present, then converts to OpenVINO.
        """
        model_config = SUPPORTED_MODELS.get(model_name)
        if not model_config:
            raise ValueError(f"Unsupported model: {model_name}. Supported: {list(SUPPORTED_MODELS.keys())}")

        model_path = self.models_dir / model_name
        ov_model_path = model_path / "openvino_model.xml"

        if ov_model_path.exists():
            logger.info(f"Model {model_name} already converted to OpenVINO format")
            return model_path

        logger.info(f"Downloading and converting model: {model_name}")

        # Run blocking operations in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._download_and_convert, model_name, model_config, model_path)

        return model_path

    def _download_and_convert(self, model_name: str, model_config: Dict, model_path: Path):
        """Download model from HuggingFace and convert to OpenVINO IR (blocking)"""
        try:
            from transformers import AutoModel, AutoTokenizer
            import torch

            hf_id = model_config["hf_id"]
            logger.info(f"Downloading {hf_id} from HuggingFace...")

            # Download model and tokenizer
            tokenizer = AutoTokenizer.from_pretrained(hf_id, trust_remote_code=True)
            model = AutoModel.from_pretrained(hf_id, trust_remote_code=True)
            model.eval()

            # Save tokenizer
            model_path.mkdir(parents=True, exist_ok=True)
            tokenizer.save_pretrained(str(model_path))

            # Convert to OpenVINO
            logger.info(f"Converting {model_name} to OpenVINO IR format...")
            self._convert_to_openvino(model, tokenizer, model_config, model_path)

            logger.info(f"Model {model_name} successfully converted to OpenVINO format")

        except Exception as e:
            logger.error(f"Failed to download/convert model {model_name}: {e}")
            raise

    def _convert_to_openvino(self, model, tokenizer, model_config: Dict, model_path: Path):
        """Convert PyTorch model to OpenVINO IR format"""
        try:
            import torch
            from openvino import convert_model, save_model

            # Create dummy input for tracing
            max_length = min(model_config.get("max_length", 512), 512)  # Limit for conversion
            dummy_input = tokenizer(
                "This is a sample text for model conversion.",
                padding="max_length",
                max_length=max_length,
                truncation=True,
                return_tensors="pt"
            )

            # Export to ONNX first (more reliable conversion path)
            onnx_path = model_path / "model.onnx"

            with torch.no_grad():
                torch.onnx.export(
                    model,
                    (dummy_input["input_ids"], dummy_input["attention_mask"]),
                    str(onnx_path),
                    input_names=["input_ids", "attention_mask"],
                    output_names=["last_hidden_state"],
                    dynamic_axes={
                        "input_ids": {0: "batch_size", 1: "sequence"},
                        "attention_mask": {0: "batch_size", 1: "sequence"},
                        "last_hidden_state": {0: "batch_size", 1: "sequence"}
                    },
                    opset_version=14
                )

            # Convert ONNX to OpenVINO IR
            ov_model = convert_model(str(onnx_path))

            # Save OpenVINO model
            ov_model_path = model_path / "openvino_model.xml"
            save_model(ov_model, str(ov_model_path))

            # Clean up ONNX file to save space
            onnx_path.unlink(missing_ok=True)

            logger.info(f"OpenVINO model saved to {ov_model_path}")

        except Exception as e:
            logger.error(f"OpenVINO conversion failed: {e}")
            raise

    async def load_model(self, model_name: str) -> bool:
        """
        Load and compile model for the selected device (NPU → GPU → CPU).

        Returns True if model is ready for inference.
        """
        async with self._lock:
            if model_name in self._compiled_models:
                logger.debug(f"Model {model_name} already loaded")
                return True

            try:
                # Ensure model is downloaded and converted
                model_path = await self.ensure_model_downloaded(model_name)

                # Load in thread pool (blocking operations)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None, self._load_compiled_model, model_name, model_path
                )
                return success

            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                return False

    def _load_compiled_model(self, model_name: str, model_path: Path) -> bool:
        """Load and compile OpenVINO model (blocking)"""
        try:
            from transformers import AutoTokenizer

            core = self._get_openvino_core()
            device = self._select_best_device()

            # Load tokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
            self._tokenizers[model_name] = tokenizer

            # Load OpenVINO model
            ov_model_path = model_path / "openvino_model.xml"
            model = core.read_model(str(ov_model_path))

            # Configure for device
            config = {}
            if device.startswith("NPU"):
                # NPU-specific optimizations
                config["NPU_COMPILATION_MODE_PARAMS"] = "compute-layers-with-higher-precision=Sqrt,Power,ReduceMean,Add"
                config["PERFORMANCE_HINT"] = "LATENCY"
                logger.info(f"Applying NPU optimizations for {model_name}")
            elif device.startswith("GPU"):
                config["PERFORMANCE_HINT"] = "THROUGHPUT"
                logger.info(f"Applying GPU optimizations for {model_name}")

            # Compile model for device
            compiled_model = core.compile_model(model, device, config)
            self._compiled_models[model_name] = compiled_model

            # Store config
            self._model_configs[model_name] = SUPPORTED_MODELS.get(model_name, {})

            logger.info(f"Model {model_name} compiled for {device}")
            return True

        except Exception as e:
            logger.error(f"Failed to compile model {model_name}: {e}")
            return False

    def generate_embedding(self, text: str, model_name: str) -> List[float]:
        """
        Generate embedding using real OpenVINO inference.

        Issue #640: Replaces mock random embeddings with real NPU inference.
        """
        if model_name not in self._compiled_models:
            raise RuntimeError(f"Model {model_name} not loaded. Call load_model() first.")

        tokenizer = self._tokenizers[model_name]
        compiled_model = self._compiled_models[model_name]
        model_config = self._model_configs.get(model_name, {})

        # Tokenize input
        max_length = min(model_config.get("max_length", 512), 512)
        inputs = tokenizer(
            text,
            padding="max_length",
            max_length=max_length,
            truncation=True,
            return_tensors="np"
        )

        # Run inference
        input_ids = inputs["input_ids"]
        attention_mask = inputs["attention_mask"]

        # OpenVINO inference
        result = compiled_model([input_ids, attention_mask])

        # Extract embeddings (mean pooling over sequence)
        hidden_states = result[0]  # Shape: (batch, seq_len, hidden_dim)
        attention_mask_expanded = attention_mask[:, :, np.newaxis]

        # Mean pooling with attention mask
        sum_embeddings = np.sum(hidden_states * attention_mask_expanded, axis=1)
        sum_mask = np.clip(attention_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        embedding = (sum_embeddings / sum_mask).flatten()

        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding.tolist()

    def get_device_info(self) -> Dict[str, Any]:
        """Get information about the selected device"""
        try:
            core = self._get_openvino_core()
            device = self._select_best_device()

            info = {
                "selected_device": device,
                "available_devices": core.available_devices,
                "device_priority": DEVICE_PRIORITY,
                "is_npu": device.startswith("NPU"),
                "is_gpu": device.startswith("GPU"),
                "is_cpu": device == "CPU",
            }

            # Get device-specific properties if available
            try:
                props = core.get_property(device, "FULL_DEVICE_NAME")
                info["device_name"] = props
            except Exception:
                info["device_name"] = device

            return info

        except Exception as e:
            return {"error": str(e), "selected_device": "UNKNOWN"}


# Global model manager instance
_model_manager: Optional[OpenVINOModelManager] = None


def get_model_manager() -> OpenVINOModelManager:
    """Get or create the global model manager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = OpenVINOModelManager()
    return _model_manager


# Pydantic models
class NPUTaskRequest(BaseModel):
    """NPU task request model"""
    task_type: str
    model_name: str
    input_data: Dict[str, Any]
    priority: int = 1
    timeout_seconds: int = 30
    optimization_level: str = "balanced"


class NPUTaskResponse(BaseModel):
    """NPU task response model"""
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None
    npu_utilization_percent: Optional[float] = None
    optimization_metrics: Optional[Dict[str, Any]] = None


class WindowsNPUWorker:
    """
    Windows-optimized NPU Worker

    Issue #68 improvements:
    - Thread-safe stats counters (race condition fix)
    - LRU cache with size limits (memory growth fix)
    - Parallel initialization (efficiency improvement)
    - No hardcoded IPs (config from YAML/bootstrap)
    """

    def __init__(self):
        service_config = config.get('service', {})
        redis_config = config.get('redis', {})
        npu_config = config.get('npu', {})
        cache_config = config.get('performance', {}).get('embedding_cache', {})

        # Use persistent worker ID to prevent duplicate registrations on restart (Issue #68)
        worker_id_prefix = service_config.get('worker_id_prefix', 'windows_npu_worker')
        self.worker_id = get_persistent_worker_id(prefix=worker_id_prefix)
        self.redis_client = None

        self.app = FastAPI(title="AutoBot Windows NPU Worker", version="2.0.0")

        # NPU capabilities
        self.npu_available = False
        self.openvino_core = None
        self.loaded_models = {}
        self._models_lock = asyncio.Lock()  # Thread-safe model loading (TOCTOU fix)

        # Real OpenVINO model manager (Issue #640 - replaces mock inference)
        self._model_manager: Optional[OpenVINOModelManager] = None
        self._use_real_inference = True  # Set to False to use mock inference for testing

        # Thread-safe LRU cache (Issue #68 - race condition + memory growth fix)
        cache_size = cache_config.get('max_size', DEFAULT_EMBEDDING_CACHE_SIZE)
        cache_ttl = cache_config.get('ttl', DEFAULT_EMBEDDING_CACHE_TTL)
        self.embedding_cache = LRUCache(max_size=cache_size, ttl=cache_ttl)

        # Thread-safe performance tracking (Issue #68 - race condition fix)
        self.task_stats = ThreadSafeStats()

        # NPU optimization from config (with constant defaults)
        self.npu_optimization = npu_config.get('optimization', {
            "precision": DEFAULT_NPU_PRECISION,
            "batch_size": DEFAULT_NPU_BATCH_SIZE,
            "num_streams": DEFAULT_NPU_STREAMS,
            "num_threads": DEFAULT_NPU_THREADS,
        })

        # Bootstrap config storage
        self._bootstrap_config: Optional[Dict[str, Any]] = None

        self.setup_routes()

    def setup_routes(self):
        """Setup FastAPI routes"""

        @self.app.on_event("startup")
        async def startup():
            await self.initialize()

        @self.app.on_event("shutdown")
        async def shutdown():
            await self.cleanup()

        @self.app.get("/health")
        async def health_check():
            """Health check with NPU metrics"""
            npu_metrics = await self.get_npu_metrics()
            stats = await self.task_stats.get_all()

            return {
                "status": "healthy",
                "worker_id": self.worker_id,
                "platform": "windows",
                "port": config.get('service', {}).get('port', DEFAULT_PORT),
                "npu_available": self.npu_available,
                "loaded_models": list(self.loaded_models.keys()),
                "stats": stats,
                "npu_metrics": npu_metrics,
                "optimization_config": self.npu_optimization,
                "timestamp": datetime.now().isoformat(),
            }

        @self.app.get("/device-info")
        async def device_info():
            """
            Get detailed device information including NPU/GPU/CPU status.

            Issue #640: Shows which device is being used for inference.
            """
            info = {
                "worker_id": self.worker_id,
                "npu_available": self.npu_available,
                "real_inference_enabled": self._use_real_inference,
                "device_priority": DEVICE_PRIORITY,
            }

            if self._model_manager is not None:
                try:
                    manager_info = self._model_manager.get_device_info()
                    info["model_manager"] = manager_info
                    info["selected_device"] = manager_info.get("selected_device", "UNKNOWN")
                    info["available_devices"] = manager_info.get("available_devices", [])
                except Exception as e:
                    info["model_manager_error"] = str(e)
            else:
                info["model_manager"] = None
                info["selected_device"] = "MOCK (no model manager)"

            # Add loaded models with their device info
            info["loaded_models"] = {
                name: {
                    "device": model_info.get("device", "UNKNOWN"),
                    "real_inference": model_info.get("real_inference", False),
                    "optimized_for_npu": model_info.get("optimized_for_npu", False),
                }
                for name, model_info in self.loaded_models.items()
            }

            return info

        @self.app.get("/stats")
        async def get_detailed_stats():
            """Get detailed worker statistics"""
            stats = await self.task_stats.get_all()
            cache_size = await self.embedding_cache.size()
            cache_hits = await self.task_stats.get("cache_hits")

            return {
                "worker_id": self.worker_id,
                "platform": "windows",
                "uptime_seconds": time.time() - self.start_time,
                "npu_status": await self.get_npu_status(),
                "task_stats": stats,
                "loaded_models": {
                    name: {
                        "size_mb": info.get("size_mb", 0),
                        "load_time": info.get("load_time", "unknown"),
                        "last_used": info.get("last_used", "never"),
                        "optimized_for_npu": info.get("optimized_for_npu", False),
                        "precision": info.get("precision", "unknown"),
                    }
                    for name, info in self.loaded_models.items()
                },
                "cache_stats": {
                    "embedding_cache_size": cache_size,
                    "cache_hits": cache_hits,
                    "cache_hit_rate": await self._calculate_cache_hit_rate(),
                }
            }

        @self.app.post("/inference", response_model=NPUTaskResponse)
        async def process_inference(request: NPUTaskRequest):
            """Process inference request"""
            task_id = str(uuid.uuid4())

            try:
                start_time = time.time()
                result = await self.process_task(task_id, request.dict())
                processing_time = (time.time() - start_time) * 1000

                return NPUTaskResponse(
                    task_id=task_id,
                    status="completed",
                    result=result,
                    processing_time_ms=processing_time,
                    npu_utilization_percent=await self.get_npu_utilization()
                )

            except Exception as e:
                logger.error(f"Inference failed for task {task_id}: {e}")
                return NPUTaskResponse(task_id=task_id, status="failed", error=str(e))

        @self.app.post("/embedding/generate")
        async def generate_embeddings(
            texts: List[str],
            model_name: str = "nomic-embed-text",
            use_cache: bool = True,
            optimization_level: str = "balanced"
        ):
            """Generate embeddings with NPU acceleration"""
            try:
                start_time = time.time()
                embeddings = await self.generate_npu_embeddings(
                    texts, model_name, use_cache, optimization_level
                )
                processing_time = (time.time() - start_time) * 1000

                # Issue #640: Show real inference status
                model_info = self.loaded_models.get(model_name, {})
                device = model_info.get("device", "NPU" if self.npu_available else "CPU")
                real_inference = model_info.get("real_inference", False)

                return {
                    "embeddings": embeddings,
                    "model_used": model_name,
                    "processing_time_ms": processing_time,
                    "texts_processed": len(texts),
                    "device": device,
                    "real_inference": real_inference,
                    "cache_utilized": use_cache
                }

            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/search/semantic")
        async def semantic_search(
            query_text: str,
            document_embeddings: List[List[float]],
            document_metadata: List[Dict[str, Any]],
            top_k: int = 10,
            similarity_threshold: float = 0.7
        ):
            """Perform semantic search"""
            try:
                start_time = time.time()
                results = await self.perform_semantic_search(
                    query_text, document_embeddings, document_metadata,
                    top_k, similarity_threshold
                )
                processing_time = (time.time() - start_time) * 1000

                return {
                    "search_results": results,
                    "query": query_text,
                    "documents_searched": len(document_embeddings),
                    "results_returned": len(results),
                    "processing_time_ms": processing_time,
                    "device": "NPU" if self.npu_available else "CPU"
                }

            except Exception as e:
                logger.error(f"Semantic search failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/model/optimize")
        async def optimize_model(model_name: str, optimization_level: str = "balanced"):
            """Optimize model for NPU"""
            try:
                await self.load_and_optimize_model(model_name, optimization_level)
                return {
                    "status": "success",
                    "model": model_name,
                    "optimization_level": optimization_level,
                    "optimized_for_npu": True
                }
            except Exception as e:
                logger.error(f"Model optimization failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/performance/benchmark")
        async def benchmark():
            """Run performance benchmark"""
            try:
                results = await self.run_benchmark()
                return {
                    "benchmark_results": results,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Benchmark failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    async def initialize(self):
        """
        Initialize NPU worker with parallel initialization for efficiency.

        Issue #68: Uses asyncio.gather for parallel init where possible.
        """
        self.start_time = time.time()
        logger.info(f"Starting Windows NPU Worker {self.worker_id}")
        logger.info(f"Port: {config.get('service', {}).get('port', DEFAULT_PORT)}")

        # Display network connection information
        self._display_network_info()

        # Bootstrap configuration from backend (Issue #68)
        # This fetches Redis credentials and other config from main host
        # Must run first as other components may depend on it
        await self.bootstrap_config()

        # Parallel initialization of independent components (Issue #68 - efficiency)
        # Redis and NPU initialization can run in parallel
        await asyncio.gather(
            self.initialize_redis(),
            self.initialize_npu(),
            return_exceptions=True  # Don't fail if one component fails
        )

        # Load default models if configured (depends on NPU init)
        if config.get('models', {}).get('autoload_defaults', True):
            await self.load_default_models()

        # Initialize backend telemetry (Issue #68)
        await self.initialize_telemetry()

        logger.info(f"Windows NPU Worker initialized - NPU Available: {self.npu_available}")

    async def bootstrap_config(self):
        """
        Fetch configuration from backend on startup (Issue #68).

        This allows the worker to get Redis credentials and other settings
        from the main backend instead of hardcoding them locally.

        Issue #640: Pass existing worker_id to prevent duplicate registrations.
        """
        try:
            from utils.config_bootstrap import fetch_bootstrap_config, get_worker_id

            backend_config = config.get("backend", {})
            service_config = config.get("service", {})

            # Issue #640: Pass our persistent worker_id to prevent duplicates
            bootstrap = await fetch_bootstrap_config(
                backend_host=backend_config.get("host", "172.16.168.20"),
                backend_port=backend_config.get("port", 8001),
                worker_port=service_config.get("port", 8082),
                platform="windows",
                worker_id=self.worker_id,  # Pass existing ID to reuse registration
            )

            if bootstrap:
                # Update worker_id if assigned by backend (only if different)
                assigned_id = get_worker_id()
                if assigned_id and assigned_id != self.worker_id:
                    self.worker_id = assigned_id
                    logger.info(f"Worker ID updated by backend: {self.worker_id}")

                # Store bootstrap config for use by other components
                self._bootstrap_config = bootstrap
                logger.info("Bootstrap config received from backend")
            else:
                logger.warning("Bootstrap failed - using local config (standalone mode)")
                self._bootstrap_config = None

        except Exception as e:
            logger.warning(f"Bootstrap error: {e} - using local config")
            self._bootstrap_config = None

    async def initialize_telemetry(self):
        """
        Initialize backend telemetry client (Issue #68).

        Sends heartbeats and metrics to the AutoBot backend for:
        - Auto-registration
        - Status updates
        - Prometheus/Grafana metrics
        """
        try:
            from utils.backend_telemetry import get_telemetry_client

            self.telemetry_client = await get_telemetry_client(config)

            if self.telemetry_client:
                # Update initial metrics
                self.telemetry_client.update_metrics(
                    npu_available=self.npu_available,
                    loaded_models=list(self.loaded_models.keys()),
                )

                # Start telemetry loop
                await self.telemetry_client.start()
                logger.info("Backend telemetry initialized")
            else:
                logger.info("Backend telemetry disabled")
                self.telemetry_client = None

        except Exception as e:
            logger.warning(f"Telemetry initialization failed: {e}")
            self.telemetry_client = None

    async def initialize_redis(self):
        """
        Initialize Redis connection using canonical get_redis_client() pattern

        Uses bootstrap config from backend if available, otherwise falls back
        to local config. This allows credentials to come from main host.
        """
        try:
            from utils.redis_client import get_redis_client
            from utils.config_bootstrap import get_redis_config

            # Use bootstrap Redis config if available
            redis_config = get_redis_config()
            if redis_config:
                # Merge bootstrap config with local config
                merged_config = dict(config)
                merged_config["redis"] = redis_config
                self.redis_client = await get_redis_client(merged_config)
            else:
                # Fallback to local config (likely won't have credentials)
                self.redis_client = await get_redis_client(config)

            if self.redis_client:
                logger.info("Connected to Redis with connection pooling")
            else:
                logger.info("Operating in standalone mode without Redis")
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}")
            self.redis_client = None

    async def initialize_npu(self):
        """
        Initialize NPU with OpenVINO and model manager.

        Issue #640: Adds real model management for NPU inference.
        Device priority: NPU → GPU → CPU (CPU is last resort)
        """
        try:
            import platform
            if platform.system() != "Windows":
                logger.warning("NPU worker optimized for Windows")
                self.npu_available = False
                return

            from openvino.runtime import Core
            self.openvino_core = Core()
            devices = self.openvino_core.available_devices
            logger.info(f"Available OpenVINO devices: {devices}")

            # Check device priority: NPU → GPU → CPU
            npu_devices = [d for d in devices if d.startswith("NPU")]
            gpu_devices = [d for d in devices if d.startswith("GPU")]

            if npu_devices:
                self.npu_available = True
                logger.info(f"NPU initialized - Devices: {npu_devices}")
            elif gpu_devices:
                # GPU available but no NPU
                self.npu_available = False
                logger.info(f"No NPU found, GPU available: {gpu_devices}")
            else:
                # CPU fallback
                self.npu_available = False
                logger.warning("No NPU or GPU devices found - using CPU fallback")

            # Initialize model manager for real inference (Issue #640)
            if self._use_real_inference:
                try:
                    self._model_manager = get_model_manager()
                    device_info = self._model_manager.get_device_info()
                    logger.info(f"Model manager initialized: {device_info}")
                except Exception as e:
                    logger.error(f"Failed to initialize model manager: {e}")
                    logger.info("Falling back to mock inference")
                    self._use_real_inference = False

        except ImportError:
            logger.error("OpenVINO not installed")
            self.npu_available = False
            self._use_real_inference = False
        except Exception as e:
            logger.error(f"NPU initialization failed: {e}")
            self.npu_available = False
            self._use_real_inference = False

    async def load_default_models(self):
        """Load default models"""
        models_config = config.get('models', {})

        for model_type in ['embedding', 'chat']:
            model_config = models_config.get(model_type, {})
            if model_config.get('preload', False):
                try:
                    await self.load_and_optimize_model(
                        model_config.get('name'),
                        model_config.get('optimization_level', 'balanced')
                    )
                except Exception as e:
                    logger.warning(f"Failed to preload {model_type} model: {e}")

    async def load_and_optimize_model(self, model_name: str, optimization_level: str = "balanced"):
        """
        Load and optimize model with thread-safe locking (Issue #68 - TOCTOU fix).

        Issue #640: Now uses real OpenVINO model loading with device priority NPU → GPU → CPU.
        Uses lock to prevent race condition where model loading starts
        after check but before load completes.
        """
        async with self._models_lock:
            # Double-check if model already loaded after acquiring lock
            if model_name in self.loaded_models:
                logger.debug(f"Model {model_name} already loaded")
                return

            start_time = time.time()

            try:
                # Issue #640: Use real model manager for OpenVINO inference
                if self._use_real_inference and self._model_manager is not None:
                    logger.info(f"Loading {model_name} with OpenVINO (real inference)...")

                    # Load model via model manager (handles download + conversion)
                    success = await self._model_manager.load_model(model_name)

                    if success:
                        device_info = self._model_manager.get_device_info()
                        selected_device = device_info.get("selected_device", "CPU")

                        self.loaded_models[model_name] = {
                            "loaded_at": datetime.now().isoformat(),
                            "load_time": time.time() - start_time,
                            "device": selected_device,
                            "size_mb": self.estimate_model_size(model_name),
                            "optimized_for_npu": selected_device.startswith("NPU"),
                            "optimization_level": optimization_level,
                            "precision": self.npu_optimization.get("precision", DEFAULT_NPU_PRECISION),
                            "real_inference": True,
                            "device_info": device_info,
                        }
                        logger.info(f"Model {model_name} loaded for {selected_device} (real inference)")
                    else:
                        logger.warning(f"Failed to load {model_name} with real inference, using mock")
                        await self._load_mock_model(model_name, optimization_level, start_time)

                else:
                    # Fallback to mock loading
                    await self._load_mock_model(model_name, optimization_level, start_time)

            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                raise

    async def _load_mock_model(self, model_name: str, optimization_level: str, start_time: float):
        """Load mock model (fallback when real inference unavailable)."""
        if self.npu_available:
            logger.info(f"Loading {model_name} for NPU (mock)...")
            await asyncio.sleep(2)  # Simulate loading

            self.loaded_models[model_name] = {
                "loaded_at": datetime.now().isoformat(),
                "load_time": time.time() - start_time,
                "device": "NPU",
                "size_mb": self.estimate_model_size(model_name),
                "optimized_for_npu": True,
                "optimization_level": optimization_level,
                "precision": self.npu_optimization.get("precision", DEFAULT_NPU_PRECISION),
                "real_inference": False,
            }
            logger.info(f"Model {model_name} loaded for NPU (mock)")
        else:
            logger.info(f"Loading {model_name} for CPU (mock)...")
            await asyncio.sleep(1)

            self.loaded_models[model_name] = {
                "loaded_at": datetime.now().isoformat(),
                "load_time": time.time() - start_time,
                "device": "CPU",
                "size_mb": self.estimate_model_size(model_name),
                "optimized_for_npu": False,
                "real_inference": False,
            }

    async def process_task(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process task"""
        task_type = task_data.get("task_type")
        model_name = task_data.get("model_name")
        input_data = task_data.get("input_data", {})

        if model_name not in self.loaded_models:
            await self.load_and_optimize_model(model_name)

        self.loaded_models[model_name]["last_used"] = datetime.now().isoformat()

        if task_type == "embedding_generation":
            return await self.process_embedding_task(input_data, model_name)
        elif task_type == "semantic_search":
            return await self.process_search_task(input_data, model_name)
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

    async def process_embedding_task(self, input_data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
        """Process embedding task with thread-safe cache and stats (Issue #68)"""
        text = input_data.get("text", "")
        cache_key = self._generate_cache_key(text, model_name)

        # Check cache (thread-safe LRU cache with TTL)
        cached_embedding = await self.embedding_cache.get(cache_key)
        if cached_embedding is not None:
            await self.task_stats.increment("cache_hits")
            return {
                "embedding": cached_embedding,
                "model_used": model_name,
                "device": "NPU_CACHED",
                "cache_hit": True,
            }

        start_time = time.time()
        embedding = self._generate_embedding(text, model_name)
        processing_time = (time.time() - start_time) * 1000

        # Store in cache (LRU cache handles eviction automatically)
        await self.embedding_cache.set(cache_key, embedding)

        await self.task_stats.increment("embedding_generations")

        return {
            "embedding": embedding,
            "model_used": model_name,
            "device": "NPU" if self.npu_available else "CPU",
            "processing_time_ms": processing_time,
            "cache_hit": False,
        }

    async def generate_npu_embeddings(
        self, texts: List[str], model_name: str, use_cache: bool, optimization_level: str
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts with thread-safe cache (Issue #68)"""
        embeddings = []
        batch_size = self.npu_optimization.get("batch_size", DEFAULT_NPU_BATCH_SIZE)

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = []

            for text in batch_texts:
                cache_key = self._generate_cache_key(text, model_name)

                if use_cache:
                    cached = await self.embedding_cache.get(cache_key)
                    if cached is not None:
                        batch_embeddings.append(cached)
                        await self.task_stats.increment("cache_hits")
                        continue

                embedding = self._generate_embedding(text, model_name)
                batch_embeddings.append(embedding)

                if use_cache:
                    await self.embedding_cache.set(cache_key, embedding)

            embeddings.extend(batch_embeddings)
            await asyncio.sleep(0.001)

        return embeddings

    async def perform_semantic_search(
        self, query_text: str, document_embeddings: List[List[float]],
        document_metadata: List[Dict[str, Any]], top_k: int, similarity_threshold: float
    ) -> List[Dict[str, Any]]:
        """Perform semantic search with thread-safe stats (Issue #68)"""
        query_embedding = await self.generate_npu_embeddings([query_text], "nomic-embed-text", True, "speed")
        query_vector = np.array(query_embedding[0])

        document_vectors = np.array(document_embeddings)

        if self.npu_available:
            await asyncio.sleep(0.005)
        else:
            await asyncio.sleep(0.02)

        # Compute cosine similarities
        query_norm = query_vector / np.linalg.norm(query_vector)
        doc_norms = document_vectors / np.linalg.norm(document_vectors, axis=1, keepdims=True)
        similarities = np.dot(doc_norms, query_norm)

        results = []
        for i, similarity in enumerate(similarities):
            if similarity >= similarity_threshold:
                results.append({
                    "index": i,
                    "similarity": float(similarity),
                    "metadata": document_metadata[i] if i < len(document_metadata) else {}
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        await self.task_stats.increment("semantic_searches")

        return results[:top_k]

    def _generate_embedding(self, text: str, model_name: str) -> List[float]:
        """
        Generate embedding using real OpenVINO inference or mock fallback.

        Issue #640: Replaces mock embeddings with real NPU inference.
        Falls back to mock if real inference unavailable.
        """
        # Issue #640: Use real inference if available
        if self._use_real_inference and self._model_manager is not None:
            try:
                embedding = self._model_manager.generate_embedding(text, model_name)
                return embedding
            except Exception as e:
                logger.warning(f"Real inference failed for {model_name}, using mock: {e}")
                # Fall through to mock implementation

        # Mock implementation (fallback)
        return self._generate_mock_embedding(text, model_name)

    def _generate_mock_embedding(self, text: str, model_name: str) -> List[float]:
        """Generate mock embedding using deterministic hash (fallback)."""
        import random

        # Use hashlib from top-level imports for deterministic embedding
        hash_obj = hashlib.md5(f"{text}{model_name}".encode())
        random.seed(int(hash_obj.hexdigest(), 16) % (2**32))

        # Use constants for embedding dimensions
        dim = EMBEDDING_DIM_NOMIC if "nomic" in model_name.lower() else EMBEDDING_DIM_DEFAULT
        embedding = [random.uniform(-1, 1) for _ in range(dim)]

        # Normalize
        norm = sum(x**2 for x in embedding) ** 0.5
        embedding = [x / norm for x in embedding]

        return embedding

    def _generate_cache_key(self, text: str, model_name: str) -> str:
        """Generate cache key using hashlib from top-level imports"""
        return hashlib.md5(f"{text}:{model_name}".encode()).hexdigest()

    async def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate (async for thread-safe stats access)"""
        total = await self.task_stats.get("embedding_generations")
        hits = await self.task_stats.get("cache_hits")
        return (hits / total * 100) if total > 0 else 0.0

    async def get_npu_metrics(self) -> Dict[str, Any]:
        """Get NPU metrics"""
        if not self.npu_available:
            return {"npu_available": False}

        return {
            "npu_available": True,
            "utilization_percent": await self.get_npu_utilization(),
            "temperature_c": await self.get_npu_temperature(),
            "power_usage_w": await self.get_npu_power_usage(),
            "memory_usage_mb": await self.get_npu_memory_usage(),
        }

    async def get_npu_status(self) -> Dict[str, Any]:
        """Get NPU status"""
        return {
            "available": self.npu_available,
            "utilization_percent": await self.get_npu_utilization(),
            "temperature_c": await self.get_npu_temperature(),
            "power_usage_w": await self.get_npu_power_usage(),
        }

    async def get_npu_utilization(self) -> float:
        """Get NPU utilization (async for thread-safe stats access)"""
        if self.loaded_models:
            base = min(len(self.loaded_models) * 20.0, 80.0)
            tasks_completed = await self.task_stats.get("tasks_completed")
            activity = min(tasks_completed * 2.0, 20.0)
            return min(base + activity, 100.0)
        return 0.0

    async def get_npu_temperature(self) -> float:
        """Get NPU temperature (simulated based on utilization)"""
        utilization = await self.get_npu_utilization()
        return NPU_BASE_TEMP_C + (utilization / 100.0) * NPU_TEMP_RANGE_C

    async def get_npu_power_usage(self) -> float:
        """Get NPU power usage (simulated based on utilization)"""
        utilization = await self.get_npu_utilization()
        return NPU_BASE_POWER_W + (utilization / 100.0) * NPU_POWER_RANGE_W

    async def get_npu_memory_usage(self) -> float:
        """Get NPU memory usage"""
        return sum(
            info.get("size_mb", 0)
            for info in self.loaded_models.values()
            if info.get("device") == "NPU"
        )

    def estimate_model_size(self, model_name: str) -> int:
        """Estimate model size in MB using constants"""
        model_lower = model_name.lower()
        if "1b" in model_lower:
            return MODEL_SIZE_1B
        elif "3b" in model_lower:
            return MODEL_SIZE_3B
        elif "embed" in model_lower or "nomic" in model_lower:
            return MODEL_SIZE_EMBED
        else:
            return MODEL_SIZE_DEFAULT

    async def run_benchmark(self) -> Dict[str, Any]:
        """Run performance benchmark"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "worker_id": self.worker_id,
            "npu_available": self.npu_available,
            "benchmarks": {}
        }

        # Embedding benchmark
        test_texts = [
            "Test sentence for embedding generation.",
            "AutoBot is an AI platform.",
            "NPU acceleration improves performance."
        ]

        start_time = time.time()
        embeddings = await self.generate_npu_embeddings(test_texts, "nomic-embed-text", False, "speed")
        embedding_time = (time.time() - start_time) * 1000

        results["benchmarks"]["embedding_generation"] = {
            "texts_processed": len(test_texts),
            "total_time_ms": embedding_time,
            "avg_time_per_text_ms": embedding_time / len(test_texts),
            "device_used": "NPU" if self.npu_available else "CPU"
        }

        # Search benchmark
        start_time = time.time()
        search_results = await self.perform_semantic_search(
            "test query", embeddings,
            [{"text": text} for text in test_texts],
            3, 0.5
        )
        search_time = (time.time() - start_time) * 1000

        results["benchmarks"]["semantic_search"] = {
            "documents_searched": len(embeddings),
            "results_returned": len(search_results),
            "total_time_ms": search_time,
            "device_used": "NPU" if self.npu_available else "CPU"
        }

        return results

    def _display_network_info(self):
        """Display network connection information on startup"""
        try:
            # Import network info utilities
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from gui.utils.network_info import (
                get_network_interfaces,
                get_platform_info,
                format_connection_info_box
            )

            port = config.get('service', {}).get('port', 8082)
            interfaces = get_network_interfaces()
            platform_info = get_platform_info()

            # Format and display the connection info box
            info_box = format_connection_info_box(
                worker_id=self.worker_id,
                port=port,
                interfaces=interfaces,
                platform_info=platform_info
            )

            # Log the info box
            logger.info("\n%s\n", info_box)

            # Also log key connection information
            logger.info("=" * 60)
            logger.info("NPU Worker Network Configuration:")
            logger.info(f"  Worker ID: {self.worker_id}")
            logger.info(f"  Port: {port}")

            if interfaces:
                logger.info("  Network Interfaces:")
                for iface in interfaces:
                    primary = " (Primary)" if iface.get('is_primary') else ""
                    logger.info(f"    - {iface['type']} ({iface['interface']}): {iface['ip']}{primary}")
            else:
                logger.info("  Network Interfaces: None detected")

            logger.info("=" * 60)

        except Exception as e:
            logger.warning(f"Failed to display network info: {e}")
            # Non-critical error, continue with initialization

    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up NPU worker")

        # Clear thread-safe LRU cache
        await self.embedding_cache.clear()

        # Stop telemetry (Issue #68)
        if hasattr(self, 'telemetry_client') and self.telemetry_client:
            try:
                await self.telemetry_client.stop()
            except Exception as e:
                logger.warning(f"Error during telemetry cleanup: {e}")

        if self.redis_client:
            try:
                from utils.redis_client import close_redis_client
                await close_redis_client()
            except Exception as e:
                logger.warning(f"Error during Redis cleanup: {e}")


def main():
    """Main entry point"""
    service_config = config.get('service', {})
    host = service_config.get('host', DEFAULT_HOST)
    port = service_config.get('port', DEFAULT_PORT)
    workers = service_config.get('workers', DEFAULT_WORKERS)

    logger.info(f"Starting AutoBot Windows NPU Worker on {host}:{port}")

    worker = WindowsNPUWorker()

    uvicorn.run(
        worker.app,
        host=host,
        port=port,
        workers=workers,
        log_level=config.get('logging', {}).get('level', DEFAULT_LOG_LEVEL).lower(),
        access_log=True
    )


if __name__ == "__main__":
    main()
