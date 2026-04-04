# Vision Modal + GUI Automation Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move vision image analysis into a chat input modal, embed GUI automation into the Browser tab, and remove the standalone `/vision` route.

**Architecture:** New `VisionAnalysisModal.vue` component triggered from chat input eye button. `GUIAutomationControls.vue` embedded as collapsible panel in `VisualBrowserPanel.vue`. Vision route and unused vision components deleted.

**Tech Stack:** Vue 3 + TypeScript, existing `VisionMultimodalApiClient.ts`, existing design tokens.

**Issue:** #1242

---

### Task 1: Create VisionAnalysisModal Component

**Files:**
- Create: `autobot-frontend/src/components/chat/VisionAnalysisModal.vue`

**Step 1: Create the modal component**

This component contains the full image analysis workflow: upload, intent picker, analyze, results, and "Send to Chat" action. Adapted from `ImageAnalyzer.vue` (lines 1-328) but wrapped in a modal overlay.

```vue
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * VisionAnalysisModal — Modal dialog for image analysis from the chat input.
 *
 * Provides upload, intent selection, analysis results, and "Send to Chat"
 * to insert results into the conversation. Issue #1242.
 */

import { ref, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import {
  visionMultimodalApiClient,
  type ProcessingIntent,
  type MultiModalResponse,
} from '@/utils/VisionMultimodalApiClient'

const logger = createLogger('VisionAnalysisModal')

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'send-to-chat', payload: {
    filename: string
    intent: ProcessingIntent
    question?: string
    result: MultiModalResponse
  }): void
}>()

// File state
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const previewUrl = ref<string | null>(null)
const isDragging = ref(false)

// Options
const selectedIntent = ref<ProcessingIntent>('analysis')
const question = ref('')

// Processing state
const processing = ref(false)
const analysisResult = ref<MultiModalResponse | null>(null)
const error = ref<string | null>(null)
const showRawJson = ref(false)

const intentLabels: Record<string, string> = {
  analysis: 'General Analysis',
  visual_qa: 'Visual Q&A',
  automation: 'Automation Detection',
  content_generation: 'Content Generation',
}

function triggerFileInput(): void {
  fileInput.value?.click()
}

function handleFileSelect(event: Event): void {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) selectFile(file)
}

function handleDrop(event: DragEvent): void {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) {
    selectFile(file)
  } else {
    error.value = 'Please drop a valid image file'
  }
}

function selectFile(file: File): void {
  selectedFile.value = file
  analysisResult.value = null
  error.value = null
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)
  logger.debug('File selected:', file.name)
}

function clearFile(): void {
  selectedFile.value = null
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
  analysisResult.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function analyzeImage(): Promise<void> {
  if (!selectedFile.value) return
  processing.value = true
  error.value = null
  try {
    const q = selectedIntent.value === 'visual_qa'
      ? question.value
      : undefined
    const response = await visionMultimodalApiClient.processImage(
      selectedFile.value,
      selectedIntent.value,
      q,
    )
    if (response.success && response.data) {
      analysisResult.value = response.data
      logger.debug('Analysis complete:', response.data)
    } else {
      error.value = response.error || 'Analysis failed'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown error'
    logger.error('Analysis error:', err)
  } finally {
    processing.value = false
  }
}

function sendToChat(): void {
  if (!analysisResult.value || !selectedFile.value) return
  emit('send-to-chat', {
    filename: selectedFile.value.name,
    intent: selectedIntent.value,
    question: selectedIntent.value === 'visual_qa'
      ? question.value
      : undefined,
    result: analysisResult.value,
  })
  emit('close')
}

function exportResults(): void {
  if (!analysisResult.value) return
  const blob = new Blob(
    [JSON.stringify(analysisResult.value, null, 2)],
    { type: 'application/json' },
  )
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `analysis_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

