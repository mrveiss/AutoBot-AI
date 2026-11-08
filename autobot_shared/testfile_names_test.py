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
