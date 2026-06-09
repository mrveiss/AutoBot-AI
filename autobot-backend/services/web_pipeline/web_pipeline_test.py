# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for services/web_pipeline — Phase 1 (XHRInterceptor + AccessibilitySnapshot).

Coverage:
  XHRInterceptor
  - generate_intercept_script() returns non-empty JS string containing key markers
  - generate_intercept_script() is idempotent (no mutable state)
  - collect_results() parses a well-formed capture list correctly
  - collect_results() returns empty list on evaluate error
  - collect_results() skips non-dict entries gracefully
  - collect_results() preserves optional None fields
  - InterceptedRequest.succeeded is True when response received, False otherwise

  AccessibilitySnapshot
  - capture() returns None when page returns None tree
  - capture() returns None on evaluate exception
  - capture() builds a correctly structured AccessibilityNode tree
  - to_text() returns empty string for None tree
  - to_text() renders role, name, value, checked, and disabled markers
  - to_text() indents child nodes
  - find_by_role() returns empty list for None tree
  - find_by_role() returns all matching nodes (case-insensitive)
  - find_by_name() returns empty list for None tree
  - find_by_name() returns nodes whose name contains the substring (case-insensitive)
  - AccessibilityNode.to_dict() omits None fields and serialises children

Issue #1967 — Web Pipeline Engine Phase 1.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.web_pipeline.interceptor import InterceptedRequest, XHRInterceptor
from services.web_pipeline.snapshot import AccessibilityNode, AccessibilitySnapshot

# ===========================================================================
# XHRInterceptor
# ===========================================================================


class TestGenerateInterceptScript:
    """generate_intercept_script() — JS source generation."""

    def test_returns_non_empty_string(self) -> None:
        """Script must be a non-empty string."""
        script = XHRInterceptor().generate_intercept_script()
        assert isinstance(script, str)
        assert len(script) > 100

    def test_contains_fetch_patch_marker(self) -> None:
        """Script must patch window.fetch."""
        script = XHRInterceptor().generate_intercept_script()
        assert "window.fetch" in script

    def test_contains_xhr_patch_marker(self) -> None:
        """Script must patch XMLHttpRequest."""
        script = XHRInterceptor().generate_intercept_script()
        assert "XMLHttpRequest" in script

    def test_contains_capture_buffer(self) -> None:
        """Script must use the canonical capture buffer name."""
        script = XHRInterceptor().generate_intercept_script()
        assert "__autobotXHRCapture" in script

    def test_is_idempotent_guard(self) -> None:
        """Script must contain an idempotency guard."""
        script = XHRInterceptor().generate_intercept_script()
        assert "__autobotXHRCapture" in script
        # Idempotency guard: early-return if already installed
        assert "if (window.__autobotXHRCapture)" in script

    def test_two_calls_return_same_script(self) -> None:
        """Repeated calls must return identical strings."""
        interceptor = XHRInterceptor()
        assert interceptor.generate_intercept_script() == interceptor.generate_intercept_script()


