<template>
  <div class="session-orphan-manager">
    <div class="section-header">
      <div class="header-content">
        <h4><Icon name="broom" /> {{ $t('knowledge.sessionOrphan.title') }}</h4>
        <p class="header-description">
          {{ $t('knowledge.sessionOrphan.description') }}
        </p>
      </div>
    </div>

    <div class="orphan-content">
      <!-- Scan Results Summary -->
      <div v-if="orphanScanResult" class="orphan-summary">
        <div class="summary-stats">
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.total_facts_checked }}</span>
            <span class="stat-label">{{ $t('knowledge.sessionOrphan.factsChecked') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.facts_with_session_tracking }}</span>
            <span class="stat-label">{{ $t('knowledge.sessionOrphan.withSessionTracking') }}</span>
          </div>
          <div class="stat-item highlight">
            <span class="stat-value">{{ orphanScanResult.orphaned_count }}</span>
            <span class="stat-label">{{ $t('knowledge.sessionOrphan.orphanedFacts') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.orphaned_sessions }}</span>
            <span class="stat-label">{{ $t('knowledge.sessionOrphan.deletedSessions') }}</span>
          </div>
        </div>

        <!-- Orphan Preview -->
        <div v-if="orphanScanResult.orphaned_facts?.length > 0" class="orphan-preview">
          <h5>{{ $t('knowledge.sessionOrphan.previewTitle') }}</h5>
          <div class="orphan-list">
            <div
              v-for="fact in orphanScanResult.orphaned_facts.slice(0, 10)"
              :key="fact.fact_id"
              class="orphan-item"
            >
              <div class="orphan-meta">
                <span class="orphan-category">{{ fact.category }}</span>
                <span v-if="fact.important" class="orphan-important">
                  <Icon name="star" /> {{ $t('knowledge.sessionOrphan.important') }}
                </span>
              </div>
              <p class="orphan-content-text">{{ fact.content_preview }}</p>
              <small class="orphan-session">Session: {{ fact.session_id?.slice(0, 12) }}...</small>
            </div>
          </div>
          <p v-if="orphanScanResult.orphaned_facts.length > 10" class="orphan-more">
            {{ $t('knowledge.sessionOrphan.moreOrphans', { count: orphanScanResult.orphaned_facts.length - 10 }) }}
          </p>
        </div>
      </div>

      <!-- Actions -->
      <div class="orphan-actions">
        <div class="action-card">
          <div class="action-content">
            <div class="action-icon scan">
              <Icon name="search" />
            </div>
            <h5>{{ $t('knowledge.sessionOrphan.scanTitle') }}</h5>
            <p>{{ $t('knowledge.sessionOrphan.scanDescription') }}</p>
            <small class="action-meta">{{ $t('knowledge.sessionOrphan.scanMeta') }}</small>
          </div>
          <BaseButton
            variant="secondary"
            @click="scanSessionOrphans"
            :disabled="isScanning || isCleaningOrphans"
            :loading="isScanning"
            class="action-btn"
          >
            <Icon name="search" v-if="!isScanning" />
            {{ isScanning ? $t('knowledge.sessionOrphan.scanning') : $t('knowledge.sessionOrphan.scanNow') }}
          </BaseButton>
        </div>

        <div class="action-card warning">
          <div class="action-content">
            <div class="action-icon cleanup">
              <Icon name="broom" />
            </div>
            <h5>{{ $t('knowledge.sessionOrphan.cleanupTitle') }}</h5>
            <p>{{ $t('knowledge.sessionOrphan.cleanupDescription') }}</p>
            <small class="action-meta">
              {{ $t('knowledge.sessionOrphan.factsToClean', { count: orphanScanResult?.orphaned_count || 0 }) }}
            </small>
          </div>
          <BaseButton
            variant="warning"
            @click="cleanupSessionOrphans"
            :disabled="!orphanScanResult || orphanScanResult.orphaned_count === 0 || isCleaningOrphans || isScanning"
            :loading="isCleaningOrphans"
            class="action-btn"
          >
            <Icon name="broom" v-if="!isCleaningOrphans" />
            {{ isCleaningOrphans ? $t('knowledge.sessionOrphan.cleaning') : $t('knowledge.sessionOrphan.cleanUp') }}
          </BaseButton>
        </div>
      </div>

      <!-- Status Messages -->
      <div v-if="statusMessage" :class="['status-message', statusMessage.type]">
        <Icon :name="statusMessage.icon" />
        <span>{{ statusMessage.text }}</span>
        <button @click="statusMessage = null" class="dismiss-btn">
          <Icon name="times" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useKnowledgeOrphans } from '@/composables/knowledge/useKnowledgeOrphans'