onUnmounted(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<template>
  <div class="vision-modal-overlay" @click.self="emit('close')">
    <div class="vision-modal">
      <!-- Header -->
      <div class="modal-header">
        <div class="header-title">
          <i class="fas fa-eye"></i>
          <h3>Image Analysis</h3>
        </div>
        <button @click="emit('close')" class="btn-close">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <!-- Body -->
      <div class="modal-body">
        <!-- Upload Zone -->
        <div
          class="drop-zone"
          :class="{ dragging: isDragging, 'has-file': selectedFile }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
          @click="triggerFileInput"
        >
          <input
            ref="fileInput"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            @change="handleFileSelect"
            hidden
          />
          <div v-if="!selectedFile" class="drop-placeholder">
            <i class="fas fa-cloud-upload-alt"></i>
            <p>Drag & drop an image or click to browse</p>
            <span class="formats">PNG, JPG, WebP, GIF</span>
          </div>
          <div v-else-if="previewUrl" class="file-preview">
            <img :src="previewUrl" alt="Preview" class="preview-image" />
            <div class="file-info">
              <span class="filename">{{ selectedFile.name }}</span>
              <span class="filesize">{{ formatFileSize(selectedFile.size) }}</span>
            </div>
            <button @click.stop="clearFile" class="btn-clear">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>

        <!-- Options -->
        <div class="options-row">
          <div class="option-group">
            <label>Intent</label>
            <select v-model="selectedIntent">
              <option value="analysis">General Analysis</option>
              <option value="visual_qa">Visual Q&A</option>
              <option value="automation">Automation Detection</option>
              <option value="content_generation">Content Generation</option>
            </select>
          </div>
          <div v-if="selectedIntent === 'visual_qa'" class="option-group flex-1">
            <label>Question</label>
            <input
              v-model="question"
              type="text"
              placeholder="What would you like to know about this image?"
            />
          </div>
        </div>

        <!-- Analyze Button -->
        <button
          @click="analyzeImage"
          class="btn-analyze"
          :disabled="!selectedFile || processing"
        >
          <i :class="processing ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          {{ processing ? 'Analyzing...' : 'Analyze Image' }}
        </button>

        <!-- Error -->
        <div v-if="error" class="error-banner">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ error }}</span>
          <button @click="error = null" class="error-dismiss">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <!-- Results -->
        <div v-if="analysisResult" class="results-section">
          <div class="results-header">
            <h4><i class="fas fa-check-circle"></i> Results</h4>
            <div class="results-meta">
              <span class="meta-badge">
                {{ (analysisResult.confidence * 100).toFixed(1) }}%
              </span>
              <span class="meta-badge">
                {{ analysisResult.processing_time.toFixed(2) }}s
              </span>
              <span v-if="analysisResult.device_used" class="meta-badge">
                {{ analysisResult.device_used }}
              </span>
            </div>
          </div>

          <div class="results-content">
            <!-- Description -->
            <div
              v-if="(analysisResult.result_data as any)?.description"
              class="result-item"
            >
              <span class="result-label">Description</span>
              <p class="result-value">
                {{ (analysisResult.result_data as any).description }}
              </p>
            </div>

            <!-- Labels -->
            <div
              v-if="(analysisResult.result_data as any)?.labels?.length"
              class="result-item"
            >
              <span class="result-label">Labels</span>
              <div class="tags">
                <span
                  v-for="label in (analysisResult.result_data as any).labels"
                  :key="label"
                  class="tag"
                >{{ label }}</span>
              </div>
            </div>

            <!-- Objects -->
            <div
              v-if="(analysisResult.result_data as any)?.objects?.length"
              class="result-item"
            >
              <span class="result-label">Detected Objects</span>
              <div class="objects-list">
                <div
                  v-for="(obj, idx) in (analysisResult.result_data as any).objects"
                  :key="idx"
                  class="object-row"
                >
                  <span>{{ obj.name || obj.label }}</span>
                  <span v-if="obj.confidence" class="obj-confidence">
                    {{ (obj.confidence * 100).toFixed(0) }}%
                  </span>
                </div>
              </div>
            </div>

            <!-- Raw JSON toggle -->
            <button @click="showRawJson = !showRawJson" class="btn-toggle-json">
              <i :class="showRawJson ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
              {{ showRawJson ? 'Hide' : 'Show' }} Raw JSON
            </button>
            <pre v-if="showRawJson" class="json-display">{{
              JSON.stringify(analysisResult, null, 2)
            }}</pre>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <button @click="exportResults" class="btn-secondary" :disabled="!analysisResult">
          <i class="fas fa-download"></i> Export JSON
        </button>
        <div class="footer-right">
          <button @click="emit('close')" class="btn-secondary">Cancel</button>
          <button
            @click="sendToChat"
            class="btn-primary"
            :disabled="!analysisResult"
          >
            <i class="fas fa-paper-plane"></i> Send to Chat
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vision-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.vision-modal {
  background: var(--bg-secondary, #fff);
  border-radius: 12px;
  width: 90%;
  max-width: 640px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

/* Header */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-title i {
  color: var(--color-primary);
  font-size: 18px;
}

.header-title h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-close {
  padding: 8px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
}

.btn-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Body */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Drop zone */
.drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: 10px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--color-primary);
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.05));
}

