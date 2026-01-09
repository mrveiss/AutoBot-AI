<template>
  <div class="knowledge-entries">
    <!-- Sub-tabs for Manage section -->
    <div class="manage-tabs">
      <BaseButton
        variant="ghost"
        @click="manageTab = 'upload'"
        :class="['manage-tab-btn', { active: manageTab === 'upload' }]"
      >
        <i class="fas fa-upload mr-2"></i>Upload
      </BaseButton>
      <BaseButton
        variant="ghost"
        @click="manageTab = 'manage'"
        :class="['manage-tab-btn', { active: manageTab === 'manage' }]"
      >
        <i class="fas fa-edit mr-2"></i>Manage
      </BaseButton>
      <BaseButton
        variant="ghost"
        @click="manageTab = 'advanced'"
        :class="['manage-tab-btn', { active: manageTab === 'advanced' }]"
      >
        <i class="fas fa-cog mr-2"></i>Advanced
      </BaseButton>
    </div>

    <!-- Upload Tab Content -->
    <KnowledgeUpload v-if="manageTab === 'upload'" />

    <!-- Advanced Tab Content -->
    <div v-if="manageTab === 'advanced'" class="advanced-content">
      <!-- System Knowledge Management: Initialize, Reindex, Repopulate -->
      <SystemKnowledgeManager />

      <!-- Deduplication & Orphan Management: Remove duplicates and clean up orphaned documents -->
      <DeduplicationManager />

      <!-- Session Orphan Cleanup: Remove KB facts from deleted conversations (Issue #547) -->
      <SessionOrphanManager />

      <!-- Failed Vectorizations Manager: Retry or Clear Failed Vectorization Jobs -->
      <FailedVectorizationsManager />

      <!-- Man Page Management: Search, Browse, and Integrate Man Pages -->
      <ManPageManager />
    </div>

    <!-- Manage Tab Content -->
    <div v-if="manageTab === 'manage'" class="entries-content">
    <div class="entries-header">
      <div class="header-actions">
        <div class="search-box">
          <i class="fas fa-search search-icon"></i>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search entries..."
            class="search-input"
            @input="filterEntries"
          />
        </div>
        <BaseButton
          variant="primary"
          size="sm"
          @click="exportSelected"
          :disabled="selectedEntries.length === 0"
          class="action-btn"
        >
          <i class="fas fa-download"></i>
          Export ({{ selectedEntries.length }})
        </BaseButton>
        <BaseButton
          variant="danger"
          size="sm"
          @click="deleteSelected"
          :disabled="selectedEntries.length === 0"
          class="action-btn danger"
        >
          <i class="fas fa-trash"></i>
          Delete ({{ selectedEntries.length }})
        </BaseButton>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>Category:</label>
        <select v-model="filterCategory" @change="filterEntries" class="filter-select">
          <option value="">All Categories</option>
          <option v-for="cat in store.categories" :key="cat.id" :value="cat.name">
            {{ cat.name }} ({{ cat.documentCount }})
          </option>
        </select>
      </div>

      <div class="filter-group">
        <label>Type:</label>
        <select v-model="filterType" @change="filterEntries" class="filter-select">
          <option value="">All Types</option>
          <option value="document">Documents</option>
          <option value="webpage">Web Pages</option>
          <option value="api">API Docs</option>
          <option value="upload">Uploads</option>
        </select>
      </div>

      <div class="filter-group">
        <label>Sort by:</label>
        <select v-model="sortBy" @change="sortEntries" class="filter-select">
          <option value="updatedAt">Last Updated</option>
          <option value="createdAt">Date Created</option>
          <option value="title">Title</option>
          <option value="category">Category</option>
        </select>
      </div>

      <BaseButton
        variant="secondary"
        size="sm"
        @click="clearFilters"
        class="clear-filters-btn"
      >
        Clear Filters
      </BaseButton>
    </div>

    <!-- Entries list -->
    <div v-if="store.isLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <p>Loading entries...</p>
    </div>

    <EmptyState
      v-else-if="filteredDocuments.length === 0"
      icon="fas fa-file-alt"
      title="No entries found"
      :message="searchQuery || filterCategory || filterType ? 'Try adjusting your filters' : 'Add your first knowledge entry'"
    />

    <div v-else class="entries-table">
      <table>
        <thead>
          <tr>
            <th class="checkbox-column">
              <input
                type="checkbox"
                :checked="allSelected"
                @change="toggleSelectAll"
              />
            </th>
            <th>Title</th>
            <th>Category</th>
            <th>Type</th>
            <th>Tags</th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in paginatedEntries"
            :key="entry.id"
            :class="{ 'selected': selectedEntries.includes(entry.id) }"
          >
            <td class="checkbox-column">
              <input
                type="checkbox"
                :checked="selectedEntries.includes(entry.id)"
                @change="toggleSelection(entry.id)"
              />
            </td>
            <td class="title-cell" @click="viewEntry(entry)">
              <span class="entry-title">{{ entry.title || 'Untitled' }}</span>
            </td>
            <td>
              <span class="category-badge" :style="getCategoryStyle(entry.category)">
                {{ entry.category }}
              </span>
            </td>
            <td>
              <span class="type-badge">
                <i :class="getDocumentTypeIcon(entry.type)"></i>
                {{ entry.type }}
              </span>
            </td>
            <td>
              <div class="tags-cell">
                <span v-for="tag in entry.tags.slice(0, 3)" :key="tag" class="tag-chip">
                  {{ tag }}
                </span>
                <span v-if="entry.tags.length > 3" class="more-tags">
                  +{{ entry.tags.length - 3 }}
                </span>
              </div>
            </td>
            <td class="date-cell">{{ formatDate(entry.updatedAt) }}</td>
            <td class="actions-cell">
              <BaseButton
                variant="ghost"
                size="xs"
                @click="viewEntry(entry)"
                class="icon-btn"
                title="View"
              >
                <i class="fas fa-eye"></i>
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="xs"
                @click="editEntry(entry)"
                class="icon-btn"
                title="Edit"
              >
                <i class="fas fa-edit"></i>
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="xs"
                @click="deleteEntry(entry)"
                class="icon-btn danger"
                title="Delete"
              >
                <i class="fas fa-trash"></i>
              </BaseButton>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div class="pagination">
        <BaseButton
          variant="outline"
          size="sm"
          @click="currentPage--"
          :disabled="currentPage === 1"
          class="page-btn"
        >
          <i class="fas fa-chevron-left"></i>
        </BaseButton>

        <span class="page-info">
          Page {{ currentPage }} of {{ totalPages }}
          ({{ filteredDocuments.length }} entries)
        </span>

        <BaseButton
          variant="outline"
          size="sm"
          @click="currentPage++"
          :disabled="currentPage === totalPages"
          class="page-btn"
        >
          <i class="fas fa-chevron-right"></i>
        </BaseButton>
      </div>
    </div>

    <!-- View/Edit Dialog -->
    <BaseModal
      v-model="showDialog"
      :title="dialogMode === 'view' ? 'View Entry' : 'Edit Entry'"
      size="large"
      scrollable
    >
      <div v-if="currentEntry && dialogMode === 'view'" class="view-mode">
        <div class="entry-metadata">
          <div class="meta-item">
            <label>Title:</label>
            <span>{{ currentEntry.title || 'Untitled' }}</span>
          </div>
          <div class="meta-item">
            <label>Category:</label>
            <span class="category-badge" :style="getCategoryStyle(currentEntry.category)">
              {{ currentEntry.category }}
            </span>
          </div>
          <div class="meta-item">
            <label>Type:</label>
            <span class="type-badge">
              <i :class="getDocumentTypeIcon(currentEntry.type)"></i>
              {{ currentEntry.type }}
            </span>
          </div>
          <div class="meta-item">
            <label>Source:</label>
            <span>{{ currentEntry.source }}</span>
          </div>
          <div class="meta-item">
            <label>Created:</label>
            <span>{{ formatDateTime(currentEntry.createdAt) }}</span>
          </div>
          <div class="meta-item">
            <label>Updated:</label>
            <span>{{ formatDateTime(currentEntry.updatedAt) }}</span>
          </div>
          <div v-if="currentEntry.tags.length > 0" class="meta-item tags-section">
            <label>Tags:</label>
            <div class="tags-list">
              <span v-for="tag in currentEntry.tags" :key="tag" class="tag-chip">
                {{ tag }}
              </span>
            </div>
          </div>
        </div>

        <div class="entry-content">
          <h4>Content</h4>
          <div class="content-viewer" v-html="formatContent(currentEntry.content)"></div>
        </div>
      </div>

      <div v-else-if="currentEntry" class="edit-mode">
        <div class="form-group">
          <label for="edit-title">Title</label>
          <input
            id="edit-title"
            v-model="editForm.title"
            type="text"
            class="form-input"
          />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="edit-category">Category</label>
            <select id="edit-category" v-model="editForm.category" class="form-select">
              <option v-for="cat in store.categories" :key="cat.id" :value="cat.name">
                {{ cat.name }}
              </option>
            </select>
          </div>

          <div class="form-group">
            <label for="edit-source">Source</label>
            <input
              id="edit-source"
              v-model="editForm.source"
              type="text"
              class="form-input"
            />
          </div>
        </div>

        <div class="form-group">
          <label for="edit-tags">Tags (comma-separated)</label>
          <input
            id="edit-tags"
            v-model="editForm.tagsInput"
            type="text"
            class="form-input"
            placeholder="tag1, tag2, tag3"
          />
        </div>

        <div class="form-group">
          <label for="edit-content">Content</label>
          <textarea
            id="edit-content"
            v-model="editForm.content"
            class="form-textarea"
            rows="10"
          ></textarea>
        </div>
      </div>

      <template #actions>
        <BaseButton
          v-if="dialogMode === 'view'"
          variant="primary"
          @click="switchToEdit"
        >
          <i class="fas fa-edit"></i>
          Edit
        </BaseButton>
        <BaseButton
          v-if="dialogMode === 'edit'"
          variant="secondary"
          @click="cancelEdit"
        >
          Cancel
        </BaseButton>
        <BaseButton
          v-if="dialogMode === 'edit'"
          variant="primary"
          @click="saveEdit"
        >
          Save Changes
        </BaseButton>
      </template>
    </BaseModal>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import KnowledgeUpload from './KnowledgeUpload.vue'
// @ts-ignore - Component lacks TypeScript declaration file
import SystemKnowledgeManager from '@/components/SystemKnowledgeManager.vue'
// @ts-ignore - Component lacks TypeScript declaration file
import ManPageManager from '@/components/ManPageManager.vue'
import FailedVectorizationsManager from '@/components/knowledge/FailedVectorizationsManager.vue'
import DeduplicationManager from '@/components/knowledge/DeduplicationManager.vue'
import SessionOrphanManager from '@/components/knowledge/SessionOrphanManager.vue'
import { formatDate, formatDateTime } from '@/utils/formatHelpers'
import { getDocumentTypeIcon } from '@/utils/iconMappings'
import { useDebounce } from '@/composables/useDebounce'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useModal } from '@/composables/useModal'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeEntries')

