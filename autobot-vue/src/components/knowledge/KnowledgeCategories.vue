<template>
  <div class="knowledge-categories">
    <div class="categories-header">
      <h3>Knowledge Categories</h3>
      <button @click="showCreateDialog = true" class="create-category-btn">
        <i class="fas fa-plus"></i> New Category
      </button>
    </div>

    <div v-if="store.isLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <p>Loading categories...</p>
    </div>

    <div v-else-if="store.categories.length === 0" class="empty-state">
      <i class="fas fa-folder-open empty-icon"></i>
      <p>No categories yet</p>
      <p class="empty-hint">Create your first category to organize knowledge</p>
    </div>

    <div v-else class="categories-grid">
      <div
        v-for="category in sortedCategories"
        :key="category.id"
        class="category-card"
        :class="{ 'selected': selectedCategory?.id === category.id }"
        @click="selectCategory(category)"
      >
        <div class="category-header">
          <div class="category-icon" :style="{ backgroundColor: category.color || '#6b7280' }">
            <i class="fas fa-folder"></i>
          </div>
          <div class="category-actions">
            <button @click.stop="editCategory(category)" class="action-btn" title="Edit">
              <i class="fas fa-edit"></i>
            </button>
            <button @click.stop="deleteCategory(category)" class="action-btn danger" title="Delete">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>

        <h4 class="category-name">{{ category.name }}</h4>
        <p class="category-description">{{ category.description || 'No description' }}</p>

        <div class="category-stats">
          <span class="stat-item">
            <i class="fas fa-file-alt"></i>
            {{ category.documentCount }} documents
          </span>
          <span class="stat-item">
            <i class="fas fa-clock"></i>
            {{ formatDate(category.updatedAt) }}
          </span>
        </div>

        <div class="category-actions-bottom">
          <button @click.stop="viewDocuments(category)" class="view-docs-btn">
            View Documents
          </button>
        </div>
      </div>
    </div>

    <!-- Create/Edit Category Dialog -->
    <div v-if="showCreateDialog || showEditDialog" class="dialog-overlay" @click="closeDialogs">
      <div class="dialog" @click.stop>
        <div class="dialog-header">
          <h3>{{ showEditDialog ? 'Edit Category' : 'Create Category' }}</h3>
          <button @click="closeDialogs" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="dialog-content">
          <div class="form-group">
            <label for="category-name">Category Name *</label>
            <input
              id="category-name"
              v-model="categoryForm.name"
              type="text"
              class="form-input"
              placeholder="e.g., Technical Documentation"
              required
            />
          </div>

          <div class="form-group">
            <label for="category-description">Description</label>
            <textarea
              id="category-description"
              v-model="categoryForm.description"
              class="form-textarea"
              rows="3"
              placeholder="Brief description of this category..."
            ></textarea>
          </div>

          <div class="form-group">
            <label for="category-color">Color</label>
            <div class="color-picker">
              <div
                v-for="color in colorOptions"
                :key="color"
                class="color-option"
                :class="{ 'selected': categoryForm.color === color }"
                :style="{ backgroundColor: color }"
                @click="categoryForm.color = color"
              ></div>
            </div>
          </div>
        </div>

        <div class="dialog-actions">
          <button @click="closeDialogs" class="cancel-btn">Cancel</button>
          <button
            @click="saveCategory"
            class="save-btn"
            :disabled="!categoryForm.name.trim()"
          >
            {{ showEditDialog ? 'Update' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Documents View Panel -->
    <div v-if="showDocumentsPanel" class="documents-panel">
      <div class="panel-header">
        <h3>{{ selectedCategory?.name }} - Documents</h3>
        <button @click="closeDocumentsPanel" class="close-panel-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <div class="documents-list">
        <div v-if="categoryDocuments.length === 0" class="no-documents">
          <p>No documents in this category yet.</p>
        </div>

        <div
          v-for="doc in categoryDocuments"
          :key="doc.id"
          class="document-item"
          @click="viewDocument(doc)"
        >
          <div class="doc-icon">
            <i :class="getTypeIcon(doc.type)"></i>
          </div>
          <div class="doc-info">
            <h5>{{ doc.title || 'Untitled' }}</h5>
            <p class="doc-meta">
              {{ doc.type }} • {{ formatDate(doc.updatedAt) }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import { useAppStore } from '@/stores/useAppStore'
import type { KnowledgeCategory, KnowledgeDocument } from '@/stores/useKnowledgeStore'

// Stores and controller
const store = useKnowledgeStore()
const controller = useKnowledgeController()
const appStore = useAppStore()

// UI state
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showDocumentsPanel = ref(false)
const selectedCategory = ref<KnowledgeCategory | null>(null)
const categoryDocuments = ref<KnowledgeDocument[]>([])

// Form state
const categoryForm = ref({
  name: '',
  description: '',
  color: '#6b7280'
})

// Color options for categories
const colorOptions = [
  '#ef4444', '#f59e0b', '#10b981', '#3b82f6',
  '#6366f1', '#8b5cf6', '#ec4899', '#6b7280'
]

// Computed
const sortedCategories = computed(() => {
  return [...store.categories].sort((a, b) => {
    return b.documentCount - a.documentCount
  })
})

// Methods
const selectCategory = (category: KnowledgeCategory) => {
  selectedCategory.value = category
}

const editCategory = (category: KnowledgeCategory) => {
  selectedCategory.value = category
  categoryForm.value = {
    name: category.name,
    description: category.description || '',
    color: category.color || '#6b7280'
  }
  showEditDialog.value = true
}

const deleteCategory = async (category: KnowledgeCategory) => {
  if (!confirm(`Delete category "${category.name}"? Documents will be moved to "Uncategorized".`)) {
    return
  }

  try {
    controller.deleteCategory(category.id)
    appStore.setGlobalError(null)
  } catch (error) {
    console.error('Failed to delete category:', error)
  }
}

const viewDocuments = async (category: KnowledgeCategory) => {
  selectedCategory.value = category
  categoryDocuments.value = store.documentsByCategory.get(category.name) || []
  showDocumentsPanel.value = true
}

const viewDocument = (doc: KnowledgeDocument) => {
  store.selectDocument(doc)
  store.setActiveTab('entries')
}

const saveCategory = async () => {
  if (!categoryForm.value.name.trim()) return

  try {
    if (showEditDialog.value && selectedCategory.value) {
      controller.updateCategory(selectedCategory.value.id, categoryForm.value)
    } else {
      controller.addCategory(categoryForm.value.name, categoryForm.value.description)
    }
    closeDialogs()
  } catch (error) {
    console.error('Failed to save category:', error)
  }
}

const closeDialogs = () => {
  showCreateDialog.value = false
  showEditDialog.value = false
  categoryForm.value = {
    name: '',
    description: '',
    color: '#6b7280'
  }
  selectedCategory.value = null
}

const closeDocumentsPanel = () => {
  showDocumentsPanel.value = false
  categoryDocuments.value = []
}

// Utility functions
const formatDate = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString()
}

const getTypeIcon = (type: string): string => {
  const icons: Record<string, string> = {
    document: 'fas fa-file-alt',
    webpage: 'fas fa-globe',
    api: 'fas fa-code',
    upload: 'fas fa-upload'
  }
  return icons[type] || 'fas fa-file'
}

// Load categories on mount
onMounted(() => {
  controller.loadCategories()
})
</script>

<style scoped>
.knowledge-categories {
  padding: 1rem;
}

.categories-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.categories-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.create-category-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background-color: #3b82f6;
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.create-category-btn:hover {
  background-color: #2563eb;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 3rem;
  color: #6b7280;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
}

.category-card {
  background: white;
  border: 2px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.category-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.category-card.selected {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.category-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.category-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 1.25rem;
}

.category-actions {
  display: flex;
  gap: 0.5rem;
}

.action-btn {
  width: 2rem;
  height: 2rem;
  border: none;
  background: #f3f4f6;
  border-radius: 0.25rem;
  color: #6b7280;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

.action-btn.danger:hover {
  background: #fee2e2;
  color: #dc2626;
}

.category-name {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.5rem;
}

.category-description {
  color: #6b7280;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.category-stats {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  color: #6b7280;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.view-docs-btn {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #e5e7eb;
  background: white;
  border-radius: 0.375rem;
  color: #3b82f6;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.view-docs-btn:hover {
  background: #eff6ff;
  border-color: #3b82f6;
}

/* Dialog styles */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: white;
  border-radius: 0.5rem;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.dialog-content {
  padding: 1.5rem;
}

.form-group {
  margin-bottom: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #374151;
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.color-picker {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.color-option {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.375rem;
  cursor: pointer;
  position: relative;
  transition: transform 0.2s;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.selected::after {
  content: '✓';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: white;
  font-weight: bold;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid #e5e7eb;
}

.cancel-btn,
.save-btn {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.cancel-btn {
  background: #f3f4f6;
  color: #374151;
}

.cancel-btn:hover {
  background: #e5e7eb;
}

.save-btn {
  background: #3b82f6;
  color: white;
}

.save-btn:hover:not(:disabled) {
  background: #2563eb;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Documents Panel */
.documents-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  background: white;
  box-shadow: -2px 0 10px rgba(0, 0, 0, 0.1);
  z-index: 100;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.close-panel-btn {
  width: 2rem;
  height: 2rem;
  border: none;
  background: #f3f4f6;
  border-radius: 0.25rem;
  color: #6b7280;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-panel-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

.documents-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.no-documents {
  text-align: center;
  padding: 2rem;
  color: #6b7280;
}

.document-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.document-item:hover {
  background: #f9fafb;
  border-color: #3b82f6;
}

.doc-icon {
  width: 2.5rem;
  height: 2.5rem;
  background: #eff6ff;
  border-radius: 0.375rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #3b82f6;
}

.doc-info h5 {
  font-weight: 500;
  color: #1f2937;
  margin-bottom: 0.25rem;
}

.doc-meta {
  font-size: 0.75rem;
  color: #6b7280;
}
</style>
