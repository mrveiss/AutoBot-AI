# AutoBot Knowledge Base GUI - Comprehensive Test Plan

**Generated:** 2025-10-03
**Target Frontend:** http://172.16.168.21:5173
**Target Backend:** http://172.16.168.20:8001

## Table of Contents

1. [Expected Functionality Analysis](#expected-functionality-analysis)
2. [Predicted Issues & Error Scenarios](#predicted-issues--error-scenarios)
3. [Test Coverage Gaps](#test-coverage-gaps)
4. [Critical User Workflows](#critical-user-workflows)
5. [Recommended Test Suite](#recommended-test-suite)
6. [Manual Testing Checklist](#manual-testing-checklist)

---

## 1. Expected Functionality Analysis

### 1.1 Knowledge Manager Component (Main Container)

**File:** `autobot-vue/src/components/knowledge/KnowledgeManager.vue`

**Expected Features:**
- Tab navigation system with 6 tabs:
  - Search - Semantic and RAG search
  - Categories - Knowledge organization browser
  - Upload - File/URL/text upload
  - Manage - Document management interface
  - Statistics - Knowledge base metrics
  - Advanced - System knowledge actions
- Lazy loading of heavy components
- Error boundary fallback handling
- Persistent tab state via Pinia store

**Critical Integration Points:**
- `useKnowledgeStore()` - Central state management
- Dynamic component loading for performance
- Tab synchronization across sessions

### 1.2 Search Tab (KnowledgeSearch.vue)

**Expected Features:**
- **Dual search modes:**
  - Traditional semantic search (vector-based)
  - RAG-enhanced AI synthesis search
- **Search interface:**
  - Real-time query input with Enter key support
  - Search mode toggle (Traditional ↔ RAG)
  - Results limit selector (5/10/15/20)
  - Query auto-enhancement option
- **Results display:**
  - Match score indicators (color-coded: high/medium/low)
  - Document type and category badges
  - Content highlights/snippets
  - AI synthesis response (RAG mode)
  - Confidence scores and source citations
  - Query reformulation display
- **Error handling:**
  - RAG unavailable fallback to traditional search
  - Empty results with actionable suggestions
  - Network error recovery

**API Dependencies:**
- `/api/knowledge_base/rag_search` (RAG mode)
- `/api/knowledge_base/search` (traditional)
- `KnowledgeRepository.ragSearch()`
- `KnowledgeRepository.searchKnowledge()`

**Predicted Console Errors:**
```javascript
// RAG not available
"RAG functionality is currently unavailable"

// Search failure
"Knowledge search failed: [error]"

// Empty document access
"Cannot read property 'title' of undefined"
"Cannot read property 'score' of undefined"
```

### 1.3 Categories Tab (KnowledgeCategories.vue)

**Expected Features:**
- **AutoBot Knowledge Browser:**
  - File system tree navigation
  - Per-host knowledge organization
  - Document preview panel
- **Category display:**
  - Dynamic category loading from backend
  - Document counts per category
  - Category icons and metadata
- **Document viewer:**
  - Modal document display
  - Metadata preview (path, type, size)
  - Content preview (first 2000 chars)
- **User Categories (hidden but exists):**
  - Custom category creation/editing
  - Color picker for categories
  - Document assignment to categories

**API Dependencies:**
- `/api/knowledge_base/categories`
- `/api/knowledge_base/stats/basic`
- `/api/knowledge_base/facts/by_category`

**Predicted Issues:**
- Category counts mismatch with actual documents
- Undefined category paths causing crashes
- Modal stacking (multiple modals open simultaneously)
- Teleport accumulation on unmount

### 1.4 Upload Tab (KnowledgeUpload.vue)

**Expected Features:**
- **Text Entry Method:**
  - Title input (optional)
  - Content textarea with character counter
  - Category selection dropdown
  - Tags input (comma-separated)
  - Add to KB button (disabled when empty)
- **URL Import Method:**
  - URL validation (must be valid URL)
  - Category and tags support
  - Import progress indicator
  - Content fetching simulation
- **File Upload Method:**
  - Drag-and-drop zone
  - File browser button
  - Multiple file support
  - File type validation (.txt, .md, .pdf, .doc, .docx, .json, .csv)
  - 10MB size limit per file
  - File list with remove buttons
  - Batch category and tags
  - Upload progress bar
- **Feedback System:**
  - Success messages (auto-dismiss 3s)
  - Error messages (persistent)
  - Progress tracking with percentages

**API Dependencies:**
- `/api/knowledge_base/add_text`
- `useKnowledgeController.addTextDocument()`
- `useKnowledgeController.addUrlDocument()`
- `useKnowledgeController.addFileDocument()`

**Predicted Issues:**
```javascript
// Controller not initialized
"Controller not available"

// Upload failures
"Failed to add text entry"
"Failed to import URL"
"Failed to upload files"

// Validation errors
"File 'example.exe' is too large (max 10MB)"
"Text content is required"
```

### 1.5 Manage Tab (KnowledgeEntries.vue)

**Expected Features:**
- **Sub-tab Navigation:**
  - Upload sub-tab (reuses KnowledgeUpload component)
  - Manage sub-tab (document CRUD)
  - Advanced sub-tab (SystemKnowledgeManager)
- **Document Management (Manage sub-tab):**
  - Search/filter bar
  - Category and type filters
  - Sort options (updated/created/title/category)
  - Batch selection with checkboxes
  - Export selected (JSON format)
  - Delete selected (with confirmation)
  - Pagination (20 items per page)
- **Document Table:**
  - Title (clickable to view)
  - Category badge
  - Type icon + label
  - Tags (first 3 + count)
  - Updated date
  - Actions (view/edit/delete buttons)
- **View/Edit Modal:**
  - View mode: Full metadata + content
  - Edit mode: All fields editable
  - Switch between modes
  - Save changes functionality

**API Dependencies:**
- `useKnowledgeController.loadAllDocuments()`
- `useKnowledgeController.deleteDocument()`
- `useKnowledgeController.bulkDeleteDocuments()`
- `useKnowledgeController.updateDocument()`

**Predicted Issues:**
- Controller methods returning `undefined`
- Pagination reset on filter changes
- Selection state not cleared after bulk delete
- Modal not closing after edit
- Content formatting breaking on special characters

### 1.6 Statistics Tab (KnowledgeStats.vue)

**Expected Features:**
- **Vector Database Statistics:**
  - Total facts count
  - Total vectors count
  - Database size
  - Status indicator (online/offline)
  - RAG availability flag
  - Vectorization notice (if needed)
- **Vector Health Indicators:**
  - Initialized status
  - LlamaIndex configured
  - LangChain integration
  - Index availability
  - RAG availability
- **Vector Details:**
  - Redis DB number
  - Index name
  - Embedding model + dimensions
  - Last updated timestamp
  - Indexed documents count
- **Category Distribution Chart:**
  - Horizontal bar chart by category
  - Fact counts per category
  - Percentage calculations
- **Overview Cards:**
  - Total documents
  - Categories count
  - Unique tags
  - Storage used
- **Charts:**
  - Documents by category (bar chart)
  - Documents by type (pie chart breakdown)
- **Recent Activity Timeline:**
  - Last 10 document operations
  - Activity icons (created/updated/deleted)
  - Relative timestamps
- **Popular Tags Cloud:**
  - Top 30 tags
  - Size based on usage frequency
- **Action Buttons:**
  - Export statistics (JSON)
  - Optimize database
  - Generate report (Markdown)

**API Dependencies:**
- `/api/knowledge_base/stats`
- `/api/knowledge_base/stats/basic`
- `/api/knowledge_base/facts/by_category`
- `useKnowledgeController.refreshStats()`
- `useKnowledgeController.getDetailedStats()`

**Predicted Issues:**
```javascript
// Controller not available
"Controller refreshStats method not available"
"Controller getDetailedStats method not available"

// Stats calculation
"Cannot read property 'total_facts' of null"
"categoryCounts is undefined"

// Division by zero
"NaN%" in percentage displays
```

### 1.7 Advanced Tab (SystemKnowledgeManager component)

**Expected Features:**
- **System Knowledge Operations:**
  - Initialize Machine Knowledge
  - Reindex Knowledge Base
  - Populate Man Pages
  - Populate AutoBot Docs
  - Refresh System Knowledge
  - Start Background Vectorization
- **Per-host operations:**
  - Host selection dropdown
  - Host-specific initialization
  - Force re-initialization option
- **Progress tracking:**
  - Current task display
  - Overall progress bar
  - Task-specific progress
  - Status messages
  - Error/success indicators

**API Dependencies:**
- `/api/knowledge_base/machine_knowledge/initialize`
- `/api/knowledge_base/man_pages/integrate`
- `/api/knowledge_base/populate_man_pages`
- `/api/knowledge_base/populate_autobot_docs`
- `/api/knowledge_base/refresh_system_knowledge`
- `/api/knowledge_base/vectorize_facts/background`
- `/api/knowledge_base/vectorize_facts/status`

**Predicted Issues:**
- Long-running operations timing out
- Progress updates not received
- Background tasks not visible
- Host selection state not persisting

---

## 2. Predicted Issues & Error Scenarios

### 2.1 Reactive State Issues

**Problem:** Promise objects displayed as `[object Promise]`
- **Location:** Categories, Stats tabs
- **Cause:** Async functions not awaited before rendering
- **Expected Error:**
  ```javascript
  // Template renders before data loads
  {{ stats }} // Shows: [object Promise]
  ```

**Solution Test:**
```javascript
// Verify all async calls use await or .then()
const stats = await fetchStats()
// NOT: const stats = fetchStats()
```

### 2.2 API Response Handling

**Problem:** Undefined property access
- **Location:** All components making API calls
- **Cause:** Response structure changes or null responses
- **Expected Errors:**
  ```javascript
  "Cannot read property 'results' of undefined"
  "Cannot read property 'categories' of null"
  "Cannot destructure property 'document' of 'undefined'"
  ```

**Test Coverage Needed:**
- Empty response handling
- Null/undefined checks
- Default value fallbacks
- Loading states

### 2.3 Component Lifecycle Issues

**Problem:** Modal/teleport accumulation
- **Location:** Categories tab (document modals)
- **Cause:** Missing cleanup in `onUnmounted`
- **Evidence:** Code has cleanup implemented (lines 459-473)
- **Test:** Verify modals close properly and don't accumulate in DOM

### 2.4 Data Flow Issues

**Problem:** Controller methods undefined
- **Location:** Stats, Entries tabs
- **Cause:** Defensive initialization with fallback mock (lines 342-354 in Stats)
- **Expected Console Warnings:**
  ```javascript
  "Controller not available"
  "Controller refreshStats method not available"
  ```

**Test Coverage Needed:**
- Verify controller initialization
- Test mock fallback behavior
- Validate all controller methods exist

### 2.5 Search Functionality Issues

**Problem:** RAG search fallback
- **Location:** Search tab
- **Behavior:** Falls back to traditional search if RAG fails
- **Expected Flow:**
  1. Try RAG search
  2. Catch error → set ragError
  3. Fallback to traditional search
  4. Display results with warning

**Test Scenarios:**
- RAG available and working
- RAG unavailable (backend not configured)
- RAG timeout
- Traditional search also fails

### 2.6 File Upload Edge Cases

**Problem:** File size validation
- **Location:** Upload tab
- **Limit:** 10MB per file
- **Expected Behavior:**
  - Files over 10MB rejected
  - Error message displayed
  - Valid files still processed

**Test Scenarios:**
- Single file exactly 10MB
- Single file over 10MB
- Multiple files with one over limit
- Zero-byte files
- Unsupported file types

### 2.7 Pagination Issues

**Problem:** Cursor-based pagination state
- **Location:** File browser (KnowledgeFileBrowser.vue)
- **Implementation:**
  - Cursor tracking for "Load More"
  - Accumulated entries array
  - "Has more" flag
- **Potential Issues:**
  - Cursor not advancing
  - Duplicate entries
  - "Load More" not appearing when entries available
  - "Load More" not disappearing when exhausted

---

## 3. Test Coverage Gaps

### 3.1 Missing Unit Tests

**No Vue component unit tests found for:**
- KnowledgeManager.vue
- KnowledgeSearch.vue
- KnowledgeCategories.vue
- KnowledgeUpload.vue
- KnowledgeEntries.vue
- KnowledgeStats.vue
- KnowledgeFileBrowser.vue

**Recommended Framework:** Vitest + @vue/test-utils (Vue 3)

### 3.2 Missing Integration Tests

**No integration tests for:**
- Search → Results → View workflow
- Upload → Verify → Search workflow
- Category browse → Document view
- Bulk operations (select → delete/export)
- Tab switching state persistence

**Recommended Framework:** Playwright (config exists at `tests/playwright.config.js`)

### 3.3 Missing E2E Tests

**Critical user journeys not covered:**
- Complete knowledge upload workflow
- Multi-tab navigation persistence
- Error recovery workflows
- Long-running operation handling

### 3.4 Missing API Integration Tests

**Backend endpoints not tested:**
- `/api/knowledge_base/rag_search`
- `/api/knowledge_base/vectorize_facts/background`
- `/api/knowledge_base/vectorize_facts/status`
- `/api/knowledge_base/categories`

### 3.5 Missing Performance Tests

**No tests for:**
- Large dataset rendering (1000+ documents)
- Search result pagination
- Concurrent uploads
- File tree rendering performance
- Modal open/close performance

---

## 4. Critical User Workflows

### Workflow 1: Upload Text Knowledge

**Steps:**
1. Navigate to Knowledge → Upload tab
2. Select "Text Entry" method
3. Enter title: "Test Document"
4. Enter content: "This is test content"
5. Select category: "General"
6. Enter tags: "test, documentation"
7. Click "Add to Knowledge Base"
8. Verify success message
9. Switch to Manage tab
10. Search for "Test Document"
11. Verify document appears in list

**Expected Results:**
- ✅ Success message displays
- ✅ Document appears in search
- ✅ Category and tags are correct
- ✅ Content is preserved

**Predicted Failures:**
- ⚠️ Controller not initialized → shows error
- ⚠️ Backend timeout → no response
- ⚠️ Success message never displays

### Workflow 2: Search and View

**Steps:**
1. Navigate to Knowledge → Search tab
2. Enter query: "redis configuration"
3. Click "Search" or press Enter
4. Wait for results to load
5. Verify results appear
6. Click on first result
7. Verify document details display

**Expected Results:**
- ✅ Results load within 5 seconds
- ✅ Match scores are displayed
- ✅ Results are relevant to query
- ✅ Clicking result opens view

**Predicted Failures:**
- ⚠️ Results show as `[object Promise]`
- ⚠️ "No results" despite existing data
- ⚠️ Click on result does nothing
- ⚠️ RAG mode fails silently

### Workflow 3: Browse Categories

**Steps:**
1. Navigate to Knowledge → Categories tab
2. Wait for file browser to load
3. Select a category filter
4. Expand a folder in tree
5. Click on a document
6. Verify content displays in right panel
7. Close content panel
8. Try different category
9. Repeat steps 3-7

**Expected Results:**
- ✅ File tree loads
- ✅ Category filters work
- ✅ Folders expand/collapse
- ✅ Content displays correctly
- ✅ Panel closes properly

**Predicted Failures:**
- ⚠️ Infinite loading spinner
- ⚠️ Categories load but show 0 documents
- ⚠️ Tree doesn't respond to clicks
- ⚠️ Content panel shows error
- ⚠️ Modal stacking when opening multiple docs

### Workflow 4: Manage Documents

**Steps:**
1. Navigate to Knowledge → Manage tab
2. Click "Manage" sub-tab
3. Use search to filter: "test"
4. Select checkbox on first 3 results
5. Click "Delete Selected"
6. Confirm deletion
7. Verify documents removed from list
8. Verify selection cleared

**Expected Results:**
- ✅ Search filters correctly
- ✅ Selection state updates
- ✅ Delete confirmation shows
- ✅ Documents deleted from backend
- ✅ UI updates immediately
- ✅ Selection checkboxes cleared

**Predicted Failures:**
- ⚠️ Selection doesn't update
- ⚠️ Delete confirmation never appears
- ⚠️ Documents deleted but UI doesn't update
- ⚠️ Selection state persists after delete

### Workflow 5: View Statistics

**Steps:**
1. Navigate to Knowledge → Statistics tab
2. Wait for stats to load
3. Verify all stat cards display numbers
4. Check vector database section
5. Verify charts render
6. Click "Refresh" button
7. Verify stats update

**Expected Results:**
- ✅ All stats load within 3 seconds
- ✅ Numbers are not NaN or undefined
- ✅ Charts display correctly
- ✅ Refresh updates data
- ✅ No console errors

**Predicted Failures:**
- ⚠️ Stats show as `[object Promise]`
- ⚠️ NaN% displays in percentages
- ⚠️ Charts fail to render
- ⚠️ Refresh button does nothing
- ⚠️ Vector stats section empty despite data

### Workflow 6: System Knowledge Operations

**Steps:**
1. Navigate to Knowledge → Advanced tab
2. Click "Initialize Machine Knowledge"
3. Monitor progress bar
4. Wait for completion
5. Verify success message
6. Check Statistics tab for updated counts
7. Return to Advanced tab
8. Click "Start Background Vectorization"
9. Monitor status updates
10. Verify completion

**Expected Results:**
- ✅ Progress bar updates
- ✅ Status messages appear
- ✅ Success confirmed
- ✅ Stats reflect changes
- ✅ Background task completes

**Predicted Failures:**
- ⚠️ Operation times out
- ⚠️ Progress bar stuck at 0%
- ⚠️ No status updates
- ⚠️ Stats don't reflect changes
- ⚠️ Background task status not accessible

---

## 5. Recommended Test Suite

### 5.1 Unit Tests (Vitest + @vue/test-utils)

**File:** `tests/unit/knowledge/KnowledgeSearch.spec.ts`

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import KnowledgeSearch from '@/components/knowledge/KnowledgeSearch.vue'
import { createPinia, setActivePinia } from 'pinia'

describe('KnowledgeSearch.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders search interface correctly', () => {
    const wrapper = mount(KnowledgeSearch)

    expect(wrapper.find('[data-testid="search-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="search-button"]').exists()).toBe(true)
    expect(wrapper.find('.search-mode-toggle').exists()).toBe(true)
  })

  it('toggles between traditional and RAG search modes', async () => {
    const wrapper = mount(KnowledgeSearch)

    const ragButton = wrapper.find('[data-testid="rag-mode-button"]')
    await ragButton.trigger('click')

    expect(wrapper.vm.useRagSearch).toBe(true)
  })

  it('performs traditional search on Enter key', async () => {
    const wrapper = mount(KnowledgeSearch)
    const searchSpy = vi.spyOn(wrapper.vm, 'handleSearch')

    const input = wrapper.find('[data-testid="search-input"]')
    await input.setValue('test query')
    await input.trigger('keyup.enter')

    expect(searchSpy).toHaveBeenCalled()
  })

  it('displays search results correctly', async () => {
    const mockResults = [
      {
        document: { id: '1', title: 'Test Doc', type: 'document', category: 'general', content: 'test' },
        score: 0.95,
        highlights: ['test content']
      }
    ]

    const wrapper = mount(KnowledgeSearch)
    wrapper.vm.searchResults = mockResults
    wrapper.vm.searchPerformed = true
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('[data-testid="search-result"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Test Doc')
    expect(wrapper.text()).toContain('95% match')
  })

  it('handles empty search results gracefully', async () => {
    const wrapper = mount(KnowledgeSearch)
    wrapper.vm.searchResults = []
    wrapper.vm.searchPerformed = true
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="no-results"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('No documents found')
  })

  it('falls back to traditional search when RAG fails', async () => {
    const wrapper = mount(KnowledgeSearch)
    wrapper.vm.useRagSearch = true

    // Mock RAG failure
    vi.spyOn(wrapper.vm, 'performRagSearch').mockRejectedValue(new Error('RAG unavailable'))

    await wrapper.vm.handleSearch()
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.ragError).toBeTruthy()
    expect(wrapper.find('[data-testid="rag-error"]').exists()).toBe(true)
  })
})
```

**File:** `tests/unit/knowledge/KnowledgeUpload.spec.ts`

```typescript
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import KnowledgeUpload from '@/components/knowledge/KnowledgeUpload.vue'

describe('KnowledgeUpload.vue', () => {
  it('validates text content before submission', async () => {
    const wrapper = mount(KnowledgeUpload)

    const submitButton = wrapper.find('[data-testid="submit-text-button"]')
    expect(submitButton.attributes('disabled')).toBeDefined()

    const textarea = wrapper.find('[data-testid="text-content"]')
    await textarea.setValue('Test content')

    expect(submitButton.attributes('disabled')).toBeUndefined()
  })

  it('validates URL format', () => {
    const wrapper = mount(KnowledgeUpload)

    expect(wrapper.vm.isValidUrl('https://example.com')).toBe(true)
    expect(wrapper.vm.isValidUrl('http://test.org/path')).toBe(true)
    expect(wrapper.vm.isValidUrl('not a url')).toBe(false)
    expect(wrapper.vm.isValidUrl('')).toBe(false)
  })

  it('rejects files over 10MB', async () => {
    const wrapper = mount(KnowledgeUpload)

    const largeFile = new File(['x'.repeat(11 * 1024 * 1024)], 'large.txt', { type: 'text/plain' })
    wrapper.vm.addFiles([largeFile])

    expect(wrapper.vm.selectedFiles).toHaveLength(0)
    expect(wrapper.vm.errorMessage).toContain('too large')
  })

  it('accepts multiple valid files', async () => {
    const wrapper = mount(KnowledgeUpload)

    const file1 = new File(['content 1'], 'file1.txt', { type: 'text/plain' })
    const file2 = new File(['content 2'], 'file2.md', { type: 'text/markdown' })

    wrapper.vm.addFiles([file1, file2])

    expect(wrapper.vm.selectedFiles).toHaveLength(2)
  })

  it('shows upload progress', async () => {
    const wrapper = mount(KnowledgeUpload)

    wrapper.vm.uploadProgress.show = true
    wrapper.vm.uploadProgress.percentage = 50
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="upload-progress"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('50%')
  })
})
```

### 5.2 Integration Tests (Playwright)

**File:** `tests/e2e/knowledge-search.spec.ts`

```typescript
import { test, expect } from '@playwright/test'

test.describe('Knowledge Base Search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://172.16.168.21:5173')
    await page.click('[data-testid="knowledge-tab"]')
    await page.waitForLoadState('networkidle')
  })

  test('performs traditional search successfully', async ({ page }) => {
    await page.fill('[data-testid="search-input"]', 'redis configuration')
    await page.click('[data-testid="search-button"]')

    await page.waitForSelector('[data-testid="search-results"]', { timeout: 10000 })

    const results = page.locator('[data-testid="search-result"]')
    await expect(results.first()).toBeVisible()
  })

  test('toggles to RAG search mode', async ({ page }) => {
    const ragButton = page.locator('[data-testid="rag-mode-button"]')
    await ragButton.click()

    await expect(ragButton).toHaveClass(/active/)
    await expect(page.locator('[data-testid="rag-options"]')).toBeVisible()
  })

  test('displays RAG synthesis when available', async ({ page }) => {
    await page.click('[data-testid="rag-mode-button"]')
    await page.fill('[data-testid="search-input"]', 'what is redis?')
    await page.click('[data-testid="search-button"]')

    await page.waitForSelector('[data-testid="rag-synthesis"]', { timeout: 30000 })

    const synthesis = page.locator('[data-testid="rag-synthesis"]')
    await expect(synthesis).toBeVisible()
    await expect(synthesis).toContainText('AI Synthesis')
  })

  test('handles no results gracefully', async ({ page }) => {
    await page.fill('[data-testid="search-input"]', 'xyznonexistentquery123')
    await page.click('[data-testid="search-button"]')

    await page.waitForSelector('[data-testid="no-results"]')
    await expect(page.locator('[data-testid="no-results"]')).toBeVisible()
  })

  test('displays match scores correctly', async ({ page }) => {
    await page.fill('[data-testid="search-input"]', 'test')
    await page.click('[data-testid="search-button"]')

    await page.waitForSelector('[data-testid="search-result"]')

    const firstResult = page.locator('[data-testid="search-result"]').first()
    const score = firstResult.locator('[data-testid="result-score"]')

    await expect(score).toBeVisible()
    await expect(score).toContainText('%')
  })
})
```

**File:** `tests/e2e/knowledge-upload.spec.ts`

```typescript
import { test, expect } from '@playwright/test'

