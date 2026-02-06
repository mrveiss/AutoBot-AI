<template>
  <div class="session-orphan-manager">
    <div class="section-header">
      <div class="header-content">
        <h4><i class="fas fa-broom"></i> Session Orphan Cleanup</h4>
        <p class="header-description">
          Find and remove KB facts from deleted conversations
        </p>
      </div>
    </div>

    <div class="orphan-content">
      <!-- Scan Results Summary -->
      <div v-if="orphanScanResult" class="orphan-summary">
        <div class="summary-stats">
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.total_facts_checked }}</span>
            <span class="stat-label">Facts Checked</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.facts_with_session_tracking }}</span>
            <span class="stat-label">With Session Tracking</span>
          </div>
          <div class="stat-item highlight">
            <span class="stat-value">{{ orphanScanResult.orphaned_count }}</span>
            <span class="stat-label">Orphaned Facts</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.orphaned_sessions }}</span>
            <span class="stat-label">Deleted Sessions</span>
          </div>
        </div>

        <!-- Orphan Preview -->
        <div v-if="orphanScanResult.orphaned_facts?.length > 0" class="orphan-preview">
          <h5>Preview of Orphaned Facts:</h5>
          <div class="orphan-list">
            <div
              v-for="fact in orphanScanResult.orphaned_facts.slice(0, 10)"
              :key="fact.fact_id"
              class="orphan-item"
            >
              <div class="orphan-meta">
                <span class="orphan-category">{{ fact.category }}</span>
                <span v-if="fact.important" class="orphan-important">
                  <i class="fas fa-star"></i> Important
                </span>
              </div>
              <p class="orphan-content-text">{{ fact.content_preview }}</p>
              <small class="orphan-session">Session: {{ fact.session_id?.slice(0, 12) }}...</small>
            </div>
          </div>
          <p v-if="orphanScanResult.orphaned_facts.length > 10" class="orphan-more">
            ... and {{ orphanScanResult.orphaned_facts.length - 10 }} more orphaned facts
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
            <h5>Scan for Orphans</h5>
            <p>Find KB facts from conversations that have been deleted</p>
            <small class="action-meta">Non-destructive scan</small>
          </div>
          <BaseButton
            variant="secondary"
            @click="scanSessionOrphans"
            :disabled="isScanning || isCleaningOrphans"
            :loading="isScanning"
            class="action-btn"
          >
            <i v-if="!isScanning" class="fas fa-search"></i>
            {{ isScanning ? 'Scanning...' : 'Scan Now' }}
          </BaseButton>
        </div>

        <div class="action-card warning">
          <div class="action-content">
            <div class="action-icon cleanup">
              <i class="fas fa-broom"></i>
            </div>
            <h5>Clean Up Orphans</h5>
            <p>Remove orphaned facts (preserves facts marked as important)</p>
            <small class="action-meta">
              {{ orphanScanResult?.orphaned_count || 0 }} facts to clean
            </small>
          </div>
          <BaseButton
            variant="warning"
            @click="cleanupSessionOrphans"
            :disabled="!orphanScanResult || orphanScanResult.orphaned_count === 0 || isCleaningOrphans || isScanning"
            :loading="isCleaningOrphans"
            class="action-btn"
          >
            <i v-if="!isCleaningOrphans" class="fas fa-broom"></i>
            {{ isCleaningOrphans ? 'Cleaning...' : 'Clean Up' }}
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
import apiClient from '@/utils/ApiClient'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SessionOrphanManager')

// Types
interface OrphanedFact {
  fact_id: string
  session_id: string
  category: string
  content_preview: string
  important: boolean
}

interface OrphanScanResult {
  total_facts_checked: number
  facts_with_session_tracking: number
  orphaned_count: number
  orphaned_sessions: number
  session_breakdown: Record<string, number>
  orphaned_facts: OrphanedFact[]
}

interface StatusMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
  icon: string
}

// State
const orphanScanResult = ref<OrphanScanResult | null>(null)
const isScanning = ref(false)
const isCleaningOrphans = ref(false)
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

const scanSessionOrphans = async () => {
  if (isScanning.value || isCleaningOrphans.value) return

  try {
    isScanning.value = true
    orphanScanResult.value = null
    statusMessage.value = null

    // Issue #552: Fixed path to match backend /api/knowledge-maintenance/session-orphans
    const response = await apiClient.get('/api/knowledge-maintenance/session-orphans')

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(errorText || `Server error: ${response.status}`)
    }

    const data = await response.json()

    if (data.status === 'success') {
      orphanScanResult.value = data.data as OrphanScanResult

      if (data.data.orphaned_count > 0) {
        showStatus('warning',
          `Found ${data.data.orphaned_count} facts from ${data.data.orphaned_sessions} deleted sessions`)
      } else {
        showStatus('success',
          `Checked ${data.data.total_facts_checked} facts - all belong to active sessions`)
      }
    } else {
      throw new Error(data.message || 'Failed to scan for orphans')
    }
  } catch (error: any) {
    logger.error('Failed to scan for session orphans:', error)
    showStatus('error', error.message || 'An error occurred while scanning for orphaned facts')
  } finally {
    isScanning.value = false
  }
}

