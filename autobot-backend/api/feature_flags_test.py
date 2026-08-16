# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``previous_mode`` audit-log default in
``update_enforcement_mode`` (#14047).

Unconditional literal (not a caller-supplied ``.get(key, default)``), so
there is no override case — only that the fallback value is unchanged.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.feature_flags import update_enforcement_mode
from api.schemas_system import EnforcementModeUpdate
from constants.threshold_constants import CategoryDefaults
from services.feature_flags import EnforcementMode


@pytest.mark.asyncio
async def test_previous_mode_defaults_to_unknown_in_audit_log():
    mock_flags = AsyncMock()
    mock_flags.set_enforcement_mode.return_value = True
    update = EnforcementModeUpdate(mode=EnforcementMode.ENFORCED)
    admin = {"username": "root"}

    with patch("api.feature_flags.audit_log", new_callable=AsyncMock) as mock_audit_log:
        await update_enforcement_mode(update, admin, mock_flags)

    _, kwargs = mock_audit_log.call_args
    assert kwargs["details"]["previous_mode"] == CategoryDefaults.UNKNOWN