test.describe('Knowledge Base Upload', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://172.16.168.21:5173')
    await page.click('[data-testid="knowledge-tab"]')
    await page.click('[data-testid="upload-tab"]')
    await page.waitForLoadState('networkidle')
  })

  test('uploads text successfully', async ({ page }) => {
    await page.fill('[data-testid="text-title"]', 'Test Document')
    await page.fill('[data-testid="text-content"]', 'This is test content for knowledge base.')
    await page.selectOption('[data-testid="text-category"]', 'General')
    await page.fill('[data-testid="text-tags"]', 'test, automation')

    await page.click('[data-testid="submit-text-button"]')

    await expect(page.locator('[data-testid="success-message"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="success-message"]')).toContainText('added successfully')
  })

  test('validates required fields', async ({ page }) => {
    const submitButton = page.locator('[data-testid="submit-text-button"]')

    await expect(submitButton).toBeDisabled()

    await page.fill('[data-testid="text-content"]', 'Content')

    await expect(submitButton).toBeEnabled()
  })

  test('imports from URL', async ({ page }) => {
    await page.fill('[data-testid="url-input"]', 'https://example.com')
    await page.selectOption('[data-testid="url-category"]', 'Web Content')

    await page.click('[data-testid="submit-url-button"]')

    await expect(page.locator('[data-testid="upload-progress"]')).toBeVisible()
    await expect(page.locator('[data-testid="success-message"]')).toBeVisible({ timeout: 30000 })
  })

  test('uploads file with drag and drop', async ({ page }) => {
    const fileChooserPromise = page.waitForEvent('filechooser')
    await page.click('[data-testid="file-drop-zone"]')
    const fileChooser = await fileChooserPromise

    await fileChooser.setFiles([{
      name: 'test.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Test file content')
    }])

    await expect(page.locator('[data-testid="selected-file"]')).toBeVisible()
    await expect(page.locator('[data-testid="selected-file"]')).toContainText('test.txt')
  })

  test('rejects oversized files', async ({ page }) => {
    // Create 11MB file
    const largeBuffer = Buffer.alloc(11 * 1024 * 1024)

    const fileChooserPromise = page.waitForEvent('filechooser')
    await page.click('[data-testid="file-drop-zone"]')
    const fileChooser = await fileChooserPromise

    await fileChooser.setFiles([{
      name: 'large.txt',
      mimeType: 'text/plain',
      buffer: largeBuffer
    }])

    await expect(page.locator('[data-testid="error-message"]')).toBeVisible()
    await expect(page.locator('[data-testid="error-message"]')).toContainText('too large')
  })
})
```

### 5.3 API Integration Tests (Python)

**File:** `tests/api/test_knowledge_endpoints.py`

```python
import pytest
import httpx
from typing import Dict, Any