const { t } = useI18n()

const logger = createLogger('SessionOrphanManager')

// Types
interface StatusMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
  icon: string
}

// Composable
const { orphanScanResult, isScanning, isCleaningOrphans, scanSessionOrphans: doScan, cleanupSessionOrphans: doCleanup } = useKnowledgeOrphans()

// State
const statusMessage = ref<StatusMessage | null>(null)

// Methods
const showStatus = (type: StatusMessage['type'], text: string) => {
  const icons = {
    success: 'check-circle',
    error: 'exclamation-circle',
    warning: 'exclamation-triangle',
    info: 'info-circle'
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
  statusMessage.value = null

  try {
    const data = await doScan()

    if (data.orphaned_count > 0) {
      showStatus('warning',
        t('knowledge.sessionOrphan.foundOrphans', { count: data.orphaned_count, sessions: data.orphaned_sessions }))
    } else {
      showStatus('success',
        t('knowledge.sessionOrphan.allActive', { count: data.total_facts_checked }))
    }
  } catch (error: any) {
    logger.error('Failed to scan for session orphans:', error)
    showStatus('error', error.message || t('knowledge.sessionOrphan.scanError'))
  }
}

const cleanupSessionOrphans = async () => {
  if (isCleaningOrphans.value || isScanning.value) return
  if (!orphanScanResult.value || orphanScanResult.value.orphaned_count === 0) return

  // Confirm before cleanup
  const confirmed = window.confirm(
    t('knowledge.sessionOrphan.confirmCleanup', { count: orphanScanResult.value.orphaned_count, sessions: orphanScanResult.value.orphaned_sessions })
  )

  if (!confirmed) return

  try {
    const data = await doCleanup()

    const preserved = data.facts_preserved > 0
      ? t('knowledge.sessionOrphan.preservedSuffix', { count: data.facts_preserved })
      : ''
    showStatus('success', t('knowledge.sessionOrphan.deleteSuccess', { count: data.facts_removed, preserved }))
  } catch (error: any) {
    logger.error('Failed to cleanup session orphans:', error)
    showStatus('error', error.message || t('knowledge.sessionOrphan.cleanupError'))
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.session-orphan-manager {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  margin: var(--spacing-4);
  box-shadow: var(--shadow-sm);
}

.section-header {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.section-header h4 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1) var(--spacing-0);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.header-description {
  color: var(--text-tertiary);
  margin: var(--spacing-0);
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
  font-weight: 700;
  color: var(--text-primary);
}

.stat-item.highlight .stat-value {
  color: var(--color-warning-dark);
}

.stat-label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-1);
}

.orphan-preview {
  background: var(--color-warning-bg-light);
  border: 1px solid var(--color-warning-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.orphan-preview h5 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-warning-darker);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3) var(--spacing-0);
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

.orphan-category {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-primary-bg);
  color: var(--color-primary-dark);
  border-radius: var(--radius-full);
}

.orphan-important {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
  border-radius: var(--radius-full);
}

.orphan-content-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1) var(--spacing-0);
  line-height: 1.4;
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
  color: var(--text-tertiary);
  font-style: italic;
  margin: var(--spacing-3) var(--spacing-0) var(--spacing-0) var(--spacing-0);
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
  transition: all var(--duration-200);
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
  font-size: var(--text-xl);
  margin-bottom: var(--spacing-4);
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
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
}

.action-card p {
  color: var(--text-tertiary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4) var(--spacing-0);
  line-height: 1.5;
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
  padding: var(--spacing-1);
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
