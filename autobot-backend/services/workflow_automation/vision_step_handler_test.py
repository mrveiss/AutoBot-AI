# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for vision workflow step execution handlers (#2397)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from services.workflow_automation.vision_step_handler import (
    VISION_STEP_TYPES,
    _build_vnc_payload,
    _build_web_action_payload,
    _element_matches,
    execute_vision_step,
)


class TestVisionStepTypes:
    """Tests for step type constants."""

    def test_all_six_types_present(self):
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

    def test_frozenset_is_immutable(self):
        """VISION_STEP_TYPES is a frozenset."""
        assert isinstance(VISION_STEP_TYPES, frozenset)


class TestBuildVncPayload:
    """Tests for VNC payload construction."""

    def test_capture_payload(self):
        """vision-capture includes include_multimodal."""
        result = _build_vnc_payload("vision-capture", {"include_multimodal": False})
        assert result == {"include_multimodal": False}

    def test_find_element_payload(self):
        """vision-find-element includes element_type and min_confidence."""
        result = _build_vnc_payload("vision-find-element", {"element_type": "button"})
        assert result["element_type"] == "button"
        assert result["min_confidence"] == 0.5

    def test_ocr_payload(self):
        """vision-ocr includes region."""
        result = _build_vnc_payload("vision-ocr", {"region": [0, 0, 100, 100]})
        assert result == {"region": [0, 0, 100, 100]}

    def test_unknown_returns_empty(self):
        """Unknown step types return empty payload."""
        result = _build_vnc_payload("vision-click", {})
        assert result == {}


class TestElementMatches:
    """Tests for element search matching."""

    def test_matches_by_text(self):
        """Matches element by text content."""
        elements = [{"text": "Submit", "label": ""}]
        assert _element_matches(elements, "submit") is True

    def test_matches_by_label(self):
        """Matches element by label."""
        elements = [{"text": "", "label": "Username"}]
        assert _element_matches(elements, "user") is True

    def test_no_match(self):
        """Returns False when no element matches."""
        elements = [{"text": "Cancel", "label": "Close"}]
        assert _element_matches(elements, "submit") is False

    def test_empty_search_matches_any(self):
        """Empty search text matches any non-empty element list."""
        assert _element_matches([{"text": "any"}], "") is True

    def test_empty_elements_no_match(self):
        """Empty element list never matches."""
        assert _element_matches([], "submit") is False
        assert _element_matches([], "") is False


class TestBuildWebActionPayload:
    """Tests for web browser action payload construction."""

    def test_click_payload(self):
        """vision-click builds click action with selector."""
        result = _build_web_action_payload(
            "vision-click", {"action": "click"}, {"selector": "#btn"}
        )
        assert result == {"action": "click", "selector": "#btn"}

    def test_type_text_payload(self):
        """vision-type-text builds type action with selector and text."""
        result = _build_web_action_payload(
            "vision-type-text",
            {"action": "type"},
            {"selector": "#input", "text": "hello"},
        )
        assert result == {"action": "type", "selector": "#input", "text": "hello"}

    def test_wait_payload(self):
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
    async def test_vnc_capture_success(self):
        """Successful VNC capture returns success=True with timing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"analysis": "screen data"}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "services.workflow_automation.vision_step_handler.httpx.AsyncClient"
        ) as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=mock_response)

            result = await execute_vision_step(
                "vision-capture",
                {"target": "vnc"},
                backend_url="https://localhost:8443",
            )

        assert result["success"] is True
        assert result["step_type"] == "vision-capture"
        assert result["target"] == "vnc"
        assert "execution_time" in result

    @pytest.mark.asyncio
    async def test_web_requires_session_id(self):
        """Web target without browser_session_id returns success=False."""
        result = await execute_vision_step(
            "vision-click",
            {"target": "web"},
            backend_url="https://localhost:8443",
        )
        assert result["success"] is False
        assert "browser_session_id" in result["result"]

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Exception during execution returns success=False with timing."""
        with patch(
            "services.workflow_automation.vision_step_handler.httpx.AsyncClient"
        ) as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            result = await execute_vision_step(
                "vision-ocr",
                {"target": "vnc"},
                backend_url="https://localhost:8443",
            )

        assert result["success"] is False
        assert "execution_time" in result
        assert result["step_type"] == "vision-ocr"

    @pytest.mark.asyncio
    async def test_default_target_is_vnc(self):
        """When no target specified, defaults to vnc."""
        with patch(
            "services.workflow_automation.vision_step_handler.httpx.AsyncClient"
        ) as mock_client:
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