const store = useKnowledgeStore()
const controller = useKnowledgeController()

// Manage tab state
const manageTab = ref<'upload' | 'manage' | 'advanced'>('upload')

// Search and filter state
const searchQuery = ref('')
const debouncedSearchQuery = useDebounce(searchQuery, 300) // Debounce search for better performance
const filterCategory = ref('')
const filterType = ref('')
const sortBy = ref('updatedAt')

// Pagination
const currentPage = ref(1)
const itemsPerPage = 20

// Selection state
const selectedEntries = ref<string[]>([])

// Dialog state
const { isOpen: showDialog, open: openDialog, close: closeDialogModal } = useModal({ id: 'entry-dialog' })
const dialogMode = ref<'view' | 'edit'>('view')
const currentEntry = ref<KnowledgeDocument | null>(null)

const editForm = reactive({
  title: '',
  category: '',
  source: '',
  content: '',
  tagsInput: ''
})

// Computed
const filteredDocuments = computed(() => {
  let docs = [...store.documents]

  // Apply search filter (debounced for better performance)
  if (debouncedSearchQuery.value) {
    const query = debouncedSearchQuery.value.toLowerCase()
    docs = docs.filter(doc =>
      doc.title?.toLowerCase().includes(query) ||
      doc.content.toLowerCase().includes(query) ||
      doc.tags.some(tag => tag.toLowerCase().includes(query))
    )
  }

  // Apply category filter
  if (filterCategory.value) {
    docs = docs.filter(doc => doc.category === filterCategory.value)
  }

  // Apply type filter
  if (filterType.value) {
    docs = docs.filter(doc => doc.type === filterType.value)
  }

  // Apply sorting
  docs.sort((a, b) => {
    switch (sortBy.value) {
      case 'title':
        return (a.title || '').localeCompare(b.title || '')
      case 'category':
        return a.category.localeCompare(b.category)
      case 'createdAt':
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      case 'updatedAt':
      default:
        return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    }
  })

  return docs
})

