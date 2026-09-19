# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Process settings for the Windows NPU worker (#15642).

The constants, the YAML config the whole worker reads, the logging setup and
the device-priority helpers that answer "which accelerator does this workload
get" from that config. Imported first by every other module here, because
importing it is what configures logging.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # Reconfigure stdout/stderr to use UTF-8 if possible
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)


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

# Semantic search defaults. #15642: the /search/semantic route carried this as
# a bare `10` in its signature, which the hardcoded-value guard rejects and
# which no operator could tune. Named here with the other defaults.
DEFAULT_SEMANTIC_SEARCH_TOP_K = 10

# Model paths and HuggingFace identifiers
MODELS_DIR = Path(__file__).parent.parent / "models"
#
# revision/weight_digests (#17087): this worker cannot import
# autobot_shared.pinned_model_registry (see module docstring), so each
# entry carries its own pin -- same principle (a real, verified commit SHA
# and weight-file sha256, never guessed), obtained via the exact procedure
# in docs/developer/MODEL_REVISION_PINNING.md's "Bump procedure" section.
# trust_remote_code is per-model, not a blanket True: nomic-embed-text
# genuinely needs it (its config.json declares an auto_map to
# nomic-ai/nomic-bert-2048's custom modeling code -- pinning this repo's own
# revision does not also pin that referenced repo, which is a follow-up, not
# yet covered); the other two are vanilla BertModel with no auto_map, so
# trust_remote_code was previously enabled for them with nothing to trust.
SUPPORTED_MODELS = {
    "nomic-embed-text": {
        "hf_id": "nomic-ai/nomic-embed-text-v1",
        "dim": EMBEDDING_DIM_NOMIC,
        "max_length": 8192,
        "revision": "3ac47f125a41961d13b397d0332866be2f9152e1",  # pinned 2026-09-19 by mrveiss (#17087)
        "trust_remote_code": True,
        "weight_digests": {
            "model.safetensors": "47e396424a085a613034450cd4bf9e8acfb568b19089ae1c5c4e7051ae286877",
            "pytorch_model.bin": "9fc78c00133aac4e12f358cfe9546e893cb82bb9bb7956506fbbcaa1700ce17c",
        },
    },
    "all-MiniLM-L6-v2": {
        "hf_id": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
        "max_length": 512,
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",  # pinned 2026-09-19 by mrveiss (#17087)
        "trust_remote_code": False,
        "weight_digests": {
            "model.safetensors": "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db",
            "pytorch_model.bin": "c3a85f238711653950f6a79ece63eb0ea93d76f6a6284be04019c53733baf256",
        },
    },
    "bge-small-en-v1.5": {
        "hf_id": "BAAI/bge-small-en-v1.5",
        "dim": 384,
        "max_length": 512,
        "revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",  # pinned 2026-09-19 by mrveiss (#17087)
        "trust_remote_code": False,
        "weight_digests": {
            "model.safetensors": "3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad",
            "pytorch_model.bin": "84868a67d847f7f37d1df745b73a4c20b5bc0a797c87a23b265f8a0131728b88",
        },
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
        logger.debug("Suppressed exception in try block", exc_info=True)
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
        logger.debug("Suppressed exception in try block", exc_info=True)
    return default_config


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file with UTF-8 encoding"""
    config_path = Path(__file__).parent.parent / "config" / "npu_worker.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


# Load configuration
config = load_config()

# Configure logging
log_dir = Path(__file__).parent.parent / config.get("logging", {}).get("directory", "logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=config.get("logging", {}).get("level", DEFAULT_LOG_LEVEL),
    format=config.get("logging", {}).get("format", DEFAULT_LOG_FORMAT),
    handlers=[
        logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
