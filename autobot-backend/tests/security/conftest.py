# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixtures the #20443 revocation tests share: an in-memory epoch store and the real ``get_current_user``."""

from tests.security._revocation_harness import epochs, get_current_user  # noqa: F401  (pytest finds fixtures by name)
