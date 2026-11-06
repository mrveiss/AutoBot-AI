# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: a non-ASCII key header is refused, never a 500 from ``compare_digest``."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from autobot_shared.auth import internal_api_key as mod

_KEY = "k" * 32  # pragma: allowlist secret


async def test_a_non_ascii_header_is_refused_not_an_error() -> None:
    with patch.object(mod.node_proxy, "internal_api_key", return_value=_KEY):
        assert mod.verify_internal_api_key("é" * 32) is False
        with pytest.raises(HTTPException) as refused:
            await mod.require_internal_api_key("é" * 32)
    assert refused.value.status_code == 403


async def test_contrast_the_right_key_passes() -> None:
    with patch.object(mod.node_proxy, "internal_api_key", return_value=_KEY):
        assert mod.verify_internal_api_key(_KEY) is True
        assert await mod.require_internal_api_key(_KEY) is None
