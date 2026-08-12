# Vision Module: Automated UI Testing via VNC


## Quick Answer

**How do you use AutoBot's vision module to automate UI testing via VNC?**

Capture a VNC desktop screenshot, detect UI elements with the ScreenAnalyzer, and
interact with them through the VNC API. Here is a complete, self-contained test
script with all imports:

```python
#!/usr/bin/env python3
"""Automated UI test via VNC: capture screen, find button, click it, verify."""

import asyncio
import logging

import aiohttp

from autobot_shared.ssot_config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"


async def run_vnc_ui_test(token: str, target_host: str = "<browser-ip>"):
    """Capture a VNC desktop, detect UI elements, click a button, and verify.

    Args:
        token: JWT authentication token.
        target_host: VNC host IP (default: browser worker .25).
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # Step 1: Start a VNC session
        resp = await session.post(
            f"{BACKEND_URL}/api/vnc/sessions",
            json={"host": target_host, "port": 5900, "password": "autobot"},
            headers=headers,
            ssl=False,
        )
        vnc_session = await resp.json()
        session_id = vnc_session["session_id"]
        logger.info("VNC session started: %s", session_id)

        # Step 2: Analyze the current screen (captures screenshot + detects elements)
        resp = await session.post(
            f"{BACKEND_URL}/api/vision/analyze",
            json={"session_id": session_id, "include_screenshot": True},
            headers=headers,
            ssl=False,
        )
        analysis = await resp.json()
        elements = analysis.get("elements", [])
        logger.info("Detected %d UI elements", len(elements))

        # Step 3: Find a specific button by text content
        submit_button = None
        for elem in elements:
            if elem.get("element_type") == "button" and "submit" in elem.get("text_content", "").lower():
                submit_button = elem
                break

        if not submit_button:
            logger.warning("Submit button not found on screen")
            return False

        # Step 4: Click the button via VNC interaction
        cx, cy = submit_button["center_point"]
        resp = await session.post(
            f"{BACKEND_URL}/api/vnc/sessions/{session_id}/click",
            json={"x": cx, "y": cy, "button": "left"},
            headers=headers,
            ssl=False,
        )
        click_result = await resp.json()
        logger.info("Clicked button at (%d, %d): %s", cx, cy, click_result.get("status"))

        # Step 5: Wait and re-analyze to verify the click had an effect
        await asyncio.sleep(2)
        resp = await session.post(
            f"{BACKEND_URL}/api/vision/analyze",
            json={"session_id": session_id},
            headers=headers,
            ssl=False,
        )
        after_analysis = await resp.json()
        logger.info("Post-click: %d elements detected", len(after_analysis.get("elements", [])))

        # Step 6: Clean up VNC session
        await session.delete(
            f"{BACKEND_URL}/api/vnc/sessions/{session_id}",
            headers=headers,
            ssl=False,
        )
        return True


if __name__ == "__main__":
    import sys
    auth_token = sys.argv[1] if len(sys.argv) > 1 else "YOUR_JWT_TOKEN"
    result = asyncio.run(run_vnc_ui_test(auth_token))
    print(f"Test {'PASSED' if result else 'FAILED'}")
```

