# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Add hardware monitoring router to the registry
"""

import re

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)


def add_hardware_monitoring_to_registry():
    """Add hardware monitoring router to the registry"""

    base_dir = config.base_dir
    registry_file = f"{base_dir}/backend/api/registry.py"

    # Read the current file
    with open(registry_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the monitoring section and add the hardware monitoring router
    hardware_router_config = """            "hardware_monitoring": RouterConfig(
                name="hardware_monitoring",
                module_path="api.hardware_monitoring",
                prefix="/api/monitoring/hardware",
                tags=["monitoring", "gpu", "npu", "performance"],
                status=RouterStatus.ENABLED,
                description="Hardware performance monitoring for GPU/NPU utilization and multi-modal AI"
            ),"""

    # Insert after the existing monitoring router config
    pattern = r'("monitoring": RouterConfig\(.*?\),)'
    replacement = r"\1\n" + hardware_router_config

    updated_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # Write the updated content back
    with open(registry_file, "w", encoding="utf-8") as f:
        f.write(updated_content)

    logger.info("Hardware monitoring router added to registry successfully!")


if __name__ == "__main__":
    add_hardware_monitoring_to_registry()