.drop-zone.has-file {
  border-style: solid;
  padding: 16px;
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-tertiary);
}

.drop-placeholder i {
  font-size: 36px;
  color: var(--text-muted);
}

.drop-placeholder p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.formats {
  font-size: 12px;
  color: var(--text-muted);
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
}

.preview-image {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: left;
}

.filename {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-all;
}

.filesize {
  font-size: 12px;
  color: var(--text-tertiary);
}

.btn-clear {
  padding: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.btn-clear:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Options */
.options-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 160px;
}

.option-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.option-group select,
.option-group input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
}

.option-group select:focus,
.option-group input:focus {
  outline: none;
  border-color: var(--color-primary);
}

/* Analyze button */
.btn-analyze {
  padding: 10px 24px;
  background: var(--color-primary);
  color: var(--text-on-primary, #fff);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  align-self: center;
}

.btn-analyze:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-analyze:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border, var(--color-error));
  border-radius: 8px;
  color: var(--color-error);
  font-size: 13px;
}

.error-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
}

/* Results */
.results-section {
  background: var(--bg-tertiary);
  border-radius: 10px;
  overflow: hidden;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--color-success-bg);
}

.results-header h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: 6px;
}

.results-meta {
  display: flex;
  gap: 8px;
}

.meta-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.results-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.result-value {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag {
  font-size: 11px;
  padding: 3px 8px;
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.1));
  color: var(--color-primary);
  border-radius: 10px;
}

.objects-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.object-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-primary);
}

.obj-confidence {
  font-size: 12px;
  color: var(--text-tertiary);
}

.btn-toggle-json {
  padding: 6px 10px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-toggle-json:hover {
  color: var(--text-secondary);
}

.json-display {
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
  margin: 0;
}

/* Footer */
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-top: 1px solid var(--border-default);
}

.footer-right {
  display: flex;
  gap: 8px;
}

