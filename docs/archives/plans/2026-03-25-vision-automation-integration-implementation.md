# Vision → Automation Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge `/vision` route into `/automation` — embed vision panels in the sidebar and add 6 vision node types to the workflow canvas.

**Architecture:** Reuse existing vision components (`ScreenCaptureViewer`, `VideoProcessor`, `MediaGallery`) by importing them into `WorkflowBuilderView.vue`. Extend `WorkflowCanvas.vue` with 6 new vision node types. Remove `/vision` route and all references.

**Tech Stack:** Vue 3 + TypeScript, vue-router, Pinia, vue-i18n

**Issue:** #2373

---

### Task 1: Remove `/vision` route from router

**Files:**
- Modify: `autobot-frontend/src/router/index.ts:42` (VisionView import)
- Modify: `autobot-frontend/src/router/index.ts:555-613` (vision route block)

**Step 1: Remove VisionView import (line 42)**

Delete this line:
```typescript
import VisionView from '@/views/VisionView.vue'
```

**Step 2: Remove vision route block (lines 555-613)**

Delete the entire block from `// Issue #777/#1301: Vision & Multimodal AI Features (restored)` through the closing `}` and its children (the `/vision` parent route with `analyze`, `video`, `gallery`, `automation` children).

**Step 3: Verify the build compiles**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit 2>&1 | head -30`
Expected: No errors referencing VisionView or /vision routes.

**Step 4: Commit**

```bash
git add autobot-frontend/src/router/index.ts
git commit -m "feat(automation): remove /vision route (#2373)"
```

---

### Task 2: Remove `/vision` nav link from App.vue

**Files:**
- Modify: `autobot-frontend/src/App.vue:733`

**Step 1: Delete the vision nav item from the navItems array**

In `App.vue` around line 733, remove:
```typescript
{ to: '/vision', labelKey: 'nav.vision', iconPaths: ['M10 12a2 2 0 100-4 2 2 0 000 4z', 'M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z'] },
```

**Step 2: Commit**

```bash
git add autobot-frontend/src/App.vue
git commit -m "feat(automation): remove /vision nav link from App.vue (#2373)"
```

---

### Task 3: Remove `vision` from useAppStore

**Files:**
- Modify: `autobot-frontend/src/stores/useAppStore.ts:8` (TabType)
- Modify: `autobot-frontend/src/stores/useAppStore.ts:208` (routeMap)

**Step 1: Remove `'vision'` from the TabType union (line 8)**

Remove `| 'vision'` from the union type.

**Step 2: Remove `'vision': '/vision'` from routeMap (line 208)**

Delete the `'vision': '/vision'` entry.

**Step 3: Commit**

```bash
git add autobot-frontend/src/stores/useAppStore.ts
git commit -m "feat(automation): remove vision from useAppStore (#2373)"
```

---

### Task 4: Update VisualBrowserPanel.vue

**Files:**
- Modify: `autobot-frontend/src/components/chat/VisualBrowserPanel.vue`

**Step 1: Check what references `/vision`**

Run: `grep -n '/vision' autobot-frontend/src/components/chat/VisualBrowserPanel.vue`

Lines 18, 20, 47 reference vision component/API imports (`@/components/vision/`, `@/utils/VisionMultimodalApiClient`). These are NOT route references — they import components and API client, which we keep. Only update if any string literal route paths like `'/vision/analyze'` exist.

**Step 2: If no route references found, skip. Otherwise update any `/vision/...` route links to point to `/automation` with the appropriate section.**

**Step 3: Commit (only if changes were made)**

---

### Task 5: Add VISION sidebar group to WorkflowBuilderView

**Files:**
- Modify: `autobot-frontend/src/views/WorkflowBuilderView.vue`

**Step 1: Extend SectionType union (line 551)**

Change:
```typescript
type SectionType =
  | 'overview'
  | 'canvas'
  | 'templates'
  | 'natural-language'
  | 'runner'
  | 'history'
  | 'orchestration'
  | 'agents'
  | 'gui-automation';
