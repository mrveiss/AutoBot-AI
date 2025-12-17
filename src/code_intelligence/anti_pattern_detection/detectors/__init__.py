# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detectors Package

Contains specialized detector modules for different anti-pattern categories.

Part of Issue #381 - God Class Refactoring
"""

from .bloaters import BloaterDetector
from .couplers import CouplerDetector
from .dispensables import DispensableDetector
from .naming import NamingDetector

__all__ = [
    "BloaterDetector",
    "CouplerDetector",
    "DispensableDetector",
    "NamingDetector",
]
