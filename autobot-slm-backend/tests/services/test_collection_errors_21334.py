# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21334: the helper is the one decision point - callers hand it any exception."""

import pytest
from sqlalchemy.exc import OperationalError

from services.collection_errors import operational_failure_reason


def test_an_operational_error_becomes_a_class_name_only_reason() -> None:
    reason = operational_failure_reason("outdated nodes", OperationalError("SELECT secret", {}, Exception("boom")))
    assert reason == "Could not determine outdated nodes: OperationalError"


def test_an_os_error_is_operational() -> None:
    assert operational_failure_reason("x", OSError("disk")) == "Could not determine x: OSError"


def test_a_programming_error_is_re_raised_to_the_caller() -> None:
    with pytest.raises(TypeError):
        operational_failure_reason("outdated nodes", TypeError("object is not awaitable"))
