#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot NPU Integration Test
Tests NPU integration with AutoBot system
"""

import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_openvino_npu_detection():
    """Test if OpenVINO can detect NPU devices"""
    try:
        import openvino as ov

        core = ov.Core()
        devices = core.available_devices

        logger.info(f"📋 Available OpenVINO devices: {devices}")

        npu_devices = [d for d in devices if "NPU" in d]
        if npu_devices:
            logger.info(f"✅ OpenVINO NPU devices found: {npu_devices}")

            # Try to get NPU device info
            for npu_device in npu_devices:
                try:
                    device_name = core.get_property(npu_device, "FULL_DEVICE_NAME")
                    logger.info(f"📋 NPU device name: {device_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not get NPU device info: {e}")

            return True
        else:
            logger.warning("⚠️ No NPU devices detected by OpenVINO")
            return False

    except ImportError:
        logger.error("❌ OpenVINO not available")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking OpenVINO NPU devices: {e}")
        return False


def test_level_zero_libraries():
    """Test if Level Zero libraries are accessible"""
    try:
        # Check if Level Zero libraries are installed
        result = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True)
        libs_found = []

        level_zero_libs = ["libze_loader.so", "libze_intel_npu.so"]
        for lib in level_zero_libs:
            if lib in result.stdout:
                libs_found.append(lib)
                logger.info(f"✅ Found Level Zero library: {lib}")
            else:
                logger.warning(f"⚠️ Level Zero library not found: {lib}")

        return len(libs_found) > 0

    except Exception as e:
        logger.error(f"❌ Error checking Level Zero libraries: {e}")
        return False


def test_npu_worker_compatibility():
    """Test NPU worker Python compatibility"""
    try:
        # Test if we can import our NPU model manager
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "docker" / "npu-worker")
        )

        try:
            from npu_model_manager import NPUModelManager

            logger.info("✅ NPU model manager can be imported")

            # Try to initialize (this will likely fail without hardware)
            try:
                manager = NPUModelManager()
                logger.info("✅ NPU model manager initialized")
                logger.info(f"📋 NPU available: {manager.npu_available}")
                return True
            except Exception as e:
                logger.warning(
                    f"⚠️ NPU model manager initialization failed (expected without hardware): {e}"
                )
                return False

        except ImportError as e:
            logger.error(f"❌ Could not import NPU model manager: {e}")
            return False

    except Exception as e:
        logger.error(f"❌ Error testing NPU worker compatibility: {e}")
        return False


def test_docker_npu_container():
    """Test if Docker NPU container can be built"""
    try:
        logger.info("🔨 Testing Docker NPU container build...")

        # Check if docker-compose file exists
        compose_file = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "compose"
            / "docker-compose.hybrid.yml"
        )
        if not compose_file.exists():
            logger.error("❌ Docker compose file not found")
            return False

        # Try to build NPU worker (dry run)
        cmd = ["docker", "compose", "-f", str(compose_file), "config", "--services"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and "autobot-npu-worker" in result.stdout:
            logger.info("✅ Docker NPU service configuration is valid")
            return True
        else:
            logger.error(f"❌ Docker compose config failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("❌ Docker compose config timed out")
        return False
    except Exception as e:
        logger.error(f"❌ Error testing Docker NPU container: {e}")
        return False


def main():
    """Run all NPU integration tests"""
    logger.info("🚀 Starting AutoBot NPU Integration Tests...")
    logger.info("=" * 60)

    tests = [
        ("Level Zero Libraries", test_level_zero_libraries),
        ("OpenVINO NPU Detection", test_openvino_npu_detection),
        ("NPU Worker Compatibility", test_npu_worker_compatibility),
        ("Docker NPU Container", test_docker_npu_container),
    ]

    results = {}
    for name, test_func in tests:
        logger.info(f"\n🔍 Testing {name}...")
        try:
            result = test_func()
            results[name] = result
            if result:
                logger.info(f"✅ {name}: PASS")
            else:
                logger.warning(f"⚠️ {name}: PARTIAL/FAIL")
        except Exception as e:
            logger.error(f"❌ {name}: ERROR - {e}")
            results[name] = False

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 NPU INTEGRATION TEST SUMMARY:")
    logger.info("=" * 60)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL/PARTIAL"
        logger.info(f"{status}: {name}")

    logger.info(f"\n📈 Overall Score: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All NPU integration tests passed!")
        logger.info("🚀 NPU worker should work when hardware is available")
        return 0
    elif passed > 0:
        logger.warning("⚠️ Partial NPU integration - some components ready")
        logger.warning("🔧 NPU worker may work with limitations")
        return 1
    else:
        logger.error("💥 NPU integration tests failed!")
        logger.error("🔧 NPU worker requires setup fixes")
        return 2


if __name__ == "__main__":
    sys.exit(main())
