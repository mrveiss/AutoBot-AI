# Interactive Browser Control Design

**Issue:** #1416
**Date:** 2026-03-06
**Status:** Approved

## Problem

Both browser views (VisualBrowserPanel in chat, KnowledgeResearchPanel in knowledge/research)
display static screenshots from the Playwright browser on .25. Users cannot scroll, click links,
or type into forms. The browser is observation-only.

## Solution

Add interactive browser control via coordinate-based actions on the persistent `navPage` in
`playwright-server.js`. Build a shared `InteractiveScreenshot.vue` component that both panels use.

## Architecture

```
Frontend: InteractiveScreenshot.vue (NEW shared component)
  - Click -> coordinate mapping (with image scaling) -> API
  - Mousewheel -> scroll API (debounced)
  - Scroll buttons toolbar (up/down/page-up/page-down)
  - Type overlay for text input
  - Auto-refreshes screenshot after each interaction

Backend: api/playwright.py (EXTEND)
  - POST /api/playwright/interact { action, params }
  - Proxies to Browser VM navPage endpoints

Browser VM: playwright-server.js (EXTEND)
  - POST /click  { x, y }       -> mouse.click with jitter + screenshot
  - POST /scroll { deltaX, deltaY } -> mouse.wheel + screenshot
  - POST /type   { text }       -> keyboard.type + screenshot
  - POST /hover  { x, y }       -> mouse.move with jitter + screenshot
```

## Anti-Detection: Click Jitter

Clicks never land at exact coordinates. Server-side jitter applied:
- Random offset +/-2-5px per axis
- Slight bias away from element center (upper-left quadrant preference)
- Mimics natural mouse approach trajectory

## Browser VM Endpoints (playwright-server.js)

All endpoints operate on the persistent `navPage` (not `mcpPage`).
All return `{ success, screenshot, url, title, viewportWidth, viewportHeight }`.

### POST /click
```json
{ "x": 450, "y": 300 }
```
Applies jitter, calls `page.mouse.click(jitteredX, jitteredY)`, returns screenshot.

### POST /scroll
```json
{ "deltaX": 0, "deltaY": 300 }
```
Calls `page.mouse.wheel(deltaX, deltaY)`, waits 200ms for render, returns screenshot.

### POST /type
```json
{ "text": "search query" }
```
Calls `page.keyboard.type(text, { delay: 50 })` with human-like keystroke delay,
returns screenshot.

### POST /hover
```json
{ "x": 450, "y": 300 }
```
Applies jitter, calls `page.mouse.move(jitteredX, jitteredY)`, returns screenshot.

## Backend Proxy (api/playwright.py)

Single unified endpoint matching existing `/automation` pattern:

```python
@router.post("/interact")
async def interact(request: InteractRequest):
    # request.action: "click" | "scroll" | "type" | "hover"
    # request.params: { x, y, deltaX, deltaY, text }
    # Proxies to Browser VM: POST /{action} with params
```

## Frontend: InteractiveScreenshot.vue

### Props
- `screenshot: string | null` - base64 PNG
- `loading: boolean` - dims image during API round-trip
- `interactive: boolean` - enables/disables interaction (default true)
- `viewportWidth: number` - actual page viewport width (from API response)
- `viewportHeight: number` - actual page viewport height (from API response)

### Events
- `@interact({ action, params })` - emitted for each interaction

### Coordinate Scaling

Screenshot may be displayed smaller than actual viewport:
```
pageX = (clickX / imgElement.clientWidth) * viewportWidth
pageY = (clickY / imgElement.clientHeight) * viewportHeight
```

### Interaction Behaviors

**Click:** `@click` on image -> scale coordinates -> emit interact event.
Cursor shows `pointer` over image.

**Scroll (mousewheel):** `@wheel` with 100ms debounce -> accumulate delta ->
emit interact event. Prevents page scroll with `event.preventDefault()`.

**Scroll (buttons):** Toolbar overlay at right edge:
- Up arrow: scroll(-300)
- Down arrow: scroll(+300)
- Page Up: scroll(-viewportHeight)
- Page Down: scroll(+viewportHeight)

**Type:** Floating input appears when user presses any key while image is focused.
On Enter or blur -> emit interact event -> hide input.

**Loading:** Brief opacity dim (0.6) during API call, matching existing pattern.

### Integration

**VisualBrowserPanel.vue:** Replace `<img>` at line 264-270 with:
```html
<InteractiveScreenshot
  :screenshot="screenshot"
  :loading="loading"
  :interactive="isConnected"
  :viewport-width="viewportWidth"
  :viewport-height="viewportHeight"
  @interact="handleInteract"
/>
```

**KnowledgeResearchPanel.vue:** Replace `<img>` at line 442-448 with same component,
`interactive` bound to `isResearching`.

## Viewport Dimensions

Extend screenshot responses to include viewport size. In `playwright-server.js`,
all endpoints that return screenshots also return:
```json
{
  "viewportWidth": 1280,
  "viewportHeight": 720
}
```
Retrieved via `page.viewportSize()`.

## Phase 2 (Future): Inspect Mode

Not in scope for this implementation. Future enhancement:
- Toggle button to enter "inspect mode"
- Playwright returns clickable element bounding boxes
- Overlay transparent hotspots on screenshot
- Clicking hotspot uses CSS selector instead of coordinates

## Files Changed

### New
- `autobot-frontend/src/components/browser/InteractiveScreenshot.vue`

### Modified
- `autobot-browser-worker/playwright-server.js` - add /click, /scroll, /type, /hover endpoints
- `autobot-backend/api/playwright.py` - add /interact proxy endpoint
- `autobot-frontend/src/components/chat/VisualBrowserPanel.vue` - use InteractiveScreenshot
- `autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue` - use InteractiveScreenshot
- `autobot-frontend/src/i18n/locales/en.json` - new interaction UI strings
