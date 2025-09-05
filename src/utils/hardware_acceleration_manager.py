"""
Hardware Acceleration Manager wrapper.
Re-exports the HardwareAccelerationManager from the main hardware_acceleration module.
"""

# Re-export the HardwareAccelerationManager from the main module
from src.hardware_acceleration import HardwareAccelerationManager

__all__ = ['HardwareAccelerationManager']