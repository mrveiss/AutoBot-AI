# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``_build_workflows_template`` (#14047).

The category is an unconditional template literal (no caller-supplied
override path) -- only the fallback value itself is asserted.
"""

from constants.threshold_constants import CategoryDefaults
from manage_system_knowledge import _build_workflows_template


def test_workflows_template_category_defaults_to_general():
    template = _build_workflows_template("deploy")

    assert template["metadata"]["category"] == CategoryDefaults.GENERAL
