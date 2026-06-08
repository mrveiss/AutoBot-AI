# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for web_fetch.types — enum validation, FetchResult dataclass, cache_key."""

import hashlib

import pytest

from web_fetch.types import (
    ERR_CIRCUIT_OPEN,
    ERR_CONNECTION,
    ERR_HTTP_ERROR,
    ERR_ROBOTS_BLOCKED,
    ERR_SSRF_BLOCKED,
    ERR_TIMEOUT,
    ERR_TOO_LARGE,
    ERR_UNKNOWN,
    FetchResult,
    RenderMode,
)


class TestRenderMode:
    def test_values(self) -> None:
        assert RenderMode.AUTO.value == "auto"
        assert RenderMode.FAST.value == "fast"
        assert RenderMode.PLAYWRIGHT.value == "playwright"

    def test_is_str_enum(self) -> None:
        assert RenderMode.AUTO == "auto"
        assert RenderMode.FAST == "fast"

    def test_from_value(self) -> None:
        assert RenderMode("auto") is RenderMode.AUTO
        assert RenderMode("playwright") is RenderMode.PLAYWRIGHT

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            RenderMode("nonsense")

    def test_all_three_members(self) -> None:
        members = {m.value for m in RenderMode}
        assert members == {"auto", "fast", "playwright"}


class TestFetchResult:
    def test_success_defaults(self) -> None:
        r = FetchResult(url="https://example.com", success=True, markdown="# Hello")
        assert r.url == "https://example.com"
        assert r.success is True
        assert r.markdown == "# Hello"
        assert r.title == ""
        assert r.error_code is None
        assert r.retryable is False
        assert r.status_code is None

    def test_failure_defaults(self) -> None:
        r = FetchResult(url="https://bad.com", success=False, error_code=ERR_SSRF_BLOCKED)
        assert r.success is False
        assert r.error_code == ERR_SSRF_BLOCKED

    def test_cache_key_deterministic(self) -> None:
        r = FetchResult(url="https://example.com", success=True)
        k1 = r.cache_key(RenderMode.AUTO)
        k2 = r.cache_key(RenderMode.AUTO)
        assert k1 == k2

    def test_cache_key_differs_by_mode(self) -> None:
        r = FetchResult(url="https://example.com", success=True)
        assert r.cache_key(RenderMode.AUTO) != r.cache_key(RenderMode.PLAYWRIGHT)

    def test_cache_key_format(self) -> None:
        r = FetchResult(url="https://example.com", success=True)
        key = r.cache_key(RenderMode.FAST)
        assert key.startswith("web_fetch:content:")
        digest_part = key.split(":", 2)[2]
        assert len(digest_part) == 64  # sha256 hex

    def test_cache_key_uses_url_and_mode(self) -> None:
        r = FetchResult(url="https://example.com", success=True)
        raw = "https://example.com|fast"
        expected = "web_fetch:content:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
        assert r.cache_key(RenderMode.FAST) == expected


class TestErrorConstants:
    def test_all_constants_are_strings(self) -> None:
        for const in (
            ERR_SSRF_BLOCKED,
            ERR_ROBOTS_BLOCKED,
            ERR_CIRCUIT_OPEN,
            ERR_HTTP_ERROR,
            ERR_TIMEOUT,
            ERR_CONNECTION,
            ERR_TOO_LARGE,
            ERR_UNKNOWN,
        ):
            assert isinstance(const, str)

    def test_constants_are_distinct(self) -> None:
        constants = [
            ERR_SSRF_BLOCKED,
            ERR_ROBOTS_BLOCKED,
            ERR_CIRCUIT_OPEN,
            ERR_HTTP_ERROR,
            ERR_TIMEOUT,
            ERR_CONNECTION,
            ERR_TOO_LARGE,
            ERR_UNKNOWN,
        ]
        assert len(set(constants)) == len(constants)
