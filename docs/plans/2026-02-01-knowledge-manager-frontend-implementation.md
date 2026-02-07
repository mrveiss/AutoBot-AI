# Knowledge Manager Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Knowledge Manager frontend with category CRUD, system docs viewer, prompt editor, and source attribution.

**Architecture:** Extend the existing modular architecture in `autobot-user-frontend/src/components/knowledge/`. Add new Vue 3 Composition API components with TypeScript. Use the existing `useKnowledgeStore` for state management. Backend APIs are stable and ready.

**Tech Stack:** Vue 3, TypeScript, Pinia store, Monaco Editor (for prompt editing), Vue Router (deep-links)

**Issue:** #747
**Branch:** `feature/747-knowledge-manager-frontend`
**Worktree:** `.worktrees/feature-747-knowledge-manager`

---

## Task 1: Store Updates - Add New State and Actions

**Files:**
- Modify: `autobot-user-frontend/src/stores/useKnowledgeStore.ts`
- Reference: `autobot-user-backend/api/knowledge_categories.py`, `autobot-user-backend/api/prompts.py`

**Step 1: Read current store structure**

Review the existing store to understand current state shape.

**Step 2: Add new state properties**

```typescript
// Add to state in useKnowledgeStore.ts

// System Docs state
systemDocs: [] as SystemDoc[],
systemDocsLoading: false,
selectedDocumentId: null as string | null,

// Prompts state
prompts: [] as Prompt[],
promptsLoading: false,
selectedPromptId: null as string | null,

// Category edit modal state
categoryEditModal: {
  open: false,
  category: null as Category | null,
  mode: 'edit' as 'edit' | 'delete'
},

// Source preview panel state (for chat integration)
sourcePanel: {
  open: false,
  document: null as SystemDoc | null
}
```

**Step 3: Add TypeScript interfaces**

```typescript
// Add to types or top of store file

export interface SystemDoc {
  id: string
  title: string
  path: string
  content: string
  type: string
  collection: string
  updated_at?: string
  metadata?: Record<string, unknown>
}

export interface Prompt {
  id: string
  name: string
  type: 'system' | 'agent' | 'template'
  path: string
  content: string
  full_content_available: boolean
}

export interface Category {
  id: string
  name: string
  description?: string
  icon?: string
  color?: string
  parent_id?: string | null
  fact_count?: number
  children?: Category[]
}
```

**Step 4: Add actions for categories**

```typescript
// Category actions
async updateCategory(id: string, data: Partial<Category>) {
  const response = await apiClient.put(`/api/knowledge_base/categories/${id}`, data)
  const result = await response.json()
  if (result.status === 'success') {
    await this.loadCategories() // Refresh tree
  }
  return result
},

async deleteCategory(id: string) {
  const response = await apiClient.delete(`/api/knowledge_base/categories/${id}`)
  const result = await response.json()
  if (result.status === 'success') {
    await this.loadCategories()
  }
  return result
},

openCategoryEditModal(category: Category, mode: 'edit' | 'delete' = 'edit') {
  this.categoryEditModal = { open: true, category, mode }
},

closeCategoryEditModal() {
  this.categoryEditModal = { open: false, category: null, mode: 'edit' }
},
```

**Step 5: Add actions for system docs**

```typescript
// System docs actions
async loadSystemDocs() {
  this.systemDocsLoading = true
  try {
    const response = await apiClient.get('/api/knowledge_base/entries?collection=autobot-documentation')
    const data = await response.json()
    this.systemDocs = data.entries || []
  } catch (error) {
    console.error('Failed to load system docs:', error)
    this.systemDocs = []
  } finally {
    this.systemDocsLoading = false
  }
},

setSelectedDocument(id: string | null) {
  this.selectedDocumentId = id
},
```

**Step 6: Add actions for prompts**

```typescript
// Prompts actions
async loadPrompts() {
  this.promptsLoading = true
  try {
    const response = await apiClient.get('/api/prompts')
    const data = await response.json()
    this.prompts = data.prompts || []
  } catch (error) {
    console.error('Failed to load prompts:', error)
    this.prompts = []
  } finally {
    this.promptsLoading = false
  }
},

async updatePrompt(id: string, content: string) {
  const response = await apiClient.put(`/api/prompts/${id}`, { content })
  return response.json()
},

async revertPrompt(id: string) {
  const response = await apiClient.post(`/api/prompts/${id}/revert`)
  return response.json()
},

setSelectedPrompt(id: string | null) {
  this.selectedPromptId = id
},
```

**Step 7: Add source panel actions**

```typescript
// Source panel actions (for chat integration)
openSourcePanel(document: SystemDoc) {
  this.sourcePanel = { open: true, document }
},

closeSourcePanel() {
  this.sourcePanel = { open: false, document: null }
},
```

**Step 8: Commit**

```bash
git add autobot-user-frontend/src/stores/useKnowledgeStore.ts
git commit -m "feat(knowledge): add store state for system docs, prompts, and modals (#747)"
```

---

## Task 2: Create CategoryEditModal Component

**Files:**
- Create: `autobot-user-frontend/src/components/knowledge/modals/CategoryEditModal.vue`
- Reference: `autobot-user-frontend/src/components/ui/BaseModal.vue`

**Step 1: Create modals directory**

```bash
mkdir -p autobot-user-frontend/src/components/knowledge/modals
```

**Step 2: Create CategoryEditModal.vue**

