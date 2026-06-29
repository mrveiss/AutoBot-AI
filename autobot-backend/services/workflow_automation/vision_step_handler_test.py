# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for vision workflow step execution handlers (#2397, #2601)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.workflow_automation.executor import (
    _navigate_path,
    _resolve_step_references,
)
from services.workflow_automation.vision_step_handler import (
    VISION_STEP_TYPES,
    _build_vnc_payload,
    _build_web_action_payload,
    _element_matches,
    _get_backend_url,
    execute_vision_step,
)


class TestVisionStepTypes:
    """Tests for step type constants."""

    def test_all_six_types_present(self) -> None:
        """All 6 vision node types are registered."""
        expected = {
            "vision-capture",
            "vision-find-element",
            "vision-click",
            "vision-type-text",
            "vision-ocr",
            "vision-wait",
        }
        assert VISION_STEP_TYPES == expected

    def test_frozenset_is_immutable(self) -> None:
        """VISION_STEP_TYPES is a frozenset."""
        assert isinstance(VISION_STEP_TYPES, frozenset)


class TestBuildVncPayload:
    """Tests for VNC payload construction."""

    def test_capture_payload(self) -> None:
        """vision-capture includes include_multimodal."""
        result = _build_vnc_payload("vision-capture", {"include_multimodal": False})
        assert result == {"include_multimodal": False}

    def test_find_element_payload(self) -> None:
        """vision-find-element includes element_type and min_confidence."""
        result = _build_vnc_payload("vision-find-element", {"element_type": "button"})
        assert result["element_type"] == "button"
        assert result["min_confidence"] == 0.5

    def test_ocr_payload(self) -> None:
        """vision-ocr includes region."""
        result = _build_vnc_payload("vision-ocr", {"region": [0, 0, 100, 100]})
        assert result == {"region": [0, 0, 100, 100]}

    def test_unknown_returns_empty(self) -> None:
        """Unknown step types return empty payload."""
        result = _build_vnc_payload("vision-click", {})
        assert result == {}


class TestElementMatches:
    """Tests for element search matching."""

    def test_matches_by_text(self) -> None:
        """Matches element by text content."""
        elements = [{"text": "Submit", "label": ""}]
        assert _element_matches(elements, "submit") is True

    def test_matches_by_label(self) -> None:
        """Matches element by label."""
        elements = [{"text": "", "label": "Username"}]
        assert _element_matches(elements, "user") is True

    def test_no_match(self) -> None:
        """Returns False when no element matches."""
        elements = [{"text": "Cancel", "label": "Close"}]
        assert _element_matches(elements, "submit") is False

    def test_empty_search_matches_any(self) -> None:
        """Empty search text matches any non-empty element list."""
        assert _element_matches([{"text": "any"}], "") is True

    def test_empty_elements_no_match(self) -> None:
        """Empty element list never matches."""
        assert _element_matches([], "submit") is False
        assert _element_matches([], "") is False


class TestBuildWebActionPayload:
    """Tests for web browser action payload construction."""

    def test_click_payload(self) -> None:
        """vision-click builds click action with selector."""
        result = _build_web_action_payload("vision-click", {"action": "click"}, {"selector": "#btn"})
        assert result == {"action": "click", "selector": "#btn"}

    def test_type_text_payload(self) -> None:
        """vision-type-text builds type action with selector and text."""
        result = _build_web_action_payload(
            "vision-type-text",
            {"action": "type"},
            {"selector": "#input", "text": "hello"},
        )
        assert result == {"action": "type", "selector": "#input", "text": "hello"}

    def test_wait_payload(self) -> None:
        """vision-wait builds wait_for_selector with timeout."""
        result = _build_web_action_payload(
            "vision-wait",
            {"action": "wait_for_selector"},
            {"selector": ".loaded", "timeout": 5000},
        )
        assert result["action"] == "wait_for_selector"
        assert result["selector"] == ".loaded"
        assert result["timeout"] == 5000


