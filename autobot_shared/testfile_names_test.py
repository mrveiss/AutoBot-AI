# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical test-file-name detector (#20493), including its route_order call site."""

from pathlib import Path

import pytest

from autobot_shared.api_routing.route_order import is_test_path
from autobot_shared.testfile_names import is_test_filename


@pytest.mark.parametrize("name", ["a_test.py", "test_a.py", "tests.py", "conftest.py", "A_Test.PY", "x/y/a_test.py"])
def test_python_test_names(name):
    assert is_test_filename(name)


@pytest.mark.parametrize("name", ["contest.py", "latest.py", "testing.py", "attestation.py", "a_test.pyc", "test.py"])
def test_production_names(name):
    assert not is_test_filename(name)


def test_route_order_uses_the_canonical_rule_plus_its_directory_rule():
    assert is_test_path(Path("api/x_test.py")) and is_test_path(Path("tests/helpers.py"))
    assert is_test_path(Path("api/conftest.py")) and not is_test_path(Path("api/users.py"))


@pytest.mark.parametrize("name", ["test_.py", "_test.py", "x/test_.py", "x/_test.py"])
def test_degenerate_names_are_tests(name):
    """The old ``startswith("test_")`` / ``endswith("_test")`` rules counted these; meta_agent's
    ``_validate_target`` refuses test files as targets, so they must stay refused (#21078)."""
    assert is_test_filename(name, include_js=False)


def test_include_conftest_false_keeps_conftest_in_a_tools_population():
    assert is_test_filename("conftest.py") and is_test_filename("a/b/conftest.py", include_js=False)
    assert not is_test_filename("conftest.py", include_conftest=False)
    assert not is_test_filename("a/Conftest.PY", include_js=False, include_conftest=False)
    # Every other test name is unaffected by the keyword.
    for name in ("a_test.py", "test_a.py", "tests.py", "test_.py", "_test.py", "a.test.ts", "b.spec.vue"):
        assert is_test_filename(name, include_conftest=False)
