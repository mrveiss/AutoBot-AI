# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Contract tests for ``tests.fixtures.mocks.make_llm_response`` (#7134).

Pins the canonical LLMResponse-stub factory's behavior so the 7+ ad-hoc
test patterns that exist today can be migrated onto it with confidence.

Why a fixture-test exists at all: the factory's whole value comes from
returning the **real** ``LLMResponse`` from ``llm_shared.models``
when importable. If a future field rename or type change happens on
that dataclass, this test fails first — the migration target is broken,
not silently producing wrong-shape mocks.
"""

from __future__ import annotations

import pytest

from tests.fixtures import make_llm_response


def test_returns_real_llmresponse_when_importable() -> None:
    """The factory's primary value: returns the actual LLMResponse class
    so the field contract is pinned. If imports work in this environment,
    the result must be an instance of the real LLMResponse.
    """
    try:
        from llm_shared.models import LLMResponse
    except ImportError:
        pytest.skip("llm_shared.models not importable — fallback path is fine")

    response = make_llm_response(content="hello")
    assert isinstance(response, LLMResponse)


def test_default_content_is_empty_string() -> None:
    """Bare call returns a healthy, no-content response."""
    response = make_llm_response()
    assert response.content == ""
    assert response.error is None


def test_passes_through_all_documented_kwargs() -> None:
    response = make_llm_response(
        content="hello",
        error="rate limit",
        model="gpt-4",
        provider="openai",
    )
    assert response.content == "hello"
    assert response.error == "rate limit"
    assert response.model == "gpt-4"
    assert response.provider == "openai"


def test_keyword_only_args() -> None:
    """All args are keyword-only — positional would invite the same
    field-shape drift the function exists to prevent.
    """
    with pytest.raises(TypeError):
        make_llm_response("hello")  # type: ignore[misc]


def test_error_field_supports_none_default() -> None:
    """The healthy default — ``error=None`` — must not be coerced to ``""``;
    callers like ``WorkflowDocumenter`` check ``if not response.error`` and
    an empty-string error would be indistinguishable from None for falsy
    checks but DIFFERENT from None for ``response.error is None`` checks.
    """
    response = make_llm_response(content="ok")
    assert response.error is None
    # Falsy check works either way:
    assert not response.error


def test_back_compat_underscore_alias_still_works() -> None:
    """``_build_mock_response(content)`` is the legacy entry point used
    inside ``MockLLMService.chat`` — keeping it functional avoids breaking
    the existing demo `__main__` blocks.
    """
    from tests.fixtures.mocks import _build_mock_response

    response = _build_mock_response("hello")
    assert response.content == "hello"
    # Legacy alias still uses the documented "mock" defaults
    assert response.model == "mock"
    assert response.provider == "mock"


def test_factory_is_re_exported_from_fixtures_package() -> None:
    """``from tests.fixtures import make_llm_response`` is the documented
    import path — pinning it prevents an accidental rename / removal.
    """
    import tests.fixtures as fixtures

    assert "make_llm_response" in fixtures.__all__
    assert callable(fixtures.make_llm_response)