```vue
<template>
  <BaseModal
    v-model="store.categoryEditModal.open"
    :title="isDeleteMode ? 'Delete Category' : 'Edit Category'"
    size="medium"
    @close="store.closeCategoryEditModal()"
  >
    <!-- Delete Confirmation -->
    <div v-if="isDeleteMode" class="delete-confirmation">
      <div class="warning-icon">⚠️</div>
      <p>Are you sure you want to delete <strong>{{ category?.name }}</strong>?</p>
      <p v-if="category?.fact_count" class="fact-warning">
        This category contains <strong>{{ category.fact_count }} facts</strong> that will be uncategorized.
      </p>
      <div class="modal-actions">
        <BaseButton variant="outline" @click="store.closeCategoryEditModal()">
          Cancel
        </BaseButton>
        <BaseButton variant="danger" :loading="deleting" @click="handleDelete">
          Delete Category
        </BaseButton>
      </div>
    </div>

    <!-- Edit Form -->
    <form v-else @submit.prevent="handleSave" class="edit-form">
      <div class="form-group">
        <label for="category-name">Name</label>
        <input
          id="category-name"
          v-model="form.name"
          type="text"
          required
          placeholder="Category name"
        />
      </div>

      <div class="form-group">
        <label for="category-description">Description</label>
        <textarea
          id="category-description"
          v-model="form.description"
          rows="3"
          placeholder="Optional description"
        />
      </div>

      <div class="form-row">
        <div class="form-group">
          <label for="category-icon">Icon</label>
          <input
            id="category-icon"
            v-model="form.icon"
            type="text"
            placeholder="📁"
          />
        </div>
        <div class="form-group">
          <label for="category-color">Color</label>
          <input
            id="category-color"
            v-model="form.color"
            type="color"
          />
        </div>
      </div>

      <div class="modal-actions">
        <BaseButton variant="outline" type="button" @click="store.closeCategoryEditModal()">
          Cancel
        </BaseButton>
        <BaseButton variant="primary" type="submit" :loading="saving">
          Save Changes
        </BaseButton>
      </div>
    </form>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useToast } from '@/composables/useToast'

const store = useKnowledgeStore()
const toast = useToast()

const saving = ref(false)
const deleting = ref(false)

const category = computed(() => store.categoryEditModal.category)
const isDeleteMode = computed(() => store.categoryEditModal.mode === 'delete')

const form = ref({
  name: '',
  description: '',
  icon: '',
  color: '#3b82f6'
})

// Sync form with category when modal opens
watch(() => store.categoryEditModal.open, (open) => {
  if (open && category.value) {
    form.value = {
      name: category.value.name || '',
      description: category.value.description || '',
      icon: category.value.icon || '📁',
      color: category.value.color || '#3b82f6'
    }
  }
})

async function handleSave() {
  if (!category.value?.id) return

  saving.value = true
  try {
    const result = await store.updateCategory(category.value.id, form.value)
    if (result.status === 'success') {
      toast.success('Category updated successfully')
      store.closeCategoryEditModal()
    } else {
      toast.error(result.message || 'Failed to update category')
    }
  } catch (error) {
    toast.error('Failed to update category')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!category.value?.id) return

  deleting.value = true
  try {
    const result = await store.deleteCategory(category.value.id)
    if (result.status === 'success') {
      toast.success('Category deleted successfully')
      store.closeCategoryEditModal()
    } else {
      toast.error(result.message || 'Failed to delete category')
    }
  } catch (error) {
    toast.error('Failed to delete category')
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.delete-confirmation {
  text-align: center;
  padding: var(--spacing-4);
}

.warning-icon {
  font-size: 3rem;
  margin-bottom: var(--spacing-4);
}

.fact-warning {
  color: var(--color-warning);
  background: var(--bg-warning);
  padding: var(--spacing-3);
  border-radius: var(--radius-sm);
  margin: var(--spacing-4) 0;
}

.edit-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.form-group label {
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.form-group input,
.form-group textarea {
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}
</style>
```

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/modals/CategoryEditModal.vue
git commit -m "feat(knowledge): add CategoryEditModal for edit/delete (#747)"
```

---

## Task 3: Enhance KnowledgeCategories with Edit/Delete Actions

**Files:**
- Modify: `autobot-user-frontend/src/components/knowledge/KnowledgeCategories.vue`

**Step 1: Import CategoryEditModal and add to template**

Add import at top of script:
```typescript
import CategoryEditModal from './modals/CategoryEditModal.vue'
```

Add component to template (before closing `</div>`):
```vue
<CategoryEditModal />
```

**Step 2: Add dropdown menu to category cards**

Find the category card in the template and add action buttons:
```vue
<div class="category-actions">
  <button
    class="action-btn edit"
    @click.stop="store.openCategoryEditModal(category, 'edit')"
    title="Edit category"
  >
    ✏️
  </button>
  <button
    class="action-btn delete"
    @click.stop="store.openCategoryEditModal(category, 'delete')"
    title="Delete category"
  >
    🗑️
  </button>
</div>
```

**Step 3: Add styles for action buttons**

```css
.category-actions {
  display: flex;
  gap: var(--spacing-2);
  opacity: 0;
  transition: opacity var(--duration-200);
}

.main-category-card:hover .category-actions {
  opacity: 1;
}

.action-btn {
  padding: var(--spacing-2);
  border: none;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--duration-200);
}

.action-btn:hover {
  background: var(--bg-tertiary);
}

.action-btn.delete:hover {
  background: var(--color-danger-bg);
}
```

**Step 4: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/KnowledgeCategories.vue
git commit -m "feat(knowledge): add edit/delete actions to category cards (#747)"
```

---

## Task 4: Create KnowledgeSystemDocs Component

**Files:**
- Create: `autobot-user-frontend/src/components/knowledge/KnowledgeSystemDocs.vue`

**Step 1: Create the component**