BASE_URL = "http://172.16.168.20:8001"

@pytest.fixture
def api_client():
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

@pytest.mark.asyncio
async def test_knowledge_search_endpoint(api_client):
    """Test traditional knowledge search"""
    response = await api_client.post('/api/knowledge_base/search', json={
        'query': 'redis configuration',
        'limit': 10
    })

    assert response.status_code == 200
    data = response.json()

    assert 'results' in data
    assert isinstance(data['results'], list)

    if len(data['results']) > 0:
        result = data['results'][0]
        assert 'document' in result
        assert 'score' in result
        assert 'highlights' in result

@pytest.mark.asyncio
async def test_rag_search_endpoint(api_client):
    """Test RAG-enhanced search"""
    response = await api_client.post('/api/knowledge_base/rag_search', json={
        'query': 'what is redis?',
        'limit': 5,
        'reformulate_query': True
    })

    if response.status_code == 200:
        data = response.json()
        assert 'synthesized_response' in data
        assert 'results' in data
        assert 'rag_analysis' in data
        assert 'confidence' in data['rag_analysis']
    else:
        # RAG may not be available
        assert response.status_code in [500, 503]

@pytest.mark.asyncio
async def test_add_text_knowledge(api_client):
    """Test adding text to knowledge base"""
    response = await api_client.post('/api/knowledge_base/add_text', json={
        'text': 'Test knowledge entry content',
        'title': 'Test Entry',
        'category': 'test',
        'metadata': {'source': 'automated_test'}
    })

    assert response.status_code == 200
    data = response.json()

    assert data['status'] in ['success', 'ok']
    assert 'fact_id' in data or 'id' in data

