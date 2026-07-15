<template>
  <div class="tools-grid">
    <!-- Transient notice (e.g. cancelled danger-zone confirmation) -->
    <div v-if="noticeMessage" class="tools-notice" role="status" aria-live="polite">
      {{ noticeMessage }}
    </div>

    <!-- Deduplication Manager -->
    <div class="tools-section">
      <DeduplicationManager />
    </div>

    <!-- Session Orphan Manager -->
    <div class="tools-section">
      <SessionOrphanManager />
    </div>

    <!-- Cleanup Statistics -->
    <div class="tools-section">
      <CleanupStatistics @cleanup-complete="emit('refresh-strip')" />
    </div>

    <!-- Backup Manager -->
    <div class="tools-section">
      <BackupManager />
    </div>

    <!-- System Knowledge Manager -->
    <div class="tools-section">
      <SystemKnowledgeManager />
    </div>

    <!-- Failed Vectorizations Manager -->
    <div class="tools-section">
      <FailedVectorizationsManager />
    </div>

    <!-- Man Page Manager -->
    <div class="tools-section">
      <ManPageManager />
    </div>

    <!-- Database Actions -->
    <div class="tools-section db-actions-section">
      <h3 class="section-heading">{{ $t('knowledge.advanced.databaseManagement') }}</h3>
      <div class="db-actions">
        <button class="action-btn" :disabled="isOptimizing" @click="optimizeKnowledge">
          <Icon name="compress" />
          {{ $t('knowledge.stats.optimizeDb') }}
        </button>
      </div>
    </div>

    <!-- Issue #11555: Danger zone — clear-all moved from KnowledgeAdvanced -->
    <div class="tools-section danger-zone-section">
      <h3 class="section-heading danger-heading">
        <Icon name="exclamation-triangle" />
        {{ $t('knowledge.health.dangerZone') }}
      </h3>
      <div class="danger-card">
        <div class="danger-content">
          <div class="danger-icon">
            <Icon name="trash-alt" />
          </div>
          <div class="danger-text">
            <h4>{{ $t('knowledge.advanced.clearAllKnowledge') }}</h4>
            <p>
              {{ $t('knowledge.advanced.clearAllDescription') }}
              <strong>{{ $t('knowledge.advanced.clearAllWarning') }}</strong>
            </p>
            <small class="danger-meta">{{ $t('knowledge.advanced.clearAllMeta') }}</small>
          </div>
        </div>
        <button
          class="action-btn danger-btn"
          :disabled="isClearing"
          @click="clearAllKnowledge"
        >
          <Icon name="spinner" class="animate-spin" v-if="isClearing" />
          <Icon name="exclamation-triangle" v-else />
          {{ isClearing ? $t('knowledge.advanced.clearing') : $t('knowledge.advanced.clearAll') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useTransientError } from '@/composables/useTransientError'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers/index'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import DeduplicationManager from '@/components/knowledge/DeduplicationManager.vue'
import SessionOrphanManager from '@/components/knowledge/SessionOrphanManager.vue'
import CleanupStatistics from '@/components/knowledge/CleanupStatistics.vue'
import BackupManager from '@/components/knowledge/BackupManager.vue'
import SystemKnowledgeManager from '@/components/knowledge/SystemKnowledgeManager.vue'
import FailedVectorizationsManager from '@/components/knowledge/FailedVectorizationsManager.vue'
import ManPageManager from '@/components/manpage/ManPageManager.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeHealthTools')

// Re-emit CleanupStatistics' cleanup-complete so the shell can refresh the
// health dashboard strip (restores the old KnowledgeMaintenance seam, #11558)
const emit = defineEmits<{
  (e: 'refresh-strip'): void
}>()

const { t } = useI18n()
const { confirm } = useConfirmDialog()
const { message: noticeMessage, show: showNotice } = useTransientError()
const store = useKnowledgeStore()

interface KnowledgeController {
  cleanupKnowledgeBase: () => Promise<void>
  reindexKnowledgeBase: () => Promise<void>
  refreshStats: () => Promise<void>
}

