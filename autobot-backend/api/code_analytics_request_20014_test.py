# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``CodeAnalyticsRequest`` offers only what its endpoints read (#20014)."""

import pytest
from pydantic import ValidationError

from api.schemas_code import CodeAnalyticsRequest


def test_the_request_carries_only_the_field_the_endpoints_read():
    assert set(CodeAnalyticsRequest.model_fields) == {"root_path"}
    assert CodeAnalyticsRequest(root_path="/repo").root_path == "/repo"


@pytest.mark.parametrize("field", ["include_patterns", "exclude_patterns", "languages"])
def test_a_filter_the_analysis_cannot_apply_is_refused_not_ignored(field):
    with pytest.raises(ValidationError):
        CodeAnalyticsRequest(root_path="/repo", **{field: ["x"]})