@pytest.mark.asyncio
async def test_get_categories(api_client):
    """Test retrieving knowledge categories"""
    response = await api_client.get('/api/knowledge_base/categories')

    assert response.status_code == 200
    data = response.json()

    assert 'categories' in data
    assert isinstance(data['categories'], list)

@pytest.mark.asyncio
async def test_get_stats(api_client):
    """Test knowledge base statistics endpoint"""
    response = await api_client.get('/api/knowledge_base/stats')

    assert response.status_code == 200
    data = response.json()

    assert 'total_facts' in data
    assert 'total_vectors' in data
    assert 'status' in data
    assert isinstance(data['total_facts'], int)

@pytest.mark.asyncio
async def test_get_basic_stats(api_client):
    """Test basic statistics endpoint"""
    response = await api_client.get('/api/knowledge_base/stats/basic')

    assert response.status_code == 200
    data = response.json()

    assert 'total_facts' in data
    assert 'status' in data

@pytest.mark.asyncio
async def test_vectorization_status_batch(api_client):
    """Test batch vectorization status check"""
    # Get some fact IDs first
    stats_response = await api_client.get('/api/knowledge_base/stats')

    if stats_response.status_code == 200:
        # Test with mock fact IDs
        response = await api_client.post('/api/knowledge_base/vectorization_status', json={
            'fact_ids': ['fact-1', 'fact-2', 'fact-3'],
            'include_dimensions': True,
            'use_cache': False
        })

        assert response.status_code in [200, 400, 500]

        if response.status_code == 200:
            data = response.json()
            assert 'statuses' in data
            assert 'summary' in data
            assert 'check_time_ms' in data

