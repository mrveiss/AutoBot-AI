# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward-compatibility shim for trusted-proxy utilities (Issue #2408).

The canonical implementation has moved to autobot_shared.proxy_utils.
All existing imports of ``from middleware.proxy_utils import get_client_ip``
continue to work unchanged via this re-export.

Usage
-----
    from middleware.proxy_utils import get_client_ip   # legacy — still works
    from autobot_shared.proxy_utils import get_client_ip  # preferred
"""

from autobot_shared.proxy_utils import _normalize_ip, get_client_ip

__all__ = ["get_client_ip", "_normalize_ip"]