```vue
<template>
  <div class="system-docs">
    <!-- Header -->
    <div class="docs-header">
      <div class="search-bar">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search documentation..."
          class="search-input"
        />
      </div>
      <div class="header-actions">
        <select v-model="filterType" class="filter-select">
          <option value="all">All Types</option>
          <option value="api">API</option>
          <option value="guide">Guides</option>
          <option value="architecture">Architecture</option>
        </select>
        <BaseButton variant="outline" @click="exportAll">
          <i class="fas fa-download"></i> Export All
        </BaseButton>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="store.systemDocsLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <p>Loading documentation...</p>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else-if="filteredDocs.length === 0"
      icon="fas fa-book"
      message="No documentation found"
      :action="{ label: 'Refresh', handler: () => store.loadSystemDocs() }"
    />

    <!-- Content -->
    <div v-else class="docs-content">
      <!-- Document List -->
      <div class="docs-list">
        <div
          v-for="doc in filteredDocs"
          :key="doc.id"
          class="doc-item"
          :class="{ selected: selectedDoc?.id === doc.id }"
          @click="selectDoc(doc)"
        >
          <div class="doc-icon">{{ getDocIcon(doc.type) }}</div>
          <div class="doc-info">
            <h4>{{ doc.title || doc.path }}</h4>
            <span class="doc-type">{{ doc.type || 'document' }}</span>
          </div>
        </div>
      </div>

      <!-- Document Preview -->
      <div class="doc-preview">
        <div v-if="selectedDoc" class="preview-content">
          <div class="preview-header">
            <h3>{{ selectedDoc.title }}</h3>
            <div class="preview-actions">
              <BaseButton variant="ghost" size="small" @click="copyContent">
                <i class="fas fa-copy"></i> Copy
              </BaseButton>
              <BaseButton variant="ghost" size="small" @click="exportDoc(selectedDoc)">
                <i class="fas fa-download"></i> Export
              </BaseButton>
            </div>
          </div>
          <div class="preview-meta">
            <span v-if="selectedDoc.path"><i class="fas fa-file"></i> {{ selectedDoc.path }}</span>
            <span v-if="selectedDoc.updated_at"><i class="fas fa-clock"></i> {{ formatDate(selectedDoc.updated_at) }}</span>
          </div>
          <div class="preview-body" v-html="renderedContent"></div>
        </div>
        <div v-else class="no-selection">
          <i class="fas fa-file-alt"></i>
          <p>Select a document to preview</p>
        </div>
      </div>
    </div>

    <!-- Export Modal -->
    <DocumentExportModal
      v-model="showExportModal"
      :document="exportTarget"
      @export="handleExport"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useKnowledgeStore, type SystemDoc } from '@/stores/useKnowledgeStore'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import DocumentExportModal from './modals/DocumentExportModal.vue'
import { useToast } from '@/composables/useToast'
import { marked } from 'marked'

const store = useKnowledgeStore()
const route = useRoute()
const toast = useToast()

const searchQuery = ref('')
const filterType = ref('all')
const selectedDoc = ref<SystemDoc | null>(null)
const showExportModal = ref(false)
const exportTarget = ref<SystemDoc | null>(null)

const filteredDocs = computed(() => {
  let docs = store.systemDocs

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    docs = docs.filter(d =>
      d.title?.toLowerCase().includes(query) ||
      d.content?.toLowerCase().includes(query) ||
      d.path?.toLowerCase().includes(query)
    )
  }

  if (filterType.value !== 'all') {
    docs = docs.filter(d => d.type === filterType.value)
  }

  return docs
})

const renderedContent = computed(() => {
  if (!selectedDoc.value?.content) return ''
  return marked(selectedDoc.value.content)
})

function getDocIcon(type: string): string {
  const icons: Record<string, string> = {
    api: '📡',
    guide: '📖',
    architecture: '🏗️',
    readme: '📄',
    default: '📄'
  }
  return icons[type] || icons.default
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString()
}

function selectDoc(doc: SystemDoc) {
  selectedDoc.value = doc
  store.setSelectedDocument(doc.id)
}

async function copyContent() {
  if (!selectedDoc.value?.content) return
  await navigator.clipboard.writeText(selectedDoc.value.content)
  toast.success('Content copied to clipboard')
}

function exportDoc(doc: SystemDoc) {
  exportTarget.value = doc
  showExportModal.value = true
}

function exportAll() {
  exportTarget.value = null // null means export all
  showExportModal.value = true
}

function handleExport(format: string) {
  // Implementation in DocumentExportModal
  showExportModal.value = false
}

onMounted(async () => {
  await store.loadSystemDocs()

  // Handle deep-link
  const docId = route.query.doc as string
  if (docId) {
    const doc = store.systemDocs.find(d => d.id === docId)
    if (doc) selectDoc(doc)
  }
})
</script>

<style scoped>
.system-docs {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.docs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  gap: var(--spacing-4);
}

.search-input {
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  min-width: 250px;
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
}

.filter-select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.docs-content {
  display: grid;
  grid-template-columns: 300px 1fr;
  flex: 1;
  overflow: hidden;
}

.docs-list {
  border-right: 1px solid var(--border-default);
  overflow-y: auto;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
  transition: background var(--duration-200);
}

.doc-item:hover {
  background: var(--bg-secondary);
}

.doc-item.selected {
  background: var(--bg-tertiary);
  border-left: 3px solid var(--color-primary);
}

.doc-icon {
  font-size: 1.5rem;
}

.doc-info h4 {
  margin: 0;
  font-size: var(--text-sm);
}

.doc-type {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.doc-preview {
  overflow-y: auto;
  padding: var(--spacing-4);
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-3);
}

.preview-actions {
  display: flex;
  gap: var(--spacing-2);
}

.preview-meta {
  display: flex;
  gap: var(--spacing-4);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-4);
}

.preview-body {
  line-height: 1.6;
}

.preview-body :deep(pre) {
  background: var(--bg-secondary);
  padding: var(--spacing-3);
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.no-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
}

.no-selection i {
  font-size: 3rem;
  margin-bottom: var(--spacing-4);
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/KnowledgeSystemDocs.vue
git commit -m "feat(knowledge): add KnowledgeSystemDocs viewer component (#747)"
```

---

## Task 5: Create DocumentExportModal Component

**Files:**
- Create: `autobot-user-frontend/src/components/knowledge/modals/DocumentExportModal.vue`

**Step 1: Create the component**