class TestCollectResults:
    """collect_results() — result parsing and error handling."""

    def _make_page(self, return_value):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=return_value)
        return page

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_buffer(self) -> None:
        page = self._make_page([])
        results = await XHRInterceptor().collect_results(page)
        assert results == []

    @pytest.mark.asyncio
    async def test_parses_fetch_entry(self) -> None:
        raw = [
            {
                "url": "https://api.example.com/data",
                "method": "GET",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "response_status": 200,
                "response_headers": {"content-type": "application/json"},
                "response_body": '{"ok": true}',
                "error": None,
            }
        ]
        page = self._make_page(raw)
        results = await XHRInterceptor().collect_results(page)

        assert len(results) == 1
        req = results[0]
        assert req.url == "https://api.example.com/data"
        assert req.method == "GET"
        assert req.request_headers == {"Accept": "application/json"}
        assert req.request_body is None
        assert req.response_status == 200
        assert req.response_headers == {"content-type": "application/json"}
        assert req.response_body == '{"ok": true}'
        assert req.error is None

    @pytest.mark.asyncio
    async def test_parses_error_entry(self) -> None:
        raw = [
            {
                "url": "https://api.example.com/fail",
                "method": "POST",
                "request_headers": {},
                "request_body": "data",
                "response_status": None,
                "response_headers": {},
                "response_body": None,
                "error": "TypeError: Failed to fetch",
            }
        ]
        page = self._make_page(raw)
        results = await XHRInterceptor().collect_results(page)

        assert len(results) == 1
        req = results[0]
        assert req.error == "TypeError: Failed to fetch"
        assert req.response_status is None

    @pytest.mark.asyncio
    async def test_returns_empty_on_evaluate_exception(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=RuntimeError("context destroyed"))
        results = await XHRInterceptor().collect_results(page)
        assert results == []

    @pytest.mark.asyncio
    async def test_skips_non_dict_entries(self) -> None:
        """Non-dict entries in the capture buffer are silently skipped."""
        raw = ["bad_entry", 42, None, {"url": "https://ok.com", "method": "GET"}]
        page = self._make_page(raw)
        results = await XHRInterceptor().collect_results(page)
        # Only the valid dict entry should produce an InterceptedRequest
        assert len(results) == 1
        assert results[0].url == "https://ok.com"

    @pytest.mark.asyncio
    async def test_multiple_entries_preserved_in_order(self) -> None:
        raw = [
            {"url": "https://a.com", "method": "GET"},
            {"url": "https://b.com", "method": "POST"},
        ]
        page = self._make_page(raw)
        results = await XHRInterceptor().collect_results(page)
        assert [r.url for r in results] == ["https://a.com", "https://b.com"]

    @pytest.mark.asyncio
    async def test_uses_correct_evaluate_expression(self) -> None:
        page = self._make_page([])
        await XHRInterceptor().collect_results(page)
        page.evaluate.assert_awaited_once_with("window.__autobotXHRCapture || []")


class TestInterceptedRequest:
    """InterceptedRequest dataclass behaviour."""

    def test_succeeded_true_when_status_and_no_error(self) -> None:
        req = InterceptedRequest(url="https://x.com", method="GET", response_status=200)
        assert req.succeeded is True

    def test_succeeded_false_when_error_present(self) -> None:
        req = InterceptedRequest(url="https://x.com", method="GET", error="network error")
        assert req.succeeded is False

    def test_succeeded_false_when_no_status(self) -> None:
        req = InterceptedRequest(url="https://x.com", method="GET")
        assert req.succeeded is False

    def test_to_dict_round_trips(self) -> None:
        req = InterceptedRequest(
            url="https://x.com",
            method="PUT",
            request_headers={"X-Token": "abc"},
            request_body='{"a": 1}',
            response_status=201,
            response_headers={"location": "/x/1"},
            response_body="created",
        )
        d = req.to_dict()
        assert d["url"] == "https://x.com"
        assert d["method"] == "PUT"
        assert d["request_headers"] == {"X-Token": "abc"}
        assert d["response_status"] == 201
        assert d["response_body"] == "created"


# ===========================================================================
# AccessibilitySnapshot
# ===========================================================================


