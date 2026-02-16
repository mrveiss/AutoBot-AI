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
    <!-- Search Bar -->
    <div class="entries-header">
      <div class="search-box">
        <i class="fas fa-search search-icon"></i>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search entries..."
          class="search-input"
          aria-label="Search knowledge base entries"
          @input="filterEntries"
        />
      </div>
      <span class="total-count">{{ filteredDocuments.length }} entries</span>
    </div>

    <!-- Issue #747: Bulk Actions Toolbar -->
    <BulkActionsToolbar
      :selected-count="selectedEntries.length"
      :total-count="filteredDocuments.length"
      :page-count="paginatedEntries.length"
      :all-page-selected="allSelected"
      :all-matching-selected="allMatchingSelected"
      @select-all-page="selectAllPage"
      @select-all-matching="selectAllMatching"
      @clear-selection="clearSelection"
      @export="handleExport"
      @change-category="openBulkCategoryChange"
      @add-tags="openBulkAddTags"
      @remove-tags="openBulkRemoveTags"
      @delete="deleteSelected"
    />

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="filter-group">
        <label for="category-filter">Category:</label>
        <select
          id="category-filter"
          v-model="filterCategory"
          @change="filterEntries"
          class="filter-select"
          aria-label="Filter by category"
        >
          <option value="">All Categories</option>
          <option v-for="cat in store.categories" :key="cat.id" :value="cat.name">
            {{ cat.name }} ({{ cat.documentCount }})
          </option>
        </select>
      </div>

      <div class="filter-group">
        <label for="type-filter">Type:</label>
        <select
          id="type-filter"
          v-model="filterType"
          @change="filterEntries"
          class="filter-select"
          aria-label="Filter by entry type"
        >
          <option value="">All Types</option>
          <option value="document">Documents</option>
          <option value="webpage">Web Pages</option>
          <option value="api">API Docs</option>
          <option value="upload">Uploads</option>
        </select>
      </div>

      <div class="filter-group">
        <label for="sort-filter">Sort by:</label>
        <select
          id="sort-filter"
          v-model="sortBy"
          @change="sortEntries"
          class="filter-select"
          aria-label="Sort entries by"
        >
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

    <!-- Issue #747: Bulk Edit Modal -->
    <BulkEditModal
      v-model="showBulkEditModal"
      :mode="bulkEditMode"
      :selected-entries="selectedBulkEditEntries"
      @confirm="handleBulkEditConfirm"
    />
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
import SystemKnowledgeManager from '@/components/knowledge/SystemKnowledgeManager.vue'
// @ts-ignore - Component lacks TypeScript declaration file
import ManPageManager from '@/components/manpage/ManPageManager.vue'
import FailedVectorizationsManager from '@/components/knowledge/FailedVectorizationsManager.vue'
import DeduplicationManager from '@/components/knowledge/DeduplicationManager.vue'
import SessionOrphanManager from '@/components/knowledge/SessionOrphanManager.vue'
import BulkActionsToolbar from '@/components/knowledge/BulkActionsToolbar.vue'
import BulkEditModal from '@/components/knowledge/modals/BulkEditModal.vue'
import type { BulkEditMode, BulkEditEntry, ExportFormat } from '@/components/knowledge/modals/BulkEditModal.vue'
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
const allMatchingSelected = ref(false)

// Bulk edit state (Issue #747)
const showBulkEditModal = ref(false)
const bulkEditMode = ref<BulkEditMode>('category')

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

// Issue #747: Bulk edit computed properties
const selectedBulkEditEntries = computed<BulkEditEntry[]>(() => {
  return store.documents
    .filter(doc => selectedEntries.value.includes(doc.id))
    .map(doc => ({
      id: doc.id,
      title: doc.title || 'Untitled',
      category: doc.category,
      tags: doc.tags
    }))
})

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
  handleExport('json')
}

// Issue #747: Enhanced export with multiple formats
const handleExport = (format: ExportFormat) => {
  const entries = store.documents.filter(doc =>
    selectedEntries.value.includes(doc.id)
  )

  let content: string
  let mimeType: string
  let extension: string

  switch (format) {
    case 'markdown':
      content = generateMarkdownExport(entries)
      mimeType = 'text/markdown'
      extension = 'md'
      break
    case 'csv':
      content = generateCsvExport(entries)
      mimeType = 'text/csv'
      extension = 'csv'
      break
    case 'json':
    default:
      content = JSON.stringify(entries.map(entry => ({
        title: entry.title,
        content: entry.content,
        category: entry.category,
        type: entry.type,
        source: entry.source,
        tags: entry.tags,
        createdAt: entry.createdAt,
        updatedAt: entry.updatedAt
      })), null, 2)
      mimeType = 'application/json'
      extension = 'json'
  }

  downloadFile(content, `knowledge-export-${new Date().toISOString().split('T')[0]}.${extension}`, mimeType)
}