```vue
<template>
  <BaseModal
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    title="Export Documentation"
    size="small"
  >
    <div class="export-options">
      <div class="option-group">
        <label>Format</label>
        <div class="radio-group">
          <label class="radio-option">
            <input type="radio" v-model="format" value="markdown" />
            <span>Markdown (.md)</span>
          </label>
          <label class="radio-option">
            <input type="radio" v-model="format" value="json" />
            <span>JSON (.json)</span>
          </label>
          <label class="radio-option">
            <input type="radio" v-model="format" value="txt" />
            <span>Plain Text (.txt)</span>
          </label>
        </div>
      </div>

      <div class="option-group" v-if="!document">
        <label>Scope</label>
        <div class="radio-group">
          <label class="radio-option">
            <input type="radio" v-model="scope" value="all" />
            <span>All Documents ({{ store.systemDocs.length }})</span>
          </label>
          <label class="radio-option">
            <input type="radio" v-model="scope" value="filtered" />
            <span>Filtered Results</span>
          </label>
        </div>
      </div>

      <div class="option-group">
        <label class="checkbox-option">
          <input type="checkbox" v-model="includeMetadata" />
          <span>Include metadata (path, dates, type)</span>
        </label>
      </div>
    </div>

    <template #footer>
      <BaseButton variant="outline" @click="emit('update:modelValue', false)">
        Cancel
      </BaseButton>
      <BaseButton variant="primary" @click="handleExport">
        <i class="fas fa-download"></i> Export
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useKnowledgeStore, type SystemDoc } from '@/stores/useKnowledgeStore'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  modelValue: boolean
  document: SystemDoc | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'export': [format: string]
}>()

const store = useKnowledgeStore()
const toast = useToast()

const format = ref('markdown')
const scope = ref('all')
const includeMetadata = ref(true)

function handleExport() {
  const docs = props.document ? [props.document] : store.systemDocs
  let content = ''
  let filename = ''

  if (format.value === 'json') {
    const exportData = docs.map(d => ({
      title: d.title,
      content: d.content,
      ...(includeMetadata.value ? { path: d.path, type: d.type, updated_at: d.updated_at } : {})
    }))
    content = JSON.stringify(exportData, null, 2)
    filename = props.document ? `${props.document.title}.json` : 'documentation.json'
  } else if (format.value === 'markdown') {
    content = docs.map(d => {
      let md = `# ${d.title}\n\n`
      if (includeMetadata.value) {
        md += `> Path: ${d.path}\n`
        if (d.updated_at) md += `> Updated: ${d.updated_at}\n`
        md += '\n'
      }
      md += d.content
      return md
    }).join('\n\n---\n\n')
    filename = props.document ? `${props.document.title}.md` : 'documentation.md'
  } else {
    content = docs.map(d => d.content).join('\n\n---\n\n')
    filename = props.document ? `${props.document.title}.txt` : 'documentation.txt'
  }

  // Download file
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)

  toast.success(`Exported ${docs.length} document(s)`)
  emit('update:modelValue', false)
  emit('export', format.value)
}
</script>

<style scoped>
.export-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.option-group label:first-child {
  font-weight: var(--font-medium);
  margin-bottom: var(--spacing-2);
  display: block;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.radio-option,
.checkbox-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
}

.radio-option input,
.checkbox-option input {
  cursor: pointer;
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/modals/DocumentExportModal.vue
git commit -m "feat(knowledge): add DocumentExportModal for export options (#747)"
```

---

## Task 6: Create KnowledgePromptEditor Component

**Files:**
- Create: `autobot-user-frontend/src/components/knowledge/KnowledgePromptEditor.vue`

**Step 1: Create the component**

```vue
<template>
  <div class="prompt-editor">
    <!-- Header -->
    <div class="editor-header">
      <div class="search-bar">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search prompts..."
          class="search-input"
        />
      </div>
      <div class="header-actions">
        <select v-model="filterType" class="filter-select">
          <option value="all">All Types</option>
          <option value="system">System</option>
          <option value="agent">Agents</option>
          <option value="template">Templates</option>
        </select>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="store.promptsLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <p>Loading prompts...</p>
    </div>

    <!-- Content -->
    <div v-else class="editor-content">
      <!-- Prompt List -->
      <div class="prompt-list">
        <div
          v-for="(group, type) in groupedPrompts"
          :key="type"
          class="prompt-group"
        >
          <h4 class="group-header">
            {{ getGroupIcon(type) }} {{ formatGroupName(type) }}
          </h4>
          <div
            v-for="prompt in group"
            :key="prompt.id"
            class="prompt-item"
            :class="{ selected: selectedPrompt?.id === prompt.id, modified: isModified(prompt.id) }"
            @click="selectPrompt(prompt)"
          >
            <span class="prompt-name">{{ prompt.name }}</span>
            <span v-if="isModified(prompt.id)" class="modified-badge">●</span>
          </div>
        </div>
      </div>

      <!-- Editor Panel -->
      <div class="editor-panel">
        <div v-if="selectedPrompt" class="editor-wrapper">
          <div class="editor-toolbar">
            <h3>{{ selectedPrompt.name }}</h3>
            <div class="toolbar-actions">
              <BaseButton
                variant="ghost"
                size="small"
                @click="showHistory = true"
                title="Version History"
              >
                <i class="fas fa-history"></i> History
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="small"
                :disabled="!isModified(selectedPrompt.id)"
                @click="revertChanges"
              >
                <i class="fas fa-undo"></i> Revert
              </BaseButton>
              <BaseButton
                variant="primary"
                size="small"
                :disabled="!isModified(selectedPrompt.id)"
                :loading="saving"
                @click="savePrompt"
              >
                <i class="fas fa-save"></i> Save
              </BaseButton>
            </div>
          </div>

          <div class="editor-meta">
            <span><i class="fas fa-file"></i> {{ selectedPrompt.path }}</span>
            <span><i class="fas fa-tag"></i> {{ selectedPrompt.type }}</span>
          </div>

          <!-- Monaco Editor placeholder - will use textarea for now -->
          <textarea
            v-model="editorContent"
            class="prompt-textarea"
            @input="markAsModified"
            spellcheck="false"
          ></textarea>

          <div class="editor-footer">
            <span class="char-count">{{ editorContent.length }} characters</span>
            <span v-if="selectedPrompt.full_content_available" class="truncation-warning">
              ⚠️ Content was truncated for preview
            </span>
          </div>
        </div>

        <div v-else class="no-selection">
          <i class="fas fa-edit"></i>
          <p>Select a prompt to edit</p>
        </div>
      </div>
    </div>

    <!-- History Modal -->
    <PromptHistoryModal
      v-model="showHistory"
      :prompt="selectedPrompt"
      @revert="handleRevert"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useKnowledgeStore, type Prompt } from '@/stores/useKnowledgeStore'
