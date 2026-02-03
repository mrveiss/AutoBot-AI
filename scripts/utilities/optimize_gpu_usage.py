#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Optimize GPU usage for AutoBot multi-agent system.
Configure RTX 4070 Laptop GPU for optimal performance.
"""

import json
import logging
import os
import subprocess
from pathlib import Path

import yaml

from src.constants import ServiceURLs

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_gpu_status():
    """Check current GPU status and configuration."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            logger.info("🎮 GPU Status: %s", gpu_info)

            parts = gpu_info.split(",")
            if len(parts) >= 5:
                name = parts[0].strip()
                total_mem = int(parts[1].strip())
                used_mem = int(parts[2].strip())
                utilization = int(parts[3].strip())
                temp = int(parts[4].strip())

                logger.info("   Name: %s", name)
                logger.info(
                    f"   Memory: {used_mem}/{total_mem} MB ({(used_mem/total_mem)*100:.1f}% used)"
                )
                logger.info("   Utilization: %s%", utilization)
                logger.info("   Temperature: %s°C", temp)

                return {
                    "name": name,
                    "total_memory_mb": total_mem,
                    "used_memory_mb": used_mem,
                    "utilization_percent": utilization,
                    "temperature_c": temp,
                    "available": True,
                }
        else:
            logger.error("❌ Could not query GPU status")
            return {"available": False}

    except Exception as e:
        logger.error("❌ Error checking GPU: %s", e)
        return {"available": False}


def optimize_ollama_gpu_config():
    """Configure Ollama for optimal GPU usage."""
    try:
        # Set GPU environment variables
        gpu_env_vars = {
            "OLLAMA_DEVICE": "gpu",
            "CUDA_VISIBLE_DEVICES": "0",
            "NVIDIA_VISIBLE_DEVICES": "0",
            "OLLAMA_GPU_LAYERS": "999",  # Use all layers on GPU
            "OLLAMA_PARALLEL": "2",  # Allow 2 parallel requests
            "OLLAMA_NUM_THREAD": "4",  # CPU threads for non-GPU work
        }

        logger.info("🔧 Configuring Ollama for GPU optimization:")
        for key, value in gpu_env_vars.items():
            os.environ[key] = value
            logger.info("   %s=%s", key, value)

        # Write environment config
        config_file = Path(__file__).parent / "gpu_env_config.sh"
        with open(config_file, "w") as f:
            f.write("#!/bin/bash\n")
            f.write("# GPU Environment Configuration for AutoBot\n\n")
            for key, value in gpu_env_vars.items():
                f.write(f'export {key}="{value}"\n')

        logger.info("✅ GPU configuration written to %s", config_file)

        return True

    except Exception as e:
        logger.error("❌ Error configuring GPU: %s", e)
        return False


def update_autobot_config():
    """Update AutoBot configuration for optimal GPU usage."""
    try:
        config_file = Path(__file__).parent / "src" / "config.yaml"

        # Load existing config or create new one
        if config_file.exists():
            with open(config_file, "r") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        # Update hardware acceleration configuration
        config.setdefault("hardware_acceleration", {})
        config["hardware_acceleration"].update(
            {
                "priority": ["cuda", "openvino", "cpu"],
                "gpu_optimization": {
                    "enabled": True,
                    "device_id": 0,
                    "memory_limit_mb": 6000,  # Leave 2GB for system
                    "parallel_requests": 2,
                    "fp16_optimization": True,
                },
                "agent_device_assignments": {
                    # Large models on GPU
                    "orchestrator": "gpu",
                    "rag": "gpu",
                    "research": "gpu",
                    "analysis": "gpu",
                    "planning": "gpu",
                    # Small models can use CPU or GPU
                    "chat": "gpu",  # Fast GPU inference
                    "system_commands": "cpu",  # Keep system commands on CPU
                    "knowledge_retrieval": "gpu",
                    "search": "gpu",
                    "code": "gpu",
                },
            }
        )

        # Update LLM configuration
        config.setdefault("llm_config", {})
        config["llm_config"].update(
            {
                "default_provider": "ollama",
                "ollama": {
                    "host": ServiceURLs.OLLAMA_LOCAL,
                    "gpu_enabled": True,
                    "gpu_layers": 999,
                    "context_length": 4096,
                    "parallel_requests": 2,
                },
            }
        )

        # Write updated config
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)

        logger.info("✅ AutoBot configuration updated in %s", config_file)

        return True

    except Exception as e:
        logger.error("❌ Error updating AutoBot config: %s", e)
        return False


