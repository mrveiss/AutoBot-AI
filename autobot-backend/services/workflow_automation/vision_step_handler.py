# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Vision workflow step execution handlers (#2397, #2601).

Routes vision node types to the appropriate backend API endpoint
based on the step's target property (vnc or web).
"""

import asyncio
import time
from typing import Any

import httpx

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from autobot_shared.ssot_config import config as ssot_config

# TLS verification for outbound calls to internal vision/browser services.
# Set AUTOBOT_SKIP_TLS_VERIFY=true ONLY in dev/test environments that use
# self-signed certificates.  Production must leave this unset (#2852).
_VERIFY_TLS = config.skip_tls_verify.lower() != "true"

logger = get_logger(__name__)

# Map vision node types to their VNC API endpoints
_VNC_ENDPOINT: dict[str, str] = {
    "vision-capture": "/api/vision/analyze",
    "vision-find-element": "/api/vision/elements",
    "vision-click": "/api/vision/automation-opportunities",
    "vision-type-text": "/api/vision/automation-opportunities",
    "vision-ocr": "/api/vision/ocr",
    "vision-wait": "/api/vision/elements",
}

VISION_STEP_TYPES: frozenset[str] = frozenset(_VNC_ENDPOINT.keys())

# Vision steps that use GET rather than POST against the VNC API
_VNC_GET_STEPS: frozenset[str] = frozenset({"vision-click", "vision-type-text"})


def _get_backend_url() -> str:
    """Return the backend base URL from SSOT config (#2601)."""
    return ssot_config.backend_url


async def execute_vision_step(
    step_type: str,
    step_config: dict[str, Any],
    backend_url: str | None = None,
) -> dict[str, Any]:
    """Execute a vision workflow step by routing to the appropriate API.

    Args:
        step_type: One of the VISION_STEP_TYPES (e.g. "vision-capture").
        step_config: Step configuration from the workflow definition.
            Expected keys: target ("vnc" or "web"), plus type-specific params.
        backend_url: Backend base URL. Defaults to SSOT config value (#2601).

    Returns:
        Execution result dict with keys: success, result, execution_time,
        step_type, target.  (#2397, #2601)
    """
    if backend_url is None:
        backend_url = _get_backend_url()
    target = step_config.get("target", "vnc")
    start = time.monotonic()

    try:
        if target == "web":
            result = await _execute_web_step(step_type, step_config, backend_url)
        else:
            result = await _execute_vnc_step(step_type, step_config, backend_url)

        return _build_success_result(step_type, target, result, start)
    except Exception as exc:
        logger.error("Vision step %s/%s failed: %s", step_type, target, exc)
        return _build_error_result(step_type, target, exc, start)


def _build_success_result(step_type: str, target: str, result: dict, start: float) -> dict[str, Any]:
    """Build the standard success result envelope."""
    return {
        "success": True,
        "result": result,
        "execution_time": round(time.monotonic() - start, 3),
        "step_type": step_type,
        "target": target,
    }


def _build_error_result(step_type: str, target: str, exc: Exception, start: float) -> dict[str, Any]:
    """Build the standard error result envelope."""
    return {
        "success": False,
        "result": str(exc),
        "execution_time": round(time.monotonic() - start, 3),
        "step_type": step_type,
        "target": target,
    }


async def _execute_vnc_step(step_type: str, config: dict[str, Any], backend_url: str) -> dict:
    """Execute a vision step via the VNC vision API."""
    endpoint = _VNC_ENDPOINT.get(step_type)
    if not endpoint:
        raise ValueError(f"Unknown vision step type: {step_type}")

    async with httpx.AsyncClient(verify=_VERIFY_TLS, timeout=30.0) as client:
        if step_type == "vision-wait":
            payload = _build_vnc_payload(step_type, config)
            return await _poll_vnc_element(client, backend_url, endpoint, payload, config)

        if step_type in _VNC_GET_STEPS:
            response = await client.get(f"{backend_url}{endpoint}")
        else:
            payload = _build_vnc_payload(step_type, config)
            response = await client.post(f"{backend_url}{endpoint}", json=payload)

        response.raise_for_status()
        return response.json()


def _build_vnc_payload(step_type: str, config: dict[str, Any]) -> dict:
    """Build API payload from step configuration."""
    if step_type == "vision-capture":
        return {"include_multimodal": config.get("include_multimodal", True)}
    if step_type in ("vision-find-element", "vision-wait"):
        return {
            "element_type": config.get("element_type"),
            "min_confidence": config.get("min_confidence", 0.5),
        }
    if step_type == "vision-ocr":
        return {"region": config.get("region")}
    return {}


async def _poll_vnc_element(
    client: httpx.AsyncClient,
    backend_url: str,
    endpoint: str,
    payload: dict,
    config: dict[str, Any],
) -> dict:
    """Poll the vision elements endpoint until the target element appears or timeout."""
    timeout = float(config.get("timeout", 10))
    interval = float(config.get("poll_interval", 1.0))
    search_text = config.get("search_text", "")
    elapsed = 0.0

    while elapsed < timeout:
        response = await client.post(f"{backend_url}{endpoint}", json=payload)
        if response.status_code == 200:
            data = response.json()
            elements = data.get("elements", [])
            if _element_matches(elements, search_text):
                return {
                    "found": True,
                    "elements": elements,
                    "elapsed": round(elapsed, 2),
                }
        await asyncio.sleep(interval)
        elapsed += interval

    return {"found": False, "elapsed": round(elapsed, 2), "timeout": timeout}


def _element_matches(elements: list, search_text: str) -> bool:
    """Return True if any element matches the search criteria."""
    if not search_text:
        return len(elements) > 0
    needle = search_text.lower()
    return any(needle in str(e.get("text", "")).lower() or needle in str(e.get("label", "")).lower() for e in elements)


# ---------------------------------------------------------------------------
# Web (browser) step execution
# ---------------------------------------------------------------------------

_WEB_ACTION_MAP: dict[str, dict] = {
    "vision-capture": {"action": "screenshot"},
    "vision-find-element": {"action": "evaluate"},
    "vision-click": {"action": "click"},
    "vision-type-text": {"action": "type"},
    "vision-wait": {"action": "wait_for_selector"},
}


async def _execute_web_step(step_type: str, config: dict[str, Any], backend_url: str) -> dict:
    """Execute a vision step via the browser automation API."""
    session_id = config.get("browser_session_id")
    if not session_id:
        raise ValueError("browser_session_id required for web target vision steps")

    if step_type == "vision-ocr":
        return await _web_ocr_step(session_id, config, backend_url)

    action_base = _WEB_ACTION_MAP.get(step_type)
    if not action_base:
        raise ValueError(f"No web handler for step type: {step_type}")

    action_payload = _build_web_action_payload(step_type, action_base, config)

    async with httpx.AsyncClient(verify=_VERIFY_TLS, timeout=30.0) as client:
        response = await client.post(
            f"{backend_url}/api/research-browser/session/action",
            json={"session_id": session_id, **action_payload},
        )
        response.raise_for_status()
        return response.json()


def _build_web_action_payload(step_type: str, action_base: dict, config: dict[str, Any]) -> dict:
    """Build browser action payload for a given step type."""
    payload = dict(action_base)
    if step_type == "vision-find-element":
        selector = config.get("selector", "body")
        payload["script"] = f"document.querySelector('{selector}')"
    elif step_type == "vision-click":
        payload["selector"] = config.get("selector", "")
    elif step_type == "vision-type-text":
        payload["selector"] = config.get("selector", "")
        payload["text"] = config.get("text", "")
    elif step_type == "vision-wait":
        payload["selector"] = config.get("selector", "")
        payload["timeout"] = config.get("timeout", 10000)
    return payload


async def _web_ocr_step(session_id: str, config: dict[str, Any], backend_url: str) -> dict:
    """Capture a browser screenshot then run OCR via the vision pipeline (#2601).

    Two-stage pipeline:
      1. POST to /api/research-browser/session/action with action=screenshot
      2. POST the screenshot image data to /api/vision/ocr
    """
    async with httpx.AsyncClient(verify=_VERIFY_TLS, timeout=30.0) as client:
        screenshot_data = await _capture_browser_screenshot(client, session_id, backend_url)
        return await _run_ocr_on_screenshot(client, screenshot_data, config, backend_url)


async def _capture_browser_screenshot(client: httpx.AsyncClient, session_id: str, backend_url: str) -> dict:
    """POST screenshot action to the browser session API and return response JSON."""
    resp = await client.post(
        f"{backend_url}/api/research-browser/session/action",
        json={"session_id": session_id, "action": "screenshot"},
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("vision-ocr web step captured screenshot for session %s", session_id)
    return data


async def _run_ocr_on_screenshot(
    client: httpx.AsyncClient,
    screenshot_data: dict,
    config: dict[str, Any],
    backend_url: str,
) -> dict:
    """POST screenshot image data to /api/vision/ocr and return OCR result."""
    ocr_payload = {
        "image_data": screenshot_data.get("screenshot", ""),
        "region": config.get("region"),
    }
    ocr_resp = await client.post(f"{backend_url}/api/vision/ocr", json=ocr_payload)
    ocr_resp.raise_for_status()
    return ocr_resp.json()
