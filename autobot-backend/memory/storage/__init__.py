# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Storage Components - Task and General Storage
"""

from .general_storage import GeneralStorage
from .task_storage import TaskStorage

__all__ = [
    "TaskStorage",
    "GeneralStorage",
]