class TestCapture:
    """AccessibilitySnapshot.capture() — tree building and error handling."""

    def _make_page(self, snapshot_return):
        page = MagicMock()
        page.accessibility = MagicMock()
        page.accessibility.snapshot = AsyncMock(return_value=snapshot_return)
        return page

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_snapshot(self) -> None:
        page = self._make_page(None)
        result = await AccessibilitySnapshot().capture(page)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self) -> None:
        page = MagicMock()
        page.accessibility = MagicMock()
        page.accessibility.snapshot = AsyncMock(side_effect=RuntimeError("detached"))
        result = await AccessibilitySnapshot().capture(page)
        assert result is None

    @pytest.mark.asyncio
    async def test_builds_root_node(self) -> None:
        page = self._make_page({"role": "WebArea", "name": "Home"})
        root = await AccessibilitySnapshot().capture(page)
        assert root is not None
        assert root.role == "WebArea"
        assert root.name == "Home"

    @pytest.mark.asyncio
    async def test_builds_child_nodes(self) -> None:
        raw = {
            "role": "WebArea",
            "name": "",
            "children": [
                {"role": "button", "name": "Submit"},
                {"role": "textbox", "name": "Email"},
            ],
        }
        page = self._make_page(raw)
        root = await AccessibilitySnapshot().capture(page)
        assert root is not None
        assert len(root.children) == 2
        assert root.children[0].role == "button"
        assert root.children[0].name == "Submit"
        assert root.children[1].role == "textbox"

    @pytest.mark.asyncio
    async def test_maps_typed_attrs(self) -> None:
        raw = {
            "role": "checkbox",
            "name": "Remember me",
            "checked": True,
            "disabled": False,
            "required": True,
        }
        page = self._make_page(raw)
        root = await AccessibilitySnapshot().capture(page)
        assert root is not None
        assert root.checked is True
        assert root.disabled is False
        assert root.required is True

    @pytest.mark.asyncio
    async def test_unknown_attrs_go_to_properties(self) -> None:
        raw = {"role": "generic", "name": "", "data-custom": "val"}
        page = self._make_page(raw)
        root = await AccessibilitySnapshot().capture(page)
        assert root is not None
        assert root.properties.get("data-custom") == "val"

    @pytest.mark.asyncio
    async def test_uses_interesting_only_false(self) -> None:
        page = self._make_page(None)
        await AccessibilitySnapshot().capture(page)
        page.accessibility.snapshot.assert_awaited_once_with(interesting_only=False)


class TestToText:
    """AccessibilitySnapshot.to_text() — plain-text rendering."""

    def test_returns_empty_for_none(self) -> None:
        assert AccessibilitySnapshot().to_text(None) == ""

    def test_renders_role(self) -> None:
        node = AccessibilityNode(role="button", name="OK")
        text = AccessibilitySnapshot().to_text(node)
        assert "button" in text

    def test_renders_name_in_quotes(self) -> None:
        node = AccessibilityNode(role="button", name="OK")
        text = AccessibilitySnapshot().to_text(node)
        assert '"OK"' in text

    def test_renders_value(self) -> None:
        node = AccessibilityNode(role="textbox", name="Email", value="user@example.com")
        text = AccessibilitySnapshot().to_text(node)
        assert "user@example.com" in text

    def test_renders_checked(self) -> None:
        node = AccessibilityNode(role="checkbox", name="Accept", checked=True)
        text = AccessibilitySnapshot().to_text(node)
        assert "checked=True" in text

    def test_renders_disabled(self) -> None:
        node = AccessibilityNode(role="button", name="Save", disabled=True)
        text = AccessibilitySnapshot().to_text(node)
        assert "disabled" in text

    def test_children_indented(self) -> None:
        child = AccessibilityNode(role="button", name="Cancel")
        root = AccessibilityNode(role="WebArea", name="Page", children=[child])
        lines = AccessibilitySnapshot().to_text(root).splitlines()
        # Root at column 0, child indented
        assert lines[0].startswith("WebArea")
        assert lines[1].startswith("  ")

    def test_node_with_no_name_omits_quotes(self) -> None:
        node = AccessibilityNode(role="generic", name="")
        text = AccessibilitySnapshot().to_text(node)
        assert '"' not in text