.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary, #fff);
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
```

**Step 2: Verify file created**

Run: `ls -la autobot-frontend/src/components/chat/VisionAnalysisModal.vue`
Expected: File exists

**Step 3: Commit**

```bash
git add autobot-frontend/src/components/chat/VisionAnalysisModal.vue
git commit -m "feat(chat): add VisionAnalysisModal component (#1242)"
```

---

### Task 2: Add Eye Button to ChatInput + Wire Modal

**Files:**
- Modify: `autobot-frontend/src/components/chat/ChatInput.vue`

**Step 1: Add import and state for the modal**

At `ChatInput.vue:269` (after BaseButton import), add the VisionAnalysisModal import:

```typescript
import VisionAnalysisModal from './VisionAnalysisModal.vue'
```

At `ChatInput.vue:300` (after `showEmojiPicker` ref), add:

```typescript
const showVisionModal = ref(false)
```

**Step 2: Add eye button in template between paperclip (line 150) and voice input (line 152)**

After the closing `</BaseButton>` of the paperclip button (line 150) and before the Voice Input comment (line 152), insert:

```html
            <!-- Vision Analysis Button (#1242) -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="showVisionModal = true"
              class="action-btn"
              :disabled="isDisabled"
              aria-label="Analyze image"
            >
              <i class="fas fa-eye" aria-hidden="true"></i>
            </BaseButton>
```

**Step 3: Add modal to template and emit handler**

Before the closing `</div>` of the root element (line 259, just after the emoji picker closing div), add:

```html
    <!-- Vision Analysis Modal (#1242) -->
    <VisionAnalysisModal
      v-if="showVisionModal"
      @close="showVisionModal = false"
      @send-to-chat="handleVisionSendToChat"
    />
```

**Step 4: Add the emit and handler**

Add emit declaration. Since ChatInput uses `controller.sendMessage` directly and doesn't use `defineEmits`, we need to add it. After the `useVoiceOutput` line (~line 279), add the emit:

```typescript
const emit = defineEmits<{
  (e: 'vision-send-to-chat', payload: {
    filename: string
    intent: string
    question?: string
    result: import('@/utils/VisionMultimodalApiClient').MultiModalResponse
  }): void
}>()
```

Then add the handler function after `toggleEmojiPicker` (~line 621):

```typescript
const handleVisionSendToChat = (payload: {
  filename: string
  intent: string
  question?: string
  result: import('@/utils/VisionMultimodalApiClient').MultiModalResponse
}) => {
  showVisionModal.value = false
  emit('vision-send-to-chat', payload)
}
```

**Step 5: Commit**

```bash
git add autobot-frontend/src/components/chat/ChatInput.vue
git commit -m "feat(chat): add vision eye button to chat input (#1242)"
```

---

### Task 3: Handle Vision Results in ChatInterface

**Files:**
- Modify: `autobot-frontend/src/components/chat/ChatInterface.vue`

**Step 1: Add provide for vision send-to-chat handler**

ChatInput doesn't actually have a direct event connection to ChatInterface (it's nested inside ChatTabContent). Instead, use provide/inject pattern (same as overseer).

Alternative approach: Since ChatTabContent renders ChatInput, propagate the event up.

First, in `ChatTabContent.vue` add the emit propagation. Add to emit interface (~line 213):

```typescript
'vision-send-to-chat': [payload: {
  filename: string
  intent: string
  question?: string
  result: Record<string, unknown>
}]
```

In the ChatInput usage in template (line 8), add:

```html
<ChatInput class="flex-shrink-0" @vision-send-to-chat="(p: any) => emit('vision-send-to-chat', p)" />
```

**Step 2: Handle the event in ChatInterface**

In `ChatInterface.vue` template, on the ChatTabContent component (line 81), add:

```html
@vision-send-to-chat="handleVisionSendToChat"
```

Then in the script, after `handleToolCallDetected` (~line 490), add the handler:

```typescript
// Issue #1242: Handle vision analysis results being sent to chat
const handleVisionSendToChat = (payload: {
  filename: string
  intent: string
  question?: string
  result: {
    confidence: number
    processing_time: number
    device_used?: string
    result_data: Record<string, unknown>
  }
}) => {
  logger.debug('Vision analysis sent to chat:', payload.filename)

  const intentLabels: Record<string, string> = {
    analysis: 'General Analysis',
    visual_qa: 'Visual Q&A',
    automation: 'Automation Detection',
    content_generation: 'Content Generation',
  }
  const intentLabel = intentLabels[payload.intent] || payload.intent

  // Add user message
  store.addMessage({
    content: `Analyzed image: **${payload.filename}** (${intentLabel})${payload.question ? `\nQuestion: ${payload.question}` : ''}`,
    sender: 'user',
    status: 'sent',
    type: 'message',
  })

  // Build formatted assistant response
  const rd = payload.result.result_data as Record<string, unknown>
  const parts: string[] = []

  parts.push(`**Image Analysis Results** — ${(payload.result.confidence * 100).toFixed(1)}% confidence, ${payload.result.processing_time.toFixed(2)}s`)

  if (rd.description) {
    parts.push(`\n**Description:** ${rd.description}`)
  }
  if (Array.isArray(rd.labels) && rd.labels.length > 0) {
    parts.push(`\n**Labels:** ${rd.labels.join(', ')}`)
  }
  if (Array.isArray(rd.objects) && rd.objects.length > 0) {
    const objLines = (rd.objects as Array<{ name?: string; label?: string; confidence?: number }>)
      .map(o => {
        const name = o.name || o.label || 'Unknown'
        const conf = o.confidence ? ` (${(o.confidence * 100).toFixed(0)}%)` : ''
        return `- ${name}${conf}`
      })
      .join('\n')
    parts.push(`\n**Detected Objects:**\n${objLines}`)
  }

  if (payload.result.device_used) {
    parts.push(`\n*Processed on: ${payload.result.device_used}*`)
  }

  store.addMessage({
    content: parts.join('\n'),
    sender: 'assistant',
    status: 'sent',
    type: 'message',
  })
}
```

**Step 3: Commit**

```bash
git add autobot-frontend/src/components/chat/ChatTabContent.vue autobot-frontend/src/components/chat/ChatInterface.vue
git commit -m "feat(chat): wire vision modal results into chat conversation (#1242)"
```

---

### Task 4: Add GUI Automation Panel to VisualBrowserPanel

**Files:**
- Modify: `autobot-frontend/src/components/chat/VisualBrowserPanel.vue`

**Step 1: Add imports and state for automation panel**

At `VisualBrowserPanel.vue:14` (after `createLogger` import), add:

```typescript
import GUIAutomationControls from '@/components/vision/GUIAutomationControls.vue'
import {
  visionMultimodalApiClient,
  type AutomationOpportunity,
} from '@/utils/VisionMultimodalApiClient'
```

After `statusChecked` ref (line 27), add automation state:

```typescript
// GUI Automation panel state (#1242)
const showAutomation = ref(false)
const automationOpportunities = ref<AutomationOpportunity[]>([])
const automationLoading = ref(false)

async function loadAutomationOpportunities(): Promise<void> {
  automationLoading.value = true
  try {
    const res = await visionMultimodalApiClient.getAutomationOpportunities()
    if (res.success && res.data) {
      automationOpportunities.value = res.data.opportunities || []
    }
  } catch (e) {
    logger.warn('Failed to load automation opportunities:', e)
  } finally {
    automationLoading.value = false
  }
}

function toggleAutomation(): void {
  showAutomation.value = !showAutomation.value
  if (showAutomation.value && automationOpportunities.value.length === 0) {
    loadAutomationOpportunities()
  }
}
```

**Step 2: Add automation toggle button in address bar**

After the screenshot button (line 192, the `</button>` of `.screenshot-btn`), before the closing `</div>` of `.address-row`, add:

```html
        <!-- Automation toggle (#1242) -->
        <button
          @click="toggleAutomation"
          class="nav-btn automation-toggle-btn"
          :class="{ 'automation-active': showAutomation }"
          title="Toggle GUI Automation Panel"
        >
          <i class="fas fa-robot"></i>
        </button>
```

**Step 3: Change viewport layout to support side panel**

Replace the `<!-- Viewport -->` section (lines 203-235) with a flex container:

```html
    <!-- Content Area (viewport + optional automation panel) -->
    <div class="browser-content">
      <!-- Viewport -->
      <div class="browser-viewport">
        <!-- Loading Spinner -->
        <div v-if="loading && !screenshot" class="viewport-state">
          <i class="fas fa-spinner fa-spin viewport-icon"></i>
          <p class="viewport-msg">Loading...</p>
        </div>

        <!-- Disconnected / not started -->
        <div v-else-if="!isConnected" class="viewport-state">
          <i class="fas fa-globe viewport-icon viewport-icon--dim"></i>
          <h3 class="viewport-title">Browser</h3>
          <p class="viewport-msg">Enter a URL above and press Enter or click the search icon to start browsing.</p>
        </div>

        <!-- Screenshot Display -->
        <img
          v-else-if="screenshot"
          :src="`data:image/png;base64,${screenshot}`"
          alt="Browser screenshot"
          class="screenshot-img"
          :class="{ 'screenshot-img--loading': loading }"
        />

        <!-- Connected but no screenshot yet -->
        <div v-else class="viewport-state">
          <i class="fas fa-camera viewport-icon viewport-icon--dim"></i>
          <p class="viewport-msg">No screenshot yet — navigate to a URL to capture the browser view.</p>
          <button @click="captureScreenshot" class="capture-btn">
            <i class="fas fa-camera mr-2"></i>Capture Screenshot
          </button>
        </div>
      </div>

      <!-- GUI Automation Side Panel (#1242) -->
      <Transition name="slide-panel">
        <div v-if="showAutomation" class="automation-panel">
          <GUIAutomationControls
            :opportunities="automationOpportunities"
            :loading="automationLoading"
            @refresh="loadAutomationOpportunities"
          />
        </div>
      </Transition>
    </div>
```

**Step 4: Add CSS for new layout**

Add these styles to the `<style scoped>` section:

```css
/* ---- Content area (viewport + automation panel) ---- */
.browser-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* Automation toggle active state */
.automation-toggle-btn.automation-active {
  color: var(--color-primary);
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.1));
}

/* ---- Automation side panel ---- */
.automation-panel {
  width: 360px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-default);
  background: var(--bg-primary);
  overflow-y: auto;
  padding: var(--spacing-3);
}

/* Panel slide transition */
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: width 0.25s ease, opacity 0.25s ease;
}

