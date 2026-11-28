# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`is_non_production_module` follows the canonical test-file name rule (#21078).

Beside the old prefix/suffix/`conftest` rule the canonical one also skips a submodule named
`tests` (it drags pytest in like any other) and matches case-insensitively. Pinned here so the
widening is intentional; the degenerate `test_` / `_test` names the old rule skipped stay skipped.
"""

import pytest

from autobot_shared.plugin_sdk.loader import is_non_production_module


@pytest.mark.parametrize("name", ["tests", "test_", "_test", "Test_Something", "Conftest", "PLUGIN_SDK_TEST"])
def test_canonical_rule_names_are_skipped(name):
    assert is_non_production_module(name) is True


@pytest.mark.parametrize("name", ["testing", "attestation", "latest", "contest", "test"])
def test_names_that_only_contain_test_are_not_skipped(name):
    assert is_non_production_module(name) is False
