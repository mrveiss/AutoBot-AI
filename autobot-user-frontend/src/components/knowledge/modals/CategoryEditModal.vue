<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Category Edit Modal Component (Issue #747)
 *
 * Modal for editing and deleting knowledge categories.
 * Features:
 * - Edit category name, description, icon, color
 * - Delete category with confirmation and fact count warning
 * - Safety checks for categories with children
 */

import { ref, computed, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CategoryEditModal')

// =============================================================================
// Type Definitions
// =============================================================================

export interface Category {
  id: string
  name: string
  description?: string
  icon?: string
  color?: string
  path?: string
  fact_count?: number
  has_children?: boolean
}

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps<{
  modelValue: boolean
  category: Category | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'updated', category: Category): void
  (e: 'deleted', categoryId: string): void
}>()

// =============================================================================
// State
// =============================================================================

const isLoading = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const showDeleteConfirm = ref(false)
const factCount = ref<number>(0)
const isLoadingFactCount = ref(false)

// Form state
const formData = ref({
  name: '',
  description: '',
  icon: '',
  color: ''
})

// Predefined color options
const colorOptions = [
  '#3b82f6', // blue
  '#10b981', // emerald
  '#8b5cf6', // violet
  '#f59e0b', // amber
  '#ef4444', // red
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#84cc16', // lime
  '#f97316', // orange
  '#6366f1', // indigo
]

// Predefined icon options
const iconOptions = [
  { value: 'fas fa-folder', label: 'Folder' },
  { value: 'fas fa-book', label: 'Book' },
  { value: 'fas fa-code', label: 'Code' },
  { value: 'fas fa-cog', label: 'Settings' },
  { value: 'fas fa-file-alt', label: 'Document' },
  { value: 'fas fa-database', label: 'Database' },
  { value: 'fas fa-lightbulb', label: 'Ideas' },
  { value: 'fas fa-users', label: 'Users' },
  { value: 'fas fa-shield-alt', label: 'Security' },
  { value: 'fas fa-rocket', label: 'Launch' },
  { value: 'fas fa-brain', label: 'AI/ML' },
  { value: 'fas fa-terminal', label: 'Terminal' },
]

// =============================================================================
// Computed
// =============================================================================

const isOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const categoryTitle = computed(() => {
  return props.category?.name || 'Category'
})

const hasUnsavedChanges = computed(() => {
  if (!props.category) return false
  return (
    formData.value.name !== (props.category.name || '') ||
    formData.value.description !== (props.category.description || '') ||
    formData.value.icon !== (props.category.icon || '') ||
    formData.value.color !== (props.category.color || '')
  )
})

const canDelete = computed(() => {
  // Cannot delete if has children (backend enforces this)
  return !props.category?.has_children
})

// =============================================================================
// Watchers
// =============================================================================

watch(() => props.category, (newCategory) => {
  if (newCategory) {
    formData.value = {
      name: newCategory.name || '',
      description: newCategory.description || '',
      icon: newCategory.icon || 'fas fa-folder',
      color: newCategory.color || '#3b82f6'
    }
    // Reset state when category changes
    error.value = null
    successMessage.value = null
    showDeleteConfirm.value = false
    // Load fact count for delete warning
    loadFactCount(newCategory.id)
  }
}, { immediate: true })

// =============================================================================
// Methods
// =============================================================================

async function loadFactCount(categoryId: string): Promise<void> {
  isLoadingFactCount.value = true
  try {
    const response = await apiClient.get(
      `/api/knowledge_base/categories/${encodeURIComponent(categoryId)}/facts?limit=1`
    )
    const data = await parseApiResponse(response)
    factCount.value = data?.total_count ?? 0
  } catch (err) {
    logger.error('Failed to load fact count:', err)
    factCount.value = 0
  } finally {
    isLoadingFactCount.value = false
  }
}

async function saveChanges(): Promise<void> {
  if (!props.category) return

  isLoading.value = true
  error.value = null
  successMessage.value = null

  try {
    const response = await apiClient.put(
      `/api/knowledge_base/categories/${encodeURIComponent(props.category.id)}`,
      formData.value
    )
    const data = await parseApiResponse(response)

    if (data?.status === 'success') {
      successMessage.value = 'Category updated successfully'
      emit('updated', { ...props.category, ...formData.value })

      // Close modal after brief delay to show success message
      setTimeout(() => {
        closeModal()
      }, 1000)
    } else {
      error.value = data?.message || 'Failed to update category'
    }
  } catch (err) {
    logger.error('Failed to update category:', err)
    error.value = err instanceof Error ? err.message : 'Failed to update category'
  } finally {
    isLoading.value = false
  }
}

async function deleteCategory(): Promise<void> {
  if (!props.category) return

  isLoading.value = true
  error.value = null

  try {
    const response = await apiClient.delete(
      `/api/knowledge_base/categories/${encodeURIComponent(props.category.id)}`
    )
    const data = await parseApiResponse(response)

    if (data?.status === 'success') {
      emit('deleted', props.category.id)
      closeModal()
    } else {
      error.value = data?.message || 'Failed to delete category'
      showDeleteConfirm.value = false
    }
  } catch (err) {
    logger.error('Failed to delete category:', err)

    // Handle specific error cases
    const errorMessage = err instanceof Error ? err.message : String(err)
    if (errorMessage.includes('has children')) {
      error.value = 'Cannot delete category with sub-categories. Delete children first.'
    } else {
      error.value = errorMessage || 'Failed to delete category'
    }
    showDeleteConfirm.value = false
  } finally {
    isLoading.value = false
  }
}

function closeModal(): void {
  showDeleteConfirm.value = false
  error.value = null
  successMessage.value = null
  isOpen.value = false
}

function cancelDelete(): void {
  showDeleteConfirm.value = false
}

function confirmDelete(): void {
  showDeleteConfirm.value = true
}

function selectColor(color: string): void {
  formData.value.color = color
}

function selectIcon(icon: string): void {
  formData.value.icon = icon
}
</script>

<template>
  <BaseModal
    v-model="isOpen"
    :title="`Edit Category: ${categoryTitle}`"
    size="medium"
    @close="closeModal"
  >
    <div class="category-edit-modal">
      <!-- Success Message -->
      <div v-if="successMessage" class="alert alert-success">
        <i class="fas fa-check-circle"></i>
        {{ successMessage }}
      </div>

      <!-- Error Message -->
      <div v-if="error" class="alert alert-error">
        <i class="fas fa-exclamation-circle"></i>
        {{ error }}
      </div>

      <!-- Delete Confirmation View -->
      <div v-if="showDeleteConfirm" class="delete-confirm">
        <div class="delete-warning">
          <i class="fas fa-exclamation-triangle"></i>
          <h3>Delete Category?</h3>
          <p>
            Are you sure you want to delete <strong>"{{ categoryTitle }}"</strong>?
          </p>
          <p v-if="factCount > 0" class="fact-warning">
            <i class="fas fa-file-alt"></i>
            This category contains <strong>{{ factCount }}</strong> facts that will be orphaned.
          </p>
          <p class="delete-note">This action cannot be undone.</p>
        </div>
        <div class="delete-actions">
          <BaseButton
            variant="outline"
            @click="cancelDelete"
            :disabled="isLoading"
          >
            Cancel
          </BaseButton>
          <BaseButton
            variant="danger"
            @click="deleteCategory"
            :disabled="isLoading"
          >
            <i v-if="isLoading" class="fas fa-spinner fa-spin"></i>
            <span v-else>Delete Category</span>
          </BaseButton>
        </div>
      </div>

      <!-- Edit Form -->
      <div v-else class="edit-form">
        <!-- Category Info -->
        <div v-if="props.category?.path" class="category-path">
          <label>Path</label>
          <span class="path-value">{{ props.category.path }}</span>
        </div>

        <!-- Name Field -->
        <div class="form-group">
          <label for="category-name">Name</label>
          <input
            id="category-name"
            v-model="formData.name"
            type="text"
            class="form-input"
            placeholder="Category name"
            :disabled="isLoading"
          />
        </div>

        <!-- Description Field -->
        <div class="form-group">
          <label for="category-description">Description</label>
          <textarea
            id="category-description"
            v-model="formData.description"
            class="form-textarea"
            placeholder="Brief description of this category"
            rows="3"
            :disabled="isLoading"
          ></textarea>
        </div>

        <!-- Icon Selection -->
        <div class="form-group">
          <label>Icon</label>
          <div class="icon-picker">
            <button
              v-for="icon in iconOptions"
              :key="icon.value"
              type="button"
              class="icon-option"
              :class="{ selected: formData.icon === icon.value }"
              :title="icon.label"
              @click="selectIcon(icon.value)"
              :disabled="isLoading"
            >
              <i :class="icon.value"></i>
            </button>
          </div>
        </div>

        <!-- Color Selection -->
        <div class="form-group">
          <label>Color</label>
          <div class="color-picker">
            <button
              v-for="color in colorOptions"
              :key="color"
              type="button"
              class="color-option"
              :class="{ selected: formData.color === color }"
              :style="{ backgroundColor: color }"
              @click="selectColor(color)"
              :disabled="isLoading"
            ></button>
          </div>
        </div>

        <!-- Preview -->
        <div class="form-group">
          <label>Preview</label>
          <div class="category-preview">
            <div
              class="preview-icon"
              :style="{ backgroundColor: formData.color }"
            >
              <i :class="formData.icon"></i>
            </div>
            <span class="preview-name">{{ formData.name || 'Category Name' }}</span>
          </div>
        </div>

        <!-- Actions -->
        <div class="form-actions">
          <div class="left-actions">
            <BaseButton
              v-if="canDelete"
              variant="danger-outline"
              @click="confirmDelete"
              :disabled="isLoading"
            >
              <i class="fas fa-trash"></i>
              Delete
            </BaseButton>
            <span v-else class="delete-disabled-hint">
              <i class="fas fa-info-circle"></i>
              Has sub-categories
            </span>
          </div>
          <div class="right-actions">
            <BaseButton
              variant="outline"
              @click="closeModal"
              :disabled="isLoading"
            >
              Cancel
            </BaseButton>
            <BaseButton
              variant="primary"
              @click="saveChanges"
              :disabled="isLoading || !hasUnsavedChanges"
            >
              <i v-if="isLoading" class="fas fa-spinner fa-spin"></i>
              <span v-else>Save Changes</span>
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.category-edit-modal {
  padding: 1rem;
}

/* Alerts */
.alert {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1.5rem;
  font-size: 0.875rem;
}

.alert-success {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
  border: 1px solid var(--color-success-border);
}

.alert-error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border: 1px solid var(--color-error-border);
}

