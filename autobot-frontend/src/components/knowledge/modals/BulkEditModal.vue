<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Bulk Edit Modal Component (Issue #747)
 *
 * Modal for bulk editing multiple knowledge entries.
 * Supports:
 * - Bulk category change
 * - Bulk tag add/remove
 * - Preview of affected entries
 */

import { ref, computed, watch } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BulkEditModal')

// =============================================================================
// Type Definitions
// =============================================================================

export type BulkEditMode = 'category' | 'tags-add' | 'tags-remove'

export interface BulkEditEntry {
  id: string
  title: string
  category: string
  tags: string[]
}

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps<{
  modelValue: boolean
  mode: BulkEditMode
  selectedEntries: BulkEditEntry[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm', payload: { mode: BulkEditMode; value: string | string[] }): void
}>()

// =============================================================================
// Store
// =============================================================================

const store = useKnowledgeStore()

// =============================================================================
// State
// =============================================================================

const selectedCategory = ref('')
const tagsInput = ref('')
const isProcessing = ref(false)

// =============================================================================
// Computed
// =============================================================================

const isOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const modalTitle = computed(() => {
  switch (props.mode) {
    case 'category':
      return 'Change Category'
    case 'tags-add':
      return 'Add Tags'
    case 'tags-remove':
      return 'Remove Tags'
    default:
      return 'Bulk Edit'
  }
})

const modalDescription = computed(() => {
  const count = props.selectedEntries.length
  switch (props.mode) {
    case 'category':
      return `Change the category for ${count} selected ${count === 1 ? 'entry' : 'entries'}`
    case 'tags-add':
      return `Add tags to ${count} selected ${count === 1 ? 'entry' : 'entries'}`
    case 'tags-remove':
      return `Remove tags from ${count} selected ${count === 1 ? 'entry' : 'entries'}`
    default:
      return ''
  }
})

const confirmButtonText = computed(() => {
  switch (props.mode) {
    case 'category':
      return 'Change Category'
    case 'tags-add':
      return 'Add Tags'
    case 'tags-remove':
      return 'Remove Tags'
    default:
      return 'Apply'
  }
})

const isValid = computed(() => {
  if (props.mode === 'category') {
    return selectedCategory.value.length > 0
  }
  return tagsInput.value.trim().length > 0
})

const parsedTags = computed(() => {
  return tagsInput.value
    .split(',')
    .map(tag => tag.trim().toLowerCase())
    .filter(tag => tag.length > 0)
})

const currentCategories = computed(() => {
  const categories = new Set(props.selectedEntries.map(e => e.category))
  return Array.from(categories)
})

const commonTags = computed(() => {
  if (props.selectedEntries.length === 0) return []

  // Find tags that exist in ALL selected entries
  const allTags = props.selectedEntries.map(e => new Set(e.tags))
  if (allTags.length === 0) return []

  const common = allTags.reduce((acc, tags) => {
    return new Set([...acc].filter(tag => tags.has(tag)))
  })

  return Array.from(common)
})

const allTags = computed(() => {
  // Get all unique tags from selected entries
  const tags = new Set<string>()
  props.selectedEntries.forEach(e => {
    e.tags.forEach(tag => tags.add(tag))
  })
  return Array.from(tags).sort()
})

// =============================================================================
// Methods
// =============================================================================

function closeModal(): void {
  isOpen.value = false
  resetForm()
}

function resetForm(): void {
  selectedCategory.value = ''
  tagsInput.value = ''
  isProcessing.value = false
}

function handleConfirm(): void {
  if (!isValid.value) return

  isProcessing.value = true

  try {
    if (props.mode === 'category') {
      emit('confirm', { mode: 'category', value: selectedCategory.value })
    } else {
      emit('confirm', { mode: props.mode, value: parsedTags.value })
    }

    closeModal()
  } catch (error) {
    logger.error('Bulk edit failed:', error)
  } finally {
    isProcessing.value = false
  }
}

function selectTagToRemove(tag: string): void {
  const current = parsedTags.value
  if (!current.includes(tag)) {
    const newTags = [...current, tag]
    tagsInput.value = newTags.join(', ')
  }
}

// Reset form when modal opens
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    resetForm()
    // Pre-select current category if all entries share the same one
    if (props.mode === 'category' && currentCategories.value.length === 1) {
      selectedCategory.value = currentCategories.value[0]
    }
  }
})
</script>

