# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hardware Acceleration Manager for AutoBot Multi-Agent Architecture.

Manages hardware acceleration with priority: NPU > GPU > CPU
Optimizes model execution across different hardware targets.
"""

import logging
import os
import platform
import subprocess
from enum import Enum
from typing import Any, Dict

import psutil

from src.config import config_manager

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for NPU hardware keywords (Issue #326)
NPU_HARDWARE_KEYWORDS = {"neural", "npu", "ai"}


def _parse_nvidia_smi_output(output: str) -> Dict[str, Dict[str, Any]]:
    """Parse nvidia-smi GPU status output (Issue #315: extracted).

    Args:
        output: Raw nvidia-smi CSV output

    Returns:
        Dict mapping gpu_N to status dict
    """
    devices = {}
    lines = output.strip().split("\n")

    for i, line in enumerate(lines):
        # Cache stripped line to avoid repeated calls (Issue #624)
        line_stripped = line.strip()
        if not line_stripped:
            continue
        parts = line_stripped.split(",")
        if len(parts) < 3:
            continue

        try:
            # Cache stripped parts to avoid repeated strip() calls
            util = int(parts[0].strip())
            mem_used = int(parts[1].strip())
            mem_total = int(parts[2].strip())
            devices[f"gpu_{i}"] = {
                "utilization": util,
                "memory_used_mb": mem_used,
                "memory_total_mb": mem_total,
                "memory_percent": (mem_used / mem_total) * 100,
                "status": "optimal" if util < 80 else "high_load",
            }
        except (ValueError, ZeroDivisionError):
            continue

    return devices


class AccelerationType(Enum):
    """Hardware acceleration types in priority order."""

    NPU = "npu"
    GPU = "gpu"
    CPU = "cpu"


class HardwareAccelerationManager:
    """Manages hardware acceleration configuration and device selection."""

    def __init__(self):
        """Initialize hardware acceleration manager."""
        self.available_devices = {}
        self.device_priorities = [
            AccelerationType.NPU,
            AccelerationType.GPU,
            AccelerationType.CPU,
        ]
        self.current_config = {}
        self.npu_available = False
        self.gpu_available = False
        self.cpu_cores = psutil.cpu_count()

        # Initialize device detection
        self._detect_available_hardware()
        self._configure_device_priorities()

        logger.info("Hardware Acceleration Manager initialized")
        logger.info("Available devices: %s", list(self.available_devices.keys()))

    def _detect_available_hardware(self):
        """Detect available hardware acceleration options."""
        # Detect NPU
        self.npu_available = self._detect_npu()
        if self.npu_available:
            self.available_devices[AccelerationType.NPU] = self._get_npu_info()

        # Detect GPU
        self.gpu_available = self._detect_gpu()
        if self.gpu_available:
            self.available_devices[AccelerationType.GPU] = self._get_gpu_info()

        # CPU is always available
        self.available_devices[AccelerationType.CPU] = self._get_cpu_info()

        logger.info(
            f"Hardware detection complete - NPU: {self.npu_available}, "
            f"GPU: {self.gpu_available}, CPU: Available"
        )

    def _detect_npu(self) -> bool:
        """Detect Intel NPU availability."""
        try:
            return (
                self._check_npu_device_files()
                or self._check_npu_via_lspci()
                or self._check_npu_via_openvino()
            )
        except Exception as e:
            logger.error("NPU detection error: %s", e)
            return False

    def _check_npu_device_files(self) -> bool:
        """Check for NPU device files in /dev."""
        if not os.path.exists("/dev"):
            return False

        npu_devices = [
            device
            for device in os.listdir("/dev")
            if "intel_npu" in device or "npu" in device.lower()
        ]

        if npu_devices:
            logger.info("Intel NPU devices detected: %s", npu_devices)
            return True
        return False

    def _check_npu_via_lspci(self) -> bool:
        """Check for NPU hardware via lspci command."""
        try:
            result = subprocess.run(
                ["lspci"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                output = result.stdout.lower()
                if any(keyword in output for keyword in NPU_HARDWARE_KEYWORDS):
                    logger.info("NPU hardware detected via lspci")
                    return True
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("lspci NPU detection unavailable: %s", e)
        return False

    def _check_npu_via_openvino(self) -> bool:
        """Check for NPU support via OpenVINO."""
        try:
            from openvino.runtime import Core

            core = Core()
            npu_devices = [d for d in core.available_devices if "NPU" in d]
            if npu_devices:
                logger.info("NPU devices available via OpenVINO: %s", npu_devices)
                return True
        except ImportError:
            logger.debug("OpenVINO not available for NPU detection")
        except Exception as e:
            logger.debug("OpenVINO NPU detection failed: %s", e)
        return False

    def _detect_gpu(self) -> bool:
        """Detect GPU availability."""
        try:
            # Check for NVIDIA GPU
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    logger.info("NVIDIA GPU detected")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.debug("nvidia-smi not available: %s", e)

            # Check for AMD GPU
            try:
                result = subprocess.run(
                    ["rocm-smi", "--showproductname"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.info("AMD GPU detected")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.debug("rocm-smi not available: %s", e)

            # Check for Intel GPU
            try:
                result = subprocess.run(
                    ["intel_gpu_top", "-l"], capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    logger.info("Intel GPU detected")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.debug("intel_gpu_top not available: %s", e)

            # Generic lspci check
            try:
                result = subprocess.run(
                    ["lspci", "-nn"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    output = result.stdout.lower()
                    gpu_indicators = ["vga", "3d", "display", "nvidia", "amd", "intel"]
                    if any(indicator in output for indicator in gpu_indicators):
                        logger.info("GPU hardware detected via lspci")
                        return True
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.debug("lspci GPU detection unavailable: %s", e)

            return False

        except Exception as e:
            logger.error("GPU detection error: %s", e)
            return False

    def _get_npu_info(self) -> Dict[str, Any]:
        """Get NPU information."""
        info = {
            "type": "NPU",
            "available": True,
            "recommended_models": ["1b", "3b"],  # NPU optimized for smaller models
            "memory_efficient": True,
            "power_efficient": True,
        }

        try:
            from openvino.runtime import Core

            core = Core()
            npu_devices = [d for d in core.available_devices if "NPU" in d]
            info["devices"] = npu_devices
            info["openvino_support"] = True
        except ImportError:
            info["openvino_support"] = False
            info["devices"] = ["NPU (detected)"]
        except Exception as e:
            logger.debug("NPU info gathering error: %s", e)
            info["devices"] = ["NPU (detected)"]

        return info

    def _parse_nvidia_gpu_output(self, output: str) -> list[str]:
        """Parse nvidia-smi output into GPU list (Issue #315 - extracted helper)."""
        gpus = []
        for line in output.strip().split("\n"):
            # Cache stripped line to avoid repeated calls (Issue #624)
            line_stripped = line.strip()
            if not line_stripped:
                continue
            parts = line_stripped.split(",")
            if len(parts) >= 2:
                name = parts[0].strip()
                memory = parts[1].strip()
                gpus.append(f"{name} ({memory}MB)")
        return gpus

    def _get_gpu_info(self) -> Dict[str, Any]:
        """Get GPU information (Issue #315 - refactored depth 5 to 3)."""
        info = {
            "type": "GPU",
            "available": True,
            "recommended_models": ["3b", "7b"],
            "memory_efficient": False,
            "power_efficient": False,
        }

        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info["devices"] = self._parse_nvidia_gpu_output(result.stdout)
                info["vendor"] = "NVIDIA"
                return info
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("nvidia-smi GPU info unavailable: %s", e)

        # Fallback generic GPU info
        info["devices"] = ["GPU (detected)"]
        info["vendor"] = "Generic"
        return info

    def _get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information."""
        try:
            cpu_info = {
                "type": "CPU",
                "available": True,
                "cores": self.cpu_cores,
                "threads": psutil.cpu_count(logical=True),
                "recommended_models": [
                    "1b",
                    "3b",
                    "tiny",
                ],  # CPU suitable for all models
                "memory_efficient": True,
                "power_efficient": True,
                "architecture": platform.machine(),
                "processor": platform.processor(),
            }

            # Get more detailed CPU info if available
            try:
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read()
                    if "model name" in cpuinfo:
                        model_line = [
                            line for line in cpuinfo.split("\n") if "model name" in line
                        ][0]
                        cpu_info["model"] = model_line.split(":")[1].strip()
            except (FileNotFoundError, IndexError) as e:
                logger.debug("Detailed CPU info not available: %s", e)

            return cpu_info

        except Exception as e:
            logger.error("CPU info gathering error: %s", e)
            return {"type": "CPU", "available": True, "cores": self.cpu_cores}

    def _configure_device_priorities(self):
        """Configure device priorities based on availability."""
        self.current_config = {
            "priority_order": [],
            "device_assignments": {},
            "fallback_chain": [],
        }

        # Build priority order based on availability
        for device_type in self.device_priorities:
            if device_type in self.available_devices:
                self.current_config["priority_order"].append(device_type)

        # Configure agent-specific device assignments
        self._configure_agent_device_assignments()

        # Build fallback chain
        self.current_config["fallback_chain"] = self.current_config[
            "priority_order"
        ].copy()

    def _configure_agent_device_assignments(self):
        """Configure optimal device assignments for each agent type."""
        assignments = {}

        # NPU optimal assignments (if available)
        if self.npu_available:
            # NPU excels at small, efficient models
            assignments["chat"] = AccelerationType.NPU
            assignments["knowledge_retrieval"] = AccelerationType.NPU
            assignments["system_commands"] = AccelerationType.NPU

        # GPU assignments (if available)
        if self.gpu_available:
            # GPU good for larger models requiring parallel processing
            assignments["rag"] = AccelerationType.GPU
            assignments["orchestrator"] = AccelerationType.GPU
            assignments["research"] = AccelerationType.GPU

        # CPU fallback assignments
        if not self.npu_available:
            # CPU handles small models when NPU unavailable
            assignments["chat"] = AccelerationType.CPU
            assignments["knowledge_retrieval"] = AccelerationType.CPU
            assignments["system_commands"] = AccelerationType.CPU

        if not self.gpu_available:
            # CPU handles larger models when GPU unavailable
            assignments["rag"] = AccelerationType.CPU
            assignments["orchestrator"] = AccelerationType.CPU
            assignments["research"] = AccelerationType.CPU

        self.current_config["device_assignments"] = assignments

    def get_optimal_device_for_agent(self, agent_type: str) -> AccelerationType:
        """
        Get the optimal device type for a specific agent.

        Args:
            agent_type: Type of agent (chat, rag, orchestrator, etc.)

        Returns:
            AccelerationType: Optimal device type for the agent
        """
        # Check configured assignment
        if agent_type in self.current_config["device_assignments"]:
            return self.current_config["device_assignments"][agent_type]

        # Default priority chain
        for device_type in self.current_config["priority_order"]:
            return device_type

        # Final fallback
        return AccelerationType.CPU

    def get_ollama_device_config(self, agent_type: str) -> Dict[str, Any]:
        """
        Get Ollama-specific device configuration for an agent.

        Args:
            agent_type: Type of agent

        Returns:
            Dict containing Ollama device configuration
        """
        optimal_device = self.get_optimal_device_for_agent(agent_type)

        config = {
            "device_type": optimal_device.value,
            "ollama_options": {},
            "environment_vars": {},
        }

        if optimal_device == AccelerationType.NPU:
            # NPU configuration
            config["ollama_options"].update(
                {
                    "numa": False,  # NPU doesn't use NUMA
                    "num_thread": 1,  # NPU uses specialized threads
                }
            )
            config["environment_vars"].update(
                {"OLLAMA_DEVICE": "npu", "OPENVINO_DEVICE": "NPU"}
            )

        elif optimal_device == AccelerationType.GPU:
            # GPU configuration
            config["ollama_options"].update(
                {
                    "numa": False,
                    "num_gpu": 1,  # Use one GPU
                }
            )
            config["environment_vars"].update(
                {"OLLAMA_DEVICE": "gpu", "CUDA_VISIBLE_DEVICES": "0"}
            )

        else:  # CPU
            # CPU configuration - optimized for efficiency
            optimal_threads = min(self.cpu_cores, 4)  # Don't use all cores
            config["ollama_options"].update(
                {
                    "numa": True,
                    "num_thread": optimal_threads,
                }
            )
            config["environment_vars"].update(
                {"OLLAMA_DEVICE": "cpu", "OMP_NUM_THREADS": str(optimal_threads)}
            )

        return config

    def get_hardware_recommendations(self) -> Dict[str, Any]:
        """Get hardware optimization recommendations."""
        recommendations = {
            "current_setup": {},
            "optimizations": [],
            "agent_assignments": self.current_config["device_assignments"],
            "performance_tips": [],
        }

        # Current setup summary
        recommendations["current_setup"] = {
            "npu_available": self.npu_available,
            "gpu_available": self.gpu_available,
            "cpu_cores": self.cpu_cores,
            "priority_order": [d.value for d in self.current_config["priority_order"]],
        }

        # Generate optimizations
        if not self.npu_available:
            recommendations["optimizations"].append(
                "Consider Intel NPU for efficient small model execution (1B models)"
            )

        if not self.gpu_available:
            recommendations["optimizations"].append(
                "Consider GPU for faster large model execution (3B+ models)"
            )

        if self.cpu_cores < 8:
            recommendations["optimizations"].append(
                "Consider upgrading to 8+ CPU cores for better multi-agent performance"
            )

        # Performance tips
        if self.npu_available:
            recommendations["performance_tips"].append(
                "NPU excels at 1B models - use for Chat, Knowledge Retrieval, "
                "System Commands agents"
            )

        if self.gpu_available:
            recommendations["performance_tips"].append(
                "GPU optimal for 3B models - use for RAG, Orchestrator, Research agents"
            )

        recommendations["performance_tips"].extend(
            [
                "Reserve CPU for Redis, system operations, and fallback processing",
                "Monitor hardware utilization and adjust agent distribution as needed",
                "Use quantized models (q4_K_M) for optimal hardware efficiency",
            ]
        )

        return recommendations

    def configure_system_environment(self):
        """Configure system environment variables for optimal hardware usage."""
        try:
            # Set environment variables for the current process
            env_vars = {}

            # NPU configuration
            if self.npu_available:
                env_vars.update(
                    {
                        "OPENVINO_DEVICE_PRIORITIES": "NPU,GPU,CPU",
                        "INTEL_NPU_ENABLED": "1",
                    }
                )

            # GPU configuration
            if self.gpu_available:
                env_vars.update(
                    {
                        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
                        "GPU_MAX_HEAP_SIZE": "100",
                        "GPU_USE_SYNC_OBJECTS": "1",
                    }
                )

            # CPU configuration
            cpu_threads = min(self.cpu_cores, 4)  # Reserve cores for system
            env_vars.update(
                {
                    "OMP_NUM_THREADS": str(cpu_threads),
                    "MKL_NUM_THREADS": str(cpu_threads),
                    "OPENBLAS_NUM_THREADS": str(cpu_threads),
                }
            )

            # Store environment variables in config and apply them
            config_manager.set("runtime.environment_overrides", env_vars)
            for key, value in env_vars.items():
                os.environ[key] = value
                logger.debug("Set %s=%s", key, value)

            logger.info("System environment configured for hardware optimization")

        except Exception as e:
            logger.error("Failed to configure system environment: %s", e)

    def get_device_status(self) -> Dict[str, Any]:
        """Get current device status and utilization."""
        status = {"timestamp": psutil.boot_time(), "devices": {}, "recommendations": []}

        # CPU status
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        status["devices"]["cpu"] = {
            "utilization": cpu_percent,
            "memory_percent": memory.percent,
            "available_memory_gb": memory.available / (1024**3),
            "cores": self.cpu_cores,
            "status": "optimal" if cpu_percent < 80 else "high_load",
        }

        # Add GPU status if available (Issue #315: uses helper for parsing)
        if self.gpu_available:
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=utilization.gpu,memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    gpu_devices = _parse_nvidia_smi_output(result.stdout)
                    status["devices"].update(gpu_devices)
            except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
                status["devices"]["gpu"] = {"status": "unknown"}

        # Add NPU status if available
        if self.npu_available:
            status["devices"]["npu"] = {
                "status": "available",
                "utilization": "unknown",  # NPU utilization tracking not standardized
                "power_efficient": True,
            }

        return status


# Global instance (thread-safe)
import threading

_hardware_acceleration_manager = None
_hardware_acceleration_manager_lock = threading.Lock()


def get_hardware_acceleration_manager() -> HardwareAccelerationManager:
    """Get the singleton hardware acceleration manager instance (thread-safe)."""
    global _hardware_acceleration_manager
    if _hardware_acceleration_manager is None:
        with _hardware_acceleration_manager_lock:
            # Double-check after acquiring lock
            if _hardware_acceleration_manager is None:
                _hardware_acceleration_manager = HardwareAccelerationManager()
    return _hardware_acceleration_manager