import BaseButton from '@/components/base/BaseButton.vue'
import PromptHistoryModal from './modals/PromptHistoryModal.vue'
import { useToast } from '@/composables/useToast'

const store = useKnowledgeStore()
const toast = useToast()

const searchQuery = ref('')
const filterType = ref('all')
const selectedPrompt = ref<Prompt | null>(null)
const editorContent = ref('')
const originalContent = ref('')
const modifiedPrompts = ref<Set<string>>(new Set())
const saving = ref(false)
const showHistory = ref(false)

const groupedPrompts = computed(() => {
  let prompts = store.prompts

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    prompts = prompts.filter(p =>
      p.name.toLowerCase().includes(query) ||
      p.content.toLowerCase().includes(query)
    )
  }

  if (filterType.value !== 'all') {
    prompts = prompts.filter(p => p.type === filterType.value)
  }

  // Group by type
  return prompts.reduce((acc, prompt) => {
    const type = prompt.type || 'other'
    if (!acc[type]) acc[type] = []
    acc[type].push(prompt)
    return acc
  }, {} as Record<string, Prompt[]>)
})

function getGroupIcon(type: string): string {
  const icons: Record<string, string> = {
    system: '⚙️',
    agent: '🤖',
    template: '📋',
    other: '📄'
  }
  return icons[type] || icons.other
}

function formatGroupName(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1) + ' Prompts'
}

function selectPrompt(prompt: Prompt) {
  // Warn if current has unsaved changes
  if (selectedPrompt.value && isModified(selectedPrompt.value.id)) {
    if (!confirm('You have unsaved changes. Discard them?')) {
      return
    }
    modifiedPrompts.value.delete(selectedPrompt.value.id)
  }

  selectedPrompt.value = prompt
  editorContent.value = prompt.content
  originalContent.value = prompt.content
  store.setSelectedPrompt(prompt.id)
}

function isModified(promptId: string): boolean {
  return modifiedPrompts.value.has(promptId)
}

function markAsModified() {
  if (selectedPrompt.value && editorContent.value !== originalContent.value) {
    modifiedPrompts.value.add(selectedPrompt.value.id)
  } else if (selectedPrompt.value) {
    modifiedPrompts.value.delete(selectedPrompt.value.id)
  }
}

function revertChanges() {
  if (!selectedPrompt.value) return
  editorContent.value = originalContent.value
  modifiedPrompts.value.delete(selectedPrompt.value.id)
}

async function savePrompt() {
  if (!selectedPrompt.value) return

  saving.value = true
  try {
    await store.updatePrompt(selectedPrompt.value.id, editorContent.value)
    originalContent.value = editorContent.value
    modifiedPrompts.value.delete(selectedPrompt.value.id)
    toast.success('Prompt saved successfully')
  } catch (error) {
    toast.error('Failed to save prompt')
  } finally {
    saving.value = false
  }
}

async function handleRevert(version: string) {
  if (!selectedPrompt.value) return

  try {
    await store.revertPrompt(selectedPrompt.value.id)
    await store.loadPrompts()
    // Re-select to get updated content
    const updated = store.prompts.find(p => p.id === selectedPrompt.value?.id)
    if (updated) selectPrompt(updated)
    toast.success('Prompt reverted successfully')
  } catch (error) {
    toast.error('Failed to revert prompt')
  }
}

// Warn before leaving with unsaved changes
window.addEventListener('beforeunload', (e) => {
  if (modifiedPrompts.value.size > 0) {
    e.preventDefault()
    e.returnValue = ''
  }
})

onMounted(() => {
  store.loadPrompts()
})
</script>

<style scoped>
.prompt-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  gap: var(--spacing-4);
}

.search-input,
.filter-select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
}

.search-input {
  min-width: 200px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.editor-content {
  display: grid;
  grid-template-columns: 250px 1fr;
  flex: 1;
  overflow: hidden;
}

.prompt-list {
  border-right: 1px solid var(--border-default);
  overflow-y: auto;
  padding: var(--spacing-2);
}

.prompt-group {
  margin-bottom: var(--spacing-4);
}

.group-header {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  padding: var(--spacing-2) var(--spacing-3);
  margin: 0;
}

.prompt-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-2) var(--spacing-3);
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.prompt-item:hover {
  background: var(--bg-secondary);
}

.prompt-item.selected {
  background: var(--bg-tertiary);
  color: var(--color-primary);
}

.prompt-item.modified .prompt-name {
  font-style: italic;
}

.modified-badge {
  color: var(--color-warning);
}

.editor-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.editor-toolbar h3 {
  margin: 0;
}

.toolbar-actions {
  display: flex;
  gap: var(--spacing-2);
}

.editor-meta {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  background: var(--bg-secondary);
}

.prompt-textarea {
  flex: 1;
  padding: var(--spacing-4);
  border: none;
  resize: none;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: 1.6;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.prompt-textarea:focus {
  outline: none;
}

.editor-footer {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  border-top: 1px solid var(--border-default);
}

.truncation-warning {
  color: var(--color-warning);
}

.no-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
}

