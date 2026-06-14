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

import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'
import { asIconName } from '@/utils/iconMappings'
import { ref, computed, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'
import { useLoadingState } from '@/composables/useLoadingState'
import {
  fetchCategoryFactCount,
  updateCategory,
  deleteKnowledgeCategory,
} from '@/composables/knowledge/useKnowledgeCategories'

const logger = createLogger('CategoryEditModal')
const { t } = useI18n()

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

const { isLoading, wrap } = useLoadingState()
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
const iconOptions = computed<{ value: IconName; label: string }[]>(() => [
  { value: 'folder', label: t('knowledge.modals.categoryEdit.iconFolder') },
  { value: 'book', label: t('knowledge.modals.categoryEdit.iconBook') },
  { value: 'code', label: t('knowledge.modals.categoryEdit.iconCode') },
  { value: 'cog', label: t('knowledge.modals.categoryEdit.iconSettings') },
  { value: 'file-alt', label: t('knowledge.modals.categoryEdit.iconDocument') },
  { value: 'database', label: t('knowledge.modals.categoryEdit.iconDatabase') },
  { value: 'lightbulb', label: t('knowledge.modals.categoryEdit.iconIdeas') },
  { value: 'users', label: t('knowledge.modals.categoryEdit.iconUsers') },
  { value: 'shield-alt', label: t('knowledge.modals.categoryEdit.iconSecurity') },
  { value: 'rocket', label: t('knowledge.modals.categoryEdit.iconLaunch') },
  { value: 'brain', label: t('knowledge.modals.categoryEdit.iconAiMl') },
  { value: 'terminal', label: t('knowledge.modals.categoryEdit.iconTerminal') },
])

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
      icon: newCategory.icon || 'folder',
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
    factCount.value = await fetchCategoryFactCount(categoryId)
  } catch (err) {
    logger.error('Failed to load fact count:', err)
    factCount.value = 0
  } finally {
    isLoadingFactCount.value = false
  }
}

async function saveChanges(): Promise<void> {
  if (!props.category) return

  error.value = null
  successMessage.value = null
  await wrap(async () => {
    try {
      const data = await updateCategory(props.category!.id, formData.value)

      if (data?.status === 'success') {
        successMessage.value = t('knowledge.modals.categoryEdit.updateSuccess')
        emit('updated', { ...props.category!, ...formData.value })

        // Close modal after brief delay to show success message
        setTimeout(() => {
          closeModal()
        }, 1000)
      } else {
        error.value = (data?.message as string) || t('knowledge.modals.categoryEdit.updateFailed')
      }
    } catch (err) {
      logger.error('Failed to update category:', err)
      error.value = err instanceof Error ? err.message : t('knowledge.modals.categoryEdit.updateFailed')
    }
  })
}

