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

import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch } from 'vue'
import { BaseModal } from '@autobot/ui'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'

const logger = createLogger('DocumentExportModal')
const { t } = useI18n()

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
  return props.title || t('knowledge.modals.export.title', { count: documentCount.value })
})

const formatOptions = computed(() => [
  {
    value: 'markdown' as const,
    label: t('knowledge.modals.export.formatMarkdown'),
    icon: 'file-alt' as const,
    description: t('knowledge.modals.export.formatMarkdownDesc')
  },
  {
    value: 'json' as const,
    label: t('knowledge.modals.export.formatJson'),
    icon: 'file-code' as const,
    description: t('knowledge.modals.export.formatJsonDesc')
  },
  {
    value: 'txt' as const,
    label: t('knowledge.modals.export.formatPlainText'),
    icon: 'file' as const,
    description: t('knowledge.modals.export.formatPlainTextDesc')
  }
])

// =============================================================================
// Methods
// =============================================================================

function closeModal(): void {
  isOpen.value = false
  error.value = null
}

async function performExport(): Promise<void> {
  if (documentCount.value === 0) {
    error.value = t('knowledge.modals.export.noDocuments')
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
    error.value = t('knowledge.modals.export.exportFailed')
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
    size="sm"
    @close="closeModal"
  >
    <div class="export-modal">
      <!-- Error Message -->
      <div v-if="error" class="alert alert-error">
        <Icon name="exclamation-circle" />
        {{ error }}
      </div>

      <!-- Document Count -->
      <div class="export-summary">
        <Icon name="file-export" />
        <span>{{ $t('knowledge.modals.export.documentCount', { count: documentCount }) }}</span>
      </div>

      <!-- Format Selection -->
      <div class="form-group">
        <label>{{ $t('knowledge.modals.export.exportFormat') }}</label>
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
            <Icon :name="format.icon" />
            <div class="format-info">
              <span class="format-label">{{ format.label }}</span>
              <span class="format-desc">{{ format.description }}</span>
            </div>
            <Icon name="check" class="check-icon" v-if="selectedFormat === format.value" />
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
          <span>{{ $t('knowledge.modals.export.includeMetadata') }}</span>
        </label>
      </div>

      <!-- Actions -->
      <div class="modal-actions">
        <BaseButton
          variant="outline-solid"
          @click="closeModal"
          :disabled="isExporting"
        >
          {{ $t('knowledge.modals.export.cancel') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          @click="performExport"
          :disabled="isExporting || documentCount === 0"
        >
          <Icon name="spinner" class="animate-spin" v-if="isExporting" />
          <Icon name="download" v-else />
          {{ $t('knowledge.modals.export.export') }}
        </BaseButton>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.export-modal {
  padding: var(--spacing-2);
}

/* Alert */
.alert {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-4);
  font-size: var(--text-sm);
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
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-6);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.export-summary i {
  font-size: var(--text-xl);
  color: var(--color-info);
}

/* Form Groups */
.form-group {
  margin-bottom: var(--spacing-5);
}

.form-group > label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: 500;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

/* Format Options */
.format-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.format-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3-5) var(--spacing-4);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-150);
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
  border-radius: var(--radius-md);
  color: var(--color-info);
  font-size: var(--text-base);
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
  margin-bottom: var(--spacing-0-5);
}

.format-desc {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.check-icon {
  color: var(--color-info);
}

/* Checkbox */
.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
  font-size: var(--text-sm);
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
  padding: var(--spacing-0);
  margin: var(--spacing-neg-px);
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Actions */
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  margin-top: var(--spacing-6);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}
</style>