.no-selection i {
  font-size: 3rem;
  margin-bottom: var(--spacing-4);
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/KnowledgePromptEditor.vue
git commit -m "feat(knowledge): add KnowledgePromptEditor with save/revert (#747)"
```

---

## Task 7: Create PromptHistoryModal Component

**Files:**
- Create: `autobot-user-frontend/src/components/knowledge/modals/PromptHistoryModal.vue`

**Step 1: Create the component**

```vue
<template>
  <BaseModal
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    title="Version History"
    size="large"
  >
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <p>Loading history...</p>
    </div>

    <div v-else-if="history.length === 0" class="empty-state">
      <i class="fas fa-history"></i>
      <p>No version history available</p>
    </div>

    <div v-else class="history-content">
      <div class="history-list">
        <div
          v-for="(version, index) in history"
          :key="version.timestamp"
          class="history-item"
          :class="{ selected: selectedVersion === version }"
          @click="selectedVersion = version"
        >
          <div class="version-info">
            <span class="version-label">{{ index === 0 ? 'Current' : `Version ${history.length - index}` }}</span>
            <span class="version-date">{{ formatDate(version.timestamp) }}</span>
          </div>
          <span class="version-size">{{ version.content.length }} chars</span>
        </div>
      </div>

      <div class="version-preview">
        <div v-if="selectedVersion" class="preview-content">
          <pre>{{ selectedVersion.content }}</pre>
        </div>
        <div v-else class="no-selection">
          Select a version to preview
        </div>
      </div>
    </div>

    <template #footer>
      <BaseButton variant="outline" @click="emit('update:modelValue', false)">
        Close
      </BaseButton>
      <BaseButton
        v-if="selectedVersion && history.indexOf(selectedVersion) !== 0"
        variant="primary"
        @click="handleRevert"
      >
        <i class="fas fa-undo"></i> Revert to This Version
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Prompt } from '@/stores/useKnowledgeStore'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface VersionEntry {
  timestamp: string
  content: string
}

const props = defineProps<{
  modelValue: boolean
  prompt: Prompt | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'revert': [version: string]
}>()

const loading = ref(false)
const history = ref<VersionEntry[]>([])
const selectedVersion = ref<VersionEntry | null>(null)

function formatDate(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}

function handleRevert() {
  if (selectedVersion.value) {
    emit('revert', selectedVersion.value.timestamp)
    emit('update:modelValue', false)
  }
}

// Load history when modal opens
watch(() => props.modelValue, async (open) => {
  if (open && props.prompt) {
    loading.value = true
    // For now, just show current version
    // Real implementation would fetch history from backend
    history.value = [{
      timestamp: new Date().toISOString(),
      content: props.prompt.content
    }]
    selectedVersion.value = null
    loading.value = false
  }
})
</script>

<style scoped>
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.history-content {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--spacing-4);
  min-height: 300px;
}

.history-list {
  border-right: 1px solid var(--border-default);
  padding-right: var(--spacing-4);
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3);
  cursor: pointer;
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-2);
}

.history-item:hover {
  background: var(--bg-secondary);
}

.history-item.selected {
  background: var(--bg-tertiary);
}

.version-info {
  display: flex;
  flex-direction: column;
}

.version-label {
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
}

