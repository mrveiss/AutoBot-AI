# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge-base adapter modules."""

from knowledge.adapters.okf_adapter import OKFAdapter, export_to_okf, import_from_okf

__all__ = ["OKFAdapter", "export_to_okf", "import_from_okf"]
