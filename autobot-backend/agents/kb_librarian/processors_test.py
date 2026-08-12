# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default on ``ToolInfoData.__init__`` (#14047).

``category`` has no constructor parameter — it is always set to the default
on construction, then optionally reassigned by callers afterward, so
"override" here means "can still be mutated post-construction", not a
constructor argument.
"""

from agents.kb_librarian.processors import ToolInfoData
from constants.threshold_constants import CategoryDefaults


def test_category_defaults_to_general_on_construction():
    tool = ToolInfoData("curl")

    assert tool.category == CategoryDefaults.GENERAL


def test_category_can_still_be_reassigned_after_construction():
    tool = ToolInfoData("curl")

    tool.category = "network"

    assert tool.category == "network"