let controller: KnowledgeController | null = null
try {
  controller = useKnowledgeController() as unknown as KnowledgeController
  logger.info('Knowledge controller initialized:', controller)
} catch (error) {
  logger.error('Failed to initialize knowledge controller:', error)
  controller = {
    cleanupKnowledgeBase: async () => { logger.warn('Controller not available') },
    reindexKnowledgeBase: async () => { logger.warn('Controller not available') },
    refreshStats: async () => { logger.warn('Controller not available') }
  }
}

const isOptimizing = ref(false)
// Issue #11555: clear-all danger zone state
const isClearing = ref(false)

// Shape of the clear_all endpoint response
interface ClearAllResponse {
  status?: string
  message?: string
  items_removed?: number
}

const refreshStats = async () => {
  try {
    await store.refreshStats()
  } catch (error) {
    logger.error('Failed to refresh stats:', error)
  }
}

const optimizeKnowledge = async () => {
  if (!(await confirm({ title: t('common.confirm'), message: t('knowledge.stats.confirmOptimize') }))) {
    return
  }

  isOptimizing.value = true
  try {
    if (controller && typeof controller.cleanupKnowledgeBase === 'function') {
      await controller.cleanupKnowledgeBase()
    } else {
      logger.warn('Controller cleanupKnowledgeBase method not available')
    }

    if (controller && typeof controller.reindexKnowledgeBase === 'function') {
      await controller.reindexKnowledgeBase()
    } else {
      logger.warn('Controller reindexKnowledgeBase method not available')
    }

    await refreshStats()
  } catch (error) {
    logger.error('Failed to optimize knowledge base:', error)
  } finally {
    isOptimizing.value = false
  }
}

// Issue #11555: clear-all danger zone — same flow as KnowledgeAdvanced
const clearAllKnowledge = async () => {
  if (isClearing.value) return

  const firstConfirm = await confirm({ title: t('common.confirm'), message: t('knowledge.advanced.confirmClearAll') })
  if (!firstConfirm) return

  const secondConfirm = await confirm({ title: t('common.confirm'), message: t('knowledge.advanced.confirmClearFinal') })
  if (!secondConfirm) return

  const userInput = prompt(t('knowledge.advanced.promptDeleteAll'))
  if (userInput !== 'DELETE ALL') {
    showNotice(t('knowledge.advanced.clearCancelled'))
    return
  }

  isClearing.value = true
  try {
    const response = await ApiClient.post<ClearAllResponse>(`${getApiBase()}/knowledge_base/clear_all`, {})
    if (response.status === 'success') {
      await store.refreshStats()
      logger.info(`Cleared knowledge base: ${response.items_removed ?? 0} entries removed`)
    } else {
      throw new Error(response.message || 'Failed to clear knowledge base')
    }
  } catch (error) {
    logger.error('Failed to clear knowledge base:', error)
  } finally {
    isClearing.value = false
  }
}
</script>

<style scoped>
.tools-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-6);
  padding: var(--spacing-6);
}

.tools-section {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.db-actions-section {
  padding: var(--spacing-6);
}

.section-heading {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4) var(--spacing-0);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.db-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-out);
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-hover);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tools-notice {
  grid-column: 1 / -1;
  padding: var(--spacing-3) var(--spacing-4);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--text-sm);
}

/* Issue #11555: danger zone section */
.danger-zone-section {
  grid-column: 1 / -1;
  padding: var(--spacing-6);
  border: 1px solid var(--color-error-light);
  background: var(--color-error-bg);
}

.danger-heading {
  color: var(--color-error-dark);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.danger-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.danger-content {
  display: flex;
  gap: var(--spacing-4);
  align-items: flex-start;
  flex: 1;
  min-width: 0;
}

.danger-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  background: var(--color-error-bg-hover);
  color: var(--color-error);
  flex-shrink: 0;
}

.danger-text h4 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-1) 0;
}

.danger-text p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-1) 0;
  line-height: 1.5;
}

.danger-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.danger-btn {
  color: var(--color-error);
  border-color: var(--color-error-light);
  white-space: nowrap;
  flex-shrink: 0;
}

.danger-btn:hover:not(:disabled) {
  background: var(--color-error-bg-hover);
  border-color: var(--color-error);
}

@media (max-width: 1024px) {
  .tools-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .tools-grid {
    padding: var(--spacing-4);
    gap: var(--spacing-4);
  }
}
</style>
