# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``CommandManualManager._determine_category`` (#14047)."""

from command_manual_manager import CommandManualManager
from constants.threshold_constants import CategoryDefaults


def _manager() -> CommandManualManager:
    return CommandManualManager(db_path=":memory:")


def test_no_keyword_match_defaults_to_general():
    manager = _manager()

    category = manager._determine_category("totallyunknowncmd", "no matching keywords here at all")

    assert category == CategoryDefaults.GENERAL


def test_explicit_pattern_match_overrides_default():
    manager = _manager()
    # "ls" is a known file-operation command per _load_category_patterns().
    category = manager._determine_category("ls", "list directory contents")

    assert category == "file_operations"
    assert category != CategoryDefaults.GENERAL