const generateMarkdownExport = (entries: KnowledgeDocument[]): string => {
  const lines: string[] = ['# Knowledge Base Export', '']
  lines.push(`> Exported on ${new Date().toLocaleDateString()}`)
  lines.push(`> ${entries.length} entries`)
  lines.push('')

  entries.forEach((entry, index) => {
    lines.push(`## ${index + 1}. ${entry.title || 'Untitled'}`)
    lines.push('')
    lines.push(`**Category:** ${entry.category}`)
    lines.push(`**Type:** ${entry.type}`)
    lines.push(`**Source:** ${entry.source}`)
    if (entry.tags.length > 0) {
      lines.push(`**Tags:** ${entry.tags.join(', ')}`)
    }
    lines.push(`**Created:** ${formatDateTime(entry.createdAt)}`)
    lines.push(`**Updated:** ${formatDateTime(entry.updatedAt)}`)
    lines.push('')
    lines.push('### Content')
    lines.push('')
    lines.push(entry.content)
    lines.push('')
    lines.push('---')
    lines.push('')
  })

  return lines.join('\n')
}

const generateCsvExport = (entries: KnowledgeDocument[]): string => {
  const headers = ['Title', 'Category', 'Type', 'Source', 'Tags', 'Created', 'Updated', 'Content']
  const rows = entries.map(entry => [
    escapeCsvField(entry.title || 'Untitled'),
    escapeCsvField(entry.category),
    escapeCsvField(entry.type),
    escapeCsvField(entry.source),
    escapeCsvField(entry.tags.join('; ')),
    escapeCsvField(formatDateTime(entry.createdAt)),
    escapeCsvField(formatDateTime(entry.updatedAt)),
    escapeCsvField(entry.content.substring(0, 500) + (entry.content.length > 500 ? '...' : ''))
  ])

  return [headers.join(','), ...rows.map(row => row.join(','))].join('\n')
}

const escapeCsvField = (field: string): string => {
  if (field.includes(',') || field.includes('"') || field.includes('\n')) {
    return `"${field.replace(/"/g, '""')}"`
  }
  return field
}

const downloadFile = (content: string, filename: string, mimeType: string) => {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// Issue #747: Bulk actions toolbar handlers
const selectAllPage = () => {
  allMatchingSelected.value = false
  paginatedEntries.value.forEach(entry => {
    if (!selectedEntries.value.includes(entry.id)) {
      selectedEntries.value.push(entry.id)
    }
  })
}

const selectAllMatching = () => {
  allMatchingSelected.value = true
  selectedEntries.value = filteredDocuments.value.map(doc => doc.id)
}

const clearSelection = () => {
  selectedEntries.value = []
  allMatchingSelected.value = false
}

const openBulkCategoryChange = () => {
  bulkEditMode.value = 'category'
  showBulkEditModal.value = true
}

const openBulkAddTags = () => {
  bulkEditMode.value = 'tags-add'
  showBulkEditModal.value = true
}

const openBulkRemoveTags = () => {
  bulkEditMode.value = 'tags-remove'
  showBulkEditModal.value = true
}

const handleBulkEditConfirm = async (payload: { mode: BulkEditMode; value: string | string[] }) => {
  try {
    const ids = selectedEntries.value

    if (payload.mode === 'category') {
      await controller.bulkUpdateCategory(ids, payload.value as string)
    } else if (payload.mode === 'tags-add') {
      await controller.bulkAddTags(ids, payload.value as string[])
    } else if (payload.mode === 'tags-remove') {
      await controller.bulkRemoveTags(ids, payload.value as string[])
    }

    // Clear selection after successful bulk edit
    clearSelection()
  } catch (error) {
    logger.error('Bulk edit failed:', error)
  }
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

.total-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
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

/* Issue #901: Technical Precision search input */
.search-input {
  padding: var(--spacing-2) var(--spacing-3) var(--spacing-2) var(--spacing-9);
  border: 1px solid var(--border-default);
  border-radius: 2px;
  width: 250px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px var(--color-info-bg);
}

/* Filter bar */
.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: 4px;
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
  border-radius: 2px;
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  background: var(--bg-card);
  color: var(--text-primary);
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.filter-select:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px var(--color-info-bg);
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
  border-radius: 4px;
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

/* Issue #901: Electric blue for selected rows */
tr.selected {
  background: var(--color-info-bg);
}

.checkbox-column {
  width: 40px;
  text-align: center;
}

.title-cell {
  cursor: pointer;
}

/* Issue #901: Electric blue for entry titles */
.entry-title {
  color: var(--color-info);
  font-weight: var(--font-medium);
}

.entry-title:hover {
  text-decoration: underline;
  color: var(--color-info-dark);
}

/* Issue #901: Technical Precision badges */
.category-badge {
  display: inline-block;
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: 2px;
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-sans);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
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
  border-radius: 2px;
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 400;
  color: var(--text-secondary);
}

.more-tags {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

/* Issue #901: Monospace for dates */
.date-cell {
  font-size: 12px;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
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
  border-radius: 4px;
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