/* Category Path */
.category-path {
  background: var(--bg-secondary);
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1.5rem;
}

.category-path label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.25rem;
}

.path-value {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  color: var(--color-info);
}

/* Form Groups */
.form-group {
  margin-bottom: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 0.625rem 0.875rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-input:disabled,
.form-textarea:disabled {
  background: var(--bg-secondary);
  cursor: not-allowed;
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

/* Icon Picker */
.icon-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.icon-option {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  font-size: 1rem;
}

.icon-option:hover {
  border-color: var(--color-info);
  color: var(--color-info);
}

.icon-option.selected {
  border-color: var(--color-info);
  background: var(--color-info);
  color: var(--text-on-primary);
}

.icon-option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Color Picker */
.color-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.color-option {
  width: 2rem;
  height: 2rem;
  border-radius: 0.375rem;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.selected {
  border-color: var(--text-primary);
  box-shadow: 0 0 0 2px var(--bg-card), 0 0 0 4px currentColor;
}

.color-option.selected::after {
  content: '\2713';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: white;
  font-weight: bold;
  font-size: 0.875rem;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.color-option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Category Preview */
.category-preview {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 0.5rem;
  border: 1px solid var(--border-default);
}

.preview-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 1.25rem;
}

.preview-name {
  font-weight: 600;
  color: var(--text-primary);
}

/* Form Actions */
.form-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border-default);
}

.left-actions,
.right-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.delete-disabled-hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-muted);
}

/* Delete Confirmation */
.delete-confirm {
  text-align: center;
  padding: 1rem;
}

.delete-warning {
  padding: 1.5rem;
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: 0.75rem;
  margin-bottom: 1.5rem;
}

.delete-warning i.fa-exclamation-triangle {
  font-size: 2.5rem;
  color: var(--color-warning);
  margin-bottom: 1rem;
}

.delete-warning h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}

.delete-warning p {
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.fact-warning {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: var(--color-error-bg);
  border-radius: 0.375rem;
  color: var(--color-error-dark);
  margin-top: 1rem;
}

.delete-note {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-style: italic;
  margin-top: 0.75rem;
}

.delete-actions {
  display: flex;
  justify-content: center;
  gap: 1rem;
}
</style>
