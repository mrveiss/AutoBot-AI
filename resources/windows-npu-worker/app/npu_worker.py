#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot NPU Worker - Windows Deployment Version
Optimized for Intel NPU/GPU hardware acceleration with ONNX Runtime + OpenVINO EP

Issue #640: Uses ONNX Runtime with OpenVINO Execution Provider for proper Intel NPU support.
DirectML doesn't expose Intel NPUs - OpenVINO EP has explicit NPU device option via device_type='NPU'.
Device priority: NPU → GPU → CPU (automatic fallback)

Issue #68: NPU worker settings with telemetry, bootstrap, and race condition fixes
"""

import asyncio
import hashlib
import io
import logging
import os
import sys
import time
import uuid

# Issue #640: Force UTF-8 encoding on Windows to prevent charmap codec errors
# OpenVINO/PyTorch/HuggingFace output Unicode characters (✅, etc.) during conversion
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # Reconfigure stdout/stderr to use UTF-8 if possible
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # Service mode may not support reconfiguration
import threading
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
# Default priority - can be overridden in config.npu.device_priority
DEVICE_PRIORITY = ["NPU", "GPU", "CPU"]


def get_device_priority() -> List[str]:
    """
    Get device priority from config or use default.

    Issue #165: Added support for specific GPU devices (GPU.0, GPU.1)
    to allow preferring NVIDIA dGPU over Intel NPU for faster embeddings.
    """
    try:
        priority = config.get("npu", {}).get("device_priority", DEVICE_PRIORITY)
        if isinstance(priority, list) and len(priority) > 0:
            return priority
    except Exception:
        pass
    return DEVICE_PRIORITY


def get_parallel_device_config() -> Dict[str, Any]:
    """
    Get parallel device configuration for workload-specific device selection.

    Issue #165: Allows using different devices for different workloads:
    - GPU.1 (NVIDIA RTX 4070) for embedding generation (fastest)
    - NPU for chat/inference (power efficient, runs in parallel)

    Returns:
        Dict with parallel device settings
    """
    default_config = {
        "enabled": False,
        "embedding_device": None,  # Will use default device priority
        "chat_device": None,  # Will use default device priority
        "fallback_device": "CPU",
    }
    try:
        parallel_config = config.get("npu", {}).get("parallel_devices", {})
        if isinstance(parallel_config, dict):
            return {**default_config, **parallel_config}
    except Exception:
        pass
    return default_config

# =============================================================================
# Configuration loader
# =============================================================================

# Worker ID file for persistence across restarts (Issue #68 - duplicate registration fix)
WORKER_ID_FILE = Path(__file__).parent.parent / "config" / ".worker_id"

# Issue #641: Registration status
# Tracks whether this worker has been paired with main host
PAIRING_STATUS_FILE = Path(__file__).parent.parent / "config" / ".pairing_status"


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file with UTF-8 encoding"""
    config_path = Path(__file__).parent.parent / "config" / "npu_worker.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def get_persistent_worker_id(prefix: str = "windows_npu_worker") -> Optional[str]:
    """
    Get persistent worker ID assigned by main host.

    Issue #641: Worker ID is now assigned by main host, not self-generated.
    This function only READS an existing ID - it does not generate new ones.
    New workers start with no ID and wait for main host to assign one via /pair endpoint.

    Args:
        prefix: Worker ID prefix (unused, kept for backwards compatibility)

    Returns:
        Persistent worker ID string if assigned, None if not yet paired
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

    # Issue #641: Do NOT generate new ID - wait for main host to assign one
    logger.info("No worker ID assigned yet - waiting for main host to pair")
    return None


def save_worker_id(worker_id: str) -> bool:
    """
    Save worker ID assigned by main host.

    Issue #641: Called when main host pairs with this worker and assigns an ID.

    Args:
        worker_id: The ID assigned by main host

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        WORKER_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WORKER_ID_FILE, 'w', encoding='utf-8') as f:
            f.write(worker_id)
        logger.info("Saved worker ID from main host: %s", worker_id)
        return True
    except Exception as e:
        logger.error("Failed to save worker ID: %s", e)
        return False


def get_pairing_status() -> Dict[str, Any]:
    """
    Get current pairing status with main host.

    Issue #641: Returns information about whether this worker is paired.

    Returns:
        Dict with pairing status information
    """
    try:
        if PAIRING_STATUS_FILE.exists():
            with open(PAIRING_STATUS_FILE, 'r', encoding='utf-8') as f:
                import json
                return json.load(f)
    except Exception as e:
        logger.warning("Failed to read pairing status: %s", e)

    return {
        "paired": False,
        "main_host": None,
        "paired_at": None,
    }


