# Vision → Automation Integration Design

**Date:** 2026-03-25
**Issue:** #2373
**Status:** Approved
**Goal:** Consolidate the Vision/Analyze feature into the Automation page — both as embedded UI panels and as workflow builder node types.

---

## Context

The frontend currently has two separate routes:

- `/vision` — Screen analysis, video processing, media gallery, GUI automation
- `/automation` — Workflow builder, runner, templates, orchestration

The vision capabilities (screen capture, OCR, element detection) are essential building blocks for GUI automation workflows targeting VNC sessions and web pages. Having them in a separate route creates a fragmented experience. This design merges everything under `/automation`.

## Decision

**Approach A: Embed Components + Add Workflow Nodes**

Import existing vision components into `WorkflowBuilderView.vue` as new sidebar sections. Add vision-based node types to the Visual Builder canvas. Remove the `/vision` route entirely.

---

## 1. Sidebar Navigation Changes

The automation sidebar gains a new **VISION** group:

```
BUILD:         Visual Builder | Templates | Natural Language
EXECUTE:       Runner | History | GUI Automation
VISION:        Screen Analysis | Video Processing | Media Gallery
ORCHESTRATION: Visualizer | Agents
```

Each vision section renders its existing component:

| Section | Component |
|---------|-----------|
| Screen Analysis | `ScreenCaptureViewer.vue` |
| Video Processing | `VideoProcessor.vue` |
| Media Gallery | `MediaGallery.vue` |

The vision service health indicator (healthy/degraded/offline) from `VisionView.vue` is moved into the VISION group header.

The existing GUI Automation section in EXECUTE (which already uses `GUIAutomationControls.vue`) stays where it is.

## 2. Route Changes

| Action | Detail |
|--------|--------|
| **Remove** | `/vision` parent route and all 4 child routes from `router/index.ts` |
| **Delete** | `views/VisionView.vue` (sidebar container — replaced by automation sidebar) |
| **Keep** | All `components/vision/*.vue` files (reused in-place) |
| **Keep** | `VisionMultimodalApiClient.ts` (API client — unchanged) |
| **Update** | References to `/vision` in `App.vue`, `useAppStore.ts`, `VisualBrowserPanel.vue` |

## 3. Vision Workflow Nodes

Six new node types added to the Visual Builder canvas under a **Vision** category in the node palette:

| Node | Targets | Description |
|------|---------|-------------|
| **Screen Capture & Analyze** | VNC | Capture screen, run OCR + element detection + layout analysis |
| **Find UI Element** | VNC | Locate element by type/text/position with confidence threshold |
| **Click Element** | VNC, Web | Click a detected element (accepts element reference from upstream node) |
| **Type Text** | VNC, Web | Type into an input element |
| **OCR Extract** | VNC | Extract text from screen or region |
| **Wait for Element** | VNC, Web | Poll until element appears or timeout |

### Target Context

Each node has a **target** property:
- `vnc` — vision-based pixel analysis, hits `/api/vision/*` endpoints
- `web` — browser-based via Playwright worker on .25, hits browser automation endpoints

Nodes that support both targets show a toggle in their configuration panel.

### Data Flow

Nodes pass element references downstream through output ports:
- `Screen Capture & Analyze` → outputs full analysis (elements, text, layout)
- `Find UI Element` → outputs matched element(s) with coordinates, bounding box, confidence
- `Click Element` / `Type Text` → accepts element reference as input, outputs success/failure
- `OCR Extract` → outputs extracted text string
- `Wait for Element` → outputs found element or timeout error

Example workflow: `Screen Capture → Find "Login" button → Click Element → Find "Username" input → Type Text`

## 4. Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `router/index.ts` | Modify | Remove `/vision` route block (lines ~555-613) |
| `views/WorkflowBuilderView.vue` | Modify | Import 3 vision components, add VISION sidebar group, add vision health check logic |
| `views/VisionView.vue` | Delete | No longer needed — sidebar replaced by automation sidebar |
| `App.vue` | Modify | Remove `/vision` navigation link |
| `stores/useAppStore.ts` | Modify | Remove vision route references |
| `components/chat/VisualBrowserPanel.vue` | Modify | Update any `/vision` links |
| `components/workflow/WorkflowCanvas.vue` | Modify | Add 6 vision node types to node palette, node rendering, and node configuration |

## 5. What Stays Unchanged

- All `components/vision/*.vue` files — reused as-is
- `VisionMultimodalApiClient.ts` — API client unchanged
- `GUIAutomationControls.vue` — already in EXECUTE section, no change
- All backend `/api/vision/*` endpoints — no backend changes needed for UI integration
- `components/chat/VisionAnalysisModal.vue` — chat integration stays independent

## 6. Out of Scope

- Backend workflow execution engine changes (vision nodes are frontend-only in this phase)
- New backend endpoints for vision workflow steps (future work — will need `/api/workflow-automation/` step handlers)
- Video processing as a workflow node (can be added later)
- Cross-modal search / embedding fusion as workflow nodes (can be added later)
