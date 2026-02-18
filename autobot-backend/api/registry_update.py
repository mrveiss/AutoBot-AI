import logging
import os

logger = logging.getLogger(__name__)

"""
Add Phase 9 monitoring router to the registry
"""

# Read the registry file and add the Phase 9 monitoring entry
import re


def add_phase9_monitoring_to_registry():
    """Add Phase 9 monitoring router to the registry"""

    base_dir = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
    registry_file = f"{base_dir}/backend/api/registry.py"

    # Read the current file
    with open(registry_file, "r") as f:
        content = f.read()

    # Find the monitoring section and add the Phase 9 monitoring router
    phase9_router_config = """            "phase9_monitoring": RouterConfig(
                name="phase9_monitoring",
                module_path="backend.api.phase9_monitoring",
                prefix="/api/monitoring/phase9",
                tags=["monitoring", "phase9", "gpu", "npu", "performance"],
                status=RouterStatus.ENABLED,
                description="Phase 9 comprehensive performance monitoring for GPU/NPU utilization and multi-modal AI"
            ),"""

    # Insert after the existing monitoring router config
    pattern = r'("monitoring": RouterConfig\(.*?\),)'
    replacement = r"\1\n" + phase9_router_config

    updated_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # Write the updated content back
    with open(registry_file, "w") as f:
        f.write(updated_content)

    logger.info("Phase 9 monitoring router added to registry successfully!")


if __name__ == "__main__":
    add_phase9_monitoring_to_registry()