const totalPages = computed(() =>
  Math.ceil(filteredDocuments.value.length / itemsPerPage)
)

const paginatedEntries = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return filteredDocuments.value.slice(start, end)
})

const allSelected = computed(() =>
  paginatedEntries.value.length > 0 &&
  paginatedEntries.value.every(entry => selectedEntries.value.includes(entry.id))
)

// Methods
const filterEntries = () => {
  currentPage.value = 1
}

const clearFilters = () => {
  searchQuery.value = ''
  filterCategory.value = ''
  filterType.value = ''
  sortBy.value = 'updatedAt'
  currentPage.value = 1
}

const sortEntries = () => {
  // Sorting is handled in the computed property
}

const toggleSelection = (id: string) => {
  const index = selectedEntries.value.indexOf(id)
  if (index > -1) {
    selectedEntries.value.splice(index, 1)
  } else {
    selectedEntries.value.push(id)
  }
}

const toggleSelectAll = () => {
  if (allSelected.value) {
    // Deselect all on current page
    paginatedEntries.value.forEach(entry => {
      const index = selectedEntries.value.indexOf(entry.id)
      if (index > -1) {
        selectedEntries.value.splice(index, 1)
      }
    })
  } else {
    // Select all on current page
    paginatedEntries.value.forEach(entry => {
      if (!selectedEntries.value.includes(entry.id)) {
        selectedEntries.value.push(entry.id)
      }
    })
  }
}

