# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Reusable concurrency primitives for AutoBot orchestration.

See docs/developer/PRIMITIVES.md for the full inventory and #5060 for
the extraction-first methodology.
"""

from .concurrency import bounded_gather

__all__ = ["bounded_gather"]