class TestFindByRole:
    """AccessibilitySnapshot.find_by_role() — role-based search."""

    def test_returns_empty_for_none(self) -> None:
        assert AccessibilitySnapshot().find_by_role(None, "button") == []

    def test_finds_direct_match(self) -> None:
        root = AccessibilityNode(role="button", name="OK")
        results = AccessibilitySnapshot().find_by_role(root, "button")
        assert len(results) == 1
        assert results[0] is root

    def test_case_insensitive(self) -> None:
        root = AccessibilityNode(role="Button", name="OK")
        results = AccessibilitySnapshot().find_by_role(root, "button")
        assert len(results) == 1

    def test_finds_nested_nodes(self) -> None:
        child1 = AccessibilityNode(role="button", name="Save")
        child2 = AccessibilityNode(role="button", name="Cancel")
        root = AccessibilityNode(role="WebArea", name="", children=[child1, child2])
        results = AccessibilitySnapshot().find_by_role(root, "button")
        assert len(results) == 2

    def test_returns_empty_when_no_match(self) -> None:
        root = AccessibilityNode(role="WebArea", name="")
        assert AccessibilitySnapshot().find_by_role(root, "button") == []

    def test_document_order(self) -> None:
        a = AccessibilityNode(role="button", name="A")
        b = AccessibilityNode(role="button", name="B")
        root = AccessibilityNode(role="WebArea", name="", children=[a, b])
        results = AccessibilitySnapshot().find_by_role(root, "button")
        assert [r.name for r in results] == ["A", "B"]


class TestFindByName:
    """AccessibilitySnapshot.find_by_name() — name substring search."""

    def test_returns_empty_for_none(self) -> None:
        assert AccessibilitySnapshot().find_by_name(None, "Submit") == []

    def test_exact_match(self) -> None:
        root = AccessibilityNode(role="button", name="Submit")
        results = AccessibilitySnapshot().find_by_name(root, "Submit")
        assert len(results) == 1

    def test_substring_match(self) -> None:
        root = AccessibilityNode(role="button", name="Submit Form")
        results = AccessibilitySnapshot().find_by_name(root, "Form")
        assert len(results) == 1

    def test_case_insensitive(self) -> None:
        root = AccessibilityNode(role="button", name="SUBMIT")
        results = AccessibilitySnapshot().find_by_name(root, "submit")
        assert len(results) == 1

    def test_no_match_returns_empty(self) -> None:
        root = AccessibilityNode(role="button", name="OK")
        assert AccessibilitySnapshot().find_by_name(root, "Cancel") == []

    def test_finds_across_tree(self) -> None:
        child = AccessibilityNode(role="textbox", name="Email Address")
        root = AccessibilityNode(role="WebArea", name="", children=[child])
        results = AccessibilitySnapshot().find_by_name(root, "email")
        assert len(results) == 1
        assert results[0] is child


class TestAccessibilityNodeToDict:
    """AccessibilityNode.to_dict() — serialisation."""

    def test_minimal_node(self) -> None:
        node = AccessibilityNode(role="button", name="OK")
        d = node.to_dict()
        assert d["role"] == "button"
        assert d["name"] == "OK"
        # None fields should be absent
        assert "value" not in d
        assert "checked" not in d

    def test_optional_fields_included_when_set(self) -> None:
        node = AccessibilityNode(role="checkbox", name="Accept", checked=True, required=True)
        d = node.to_dict()
        assert d["checked"] is True
        assert d["required"] is True

    def test_children_serialised_recursively(self) -> None:
        child = AccessibilityNode(role="button", name="Save")
        root = AccessibilityNode(role="WebArea", name="", children=[child])
        d = root.to_dict()
        assert "children" in d
        assert d["children"][0]["role"] == "button"

    def test_empty_children_omitted(self) -> None:
        node = AccessibilityNode(role="button", name="OK")
        d = node.to_dict()
        assert "children" not in d

    def test_properties_included_when_non_empty(self) -> None:
        node = AccessibilityNode(role="generic", name="", properties={"aria-live": "polite"})
        d = node.to_dict()
        assert d["properties"] == {"aria-live": "polite"}

    def test_empty_properties_omitted(self) -> None:
        node = AccessibilityNode(role="button", name="OK", properties={})
        d = node.to_dict()
        assert "properties" not in d