async function deleteCategory(): Promise<void> {
  if (!props.category) return

  error.value = null
  await wrap(async () => {
    try {
      const data = await deleteKnowledgeCategory(props.category!.id)

      if (data?.status === 'success') {
        emit('deleted', props.category!.id)
        closeModal()
      } else {
        error.value = (data?.message as string) || t('knowledge.modals.categoryEdit.deleteFailed')
        showDeleteConfirm.value = false
      }
    } catch (err) {
      logger.error('Failed to delete category:', err)

      // Handle specific error cases
      const errorMessage = err instanceof Error ? err.message : String(err)
      if (errorMessage.includes('has children')) {
        error.value = t('knowledge.modals.categoryEdit.deleteHasChildren')
      } else {
        error.value = errorMessage || t('knowledge.modals.categoryEdit.deleteFailed')
      }
      showDeleteConfirm.value = false
    }
  })
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
    :title="t('knowledge.modals.categoryEdit.editTitle', { name: categoryTitle })"
    size="md"
    @close="closeModal"
  >
    <div class="category-edit-modal">
      <!-- Success Message -->
      <div v-if="successMessage" class="alert alert-success">
        <Icon name="check-circle" />
        {{ successMessage }}
      </div>

      <!-- Error Message -->
      <div v-if="error" class="alert alert-error">
        <Icon name="exclamation-circle" />
        {{ error }}
      </div>

      <!-- Delete Confirmation View -->
      <div v-if="showDeleteConfirm" class="delete-confirm">
        <div class="delete-warning">
          <Icon name="exclamation-triangle" />
          <h3>{{ $t('knowledge.modals.categoryEdit.deleteConfirmTitle') }}</h3>
          <p>
            {{ $t('knowledge.modals.categoryEdit.deleteConfirmMessage', { name: categoryTitle }) }}
          </p>
          <p v-if="factCount > 0" class="fact-warning">
            <Icon name="file-alt" />
            {{ $t('knowledge.modals.categoryEdit.factWarning', { count: factCount }) }}
          </p>
          <p class="delete-note">{{ $t('knowledge.modals.categoryEdit.cannotUndo') }}</p>
        </div>
        <div class="delete-actions">
          <BaseButton
            variant="outline-solid"
            @click="cancelDelete"
            :disabled="isLoading"
          >
            {{ $t('knowledge.modals.categoryEdit.cancel') }}
          </BaseButton>
          <BaseButton
            variant="error"
            @click="deleteCategory"
            :disabled="isLoading"
          >
            <Icon name="spinner" class="animate-spin" v-if="isLoading" />
            <span v-else>{{ $t('knowledge.modals.categoryEdit.deleteCategory') }}</span>
          </BaseButton>
        </div>
      </div>

      <!-- Edit Form -->
      <div v-else class="edit-form">
        <!-- Category Info -->
        <div v-if="props.category?.path" class="category-path">
          <label>{{ $t('knowledge.modals.categoryEdit.path') }}</label>
          <span class="path-value">{{ props.category.path }}</span>
        </div>

        <!-- Name Field -->
        <div class="form-group">
          <label for="category-name">{{ $t('knowledge.modals.categoryEdit.name') }}</label>
          <input
            id="category-name"
            v-model="formData.name"
            type="text"
            class="form-input"
            :placeholder="$t('knowledge.modals.categoryEdit.namePlaceholder')"
            :disabled="isLoading"
          />
        </div>

        <!-- Description Field -->
        <div class="form-group">
          <label for="category-description">{{ $t('knowledge.modals.categoryEdit.descriptionLabel') }}</label>
          <textarea
            id="category-description"
            v-model="formData.description"
            class="form-textarea"
            :placeholder="$t('knowledge.modals.categoryEdit.descriptionPlaceholder')"
            rows="3"
            :disabled="isLoading"
          ></textarea>
        </div>

        <!-- Icon Selection -->
        <div class="form-group">
          <label>{{ $t('knowledge.modals.categoryEdit.icon') }}</label>
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
              <Icon :name="icon.value" />
            </button>
          </div>
        </div>

        <!-- Color Selection -->
        <div class="form-group">
          <label>{{ $t('knowledge.modals.categoryEdit.color') }}</label>
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
          <label>{{ $t('knowledge.modals.categoryEdit.preview') }}</label>
          <div class="category-preview">
            <div
              class="preview-icon"
              :style="{ backgroundColor: formData.color }"
            >
              <Icon :name="asIconName(formData.icon, 'folder')" />
            </div>
            <span class="preview-name">{{ formData.name || $t('knowledge.modals.categoryEdit.namePlaceholder') }}</span>
          </div>
        </div>

        <!-- Actions -->
        <div class="form-actions">
          <div class="left-actions">
            <BaseButton
              v-if="canDelete"
              variant="error"
              @click="confirmDelete"
              :disabled="isLoading"
            >
              <Icon name="trash" />
              {{ $t('knowledge.modals.categoryEdit.delete') }}
            </BaseButton>
            <span v-else class="delete-disabled-hint">
              <Icon name="info-circle" />
              {{ $t('knowledge.modals.categoryEdit.hasSubcategories') }}
            </span>
          </div>
          <div class="right-actions">
            <BaseButton
              variant="outline-solid"
              @click="closeModal"
              :disabled="isLoading"
            >
              {{ $t('knowledge.modals.categoryEdit.cancel') }}
            </BaseButton>
            <BaseButton
              variant="primary"
              @click="saveChanges"
              :disabled="isLoading || !hasUnsavedChanges"
            >
              <Icon name="spinner" class="animate-spin" v-if="isLoading" />
              <span v-else>{{ $t('knowledge.modals.categoryEdit.saveChanges') }}</span>
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.category-edit-modal {
  padding: var(--spacing-4);
}

/* Alerts */
.alert {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3-5) var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-6);
  font-size: var(--text-sm);
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
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-6);
}

.category-path label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-1);
}

.path-value {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-info);
}

/* Form Groups */
.form-group {
  margin-bottom: var(--spacing-5);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: 500;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200), box-shadow var(--duration-200);
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
.form-input:focus-visible,
.form-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
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
  gap: var(--spacing-2);
}

.icon-option {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200);
  font-size: var(--text-base);
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
  gap: var(--spacing-2);
}

.color-option {
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-md);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all var(--duration-200);
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
  font-size: var(--text-sm);
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
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.preview-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: var(--text-xl);
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
  margin-top: var(--spacing-6);
  padding-top: var(--spacing-6);
  border-top: 1px solid var(--border-default);
}

.left-actions,
.right-actions {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

.delete-disabled-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

/* Delete Confirmation */
.delete-confirm {
  text-align: center;
  padding: var(--spacing-4);
}

.delete-warning {
  padding: var(--spacing-6);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-xl);
  margin-bottom: var(--spacing-6);
}

.delete-warning i.fa-exclamation-triangle {
  font-size: 2.5rem;
  color: var(--color-warning);
  margin-bottom: var(--spacing-4);
}

.delete-warning h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-3);
}

.delete-warning p {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.fact-warning {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--color-error-bg);
  border-radius: var(--radius-md);
  color: var(--color-error-dark);
  margin-top: var(--spacing-4);
}

.delete-note {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-style: italic;
  margin-top: var(--spacing-3);
}

.delete-actions {
  display: flex;
  justify-content: center;
  gap: var(--spacing-4);
}
</style>