class TestExecuteVisionStep:
    """Tests for the main execute_vision_step dispatcher."""

    @pytest.mark.asyncio
    async def test_vnc_capture_success(self) -> None:
        """Successful VNC capture returns success=True with timing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"analysis": "screen data"}
        mock_response.raise_for_status = MagicMock()

        with patch("services.workflow_automation.vision_step_handler.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)

            result = await execute_vision_step(
                "vision-capture",
                {"target": "vnc"},
                backend_url="https://localhost:8443",  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
            )

        assert result["success"] is True
        assert result["step_type"] == "vision-capture"
        assert result["target"] == "vnc"
        assert "execution_time" in result

    @pytest.mark.asyncio
    async def test_web_requires_session_id(self) -> None:
        """Web target without browser_session_id returns success=False."""
        result = await execute_vision_step(
            "vision-click",
            {"target": "web"},
            backend_url="https://localhost:8443",  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
        )
        assert result["success"] is False
        assert "browser_session_id" in result["result"]

    @pytest.mark.asyncio
    async def test_error_handling(self) -> None:
        """Exception during execution returns success=False with timing."""
        with patch("services.workflow_automation.vision_step_handler.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

            result = await execute_vision_step(
                "vision-ocr",
                {"target": "vnc"},
                backend_url="https://localhost:8443",  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
            )

        assert result["success"] is False
        assert "execution_time" in result
        assert result["step_type"] == "vision-ocr"

    @pytest.mark.asyncio
    async def test_default_target_is_vnc(self) -> None:
        """When no target specified, defaults to vnc."""
        with patch("services.workflow_automation.vision_step_handler.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.raise_for_status = MagicMock()
            mock_instance.get = AsyncMock(return_value=mock_response)

            result = await execute_vision_step("vision-click", {})

        assert result["target"] == "vnc"


class TestGetBackendUrl:
    """Tests for SSOT-based backend URL resolution (#2601)."""

    def test_get_backend_url_uses_ssot(self) -> None:
        """_get_backend_url delegates to ssot_config.backend_url."""
        with patch("services.workflow_automation.vision_step_handler.ssot_config") as mock_cfg:
            mock_cfg.backend_url = "https://192.0.2.1:8443"
            url = _get_backend_url()
        assert url == "https://192.0.2.1:8443"

    @pytest.mark.asyncio
    async def test_execute_vision_step_default_url_from_ssot(self) -> None:
        """When backend_url is omitted, execute_vision_step uses SSOT config."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        with (
            patch("services.workflow_automation.vision_step_handler.ssot_config") as mock_cfg,
            patch("services.workflow_automation.vision_step_handler.httpx.AsyncClient") as mock_client,
        ):
            mock_cfg.backend_url = "https://192.0.2.20:8443"
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)

            await execute_vision_step("vision-capture", {"target": "vnc"})

        call_url = mock_instance.post.call_args[0][0]
        assert call_url.startswith("https://192.0.2.20:8443")


class TestWebOcrPipeline:
    """Tests for the connected web OCR pipeline (#2601)."""

    @pytest.mark.asyncio
    async def test_web_ocr_calls_vision_endpoint(self) -> None:
        """Web OCR captures screenshot then POSTs to /api/vision/ocr."""
        screenshot_resp = MagicMock()
        screenshot_resp.raise_for_status = MagicMock()
        screenshot_resp.json.return_value = {"screenshot": "base64imgdata"}

        ocr_resp = MagicMock()
        ocr_resp.raise_for_status = MagicMock()
        ocr_resp.json.return_value = {"text": "Hello World", "confidence": 0.99}

        with patch("services.workflow_automation.vision_step_handler.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(side_effect=[screenshot_resp, ocr_resp])

            result = await execute_vision_step(
                "vision-ocr",
                {
                    "target": "web",
                    "browser_session_id": "sess-1",
                    "region": [0, 0, 100, 100],
                },
                backend_url="https://localhost:8443",  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
            )

        assert result["success"] is True
        ocr_call_kwargs = mock_instance.post.call_args_list[1]
        assert "/api/vision/ocr" in ocr_call_kwargs[0][0]
        sent_payload = ocr_call_kwargs[1]["json"]
        assert sent_payload["image_data"] == "base64imgdata"
        assert sent_payload["region"] == [0, 0, 100, 100]


class TestNavigatePath:
    """Tests for the path navigation helper (#2601)."""

    def test_simple_key(self) -> None:
        """Navigates a single-level key."""
        assert _navigate_path({"a": 1}, "a") == 1

    def test_nested_key(self) -> None:
        """Navigates dot-separated nested keys."""
        data = {"result": {"elements": [{"id": "btn"}]}}
        assert _navigate_path(data, "result.elements[0].id") == "btn"

    def test_array_index(self) -> None:
        """Navigates array index in path."""
        data = {"items": ["x", "y", "z"]}
        assert _navigate_path(data, "items[1]") == "y"

    def test_missing_key_returns_none(self) -> None:
        """Missing key returns None rather than raising."""
        assert _navigate_path({"a": 1}, "b") is None

    def test_out_of_range_index_returns_none(self) -> None:
        """Out-of-range array index returns None."""
        assert _navigate_path({"items": [1]}, "items[5]") is None


class TestResolveStepReferences:
    """Tests for step config reference resolution (#2601)."""

    def test_simple_reference_resolved(self) -> None:
        """${steps.s1.result.elements[0].id} resolves from step_results."""
        step_results = {"s1": {"result": {"elements": [{"id": "btn-42"}]}}}
        config = {"target_element": "${steps.s1.result.elements[0].id}"}
        resolved = _resolve_step_references(config, step_results)
        assert resolved["target_element"] == "btn-42"

    def test_no_reference_passes_through(self) -> None:
        """Non-reference strings pass through unchanged."""
        config = {"selector": "#my-button", "timeout": 5000}
        resolved = _resolve_step_references(config, {})
        assert resolved == {"selector": "#my-button", "timeout": 5000}

    def test_unknown_step_id_resolves_to_none(self) -> None:
        """Single reference to an unknown step_id resolves to None (raw navigated value)."""
        config = {"coord": "${steps.missing.x}"}
        resolved = _resolve_step_references(config, {})
        assert resolved["coord"] is None

    def test_multiple_references_in_single_value(self) -> None:
        """Multiple ${steps.*} tokens in one string value are all substituted. (#2632)"""
        step_results = {"s1": {"result": {"x": 10, "y": 20}}}
        config = {"label": "${steps.s1.result.x},${steps.s1.result.y}"}
        resolved = _resolve_step_references(config, step_results)
        assert resolved["label"] == "10,20"

    def test_unresolved_reference_kept_as_is(self) -> None:
        """Unknown step_id inside a multi-ref string keeps the original token. (#2632)"""
        config = {"label": "${steps.unknown.foo},suffix"}
        resolved = _resolve_step_references(config, {})
        assert resolved["label"] == "${steps.unknown.foo},suffix"

    def test_non_string_values_unchanged(self) -> None:
        """Non-string config values (int, list, dict) are not modified."""
        config = {"count": 3, "tags": ["a", "b"]}
        resolved = _resolve_step_references(config, {})
        assert resolved == {"count": 3, "tags": ["a", "b"]}
