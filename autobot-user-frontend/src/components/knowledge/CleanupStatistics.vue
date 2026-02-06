<template>
  <div class="cleanup-statistics">
    <div class="section-header">
      <div class="header-content">
        <h4><i class="fas fa-broom"></i> Cleanup & Optimization</h4>
        <p class="header-description">
          Remove empty facts, orphaned tags, and fix metadata issues
        </p>
      </div>
    </div>

    <div class="cleanup-content">
      <!-- Cleanup Options -->
      <div class="cleanup-options">
        <div class="option-item">
          <label class="option-checkbox">
            <input type="checkbox" v-model="options.removeEmpty" />
            <span class="checkmark"></span>
            <span class="option-text">
              <strong>Remove Empty Facts</strong>
              <small>Delete facts with no content</small>
            </span>
          </label>
        </div>

        <div class="option-item">
          <label class="option-checkbox">
            <input type="checkbox" v-model="options.removeOrphanedTags" />
            <span class="checkmark"></span>
            <span class="option-text">
              <strong>Remove Orphaned Tags</strong>
              <small>Delete tags with no associated facts</small>
            </span>
          </label>
        </div>

        <div class="option-item">
          <label class="option-checkbox">
            <input type="checkbox" v-model="options.fixMetadata" />
            <span class="checkmark"></span>
            <span class="option-text">
              <strong>Fix Metadata Issues</strong>
              <small>Repair malformed JSON metadata</small>
            </span>
          </label>
        </div>
      </div>

      <!-- Scan Results -->
      <div v-if="scanResult" class="scan-results">
        <h5>Scan Results</h5>
        <div class="results-grid">
          <div class="result-item" :class="{ 'has-issues': scanResult.issues_found.empty_facts > 0 }">
            <span class="result-icon"><i class="fas fa-file-circle-minus"></i></span>
            <span class="result-value">{{ scanResult.issues_found.empty_facts || 0 }}</span>
            <span class="result-label">Empty Facts</span>
          </div>

          <div class="result-item" :class="{ 'has-issues': scanResult.issues_found.orphaned_tags > 0 }">
            <span class="result-icon"><i class="fas fa-tags"></i></span>
            <span class="result-value">{{ scanResult.issues_found.orphaned_tags || 0 }}</span>
            <span class="result-label">Orphaned Tags</span>
          </div>

          <div class="result-item" :class="{ 'has-issues': scanResult.issues_found.malformed_metadata > 0 }">
            <span class="result-icon"><i class="fas fa-code"></i></span>
            <span class="result-value">{{ scanResult.issues_found.malformed_metadata || 0 }}</span>
            <span class="result-label">Metadata Issues</span>
          </div>

          <div class="result-item total">
            <span class="result-icon"><i class="fas fa-exclamation-triangle"></i></span>
            <span class="result-value">{{ getTotalIssues }}</span>
            <span class="result-label">Total Issues</span>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="cleanup-actions">
        <BaseButton
          variant="secondary"
          @click="runDryScan"
          :disabled="isScanning || isCleaning"
          :loading="isScanning"
        >
          <i v-if="!isScanning" class="fas fa-search"></i>
          {{ isScanning ? 'Scanning...' : 'Scan for Issues' }}
        </BaseButton>

        <BaseButton
          variant="warning"
          @click="runCleanup"
          :disabled="!scanResult || getTotalIssues === 0 || isCleaning || isScanning"
          :loading="isCleaning"
        >
          <i v-if="!isCleaning" class="fas fa-broom"></i>
          {{ isCleaning ? 'Cleaning...' : 'Run Cleanup' }}
        </BaseButton>
      </div>

      <!-- Status Messages -->
      <div v-if="statusMessage" :class="['status-message', statusMessage.type]">
        <i :class="statusMessage.icon"></i>
        <span>{{ statusMessage.text }}</span>
        <button @click="statusMessage = null" class="dismiss-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CleanupStatistics')

const emit = defineEmits<{
  (e: 'cleanup-complete', result: { action: string; details: string }): void
}>()

// Types
interface CleanupOptions {
  removeEmpty: boolean
  removeOrphanedTags: boolean
  fixMetadata: boolean
}

interface IssuesFound {
  empty_facts: number
  orphaned_tags: number
  malformed_metadata: number
}

interface ScanResult {
  dry_run: boolean
  issues_found: IssuesFound
}

interface StatusMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
  icon: string
}

// State
const options = ref<CleanupOptions>({
  removeEmpty: true,
  removeOrphanedTags: true,
  fixMetadata: true
})

const isScanning = ref(false)
const isCleaning = ref(false)
const scanResult = ref<ScanResult | null>(null)
const statusMessage = ref<StatusMessage | null>(null)

// Computed
const getTotalIssues = computed(() => {
  if (!scanResult.value) return 0
  const issues = scanResult.value.issues_found
  return (issues.empty_facts || 0) + (issues.orphaned_tags || 0) + (issues.malformed_metadata || 0)
})