```

To:
```typescript
type SectionType =
  | 'overview'
  | 'canvas'
  | 'templates'
  | 'natural-language'
  | 'runner'
  | 'history'
  | 'gui-automation'
  | 'screen-analysis'
  | 'video-processing'
  | 'media-gallery'
  | 'orchestration'
  | 'agents';
```

**Step 2: Add vision component imports (after the GUIAutomationControls import, line ~540)**

```typescript
import ScreenCaptureViewer from '@/components/vision/ScreenCaptureViewer.vue';
import VideoProcessor from '@/components/vision/VideoProcessor.vue';
import MediaGallery from '@/components/vision/MediaGallery.vue';
```

**Step 3: Add vision health check state (after guiAutomationLoading ref, line ~620)**

```typescript
// Vision service health (#2373)
const visionHealthStatus = ref<'healthy' | 'degraded' | 'offline'>('offline');

async function checkVisionHealth(): Promise<void> {
  try {
    const res = await visionMultimodalApiClient.getVisionHealth();
    if (res.success && res.data) {
      visionHealthStatus.value = res.data.status === 'healthy' ? 'healthy' : 'degraded';
    } else {
      visionHealthStatus.value = 'offline';
    }
  } catch {
    visionHealthStatus.value = 'offline';
  }
}
```

**Step 4: Call `checkVisionHealth()` in the existing `refreshAll` function and `onMounted`**

**Step 5: Add VISION sidebar buttons in the template**

Insert after the GUI Automation button (line ~123) and before the ORCHESTRATION divider (line ~125):

```html
<div class="category-divider">
  <span>{{ $t('workflow.views.vision') }}</span>
  <span class="health-indicator" :class="visionHealthStatus">
    {{ visionHealthStatus }}
  </span>
</div>

<button
  class="category-item"
  :class="{ active: activeSection === 'screen-analysis' }"
  @click="activeSection = 'screen-analysis'"
  role="button"
  :aria-label="$t('workflow.views.screenAnalysisAriaLabel')"
  tabindex="0"
>
  <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
      d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>
  <span>{{ $t('workflow.views.screenAnalysis') }}</span>
</button>

<button
  class="category-item"
  :class="{ active: activeSection === 'video-processing' }"
  @click="activeSection = 'video-processing'"
  role="button"
  :aria-label="$t('workflow.views.videoProcessingAriaLabel')"
  tabindex="0"
>
  <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
      d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
  </svg>
  <span>{{ $t('workflow.views.videoProcessing') }}</span>
</button>

<button
  class="category-item"
  :class="{ active: activeSection === 'media-gallery' }"
  @click="activeSection = 'media-gallery'"
  role="button"
  :aria-label="$t('workflow.views.mediaGalleryAriaLabel')"
  tabindex="0"
>
  <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
      d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
  </svg>
  <span>{{ $t('workflow.views.mediaGallery') }}</span>
