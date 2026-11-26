# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every agent-terminal test starts with an empty learned-rule set (#16840)."""

import pytest

from services.command_line_risk import reset_shared_approval_manager


@pytest.fixture(autouse=True)
def _fresh_learned_rules():
    reset_shared_approval_manager()
    yield
    reset_shared_approval_manager()