// Methods
const showStatus = (type: StatusMessage['type'], text: string) => {
  const icons = {
    success: 'fas fa-check-circle',
    error: 'fas fa-exclamation-circle',
    warning: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle'
  }
  statusMessage.value = { type, text, icon: icons[type] }

  if (type === 'success') {
    setTimeout(() => {
      if (statusMessage.value?.type === 'success') {
        statusMessage.value = null
      }
    }, 5000)
  }
}

const runDryScan = async () => {
  if (isScanning.value || isCleaning.value) return

  try {
    isScanning.value = true
    scanResult.value = null
    statusMessage.value = null

    const response = await apiClient.post('/api/knowledge-maintenance/cleanup', {
      remove_empty: options.value.removeEmpty,
      remove_orphaned_tags: options.value.removeOrphanedTags,
      fix_metadata: options.value.fixMetadata,
      dry_run: true
    })

    const data = await parseApiResponse(response)

    if (data.success !== false) {
      scanResult.value = {
        dry_run: true,
        issues_found: data.issues_found || { empty_facts: 0, orphaned_tags: 0, malformed_metadata: 0 }
      }

      const total = getTotalIssues.value
      if (total > 0) {
        showStatus('warning', `Found ${total} issues that can be cleaned up`)
      } else {
        showStatus('success', 'No issues found - knowledge base is clean!')
      }
    } else {
      throw new Error(data.message || 'Scan failed')
    }
  } catch (error: any) {
    logger.error('Failed to scan for issues:', error)
    showStatus('error', error.message || 'Failed to scan for issues')
  } finally {
    isScanning.value = false
  }
}

const runCleanup = async () => {
  if (isCleaning.value || isScanning.value) return
  if (!scanResult.value || getTotalIssues.value === 0) return

  const confirmed = window.confirm(
    `Are you sure you want to clean up ${getTotalIssues.value} issues?`
  )

  if (!confirmed) return

  try {
    isCleaning.value = true

    const response = await apiClient.post('/api/knowledge-maintenance/cleanup', {
      remove_empty: options.value.removeEmpty,
      remove_orphaned_tags: options.value.removeOrphanedTags,
      fix_metadata: options.value.fixMetadata,
      dry_run: false
    })

    const data = await parseApiResponse(response)

    if (data.success !== false) {
      const total =
        (data.fixes_applied?.empty_removed || 0) +
        (data.fixes_applied?.tags_cleaned || 0) +
        (data.fixes_applied?.metadata_fixed || 0)

      showStatus('success', `Successfully cleaned up ${total} issues`)
      scanResult.value = null

      emit('cleanup-complete', {
        action: 'Knowledge Base Cleanup',
        details: `Cleaned ${total} issues`
      })
    } else {
      throw new Error(data.message || 'Cleanup failed')
    }
  } catch (error: any) {
    logger.error('Failed to run cleanup:', error)
    showStatus('error', error.message || 'Failed to run cleanup')
  } finally {
    isCleaning.value = false
  }
}
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.cleanup-statistics {
  background: var(--bg-primary);
}

.section-header {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.section-header h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-1) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.header-description {
  color: var(--text-secondary);
  margin: 0;
  font-size: var(--text-sm);
}

.cleanup-content {
  padding: var(--spacing-5);
}

.cleanup-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-6);
}

.option-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3) var(--spacing-4);
}

.option-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  cursor: pointer;
  position: relative;
}

.option-checkbox input[type="checkbox"] {
  position: absolute;
  opacity: 0;
}

.checkmark {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid var(--border-strong);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.option-checkbox input:checked ~ .checkmark {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.option-checkbox input:checked ~ .checkmark::after {
  content: '\2713';
  color: var(--text-on-primary);
  font-size: var(--text-xs);
}

.option-text {
  display: flex;
  flex-direction: column;
}

.option-text strong {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.option-text small {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.scan-results {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.scan-results h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-warning);
  margin: 0 0 var(--spacing-4) 0;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-3);
}

.result-item {
  background: var(--bg-primary);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  text-align: center;
}

.result-item.has-issues {
  border-color: var(--color-error);
  background: var(--color-error-bg);
}

.result-item.total {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.result-icon {
  font-size: 1.25rem;
  color: var(--text-secondary);
}

.result-item.has-issues .result-icon {
  color: var(--color-error);
}

.result-value {
  display: block;
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.result-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.cleanup-actions {
  display: flex;
  gap: var(--spacing-4);
}

.status-message {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-top: var(--spacing-4);
}

.status-message.success {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success);
  color: var(--color-success);
}

.status-message.error {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  color: var(--color-error);
}

.status-message.warning {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  color: var(--color-warning);
}

.status-message span {
  flex: 1;
}

.dismiss-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--spacing-1);
  color: inherit;
  opacity: 0.7;
}

@media (max-width: 768px) {
  .results-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .cleanup-actions {
    flex-direction: column;
  }
}
</style>