.version-date {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.version-size {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.version-preview {
  overflow: auto;
}

.preview-content pre {
  margin: 0;
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  white-space: pre-wrap;
  word-break: break-word;
}

.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/modals/PromptHistoryModal.vue
git commit -m "feat(knowledge): add PromptHistoryModal for version history (#747)"
```

---

## Task 8: Create SourcePreviewPanel Component

**Files:**
- Create: `autobot-user-frontend/src/components/knowledge/panels/SourcePreviewPanel.vue`

**Step 1: Create panels directory and component**

```bash
mkdir -p autobot-user-frontend/src/components/knowledge/panels
```

```vue
<template>
  <Transition name="slide">
    <div v-if="store.sourcePanel.open" class="source-panel">
      <div class="panel-header">
        <h3>{{ document?.title || 'Document' }}</h3>
        <div class="panel-actions">
          <button class="action-btn" @click="openInKnowledgeManager" title="Open in Knowledge Manager">
            <i class="fas fa-external-link-alt"></i>
          </button>
          <button class="action-btn" @click="copyContent" title="Copy">
            <i class="fas fa-copy"></i>
          </button>
          <button class="action-btn close" @click="store.closeSourcePanel()" title="Close">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>

      <div class="panel-meta">
        <span v-if="document?.path"><i class="fas fa-file"></i> {{ document.path }}</span>
        <span v-if="document?.type"><i class="fas fa-tag"></i> {{ document.type }}</span>
      </div>

      <div class="panel-content" v-html="renderedContent"></div>

      <div class="panel-footer">
        <BaseButton variant="primary" size="small" @click="openInKnowledgeManager">
          Open in Knowledge Manager
        </BaseButton>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import BaseButton from '@/components/base/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import { marked } from 'marked'

const store = useKnowledgeStore()
const router = useRouter()
const toast = useToast()

const document = computed(() => store.sourcePanel.document)

const renderedContent = computed(() => {
  if (!document.value?.content) return ''
  return marked(document.value.content)
})

function openInKnowledgeManager() {
  if (!document.value) return
  router.push({
    path: '/knowledge',
    query: { tab: 'system-docs', doc: document.value.id }
  })
  store.closeSourcePanel()
}

async function copyContent() {
  if (!document.value?.content) return
  await navigator.clipboard.writeText(document.value.content)
  toast.success('Content copied to clipboard')
}
</script>

<style scoped>
.source-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 400px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-primary);
  border-left: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  z-index: 1000;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.panel-header h3 {
  margin: 0;
  font-size: var(--text-base);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-actions {
  display: flex;
  gap: var(--spacing-2);
}

.action-btn {
  padding: var(--spacing-2);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.action-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.action-btn.close:hover {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.panel-meta {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  background: var(--bg-secondary);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-4);
  line-height: 1.6;
}

.panel-content :deep(pre) {
  background: var(--bg-secondary);
  padding: var(--spacing-3);
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.panel-content :deep(code) {
  background: var(--bg-secondary);
  padding: 0.2em 0.4em;
  border-radius: var(--radius-xs);
  font-size: 0.9em;
}

.panel-footer {
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

/* Slide transition */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/panels/SourcePreviewPanel.vue
git commit -m "feat(knowledge): add SourcePreviewPanel for chat source preview (#747)"
```

---

## Task 9: Update KnowledgeManager to Include New Tabs

**Files:**
- Modify: `autobot-user-frontend/src/components/knowledge/KnowledgeManager.vue`

**Step 1: Add new tab imports and configuration**

Update the component to include the new System Docs and Prompts tabs:

```vue
<template>
  <ErrorBoundary fallback="Knowledge Base failed to load. Please try refreshing.">
    <div class="knowledge-manager">
      <div class="tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="['tab-button', { active: store.activeTab === tab.id }]"
          @click="store.setActiveTab(tab.id)"
          :aria-label="tab.label"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="tab-content">
        <component :is="activeComponent" />
      </div>
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

// Import sub-components
import KnowledgeSearch from './KnowledgeSearch.vue'
import KnowledgeCategories from './KnowledgeCategories.vue'

// Lazy load heavier components
const KnowledgeEntries = () => import('./KnowledgeEntries.vue')
const KnowledgeUpload = () => import('./KnowledgeUpload.vue')
const KnowledgeStats = () => import('./KnowledgeStats.vue')
const KnowledgeAdvanced = () => import('./KnowledgeAdvanced.vue')
const KnowledgeSystemDocs = () => import('./KnowledgeSystemDocs.vue')
const KnowledgePromptEditor = () => import('./KnowledgePromptEditor.vue')

const store = useKnowledgeStore()

// Tab configuration - Updated with new tabs
const tabs = [
  { id: 'search', label: 'Search' },
  { id: 'categories', label: 'Categories' },
  { id: 'upload', label: 'Upload' },
  { id: 'manage', label: 'Manage' },
  { id: 'system-docs', label: 'System Docs' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'stats', label: 'Statistics' },
  { id: 'advanced', label: 'Advanced' }
] as const

// Component mapping - Updated with new components
const componentMap = {
  search: KnowledgeSearch,
  categories: KnowledgeCategories,
  upload: KnowledgeUpload,
  manage: KnowledgeEntries,
  'system-docs': KnowledgeSystemDocs,
  prompts: KnowledgePromptEditor,
  stats: KnowledgeStats,
  advanced: KnowledgeAdvanced
} as const

// Active component based on tab
const activeComponent = computed(() => {
  return componentMap[store.activeTab as keyof typeof componentMap] || KnowledgeSearch
})
</script>
```

**Step 2: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/KnowledgeManager.vue
git commit -m "feat(knowledge): add System Docs and Prompts tabs to manager (#747)"
```

---

## Task 10: Add Source Attribution to Chat Messages

**Files:**
- Modify: `autobot-user-frontend/src/components/ChatInterface.vue` or relevant chat message component

**Step 1: Find the chat message rendering component**

Look for where assistant messages are rendered and add source links.

**Step 2: Add sources display**

```vue
<!-- Add to message rendering -->
<div v-if="message.sources?.length" class="message-sources">
  <span class="sources-label">📚 Sources:</span>
  <div class="source-links">
    <button
      v-for="source in message.sources"
      :key="source.id"
      class="source-link"
      @click="openSourcePanel(source)"
    >
      {{ source.title }}
      <span class="relevance">({{ Math.round(source.relevance * 100) }}%)</span>
    </button>
  </div>
</div>
```

**Step 3: Add source panel integration**

```typescript
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'

const knowledgeStore = useKnowledgeStore()

function openSourcePanel(source: { id: string; title: string; content: string }) {
  knowledgeStore.openSourcePanel({
    id: source.id,
    title: source.title,
    content: source.content,
    path: source.path || '',
    type: source.type || 'document',
    collection: source.collection || ''
  })
}
```

**Step 4: Add SourcePreviewPanel to layout**

In the main app layout or ChatInterface:

```vue
<template>
  <div class="chat-layout">
    <!-- existing chat content -->
    <SourcePreviewPanel />
  </div>
</template>

<script setup>
import SourcePreviewPanel from '@/components/knowledge/panels/SourcePreviewPanel.vue'
</script>
```

**Step 5: Add styles**

```css
.message-sources {
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.sources-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-right: var(--spacing-2);
}

.source-links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
}

.source-link {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-200);
}

.source-link:hover {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
}

.source-link .relevance {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}
```

**Step 6: Commit**

```bash
git add autobot-user-frontend/src/components/ChatInterface.vue
git commit -m "feat(knowledge): add source attribution to chat messages (#747)"
```

---

## Task 11: Enhance KnowledgeUpload with Drag-Drop

**Files:**
- Modify: `autobot-user-frontend/src/components/knowledge/KnowledgeUpload.vue`

**Step 1: Add drag-drop zone**

Add to template:

```vue
<div
  class="drop-zone"
  :class="{ 'drag-over': isDragging }"
  @dragenter.prevent="isDragging = true"
  @dragleave.prevent="isDragging = false"
  @dragover.prevent
  @drop.prevent="handleDrop"
>
  <div class="drop-content">
    <i class="fas fa-cloud-upload-alt"></i>
    <p>Drop files here or <label class="browse-link">browse<input type="file" multiple @change="handleFileSelect" hidden /></label></p>
    <span class="supported-formats">Supports: PDF, MD, TXT, JSON</span>
  </div>
</div>

<!-- File Queue -->
<div v-if="fileQueue.length > 0" class="file-queue">
  <h4>Queued Files ({{ fileQueue.length }})</h4>
  <div v-for="(file, index) in fileQueue" :key="file.name" class="queue-item">
    <span class="file-icon">{{ getFileIcon(file.name) }}</span>
    <span class="file-name">{{ file.name }}</span>
    <span class="file-size">{{ formatSize(file.size) }}</span>
    <span class="file-status" :class="file.status">{{ file.status }}</span>
    <button class="remove-btn" @click="removeFromQueue(index)">×</button>
  </div>
  <div class="queue-actions">
    <BaseButton variant="outline" @click="clearQueue">Clear All</BaseButton>
    <BaseButton variant="primary" :loading="uploading" @click="uploadAll">
      Upload All ({{ fileQueue.length }})
    </BaseButton>
  </div>
</div>
```

**Step 2: Add script logic**

```typescript
const isDragging = ref(false)
const fileQueue = ref<Array<{ file: File; name: string; size: number; status: string }>>([])
const uploading = ref(false)

function handleDrop(e: DragEvent) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (files) {
    addFilesToQueue(Array.from(files))
  }
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    addFilesToQueue(Array.from(input.files))
  }
}

function addFilesToQueue(files: File[]) {
  for (const file of files) {
    if (!fileQueue.value.some(f => f.name === file.name)) {
      fileQueue.value.push({
        file,
        name: file.name,
        size: file.size,
        status: 'ready'
      })
    }
  }
}

function removeFromQueue(index: number) {
  fileQueue.value.splice(index, 1)
}

function clearQueue() {
  fileQueue.value = []
}

async function uploadAll() {
  uploading.value = true
  for (const item of fileQueue.value) {
    item.status = 'uploading'
    try {
      // Upload logic
      await uploadFile(item.file)
      item.status = 'done'
    } catch (error) {
      item.status = 'error'
    }
  }
  uploading.value = false
}
```

**Step 3: Add styles**

```css
.drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-8);
  text-align: center;
  transition: all var(--duration-200);
  cursor: pointer;
}

.drop-zone.drag-over {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.drop-content i {
  font-size: 3rem;
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-4);
}

.browse-link {
  color: var(--color-primary);
  cursor: pointer;
  text-decoration: underline;
}

.file-queue {
  margin-top: var(--spacing-4);
}

.queue-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-2);
}

.file-status.ready { color: var(--text-secondary); }
.file-status.uploading { color: var(--color-primary); }
.file-status.done { color: var(--color-success); }
.file-status.error { color: var(--color-danger); }
```

**Step 4: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/KnowledgeUpload.vue
git commit -m "feat(knowledge): add drag-drop and batch upload support (#747)"
```

---

## Task 12: Add Bulk Operations to KnowledgeEntries

**Files:**
- Modify: `autobot-user-frontend/src/components/knowledge/KnowledgeEntries.vue`

**Step 1: Add selection state and toolbar**

```vue
<!-- Add toolbar before entries list -->
<div v-if="selectedEntries.size > 0" class="bulk-toolbar">
  <span class="selection-count">{{ selectedEntries.size }} selected</span>
  <BaseButton variant="ghost" size="small" @click="selectAll">Select All</BaseButton>
  <BaseButton variant="ghost" size="small" @click="clearSelection">Clear</BaseButton>
  <div class="bulk-actions">
    <BaseButton variant="outline" size="small" @click="bulkExport">
      <i class="fas fa-download"></i> Export
    </BaseButton>
    <BaseButton variant="outline" size="small" @click="bulkMove">
      <i class="fas fa-folder"></i> Move
    </BaseButton>
    <BaseButton variant="danger" size="small" @click="bulkDelete">
      <i class="fas fa-trash"></i> Delete
    </BaseButton>
  </div>
</div>

<!-- Add checkbox to each entry -->
<div class="entry-item">
  <input
    type="checkbox"
    :checked="selectedEntries.has(entry.id)"
    @change="toggleSelection(entry.id)"
    class="entry-checkbox"
  />
  <!-- existing entry content -->
</div>
```

**Step 2: Add selection logic**

```typescript
const selectedEntries = ref<Set<string>>(new Set())

function toggleSelection(id: string) {
  if (selectedEntries.value.has(id)) {
    selectedEntries.value.delete(id)
  } else {
    selectedEntries.value.add(id)
  }
}

function selectAll() {
  entries.value.forEach(e => selectedEntries.value.add(e.id))
}

function clearSelection() {
  selectedEntries.value.clear()
}

async function bulkDelete() {
  if (!confirm(`Delete ${selectedEntries.value.size} entries?`)) return

  for (const id of selectedEntries.value) {
    await store.deleteEntry(id)
  }
  clearSelection()
  toast.success(`Deleted ${selectedEntries.value.size} entries`)
}

function bulkExport() {
  const entriesToExport = entries.value.filter(e => selectedEntries.value.has(e.id))
  // Export logic
}

function bulkMove() {
  // Show category selection modal
}
```

**Step 3: Add styles**

```css
.bulk-toolbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-4);
}

.selection-count {
  font-weight: var(--font-medium);
}

.bulk-actions {
  margin-left: auto;
  display: flex;
  gap: var(--spacing-2);
}

.entry-checkbox {
  margin-right: var(--spacing-3);
}
```

**Step 4: Commit**

```bash
git add autobot-user-frontend/src/components/knowledge/KnowledgeEntries.vue
git commit -m "feat(knowledge): add bulk operations to entries (#747)"
```

---

## Task 13: Final Integration and Polish

**Files:**
- Multiple files for loading states, error handling, responsive design

**Step 1: Add useToast composable if missing**

Create `autobot-user-frontend/src/composables/useToast.ts` if it doesn't exist.

**Step 2: Add route handling for deep-links**

Ensure `/knowledge` route handles query params:

```typescript
// In router or KnowledgeView
const route = useRoute()
const store = useKnowledgeStore()

watch(() => route.query.tab, (tab) => {
  if (tab) store.setActiveTab(tab as string)
}, { immediate: true })
```

**Step 3: Run type check**

```bash
npm run type-check
```

Fix any TypeScript errors.

**Step 4: Test all features manually**

- Category edit/delete
- System docs viewer
- Prompt editor
- Source panel from chat
- Upload drag-drop
- Bulk operations

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat(knowledge): complete Knowledge Manager frontend (#747)

- Category CRUD with edit/delete modals
- System documentation viewer with export
- Prompt editor with version history
- Source attribution with side panel and deep-link
- Drag-drop upload with batch support
- Bulk operations on entries
- Loading states and error handling

Closes #747"
```

---

## Summary

| Task | Component | Estimated Effort |
|------|-----------|------------------|
| 1 | Store updates | Small |
| 2 | CategoryEditModal | Medium |
| 3 | KnowledgeCategories enhancement | Small |
| 4 | KnowledgeSystemDocs | Large |
| 5 | DocumentExportModal | Small |
| 6 | KnowledgePromptEditor | Large |
| 7 | PromptHistoryModal | Medium |
| 8 | SourcePreviewPanel | Medium |
| 9 | KnowledgeManager tabs update | Small |
| 10 | Chat source attribution | Medium |
| 11 | Upload drag-drop | Medium |
| 12 | Bulk operations | Medium |
| 13 | Integration and polish | Medium |

**Total: 13 tasks**

---

*Implementation plan for Issue #747 - Knowledge Manager Frontend Completion*
