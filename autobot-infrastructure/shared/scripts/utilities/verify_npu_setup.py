#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
NPU Setup Verification Script
Verifies Intel NPU driver installation and hardware availability
"""

import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_npu_device():
    """Check if NPU device exists"""
    npu_device = Path("/dev/accel/accel0")
    if npu_device.exists():
        logger.info("✅ NPU device found: %s", npu_device)

        # Check permissions
        stat = npu_device.stat()
        logger.info("📋 Device permissions: %s", oct(stat.st_mode)[-3:])
        logger.info("📋 Device owner:group: %s:%s", stat.st_uid, stat.st_gid)

        return True
    else:
        logger.error("❌ NPU device /dev/accel/accel0 not found")
        return False


def check_kernel_module():
    """Check if intel_vpu kernel module is loaded"""
    try:
        result = subprocess.run(["lsmod"], capture_output=True, text=True)
        if "intel_vpu" in result.stdout:
            logger.info("✅ intel_vpu kernel module is loaded")
            return True
        else:
            logger.error("❌ intel_vpu kernel module not loaded")
            return False
    except Exception as e:
        logger.error("❌ Error checking kernel modules: %s", e)
        return False


def check_user_groups():
    """Check if user is in render/video groups"""
    try:
        result = subprocess.run(["groups"], capture_output=True, text=True)
        groups = result.stdout.strip()

        has_render = "render" in groups
        has_video = "video" in groups

        if has_render:
            logger.info("✅ User is in 'render' group")
        else:
            logger.warning("⚠️ User is NOT in 'render' group")

        if has_video:
            logger.info("✅ User is in 'video' group")
        else:
            logger.warning("⚠️ User is NOT in 'video' group")

        return has_render or has_video
    except Exception as e:
        logger.error("❌ Error checking user groups: %s", e)
        return False


def check_openvino_npu():
    """Check if OpenVINO can detect NPU"""
    try:
        import openvino as ov

        core = ov.Core()
        devices = core.available_devices

        logger.info("📋 Available OpenVINO devices: %s", devices)

        npu_devices = [d for d in devices if "NPU" in d]
        if npu_devices:
            logger.info("✅ OpenVINO NPU devices found: %s", npu_devices)
            return True
        else:
            logger.warning("⚠️ No NPU devices detected by OpenVINO")
            return False

    except ImportError:
        logger.warning("⚠️ OpenVINO not installed - skipping NPU device check")
        return None
    except Exception as e:
        logger.error("❌ Error checking OpenVINO NPU devices: %s", e)
        return False


def main():
    """Run all NPU verification checks"""
    logger.info("🔍 Starting NPU Setup Verification...")
    logger.info("=" * 50)

    checks = [
        ("Kernel Module", check_kernel_module),
        ("NPU Device", check_npu_device),
        ("User Groups", check_user_groups),
        ("OpenVINO NPU", check_openvino_npu),
    ]

    results = {}
    for name, check_func in checks:
        logger.info("\n🔍 Checking %s...", name)
        result = check_func()
        results[name] = result

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 VERIFICATION SUMMARY:")
    logger.info("=" * 50)

    all_passed = True
    for name, result in results.items():
        if result is True:
            logger.info("✅ %s: PASS", name)
        elif result is False:
            logger.error("❌ %s: FAIL", name)
            all_passed = False
        else:
            logger.warning("⚠️ %s: SKIPPED", name)

    if all_passed:
        logger.info("\n🎉 NPU setup verification PASSED!")
        logger.info("🚀 NPU worker should be able to access hardware acceleration")
    else:
        logger.error("\n💥 NPU setup verification FAILED!")
        logger.error("🔧 Please check the failed items above")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