@pytest.mark.asyncio
async def test_start_background_vectorization(api_client):
    """Test starting background vectorization"""
    response = await api_client.post('/api/knowledge_base/vectorize_facts/background')

    # Should succeed or fail gracefully
    assert response.status_code in [200, 400, 500]

    if response.status_code == 200:
        data = response.json()
        assert 'status' in data or 'message' in data

@pytest.mark.asyncio
async def test_get_vectorization_status(api_client):
    """Test retrieving vectorization status"""
    response = await api_client.get('/api/knowledge_base/vectorize_facts/status')

    assert response.status_code == 200
    data = response.json()

    assert 'status' in data
    assert data['status'] in ['idle', 'running', 'completed', 'error']
```

---

## 6. Manual Testing Checklist

### 6.1 Pre-Testing Setup

- [ ] Backend is running at `http://172.16.168.20:8001`
- [ ] Frontend is running at `http://172.16.168.21:5173`
- [ ] Redis is accessible at `172.16.168.23:6379`
- [ ] Browser DevTools console is open
- [ ] Network tab is recording
- [ ] Test data is prepared (sample documents, files)

### 6.2 Search Tab Testing

**Traditional Search:**
- [ ] Enter query and press Enter
- [ ] Click Search button
- [ ] Verify results load
- [ ] Check match scores display correctly
- [ ] Verify result count matches
- [ ] Click on a result
- [ ] Test empty query behavior
- [ ] Test query with no matches