.slide-panel-enter-from,
.slide-panel-leave-to {
  width: 0;
  opacity: 0;
  overflow: hidden;
}
```

Also update the existing `.browser-viewport` to work within the flex layout — change from:

```css
.browser-viewport {
  flex: 1;
  overflow: auto;
  background: var(--bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
```

No change needed — `flex: 1` already works in the flex row context.

**Step 5: Add Transition import**

Add `Transition` to the Vue imports at line 14:

```typescript
import { ref, onMounted, Transition } from 'vue'
```

Note: `Transition` is a built-in Vue component and doesn't need explicit import — it's available globally. Skip this if the linter complains.

**Step 6: Commit**

```bash
git add autobot-frontend/src/components/chat/VisualBrowserPanel.vue
git commit -m "feat(browser): add GUI automation side panel to browser tab (#1242)"
```

---

### Task 5: Remove /vision Route, Nav Links, and Unused Components

**Files:**
- Modify: `autobot-frontend/src/router/index.ts` (lines 42, 329-374, 714)
- Modify: `autobot-frontend/src/App.vue` (lines 123-139, 316-333)
- Delete: `autobot-frontend/src/views/VisionView.vue`
- Delete: `autobot-frontend/src/components/vision/VisionAutomationPage.vue`
- Delete: `autobot-frontend/src/components/vision/ImageAnalyzer.vue`
- Delete: `autobot-frontend/src/components/vision/ScreenCaptureViewer.vue`
- Delete: `autobot-frontend/src/components/vision/AnalysisResults.vue`

**Step 1: Remove VisionView import from router**

In `router/index.ts`, remove line 42:

```typescript
import VisionView from '@/views/VisionView.vue'
```

**Step 2: Remove /vision route block from router**

In `router/index.ts`, remove lines 329-374 (the entire `/vision` route object with all children).

**Step 3: Remove 'vision' from validTabs**

In `router/index.ts` line 714, change:

```typescript
const validTabs = ['chat', 'knowledge', 'automation', 'analytics', 'vision'] as const
```

to:

```typescript
const validTabs = ['chat', 'knowledge', 'automation', 'analytics'] as const
```

**Step 4: Remove desktop Vision nav link from App.vue**

Remove lines 123-139 (the desktop nav `<!-- Issue #777: Vision & Multimodal AI -->` router-link block).

**Step 5: Remove mobile Vision nav link from App.vue**

Remove lines 316-333 (the mobile nav `<!-- Issue #777: Vision & Multimodal AI -->` router-link block). Note: line numbers will have shifted after step 4 — search for the second occurrence of `<!-- Issue #777: Vision & Multimodal AI -->`.

**Step 6: Delete unused component files**

```bash
git rm autobot-frontend/src/views/VisionView.vue
git rm autobot-frontend/src/components/vision/VisionAutomationPage.vue
git rm autobot-frontend/src/components/vision/ImageAnalyzer.vue
git rm autobot-frontend/src/components/vision/ScreenCaptureViewer.vue
git rm autobot-frontend/src/components/vision/AnalysisResults.vue
```

**Step 7: Commit**

```bash
git add autobot-frontend/src/router/index.ts autobot-frontend/src/App.vue
git commit -m "refactor(vision): remove /vision route and unused vision components (#1242)"
```

---

### Task 6: Build Verification

**Files:** None (verification only)

**Step 1: Run build**

```bash
cd autobot-frontend && npm run build 2>&1 | tail -40
```

Expected: Build succeeds with no errors about missing imports or components.

**Step 2: Check for dead imports**

```bash
cd autobot-frontend && grep -r "VisionView\|VisionAutomationPage\|ImageAnalyzer\|ScreenCaptureViewer\|AnalysisResults" src/ --include="*.vue" --include="*.ts" -l
```

Expected: No results (all references removed).

**Step 3: Fix any remaining issues**

If build fails, fix import issues (likely in files that imported deleted components).

Check for any other files referencing the deleted components:
- `MediaGallery.vue` and `VideoProcessor.vue` are kept — verify they don't import deleted components.

**Step 4: Final commit if fixes needed**

```bash
git add -A && git commit -m "fix(build): clean up dead imports after vision restructure (#1242)"
```

---

### Task 7: Close Issue

**Step 1: Close the GitHub issue**

```bash
gh issue close 1242 --comment "Implemented vision restructure:
- VisionAnalysisModal: full image analysis flow as modal from chat input eye button
- GUI automation panel: collapsible side panel in Browser tab using GUIAutomationControls
- Removed /vision route and 5 unused vision components
- Build verified clean"
```

**Step 2: Verify closure**

```bash
gh issue view 1242 --json state
```

Expected: `"state": "CLOSED"`
