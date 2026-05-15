# Create an automated UI test script using the Vision module to detect and click a button on a remote VNC desktop

AutoBot's Vision module captures screenshots from a remote VNC desktop, detects UI elements (buttons, inputs, checkboxes) using computer vision, and interacts with them via simulated mouse/keyboard events — all through REST API calls.

## Full test script — detect and click a named button

```python
"""
Automated UI test: detect a named button on a VNC desktop and click it.
Uses AutoBot's Vision module (POST /api/vision/analyze) and VNC manager
(POST /vnc/click).
"""
import httpx
import time

BASE_URL = "https://autobot.example.com:8443/api"
TOKEN    = "your-jwt-token"
SESSION  = "vnc-session-001"   # Active VNC session ID

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,
)


def get_screenshot() -> bytes:
    """Capture the current VNC desktop screenshot."""
    resp = client.get("/vnc/screenshot")
    resp.raise_for_status()
    return resp.content  # PNG bytes


def find_button(button_label: str) -> dict | None:
    """
    Analyze the current screen and return the UIElement for the named button.
    Returns None if the button is not found.
    """
    resp = client.post("/vision/analyze", json={
        "session_id":         SESSION,
        "include_multimodal": False,
    })
    resp.raise_for_status()
    screen_state = resp.json()

    for element in screen_state.get("ui_elements", []):
        if (
            element.get("element_type") == "button"
            and button_label.lower() in element.get("text_content", "").lower()
        ):
            return element

    return None


def click_element(element: dict) -> bool:
    """Click the center point of a detected UI element."""
    cx, cy = element["center_point"]
    resp = client.post("/vnc/click", json={
        "x":      cx,
        "y":      cy,
        "button": "left",
    })
    return resp.json().get("status") == "success"


def test_click_button(button_label: str, retries: int = 3) -> bool:
    """Find and click a button by label; retry up to `retries` times."""
    for attempt in range(1, retries + 1):
        print(f"Attempt {attempt}/{retries}: looking for '{button_label}' button...")
        element = find_button(button_label)

        if element is None:
            print(f"  Button not found (confidence < threshold or not visible)")
            time.sleep(1)
            continue

        cx, cy = element["center_point"]
        confidence = element.get("confidence", 0)
        print(f"  Found at ({cx}, {cy}), confidence={confidence:.2f}")

        if click_element(element):
            print(f"  Clicked successfully.")
            return True
        else:
            print(f"  Click failed — retrying.")
        time.sleep(0.5)

    return False


if __name__ == "__main__":
    # Test: click the "Submit" button
    success = test_click_button("Submit")
    print("PASS" if success else "FAIL")
```

## Step-by-step breakdown

### 1. Capture a screenshot

```python
screenshot_png = client.get("/vnc/screenshot").content
# Returns raw PNG bytes of the current VNC desktop
```

### 2. Analyze the screen for UI elements

```python
screen_state = client.post("/vision/analyze", json={
    "session_id":         "vnc-session-001",
    "include_multimodal": False,
}).json()

# screen_state["ui_elements"] — list of detected elements
# screen_state["automation_opportunities"] — pre-computed recommended actions
```

### 3. Filter for buttons by label

```python
for element in screen_state["ui_elements"]:
    if element["element_type"] == "button":
        print(f"  {element['text_content']:20}  at {element['center_point']}  conf={element['confidence']:.2f}")
```

### 4. Click the target element

```python
cx, cy = element["center_point"]
client.post("/vnc/click", json={"x": cx, "y": cy, "button": "left"})
```

## `UIElement` structure

| Field | Type | Description |
|-------|------|-------------|
| `element_id` | string | Unique ID for this detected element |
| `element_type` | string | `button`, `input_field`, `checkbox`, `dropdown`, `link`, `text`, … |
| `bbox` | dict | `{x, y, width, height}` bounding box in pixels |
| `center_point` | `[x, y]` | Center of the element (use for clicks) |
| `confidence` | float | Detection confidence (0.0–1.0) |
| `text_content` | string | OCR-extracted label text |
| `possible_interactions` | list | `["click", "hover", "type", …]` |

## Vision API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /vnc/screenshot` | GET | Current VNC desktop screenshot (PNG) |
| `POST /vision/analyze` | POST | Full screen analysis — returns `ui_elements` + `automation_opportunities` |
| `POST /vision/elements` | POST | Detect elements filtered by type |
| `POST /vision/ocr` | POST | Extract text from screen or region |
| `GET /vision/automation-opportunities` | GET | Pre-computed automation recommendations |
| `GET /vision/layout` | GET | Screen layout structure analysis |

## VNC interaction endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /vnc/click` | POST | Click at `{x, y}` with `button` (`left`/`right`/`middle`) |
| `POST /vnc/type` | POST | Type a string at current focus |
| `POST /vnc/key` | POST | Send a special key (`Return`, `Tab`, `Escape`, …) |
| `POST /vnc/scroll` | POST | Scroll at position |
| `POST /vnc/drag` | POST | Drag from one point to another |

## Complete test flow — form fill and submit

```python
def fill_and_submit_form(username: str, password: str) -> bool:
    """Fill in a login form and click Submit."""
    # 1. Find and click the username field
    element = find_button("Username") or find_button("Email")
    if not element:
        return False
    client.post("/vnc/click", json={"x": element["center_point"][0],
                                    "y": element["center_point"][1]})
    client.post("/vnc/type", json={"text": username})

    # 2. Tab to password field and type
    client.post("/vnc/key", json={"key": "Tab"})
    client.post("/vnc/type", json={"text": password})

    # 3. Click Submit
    return test_click_button("Submit") or test_click_button("Login")


fill_and_submit_form("admin", "secret")
```

## Detection techniques

The Vision module uses three parallel detection methods:

| Technique | Used for |
|-----------|----------|
| **Template matching** (`cv2.matchTemplate`) | Common system UI elements (close/minimize/maximize) |
| **Geometric classifier** | Buttons (aspect ratio 0.2–5.0, area 400–50,000 px²), input fields (aspect ratio 2.0–20.0) |
| **OCR** | Extracting text labels from any detected region |

## Architecture reference

- **Vision module** — `autobot-backend/computer_vision/` (`screen_analyzer.py`, `classifiers.py`, `types.py`)
- **Vision REST API** — `autobot-backend/api/vision.py`
- **VNC interaction** — `autobot-backend/api/vnc_manager.py`
- **Workflow step handler** — `autobot-backend/services/workflow_automation/vision_step_handler.py`
