# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat-approval panel offers exactly the categories the backend enforces (#20465).

The panel's category list lives in TypeScript and cannot import ``ApprovalCategory``; a category
missing from it can never be relaxed from the UI, and one that is not a real category would be
silently dropped by the backend. This keeps the two lists equal.
"""

from __future__ import annotations

import re
from pathlib import Path

from autobot_shared.tool_catalogue import ApprovalCategory

_TS = Path(__file__).resolve().parents[3] / "autobot-slm-frontend/src/views/settings/admin/chatApprovalSettings.ts"


def test_panel_categories_equal_the_backend_enum():
    source = _TS.read_text(encoding="utf-8")
    block = re.search(r"APPROVAL_CATEGORIES = \[(.*?)\] as const", source, re.S)
    assert block, "APPROVAL_CATEGORIES not found in chatApprovalSettings.ts"
    listed = re.findall(r"'([^']+)'", block.group(1))

    assert listed, "parsed an empty category list"
    assert sorted(listed) == sorted(c.value for c in ApprovalCategory)
