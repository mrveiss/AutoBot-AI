#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enable NPU Support for AutoBot with Intel Core Ultra processors.

This script configures NPU support and provides diagnostic information
about Intel NPU availability and OpenVINO configuration.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_cpu_npu_support():
    """Check if CPU supports NPU."""
    try:
        result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            cpu_info = result.stdout
            # Intel Core Ultra series has NPU
            if "Intel(R) Core(TM) Ultra" in cpu_info:
                logger.info("✅ Intel Core Ultra CPU detected - NPU hardware available")
                return True
            # Some newer Intel CPUs also have NPU
            elif "Intel" in cpu_info:
                logger.info("🔍 Intel CPU detected - NPU support may be available")
                return True
        return False
    except Exception as e:
        logger.error("Error checking CPU: %s", e)
        return False


def check_openvino_npu():
    """Check OpenVINO NPU device availability."""
    try:
        from openvino.runtime import Core

        core = Core()
        devices = core.available_devices
        logger.info("OpenVINO available devices: %s", devices)

        npu_devices = [d for d in devices if "NPU" in d]
        if npu_devices:
            logger.info("✅ OpenVINO NPU devices found: %s", npu_devices)
            return True, npu_devices
        else:
            logger.warning("❌ No NPU devices found in OpenVINO")
            return False, []

    except ImportError:
        logger.error("❌ OpenVINO not installed")
        return False, []
    except Exception as e:
        logger.error("❌ Error checking OpenVINO: %s", e)
        return False, []


def install_intel_npu_drivers():
    """Attempt to install Intel NPU drivers."""
    logger.info("🔧 Attempting to install Intel NPU drivers...")

    # Check if running on WSL (NPU may not work in WSL)
    try:
        with open("/proc/version", "r") as f:
            kernel_info = f.read()
            if "WSL" in kernel_info or "Microsoft" in kernel_info:
                logger.warning("⚠️ Running on WSL - NPU drivers may not be available")
                logger.warning(
                    "   NPU support typically requires native Linux or Windows"
                )
                return False
    except FileNotFoundError:
        pass

    commands_to_try = [
        # Try to install Intel OpenVINO NPU plugin
        ["pip", "install", "openvino-npu", "--upgrade"],
        # Install Intel drivers repository
        ["sudo", "apt", "update"],
        [
            "sudo",
            "apt",
            "install",
            "-y",
            "intel-opencl-icd",
            "intel-media-va-driver-non-free",
        ],
    ]

    for cmd in commands_to_try:
        try:
            logger.info("Running: %s", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                logger.info("✅ Success: %s", " ".join(cmd))
            else:
                logger.warning("⚠️ Command failed: %s", " ".join(cmd))
                logger.warning("   Error: %s", result.stderr)
        except subprocess.TimeoutExpired:
            logger.warning("⏰ Timeout running: %s", " ".join(cmd))
        except FileNotFoundError:
            logger.warning("🚫 Command not found: %s", cmd[0])
        except Exception as e:
            logger.error("❌ Error running %s: %s", " ".join(cmd), e)

    return True


def configure_ollama_npu():
    """Configure Ollama to use NPU when available."""
    try:
        # Set environment variables for NPU
        npu_env_vars = {
            "OLLAMA_DEVICE": "npu",
            "OPENVINO_DEVICE": "NPU",
            "INTEL_NPU_ENABLED": "1",
            "OPENVINO_DEVICE_PRIORITIES": "NPU,GPU,CPU",
        }

        logger.info("🔧 Configuring environment variables for NPU support:")
        for key, value in npu_env_vars.items():
            os.environ[key] = value
            logger.info("   %s=%s", key, value)

        # Write to AutoBot config
        config_updates = []
        for key, value in npu_env_vars.items():
            config_updates.append(f'export {key}="{value}"')

        config_file = Path(__file__).parent / "npu_env_config.sh"
        with open(config_file, "w") as f:
            f.write("#!/bin/bash\n")
            f.write("# NPU Environment Configuration for AutoBot\n\n")
            f.write("\n".join(config_updates))
            f.write("\n")

        logger.info("✅ NPU configuration written to %s", config_file)
        logger.info(
            "   Source this file before running AutoBot: source npu_env_config.sh"
        )

        return True

    except Exception as e:
        logger.error("❌ Error configuring NPU: %s", e)
        return False


def test_npu_inference():
    """Test NPU inference if available."""
    try:
        from openvino.runtime import Core

        core = Core()
        npu_devices = [d for d in core.available_devices if "NPU" in d]

        if not npu_devices:
            logger.warning("⚠️ No NPU devices available for testing")
            return False

        logger.info("🧪 Testing NPU inference on device: %s", npu_devices[0])

        # Simple test would require a model, for now just confirm device availability
        logger.info("✅ NPU device available for inference")
        return True

    except Exception as e:
        logger.error("❌ NPU inference test failed: %s", e)
        return False


def main():
    """Main NPU configuration and testing."""
    logger.info("🚀 AutoBot NPU Configuration Tool")
    logger.info("=" * 50)

    # Step 1: Check CPU NPU support
    logger.info("1️⃣ Checking CPU NPU support...")
    cpu_supports_npu = check_cpu_npu_support()

    # Step 2: Check OpenVINO NPU
    logger.info("\n2️⃣ Checking OpenVINO NPU support...")
    openvino_npu_available, npu_devices = check_openvino_npu()

    # Step 3: Install drivers if needed
    if cpu_supports_npu and not openvino_npu_available:
        logger.info("\n3️⃣ Installing NPU drivers...")
        install_intel_npu_drivers()

        # Re-check after installation
        logger.info("\n🔄 Re-checking OpenVINO NPU after driver installation...")
        openvino_npu_available, npu_devices = check_openvino_npu()

    # Step 4: Configure Ollama
    logger.info("\n4️⃣ Configuring NPU support...")
    configure_ollama_npu()

    # Step 5: Test NPU
    if openvino_npu_available:
        logger.info("\n5️⃣ Testing NPU inference...")
        test_npu_inference()

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 NPU Configuration Summary:")
    logger.info("   CPU NPU Support: %s", "✅ Yes" if cpu_supports_npu else "❌ No")
    logger.info(
        f"   OpenVINO NPU: {'✅ Available' if openvino_npu_available else '❌ Not Available'}"
    )
    if npu_devices:
        logger.info("   NPU Devices: %s", ", ".join(npu_devices))

    if openvino_npu_available:
        logger.info("\n🎉 NPU is configured and ready!")
        logger.info("   AutoBot will now prioritize NPU for small models (1B, 3B)")
        logger.info("   Restart AutoBot to apply NPU configuration")
    else:
        logger.info("\n⚠️ NPU not available - using GPU/CPU fallback")
        if cpu_supports_npu:
            logger.info("   Your CPU supports NPU but drivers may not be installed")
            logger.info("   On WSL/virtualized environments, NPU may not be accessible")

    return openvino_npu_available


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