const viewEntry = (entry: KnowledgeDocument) => {
  currentEntry.value = entry
  dialogMode.value = 'view'
  openDialog()
}

const editEntry = (entry: KnowledgeDocument) => {
  currentEntry.value = entry
  editForm.title = entry.title || ''
  editForm.category = entry.category
  editForm.source = entry.source
  editForm.content = entry.content
  editForm.tagsInput = entry.tags.join(', ')
  dialogMode.value = 'edit'
  openDialog()
}

const deleteEntry = async (entry: KnowledgeDocument) => {
  if (!confirm(`Delete "${entry.title || 'Untitled'}"?`)) return

  try {
    await controller.deleteDocument(entry.id)
  } catch (error) {
    logger.error('Failed to delete entry:', error)
  }
}

const deleteSelected = async () => {
  if (!confirm(`Delete ${selectedEntries.value.length} selected entries?`)) return

  try {
    await controller.bulkDeleteDocuments(selectedEntries.value)
    selectedEntries.value = []
  } catch (error) {
    logger.error('Failed to delete entries:', error)
  }
}

const exportSelected = async () => {
  const entries = store.documents.filter(doc =>
    selectedEntries.value.includes(doc.id)
  )

  const data = entries.map(entry => ({
    title: entry.title,
    content: entry.content,
    category: entry.category,
    type: entry.type,
    source: entry.source,
    tags: entry.tags,
    createdAt: entry.createdAt,
    updatedAt: entry.updatedAt
  }))

  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `knowledge-export-${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const switchToEdit = () => {
  if (!currentEntry.value) return
  editEntry(currentEntry.value)
}

const cancelEdit = () => {
  dialogMode.value = 'view'
}

const saveEdit = async () => {
  if (!currentEntry.value) return

  try {
    const tags = editForm.tagsInput
      .split(',')
      .map(tag => tag.trim())
      .filter(tag => tag.length > 0)

    await controller.updateDocument(currentEntry.value.id, {
      title: editForm.title,
      category: editForm.category,
      source: editForm.source,
      content: editForm.content,
      tags
    })

    closeDialog()
  } catch (error) {
    logger.error('Failed to save changes:', error)
  }
}

const closeDialog = () => {
  closeDialogModal()
  currentEntry.value = null
  dialogMode.value = 'view'
}

// NOTE: formatDate and formatDateTime removed - now using shared utilities from @/utils/formatHelpers

const formatContent = (content: string): string => {
  // Basic markdown-like formatting
  return content
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
}

// Icon mapping now centralized in @/utils/iconMappings
// Use getDocumentTypeIcon() directly

const getCategoryStyle = (category: string) => {
  const cat = store.categories.find(c => c.name === category)
  return cat?.color ? { backgroundColor: cat.color, color: 'white' } : {}
}

// Load data on mount
onMounted(async () => {
  if (store.documents.length === 0) {
    await controller.loadAllDocuments()
  }
})

// Reset page when filters change (use debounced search for better performance)
watch([debouncedSearchQuery, filterCategory, filterType], () => {
  currentPage.value = 1
})
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */

.knowledge-entries {
  padding: var(--spacing-6);
}

.entries-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.entries-header h3 {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.search-box {
  position: relative;
}

.search-icon {
  position: absolute;
  left: var(--spacing-3);
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-secondary);
}

.search-input {
  padding: var(--spacing-2) var(--spacing-3) var(--spacing-2) var(--spacing-9);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  width: 250px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* Filter bar */
.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.filter-group label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.filter-select {
  padding: var(--spacing-1-5) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-card);
  color: var(--text-primary);
}

/* Loading and empty states */
.loading-state {
  text-align: center;
  padding: var(--spacing-12);
  color: var(--text-secondary);
}

/* Table styles */
.entries-table {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  background: var(--bg-secondary);
  padding: var(--spacing-3);
  text-align: left;
  font-weight: var(--font-medium);
  color: var(--text-primary);
  font-size: var(--text-sm);
  border-bottom: 1px solid var(--border-default);
}

td {
  padding: var(--spacing-3);
  border-bottom: 1px solid var(--border-default);
}

tr:hover {
  background: var(--bg-hover);
}

tr.selected {
  background: var(--color-primary-bg);
}

.checkbox-column {
  width: 40px;
  text-align: center;
}

.title-cell {
  cursor: pointer;
}

.entry-title {
  color: var(--color-primary);
  font-weight: var(--font-medium);
}

.entry-title:hover {
  text-decoration: underline;
}

.category-badge {
  display: inline-block;
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.type-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.tags-cell {
  display: flex;
  gap: var(--spacing-1);
  align-items: center;
}

.tag-chip {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.more-tags {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.date-cell {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.actions-cell {
  display: flex;
  gap: var(--spacing-2);
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.page-info {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* View mode styles */
.entry-metadata {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-8);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.meta-item label {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  text-transform: uppercase;
}

.meta-item span {
  color: var(--text-primary);
}

.tags-section {
  grid-column: 1 / -1;
}

.tags-list {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
  margin-top: var(--spacing-2);
}

.entry-content h4 {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.content-viewer {
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--text-primary);
  max-height: 400px;
  overflow-y: auto;
}

/* Edit mode styles */
.form-group {
  margin-bottom: var(--spacing-5);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: var(--spacing-2-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
}

/* Responsive */
@media (max-width: 768px) {
  .entries-header {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions {
    flex-direction: column;
    gap: var(--spacing-2);
  }

  .search-input {
    width: 100%;
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-group {
    flex-direction: column;
    width: 100%;
  }

  .filter-select {
    width: 100%;
  }

  .entries-table {
    overflow-x: auto;
  }

  table {
    min-width: 800px;
  }
}

/* Manage Tabs */
.manage-tabs {
  display: flex;
  gap: var(--spacing-2);
  border-bottom: 2px solid var(--border-default);
  padding: var(--spacing-4) var(--spacing-4) var(--spacing-2);
  background: var(--bg-card);
}

.manage-tab-btn.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.entries-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.advanced-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

/* System Knowledge Content */
.system-knowledge-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-4);
}

.man-pages-section {
  margin-top: var(--spacing-8);
  border-top: 2px solid var(--border-default);
  padding-top: var(--spacing-8);
}
</style>
