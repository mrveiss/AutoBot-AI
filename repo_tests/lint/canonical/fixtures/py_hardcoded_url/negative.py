# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Negative fixture: resolves the URL through the SSOT config."""

from autobot_shared.ssot_config import config

URL = config.get_service_url("backend")