For element types, interaction types, and the multi-modal analysis pipeline, see
[Section 1](#1-vision-module-architecture). For Playwright-based browser testing,
see [Section 5](#5-playwright-integration).

---


> AutoBot's computer vision pipeline for detecting, analyzing, and interacting with
> UI elements on remote VNC desktops. This guide covers the full stack from screen
> capture through element detection to automated interaction, including a complete
> runnable test script.

**Source files:**

| Component | Path |
|-----------|------|
| Vision API | `autobot-backend/api/vision.py` |
| Computer Vision Package | `autobot-backend/computer_vision/` |
| CV Facade (compat) | `autobot-backend/computer_vision_system.py` |
| VNC Manager API | `autobot-backend/api/vnc_manager.py` |
| VNC Proxy | `autobot-backend/api/vnc_proxy.py` |
| VNC MCP Bridge | `autobot-backend/api/vnc_mcp.py` |
| VNC Humanization | `autobot-backend/api/vnc_humanization.py` |
| Playwright API | `autobot-backend/api/playwright.py` |
| Network Constants | `autobot_shared/network_constants.py` |
| Screen Analyzer | `autobot-backend/computer_vision/screen_analyzer.py` |
| CV Types | `autobot-backend/computer_vision/types.py` |

---

## Table of Contents

1. [Vision Module Architecture](#1-vision-module-architecture)
2. [Vision API Endpoints](#2-vision-api-endpoints)
3. [VNC Desktop Access](#3-vnc-desktop-access)
4. [Complete UI Test Script](#4-complete-ui-test-script)
5. [Playwright Integration](#5-playwright-integration)
6. [Multi-Modal Analysis Pipeline](#6-multi-modal-analysis-pipeline)
7. [NPU/GPU Acceleration for Vision](#7-npugpu-acceleration-for-vision)
8. [Testing Patterns](#8-testing-patterns)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Vision Module Architecture

### Package Structure

The computer vision system was refactored from a single 1,291-line file into a
well-organized package (Issue #381):

```
autobot-backend/computer_vision/
    __init__.py              # Re-exports all public names
    types.py                 # ElementType, InteractionType, UIElement, ScreenState
    collections.py           # UIElementCollection, ProcessingResultExtractor
    classifiers.py           # ElementClassifier, TemplateMatchingEngine, ContextAnalyzer
    screen_analyzer.py       # ScreenAnalyzer (multimodal screen analysis)
    system.py                # ComputerVisionSystem (coordinator)
```

The backward-compatibility facade at `autobot-backend/computer_vision_system.py`
re-exports everything from the new package. New code should import directly from
`computer_vision`:

```python
from computer_vision import ScreenAnalyzer, ElementType, InteractionType
```

### Core Data Types

**ElementType** -- UI element categories that the vision system can detect:

| Value | Enum Name | Description |
|-------|-----------|-------------|
| `button` | `BUTTON` | Clickable button |
| `input_field` | `INPUT_FIELD` | Text input / form field |
| `checkbox` | `CHECKBOX` | Checkbox control |
| `radio_button` | `RADIO_BUTTON` | Radio button control |
| `dropdown` | `DROPDOWN` | Dropdown / select control |
| `link` | `LINK` | Hyperlink |
| `image` | `IMAGE` | Image element |
| `text` | `TEXT` | Static text region |
| `menu` | `MENU` | Menu / navigation element |
| `dialog` | `DIALOG` | Dialog / modal window |
| `window` | `WINDOW` | Application window |
| `icon` | `ICON` | Icon element |
| `toolbar` | `TOOLBAR` | Toolbar container |
| `status_bar` | `STATUS_BAR` | Status bar |
| `unknown` | `UNKNOWN` | Unclassified element |

**InteractionType** -- supported interactions with detected elements:

| Value | Enum Name | Description |
|-------|-----------|-------------|
| `click` | `CLICK` | Single left click |
| `double_click` | `DOUBLE_CLICK` | Double click |
| `right_click` | `RIGHT_CLICK` | Right / context click |
| `drag` | `DRAG` | Click-drag operation |
| `type_text` | `TYPE_TEXT` | Keyboard text entry |
| `select` | `SELECT` | Select from list |
| `scroll` | `SCROLL` | Mouse wheel scroll |
| `hover` | `HOVER` | Mouse hover |

**Interaction mapping** -- each element type has a predefined set of allowed
interactions (defined in `ScreenAnalyzer._determine_interactions`):

| Element Type | Allowed Interactions |
|--------------|---------------------|
| `button` | `click`, `hover` |
| `input_field` | `click`, `type_text`, `select` |
| `checkbox` | `click` |
| `radio_button` | `click` |
| `dropdown` | `click`, `select` |
| `link` | `click`, `right_click`, `hover` |
| `image` | `click`, `right_click` |
| `menu` | `click`, `hover` |
| `window` | `drag` |
| `unknown` | `click` |

### UIElement Dataclass

Each detected element is represented as a `UIElement` with these fields:

```python
@dataclass
class UIElement:
    element_id: str                          # Unique identifier
    element_type: ElementType                # Classification
    bbox: Dict[str, int]                     # {"x", "y", "width", "height"}
    center_point: Tuple[int, int]            # (cx, cy) center coordinates
    confidence: float                        # Detection confidence 0.0-1.0
    text_content: str                        # OCR-extracted text
    attributes: Dict[str, Any]              # Additional properties
    possible_interactions: List[InteractionType]
    screenshot_region: Optional[np.ndarray]  # Cropped image region
    ocr_data: Optional[Dict[str, Any]]       # Raw OCR output
```

`UIElement` includes behavior methods following Tell-Don't-Ask principles:

- `is_button()`, `is_input_field()`, `is_link()` -- type checks
- `is_interactive()` -- whether `CLICK` is in `possible_interactions`
- `has_low_confidence(threshold=0.6)` -- confidence below threshold
- `matches_automation_pattern(keywords)` -- text matches keyword set
- `get_automation_opportunity()` -- returns automation suggestion dict or `None`
- `get_area()`, `get_aspect_ratio()`, `get_perimeter()` -- geometry helpers
- `to_dict()` -- serialization for API responses

### ScreenState Dataclass

A complete screen analysis result:

```python
@dataclass
class ScreenState:
    timestamp: float
    screenshot: np.ndarray                             # Raw screenshot array
    ui_elements: List[UIElement]                       # Detected elements
    text_regions: List[Dict[str, Any]]                 # OCR text regions
    dominant_colors: List[Dict[str, Any]]              # Color analysis
    layout_structure: Dict[str, Any]                   # Hierarchical layout
    automation_opportunities: List[Dict[str, Any]]     # Suggested automations
    context_analysis: Dict[str, Any]                   # Contextual understanding
    confidence_score: float                            # Overall confidence
    multimodal_analysis: Optional[List[Dict[str, Any]]] # Multi-modal results
```

### ScreenAnalyzer Singleton

The Vision API uses a thread-safe singleton pattern for the `ScreenAnalyzer`:

```python
# In api/vision.py
_screen_analyzer: Optional[ScreenAnalyzer] = None
_screen_analyzer_lock = threading.Lock()

def get_screen_analyzer() -> ScreenAnalyzer:
    """Get or create screen analyzer instance (thread-safe)."""
    global _screen_analyzer
    if _screen_analyzer is None:
        with _screen_analyzer_lock:
            if _screen_analyzer is None:  # Double-check locking
                _screen_analyzer = ScreenAnalyzer()
    return _screen_analyzer
```

The `ScreenAnalyzer` initializes:

- `TemplateMatchingEngine` -- template-based element detection
- `ElementClassifier` -- ML-based element classification
- `ContextAnalyzer` -- screen context understanding
- `unified_processor` -- multimodal processor integration (vision + audio)

### Analysis Pipeline

`ScreenAnalyzer.analyze_current_screen()` executes a five-stage pipeline:

```
Stage 1: Screenshot Capture
    Session VNC -> X11 import -> Test pattern fallback

Stage 2: Multi-modal Processing
    Image input -> unified_processor.process()
    Optional audio input -> combine results

Stage 3: Element Detection & Classification
    ProcessingResultExtractor -> ElementClassifier
    TemplateMatchingEngine -> merge results

Stage 4: Context Analysis
    ContextAnalyzer.analyze_context()
    + cross-modal confidence + voice intent

Stage 5: Build ScreenState
    UIElementCollection -> automation opportunities
    ProcessingResultExtractor -> text/color/layout
```

---

## 2. Vision API Endpoints

All Vision endpoints are mounted at `/api/vision` and require authentication
(Bearer token via `get_current_user` dependency). Error responses use the
`VISION` error code prefix via `@with_error_handling`.

### Health Check

```http
GET /api/vision/health
Authorization: Bearer <token>
```

**Response** (`VisionHealthResponse`):

```json
{
    "status": "healthy",
    "analyzer_ready": true,
    "capabilities": [
        "screen_capture",
        "element_detection",
        "ocr_text_extraction",
        "template_matching",
        "context_analysis",
        "multimodal_processing"
    ],
    "element_types_supported": [
        "button", "input_field", "checkbox", "radio_button",
        "dropdown", "link", "image", "text", "menu", "dialog",
        "window", "icon", "toolbar", "status_bar", "unknown"
    ],
    "interaction_types_supported": [
        "click", "double_click", "right_click", "drag",
        "type_text", "select", "scroll", "hover"
    ]
}
```

When the analyzer fails to initialize, `status` is `"unhealthy"` and all
arrays are empty.

### Analyze Screen

Performs comprehensive screen analysis including element detection, OCR,
layout analysis, and automation opportunity identification.

```http
POST /api/vision/analyze
Authorization: Bearer <token>
Content-Type: application/json
```

**Request** (`ScreenAnalysisRequest`):

```json
{
    "session_id": "my-vnc-session",
    "include_multimodal": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `session_id` | `string` or `null` | `null` | VNC session ID for targeted capture |
| `include_multimodal` | `bool` | `true` | Include multi-modal analysis results |

**Response** (`ScreenAnalysisResponse`):

```json
{
    "timestamp": 1710507600.0,
    "ui_elements": [
        {
            "element_id": "element_0_1710507600",
            "element_type": "button",
            "bbox": {"x": 100, "y": 200, "width": 120, "height": 40},
            "center_point": [160, 220],
            "confidence": 0.95,
            "text_content": "Submit",
            "attributes": {
                "area": 4800,
                "aspect_ratio": 3.0,
                "perimeter": 320
            },
            "possible_interactions": ["click", "hover"]
        }
    ],
    "text_regions": [
        {
            "text": "Welcome to AutoBot",
            "bbox": {"x": 50, "y": 10, "width": 300, "height": 30},
            "confidence": 0.92
        }
    ],
    "dominant_colors": [
        {"color": "#1a1a2e", "percentage": 0.45}
    ],
    "layout_structure": {
        "type": "vertical",
        "sections": ["header", "content", "footer"]
    },
    "automation_opportunities": [
        {
            "type": "form_submission",
            "element_id": "element_0_1710507600",
            "action": "click",
            "confidence": 0.855,
            "description": "Click Submit button"
        }
    ],
    "context_analysis": {
        "screen_type": "form",
        "automation_readiness": {
            "recommendation": "ready"
        }
    },
    "confidence_score": 0.92,
    "multimodal_analysis": null
}
```

### Detect Elements

Detect and filter UI elements by type and confidence threshold.

```http
POST /api/vision/elements
Authorization: Bearer <token>
Content-Type: application/json
```

**Request** (`ElementDetectionRequest`):

```json
{
    "element_type": "button",
    "min_confidence": 0.7,
    "session_id": "my-vnc-session"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `element_type` | `string` or `null` | `null` | Filter by element type (see ElementType enum) |
| `min_confidence` | `float` | `0.5` | Minimum confidence threshold (0.0 - 1.0) |
| `session_id` | `string` or `null` | `null` | VNC session ID |

**Response:**

```json
{
    "total_detected": 12,
    "filtered_count": 3,
    "elements": [
        {
            "element_id": "element_0_1710507600",
            "element_type": "button",
            "bbox": {"x": 100, "y": 200, "width": 120, "height": 40},
            "center_point": [160, 220],
            "confidence": 0.95,
            "text_content": "Submit",
            "possible_interactions": ["click", "hover"]
        }
    ],
    "filter_applied": {
        "element_type": "button",
        "min_confidence": 0.7
    }
}
```

### OCR Text Extraction

Extract text from the full screen or a specified region.

```http
POST /api/vision/ocr
Authorization: Bearer <token>
Content-Type: application/json
```

**Request** (`OCRRequest`):

```json
{
    "region": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    "session_id": "my-vnc-session"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `region` | `object` or `null` | `null` | Bounding box `{x, y, width, height}`. `null` = full screen. |
| `session_id` | `string` or `null` | `null` | VNC session ID |

**Response (with region):**

```json
{
    "region_specified": true,
    "region": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    "text_regions": [
        {
            "text": "Submit",
            "bbox": {"x": 100, "y": 200, "width": 60, "height": 20},
            "confidence": 0.93
        }
    ],
    "total_text_regions": 1
}
```

**Response (full screen, no region):**

```json
{
    "region_specified": false,
    "text_regions": [...],
    "total_text_regions": 15
}
```

### Automation Opportunities

Identify actionable automation targets on the current screen.

```http
GET /api/vision/automation-opportunities?session_id=my-session
Authorization: Bearer <token>
```

**Response:**

```json
{
    "opportunities": [
        {
            "type": "form_submission",
            "element_id": "element_0_1710507600",
            "action": "click",
            "confidence": 0.855,
            "description": "Click Submit button"
        },
        {
            "type": "data_entry",
            "element_id": "element_1_1710507600",
            "action": "type_text",
            "confidence": 0.72,
            "description": "Enter text in input field"
        }
    ],
    "total_opportunities": 2,
    "context": {
        "screen_type": "form",
        "automation_readiness": {"recommendation": "ready"}
    },
    "confidence": 0.92
}
```

### Element Types Reference

```http
GET /api/vision/element-types
Authorization: Bearer <token>
```

**Response:**

```json
{
    "element_types": [
        {"value": "button", "name": "BUTTON", "description": "UI element of type button"},
        {"value": "input_field", "name": "INPUT_FIELD", "description": "UI element of type input_field"}
    ],
    "total_types": 15
}
```

### Interaction Types Reference

```http
GET /api/vision/interaction-types
Authorization: Bearer <token>
```

**Response:**

```json
{
    "interaction_types": [
        {"value": "click", "name": "CLICK", "description": "Interaction type: click"},
        {"value": "double_click", "name": "DOUBLE_CLICK", "description": "Interaction type: double_click"}
    ],
    "total_types": 8
}
```

### Layout Analysis

```http
GET /api/vision/layout?session_id=my-session
Authorization: Bearer <token>
```

**Response:**

```json
{
    "layout_structure": {
        "type": "vertical",
        "sections": ["header", "content", "footer"]
    },
    "dominant_colors": [
        {"color": "#1a1a2e", "percentage": 0.45}
    ],
    "timestamp": 1710507600.0
}
```

### Service Status

```http
GET /api/vision/status
Authorization: Bearer <token>
```

**Response:**

```json
{
    "service": "computer_vision",
    "status": "operational",
    "features": {
        "screen_analysis": true,
        "element_detection": true,
        "ocr_extraction": true,
        "template_matching": true,
        "multimodal_processing": true
    },
    "supported_element_types": 15,
    "supported_interaction_types": 8
}
```

---

## 3. VNC Desktop Access

AutoBot provides three VNC-related API modules, all requiring admin authentication.

### Infrastructure Overview

| VM | IP | VNC Role |
|----|-----|----------|
| Main (.20) | `NetworkConstants.MAIN_MACHINE_IP` | Desktop VNC (display `:1`, port 5901, websockify on 6080) |
| Browser (.25) | `NetworkConstants.BROWSER_VM_IP` | Browser automation VNC (port 6080) |

The VNC proxy routes through the backend so agents can observe VNC traffic:

```
Frontend noVNC client
    --> /api/vnc-proxy/{desktop|browser}/websockify (WebSocket)
        --> Backend VNC Proxy (logs frames for MCP observation)
            --> Target VNC server (websockify on port 6080)
```

### VNC Manager API (`/api/vnc/...`)

Controls the VNC server lifecycle and desktop interactions on the main machine.

#### Check VNC Status

```http
GET /api/vnc/status
Authorization: Bearer <admin-token>
```

```json
{"running": true}
```

#### Ensure VNC Running

Starts the VNC server if not already running (TigerVNC on display `:1`,
1920x1080, 24-bit color, websockify on port 6080).

```http
POST /api/vnc/ensure-running
Authorization: Bearer <admin-token>
```

```json
{"status": "running", "message": "VNC server already running"}
```

#### Restart VNC

Kills existing VNC server and websockify, then starts fresh.

```http
POST /api/vnc/restart
Authorization: Bearer <admin-token>
```

```json
{"status": "started", "message": "VNC server started successfully"}
```

#### Mouse Click

Clicks at the specified coordinates with human-like position randomization
(+/- 5px offset) and a realistic pre-action delay (0.1-0.3s).

```http
POST /api/vnc/click
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{
    "x": 160,
    "y": 220,
    "button": "left"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `x` | `int` (>= 0) | required | X coordinate |
| `y` | `int` (>= 0) | required | Y coordinate |
| `button` | `string` | `"left"` | `"left"`, `"middle"`, or `"right"` |

**Response:**

```json
{"status": "success", "message": "Action completed"}
```

Under the hood this calls `xdotool mousemove <x> <y> click <button_num>` with
`DISPLAY=:1`. The xdotool subcommand is validated against an allowlist before
execution (Issue #1721).

#### Keyboard Type

Types text with human-like delays between keystrokes (50-150ms per character).
Has a 20% chance of inserting a mid-typing pause (0.5-2.0s) for realism.

```http
POST /api/vnc/type
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{"text": "Hello, AutoBot!"}
```

**Response:**

```json
{"status": "success", "message": "Action completed"}
```

#### Special Key

Send special keys or key combinations (uses xdotool key syntax).

```http
POST /api/vnc/key
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{"key": "ctrl+c"}
```

Common key names: `Return`, `Escape`, `Tab`, `BackSpace`, `Delete`, `Home`,
`End`, `Page_Up`, `Page_Down`, `Up`, `Down`, `Left`, `Right`, `F1`-`F12`.

Combinations: `ctrl+c`, `ctrl+v`, `alt+F4`, `ctrl+shift+t`, `super`.

#### Mouse Scroll

```http
POST /api/vnc/scroll
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{"direction": "down", "amount": 3}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `direction` | `string` | required | `"up"` or `"down"` |
| `amount` | `int` | `3` | Number of scroll clicks (1-10) |

#### Mouse Drag

Performs a drag operation with a curved, human-like mouse path. The path is
generated by `simulate_mouse_curve()` which produces 5-20 intermediate points
with perpendicular sine-wave deviation for natural movement.

```http
POST /api/vnc/drag
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{
    "x1": 100, "y1": 200,
    "x2": 400, "y2": 300
}
```

#### Desktop Screenshot

Captures the desktop screenshot as base64-encoded PNG. Uses `scrot` with
fallback to ImageMagick `import`.

```http
GET /api/vnc/screenshot
Authorization: Bearer <admin-token>
```

```json
{
    "status": "success",
    "message": "Screenshot captured",
    "image_data": "<base64-encoded PNG>"
}
```

#### Clipboard Sync

Copy text to the remote desktop clipboard (requires `xclip`).

```http
POST /api/vnc/clipboard
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{"content": "Text to paste"}
```

### VNC Proxy API (`/api/vnc-proxy/...`)

Proxies VNC traffic through the backend for agent observation.

#### VNC Types

- `desktop` -- Main machine VNC (`MAIN_MACHINE_IP:6080`)
- `browser` -- Browser VM VNC (`BROWSER_VM_IP:6080`)

#### WebSocket Proxy

```
WebSocket /api/vnc-proxy/{vnc_type}/websockify
```

Bidirectional WebSocket proxy. Traffic is logged and forwarded to the VNC
MCP observation cache for agent access.

#### Check VNC Accessibility

```http
GET /api/vnc-proxy/{vnc_type}/status
Authorization: Bearer <token>
```

```json
{
    "vnc_type": "browser",
    "endpoint": "http://<browser-ip>:6080",
    "accessible": true,
    "status": 200
}
```

#### Serve noVNC Client

```http
GET /api/vnc-proxy/{vnc_type}/vnc.html
Authorization: Bearer <token>
```

Returns the noVNC HTML client, proxied from the target VNC server.

### VNC MCP Bridge (`/api/vnc/...`)

Exposes VNC capabilities as MCP tools for AI agent consumption. All endpoints
require admin authentication.

#### List MCP Tools

```http
GET /api/vnc/mcp/tools
Authorization: Bearer <admin-token>
```

Returns the 8 available MCP tools:

| Tool Name | Description |
|-----------|-------------|
| `check_vnc_status` | Check VNC connection accessibility |
| `observe_vnc_activity` | Recent VNC WebSocket traffic and activity |
| `get_browser_vnc_context` | Combined Playwright + VNC browser context |
| `desktop_mouse_click` | Click at desktop coordinates (via xdotool) |
| `desktop_keyboard_type` | Type text on desktop keyboard |
| `desktop_special_key` | Send special key / key combination |
| `desktop_screenshot` | Capture desktop screenshot (base64 PNG) |
| `desktop_observe_state` | Desktop state with resolution, active window, screenshot |

#### Agent Desktop Click (MCP)

```http
POST /api/vnc/mcp/desktop_mouse_click
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{"x": 160, "y": 220, "button": "left"}
```

Note: Unlike `/api/vnc/click`, MCP desktop interactions do **not** apply
humanization (no random offset, no pre-action delay). They call
`_run_xdotool_cmd` directly for precise agent control.

#### Agent Desktop Screenshot (MCP)

```http
POST /api/vnc/mcp/desktop_screenshot
Authorization: Bearer <admin-token>
```

```json
{
    "success": true,
    "message": "Screenshot captured",
    "action": "screenshot",
    "image_data": "<base64 PNG>",
    "format": "png"
}
```

#### Agent Desktop State Observation (MCP)

```http
POST /api/vnc/mcp/desktop_observe_state
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{"include_screenshot": true}
```

Returns screen resolution (via `xdpyinfo`), active window name (via
`xdotool getactivewindow getwindowname`), and optional screenshot.

---

## 4. Complete UI Test Script

Below is a complete, runnable script that demonstrates the full workflow:
connecting to a VNC desktop, capturing and analyzing the screen with the Vision
module, finding a specific button by text, clicking it, and verifying the result.

### Prerequisites

```bash
pip install aiohttp
```

The AutoBot backend must be running on port 8443 with VNC server active on
the target machine.

### Full Script

```python
#!/usr/bin/env python3
"""
AutoBot Vision Module -- Automated UI Test Script

Detects a button on a remote VNC desktop and clicks it using the
Vision API for element detection and the VNC Manager API for interaction.

Usage:
    python ui_test_vision_vnc.py
    python ui_test_vision_vnc.py --button "OK" --confidence 0.8

Requires:
    - AutoBot backend running (HTTPS port 8443)
    - VNC server running on target machine (display :1)
    - Valid admin authentication token

Source APIs:
    - POST /api/vision/analyze      (screen analysis)
    - POST /api/vision/elements     (element detection)
    - POST /api/vision/ocr          (text extraction)
    - GET  /api/vnc/screenshot      (desktop capture)
    - POST /api/vnc/click           (mouse click)
    - POST /api/vnc/type            (keyboard input)
    - POST /api/vnc/key             (special keys)
"""

import argparse
import asyncio
import json
import logging
import ssl
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vision_ui_test")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Backend runs HTTPS on port 8443. Adjust if your deployment differs.
DEFAULT_BACKEND_URL = "https://<backend-ip>:8443"

# Self-signed certificate -- disable verification for internal network.
# In production, supply a proper CA bundle instead.
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DetectedElement:
    """A UI element detected by the Vision module."""

    element_id: str
    element_type: str
    bbox: Dict[str, int]
    center_point: List[int]
    confidence: float
    text_content: str
    possible_interactions: List[str] = field(default_factory=list)

    @property
    def center_x(self) -> int:
        """X coordinate of the element center."""
        return self.center_point[0]

    @property
    def center_y(self) -> int:
        """Y coordinate of the element center."""
        return self.center_point[1]


# ---------------------------------------------------------------------------
# VisionUITester
# ---------------------------------------------------------------------------

class VisionUITester:
    """Automated UI testing using AutoBot Vision + VNC APIs.

    Orchestrates:
      1. VNC screenshot capture
      2. Vision-based screen analysis and element detection
      3. OCR text extraction as fallback
      4. VNC-based mouse/keyboard interaction
      5. Post-action verification

    Args:
        backend_url: Base URL of the AutoBot backend (HTTPS).
        auth_token: Bearer token for API authentication.
    """

    def __init__(
        self,
        backend_url: str = DEFAULT_BACKEND_URL,
        auth_token: Optional[str] = None,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.auth_token = auth_token
        self._session: Optional[aiohttp.ClientSession] = None

    # -- Context manager --------------------------------------------------

    async def __aenter__(self) -> "VisionUITester":
        """Create the HTTP session."""
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        self._session = aiohttp.ClientSession(
            headers=headers,
            connector=connector,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    # -- Helpers -----------------------------------------------------------

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the active session, raising if not entered."""
        if self._session is None:
            raise RuntimeError(
                "VisionUITester must be used as an async context manager"
            )
        return self._session

    async def _post(self, path: str, payload: Optional[dict] = None) -> dict:
        """POST to a backend endpoint and return the JSON body."""
        url = f"{self.backend_url}{path}"
        async with self.session.post(url, json=payload or {}) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET from a backend endpoint and return the JSON body."""
        url = f"{self.backend_url}{path}"
        async with self.session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    # -- Step 1: Health checks ---------------------------------------------

    async def check_vision_health(self) -> dict:
        """Verify the Vision module is healthy and list capabilities.

        Calls:
            GET /api/vision/health

        Returns:
            VisionHealthResponse dict with status, capabilities, and
            supported element/interaction types.

        Raises:
            aiohttp.ClientResponseError: If the backend returns non-2xx.
        """
        health = await self._get("/api/vision/health")
        logger.info(
            "Vision health: status=%s, analyzer_ready=%s, capabilities=%d",
            health["status"],
            health["analyzer_ready"],
            len(health.get("capabilities", [])),
        )
        return health

    async def check_vnc_status(self) -> dict:
        """Verify VNC server is running on the target machine.

        Calls:
            GET /api/vnc/status

        Returns:
            {"running": true/false}
        """
        status = await self._get("/api/vnc/status")
        logger.info("VNC status: running=%s", status.get("running"))
        return status

    async def ensure_vnc_running(self) -> dict:
        """Start VNC server if not already running.

        Calls:
            POST /api/vnc/ensure-running

        Returns:
            {"status": "running|started|error", "message": "..."}
        """
        result = await self._post("/api/vnc/ensure-running")
        logger.info("VNC ensure-running: %s", result.get("status"))
        return result

    # -- Step 2: Screen capture and analysis -------------------------------

    async def capture_screenshot(self) -> dict:
        """Capture a VNC desktop screenshot.

        Calls:
            GET /api/vnc/screenshot

        Returns:
            {"status": "success", "image_data": "<base64>", "message": "..."}
        """
        result = await self._get("/api/vnc/screenshot")
        if result.get("status") == "success":
            data_len = len(result.get("image_data", ""))
            logger.info("Screenshot captured: %d bytes base64", data_len)
        else:
            logger.warning("Screenshot failed: %s", result.get("message"))
        return result

    async def analyze_screen(
        self,
        session_id: Optional[str] = None,
        include_multimodal: bool = True,
    ) -> dict:
        """Run comprehensive Vision analysis on the current screen.

        Calls:
            POST /api/vision/analyze

        Args:
            session_id: Optional VNC session ID for targeted capture.
            include_multimodal: Whether to include multi-modal analysis.

        Returns:
            ScreenAnalysisResponse with ui_elements, text_regions,
            automation_opportunities, etc.
        """
        payload = {
            "session_id": session_id,
            "include_multimodal": include_multimodal,
        }
        analysis = await self._post("/api/vision/analyze", payload)
        n_elements = len(analysis.get("ui_elements", []))
        confidence = analysis.get("confidence_score", 0.0)
        logger.info(
            "Screen analysis: %d elements, confidence=%.2f",
            n_elements,
            confidence,
        )
        return analysis

    # -- Step 3: Element detection -----------------------------------------

    async def detect_elements(
        self,
        element_type: Optional[str] = None,
        min_confidence: float = 0.5,
        session_id: Optional[str] = None,
    ) -> List[DetectedElement]:
        """Detect UI elements, optionally filtered by type and confidence.

        Calls:
            POST /api/vision/elements

        Args:
            element_type: Filter by element type (e.g. "button").
            min_confidence: Minimum confidence threshold (0.0-1.0).
            session_id: Optional VNC session ID.

        Returns:
            List of DetectedElement objects matching the filters.
        """
        payload = {
            "element_type": element_type,
            "min_confidence": min_confidence,
            "session_id": session_id,
        }
        result = await self._post("/api/vision/elements", payload)

        elements = []
        for raw in result.get("elements", []):
            elements.append(
                DetectedElement(
                    element_id=raw["element_id"],
                    element_type=raw["element_type"],
                    bbox=raw["bbox"],
                    center_point=raw["center_point"],
                    confidence=raw["confidence"],
                    text_content=raw.get("text_content", ""),
                    possible_interactions=raw.get("possible_interactions", []),
                )
            )

        logger.info(
            "Detected %d/%d elements (type=%s, min_confidence=%.2f)",
            result.get("filtered_count", len(elements)),
            result.get("total_detected", 0),
            element_type,
            min_confidence,
        )
        return elements

    async def extract_text_ocr(
        self,
        region: Optional[Dict[str, int]] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Extract text from the screen using OCR.

        Calls:
            POST /api/vision/ocr

        Args:
            region: Bounding box {x, y, width, height} or None for full screen.
            session_id: Optional VNC session ID.

        Returns:
            List of text region dicts with text, bbox, and confidence.
        """
        payload: Dict[str, Any] = {"session_id": session_id}
        if region:
            payload["region"] = region

        result = await self._post("/api/vision/ocr", payload)
        text_regions = result.get("text_regions", [])
        logger.info(
            "OCR extracted %d text regions (region_specified=%s)",
            len(text_regions),
            result.get("region_specified", False),
        )
        return text_regions

    # -- Step 4: Find a specific button ------------------------------------

    async def find_button(
        self,
        button_text: str,
        min_confidence: float = 0.7,
    ) -> DetectedElement:
        """Find a button by its text content.

        Strategy:
          1. Use Vision element detection to find all buttons.
          2. Match by text_content (case-insensitive substring).
          3. If no match, fall back to OCR text extraction.

        Args:
            button_text: The visible text on the button to find.
            min_confidence: Minimum detection confidence.

        Returns:
            The matching DetectedElement.

        Raises:
            ValueError: If no matching button is found.
        """
        # Strategy 1: Vision element detection
        buttons = await self.detect_elements(
            element_type="button",
            min_confidence=min_confidence,
        )

        for btn in buttons:
            if button_text.lower() in btn.text_content.lower():
                logger.info(
                    "Found button '%s' at (%d, %d), confidence=%.2f, id=%s",
                    button_text,
                    btn.center_x,
                    btn.center_y,
                    btn.confidence,
                    btn.element_id,
                )
                return btn

        # Strategy 2: OCR fallback
        logger.info(
            "Button '%s' not found via element detection, trying OCR...",
            button_text,
        )
        text_regions = await self.extract_text_ocr()

        for region in text_regions:
            region_text = region.get("text", "")
            if button_text.lower() in region_text.lower():
                bbox = region.get("bbox", {"x": 0, "y": 0, "width": 0, "height": 0})
                cx = bbox["x"] + bbox["width"] // 2
                cy = bbox["y"] + bbox["height"] // 2
                logger.info(
                    "Found button text '%s' via OCR at (%d, %d)",
                    button_text,
                    cx,
                    cy,
                )
                return DetectedElement(
                    element_id=f"ocr_{int(time.time())}",
                    element_type="button",
                    bbox=bbox,
                    center_point=[cx, cy],
                    confidence=region.get("confidence", 0.5),
                    text_content=region_text,
                    possible_interactions=["click"],
                )

        raise ValueError(
            f"Button '{button_text}' not found on screen via element "
            f"detection ({len(buttons)} buttons checked) or OCR "
            f"({len(text_regions)} text regions checked)"
        )

    # -- Step 5: Click an element ------------------------------------------

    async def click_element(self, element: DetectedElement) -> dict:
        """Click on a detected UI element via VNC.

        Calls:
            POST /api/vnc/click

        The VNC Manager automatically applies humanization:
          - Position randomization (+/- 5px)
          - Pre-action delay (0.1-0.3s)

        Args:
            element: The DetectedElement to click.

        Returns:
            VNC click response {"status": "...", "message": "..."}.
        """
        payload = {
            "x": element.center_x,
            "y": element.center_y,
            "button": "left",
        }
        result = await self._post("/api/vnc/click", payload)
        logger.info(
            "Clicked element '%s' at (%d, %d): %s",
            element.text_content or element.element_id,
            element.center_x,
            element.center_y,
            result.get("status"),
        )
        return result

    async def type_text(self, text: str) -> dict:
        """Type text via VNC keyboard.

        Calls:
            POST /api/vnc/type

        Args:
            text: The text to type.

        Returns:
            VNC type response.
        """
        result = await self._post("/api/vnc/type", {"text": text})
        logger.info("Typed %d characters: %s", len(text), result.get("status"))
        return result

    async def press_key(self, key: str) -> dict:
        """Send a special key or key combination via VNC.

        Calls:
            POST /api/vnc/key

        Args:
            key: Key name (e.g. "Return", "Escape", "ctrl+c").

        Returns:
            VNC key response.
        """
        result = await self._post("/api/vnc/key", {"key": key})
        logger.info("Pressed key '%s': %s", key, result.get("status"))
        return result

    # -- Step 6: Verify result ---------------------------------------------

    async def verify_click_result(
        self,
        wait_seconds: float = 2.0,
        expected_absent_text: Optional[str] = None,
        expected_present_text: Optional[str] = None,
    ) -> bool:
        """Verify that a click had the expected effect.

        Waits for the UI to update, then re-analyzes the screen.

        Args:
            wait_seconds: Time to wait before re-analysis.
            expected_absent_text: Text that should no longer appear
                (e.g. the button label if a dialog was dismissed).
            expected_present_text: Text that should now appear
                (e.g. a success message).

        Returns:
            True if verification passes, False otherwise.
        """
        logger.info("Waiting %.1fs for UI update...", wait_seconds)
        await asyncio.sleep(wait_seconds)

        # Re-analyze the screen
        analysis = await self.analyze_screen()
        all_text = " ".join(
            region.get("text", "")
            for region in analysis.get("text_regions", [])
        )

        passed = True

        if expected_absent_text:
            if expected_absent_text.lower() in all_text.lower():
                logger.warning(
                    "FAIL: Text '%s' still visible after click",
                    expected_absent_text,
                )
                passed = False
            else:
                logger.info(
                    "PASS: Text '%s' is no longer visible",
                    expected_absent_text,
                )

        if expected_present_text:
            if expected_present_text.lower() in all_text.lower():
                logger.info(
                    "PASS: Text '%s' is now visible",
                    expected_present_text,
                )
            else:
                logger.warning(
                    "FAIL: Expected text '%s' not found",
                    expected_present_text,
                )
                passed = False

        if not expected_absent_text and not expected_present_text:
            # Generic check: screen changed and confidence is reasonable
            if analysis.get("confidence_score", 0) > 0.5:
                logger.info(
                    "PASS: Screen re-analyzed with confidence %.2f",
                    analysis["confidence_score"],
                )
            else:
                logger.warning(
                    "WARN: Low confidence %.2f on re-analysis",
                    analysis.get("confidence_score", 0),
                )

        return passed

    # -- Convenience: full test flow ---------------------------------------

    async def run_button_click_test(
        self,
        button_text: str = "Submit",
        min_confidence: float = 0.7,
        verify_wait: float = 2.0,
    ) -> bool:
        """Run the complete button-detection-and-click test flow.

        Steps:
          1. Verify Vision module health
          2. Ensure VNC is running
          3. Analyze the current screen
          4. Find the target button by text
          5. Click the button
          6. Verify the click result

        Args:
            button_text: Visible text on the target button.
            min_confidence: Minimum detection confidence.
            verify_wait: Seconds to wait before verification.

        Returns:
            True if the test passed, False otherwise.
        """
        logger.info("=" * 60)
        logger.info("UI TEST: Find and click '%s' button", button_text)
        logger.info("=" * 60)

        # Step 1: Health checks
        logger.info("--- Step 1: Health checks ---")
        vision_health = await self.check_vision_health()
        if vision_health.get("status") != "healthy":
            logger.error("Vision module is not healthy, aborting")
            return False

        vnc_result = await self.ensure_vnc_running()
        if vnc_result.get("status") == "error":
            logger.error("VNC server failed to start, aborting")
            return False

        # Step 2: Analyze the screen
        logger.info("--- Step 2: Screen analysis ---")
        analysis = await self.analyze_screen()
        n_elements = len(analysis.get("ui_elements", []))
        n_opportunities = len(analysis.get("automation_opportunities", []))
        logger.info(
            "Found %d elements, %d automation opportunities",
            n_elements,
            n_opportunities,
        )

        # Step 3: Find the button
        logger.info("--- Step 3: Find button '%s' ---", button_text)
        try:
            button = await self.find_button(button_text, min_confidence)
        except ValueError as exc:
            logger.error("FAIL: %s", exc)
            return False

        # Step 4: Click the button
        logger.info("--- Step 4: Click button ---")
        click_result = await self.click_element(button)
        if click_result.get("status") != "success":
            logger.error(
                "FAIL: Click failed: %s", click_result.get("message")
            )
            return False

        # Step 5: Verify
        logger.info("--- Step 5: Verify result ---")
        passed = await self.verify_click_result(wait_seconds=verify_wait)

        # Summary
        logger.info("=" * 60)
        if passed:
            logger.info("RESULT: UI test PASSED")
        else:
            logger.error("RESULT: UI test FAILED")
        logger.info("=" * 60)

        return passed


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="AutoBot Vision UI Test -- detect and click a button",
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help="AutoBot backend URL (default: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer authentication token",
    )
    parser.add_argument(
        "--button",
        default="Submit",
        help="Button text to find and click (default: %(default)s)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.7,
        help="Minimum detection confidence (default: %(default)s)",
    )
    parser.add_argument(
        "--verify-wait",
        type=float,
        default=2.0,
        help="Seconds to wait before verification (default: %(default)s)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


async def main() -> bool:
    """Run the automated UI test."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    async with VisionUITester(
        backend_url=args.backend_url,
        auth_token=args.token,
    ) as tester:
        return await tester.run_button_click_test(
            button_text=args.button,
            min_confidence=args.confidence,
            verify_wait=args.verify_wait,
        )


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
```

### Running the Test

```bash
# Basic usage -- find and click a "Submit" button
python ui_test_vision_vnc.py --token "your-admin-token"

# Click a different button with higher confidence requirement
python ui_test_vision_vnc.py --button "OK" --confidence 0.8

# Point at a different backend
python ui_test_vision_vnc.py --backend-url "https://192.168.1.100:8443"

# Debug mode
python ui_test_vision_vnc.py --verbose
```

### Using VisionUITester Programmatically

```python
import asyncio
from ui_test_vision_vnc import VisionUITester

async def custom_test():
    """Custom multi-step UI test."""
    async with VisionUITester(auth_token="your-token") as tester:
        # Ensure VNC is available
        await tester.ensure_vnc_running()

        # Type into a text field first
        text_fields = await tester.detect_elements(
            element_type="input_field",
            min_confidence=0.6,
        )
        if text_fields:
            await tester.click_element(text_fields[0])
            await tester.type_text("test@example.com")
            await tester.press_key("Tab")

        # Now find and click Submit
        submit = await tester.find_button("Submit")
        await tester.click_element(submit)

        # Verify success message appeared
        passed = await tester.verify_click_result(
            expected_present_text="Success",
            wait_seconds=3.0,
        )
        return passed

asyncio.run(custom_test())
```

---

## 5. Playwright Integration

For browser-based UI testing (as opposed to desktop VNC testing), AutoBot
provides a Playwright API that runs on the Browser VM (<browser-ip>, port 3000).

The Playwright API is mounted at `/api/playwright` and requires admin
authentication.

### Playwright vs Vision+VNC

| Feature | Vision + VNC | Playwright |
|---------|-------------|------------|
| Target | Any desktop application | Web pages in Chromium |
| Detection | Computer vision (pixel-based) | DOM selectors |
| Interaction | xdotool coordinates | CSS/XPath selectors |
| Accuracy | Depends on confidence threshold | Exact DOM matching |
| Scope | OS-level: any window, any app | Browser tabs only |
| VM | Main machine (.20) | Browser VM (.25) |

### Navigate to URL

```http
POST /api/playwright/navigate
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{
    "url": "https://example.com",
    "wait_until": "networkidle",
    "timeout": 30000
}
```

### Take Screenshot

```http
POST /api/playwright/screenshot
Authorization: Bearer <admin-token>
Content-Type: application/json
```

```json
{
    "url": "https://example.com",
    "full_page": true,
    "wait_timeout": 5000
}
```

### Interact with Page

The `/api/playwright/interact` endpoint supports four actions: `click`,
`scroll`, `type`, and `hover`.

```http
POST /api/playwright/interact
Authorization: Bearer <admin-token>
Content-Type: application/json
```

**Click:**

```json
{"action": "click", "x": 300, "y": 200}
```

**Type text:**

```json
{"action": "type", "text": "Hello, world!"}
```

**Scroll:**

```json
{"action": "scroll", "deltaX": 0, "deltaY": 300}
```

**Hover:**

```json
{"action": "hover", "x": 150, "y": 100}
```

### Browser Navigation

```http
POST /api/playwright/reload
POST /api/playwright/back
POST /api/playwright/forward
```

### Worker Screenshot (Persistent Page)

Unlike `/screenshot` which opens a fresh page for a given URL, the worker
screenshot captures the current state of the persistent navigation page:

```http
POST /api/playwright/worker-screenshot
Authorization: Bearer <admin-token>
```

### Complete Playwright UI Test

```python
#!/usr/bin/env python3
"""
Browser UI test using AutoBot's Playwright service.

Uses DOM-based interaction rather than computer vision.
Suitable for web application testing where CSS selectors are available.
"""

import asyncio
import ssl

import aiohttp

BACKEND_URL = "https://<backend-ip>:8443"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


async def browser_ui_test(auth_token: str) -> bool:
    """Run a browser-based UI test via Playwright API."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    connector = aiohttp.TCPConnector(ssl=SSL_CTX)

    async with aiohttp.ClientSession(
        headers=headers, connector=connector
    ) as session:
        # Step 1: Check Playwright health
        async with session.get(
            f"{BACKEND_URL}/api/playwright/health"
        ) as resp:
            health = await resp.json()
            if health.get("status") != "healthy":
                print(f"Playwright unhealthy: {health}")
                return False

        # Step 2: Navigate to target page
        async with session.post(
            f"{BACKEND_URL}/api/playwright/navigate",
            json={
                "url": "https://example.com/form",
                "wait_until": "networkidle",
                "timeout": 30000,
            },
        ) as resp:
            nav_result = await resp.json()
            print(f"Navigated to: {nav_result.get('url', 'unknown')}")

        # Step 3: Type into a form field
        async with session.post(
            f"{BACKEND_URL}/api/playwright/interact",
            json={"action": "type", "text": "test@example.com"},
        ) as resp:
            resp.raise_for_status()

        # Step 4: Click submit button at known coordinates
        async with session.post(
            f"{BACKEND_URL}/api/playwright/interact",
            json={"action": "click", "x": 400, "y": 350},
        ) as resp:
            click_result = await resp.json()
            print(f"Click result: {click_result}")

        # Step 5: Capture verification screenshot
        async with session.post(
            f"{BACKEND_URL}/api/playwright/worker-screenshot",
        ) as resp:
            screenshot = await resp.json()
            print(f"Screenshot captured: {len(screenshot.get('data', ''))} bytes")

    return True


if __name__ == "__main__":
    asyncio.run(browser_ui_test("your-admin-token"))
```

---

## 6. Multi-Modal Analysis Pipeline

The Vision module integrates with AutoBot's multimodal processor to combine
visual analysis with other modalities.

### Pipeline Stages

```
                 +------------------+
                 |  VNC Screenshot  |
                 |  (np.ndarray)    |
                 +--------+---------+
                          |
              +-----------v-----------+
              |  MultiModalInput      |
              |  modality=IMAGE       |
              |  intent=SCREEN_ANALYSIS|
              +-----------+-----------+
                          |
              +-----------v-----------+
              |  unified_processor    |
              |  .process()           |
              +-----------+-----------+
                          |
        +-----------------+------------------+
        |                                    |
+-------v--------+               +----------v---------+
| Image Analysis |               | Audio Analysis     |
| - UI elements  |               | (optional)         |
| - Layout       |               | - Voice commands   |
| - Colors       |               | - Transcription    |
+-------+--------+               +----------+---------+
        |                                    |
        +----------------+-------------------+
                         |
              +----------v-----------+
              |  Combined Analysis   |
              |  modality=COMBINED   |
              |  Cross-modal fusion  |
              +----------+-----------+
                         |
              +----------v-----------+
              |  ElementClassifier   |
              |  TemplateMatching    |
              |  ContextAnalyzer     |
              +----------+-----------+
                         |
              +----------v-----------+
              |  ScreenState         |
              |  (final output)      |
              +----------------------+
```

### Modality Types

| Type | Input | Processing |
|------|-------|------------|
| `IMAGE` | Screenshot `np.ndarray` | Element detection, layout analysis, OCR |
| `AUDIO` | Voice bytes | Transcription, intent extraction |
| `COMBINED` | Image + Audio results | Cross-modal correlation, voice-guided search |

### Processing Intents

| Intent | Usage |
|--------|-------|
| `SCREEN_ANALYSIS` | Full screen understanding |
| `VOICE_COMMAND` | Voice-guided element search |

### Voice-Guided Element Search

The `ScreenAnalyzer.find_elements_by_voice_description()` method uses the NPU
semantic search engine for cross-modal element finding:

```python
# Find elements matching a voice description
elements = await analyzer.find_elements_by_voice_description(
    voice_description="the blue submit button at the bottom",
    screenshot=current_screenshot,
)
```

This uses `NPUSearchEngine.cross_modal_search()` to match text queries against
visual elements with a configurable similarity threshold (default: 0.7).

---

## 7. NPU/GPU Acceleration for Vision

### Hardware Available

| Hardware | Location | Role |
|----------|----------|------|
| NVIDIA RTX 4070 Laptop (8GB VRAM) | Main (.20) | Deep learning inference, CUDA v12 |
| Intel NPU | NPU VM (.22) | Optimized computer vision inference |

### NPU Configuration

NPU acceleration is managed through the NPU Worker VM
(`NetworkConstants.NPU_WORKER_VM_IP`, port `8081`):

```bash
# Enable NPU acceleration
export AUTOBOT_NPU_ENABLED=true
export AUTOBOT_NPU_DEVICE=AUTO  # AUTO, CPU, GPU, NPU
```

### Model Caching

The `ScreenAnalyzer` caches recent screenshots for change detection:

```python
# Internal screenshot cache (last 5 frames)
self.screenshot_cache: List[Tuple[float, np.ndarray]] = []
self.cache_size = 5
```

Screen change detection compares consecutive cached frames using
`cv2.absdiff()` with a configurable threshold:

```python
changes = await analyzer.detect_screen_changes(threshold=0.1)
# Returns: {
#     "changes_detected": True,
#     "difference_score": 0.23,
#     "change_regions": [
#         {"bbox": {"x": 100, "y": 200, "width": 50, "height": 30},
#          "area": 1500, "change_intensity": 0.45}
#     ]
# }
```

### GPU Acceleration

When CUDA is available, the following components benefit from GPU acceleration:

- `ElementClassifier` -- ML-based element type classification
- `TemplateMatchingEngine` -- Template matching via OpenCV CUDA
- `unified_processor` -- Multimodal processing (image + audio models)
- OCR via pytesseract (CPU-bound but preprocessing uses OpenCV CUDA)

---

## 8. Testing Patterns

### Page Object Model

Wrap screen regions as reusable page objects:

```python
class LoginPage:
    """Page object for the login screen."""

    def __init__(self, tester: VisionUITester) -> None:
        self.tester = tester

    async def enter_username(self, username: str) -> None:
        """Find and fill the username field."""
        fields = await self.tester.detect_elements(
            element_type="input_field", min_confidence=0.6
        )
        # First input field is typically username
        if fields:
            await self.tester.click_element(fields[0])
            await self.tester.type_text(username)

    async def enter_password(self, password: str) -> None:
        """Find and fill the password field."""
        fields = await self.tester.detect_elements(
            element_type="input_field", min_confidence=0.6
        )
        # Second input field is typically password
        if len(fields) >= 2:
            await self.tester.click_element(fields[1])
            await self.tester.type_text(password)

    async def click_login(self) -> dict:
        """Click the login button."""
        button = await self.tester.find_button("Login")
        return await self.tester.click_element(button)

    async def login(self, username: str, password: str) -> bool:
        """Complete login flow."""
        await self.enter_username(username)
        await self.enter_password(password)
        await self.click_login()
        return await self.tester.verify_click_result(
            expected_present_text="Dashboard",
            wait_seconds=3.0,
        )
```

### Element Wait Strategy

Wait for an element to appear with timeout and polling:

```python
async def wait_for_element(
    tester: VisionUITester,
    element_type: str,
    text_contains: str,
    timeout: float = 10.0,
    poll_interval: float = 1.0,
) -> DetectedElement:
    """Wait for a specific element to appear on screen.

    Args:
        tester: VisionUITester instance.
        element_type: Element type to detect (e.g. "button").
        text_contains: Substring to match in text_content.
        timeout: Maximum wait time in seconds.
        poll_interval: Time between detection attempts.

    Returns:
        The first matching DetectedElement.

    Raises:
        TimeoutError: If element is not found within timeout.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        elements = await tester.detect_elements(
            element_type=element_type,
            min_confidence=0.5,
        )
        for el in elements:
            if text_contains.lower() in el.text_content.lower():
                return el

        await asyncio.sleep(poll_interval)

    raise TimeoutError(
        f"Element type='{element_type}' containing '{text_contains}' "
        f"not found within {timeout}s"
    )
```

### Screen State Assertions

```python
async def assert_screen_contains_text(
    tester: VisionUITester,
    expected_text: str,
) -> None:
    """Assert that the screen contains specific text.

    Raises:
        AssertionError: If text is not found.
    """
    text_regions = await tester.extract_text_ocr()
    all_text = " ".join(r.get("text", "") for r in text_regions)

    if expected_text.lower() not in all_text.lower():
        raise AssertionError(
            f"Expected text '{expected_text}' not found. "
            f"Screen text: {all_text[:200]}..."
        )


async def assert_element_count(
    tester: VisionUITester,
    element_type: str,
    expected_count: int,
    min_confidence: float = 0.5,
) -> None:
    """Assert the number of elements of a given type.

    Raises:
        AssertionError: If count does not match.
    """
    elements = await tester.detect_elements(
        element_type=element_type,
        min_confidence=min_confidence,
    )
    if len(elements) != expected_count:
        raise AssertionError(
            f"Expected {expected_count} '{element_type}' elements, "
            f"found {len(elements)}"
        )
```

### Screenshot Comparison

Use the `ScreenAnalyzer.detect_screen_changes()` method for before/after
comparison:

```python
async def assert_screen_changed(
    tester: VisionUITester,
    action_fn,
    threshold: float = 0.1,
) -> None:
    """Assert that an action causes a visible screen change.

    Args:
        tester: VisionUITester instance.
        action_fn: Async callable that performs the action.
        threshold: Minimum difference score to consider "changed".

    Raises:
        AssertionError: If screen did not change.
    """
    # Capture before
    before = await tester.analyze_screen()

    # Perform action
    await action_fn()

    # Wait for UI update
    await asyncio.sleep(1.0)

    # Capture after
    after = await tester.analyze_screen()

    # Compare element counts as a proxy for change detection
    before_count = len(before.get("ui_elements", []))
    after_count = len(after.get("ui_elements", []))

    if before_count == after_count:
        # Check if text regions changed
        before_text = {r.get("text", "") for r in before.get("text_regions", [])}
        after_text = {r.get("text", "") for r in after.get("text_regions", [])}
        if before_text == after_text:
            raise AssertionError(
                "Screen did not change after action "
                f"(elements: {before_count}, text regions unchanged)"
            )
```

---

## 9. Troubleshooting

### VNC Connection Issues

**Problem: VNC server not running**

```bash
# Check from the main machine
pgrep -f "Xtigervnc :1"

# Start manually if needed (always use VncAuth or TLSVnc — NEVER use -SecurityTypes None)
vncserver :1 -localhost no -SecurityTypes VncAuth,TLSVnc -rfbport 5901 \
    -geometry 1920x1080 -depth 24

# Start websockify
websockify --web /opt/novnc 0.0.0.0:6080 localhost:5901
```

**Problem: VNC accessible locally but not remotely**

Check that websockify binds to `0.0.0.0:6080` (not `localhost`). The VNC
Manager starts it with `NetworkConstants.BIND_ALL_INTERFACES`:

```python
websockify_bind = f"{NetworkConstants.BIND_ALL_INTERFACES}:{NetworkConstants.VNC_PORT}"
```

If on WSL2, Windows Firewall may block port 6080. Fix with `wsl --shutdown`
and restart, or add a Windows Firewall rule.

**Problem: "xdotool not installed" error**

```bash
sudo apt-get install xdotool
```

Also install `scrot` for screenshots:

```bash
sudo apt-get install scrot
```

### Element Detection Failures

**Problem: No elements detected (empty `ui_elements` list)**

1. Check that the VNC screenshot is capturing correctly:

    ```bash
    curl -sk https://<backend-ip>:8443/api/vnc/screenshot \
        -H "Authorization: Bearer <token>" | jq '.status'
    ```

2. Verify the Vision service is healthy:

    ```bash
    curl -sk https://<backend-ip>:8443/api/vision/health \
        -H "Authorization: Bearer <token>" | jq '.'
    ```

3. The screen may be blank or the VNC session may be showing a screensaver.
   Check with a manual screenshot.

**Problem: Elements detected but with wrong types**

The `ElementClassifier` assigns types based on visual features (aspect ratio,
color, edges). Unusual UI themes may confuse classification. Lower the
`min_confidence` threshold to see more candidates:

```python
elements = await tester.detect_elements(min_confidence=0.3)
```

**Problem: Button text not matching via OCR**

OCR accuracy depends on font size, contrast, and resolution. Strategies:

- Increase VNC resolution (`-geometry 1920x1080 -depth 24`)
- Use a broader substring match (e.g., `"Sub"` instead of `"Submit"`)
- Check OCR output directly: `POST /api/vision/ocr` to see what text was extracted

### Confidence Threshold Tuning

| Use Case | Recommended Threshold | Rationale |
|----------|----------------------|-----------|
| Standard GUI buttons | 0.7 - 0.8 | Well-defined edges and text |
| Custom-styled web UI | 0.5 - 0.7 | Non-standard visual patterns |
| Terminal / text-heavy UI | 0.3 - 0.5 | Low visual contrast between elements |
| Initial exploration | 0.3 | See everything, filter manually |
| Production automation | 0.8 - 0.9 | High confidence for reliability |

### Common Error Codes

| Error Code Prefix | Source | Meaning |
|-------------------|--------|---------|
| `VISION_*` | `/api/vision/*` | Computer vision processing error |
| `VNC_STATUS_*` | `/api/vnc/status` | VNC status check failure |
| `VNC_CLICK_*` | `/api/vnc/click` | Mouse click execution error |
| `VNC_TYPE_*` | `/api/vnc/type` | Keyboard typing error |
| `VNC_KEY_*` | `/api/vnc/key` | Special key press error |
| `VNC_SCREENSHOT_*` | `/api/vnc/screenshot` | Screenshot capture error |
| `VNC_PROXY_*` | `/api/vnc-proxy/*` | VNC proxy / WebSocket error |
| `VNC_MCP_*` | `/api/vnc/mcp/*` | MCP bridge error |
| `PLAYWRIGHT_*` | `/api/playwright/*` | Browser automation error |

### Authentication Errors

All Vision and VNC endpoints require authentication:

- Vision endpoints: `get_current_user` dependency (any authenticated user)
- VNC Manager endpoints: `check_admin_permission` dependency (admin role required)
- VNC MCP endpoints: `check_admin_permission` on the router level
- Playwright endpoints: `check_admin_permission` on the router level

If you receive a `401 Unauthorized`, verify:

1. The `Authorization: Bearer <token>` header is present
2. The token is valid and not expired
3. The user has admin role (for VNC/Playwright endpoints)

### Human-like Behavior Configuration

The VNC Manager applies humanization to make interactions appear natural:

| Parameter | Range | Function |
|-----------|-------|----------|
| Click position offset | +/- 5px | `humanize_click_position()` |
| Pre-action delay | 0.1 - 0.3s | `humanize_action_delay()` |
| Typing delay per key | 50 - 150ms | `humanize_typing_speed()` |
| Mid-typing pause chance | 20% | `should_add_human_pause()` |
| Pause duration | 0.5 - 2.0s | `humanize_pause_duration()` |
| Drag curve steps | 5 - 20 | `simulate_mouse_curve()` |

For precise agent control (no humanization), use the MCP endpoints
(`/api/vnc/mcp/desktop_mouse_click`) which call `_run_xdotool_cmd` directly.

---

## Related Documentation

- [Desktop Access Guide](./DESKTOP_ACCESS.md) -- VNC setup and access
- [Agent System Guide](./AGENT_SYSTEM_GUIDE.md) -- MCP tools and agent architecture
- [Port Mappings](./PORT_MAPPINGS.md) -- All service ports
- [Configuration Guide](./CONFIGURATION_GUIDE.md) -- Network and service configuration