<template>
  <BaseModal
    v-model="isOpen"
    :title="modalTitle"
    size="medium"
    @close="closeModal"
  >
    <div class="bulk-edit-content">
      <!-- Description -->
      <p class="edit-description">{{ modalDescription }}</p>

      <!-- Selected Entries Preview -->
      <div class="selected-preview">
        <div class="preview-header">
          <i class="fas fa-list-check"></i>
          <span>Selected Entries ({{ selectedEntries.length }})</span>
        </div>
        <div class="preview-list">
          <div
            v-for="entry in selectedEntries.slice(0, 5)"
            :key="entry.id"
            class="preview-item"
          >
            <span class="preview-title">{{ entry.title || 'Untitled' }}</span>
            <span class="preview-category">{{ entry.category }}</span>
          </div>
          <div v-if="selectedEntries.length > 5" class="preview-more">
            +{{ selectedEntries.length - 5 }} more entries
          </div>
        </div>
      </div>

      <!-- Category Selection -->
      <div v-if="mode === 'category'" class="form-section">
        <label class="form-label">
          <i class="fas fa-folder"></i>
          New Category
        </label>
        <select v-model="selectedCategory" class="form-select">
          <option value="">Select a category...</option>
          <option
            v-for="cat in store.categories"
            :key="cat.id"
            :value="cat.name"
          >
            {{ cat.name }}
          </option>
        </select>
        <p v-if="currentCategories.length > 1" class="form-hint">
          Currently: {{ currentCategories.join(', ') }}
        </p>
      </div>

      <!-- Tags Add Section -->
      <div v-if="mode === 'tags-add'" class="form-section">
        <label class="form-label">
          <i class="fas fa-tags"></i>
          Tags to Add
        </label>
        <input
          v-model="tagsInput"
          type="text"
          class="form-input"
          placeholder="Enter tags separated by commas..."
        />
        <p class="form-hint">
          Example: documentation, api, important
        </p>

        <!-- Tag Preview -->
        <div v-if="parsedTags.length > 0" class="tags-preview">
          <span class="preview-label">Will add:</span>
          <div class="tags-list">
            <span
              v-for="tag in parsedTags"
              :key="tag"
              class="tag-chip add"
            >
              <i class="fas fa-plus"></i>
              {{ tag }}
            </span>
          </div>
        </div>
      </div>

      <!-- Tags Remove Section -->
      <div v-if="mode === 'tags-remove'" class="form-section">
        <label class="form-label">
          <i class="fas fa-tag"></i>
          Tags to Remove
        </label>

        <!-- Quick select from existing tags -->
        <div v-if="allTags.length > 0" class="existing-tags">
          <span class="existing-label">Click to select:</span>
          <div class="tags-list clickable">
            <button
              v-for="tag in allTags"
              :key="tag"
              type="button"
              class="tag-chip"
              :class="{ selected: parsedTags.includes(tag) }"
              @click="selectTagToRemove(tag)"
            >
              {{ tag }}
              <span v-if="commonTags.includes(tag)" class="common-indicator" title="Common to all selected">
                <i class="fas fa-check-double"></i>
              </span>
            </button>
          </div>
        </div>

        <input
          v-model="tagsInput"
          type="text"
          class="form-input"
          placeholder="Or type tags to remove..."
        />

        <!-- Tag Preview -->
        <div v-if="parsedTags.length > 0" class="tags-preview">
          <span class="preview-label">Will remove:</span>
          <div class="tags-list">
            <span
              v-for="tag in parsedTags"
              :key="tag"
              class="tag-chip remove"
            >
              <i class="fas fa-minus"></i>
              {{ tag }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <template #actions>
      <BaseButton variant="secondary" @click="closeModal">
        Cancel
      </BaseButton>
      <BaseButton
        variant="primary"
        :disabled="!isValid || isProcessing"
        @click="handleConfirm"
      >
        <i v-if="isProcessing" class="fas fa-spinner fa-spin"></i>
        {{ confirmButtonText }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.bulk-edit-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.edit-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin: 0;
}

/* Selected Preview */
.selected-preview {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.preview-header i {
  color: var(--color-primary);
}

.preview-list {
  max-height: 150px;
  overflow-y: auto;
}

.preview-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2) var(--spacing-3);
  border-bottom: 1px solid var(--border-light);
}

.preview-item:last-child {
  border-bottom: none;
}

.preview-title {
  font-size: var(--text-sm);
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-category {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 0.125rem var(--spacing-2);
  border-radius: var(--radius-full);
  flex-shrink: 0;
  margin-left: var(--spacing-2);
}

.preview-more {
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-style: italic;
  text-align: center;
}

/* Form Section */
.form-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.form-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.form-label i {
  color: var(--text-secondary);
}

.form-select,
.form-input {
  width: 100%;
  padding: var(--spacing-2-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-select:focus,
.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--ring-primary);
}

.form-hint {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0;
}

/* Existing Tags */
.existing-tags {
  margin-bottom: var(--spacing-2);
}

.existing-label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.tags-list.clickable .tag-chip {
  cursor: pointer;
  transition: all var(--duration-150);
}

.tags-list.clickable .tag-chip:hover {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
}

.tags-list.clickable .tag-chip.selected {
  background: var(--color-error-bg);
  color: var(--color-error);
  border-color: var(--color-error);
}

/* Tag Chips */
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  color: var(--text-primary);
}

.tag-chip.add {
  background: var(--color-success-bg);
  color: var(--color-success);
  border-color: var(--color-success);
}

.tag-chip.add i {
  font-size: 0.5rem;
}

.tag-chip.remove {
  background: var(--color-error-bg);
  color: var(--color-error);
  border-color: var(--color-error);
}

.tag-chip.remove i {
  font-size: 0.5rem;
}

.common-indicator {
  margin-left: var(--spacing-1);
  font-size: 0.5rem;
  opacity: 0.7;
}

/* Tags Preview */
.tags-preview {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.preview-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  flex-shrink: 0;
}
</style>