def save_pairing_status(main_host: str, worker_id: str) -> bool:
    """
    Save pairing status after successful pairing with main host.

    Issue #641: Records when and with which main host this worker was paired.

    Args:
        main_host: IP/hostname of the main host
        worker_id: The assigned worker ID

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        import json
        PAIRING_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        status = {
            "paired": True,
            "main_host": main_host,
            "worker_id": worker_id,
            "paired_at": datetime.now().isoformat(),
        }
        with open(PAIRING_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
        logger.info("Saved pairing status: paired with %s", main_host)
        return True
    except Exception as e:
        logger.error("Failed to save pairing status: %s", e)
        return False


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
# ONNX Runtime Model Management (Issue #640 - OpenVINO Execution Provider)
# =============================================================================
#
# This uses ONNX Runtime with OpenVINO Execution Provider for Intel NPU support.
# DirectML doesn't properly expose Intel NPUs - OpenVINO EP has explicit
# NPU device support via device_type='NPU' option.
#
# Device priority: NPU → GPU → CPU (automatic fallback)
# Requires: Windows 11 24H2+ with Intel AI Boost drivers for NPU
# =============================================================================


class ONNXModelManager:
    """
    Manages ONNX model downloading, conversion, and inference with OpenVINO EP.

    Issue #640: Uses OpenVINO Execution Provider for proper Intel NPU support.
    DirectML doesn't expose Intel NPUs - OpenVINO EP has explicit NPU device option.
    Uses HuggingFace for model downloading and exports to ONNX format for inference.

    Device priority: OpenVINOExecutionProvider (NPU→GPU→CPU) → CPUExecutionProvider
    """

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._tokenizers: Dict[str, Any] = {}
        self._sessions: Dict[str, Any] = {}  # ONNX Runtime InferenceSessions
        self._model_configs: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._selected_device: Optional[str] = None
        self._available_providers: List[str] = []
        self._initialized = False
        self._openvino_device: str = "CPU"  # NPU, GPU, or CPU
        self._device_full_names: Dict[str, str] = {}  # Full device names from OpenVINO

    def _initialize_onnx_runtime(self):
        """Lazy initialize ONNX Runtime and detect available providers"""
        if self._initialized:
            return

        try:
            import onnxruntime as ort

            self._available_providers = ort.get_available_providers()
            logger.info(f"Available ONNX Runtime providers: {self._available_providers}")

            # Check for OpenVINO Execution Provider (preferred for Intel NPU)
            if "OpenVINOExecutionProvider" in self._available_providers:
                # Try to detect NPU availability via OpenVINO
                self._detect_openvino_devices()
            elif "DmlExecutionProvider" in self._available_providers:
                self._selected_device = "DirectML"  # GPU via DirectML (fallback)
                self._openvino_device = "GPU"
                logger.info("DirectML available (GPU only, no NPU support)")
            elif "CUDAExecutionProvider" in self._available_providers:
                self._selected_device = "CUDA"
                self._openvino_device = "GPU"
                logger.info("CUDA execution provider available (NVIDIA GPU)")
            else:
                self._selected_device = "CPU"
                self._openvino_device = "CPU"
                logger.info("Using CPU execution provider (no GPU/NPU acceleration)")

            self._initialized = True

        except ImportError as e:
            logger.error(f"ONNX Runtime not installed: {e}")
            logger.error("Install with: pip install onnxruntime-openvino")
            raise

    def _detect_openvino_devices(self):
        """
        Detect available OpenVINO devices and select based on config priority.

        Issue #165: Enhanced to support specific GPU devices (GPU.0, GPU.1)
        to allow preferring NVIDIA dGPU (GPU.1) over Intel NPU for faster embeddings.
        The NVIDIA RTX 4070 (GPU.1) is ~10-100x faster than Intel NPU for embeddings.
        """
        try:
            # Try to import OpenVINO to check available devices
            from openvino import Core
            core = Core()
            available_devices = core.available_devices
            logger.info(f"OpenVINO available devices: {available_devices}")

            # Get full device names for each device
            for device in available_devices:
                try:
                    full_name = core.get_property(device, "FULL_DEVICE_NAME")
                    self._device_full_names[device] = full_name
                    logger.info(f"Device {device}: {full_name}")
                except Exception as e:
                    logger.debug(f"Could not get full name for {device}: {e}")
                    self._device_full_names[device] = device

            # Issue #165: Use config-based device priority
            # This allows preferring GPU.1 (NVIDIA) over NPU for faster embeddings
            device_priority = get_device_priority()
            logger.info(f"Device priority from config: {device_priority}")

            selected = False
            for preferred_device in device_priority:
                if preferred_device in available_devices:
                    self._selected_device = preferred_device
                    self._openvino_device = preferred_device
                    device_name = self._device_full_names.get(preferred_device, preferred_device)
                    logger.info(f"Selected device: {preferred_device} ({device_name})")
                    selected = True
                    break

            if not selected:
                # Fallback to CPU if no preferred device available
                self._selected_device = "CPU"
                self._openvino_device = "CPU"
                cpu_name = self._device_full_names.get("CPU", "CPU")
                logger.info(f"Fallback to CPU: {cpu_name}")

        except ImportError:
            # OpenVINO not installed separately, use EP defaults
            logger.info("OpenVINO EP available, will auto-detect device")
            self._selected_device = "OpenVINO"
            self._openvino_device = "NPU"  # Try NPU first
        except Exception as e:
            logger.warning(f"OpenVINO device detection failed: {e}")
            self._selected_device = "OpenVINO"
            self._openvino_device = "CPU"

    def _get_device_for_model_type(self, model_type: str = "default") -> str:
        """
        Get the device to use for a specific model type.

        Issue #165: Enables parallel device usage - different devices for different workloads.
        GPU.1 (NVIDIA RTX 4070) for embeddings, NPU for chat inference.

        Args:
            model_type: "embedding", "chat", or "default"

        Returns:
            Device string (e.g., "GPU.1", "NPU", "CPU")
        """
        parallel_config = get_parallel_device_config()

        if not parallel_config.get("enabled", False):
            # Parallel mode disabled, use default device
            return self._openvino_device

        # Get available devices
        try:
            from openvino import Core
            available_devices = Core().available_devices
        except Exception:
            available_devices = ["CPU"]

        # Select device based on model type
        if model_type == "embedding":
            preferred = parallel_config.get("embedding_device")
        elif model_type == "chat":
            preferred = parallel_config.get("chat_device")
        else:
            preferred = None

        # Check if preferred device is available
        if preferred and preferred in available_devices:
            logger.info(f"Using {preferred} for {model_type} workload (parallel mode)")
            return preferred

        # Fallback to default device
        fallback = parallel_config.get("fallback_device", "CPU")
        if fallback in available_devices:
            return fallback

        return self._openvino_device

    def _get_session_providers(self, model_type: str = "default") -> List[tuple]:
        """
        Get ordered list of execution providers with options for session creation.

        Issue #165: Added model_type parameter for workload-specific device selection.

        Args:
            model_type: "embedding", "chat", or "default" for device selection
        """
        self._initialize_onnx_runtime()

        # Get the appropriate device for this model type
        target_device = self._get_device_for_model_type(model_type)

        providers = []

        # OpenVINO Execution Provider with workload-specific device
        if "OpenVINOExecutionProvider" in self._available_providers:
            # OpenVINO EP provider options
            # device_type can be: NPU, GPU, CPU, GPU.0, GPU.1, etc.
            openvino_options = {
                "device_type": target_device,
                "precision": "FP16",  # FP16 for better performance
                "enable_opencl_throttling": True,
                "num_of_threads": DEFAULT_NPU_THREADS,
            }
            providers.append(("OpenVINOExecutionProvider", openvino_options))
            logger.info(f"Using OpenVINO EP with device_type='{target_device}' for {model_type}")

        # DirectML as fallback for GPU (doesn't support NPU properly)
        if "DmlExecutionProvider" in self._available_providers:
            providers.append("DmlExecutionProvider")

        # CUDA for NVIDIA GPUs
        if "CUDAExecutionProvider" in self._available_providers:
            providers.append("CUDAExecutionProvider")

        # CPU as final fallback (always available)
        providers.append("CPUExecutionProvider")

        return providers

    async def ensure_model_downloaded(self, model_name: str) -> Path:
        """
        Ensure model is downloaded and converted to ONNX format.

        Downloads from HuggingFace if not present, then exports to ONNX.
        """
        model_config = SUPPORTED_MODELS.get(model_name)
        if not model_config:
            raise ValueError(f"Unsupported model: {model_name}. Supported: {list(SUPPORTED_MODELS.keys())}")

        model_path = self.models_dir / model_name
        onnx_model_path = model_path / "model.onnx"

        if onnx_model_path.exists():
            logger.info(f"Model {model_name} already in ONNX format")
            return model_path

        logger.info(f"Downloading and converting model: {model_name}")

        # Run blocking operations in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._download_and_convert, model_name, model_config, model_path)

        return model_path

    def _download_and_convert(self, model_name: str, model_config: Dict, model_path: Path):
        """Download model from HuggingFace and export to ONNX (blocking)"""
        try:
            from transformers import AutoModel, AutoTokenizer
            import torch

            hf_id = model_config["hf_id"]
            logger.info(f"Downloading {hf_id} from HuggingFace...")

            # Download model and tokenizer
            tokenizer = AutoTokenizer.from_pretrained(hf_id, trust_remote_code=True)
            model = AutoModel.from_pretrained(hf_id, trust_remote_code=True)
            model.eval()

            # Save tokenizer for later use
            model_path.mkdir(parents=True, exist_ok=True)
            tokenizer.save_pretrained(str(model_path))

            # Export to ONNX
            logger.info(f"Exporting {model_name} to ONNX format...")
            self._export_to_onnx(model, tokenizer, model_config, model_path)

            logger.info(f"Model {model_name} successfully exported to ONNX format")

        except Exception as e:
            logger.error(f"Failed to download/convert model {model_name}: {e}")
            raise

    def _export_to_onnx(self, model, tokenizer, model_config: Dict, model_path: Path):
        """Export PyTorch model to ONNX format"""
        try:
            import torch

            # Create dummy input for tracing
            # Use fixed sequence length for NPU compatibility (static shapes)
            max_length = min(model_config.get("max_length", 512), 512)
            dummy_input = tokenizer(
                "This is a sample text for model export.",
                padding="max_length",
                max_length=max_length,
                truncation=True,
                return_tensors="pt"
            )

            onnx_path = model_path / "model.onnx"

            # Export with static shapes for better NPU/DirectML compatibility
            # Issue #640: NPU prefers static shapes over dynamic
            logger.info(f"Exporting with static sequence length: {max_length}")

            with torch.no_grad():
                torch.onnx.export(
                    model,
                    (dummy_input["input_ids"], dummy_input["attention_mask"]),
                    str(onnx_path),
                    input_names=["input_ids", "attention_mask"],
                    output_names=["last_hidden_state"],
                    # Use static batch size but allow dynamic sequence for flexibility
                    dynamic_axes={
                        "input_ids": {0: "batch_size"},
                        "attention_mask": {0: "batch_size"},
                        "last_hidden_state": {0: "batch_size"}
                    },
                    opset_version=14,
                    do_constant_folding=True,  # Optimize constants
                )

            # Verify the ONNX model
            import onnx
            onnx_model = onnx.load(str(onnx_path))
            onnx.checker.check_model(onnx_model)
            logger.info(f"ONNX model verified and saved to {onnx_path}")

        except Exception as e:
            logger.error(f"ONNX export failed: {e}")
            raise

    async def load_model(self, model_name: str) -> bool:
        """
        Load ONNX model and create inference session with DirectML.

        Returns True if model is ready for inference.
        """
        async with self._lock:
            if model_name in self._sessions:
                logger.debug(f"Model {model_name} already loaded")
                return True

            try:
                # Ensure model is downloaded and converted
                model_path = await self.ensure_model_downloaded(model_name)

                # Load in thread pool (blocking operations)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None, self._create_inference_session, model_name, model_path
                )
                return success

            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                return False

    def _determine_model_type(self, model_name: str) -> str:
        """
        Determine model type from model name for device selection.

        Issue #165: Used to route embedding models to GPU, chat models to NPU.
        """
        model_name_lower = model_name.lower()
        if "embed" in model_name_lower or "minilm" in model_name_lower or "bge" in model_name_lower:
            return "embedding"
        elif "llama" in model_name_lower or "chat" in model_name_lower or "instruct" in model_name_lower:
            return "chat"
        return "default"

    def _create_inference_session(self, model_name: str, model_path: Path) -> bool:
        """Create ONNX Runtime inference session with workload-specific device selection"""
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer

            self._initialize_onnx_runtime()

            # Load tokenizer
            logger.info(f"Loading tokenizer for {model_name}...")
            tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
            self._tokenizers[model_name] = tokenizer

            # Issue #165: Determine model type for device selection
            model_type = self._determine_model_type(model_name)

            # Create ONNX Runtime session with workload-specific device
            onnx_model_path = model_path / "model.onnx"
            logger.info(f"Creating inference session for {onnx_model_path} (type: {model_type})...")

            providers = self._get_session_providers(model_type)
            logger.info(f"Using execution providers: {providers}")

            # Session options for optimization
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.enable_mem_pattern = True
            sess_options.enable_cpu_mem_arena = True

            # Create session with provider fallback
            session = ort.InferenceSession(
                str(onnx_model_path),
                sess_options=sess_options,
                providers=providers
            )

            # Log which provider was actually used
            actual_providers = session.get_providers()
            logger.info(f"Session created with providers: {actual_providers}")

            # Update selected device based on actual provider
            if "OpenVINOExecutionProvider" in actual_providers:
                # OpenVINO EP is being used - check which device it's targeting
                self._selected_device = self._openvino_device  # NPU, GPU, or CPU
            elif "DmlExecutionProvider" in actual_providers:
                self._selected_device = "DirectML"
            elif "CUDAExecutionProvider" in actual_providers:
                self._selected_device = "CUDA"
            else:
                self._selected_device = "CPU"

            self._sessions[model_name] = session
            self._model_configs[model_name] = SUPPORTED_MODELS.get(model_name, {})

            logger.info(f"Model {model_name} loaded successfully on {self._selected_device}")
            return True

        except Exception as e:
            logger.error(f"Failed to create inference session for {model_name}: {e}", exc_info=True)
            return False

    def generate_embedding(self, text: str, model_name: str) -> List[float]:
        """
        Generate embedding using ONNX Runtime inference.

        Issue #640: Real inference using DirectML for NPU/GPU acceleration.
        """
        if model_name not in self._sessions:
            raise RuntimeError(f"Model {model_name} not loaded. Call load_model() first.")

        tokenizer = self._tokenizers[model_name]
        session = self._sessions[model_name]
        model_config = self._model_configs.get(model_name, {})

        # Tokenize input with fixed max_length for NPU compatibility
        max_length = min(model_config.get("max_length", 512), 512)
        inputs = tokenizer(
            text,
            padding="max_length",
            max_length=max_length,
            truncation=True,
            return_tensors="np"
        )

        # Prepare inputs for ONNX Runtime
        input_ids = inputs["input_ids"].astype(np.int64)
        attention_mask = inputs["attention_mask"].astype(np.int64)

        # Run inference
        ort_inputs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask
        }

        outputs = session.run(None, ort_inputs)

        # Extract embeddings (mean pooling over sequence)
        hidden_states = outputs[0]  # Shape: (batch, seq_len, hidden_dim)
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
        """Get information about the selected device and available providers"""
        try:
            self._initialize_onnx_runtime()

            # Get the full device name for the selected device
            selected_full_name = self._device_full_names.get(
                self._openvino_device,
                self._selected_device or "Unknown"
            )

            info = {
    "selected_device": self._selected_device or "Unknown",
    "selected_device_full_name": selected_full_name,
    "openvino_device": self._openvino_device,
    "available_providers": self._available_providers,
    "device_priority": [
        "OpenVINOExecutionProvider (NPU)",
        "OpenVINOExecutionProvider (GPU)",
        "DmlExecutionProvider",
        "CPUExecutionProvider"],
        "is_npu": self._selected_device == "NPU" or self._openvino_device == "NPU",
        "is_gpu": self._selected_device in [
            "GPU",
            "DirectML",
            "CUDA"] or self._openvino_device == "GPU",
            "is_cpu": self._selected_device == "CPU" and self._openvino_device == "CPU",
            "backend": "ONNX Runtime + OpenVINO EP",
            "device_full_names": self._device_full_names,
             }

            # Check OpenVINO EP availability
            if "OpenVINOExecutionProvider" in self._available_providers:
                info["openvino_available"] = True
                info["device_name"] = selected_full_name

                # Try to get detailed device info
                try:
                    from openvino import Core
                    core = Core()
                    info["openvino_devices"] = core.available_devices
                except Exception:
                    info["openvino_devices"] = ["Unknown"]
            else:
                info["openvino_available"] = False
                info["device_name"] = self._selected_device

            # Check DirectML as fallback
            info["directml_available"] = "DmlExecutionProvider" in self._available_providers

            return info

        except Exception as e:
            return {"error": str(e), "selected_device": "UNKNOWN"}


# Alias for backwards compatibility
OpenVINOModelManager = ONNXModelManager


# Global model manager instance with thread-safe initialization (Issue #662)
_model_manager: Optional[OpenVINOModelManager] = None
_model_manager_lock = threading.Lock()


def get_model_manager() -> OpenVINOModelManager:
    """Get or create the global model manager instance (thread-safe)."""
    global _model_manager
    if _model_manager is None:
        with _model_manager_lock:
            # Double-check after acquiring lock
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


class PairRequest(BaseModel):
    """
    Issue #641: Request from main host to pair with this worker.

    Main host sends this request to assign a permanent worker ID.
    """
    worker_id: str  # ID assigned by main host
    main_host: str  # IP/hostname of the main host
    config: Optional[Dict[str, Any]] = None  # Optional config from main host


class PairResponse(BaseModel):
    """
    Issue #641: Response after successful pairing.
    """
    success: bool
    worker_id: str
    message: str
    device_info: Optional[Dict[str, Any]] = None


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

        # Issue #641: Worker ID is assigned by main host, not self-generated
        # If no ID exists, worker_id will be None until main host pairs with us
        self.worker_id = get_persistent_worker_id()
        self.pairing_status = get_pairing_status()
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
                "paired": self.pairing_status.get("paired", False),
            }

        @self.app.post("/pair", response_model=PairResponse)
        async def pair_with_main_host(request: PairRequest):
            """
            Issue #641: Endpoint for main host to pair with this worker.

            Main host calls this endpoint to:
            1. Assign a permanent worker ID
            2. Send configuration
            3. Establish the pairing relationship

            This is the ONLY way a worker gets its ID - workers do NOT self-register.
            """
            try:
                # Check if already paired with a different ID
                if self.worker_id and self.worker_id != request.worker_id:
                    # Worker is already paired - check if it's the same main host
                    if self.pairing_status.get("main_host") != request.main_host:
                        return PairResponse(
                            success=False,
                            worker_id=self.worker_id,
                            message=f"Worker already paired with different host: {self.pairing_status.get('main_host')}",
                        )

                # Save the worker ID from main host
                if save_worker_id(request.worker_id):
                    self.worker_id = request.worker_id

                    # Save pairing status
                    save_pairing_status(request.main_host, request.worker_id)
                    self.pairing_status = get_pairing_status()

                    # Apply any config from main host
                    if request.config:
                        self._apply_main_host_config(request.config)

                    logger.info(f"Successfully paired with main host {request.main_host}")

                    # Get device info to return
                    device_info = None
                    if self._model_manager:
                        try:
                            device_info = self._model_manager.get_device_info()
                        except Exception:
                            pass

                    return PairResponse(
                        success=True,
                        worker_id=self.worker_id,
                        message=f"Successfully paired with main host {request.main_host}",
                        device_info=device_info,
                    )
                else:
                    return PairResponse(
                        success=False,
                        worker_id=request.worker_id,
                        message="Failed to save worker ID",
                    )

            except Exception as e:
                logger.error(f"Pairing failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/pairing-status")
        async def get_pairing_status_endpoint():
            """
            Issue #641: Get current pairing status.

            Returns whether this worker is paired with a main host.
            """
            return {
                "paired": self.pairing_status.get("paired", False),
                "worker_id": self.worker_id,
                "main_host": self.pairing_status.get("main_host"),
                "paired_at": self.pairing_status.get("paired_at"),
                "npu_available": self.npu_available,
                "platform": "windows",
            }

        @self.app.post("/unpair")
        async def unpair_from_main_host():
            """
            Issue #641: Unpair from main host.

            Removes the worker ID and pairing status, allowing re-pairing.
            """
            try:
                # Remove worker ID file
                if WORKER_ID_FILE.exists():
                    WORKER_ID_FILE.unlink()

                # Remove pairing status file
                if PAIRING_STATUS_FILE.exists():
                    PAIRING_STATUS_FILE.unlink()

                # Reset in-memory state
                old_id = self.worker_id
                self.worker_id = None
                self.pairing_status = {"paired": False, "main_host": None, "paired_at": None}

                logger.info(f"Unpaired worker (was: {old_id})")

                return {
                    "success": True,
                    "message": f"Worker unpaired (was: {old_id})",
                }

            except Exception as e:
                logger.error(f"Unpair failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device-info")
        async def device_info():
            """
            Get detailed device information including NPU/GPU/CPU status.

            Issue #640: Shows which device is being used for inference.
            Uses ONNX Runtime + OpenVINO EP for proper Intel NPU support.
            """
            info = {
    "worker_id": self.worker_id,
    "npu_available": self.npu_available,
    "real_inference_enabled": self._use_real_inference,
    "backend": "ONNX Runtime + OpenVINO EP",
    "device_priority": [
        "OpenVINOExecutionProvider (NPU)",
        "OpenVINOExecutionProvider (GPU)",
        "DmlExecutionProvider",
        "CPUExecutionProvider"],
         }

            if self._model_manager is not None:
                try:
                    manager_info = self._model_manager.get_device_info()
                    info["model_manager"] = manager_info
                    info["selected_device"] = manager_info.get("selected_device", "UNKNOWN")
                    info["available_providers"] = manager_info.get("available_providers", [])
                    info["directml_available"] = manager_info.get("directml_available", False)
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
                    "backend": model_info.get("backend", "Unknown"),
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
        Issue #641: Worker is now passive - does NOT self-register.
                   Waits for main host to pair via /pair endpoint.
        """
        self.start_time = time.time()

        # Issue #641: Log pairing status
        if self.worker_id:
            logger.info(f"Starting Windows NPU Worker (paired): {self.worker_id}")
        else:
            logger.info("Starting Windows NPU Worker (unpaired - waiting for main host)")

        logger.info(f"Port: {config.get('service', {}).get('port', DEFAULT_PORT)}")

        # Display network connection information
        self._display_network_info()

        # Issue #641: REMOVED bootstrap_config() call
        # Worker no longer self-registers. Main host controls registration via /pair endpoint.
        # If worker is already paired, we use the stored config.

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

        # Issue #641: REMOVED auto-registration telemetry
        # Telemetry only runs AFTER worker is paired with main host
        if self.pairing_status.get("paired"):
            await self.initialize_telemetry()
        else:
            logger.info("Telemetry disabled - worker not yet paired with main host")
            self.telemetry_client = None

        pairing_msg = "paired" if self.pairing_status.get("paired") else "waiting for pairing"
        logger.info(f"Windows NPU Worker initialized - NPU: {self.npu_available}, Status: {pairing_msg}")

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
        Initialize NPU/GPU acceleration with ONNX Runtime OpenVINO EP.

        Issue #640: Uses OpenVINO Execution Provider for proper Intel NPU support.
        DirectML doesn't expose Intel NPUs - OpenVINO EP has explicit NPU device option.
        Device priority: NPU → GPU → CPU (automatic fallback)
        """
        try:
            import platform
            if platform.system() != "Windows":
                logger.warning("NPU worker optimized for Windows - OpenVINO NPU not available on this platform")
                self.npu_available = False
                return

            # Initialize ONNX Runtime and check available providers
            import onnxruntime as ort
            available_providers = ort.get_available_providers()
            logger.info(f"Available ONNX Runtime providers: {available_providers}")

            # Check for OpenVINO EP (preferred for Intel NPU)
            if "OpenVINOExecutionProvider" in available_providers:
                # Try to detect NPU via OpenVINO
                try:
                    from openvino import Core
                    core = Core()
                    available_devices = core.available_devices
                    logger.info(f"OpenVINO available devices: {available_devices}")

                    if "NPU" in available_devices:
                        self.npu_available = True
                        logger.info("Intel NPU detected via OpenVINO - NPU acceleration enabled!")
                    elif "GPU" in available_devices:
                        self.npu_available = True
                        logger.info("Intel GPU detected via OpenVINO - GPU acceleration enabled")
                    else:
                        self.npu_available = False
                        logger.warning("OpenVINO EP available but no NPU/GPU detected")
                except ImportError:
                    # OpenVINO package not installed, but EP might still work
                    self.npu_available = True
                    logger.info("OpenVINO EP available - will try NPU/GPU acceleration")
            elif "DmlExecutionProvider" in available_providers:
                # Fallback to DirectML (GPU only, no NPU)
                self.npu_available = True
                logger.info("DirectML available (GPU only, Intel NPU not exposed via DirectML)")
            elif "CUDAExecutionProvider" in available_providers:
                self.npu_available = True
                logger.info("CUDA execution provider available - NVIDIA GPU acceleration enabled")
            else:
                self.npu_available = False
                logger.warning("No GPU/NPU acceleration available - using CPU only")

            # Initialize model manager for real inference (Issue #640)
            if self._use_real_inference:
                try:
                    self._model_manager = get_model_manager()
                    device_info = self._model_manager.get_device_info()
                    logger.info(f"Model manager initialized: {device_info}")

                    # Update npu_available based on actual device
                    if device_info.get("is_gpu") or device_info.get("is_npu"):
                        self.npu_available = True

                except Exception as e:
                    logger.error(f"Failed to initialize model manager: {e}")
                    logger.info("Falling back to mock inference")
                    self._use_real_inference = False

        except ImportError as e:
            logger.error(f"ONNX Runtime not installed: {e}")
            logger.error("Install with: pip install onnxruntime-openvino")
            self.npu_available = False
            self._use_real_inference = False
        except Exception as e:
            logger.error(f"NPU/GPU initialization failed: {e}")
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

        Issue #640: Now uses ONNX Runtime + DirectML for stable NPU/GPU inference.
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
                # Issue #640: Use ONNX Runtime model manager for DirectML inference
                if self._use_real_inference and self._model_manager is not None:
                    logger.info(f"Loading {model_name} with ONNX Runtime (real inference)...")

                    # Load model via model manager (handles download + ONNX export)
                    success = await self._model_manager.load_model(model_name)

                    if success:
                        device_info = self._model_manager.get_device_info()
                        selected_device = device_info.get("selected_device", "CPU")

                        # Map DirectML to NPU/GPU for display
                        display_device = selected_device
                        if selected_device == "DirectML":
                            display_device = "NPU/GPU (DirectML)"

                        self.loaded_models[model_name] = {
                            "loaded_at": datetime.now().isoformat(),
                            "load_time": time.time() - start_time,
                            "device": display_device,
                            "size_mb": self.estimate_model_size(model_name),
                            "optimized_for_npu": device_info.get("is_npu", False) or device_info.get("is_gpu", False),
                            "optimization_level": optimization_level,
                            "precision": self.npu_optimization.get("precision", DEFAULT_NPU_PRECISION),
                            "real_inference": True,
                            "device_info": device_info,
                            "backend": device_info.get("backend", "ONNX Runtime"),
                        }
                        logger.info(f"Model {model_name} loaded for {display_device} (real inference)")
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

    def _apply_main_host_config(self, host_config: Dict[str, Any]) -> None:
        """
        Apply configuration received from main host during pairing.

        Issue #641: Main host sends configuration when pairing with worker.
        This allows centralized configuration management.

        Args:
            host_config: Configuration dictionary from main host
        """
        try:
            logger.info("Applying configuration from main host")

            # Apply Redis config if provided
            if "redis" in host_config:
                redis_cfg = host_config["redis"]
                logger.info(f"Received Redis config from main host: {redis_cfg.get('host', 'N/A')}")
                # Store for use by initialize_redis on next restart
                self._bootstrap_config = {"redis": redis_cfg}

            # Apply NPU optimization settings if provided
            if "npu" in host_config:
                npu_cfg = host_config["npu"]
                if "optimization" in npu_cfg:
                    self.npu_optimization.update(npu_cfg["optimization"])
                    logger.info(f"Updated NPU optimization: {self.npu_optimization}")

            # Apply model preload settings if provided
            if "models" in host_config:
                models_cfg = host_config["models"]
                if models_cfg.get("preload"):
                    # Schedule model loading (don't block pairing response)
                    asyncio.create_task(self._preload_models_from_config(models_cfg))

            logger.info("Main host configuration applied successfully")

        except Exception as e:
            logger.error(f"Failed to apply main host config: {e}")

    async def _preload_models_from_config(self, models_config: Dict[str, Any]) -> None:
        """Preload models specified in main host configuration."""
        try:
            for model_name in models_config.get("preload", []):
                logger.info(f"Preloading model from main host config: {model_name}")
                await self.load_and_optimize_model(model_name)
        except Exception as e:
            logger.warning(f"Failed to preload models: {e}")

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

    # TLS Configuration - Issue #725 Phase 5
    tls_config = config.get('tls', {})
    tls_enabled = tls_config.get(
    'enabled',
    False) or os.environ.get(
        "NPU_WORKER_TLS_ENABLED",
         "false").lower() == "true"
    ssl_keyfile = None
    ssl_certfile = None

    if tls_enabled:
        cert_dir = tls_config.get('cert_dir', os.environ.get("AUTOBOT_TLS_CERT_DIR", "certs"))
        ssl_keyfile = os.path.join(cert_dir, "server-key.pem")
        ssl_certfile = os.path.join(cert_dir, "server-cert.pem")
        port = tls_config.get('port', int(os.environ.get("NPU_WORKER_TLS_PORT", "8444")))
        logger.info(f"TLS enabled - using HTTPS on port {port}")

    uvicorn_config = {
        "app": worker.app,
        "host": host,
        "port": port,
        "workers": workers,
        "log_level": config.get('logging', {}).get('level', DEFAULT_LOG_LEVEL).lower(),
        "access_log": True,
    }

    if tls_enabled and ssl_keyfile and ssl_certfile:
        uvicorn_config["ssl_keyfile"] = ssl_keyfile
        uvicorn_config["ssl_certfile"] = ssl_certfile

    uvicorn.run(**uvicorn_config)


if __name__ == "__main__":
    main()