**RAG Search:**
- [ ] Toggle to RAG mode
- [ ] RAG options appear
- [ ] Adjust result limit
- [ ] Toggle query reformulation
- [ ] Perform search
- [ ] Verify AI synthesis appears
- [ ] Check confidence scores
- [ ] Verify source citations
- [ ] Test RAG fallback when unavailable

**Console Errors to Watch:**
- `[object Promise]` in results
- `Cannot read property of undefined`
- RAG error messages
- Network errors

### 6.3 Categories Tab Testing

**File Browser:**
- [ ] File tree loads
- [ ] Categories populate correctly
- [ ] Click category filter
- [ ] Tree updates to show filtered items
- [ ] Expand folder in tree
- [ ] Collapse folder in tree
- [ ] Click on document
- [ ] Content displays in right panel
- [ ] Close content panel
- [ ] Search for files
- [ ] Verify search results
- [ ] Load more entries (if paginated)

**Console Errors to Watch:**
- Category loading failures
- Tree rendering errors
- Content loading failures
- Modal stacking issues

### 6.4 Upload Tab Testing

**Text Entry:**
- [ ] Fill in title (optional)
- [ ] Fill in content (required)
- [ ] Select category
- [ ] Enter tags
- [ ] Character counter updates
- [ ] Submit button enables when valid
- [ ] Click submit
- [ ] Success message appears
- [ ] Form resets after submission