def create_model_recommendations():
    """Create model recommendations based on GPU memory."""
    try:
        gpu_status = check_gpu_status()
        if not gpu_status.get("available"):
            return False

        total_memory = gpu_status.get("total_memory_mb", 8000)

        # Recommend models based on GPU memory
        if total_memory >= 8000:  # 8GB+ GPU
            recommended_models = {
                "orchestrator": "artifish/llama3.2-uncensored:latest",  # 2.2GB
                "rag": "artifish/llama3.2-uncensored:latest",  # 2.2GB
                "research": "artifish/llama3.2-uncensored:latest",  # 2.2GB
                "chat": "llama3.2:3b-instruct-q4_K_M",  # 2GB
                "analysis": "artifish/llama3.2-uncensored:latest",  # 2.2GB
                "planning": "artifish/llama3.2-uncensored:latest",  # 2.2GB
            }
            parallel_capacity = "2-3 concurrent models"
        elif total_memory >= 6000:  # 6GB GPU
            recommended_models = {
                "orchestrator": "llama3.2:3b-instruct-q4_K_M",  # 2GB
                "rag": "artifish/llama3.2-uncensored:latest",  # 2.2GB
                "research": "llama3.2:3b-instruct-q4_K_M",  # 2GB
                "chat": "llama3.2:1b-instruct-q4_K_M",  # 807MB
                "analysis": "llama3.2:3b-instruct-q4_K_M",  # 2GB
            }
            parallel_capacity = "2 concurrent models"
        else:  # 4GB GPU
            recommended_models = {
                "orchestrator": "llama3.2:1b-instruct-q4_K_M",  # 807MB
                "rag": "llama3.2:1b-instruct-q4_K_M",  # 807MB
                "research": "llama3.2:1b-instruct-q4_K_M",  # 807MB
                "chat": "llama3.2:1b-instruct-q4_K_M",  # 807MB
            }
            parallel_capacity = "1-2 concurrent models"

        logger.info("📋 Model Recommendations for %sMB GPU:", total_memory)
        logger.info("   Parallel Capacity: %s", parallel_capacity)
        for agent, model in recommended_models.items():
            logger.info(f"   {agent:20}: {model}")

        # Write recommendations to file
        recommendations_file = Path(__file__).parent / "gpu_model_recommendations.json"
        with open(recommendations_file, "w") as f:
            json.dump(
                {
                    "gpu_memory_mb": total_memory,
                    "parallel_capacity": parallel_capacity,
                    "recommended_models": recommended_models,
                    "optimization_tips": [
                        "Use quantized models (q4_K_M) for memory efficiency",
                        "Monitor GPU memory usage with nvidia-smi",
                        "Consider model swapping for peak memory usage",
                        "Use FP16 precision when possible",
                    ],
                },
                f,
                indent=2,
            )

        logger.info("✅ Model recommendations saved to %s", recommendations_file)

        return True

    except Exception as e:
        logger.error("❌ Error creating model recommendations: %s", e)
        return False


def test_gpu_inference():
    """Test GPU inference performance."""
    try:
        logger.info("🧪 Testing GPU inference...")

        # Simple CUDA availability test
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            memory_allocated = torch.cuda.memory_allocated(0) / 1024**3
            memory_cached = torch.cuda.memory_reserved(0) / 1024**3

            logger.info("✅ PyTorch CUDA available")
            logger.info("   Device: %s", device_name)
            logger.info("   Memory Allocated: %.2f GB", memory_allocated)
            logger.info("   Memory Cached: %.2f GB", memory_cached)

            return True
        else:
            logger.warning("⚠️ PyTorch CUDA not available")
            return False

    except ImportError:
        logger.info("ℹ️ PyTorch not installed - skipping CUDA test")
        return True
    except Exception as e:
        logger.error("❌ GPU inference test failed: %s", e)
        return False


def main():
    """Main GPU optimization function."""
    logger.info("🚀 AutoBot GPU Optimization Tool")
    logger.info("=" * 50)

    # Step 1: Check GPU status
    logger.info("1️⃣ Checking GPU status...")
    gpu_status = check_gpu_status()

    if not gpu_status.get("available"):
        logger.error("❌ GPU not available - optimization cannot continue")
        return False

    # Step 2: Configure Ollama
    logger.info("\n2️⃣ Configuring Ollama for GPU...")
    optimize_ollama_gpu_config()

    # Step 3: Update AutoBot config
    logger.info("\n3️⃣ Updating AutoBot configuration...")
    update_autobot_config()

    # Step 4: Create model recommendations
    logger.info("\n4️⃣ Creating model recommendations...")
    create_model_recommendations()

    # Step 5: Test GPU inference
    logger.info("\n5️⃣ Testing GPU inference...")
    test_gpu_inference()

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 GPU Optimization Summary:")
    logger.info("   GPU: %s", gpu_status.get('name', 'Unknown'))
    logger.info("   Memory: %s MB total", gpu_status.get('total_memory_mb', 0))
    logger.info("   Current Usage: %s%", gpu_status.get('utilization_percent', 0))
    logger.info("\n🎉 GPU optimization complete!")
    logger.info("   Source gpu_env_config.sh before starting AutoBot")
    logger.info("   Monitor GPU usage with: watch nvidia-smi")

    return True


if __name__ == "__main__":
    success = main()
    if success:
        print("\n🚀 To apply GPU optimization:")
        print("   1. source gpu_env_config.sh")
        print("   2. ./run_agent.sh")
        print("   3. Monitor with: watch nvidia-smi")
    exit(0 if success else 1)
