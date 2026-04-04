# Vision Modal in Chat + GUI Automation in Browser Tab

**Issue:** #1242
**Date:** 2026-02-27

## Overview

Restructure vision/multimodal features: move image analysis into a chat input modal, embed GUI automation into the Browser tab panel, and remove the standalone `/vision` route.

## Part 1: Vision Image Analysis Modal in Chat Input

### New Component: `VisionAnalysisModal.vue`

Location: `src/components/chat/VisionAnalysisModal.vue`

A modal dialog containing the image analysis workflow:
- **Upload section:** drag-and-drop zone + file browser, preview thumbnail
- **Options:** Processing Intent dropdown (analysis, visual_qa, automation, content_generation) + conditional question field for Visual Q&A
- **Analyze button:** calls `POST /api/multimodal/process/image` via `VisionMultimodalApiClient`
- **Results display:** confidence score, processing time, device, description, labels, detected objects, raw JSON toggle
- **Actions:** "Send to Chat" button, "Export JSON" button

### ChatInput.vue Changes

- Add eye icon button (`fas fa-eye`) between paperclip and microphone in `.input-actions`
- `showVisionModal` ref to control modal visibility
- On "Send to Chat": emit event to parent with analysis result + file info

### ChatInterface.vue Changes

- Handle `vision-analysis-complete` event from ChatInput
- Insert two messages into the conversation:
  1. **User message:** "Analyzed image: {filename} ({intent})" with image attachment metadata
  2. **Assistant message:** Formatted analysis results (description, labels, objects with confidence, processing time)

### Data Flow

```
User clicks eye icon in chat input
  → VisionAnalysisModal opens
  → User uploads image, selects intent, optionally types question
  → User clicks "Analyze Image"
  → POST /api/multimodal/process/image (FormData: file, intent, question)
  → Results displayed in modal
  → User clicks "Send to Chat"
  → Modal closes
  → ChatInterface adds user message + assistant message to conversation
  → Messages visible in chat history
```

## Part 2: GUI Automation Panel in Browser Tab

### VisualBrowserPanel.vue Changes

- Add "Automation" toggle button in address bar row (right side)
- Collapsible right side panel (30-40% width) containing `GUIAutomationControls`
- Panel slides in/out with CSS transition
- Layout: screenshot viewport shrinks when panel is open

```
┌──────────────────────────────────────────────────┐
│ ◄ ► ↻  [URL bar]        [Go] [📷] [🤖 Automate]│
├──────────────────────────────┬───────────────────┤
│                              │ GUI Automation    │
│   Browser Screenshot         │ Opportunities     │
│   (flex: 1)                  │ (width: 360px)    │
│                              │ (collapsible)     │
└──────────────────────────────┴───────────────────┘
```

### GUIAutomationControls.vue

Reused as-is from `src/components/vision/`. No changes needed — it independently fetches automation opportunities from `GET /api/vision/automation-opportunities`.

## Part 3: Remove /vision Route

### Files to Delete

| File | Reason |
|------|--------|
| `src/views/VisionView.vue` | Container view with sidebar nav — no longer needed |
| `src/components/vision/VisionAutomationPage.vue` | Thin wrapper — GUIAutomationControls moves to Browser tab |
| `src/components/vision/ImageAnalyzer.vue` | Logic moves to VisionAnalysisModal |
| `src/components/vision/ScreenCaptureViewer.vue` | Browser tab covers screenshot functionality |
| `src/components/vision/AnalysisResults.vue` | Screen analysis results — removed with ScreenCaptureViewer |

### Files to Keep

| File | Reason |
|------|--------|
| `src/utils/VisionMultimodalApiClient.ts` | API client still used by modal + automation panel |
| `src/components/vision/GUIAutomationControls.vue` | Reused in Browser tab panel |
| `src/components/vision/MediaGallery.vue` | May be used elsewhere |
| `src/components/vision/VideoProcessor.vue` | May be used elsewhere |

### Router Changes

- Remove `/vision` parent route and all children (`/vision/analyze`, `/vision/image`, `/vision/automation`)
- Remove Vision nav link from `App.vue` sidebar

### Cleanup

- Remove any imports of deleted components
- Verify build passes with no dead references
