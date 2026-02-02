<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Document Export Modal Component (Issue #747)
 *
 * Modal for exporting documents in various formats.
 * Features:
 * - Format selection: Markdown, JSON, PDF
 * - Scope: Single document, Category, All
 * - Include/exclude metadata option
 */

import { ref, computed, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DocumentExportModal')

// =============================================================================
// Type Definitions
// =============================================================================

export interface ExportDocument {
  id: string
  title: string
  content: string
  path?: string
  metadata?: Record<string, unknown>
}

export interface ExportOptions {
  format: 'markdown' | 'json' | 'txt'
  includeMetadata: boolean
}

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps<{
  modelValue: boolean
  documents: ExportDocument[]
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'export', options: ExportOptions): void
}>()

// =============================================================================
// State
// =============================================================================

const isExporting = ref(false)
const selectedFormat = ref<'markdown' | 'json' | 'txt'>('markdown')
const includeMetadata = ref(true)
const error = ref<string | null>(null)

// =============================================================================
// Computed
// =============================================================================

const isOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const documentCount = computed(() => props.documents?.length || 0)

const modalTitle = computed(() => {
  return props.title || `Export ${documentCount.value} Document${documentCount.value !== 1 ? 's' : ''}`
})

const formatOptions = [
  {
    value: 'markdown' as const,
    label: 'Markdown',
    icon: 'fas fa-file-alt',
    description: 'Best for documentation and readability'
  },
  {
    value: 'json' as const,
    label: 'JSON',
    icon: 'fas fa-file-code',
    description: 'Best for data processing and imports'
  },
  {
    value: 'txt' as const,
    label: 'Plain Text',
    icon: 'fas fa-file',
    description: 'Simple format, no formatting'
  }
]

// =============================================================================
// Methods
// =============================================================================

function closeModal(): void {
  isOpen.value = false
  error.value = null
}

async function performExport(): Promise<void> {
  if (documentCount.value === 0) {
    error.value = 'No documents to export'
    return
  }

  isExporting.value = true
  error.value = null

  try {
    let content: string
    let filename: string
    let mimeType: string

    const docs = props.documents

    switch (selectedFormat.value) {
      case 'json':
        content = JSON.stringify(
          includeMetadata.value ? docs : docs.map(d => ({
            id: d.id,
            title: d.title,
            content: d.content
          })),
          null,
          2
        )
        filename = `export-${Date.now()}.json`
        mimeType = 'application/json'
        break

      case 'txt':
        content = docs.map(doc => {
          let text = `${doc.title}\n${'='.repeat(doc.title.length)}\n\n${doc.content}`
          if (includeMetadata.value && doc.metadata) {
            text += `\n\n---\nMetadata: ${JSON.stringify(doc.metadata)}`
          }
          return text
        }).join('\n\n---\n\n')
        filename = `export-${Date.now()}.txt`
        mimeType = 'text/plain'
        break

      case 'markdown':
      default:
        content = docs.map(doc => {
          let md = `# ${doc.title}\n\n${doc.content}`
          if (includeMetadata.value && doc.path) {
            md = `<!-- Path: ${doc.path} -->\n${md}`
          }
          return md
        }).join('\n\n---\n\n')
        filename = `export-${Date.now()}.md`
        mimeType = 'text/markdown'
        break
    }

    // Create and trigger download
    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    // Emit event and close
    emit('export', {
      format: selectedFormat.value,
      includeMetadata: includeMetadata.value
    })

    closeModal()
  } catch (err) {
    logger.error('Export failed:', err)
    error.value = 'Failed to export documents'
  } finally {
    isExporting.value = false
  }
}

// Reset state when modal opens
watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    error.value = null
    selectedFormat.value = 'markdown'
    includeMetadata.value = true
  }
})
</script>

<template>
  <BaseModal
    v-model="isOpen"
    :title="modalTitle"
    size="small"
    @close="closeModal"
  >
    <div class="export-modal">
      <!-- Error Message -->
      <div v-if="error" class="alert alert-error">
        <i class="fas fa-exclamation-circle"></i>
        {{ error }}
      </div>

      <!-- Document Count -->
      <div class="export-summary">
        <i class="fas fa-file-export"></i>
        <span>{{ documentCount }} document{{ documentCount !== 1 ? 's' : '' }} will be exported</span>
      </div>

      <!-- Format Selection -->
      <div class="form-group">
        <label>Export Format</label>
        <div class="format-options">
          <label
            v-for="format in formatOptions"
            :key="format.value"
            class="format-option"
            :class="{ selected: selectedFormat === format.value }"
          >
            <input
              type="radio"
              :value="format.value"
              v-model="selectedFormat"
              class="sr-only"
            />
            <i :class="format.icon" class="format-icon"></i>
            <div class="format-info">
              <span class="format-label">{{ format.label }}</span>
              <span class="format-desc">{{ format.description }}</span>
            </div>
            <i v-if="selectedFormat === format.value" class="fas fa-check check-icon"></i>
          </label>
        </div>
      </div>

      <!-- Options -->
      <div class="form-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            v-model="includeMetadata"
          />
          <span>Include metadata (paths, dates, etc.)</span>
        </label>
      </div>

      <!-- Actions -->
      <div class="modal-actions">
        <BaseButton
          variant="outline"
          @click="closeModal"
          :disabled="isExporting"
        >
          Cancel
        </BaseButton>
        <BaseButton
          variant="primary"
          @click="performExport"
          :disabled="isExporting || documentCount === 0"
        >
          <i v-if="isExporting" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-download"></i>
          Export
        </BaseButton>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.export-modal {
  padding: 0.5rem;
}

/* Alert */
.alert {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
}

.alert-error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border: 1px solid var(--color-error-border);
}

/* Export Summary */
.export-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 0.5rem;
  margin-bottom: 1.5rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.export-summary i {
  font-size: 1.25rem;
  color: var(--color-info);
}

/* Form Groups */
.form-group {
  margin-bottom: 1.25rem;
}

.form-group > label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-primary);
  font-size: 0.875rem;
}

/* Format Options */
.format-options {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.format-option {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border: 2px solid var(--border-default);
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.15s;
}

.format-option:hover {
  border-color: var(--color-info);
  background: var(--bg-secondary);
}

.format-option.selected {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

.format-icon {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  border-radius: 0.375rem;
  color: var(--color-info);
  font-size: 1rem;
}

.format-option.selected .format-icon {
  background: var(--color-info);
  color: var(--text-on-primary);
}

.format-info {
  flex: 1;
}

.format-label {
  display: block;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.125rem;
}

.format-desc {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.check-icon {
  color: var(--color-info);
}

/* Checkbox */
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.checkbox-label input[type="checkbox"] {
  width: 1rem;
  height: 1rem;
  accent-color: var(--color-info);
}

/* Screen reader only */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Actions */
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}
</style>