const cleanupSessionOrphans = async () => {
  if (isCleaningOrphans.value || isScanning.value) return
  if (!orphanScanResult.value || orphanScanResult.value.orphaned_count === 0) return

  // Confirm before cleanup
  const confirmed = window.confirm(
    `Are you sure you want to delete ${orphanScanResult.value.orphaned_count} orphaned facts?\n\n` +
    `This will remove facts from ${orphanScanResult.value.orphaned_sessions} deleted conversation(s).\n` +
    `Facts marked as "important" will be preserved.`
  )

  if (!confirmed) return

  try {
    isCleaningOrphans.value = true

    // Issue #552: Fixed path to match backend /api/knowledge-maintenance/session-orphans
    const response = await apiClient.delete('/api/knowledge-maintenance/session-orphans?dry_run=false&preserve_important=true')

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(errorText || `Server error: ${response.status}`)
    }

    const data = await response.json()

    if (data.status === 'success') {
      const preserved = data.data.facts_preserved > 0
        ? ` Preserved ${data.data.facts_preserved} important facts.`
        : ''
      showStatus('success', `Removed ${data.data.facts_removed} orphaned facts.${preserved}`)

      // Clear the scan result after cleanup
      orphanScanResult.value = null
    } else {
      throw new Error(data.message || 'Failed to cleanup orphans')
    }
  } catch (error: any) {
    logger.error('Failed to cleanup session orphans:', error)
    showStatus('error', error.message || 'An error occurred while cleaning up orphaned facts')
  } finally {
    isCleaningOrphans.value = false
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.session-orphan-manager {
  background: var(--bg-card);
  border-radius: 0.5rem;
  margin: 1rem;
  box-shadow: var(--shadow-sm);
}

.section-header {
  padding: 1.25rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.section-header h4 {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.25rem 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.header-description {
  color: var(--text-tertiary);
  margin: 0;
  font-size: 0.875rem;
}

.orphan-content {
  padding: 1.25rem;
}

.orphan-summary {
  margin-bottom: 1.5rem;
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-item {
  text-align: center;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 0.5rem;
  border: 1px solid var(--border-default);
}

.stat-item.highlight {
  background: var(--color-warning-bg);
  border-color: var(--color-warning);
}

.stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-item.highlight .stat-value {
  color: var(--color-warning-dark);
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 0.25rem;
}

.orphan-preview {
  background: var(--color-warning-bg-light);
  border: 1px solid var(--color-warning-light);
  border-radius: 0.5rem;
  padding: 1rem;
}

.orphan-preview h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-warning-darker);
  margin: 0 0 0.75rem 0;
}

.orphan-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 300px;
  overflow-y: auto;
}

.orphan-item {
  background: var(--bg-card);
  border: 1px solid var(--color-warning-light);
  border-radius: 0.375rem;
  padding: 0.75rem;
}

.orphan-meta {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.orphan-category {
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  background: var(--color-primary-bg);
  color: var(--color-primary-dark);
  border-radius: 9999px;
}

.orphan-important {
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
  border-radius: 9999px;
}

.orphan-content-text {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0 0 0.25rem 0;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orphan-session {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.orphan-more {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  font-style: italic;
  margin: 0.75rem 0 0 0;
  text-align: center;
}

.orphan-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

.action-card {
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 200px;
  transition: all 0.2s;
}

.action-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-md);
}

.action-card.warning {
  border-color: var(--color-warning-light);
  background: var(--color-warning-bg-light);
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
  font-size: 1.25rem;
  margin-bottom: 1rem;
}

.action-icon.scan {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.action-icon.cleanup {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.action-card h5 {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
}

.action-card p {
  color: var(--text-tertiary);
  margin: 0 0 1rem 0;
  line-height: 1.5;
}

.action-meta {
  color: var(--text-muted);
  font-size: 0.75rem;
  display: block;
  margin-bottom: 1rem;
}

.action-btn {
  width: 100%;
}

/* Status Messages */
.status-message {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 0.5rem;
  margin-top: 1.5rem;
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
  background: var(--color-warning-bg-light);
  border: 1px solid var(--color-warning);
  color: var(--color-warning-darker);
}

.status-message.info {
  background: var(--color-info-bg);
  border: 1px solid var(--color-primary);
  color: var(--color-info-dark);
}

.status-message span {
  flex: 1;
}

.dismiss-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem;
  color: inherit;
  opacity: 0.7;
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
