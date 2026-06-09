# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Hardware Acceleration Manager wrapper.
Re-exports the HardwareAccelerationManager from the main hardware_acceleration module.
"""

# Re-export the HardwareAccelerationManager from the main module
from hardware_acceleration import HardwareAccelerationManager

__all__ = ["HardwareAccelerationManager"]
