<template>
  <div class="memory-orphan-manager">
    <div class="section-header">
      <div class="header-content">
        <h4><i class="fas fa-brain"></i> {{ $t('knowledge.memoryOrphan.title') }}</h4>
        <p class="header-description">
          {{ $t('knowledge.memoryOrphan.description') }}
        </p>
      </div>
    </div>

    <div class="orphan-content">
      <!-- Scan Results Summary -->
      <div v-if="orphanScanResult" class="orphan-summary">
        <div class="summary-stats">
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.total_conversation_entities }}</span>
            <span class="stat-label">{{ $t('knowledge.memoryOrphan.conversationEntities') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.active_sessions }}</span>
            <span class="stat-label">{{ $t('knowledge.memoryOrphan.activeSessions') }}</span>
          </div>
          <div class="stat-item highlight">
            <span class="stat-value">{{ orphanScanResult.orphaned_count }}</span>
            <span class="stat-label">{{ $t('knowledge.memoryOrphan.orphanedEntities') }}</span>
          </div>
        </div>

        <!-- Orphan Preview -->
        <div v-if="orphanScanResult.orphaned_entities?.length > 0" class="orphan-preview">
          <h5>{{ $t('knowledge.memoryOrphan.previewTitle') }}</h5>
          <div class="orphan-list">
            <div
              v-for="entity in orphanScanResult.orphaned_entities.slice(0, 10)"
              :key="entity.id"
              class="orphan-item"
            >
              <div class="orphan-meta">
                <span class="orphan-name">{{ entity.name }}</span>
              </div>
              <div v-if="entity.observations?.length" class="orphan-observations">
                <p v-for="(obs, idx) in entity.observations" :key="idx" class="observation-text">
                  {{ obs }}
                </p>
              </div>
              <small class="orphan-session">Session: {{ entity.session_id?.slice(0, 12) }}...</small>
            </div>
          </div>
          <p v-if="orphanScanResult.orphaned_entities.length > 10" class="orphan-more">
            {{ $t('knowledge.memoryOrphan.moreOrphans', { count: orphanScanResult.orphaned_entities.length - 10 }) }}
          </p>
        </div>
      </div>

      <!-- Actions -->
      <div class="orphan-actions">
        <div class="action-card">
          <div class="action-content">
            <div class="action-icon scan">
              <i class="fas fa-search"></i>
            </div>
            <h5>{{ $t('knowledge.memoryOrphan.scanTitle') }}</h5>
            <p>{{ $t('knowledge.memoryOrphan.scanDescription') }}</p>
            <small class="action-meta">{{ $t('knowledge.memoryOrphan.scanMeta') }}</small>
          </div>
          <BaseButton
            variant="secondary"
            @click="scanOrphans"
            :disabled="isScanning || isCleaning"
            :loading="isScanning"
            class="action-btn"
          >
            <i v-if="!isScanning" class="fas fa-search"></i>
            {{ isScanning ? $t('knowledge.memoryOrphan.scanning') : $t('knowledge.memoryOrphan.scanNow') }}
          </BaseButton>
        </div>

        <div class="action-card warning">
          <div class="action-content">
            <div class="action-icon cleanup">
              <i class="fas fa-broom"></i>
            </div>
            <h5>{{ $t('knowledge.memoryOrphan.cleanupTitle') }}</h5>
            <p>{{ $t('knowledge.memoryOrphan.cleanupDescription') }}</p>
            <small class="action-meta">
              {{ $t('knowledge.memoryOrphan.entitiesToClean', { count: orphanScanResult?.orphaned_count || 0 }) }}
            </small>
          </div>
          <BaseButton
            variant="warning"
            @click="cleanupOrphans"
            :disabled="!orphanScanResult || orphanScanResult.orphaned_count === 0 || isCleaning || isScanning"
            :loading="isCleaning"
            class="action-btn"
          >
            <i v-if="!isCleaning" class="fas fa-broom"></i>
            {{ isCleaning ? $t('knowledge.memoryOrphan.cleaning') : $t('knowledge.memoryOrphan.cleanUp') }}
          </BaseButton>
        </div>
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
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import apiClient from '@/utils/ApiClient.ts'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()

const logger = createLogger('MemoryOrphanManager')

// Emit events for parent component
const emit = defineEmits<{
  (e: 'cleanup-complete'): void
}>()

// Types
interface OrphanedEntity {
  id: string
  name: string
  session_id: string
  created_at?: string
  observations?: string[]
}

interface OrphanScanResult {
  total_conversation_entities: number
  active_sessions: number
  orphaned_count: number
  orphaned_entities: OrphanedEntity[]
}

interface StatusMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
  icon: string
}

// State
const orphanScanResult = ref<OrphanScanResult | null>(null)
const isScanning = ref(false)
const isCleaning = ref(false)
const statusMessage = ref<StatusMessage | null>(null)

// Methods
const showStatus = (type: StatusMessage['type'], text: string) => {
  const icons = {
    success: 'fas fa-check-circle',
    error: 'fas fa-exclamation-circle',
    warning: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle'
  }
  statusMessage.value = { type, text, icon: icons[type] }

  // Auto-dismiss success messages
  if (type === 'success') {
    setTimeout(() => {
      if (statusMessage.value?.type === 'success') {
        statusMessage.value = null
      }
    }, 5000)
  }
}

