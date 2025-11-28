# Individual Document Vectorization - UX Design Specification

**GitHub Issue:** [#254](https://github.com/mrveiss/AutoBot-AI/issues/254)
**Version:** 1.0
**Date:** 2025-10-02
**Component:** Knowledge Base File Browser
**Technology:** Vue 3 + TypeScript + Font Awesome

---

## Table of Contents

1. [Overview](#overview)
2. [Design System Foundation](#design-system-foundation)
3. [Component Architecture](#component-architecture)
4. [Visual Specifications](#visual-specifications)
5. [Interaction Patterns](#interaction-patterns)
6. [State Management](#state-management)
7. [API Integration](#api-integration)
8. [Accessibility](#accessibility)
9. [Mobile & Responsive](#mobile--responsive)
10. [Implementation Roadmap](#implementation-roadmap)

---

## 1. Overview

### Purpose
Enable users to trigger vectorization for individual documents directly from the Knowledge Base file browser, providing granular control over which documents receive vector embeddings for semantic search capabilities.

### User Goals
- **Quickly vectorize** individual documents without batch operations
- **View vectorization status** at a glance for each document
- **Batch select and process** multiple documents selectively
- **Retry failed** vectorization attempts with clear feedback
- **Understand progress** through visual indicators and messaging

### Current State Analysis
- ✅ **Exists**: Batch vectorization API endpoints, background processing
- ✅ **Exists**: Tree-based file browser with category organization
- ❌ **Missing**: Per-document vectorization UI triggers
- ❌ **Missing**: Visual vectorization status indicators
- ❌ **Missing**: Batch selection interface for selective processing
- ❌ **Missing**: Error handling and retry mechanisms in UI

---

## 2. Design System Foundation

### Color Palette

```typescript
const VECTORIZATION_COLORS = {
  // Status Colors
  notVectorized: '#9ca3af',    // Gray-400 - Neutral state
  vectorizing: '#3b82f6',      // Blue-500 - Processing
  vectorized: '#10b981',       // Green-500 - Success
  failed: '#ef4444',           // Red-500 - Error

  // UI Colors
  background: '#ffffff',       // White
  border: '#e5e7eb',          // Gray-200
  hover: '#f3f4f6',           // Gray-100
  selected: '#eff6ff',        // Blue-50

  // Action Colors
  primary: '#3b82f6',         // Blue-500
  primaryHover: '#2563eb',    // Blue-600
  secondary: '#6b7280',       // Gray-500
  danger: '#dc2626'           // Red-600
}
```

### Typography Scale

```typescript
const TYPOGRAPHY = {
  fileName: {
    size: '0.875rem',      // 14px
    weight: 400,
    lineHeight: 1.5
  },
  statusBadge: {
    size: '0.6875rem',     // 11px
    weight: 600,
    lineHeight: 1,
    transform: 'uppercase'
  },
  tooltip: {
    size: '0.75rem',       // 12px
    weight: 500,
    lineHeight: 1.4
  },
  actionLabel: {
    size: '0.8125rem',     // 13px
    weight: 500,
    lineHeight: 1.5
  }
}
```

### Spacing System

```typescript
const SPACING = {
  treeItemPadding: '0.5rem 0.75rem',      // 8px 12px
  iconGap: '0.5rem',                       // 8px
  badgeMargin: '0 0.5rem',                 // 0 8px
  actionButtonSize: '1.75rem',             // 28px
  checkboxSize: '1rem',                    // 16px
  batchToolbarHeight: '3.5rem',            // 56px
  modalPadding: '1.5rem'                   // 24px
}
```

### Icon Library (Font Awesome)

```typescript
const ICONS = {
  // Vectorization Status
  vectorized: 'fas fa-check-circle',
  notVectorized: 'far fa-circle',
  vectorizing: 'fas fa-spinner fa-spin',
  failed: 'fas fa-exclamation-triangle',

  // Actions
  vectorize: 'fas fa-cube',
  retry: 'fas fa-redo',
  cancel: 'fas fa-times',
  batchProcess: 'fas fa-cubes',

  // Selection
  checkbox: 'far fa-square',
  checkboxChecked: 'fas fa-check-square',
  selectAll: 'fas fa-check-double',

  // File Types
  file: 'fas fa-file-alt',
  folder: 'fas fa-folder',
  folderOpen: 'fas fa-folder-open'
}
```

---

## 3. Component Architecture

### Enhanced TreeNode Component

```typescript
interface TreeNodeWithVectorization extends TreeNode {
  id: string
  name: string
  type: 'folder' | 'file'
  path: string
  children?: TreeNodeWithVectorization[]

  // Vectorization Properties
  vectorizationStatus?: 'vectorized' | 'not-vectorized' | 'vectorizing' | 'failed'
  vectorId?: string
  lastVectorized?: string
  vectorizationError?: string

  // Selection State
  selected?: boolean

  // Metadata
  size?: number
  date?: string
  category?: string
}
```

### Component Hierarchy

```
KnowledgeFileBrowser
├── TreeContainer
│   ├── BatchSelectionToolbar (conditional)
│   └── TreeNodeComponent (recursive)
│       ├── SelectionCheckbox (files only)
│       ├── ExpandButton (folders only)
│       ├── NodeIcon
│       ├── NodeName
│       ├── VectorizationStatusBadge (files only)
│       └── VectorizationActionButton (files only)
└── VectorizationProgressModal (conditional)
```

### New Components to Create

#### 1. **VectorizationStatusBadge.vue**

**Purpose**: Display current vectorization status with visual feedback

```vue
<template>
  <span class="vectorization-badge" :class="statusClass">
    <i :class="statusIcon"></i>
    <span v-if="showLabel">{{ statusLabel }}</span>
  </span>
</template>

<script setup lang="ts">
interface Props {
  status: 'vectorized' | 'not-vectorized' | 'vectorizing' | 'failed'
  showLabel?: boolean
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showLabel: false,
  compact: false
})
</script>
```

**Visual States**:
- `vectorized`: Green circle with checkmark, "Vectorized" label
- `not-vectorized`: Gray outline circle, "Not Vectorized" label
- `vectorizing`: Blue spinning icon, "Vectorizing..." label
- `failed`: Red triangle with exclamation, "Failed" label

#### 2. **VectorizationActionButton.vue**

**Purpose**: Trigger vectorization for individual documents

```vue
<template>
  <button
    class="vectorize-btn"
    :class="buttonClass"
    :disabled="disabled"
    :aria-label="ariaLabel"
    @click.stop="handleClick"
  >
    <i :class="iconClass"></i>
    <span v-if="showLabel" class="btn-label">{{ label }}</span>
  </button>
</template>

<script setup lang="ts">
interface Props {
  status: 'vectorized' | 'not-vectorized' | 'vectorizing' | 'failed'
  nodeId: string
  nodePath: string
  showLabel?: boolean
}

interface Emits {
  (e: 'vectorize', payload: { nodeId: string, path: string }): void
  (e: 'retry', payload: { nodeId: string, path: string }): void
}

const emit = defineEmits<Emits>()
const props = withDefaults(defineProps<Props>(), {
  showLabel: false
})
</script>
```

**Button States**:
- `not-vectorized`: Blue cube icon, "Vectorize" action
- `vectorizing`: Disabled, spinning icon, no action
- `vectorized`: Green checkmark, disabled or hidden
- `failed`: Red retry icon, "Retry" action

#### 3. **BatchSelectionToolbar.vue**

**Purpose**: Batch operations control panel

```vue
<template>
  <div class="batch-toolbar" v-if="selectedCount > 0">
    <div class="toolbar-left">
      <button @click="selectAll" class="toolbar-btn">
        <i class="fas fa-check-double"></i>
        Select All
      </button>
      <button @click="deselectAll" class="toolbar-btn">
        <i class="fas fa-times"></i>
        Deselect All
      </button>
      <span class="selected-count">{{ selectedCount }} selected</span>
    </div>

    <div class="toolbar-right">
      <button @click="vectorizeSelected" class="toolbar-btn primary">
        <i class="fas fa-cubes"></i>
        Vectorize Selected ({{ selectedCount }})
      </button>
      <button @click="cancelSelection" class="toolbar-btn secondary">
        Cancel
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  selectedCount: number
  selectedNodes: TreeNodeWithVectorization[]
}

interface Emits {
  (e: 'selectAll'): void
  (e: 'deselectAll'): void
  (e: 'vectorizeSelected'): void
  (e: 'cancelSelection'): void
}

const emit = defineEmits<Emits>()
const props = defineProps<Props>()
</script>
```

#### 4. **VectorizationProgressModal.vue**

**Purpose**: Show progress for batch vectorization operations

```vue
<template>
  <div class="modal-overlay" v-if="isVisible" @click.self="handleCancel">
    <div class="modal-container">
      <div class="modal-header">
        <h3>Vectorizing Documents</h3>
        <button @click="handleCancel" class="close-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <div class="modal-body">
        <!-- Overall Progress -->
        <div class="progress-section">
          <div class="progress-info">
            <span>Overall Progress</span>
            <span class="progress-label">{{ completed }} / {{ total }}</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: overallProgress + '%' }"></div>
          </div>
        </div>

        <!-- Current Document -->
        <div class="current-document" v-if="currentDocument">
          <div class="document-icon">
            <i class="fas fa-spinner fa-spin"></i>
          </div>
          <div class="document-info">
            <p class="document-name">{{ currentDocument.name }}</p>
            <p class="document-status">{{ currentStatus }}</p>
          </div>
        </div>

        <!-- Results Summary -->
        <div class="results-grid">
          <div class="result-stat success">
            <i class="fas fa-check-circle"></i>
            <span>{{ successCount }} Successful</span>
          </div>
          <div class="result-stat failed">
            <i class="fas fa-exclamation-triangle"></i>
            <span>{{ failedCount }} Failed</span>
          </div>
          <div class="result-stat skipped">
            <i class="fas fa-forward"></i>
            <span>{{ skippedCount }} Skipped</span>
          </div>
        </div>

        <!-- Error Messages -->
        <div class="error-list" v-if="errors.length > 0">
          <h4>Errors</h4>
          <div class="error-item" v-for="error in errors" :key="error.documentId">
            <span class="error-doc">{{ error.documentName }}</span>
            <span class="error-msg">{{ error.message }}</span>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button v-if="!isComplete" @click="handleCancel" class="btn secondary">
          Cancel
        </button>
        <button v-else @click="handleClose" class="btn primary">
          Close
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  isVisible: boolean
  total: number
  completed: number
  successCount: number
  failedCount: number
  skippedCount: number
  currentDocument?: TreeNodeWithVectorization
  currentStatus?: string
  errors: VectorizationError[]
  isComplete: boolean
}

interface VectorizationError {
  documentId: string
  documentName: string
  message: string
}

interface Emits {
  (e: 'cancel'): void
  (e: 'close'): void
}

const emit = defineEmits<Emits>()
const props = defineProps<Props>()

const overallProgress = computed(() => {
  if (props.total === 0) return 0
  return Math.round((props.completed / props.total) * 100)
})
</script>
```

---

## 4. Visual Specifications

### Tree Item Layout (Enhanced)

```
┌─────────────────────────────────────────────────────────────┐
│ [✓] [▶] 📄 document-name.md      [●] Vectorized  [⟳]       │
│  1   2   3        4                 5      6        7        │
└─────────────────────────────────────────────────────────────┘

1. Selection checkbox (16px × 16px) - Files only
2. Expand/collapse button (20px × 20px) - Folders only
3. File/folder icon (16px) - Context-based
4. Document name (flex-1, truncate) - Primary text
5. Status indicator badge (24px × 16px) - Visual status
6. Status label - Text description
7. Action button (28px × 28px) - Vectorize/retry
```

### Status Badge Variants

#### Vectorized (Success)
```css
.vectorization-badge.vectorized {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid #10b981;
  color: #10b981;
  padding: 0.125rem 0.5rem;
  border-radius: 0.75rem;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.vectorization-badge.vectorized i {
  font-size: 0.75rem;
}
```

#### Not Vectorized (Neutral)
```css
.vectorization-badge.not-vectorized {
  background: rgba(156, 163, 175, 0.1);
  border: 1px solid #9ca3af;
  color: #6b7280;
  /* ... same structural styles */
}
```

#### Vectorizing (Processing)
```css
.vectorization-badge.vectorizing {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid #3b82f6;
  color: #3b82f6;
  /* ... same structural styles */
  animation: pulse-blue 2s ease-in-out infinite;
}

@keyframes pulse-blue {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(59, 130, 246, 0);
  }
}
```

#### Failed (Error)
```css
.vectorization-badge.failed {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid #ef4444;
  color: #ef4444;
  /* ... same structural styles */
  cursor: pointer;
}

.vectorization-badge.failed:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: #dc2626;
}
```

### Action Button States

#### Default (Vectorize)
```css
.vectorize-btn {
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 0.375rem;
  border: 1px solid #d1d5db;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  color: #3b82f6;
}

.vectorize-btn:hover:not(:disabled) {
  background: #eff6ff;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.vectorize-btn:active:not(:disabled) {
  transform: scale(0.95);
}
```

#### Disabled (Vectorizing)
```css
.vectorize-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #f9fafb;
}
```

#### Retry (Failed State)
```css
.vectorize-btn.retry {
  color: #ef4444;
  border-color: #ef4444;
}

.vectorize-btn.retry:hover:not(:disabled) {
  background: #fef2f2;
  border-color: #dc2626;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}
```

### Batch Selection Toolbar

```css
.batch-toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 0.75rem 1.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  color: white;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.toolbar-btn {
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.1);
  color: white;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  backdrop-filter: blur(10px);
}

.toolbar-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.5);
}

.toolbar-btn.primary {
  background: rgba(59, 130, 246, 0.3);
  border-color: #3b82f6;
}

.toolbar-btn.primary:hover {
  background: rgba(59, 130, 246, 0.5);
}

.selected-count {
  font-size: 0.875rem;
  font-weight: 600;
  padding: 0.25rem 0.75rem;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 0.375rem;
  backdrop-filter: blur(10px);
}
```

### Progress Modal

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

.modal-container {
  background: white;
  border-radius: 0.75rem;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: slideUp 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modal-header {
  padding: 1.5rem;
  border-bottom: 2px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.progress-bar {
  height: 0.5rem;
  background: #e5e7eb;
  border-radius: 0.25rem;
  overflow: hidden;
  margin-top: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #2563eb);
  transition: width 0.3s ease;
  border-radius: 0.25rem;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-top: 1.5rem;
}

.result-stat {
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.result-stat i {
  font-size: 1.5rem;
}

.result-stat.success {
  color: #10b981;
  background: rgba(16, 185, 129, 0.1);
}

.result-stat.failed {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.result-stat.skipped {
  color: #6b7280;
  background: rgba(107, 114, 128, 0.1);
}
```

---

## 5. Interaction Patterns

### Single Document Vectorization Flow

```
User Action → UI State → API Call → Response Handling → UI Update

1. INITIAL STATE
   User sees: File with "Not Vectorized" badge + blue cube button

2. CLICK VECTORIZE
   User clicks: Blue cube button
   UI updates:
     - Badge changes to "Vectorizing..." with spinner
     - Button disabled, shows spinner icon
     - Tooltip: "Vectorization in progress..."

3. API CALL
   POST /api/knowledge_base/vectorize_document
   Body: { document_id, document_path, category }

4a. SUCCESS RESPONSE
   UI updates:
     - Badge changes to "Vectorized" with green checkmark
     - Button hidden or shows checkmark (disabled)
     - Show toast notification: "Document vectorized successfully"
     - Update tree stats if displayed

4b. ERROR RESPONSE
   UI updates:
     - Badge changes to "Failed" with red warning
     - Button changes to retry icon (red)
     - Show error toast with details
     - Tooltip shows error message on badge hover
```

### Batch Selection & Processing Flow

```
1. ENABLE SELECTION MODE
   User action: Clicks "Select Multiple" or uses Ctrl+Click
   UI updates:
     - Checkboxes appear on all file items
     - Batch toolbar slides in from top

2. SELECT DOCUMENTS
   User action: Clicks checkboxes or uses Shift+Click for range
   UI updates:
     - Selected items highlighted with blue background
     - Selected count updates in toolbar
     - "Vectorize Selected" button shows count

3. TRIGGER BATCH VECTORIZATION
   User clicks: "Vectorize Selected (N)" button
   UI updates:
     - Progress modal opens
     - Documents processed sequentially
     - Progress bar updates with each completion
     - Current document name displayed

4. PROCESS DOCUMENTS
   For each document:
     - Show document name with spinner
     - API call to vectorize
     - Update counts (success/failed/skipped)
     - Show errors in expandable list

5. COMPLETION
   All documents processed:
     - Show final summary
     - "Close" button enabled
     - Option to retry failed items
```

### Error Handling & Retry Pattern

```
FAILED VECTORIZATION SCENARIO

Initial State:
  - Badge: "Failed" (red) with warning icon
  - Button: Retry icon (red)
  - Tooltip: Shows error reason

User Actions:
  1. Hover badge → See full error message
  2. Click retry button → Re-attempt vectorization
  3. Click "View Details" → Open error details modal

Retry Flow:
  1. User clicks retry button
  2. Confirmation tooltip: "Retry vectorization?"
  3. Click confirms → Same flow as initial vectorization
  4. Success → Normal success state
  5. Failure again → Increment retry count, show "Failed (2 attempts)"
```

### Keyboard Shortcuts

```typescript
const KEYBOARD_SHORTCUTS = {
  'Ctrl+V': 'Vectorize selected documents',
  'Ctrl+A': 'Select all visible documents',
  'Ctrl+D': 'Deselect all documents',
  'Escape': 'Exit selection mode or close modal',
  'Space': 'Toggle selection on focused item',
  'Shift+↓/↑': 'Select range of documents',
  'Enter': 'Trigger vectorization on focused item'
}
```

### Loading States & Skeleton Screens

```
LOADING SCENARIO: Fetching Vectorization Status

1. Initial Load
   Show: Skeleton badges on all files
   Duration: Until API response

2. API Response
   Replace: Skeletons with actual status badges
   Animation: Fade-in transition (200ms)

3. Real-Time Updates
   When: Background vectorization completes
   Update: Badge changes from "Vectorizing" to "Vectorized"
   Effect: Smooth color transition + checkmark animation
```

---

## 6. State Management

### Component State Structure

```typescript
// KnowledgeFileBrowser.vue
interface State {
  // Tree Data
  treeData: TreeNodeWithVectorization[]
  expandedNodes: Set<string>
  selectedFile: TreeNodeWithVectorization | null

  // Selection State
  selectionMode: boolean
  selectedNodes: Set<string>

  // Vectorization State
  vectorizingNodes: Set<string>
  vectorizationStatus: Map<string, VectorizationStatus>

  // Batch Processing
  batchProcessing: boolean
  batchProgress: BatchProgress

  // UI State
  isLoading: boolean
  error: string | null
  showProgressModal: boolean
}

interface VectorizationStatus {
  status: 'vectorized' | 'not-vectorized' | 'vectorizing' | 'failed'
  vectorId?: string
  lastVectorized?: Date
  error?: string
  retryCount?: number
}

interface BatchProgress {
  total: number
  completed: number
  successCount: number
  failedCount: number
  skippedCount: number
  currentDocument?: TreeNodeWithVectorization
  currentStatus?: string
  errors: VectorizationError[]
}
```

### State Transitions

```typescript
// Vectorization State Machine
type VectorizationState =
  | 'not-vectorized'
  | 'vectorizing'
  | 'vectorized'
  | 'failed'

const transitions: Record<VectorizationState, VectorizationState[]> = {
  'not-vectorized': ['vectorizing'],
  'vectorizing': ['vectorized', 'failed'],
  'vectorized': ['vectorizing'], // Re-vectorization
  'failed': ['vectorizing']       // Retry
}

// State update function
function updateVectorizationStatus(
  nodeId: string,
  newStatus: VectorizationState,
  additionalData?: Partial<VectorizationStatus>
) {
  const currentStatus = vectorizationStatus.value.get(nodeId)?.status || 'not-vectorized'

  // Validate transition
  if (!transitions[currentStatus].includes(newStatus)) {
    console.error(`Invalid transition: ${currentStatus} → ${newStatus}`)
    return
  }

  // Update state
  vectorizationStatus.value.set(nodeId, {
    status: newStatus,
    lastVectorized: newStatus === 'vectorized' ? new Date() : undefined,
    ...additionalData
  })

  // Update tree node
  updateTreeNode(nodeId, { vectorizationStatus: newStatus })
}
```

### Reactive Computed Properties

```typescript
// Computed values for UI
const selectedCount = computed(() => selectedNodes.value.size)

const canVectorizeSelected = computed(() => {
  if (selectedNodes.value.size === 0) return false

  return Array.from(selectedNodes.value).every(nodeId => {
    const status = vectorizationStatus.value.get(nodeId)
    return status?.status !== 'vectorizing'
  })
})

const overallProgress = computed(() => {
  if (batchProgress.value.total === 0) return 0
  return Math.round((batchProgress.value.completed / batchProgress.value.total) * 100)
})

const hasFailedVectorizations = computed(() => {
  return Array.from(vectorizationStatus.value.values())
    .some(status => status.status === 'failed')
})
```

---

## 7. API Integration

### New API Endpoint Needed

```typescript
// POST /api/knowledge_base/vectorize_document
interface VectorizeDocumentRequest {
  document_id: string
  document_path: string
  category: string
  force?: boolean  // Re-vectorize even if already vectorized
}

interface VectorizeDocumentResponse {
  status: 'success' | 'error'
  message: string
  document_id: string
  vector_id?: string
  vectorized_at?: string
  error?: string
}
```

### API Service Methods

```typescript
// useKnowledgeBase.ts additions

/**
 * Vectorize a single document
 */
const vectorizeDocument = async (
  documentId: string,
  documentPath: string,
  category: string,
  force: boolean = false
): Promise<VectorizeDocumentResponse> => {
  try {
    const response = await apiClient.post('/api/knowledge_base/vectorize_document', {
      document_id: documentId,
      document_path: documentPath,
      category: category,
      force: force
    })
    const data = await response.json()
    return data
  } catch (error) {
    console.error('Error vectorizing document:', error)
    throw error
  }
}

/**
 * Get vectorization status for multiple documents
 */
const getVectorizationStatuses = async (
  documentIds: string[]
): Promise<Map<string, VectorizationStatus>> => {
  try {
    const response = await apiClient.post('/api/knowledge_base/vectorization_status', {
      document_ids: documentIds
    })
    const data = await response.json()

    // Convert to Map
    const statusMap = new Map<string, VectorizationStatus>()
    data.statuses.forEach((item: any) => {
      statusMap.set(item.document_id, {
        status: item.status,
        vectorId: item.vector_id,
        lastVectorized: item.last_vectorized ? new Date(item.last_vectorized) : undefined,
        error: item.error
      })
    })

    return statusMap
  } catch (error) {
    console.error('Error fetching vectorization statuses:', error)
    throw error
  }
}

/**
 * Batch vectorize multiple documents
 */
const batchVectorizeDocuments = async (
  documents: Array<{ id: string, path: string, category: string }>,
  onProgress?: (progress: BatchProgress) => void
): Promise<BatchVectorizationResult> => {
  const results: BatchVectorizationResult = {
    total: documents.length,
    success: 0,
    failed: 0,
    skipped: 0,
    errors: []
  }

  for (let i = 0; i < documents.length; i++) {
    const doc = documents[i]

    try {
      // Update progress callback
      if (onProgress) {
        onProgress({
          total: documents.length,
          completed: i,
          successCount: results.success,
          failedCount: results.failed,
          skippedCount: results.skipped,
          currentDocument: doc,
          currentStatus: `Vectorizing ${doc.path}...`,
          errors: results.errors
        })
      }

      // Vectorize document
      const response = await vectorizeDocument(doc.id, doc.path, doc.category)

      if (response.status === 'success') {
        results.success++
      } else {
        results.failed++
        results.errors.push({
          documentId: doc.id,
          documentName: doc.path,
          message: response.error || 'Unknown error'
        })
      }
    } catch (error: any) {
      results.failed++
      results.errors.push({
        documentId: doc.id,
        documentName: doc.path,
        message: error.message || 'Network error'
      })
    }

    // Small delay between requests to prevent overwhelming the server
    if (i < documents.length - 1) {
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }

  // Final progress update
  if (onProgress) {
    onProgress({
      total: documents.length,
      completed: documents.length,
      successCount: results.success,
      failedCount: results.failed,
      skippedCount: results.skipped,
      currentDocument: undefined,
      currentStatus: 'Complete',
      errors: results.errors
    })
  }

  return results
}

interface BatchVectorizationResult {
  total: number
  success: number
  failed: number
  skipped: number
  errors: VectorizationError[]
}
```

### API Error Handling

```typescript
// Error types and handling
enum VectorizationErrorType {
  NETWORK_ERROR = 'network_error',
  INVALID_DOCUMENT = 'invalid_document',
  ALREADY_VECTORIZED = 'already_vectorized',
  PROCESSING_ERROR = 'processing_error',
  TIMEOUT = 'timeout',
  QUOTA_EXCEEDED = 'quota_exceeded'
}

interface VectorizationErrorDetails {
  type: VectorizationErrorType
  message: string
  retryable: boolean
  retryAfter?: number  // Seconds to wait before retry
}

function handleVectorizationError(error: any): VectorizationErrorDetails {
  // Network errors
  if (error.name === 'TypeError' || error.message.includes('fetch')) {
    return {
      type: VectorizationErrorType.NETWORK_ERROR,
      message: 'Network connection failed. Please check your internet connection.',
      retryable: true,
      retryAfter: 5
    }
  }

  // API errors
  if (error.response) {
    const status = error.response.status
    const data = error.response.data

    switch (status) {
      case 400:
        return {
          type: VectorizationErrorType.INVALID_DOCUMENT,
          message: data.message || 'Invalid document format',
          retryable: false
        }

      case 409:
        return {
          type: VectorizationErrorType.ALREADY_VECTORIZED,
          message: 'Document is already vectorized',
          retryable: false
        }

      case 429:
        return {
          type: VectorizationErrorType.QUOTA_EXCEEDED,
          message: 'Rate limit exceeded. Please wait before retrying.',
          retryable: true,
          retryAfter: parseInt(error.response.headers['retry-after'] || '60')
        }

      case 504:
        return {
          type: VectorizationErrorType.TIMEOUT,
          message: 'Vectorization timed out. Please try again.',
          retryable: true,
          retryAfter: 10
        }

      default:
        return {
          type: VectorizationErrorType.PROCESSING_ERROR,
          message: data.message || 'Failed to vectorize document',
          retryable: true,
          retryAfter: 5
        }
    }
  }

  // Unknown errors
  return {
    type: VectorizationErrorType.PROCESSING_ERROR,
    message: error.message || 'An unexpected error occurred',
    retryable: true,
    retryAfter: 5
  }
}
```

---

## 8. Accessibility

### ARIA Attributes

```html
<!-- Vectorization Status Badge -->
<span
  class="vectorization-badge"
  role="status"
  aria-live="polite"
  :aria-label="ariaStatusLabel"
>
  <i :class="statusIcon" aria-hidden="true"></i>
  <span>{{ statusLabel }}</span>
</span>

<!-- Vectorization Action Button -->
<button
  class="vectorize-btn"
  :aria-label="ariaActionLabel"
  :aria-disabled="disabled"
  :aria-busy="isVectorizing"
  @click="handleVectorize"
>
  <i :class="actionIcon" aria-hidden="true"></i>
</button>

<!-- Selection Checkbox -->
<input
  type="checkbox"
  :id="`select-${node.id}`"
  :aria-label="`Select ${node.name}`"
  :checked="isSelected"
  @change="toggleSelection"
/>
<label :for="`select-${node.id}`" class="sr-only">
  Select {{ node.name }} for batch vectorization
</label>

<!-- Batch Toolbar -->
<div
  class="batch-toolbar"
  role="toolbar"
  aria-label="Batch vectorization controls"
>
  <!-- Toolbar buttons with aria-labels -->
</div>

<!-- Progress Modal -->
<div
  class="modal-overlay"
  role="dialog"
  aria-modal="true"
  aria-labelledby="modal-title"
  aria-describedby="modal-description"
>
  <h3 id="modal-title">Vectorizing Documents</h3>
  <div id="modal-description" class="sr-only">
    Progress dialog showing vectorization status for {{ total }} documents.
    {{ completed }} completed, {{ successCount }} successful, {{ failedCount }} failed.
  </div>
</div>
```

### Screen Reader Announcements

```typescript
// Announcement utility
const announceToScreenReader = (message: string, priority: 'polite' | 'assertive' = 'polite') => {
  const announcement = document.createElement('div')
  announcement.setAttribute('role', 'status')
  announcement.setAttribute('aria-live', priority)
  announcement.setAttribute('aria-atomic', 'true')
  announcement.className = 'sr-only'
  announcement.textContent = message

  document.body.appendChild(announcement)

  setTimeout(() => {
    document.body.removeChild(announcement)
  }, 1000)
}

// Usage examples
announceToScreenReader('Vectorization started for document.md')
announceToScreenReader('Vectorization complete. 5 documents processed successfully.')
announceToScreenReader('Vectorization failed. Please check errors.', 'assertive')
```

### Keyboard Navigation

```typescript
// Enhanced tree navigation with vectorization actions
const handleKeyDown = (event: KeyboardEvent, node: TreeNodeWithVectorization) => {
  switch (event.key) {
    case 'Enter':
      // Trigger vectorization on focused file
      if (node.type === 'file' && node.vectorizationStatus !== 'vectorizing') {
        event.preventDefault()
        handleVectorize(node)
      }
      break

    case ' ': // Space
      // Toggle selection
      if (selectionMode.value && node.type === 'file') {
        event.preventDefault()
        toggleSelection(node.id)
      }
      break

    case 'v':
      // Quick vectorize shortcut (when Ctrl is pressed)
      if (event.ctrlKey && node.type === 'file') {
        event.preventDefault()
        if (selectedNodes.value.size > 0) {
          handleBatchVectorize()
        } else {
          handleVectorize(node)
        }
      }
      break

    case 'Escape':
      // Exit selection mode or close modal
      event.preventDefault()
      if (showProgressModal.value) {
        handleCancelBatch()
      } else if (selectionMode.value) {
        exitSelectionMode()
      }
      break
  }
}
```

### Focus Management

```typescript
// Focus management for modals and dynamic content
const manageFocus = {
  // Save focus before opening modal
  saveFocus() {
    this.previousFocus = document.activeElement as HTMLElement
  },

  // Focus first interactive element in modal
  focusModal() {
    const modal = document.querySelector('.modal-container')
    const firstButton = modal?.querySelector('button')
    firstButton?.focus()
  },

  // Restore focus after modal closes
  restoreFocus() {
    this.previousFocus?.focus()
  },

  // Trap focus within modal
  trapFocus(event: KeyboardEvent) {
    const modal = document.querySelector('.modal-container')
    const focusableElements = modal?.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )

    if (!focusableElements || focusableElements.length === 0) return

    const firstElement = focusableElements[0] as HTMLElement
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement

    if (event.key === 'Tab') {
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault()
        lastElement.focus()
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault()
        firstElement.focus()
      }
    }
  }
}
```

### Color Contrast Compliance

```css
/* WCAG AAA Compliance (7:1 contrast ratio for normal text) */

/* Text Colors */
.tree-node-name {
  color: #1f2937; /* Against white: 16.1:1 ✓ */
}

.status-label {
  color: #374151; /* Against white: 12.6:1 ✓ */
}

/* Status Badge Backgrounds (ensure text readability) */
.vectorization-badge.vectorized {
  background: #d1fae5; /* Light green */
  color: #065f46;      /* Dark green - 7.4:1 ✓ */
}

.vectorization-badge.failed {
  background: #fee2e2; /* Light red */
  color: #991b1b;      /* Dark red - 7.7:1 ✓ */
}

/* Interactive Elements (4.5:1 minimum for UI components) */
.vectorize-btn {
  color: #1e40af;      /* Blue-800 - 8.6:1 against white ✓ */
  border: 2px solid currentColor; /* Thick border for better visibility */
}

.vectorize-btn:focus-visible {
  outline: 3px solid #3b82f6;
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
}
```

---

## 9. Mobile & Responsive

### Breakpoint Strategy

```typescript
const BREAKPOINTS = {
  mobile: '0px',      // 0-639px
  tablet: '640px',    // 640-1023px
  desktop: '1024px',  // 1024px+
  wide: '1280px'      // 1280px+
}
```

### Mobile-First Layout Adaptations

#### Mobile (< 640px)

```css
@media (max-width: 639px) {
  /* Simplify tree item layout */
  .tree-node-content {
    flex-wrap: wrap;
    padding: 0.75rem 0.5rem;
  }

  /* Stack status and action */
  .tree-node-right {
    flex-basis: 100%;
    margin-top: 0.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  /* Larger touch targets */
  .vectorize-btn {
    width: 2.5rem;
    height: 2.5rem;
    font-size: 1.125rem;
  }

  .selection-checkbox {
    width: 1.25rem;
    height: 1.25rem;
  }

  /* Full-width batch toolbar */
  .batch-toolbar {
    flex-direction: column;
    gap: 0.75rem;
    padding: 1rem;
  }

  .toolbar-left,
  .toolbar-right {
    width: 100%;
    justify-content: center;
  }

  /* Full-screen modal on mobile */
  .modal-container {
    width: 100%;
    max-width: none;
    height: 100vh;
    max-height: none;
    border-radius: 0;
  }

  /* Hide status labels, show icons only */
  .vectorization-badge span {
    display: none;
  }

  .vectorization-badge {
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    justify-content: center;
  }
}
```

#### Tablet (640px - 1023px)

```css
@media (min-width: 640px) and (max-width: 1023px) {
  /* Compact batch toolbar */
  .batch-toolbar {
    padding: 0.75rem 1rem;
  }

  .toolbar-btn {
    padding: 0.375rem 0.75rem;
    font-size: 0.8125rem;
  }

  /* Abbreviated status labels */
  .vectorization-badge {
    font-size: 0.625rem;
    padding: 0.125rem 0.375rem;
  }

  /* Modal size adjustment */
  .modal-container {
    width: 95%;
    max-width: 500px;
  }
}
```

### Touch Interactions

```typescript
// Enhanced touch support
const touchHandlers = {
  // Long-press to enter selection mode
  longPressTimer: null as NodeJS.Timeout | null,
  longPressDelay: 500, // ms

  handleTouchStart(event: TouchEvent, node: TreeNodeWithVectorization) {
    this.longPressTimer = setTimeout(() => {
      // Enter selection mode and select this item
      if (!selectionMode.value) {
        selectionMode.value = true
        announceToScreenReader('Selection mode activated')
      }
      toggleSelection(node.id)

      // Haptic feedback if available
      if ('vibrate' in navigator) {
        navigator.vibrate(50)
      }
    }, this.longPressDelay)
  },

  handleTouchEnd() {
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer)
      this.longPressTimer = null
    }
  },

  handleTouchMove() {
    // Cancel long-press if user moves finger
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer)
      this.longPressTimer = null
    }
  },

  // Swipe actions for mobile
  swipeStart: { x: 0, y: 0 },
  swipeThreshold: 50, // px

  handleSwipeStart(event: TouchEvent) {
    const touch = event.touches[0]
    this.swipeStart = { x: touch.clientX, y: touch.clientY }
  },

  handleSwipeEnd(event: TouchEvent, node: TreeNodeWithVectorization) {
    const touch = event.changedTouches[0]
    const deltaX = touch.clientX - this.swipeStart.x
    const deltaY = Math.abs(touch.clientY - this.swipeStart.y)

    // Horizontal swipe with minimal vertical movement
    if (Math.abs(deltaX) > this.swipeThreshold && deltaY < 30) {
      if (deltaX > 0) {
        // Swipe right → Select
        toggleSelection(node.id)
      } else {
        // Swipe left → Vectorize
        handleVectorize(node)
      }

      // Haptic feedback
      if ('vibrate' in navigator) {
        navigator.vibrate(25)
      }
    }
  }
}
```

### Responsive Progress Modal

```css
@media (max-width: 639px) {
  .modal-body {
    padding: 1rem;
  }

  /* Stack results grid on mobile */
  .results-grid {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  .result-stat {
    flex-direction: row;
    justify-content: space-between;
    padding: 0.75rem;
  }

  .result-stat i {
    font-size: 1.25rem;
  }

  /* Scrollable error list */
  .error-list {
    max-height: 200px;
    overflow-y: auto;
  }

  /* Full-width modal footer buttons */
  .modal-footer {
    padding: 1rem;
  }

  .modal-footer button {
    width: 100%;
  }
}
```

### Pull-to-Refresh for Mobile

```typescript
// Pull-to-refresh to reload vectorization statuses
const pullToRefresh = {
  startY: 0,
  currentY: 0,
  pullThreshold: 80,
  refreshing: false,

  handleTouchStart(event: TouchEvent) {
    // Only at top of scroll
    const scrollTop = document.querySelector('.tree-pane')?.scrollTop
    if (scrollTop === 0) {
      this.startY = event.touches[0].clientY
    }
  },

  handleTouchMove(event: TouchEvent) {
    if (this.startY === 0) return

    this.currentY = event.touches[0].clientY
    const pullDistance = this.currentY - this.startY

    if (pullDistance > 0 && pullDistance < this.pullThreshold) {
      // Show pull indicator
      document.querySelector('.pull-indicator')?.classList.add('active')

      // Update indicator height
      const indicator = document.querySelector('.pull-indicator') as HTMLElement
      if (indicator) {
        indicator.style.height = `${pullDistance}px`
      }
    }
  },

  async handleTouchEnd() {
    const pullDistance = this.currentY - this.startY

    if (pullDistance >= this.pullThreshold && !this.refreshing) {
      this.refreshing = true

      // Show refreshing state
      document.querySelector('.pull-indicator')?.classList.add('refreshing')

      // Refresh data
      await refreshVectorizationStatuses()

      // Reset
      setTimeout(() => {
        document.querySelector('.pull-indicator')?.classList.remove('active', 'refreshing')
        this.refreshing = false
      }, 500)
    } else {
      // Snap back
      document.querySelector('.pull-indicator')?.classList.remove('active')
    }

    this.startY = 0
    this.currentY = 0
  }
}
```

---

## 10. Implementation Roadmap

### Phase 1: Foundation (Week 1)
**Goal**: Basic UI components and status display

- [ ] **Day 1-2**: Create `VectorizationStatusBadge.vue`
  - Implement all 4 status variants
  - Add CSS animations
  - Add tooltips with error details

- [ ] **Day 3-4**: Create `VectorizationActionButton.vue`
  - Implement vectorize/retry actions
  - Add loading states
  - Wire up basic API calls

- [ ] **Day 5**: Integrate into `TreeNodeComponent`
  - Add badge to file items
  - Add action button to file items
  - Update layout to accommodate new elements

**Deliverable**: Individual documents show vectorization status and have clickable vectorize buttons

---

### Phase 2: Batch Selection (Week 2)
**Goal**: Multi-select and batch processing

- [ ] **Day 1-2**: Add selection state to tree nodes
  - Implement checkbox UI
  - Add selection mode toggle
  - Implement multi-select logic (Shift+Click, Ctrl+Click)

- [ ] **Day 3-4**: Create `BatchSelectionToolbar.vue`
  - Implement toolbar design
  - Add select all/deselect all
  - Add batch action buttons

- [ ] **Day 5**: Wire up batch vectorization
  - Implement batch API calls
  - Add progress tracking
  - Handle errors in batch context

**Deliverable**: Users can select multiple documents and vectorize them in batch

---

### Phase 3: Progress & Feedback (Week 3)
**Goal**: Rich progress visualization and error handling

- [ ] **Day 1-3**: Create `VectorizationProgressModal.vue`
  - Implement modal layout
  - Add progress bars and counters
  - Add current document display
  - Add results summary

- [ ] **Day 4**: Error handling and retry logic
  - Implement error state UI
  - Add retry buttons
  - Add error detail tooltips

- [ ] **Day 5**: Toast notifications
  - Success notifications
  - Error notifications
  - Batch completion summary

**Deliverable**: Users see detailed progress and can handle errors gracefully

---

### Phase 4: Accessibility & Polish (Week 4)
**Goal**: WCAG compliance and UX refinement

- [ ] **Day 1-2**: Accessibility implementation
  - Add all ARIA attributes
  - Implement keyboard shortcuts
  - Add screen reader announcements
  - Test with screen readers

- [ ] **Day 3**: Mobile responsive design
  - Implement mobile layouts
  - Add touch interactions
  - Test on various devices

- [ ] **Day 4**: Performance optimization
  - Virtualize large tree lists
  - Optimize re-renders
  - Add debouncing/throttling

- [ ] **Day 5**: Final polish
  - Animation refinements
  - Color contrast validation
  - Cross-browser testing
  - Documentation

**Deliverable**: Production-ready, accessible, performant vectorization UI

---

### Phase 5: Advanced Features (Week 5)
**Goal**: Enhanced UX and power user features

- [ ] **Day 1**: Keyboard shortcuts refinement
  - Add shortcut help modal
  - Implement command palette integration

- [ ] **Day 2**: Bulk operations
  - Vectorize all in category
  - Vectorize all non-vectorized
  - Re-vectorize all

- [ ] **Day 3**: Filtering and search
  - Filter by vectorization status
  - Search within vectorized documents

- [ ] **Day 4**: Analytics and insights
  - Vectorization coverage stats
  - Performance metrics
  - Cost estimation (if applicable)

- [ ] **Day 5**: User preferences
  - Remember selection mode preference
  - Auto-vectorize new uploads toggle
  - Batch size preferences

**Deliverable**: Power user features for advanced workflows

---

## Success Metrics

### User Experience Metrics
- ✅ **Clarity**: Users understand vectorization status at a glance (95%+ in user testing)
- ✅ **Efficiency**: Single-click vectorization for individual documents
- ✅ **Batch Speed**: Process 100 documents in < 5 minutes
- ✅ **Error Recovery**: 100% of failed vectorizations have clear retry path

### Accessibility Metrics
- ✅ **WCAG AAA Compliance**: All contrast ratios meet 7:1 threshold
- ✅ **Keyboard Navigation**: All actions accessible via keyboard
- ✅ **Screen Reader**: 100% of UI states announced correctly
- ✅ **Touch Targets**: Minimum 44px × 44px on mobile

### Performance Metrics
- ✅ **Initial Load**: Vectorization status loads in < 500ms
- ✅ **UI Responsiveness**: All interactions < 100ms response time
- ✅ **Large Lists**: 60fps scrolling with 1000+ documents

### Technical Metrics
- ✅ **Code Coverage**: 80%+ test coverage for vectorization logic
- ✅ **API Error Rate**: < 1% error rate for vectorization calls
- ✅ **Bundle Size**: < 50KB addition to bundle size

---

## Appendix: Component Code Templates

### A. Enhanced TreeNodeComponent with Vectorization

```vue
<script setup lang="ts">
import { computed } from 'vue'
import VectorizationStatusBadge from './VectorizationStatusBadge.vue'
import VectorizationActionButton from './VectorizationActionButton.vue'

interface Props {
  node: TreeNodeWithVectorization
  expandedNodes: Set<string>
  selectedId?: string
  selectionMode?: boolean
  selected?: boolean
}

interface Emits {
  (e: 'toggle', nodeId: string): void
  (e: 'select', node: TreeNodeWithVectorization): void
  (e: 'toggleSelection', nodeId: string): void
  (e: 'vectorize', payload: { nodeId: string, path: string }): void
  (e: 'retry', payload: { nodeId: string, path: string }): void
}

const props = withDefaults(defineProps<Props>(), {
  selectionMode: false,
  selected: false
})

const emit = defineEmits<Emits>()

const isExpanded = computed(() => {
  return props.node.type === 'folder' && props.expandedNodes.has(props.node.id)
})

const getNodeIcon = computed(() => {
  if (props.node.type === 'folder') {
    return isExpanded.value ? 'fas fa-folder-open' : 'fas fa-folder'
  }
  return 'fas fa-file-alt'
})
</script>

<template>
  <div class="tree-node">
    <div
      class="node-content"
      :class="{
        'is-folder': node.type === 'folder',
        'is-file': node.type === 'file',
        'is-expanded': isExpanded,
        'is-selected': node.id === selectedId || selected
      }"
      @click="emit('select', node)"
    >
      <!-- Selection Checkbox (Files only, when in selection mode) -->
      <input
        v-if="selectionMode && node.type === 'file'"
        type="checkbox"
        class="selection-checkbox"
        :checked="selected"
        :aria-label="`Select ${node.name}`"
        @click.stop
        @change="emit('toggleSelection', node.id)"
      />

      <!-- Expand Button (Folders only) -->
      <button
        v-if="node.type === 'folder'"
        class="expand-btn"
        :aria-label="isExpanded ? 'Collapse folder' : 'Expand folder'"
        @click.stop="emit('toggle', node.id)"
      >
        <i :class="['fas', isExpanded ? 'fa-chevron-down' : 'fa-chevron-right']"></i>
      </button>
      <span v-else class="expand-spacer"></span>

      <!-- Node Icon -->
      <i :class="['node-icon', getNodeIcon]"></i>

      <!-- Node Name -->
      <span class="node-name">{{ node.name }}</span>

      <!-- File Size (Files only) -->
      <span v-if="node.type === 'file' && node.size" class="node-size">
        {{ formatFileSize(node.size) }}
      </span>

      <!-- Folder Count (Folders only) -->
      <span v-if="node.type === 'folder' && node.children" class="folder-count">
        {{ node.children.length }} items
      </span>

      <!-- Vectorization Status Badge (Files only) -->
      <VectorizationStatusBadge
        v-if="node.type === 'file' && node.vectorizationStatus"
        :status="node.vectorizationStatus"
        :show-label="true"
        :compact="false"
      />

      <!-- Vectorization Action Button (Files only) -->
      <VectorizationActionButton
        v-if="node.type === 'file'"
        :status="node.vectorizationStatus || 'not-vectorized'"
        :node-id="node.id"
        :node-path="node.path"
        :show-label="false"
        @vectorize="emit('vectorize', $event)"
        @retry="emit('retry', $event)"
      />
    </div>

    <!-- Children (Folders only, when expanded) -->
    <div
      v-if="node.type === 'folder' && isExpanded && node.children"
      class="node-children"
    >
      <TreeNodeComponent
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :expanded-nodes="expandedNodes"
        :selected-id="selectedId"
        :selection-mode="selectionMode"
        :selected="selected"
        @toggle="emit('toggle', $event)"
        @select="emit('select', $event)"
        @toggle-selection="emit('toggleSelection', $event)"
        @vectorize="emit('vectorize', $event)"
        @retry="emit('retry', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.node-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  border-radius: 0.375rem;
  transition: all 0.15s;
}

.node-content:hover {
  background: #f3f4f6;
}

.node-content.is-selected {
  background: #eff6ff;
  color: #3b82f6;
  font-weight: 500;
}

.selection-checkbox {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
}

.expand-btn {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  padding: 0;
  transition: transform 0.2s;
}

.expand-btn:hover {
  color: #374151;
}

.expand-spacer {
  width: 1.25rem;
}

.node-icon {
  color: #3b82f6;
  font-size: 0.875rem;
  min-width: 1rem;
}

.node-name {
  flex: 1;
  font-size: 0.875rem;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-size,
.folder-count {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-left: 0.5rem;
}

.node-children {
  padding-left: 1.5rem;
}
</style>
```

---

## End of Specification

**Document Version**: 1.0
**Last Updated**: 2025-10-02
**Next Review**: After Phase 1 completion

For implementation questions or design clarifications, refer to:
- **Frontend Standards**: `/docs/developer/PHASE_5_DEVELOPER_SETUP.md`
- **API Documentation**: `/docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`
- **Accessibility Guidelines**: WCAG 2.1 AAA Standards
