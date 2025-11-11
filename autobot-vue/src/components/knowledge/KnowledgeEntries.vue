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
      <div v-if="dialogMode === 'view'" class="view-mode">
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

      <div v-else class="edit-mode">
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
import SystemKnowledgeManager from '@/components/SystemKnowledgeManager.vue'
import ManPageManager from '@/components/ManPageManager.vue'
import FailedVectorizationsManager from '@/components/knowledge/FailedVectorizationsManager.vue'
import DeduplicationManager from '@/components/knowledge/DeduplicationManager.vue'
import { formatDate, formatDateTime } from '@/utils/formatHelpers'
import { getDocumentTypeIcon } from '@/utils/iconMappings'
import { useDebounce } from '@/composables/useDebounce'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useModal } from '@/composables/useModal'

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
const { isOpen: showDialog, open: openDialog, close: closeDialogModal } = useModal('entry-dialog')
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
    console.error('Failed to delete entry:', error)
  }
}

const deleteSelected = async () => {
  if (!confirm(`Delete ${selectedEntries.value.length} selected entries?`)) return

  try {
    await controller.bulkDeleteDocuments(selectedEntries.value)
    selectedEntries.value = []
  } catch (error) {
    console.error('Failed to delete entries:', error)
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
    console.error('Failed to save changes:', error)
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
.knowledge-entries {
  padding: 1.5rem;
}

.entries-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.entries-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.search-box {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: #6b7280;
}

.search-input {
  padding: 0.5rem 0.75rem 0.5rem 2.25rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  width: 250px;
}

/* Button styling handled by BaseButton component */

/* Filter bar */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.filter-group label {
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
}

.filter-select {
  padding: 0.375rem 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: white;
}

/* Button styling handled by BaseButton component */

/* Loading and empty states */
.loading-state {
  text-align: center;
  padding: 3rem;
  color: #6b7280;
}

/* Table styles */
.entries-table {
  background: white;
  border-radius: 0.5rem;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  background: #f9fafb;
  padding: 0.75rem;
  text-align: left;
  font-weight: 500;
  color: #374151;
  font-size: 0.875rem;
  border-bottom: 1px solid #e5e7eb;
}

td {
  padding: 0.75rem;
  border-bottom: 1px solid #e5e7eb;
}

tr:hover {
  background: #f9fafb;
}

tr.selected {
  background: #eff6ff;
}

.checkbox-column {
  width: 40px;
  text-align: center;
}

.title-cell {
  cursor: pointer;
}

.entry-title {
  color: #3b82f6;
  font-weight: 500;
}

.entry-title:hover {
  text-decoration: underline;
}

.category-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
  background: #e5e7eb;
  color: #374151;
}

.type-badge {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.875rem;
  color: #6b7280;
}

.tags-cell {
  display: flex;
  gap: 0.25rem;
  align-items: center;
}

.tag-chip {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  background: #f3f4f6;
  border-radius: 9999px;
  font-size: 0.75rem;
  color: #4b5563;
}

.more-tags {
  font-size: 0.75rem;
  color: #6b7280;
}

.date-cell {
  font-size: 0.875rem;
  color: #6b7280;
}

.actions-cell {
  display: flex;
  gap: 0.5rem;
}

/* Button styling handled by BaseButton component */

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border-top: 1px solid #e5e7eb;
}

/* Button styling handled by BaseButton component */

.page-info {
  font-size: 0.875rem;
  color: #6b7280;
}

/* View mode styles */
.entry-metadata {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.5rem;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.meta-item label {
  font-size: 0.75rem;
  font-weight: 500;
  color: #6b7280;
  text-transform: uppercase;
}

.meta-item span {
  color: #374151;
}

.tags-section {
  grid-column: 1 / -1;
}

.tags-list {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.5rem;
}

.entry-content h4 {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 1rem;
}

.content-viewer {
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  line-height: 1.6;
  color: #374151;
  max-height: 400px;
  overflow-y: auto;
}

/* Edit mode styles */
.form-group {
  margin-bottom: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #374151;
  font-size: 0.875rem;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

/* Button styling handled by BaseButton component */

/* Responsive */
@media (max-width: 768px) {
  .entries-header {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions {
    flex-direction: column;
    gap: 0.5rem;
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
  gap: 0.5rem;
  border-bottom: 2px solid #e5e7eb;
  padding: 1rem 1rem 0.5rem;
  background: white;
}

/* Button styling handled by BaseButton component */
.manage-tab-btn.active {
  background: #3b82f6;
  color: white;
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
  padding: 1rem;
}

.man-pages-section {
  margin-top: 2rem;
  border-top: 2px solid #e5e7eb;
  padding-top: 2rem;
}
</style>