const scanOrphans = async () => {
  if (isScanning.value || isCleaning.value) return

  try {
    isScanning.value = true
    orphanScanResult.value = null
    statusMessage.value = null

    const response = await apiClient.get('/api/memory/entities/orphans')

    // Check if we got a valid Response object
    if (!response || typeof response.ok === 'undefined') {
      throw new Error('Invalid response from server - request may have timed out')
    }

    if (!response.ok) {
      // Safely get error text - response.text may not exist if request failed
      const errorText = typeof response.text === 'function'
        ? await response.text().catch(() => '')
        : ''
      throw new Error(errorText || `Server error: ${response.status}`)
    }

    const data = await response.json()

    if (data.success) {
      orphanScanResult.value = data.data as OrphanScanResult

      if (data.data.orphaned_count > 0) {
        showStatus('warning',
          t('knowledge.memoryOrphan.foundOrphans', { count: data.data.orphaned_count }))
      } else {
        showStatus('success',
          t('knowledge.memoryOrphan.allActive', { count: data.data.total_conversation_entities }))
      }
    } else {
      throw new Error(data.message || 'Failed to scan for orphans')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    logger.error('Failed to scan for memory orphans:', error)
    showStatus('error', errorMessage || t('knowledge.memoryOrphan.scanError'))
  } finally {
    isScanning.value = false
  }
}

const cleanupOrphans = async () => {
  if (isCleaning.value || isScanning.value) return
  if (!orphanScanResult.value || orphanScanResult.value.orphaned_count === 0) return

  // Confirm before cleanup
  const confirmed = window.confirm(
    t('knowledge.memoryOrphan.confirmCleanup', { count: orphanScanResult.value.orphaned_count })
  )

  if (!confirmed) return

  try {
    isCleaning.value = true

    const response = await apiClient.delete('/api/memory/entities/orphans?dry_run=false')

    // Check if we got a valid Response object
    if (!response || typeof response.ok === 'undefined') {
      throw new Error('Invalid response from server - request may have timed out')
    }

    if (!response.ok) {
      // Safely get error text - response.text may not exist if request failed
      const errorText = typeof response.text === 'function'
        ? await response.text().catch(() => '')
        : ''
      throw new Error(errorText || `Server error: ${response.status}`)
    }

    const data = await response.json()

    if (data.success) {
      const deletedCount = data.data.deleted_count
      const failedCount = data.data.failed_count || 0

      if (failedCount > 0) {
        showStatus('warning', t('knowledge.memoryOrphan.partialDelete', { deleted: deletedCount, failed: failedCount }))
      } else {
        showStatus('success', t('knowledge.memoryOrphan.deleteSuccess', { count: deletedCount }))
      }

      // Clear the scan result after cleanup
      orphanScanResult.value = null

      // Emit event so parent can refresh
      emit('cleanup-complete')
    } else {
      throw new Error(data.message || 'Failed to cleanup orphans')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    logger.error('Failed to cleanup memory orphans:', error)
    showStatus('error', errorMessage || t('knowledge.memoryOrphan.cleanupError'))
  } finally {
    isCleaning.value = false
  }
}
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */

.memory-orphan-manager {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.section-header {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
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

.orphan-content {
  padding: var(--spacing-5);
}

.orphan-summary {
  margin-bottom: var(--spacing-6);
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-item {
  text-align: center;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.stat-item.highlight {
  background: var(--color-warning-bg);
  border-color: var(--color-warning);
}

.stat-value {
  display: block;
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-item.highlight .stat-value {
  color: var(--color-warning-dark);
}

.stat-label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.orphan-preview {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.orphan-preview h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-warning-dark);
  margin: 0 0 var(--spacing-3) 0;
}

.orphan-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  max-height: 300px;
  overflow-y: auto;
}

.orphan-item {
  background: var(--bg-card);
  border: 1px solid var(--color-warning-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
}

.orphan-meta {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.orphan-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.orphan-observations {
  margin-bottom: var(--spacing-2);
}

.observation-text {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: var(--spacing-1) 0;
  line-height: var(--leading-relaxed);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orphan-session {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.orphan-more {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-style: italic;
  margin: var(--spacing-3) 0 0 0;
  text-align: center;
}

.orphan-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-6);
}

.action-card {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 200px;
  transition: var(--transition-all);
  background: var(--bg-card);
}

.action-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-md);
}

.action-card.warning {
  border-color: var(--color-warning-light);
  background: var(--color-warning-bg);
}

.action-card.warning:hover {
  border-color: var(--color-warning);
}

.action-content {
  flex: 1;
}

.action-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  margin-bottom: var(--spacing-4);
}

.action-icon.scan {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.action-icon.cleanup {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.action-card h5 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2) 0;
}

.action-card p {
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-4) 0;
  line-height: var(--leading-normal);
}

.action-meta {
  color: var(--text-muted);
  font-size: var(--text-xs);
  display: block;
  margin-bottom: var(--spacing-4);
}

.action-btn {
  width: 100%;
}

/* Status Messages */
.status-message {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-top: var(--spacing-6);
}

.status-message.success {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success);
  color: var(--color-success-dark);
}

.status-message.error {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  color: var(--color-error-dark);
}

.status-message.warning {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  color: var(--color-warning-dark);
}

.status-message.info {
  background: var(--color-info-bg);
  border: 1px solid var(--color-info);
  color: var(--color-info-dark);
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
  transition: opacity var(--duration-200);
}

.dismiss-btn:hover {
  opacity: 1;
}

/* Responsive */
@media (max-width: 768px) {
  .orphan-actions {
    grid-template-columns: 1fr;
  }

  .summary-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
