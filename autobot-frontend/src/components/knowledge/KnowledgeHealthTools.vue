<template>
  <div class="tools-grid">
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
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers/index'
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
