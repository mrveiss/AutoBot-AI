# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for catalog_http_exceptions convenience raiser functions.

Covers raise_not_found, raise_rate_limit, raise_invalid_input, raise_internal_error.
"""

import pytest
from fastapi import HTTPException

from utils.catalog_http_exceptions import (
    raise_internal_error,
    raise_invalid_input,
    raise_not_found,
    raise_rate_limit,
)


class TestRaiseNotFound:
    """Tests for raise_not_found helper."""

    def test_raises_404(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Worker")
        assert exc_info.value.status_code == 404

    def test_detail_without_id(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Worker")
        assert exc_info.value.detail == "Worker not found"

    def test_detail_with_id(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Worker", "abc-123")
        assert exc_info.value.detail == "Worker not found: abc-123"

    def test_detail_with_none_id(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("File", None)
        assert exc_info.value.detail == "File not found"

    def test_resource_type_preserved(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Knowledge Base Entry", "entry-42")
        assert "Knowledge Base Entry" in exc_info.value.detail
        assert "entry-42" in exc_info.value.detail


class TestRaiseRateLimit:
    """Tests for raise_rate_limit helper."""

    def test_raises_429(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_rate_limit()
        assert exc_info.value.status_code == 429

    def test_detail_message(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_rate_limit()
        assert exc_info.value.detail == "Rate limit exceeded"

    def test_no_retry_after_header_when_none(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_rate_limit()
        assert exc_info.value.headers is None

    def test_retry_after_header_set(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_rate_limit(retry_after=60)
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["Retry-After"] == "60"

    def test_retry_after_zero(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_rate_limit(retry_after=0)
        assert exc_info.value.headers["Retry-After"] == "0"


class TestRaiseInvalidInput:
    """Tests for raise_invalid_input helper."""

    def test_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_invalid_input("log_level", "must be one of: DEBUG, INFO")
        assert exc_info.value.status_code == 400

    def test_detail_format(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_invalid_input("filename", "unsafe characters")
        assert exc_info.value.detail == "filename: unsafe characters"

    def test_default_reason(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_invalid_input("worker_id")
        assert exc_info.value.detail == "worker_id: invalid value"

    def test_field_in_detail(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_invalid_input("path", "does not exist")
        assert "path" in exc_info.value.detail


class TestRaiseInternalError:
    """Tests for raise_internal_error helper."""

    def test_raises_500(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_internal_error()
        assert exc_info.value.status_code == 500

    def test_detail_without_context(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_internal_error()
        assert exc_info.value.detail == "Internal server error"

    def test_detail_with_context(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_internal_error("Failed to retrieve workers")
        assert exc_info.value.detail == "Internal server error: Failed to retrieve workers"

    def test_empty_string_context(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_internal_error("")
        assert exc_info.value.detail == "Internal server error"

    def test_context_preserved(self):
        context = "Database connection refused"
        with pytest.raises(HTTPException) as exc_info:
            raise_internal_error(context)
        assert context in exc_info.value.detail