**URL Import:**
- [ ] Enter invalid URL
- [ ] Submit button stays disabled
- [ ] Enter valid URL
- [ ] Submit button enables
- [ ] Select category and tags
- [ ] Click import
- [ ] Progress bar appears
- [ ] Success message appears
- [ ] Form resets

**File Upload:**
- [ ] Click browse button
- [ ] Select valid file
- [ ] File appears in list
- [ ] File size displays correctly
- [ ] Remove file works
- [ ] Add multiple files
- [ ] Try file over 10MB
- [ ] Verify rejection and error message
- [ ] Drag and drop file
- [ ] Set category and tags for batch
- [ ] Click upload
- [ ] Progress shows each file
- [ ] Success message appears
- [ ] File list clears

**Console Errors to Watch:**
- Controller not available
- Upload failures
- File validation errors
- Progress tracking issues

### 6.5 Manage Tab Testing

**Document List:**
- [ ] Documents load
- [ ] Search bar filters correctly
- [ ] Category filter works
- [ ] Type filter works
- [ ] Sort options work
- [ ] Pagination controls function
- [ ] Page numbers accurate

**Selection:**
- [ ] Check individual checkbox
- [ ] Check "select all" checkbox
- [ ] Selection count updates
- [ ] Navigate to next page
- [ ] Selection persists

