# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC configuration package (GH#8487).

Re-exports legacy llc/config.py symbols so existing callers continue to work
now that llc/config/ directory (GH#8487) shadows the old flat module.
"""

import os

# Agent API base URL — re-exported from the legacy flat module so that
# ``from llc.config import AGENT_API_BASE_URL`` keeps working (GH#8487).
AGENT_API_BASE_URL = os.environ.get("LLC_AGENT_API_BASE_URL", "http://localhost:8001/api")

__all__ = ["AGENT_API_BASE_URL"]