</button>
```

**Step 6: Add vision content sections in the template**

Insert after the GUI Automation section (line ~458) and before the Agents section:

```html
<!-- Screen Analysis Section (#2373) -->
<section v-if="activeSection === 'screen-analysis'" class="section-screen-analysis">
  <ScreenCaptureViewer />
</section>

<!-- Video Processing Section (#2373) -->
<section v-if="activeSection === 'video-processing'" class="section-video-processing">
  <VideoProcessor />
</section>

<!-- Media Gallery Section (#2373) -->
<section v-if="activeSection === 'media-gallery'" class="section-media-gallery">
  <MediaGallery />
</section>
```

**Step 7: Add health indicator CSS to the style section**

```css
.health-indicator {
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 8px;
  text-transform: uppercase;
  font-weight: 600;
}
.health-indicator.healthy { color: #10b981; background: rgba(16, 185, 129, 0.1); }
.health-indicator.degraded { color: #f59e0b; background: rgba(245, 158, 11, 0.1); }
.health-indicator.offline { color: #6b7280; background: rgba(107, 114, 128, 0.1); }
```

**Step 8: Update sectionTitle and sectionDescription computed properties**

Add cases for new sections:
- `'screen-analysis'` → title: 'Screen Analysis', desc: 'Capture and analyze screen content'
- `'video-processing'` → title: 'Video Processing', desc: 'Process and analyze video frames'
- `'media-gallery'` → title: 'Media Gallery', desc: 'Browse captured media and analysis results'

**Step 9: Verify build**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit 2>&1 | head -30`

**Step 10: Commit**

```bash
git add autobot-frontend/src/views/WorkflowBuilderView.vue
git commit -m "feat(automation): add VISION sidebar group with screen analysis, video, gallery (#2373)"
```

---

### Task 6: Add i18n keys for vision sections

**Files:**
- Modify: i18n locale file (find with `grep -rn "workflow.views.orchestration" autobot-frontend/src/locales/`)

**Step 1: Add keys under `workflow.views`**

```json
"vision": "VISION",
"screenAnalysis": "Screen Analysis",
"screenAnalysisAriaLabel": "Screen Analysis - capture and analyze screen content",
"videoProcessing": "Video Processing",
"videoProcessingAriaLabel": "Video Processing - process and analyze video frames",
"mediaGallery": "Media Gallery",
"mediaGalleryAriaLabel": "Media Gallery - browse captured media"
```

**Step 2: Commit**

```bash
git add autobot-frontend/src/locales/
git commit -m "feat(automation): add i18n keys for vision sidebar sections (#2373)"
```

---

### Task 7: Extend WorkflowNode type with vision node types

**Files:**
- Modify: `autobot-frontend/src/composables/useWorkflowBuilder.ts:232`

**Step 1: Extend the type union on line 232**

From:
```typescript
type: 'step' | 'condition' | 'parallel' | 'loop';
```

To:
```typescript
type: 'step' | 'condition' | 'parallel' | 'loop' | 'vision-capture' | 'vision-find-element' | 'vision-click' | 'vision-type-text' | 'vision-ocr' | 'vision-wait';
```

**Step 2: Commit**

```bash
git add autobot-frontend/src/composables/useWorkflowBuilder.ts
git commit -m "feat(automation): extend WorkflowNode type with vision node types (#2373)"
```

---

### Task 8: Add vision nodes to WorkflowCanvas toolbar and rendering

**Files:**
- Modify: `autobot-frontend/src/components/workflow/WorkflowCanvas.vue`

**Step 1: Add a Vision dropdown button to the toolbar (after condition button, line ~12)**

```html
<div class="toolbar-divider"></div>
<div class="dropdown-container">
  <button class="tool-btn" @click="showVisionDropdown = !showVisionDropdown" :title="$t('workflow.canvas.addVisionNode')">
    <i class="fas fa-eye"></i> {{ $t('workflow.canvas.vision') }}
    <i class="fas fa-caret-down"></i>
  </button>
  <div v-if="showVisionDropdown" class="dropdown-menu" @mouseleave="showVisionDropdown = false">
    <button @click="addVisionNode('vision-capture')"><i class="fas fa-camera"></i> {{ $t('workflow.canvas.visionCapture') }}</button>
    <button @click="addVisionNode('vision-find-element')"><i class="fas fa-search"></i> {{ $t('workflow.canvas.visionFindElement') }}</button>
    <button @click="addVisionNode('vision-click')"><i class="fas fa-mouse-pointer"></i> {{ $t('workflow.canvas.visionClick') }}</button>
    <button @click="addVisionNode('vision-type-text')"><i class="fas fa-keyboard"></i> {{ $t('workflow.canvas.visionTypeText') }}</button>
    <button @click="addVisionNode('vision-ocr')"><i class="fas fa-font"></i> {{ $t('workflow.canvas.visionOcr') }}</button>
    <button @click="addVisionNode('vision-wait')"><i class="fas fa-clock"></i> {{ $t('workflow.canvas.visionWait') }}</button>
  </div>
</div>
```

**Step 2: Add `showVisionDropdown` ref in script**

```typescript
const showVisionDropdown = ref(false);
```

**Step 3: Extend nodeIcons (line 119)**

Replace the single-line object with:
```typescript
const nodeIcons: Record<string, string> = {
  step: 'fas fa-terminal',
  condition: 'fas fa-code-branch',
  parallel: 'fas fa-columns',
  'vision-capture': 'fas fa-camera',
  'vision-find-element': 'fas fa-search',
  'vision-click': 'fas fa-mouse-pointer',
  'vision-type-text': 'fas fa-keyboard',
  'vision-ocr': 'fas fa-font',
  'vision-wait': 'fas fa-clock',
};
```

**Step 4: Extend nodeLabels computed (line 120)**

```typescript
const nodeLabels = computed(() => ({
  step: t('workflow.canvas.stepLabel'),
  condition: t('workflow.canvas.conditionLabel'),
  parallel: t('workflow.canvas.parallelLabel'),
  'vision-capture': t('workflow.canvas.visionCapture'),
  'vision-find-element': t('workflow.canvas.visionFindElement'),
  'vision-click': t('workflow.canvas.visionClick'),
  'vision-type-text': t('workflow.canvas.visionTypeText'),
  'vision-ocr': t('workflow.canvas.visionOcr'),
  'vision-wait': t('workflow.canvas.visionWait'),
}));
```

**Step 5: Add `addVisionNode` function**

```typescript
function addVisionNode(type: WorkflowNode['type']) {
  const defaultData: Record<string, Record<string, unknown>> = {
    'vision-capture': { target: 'vnc', include_ocr: true, include_elements: true, include_layout: true },
    'vision-find-element': { target: 'vnc', element_type: '', text_match: '', confidence_threshold: 0.7 },
    'vision-click': { target: 'vnc', element_ref: '', click_type: 'single' },
    'vision-type-text': { target: 'vnc', element_ref: '', text: '', clear_first: false },
    'vision-ocr': { target: 'vnc', region: null },
    'vision-wait': { target: 'vnc', element_criteria: '', timeout_ms: 10000, poll_interval_ms: 500 },
  };
  const node: WorkflowNode = {
    id: genId(),
    type,
    position: { x: 100 + props.nodes.length * 40, y: 100 + props.nodes.length * 30 },
    data: defaultData[type] || {},
    connections: [],
  };
  emit('node-added', node);
  emit('node-selected', node.id);
  showVisionDropdown.value = false;
}
```

**Step 6: Add vision node body templates**

After the `<template v-else-if="node.type === 'condition'">` block (line ~71):

```html
<template v-else-if="node.type.startsWith('vision-')">
  <div class="node-row">
    <label class="target-label">Target:</label>
    <select v-model="(node.data as any).target" @click.stop>
      <option value="vnc">VNC</option>
      <option value="web">Web</option>
    </select>
  </div>
  <template v-if="node.type === 'vision-capture'">
    <label class="checkbox"><input type="checkbox" v-model="(node.data as any).include_ocr" @click.stop /> OCR</label>
    <label class="checkbox"><input type="checkbox" v-model="(node.data as any).include_elements" @click.stop /> Elements</label>
  </template>
  <template v-else-if="node.type === 'vision-find-element'">
    <input v-model="(node.data as any).element_type" placeholder="Element type (button, input...)" @click.stop />
    <input v-model="(node.data as any).text_match" placeholder="Text to match" @click.stop />
  </template>
  <template v-else-if="node.type === 'vision-click'">
    <select v-model="(node.data as any).click_type" @click.stop>
      <option value="single">Single Click</option>
      <option value="double">Double Click</option>
      <option value="right">Right Click</option>
    </select>
  </template>
  <template v-else-if="node.type === 'vision-type-text'">
    <input v-model="(node.data as any).text" placeholder="Text to type" @click.stop />
    <label class="checkbox"><input type="checkbox" v-model="(node.data as any).clear_first" @click.stop /> Clear first</label>
  </template>
  <template v-else-if="node.type === 'vision-ocr'">
    <span class="hint">Extracts all text from screen</span>
  </template>
  <template v-else-if="node.type === 'vision-wait'">
    <input v-model="(node.data as any).element_criteria" placeholder="Element to wait for" @click.stop />
    <input v-model.number="(node.data as any).timeout_ms" type="number" placeholder="Timeout (ms)" @click.stop />
  </template>
</template>
```

**Step 7: Add CSS for dropdown and vision node headers**

```css
.dropdown-container {
  position: relative;
  display: inline-block;
}
.dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 10;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 6px;
  padding: 4px 0;
  min-width: 180px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.dropdown-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  color: var(--text-primary, #e2e8f0);
  cursor: pointer;
  font-size: 0.85rem;
}
.dropdown-menu button:hover {
  background: var(--bg-tertiary, #334155);
}
.workflow-node[class*="vision-"] .node-header {
  background: linear-gradient(135deg, #7c3aed, #6d28d9);
}
.target-label {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
}
.hint {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  font-style: italic;
}
```

**Step 8: Commit**

```bash
git add autobot-frontend/src/components/workflow/WorkflowCanvas.vue
git commit -m "feat(automation): add 6 vision node types to workflow canvas (#2373)"
```

---

### Task 9: Add i18n keys for vision canvas nodes

**Files:**
- Modify: i18n locale file (same as Task 6)

**Step 1: Add keys under `workflow.canvas`**

```json
"vision": "Vision",
"addVisionNode": "Add vision automation node",
"visionCapture": "Screen Capture",
"visionFindElement": "Find Element",
"visionClick": "Click Element",
"visionTypeText": "Type Text",
"visionOcr": "OCR Extract",
"visionWait": "Wait for Element"
```

**Step 2: Commit**

```bash
git add autobot-frontend/src/locales/
git commit -m "feat(automation): add i18n keys for vision canvas nodes (#2373)"
```

---

### Task 10: Delete VisionView.vue

**Files:**
- Delete: `autobot-frontend/src/views/VisionView.vue`

**Step 1: Verify no other imports reference VisionView**

Run: `grep -rn "VisionView" autobot-frontend/src/`
Expected: No matches (router import was removed in Task 1).

**Step 2: Delete the file**

```bash
rm autobot-frontend/src/views/VisionView.vue
```

**Step 3: Verify build**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit 2>&1 | head -30`

**Step 4: Commit**

```bash
git add -u autobot-frontend/src/views/VisionView.vue
git commit -m "feat(automation): delete VisionView.vue — vision now under /automation (#2373)"
```

---

### Task 11: Final verification

**Step 1: Full type check**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit`
Expected: Clean.

**Step 2: Verify no remaining `/vision` route references**

Run: `grep -rn "to=.*['\"/]vision" autobot-frontend/src/ --include="*.vue" --include="*.ts"`
Expected: No matches. Component imports from `@/components/vision/` are fine.

**Step 3: Verify production build**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vite build 2>&1 | tail -20`
Expected: Build succeeds.

**Step 4: Add completion comment to GitHub issue**

```bash
gh issue comment 2373 --body "Implementation complete. Vision panels (Screen Analysis, Video Processing, Media Gallery) integrated into /automation sidebar under VISION group. 6 vision workflow node types added to canvas (capture, find-element, click, type-text, ocr, wait). /vision route removed."
```