**Bulk Operations:**
- [ ] Select multiple documents
- [ ] Click "Export Selected"
- [ ] JSON file downloads
- [ ] Click "Delete Selected"
- [ ] Confirmation dialog appears
- [ ] Confirm deletion
- [ ] Documents removed from list
- [ ] Selection cleared

**View/Edit:**
- [ ] Click document title
- [ ] View modal opens
- [ ] Metadata displays correctly
- [ ] Content displays correctly
- [ ] Click "Edit" button
- [ ] Edit mode activates
- [ ] All fields editable
- [ ] Modify content
- [ ] Click "Save Changes"
- [ ] Modal closes
- [ ] Document updates in list

**Console Errors to Watch:**
- Controller method undefined
- Pagination errors
- Selection state issues
- Modal not closing

### 6.6 Statistics Tab Testing

**Initial Load:**
- [ ] All stat cards display
- [ ] Numbers are not NaN
- [ ] Vector database section loads
- [ ] Charts render correctly
- [ ] Recent activity displays
- [ ] Tag cloud renders

**Refresh:**
- [ ] Click refresh button
- [ ] Loading indicator appears
- [ ] Stats update
- [ ] Charts re-render

**Vector Stats:**
- [ ] Total facts count accurate
- [ ] Total vectors count accurate
- [ ] Status indicator correct
- [ ] Vectorization notice (if applicable)
- [ ] Category distribution chart
- [ ] Health indicators

**Actions:**
- [ ] Click "Export Statistics"
- [ ] JSON file downloads
- [ ] Click "Generate Report"
- [ ] Markdown file downloads
- [ ] Click "Optimize Database"
- [ ] Confirmation dialog appears

**Console Errors to Watch:**
- `[object Promise]` in stats
- NaN in percentages
- Chart rendering failures
- Controller method errors

### 6.7 Advanced Tab Testing

**Initialize Machine Knowledge:**
- [ ] Click button
- [ ] Progress bar starts
- [ ] Status messages update
- [ ] Progress reaches 100%
- [ ] Success message appears
- [ ] Verify stats updated

**Populate Man Pages:**
- [ ] Click button
- [ ] Progress tracking works
- [ ] Completion confirmed
- [ ] Stats reflect changes

**Background Vectorization:**
- [ ] Click start button
- [ ] Task starts
- [ ] Status endpoint polls
- [ ] Progress updates
- [ ] Completion detected
- [ ] Stats reflect vectorization

**Console Errors to Watch:**
- Operation timeouts
- Progress not updating
- Status polling failures
- Backend errors

### 6.8 Cross-Tab Testing

**State Persistence:**
- [ ] Upload document in Upload tab
- [ ] Switch to Search tab
- [ ] Search for new document
- [ ] Verify it appears
- [ ] Switch to Manage tab
- [ ] Verify document in list
- [ ] Switch to Statistics tab
- [ ] Verify count increased

**Tab Navigation:**
- [ ] Click each tab multiple times
- [ ] Verify no console errors
- [ ] Check for memory leaks (DevTools Performance)
- [ ] Verify components unmount properly

### 6.9 Error Recovery Testing

**Network Errors:**
- [ ] Disconnect network
- [ ] Try to search
- [ ] Verify error message
- [ ] Reconnect network
- [ ] Retry search
- [ ] Verify recovery

**Backend Down:**
- [ ] Stop backend
- [ ] Try operations
- [ ] Verify graceful errors
- [ ] Start backend
- [ ] Verify automatic recovery

**Long Operations:**
- [ ] Start long operation (vectorization)
- [ ] Navigate away
- [ ] Return to tab
- [ ] Verify operation continues
- [ ] Check status updates

### 6.10 Performance Testing

**Large Dataset:**
- [ ] Load view with 1000+ documents
- [ ] Measure render time (< 2 seconds)
- [ ] Test scrolling performance
- [ ] Test search performance
- [ ] Test pagination

**Concurrent Operations:**
- [ ] Upload multiple files
- [ ] Search while uploading
- [ ] Switch tabs during operations
- [ ] Verify no UI freezing

**Memory Leaks:**
- [ ] Open/close modals 20 times
- [ ] Check memory usage (DevTools)
- [ ] Switch tabs repeatedly
- [ ] Monitor memory growth
- [ ] Verify cleanup on unmount

---

## Summary

This test plan identifies:

1. **Expected Functionality:** 6 main tabs with complex interactions
2. **Predicted Issues:** 7 major categories of potential bugs
3. **Test Coverage Gaps:** No Vue unit tests, minimal E2E tests
4. **Critical Workflows:** 6 essential user journeys
5. **Recommended Tests:** Unit, integration, and E2E test suites
6. **Manual Checklist:** Comprehensive 100+ point validation

**Priority Actions:**
1. Create unit tests for all Vue components
2. Set up Playwright E2E test suite
3. Add API integration tests
4. Execute manual testing checklist
5. Fix identified issues
6. Add missing error boundaries

**Estimated Testing Time:**
- Manual testing: 4-6 hours
- Test creation: 8-12 hours
- Issue fixing: Variable based on findings
