<template>
  <div class="knowledge-advanced">
    <div class="advanced-header">
      <h3>{{ $t('knowledge.advanced.title') }}</h3>
      <p class="header-description">
        {{ $t('knowledge.advanced.description') }}
      </p>
    </div>

    <div class="advanced-sections">
      <!-- Repopulate Section -->
      <div class="section-card">
        <div class="section-header">
          <h4><Icon name="database" /> {{ $t('knowledge.advanced.knowledgeBasePopulation') }}</h4>
          <p>{{ $t('knowledge.advanced.populationDescription') }}</p>
        </div>

        <div class="action-grid">
          <!-- 1. AutoBot Documentation (FIRST - Product docs, highest priority) -->
          <div class="action-card">
            <div class="action-content">
              <div class="action-icon autobot-docs">
                <Icon name="cogs" />
              </div>
              <h5>{{ $t('knowledge.advanced.autobotDocumentation') }}</h5>
              <p>{{ $t('knowledge.advanced.autobotDocsDescription') }}</p>
              <small class="action-meta">{{ $t('knowledge.advanced.autobotDocsMeta') }}</small>
            </div>
            <BaseButton
              variant="primary"
              @click="populateAutoBotDocs"
              :disabled="isPopulating"
              :loading="populateStatus.autobotDocs === 'loading'"
              class="action-btn"
            >
              <Icon name="plus" v-if="populateStatus.autobotDocs !== 'loading'" />
              {{ getButtonText('autobotDocs') }}
            </BaseButton>
          </div>

          <!-- 2. System Commands (SECOND - Common CLI commands) -->
          <div class="action-card">
            <div class="action-content">
              <div class="action-icon system-commands">
                <Icon name="terminal" />
              </div>
              <h5>{{ $t('knowledge.advanced.systemCommands') }}</h5>
              <p>{{ $t('knowledge.advanced.systemCommandsDescription') }}</p>
              <small class="action-meta">{{ $t('knowledge.advanced.systemCommandsMeta') }}</small>
            </div>
            <BaseButton
              variant="primary"
              @click="populateSystemCommands"
              :disabled="isPopulating"
              :loading="populateStatus.systemCommands === 'loading'"
              class="action-btn"
            >
              <Icon name="plus" v-if="populateStatus.systemCommands !== 'loading'" />
              {{ getButtonText('systemCommands') }}
            </BaseButton>
          </div>

          <!-- 3. Manual Pages (THIRD - Detailed reference docs) -->
          <div class="action-card">
            <div class="action-content">
              <div class="action-icon man-pages">
                <Icon name="book" />
              </div>
              <h5>{{ $t('knowledge.advanced.manualPages') }}</h5>
              <p>{{ $t('knowledge.advanced.manualPagesDescription') }}</p>
              <small class="action-meta">{{ $t('knowledge.advanced.manualPagesMeta') }}</small>
            </div>
            <BaseButton
              variant="primary"
              @click="populateManPages"
              :disabled="isPopulating"
              :loading="populateStatus.manPages === 'loading'"
              class="action-btn"
            >
              <Icon name="plus" v-if="populateStatus.manPages !== 'loading'" />
              {{ getButtonText('manPages') }}
            </BaseButton>
          </div>
        </div>
      </div>

      <!-- Management Section -->
      <div class="section-card">
        <div class="section-header">
          <h4><Icon name="tools" /> {{ $t('knowledge.advanced.databaseManagement') }}</h4>
          <p>{{ $t('knowledge.advanced.databaseManagementDescription') }}</p>
        </div>

        <div class="management-actions">
          <div class="action-card danger-zone">
            <div class="action-content">
              <div class="action-icon danger">
                <Icon name="trash-alt" />
              </div>
              <h5>{{ $t('knowledge.advanced.clearAllKnowledge') }}</h5>
              <p>{{ $t('knowledge.advanced.clearAllDescription') }} <strong>{{ $t('knowledge.advanced.clearAllWarning') }}</strong></p>
              <small class="action-meta">{{ $t('knowledge.advanced.clearAllMeta') }}</small>
            </div>
            <BaseButton
              variant="error"
              @click="clearAllKnowledge"
              :disabled="isClearing || isPopulating"
              :loading="isClearing"
              class="action-btn"
            >
              <Icon name="exclamation-triangle" v-if="!isClearing" />
              {{ isClearing ? $t('knowledge.advanced.clearing') : $t('knowledge.advanced.clearAll') }}
            </BaseButton>
          </div>
        </div>
      </div>

      <!-- Progress Section -->
      <div v-if="showProgress" class="section-card">
        <div class="section-header">
          <h4><Icon name="chart-line" /> {{ $t('knowledge.advanced.operationProgress') }}</h4>
        </div>

        <div class="progress-container">
          <div class="progress-info">
            <div class="progress-text">
              <span class="progress-operation">{{ currentOperation }}</span>
              <span class="progress-details">{{ progressDetails }}</span>
            </div>
            <div class="progress-percentage">{{ progressPercentage }}%</div>
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: `${progressPercentage}%` }"
            ></div>
          </div>
          <div class="progress-stats">
            <span>{{ $t('knowledge.advanced.itemsProcessed', { processed: itemsProcessed, total: totalItems }) }}</span>
            <span v-if="estimatedTimeRemaining">{{ $t('knowledge.advanced.eta', { time: estimatedTimeRemaining }) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Status Messages -->
    <div v-if="statusMessages.length > 0" class="status-messages">
      <div
        v-for="(message, index) in statusMessages"
        :key="index"
        :class="['status-message', message.type]"
      >
        <Icon :name="getMessageIcon(message.type)" />
        <div class="message-content">
          <div class="message-title">{{ message.title }}</div>
          <div v-if="message.details" class="message-details">{{ message.details }}</div>
        </div>
        <BaseButton
          variant="ghost"
          size="xs"
          @click="dismissMessage(index)"
          class="dismiss-btn"
          :aria-label="$t('knowledge.advanced.dismissMessage')"
        >
          <Icon name="times" />
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useFakeProgress } from '@/composables/useFakeProgress'

const logger = createLogger('KnowledgeAdvanced')
const { t } = useI18n()

const store = useKnowledgeStore()

// Shape of the knowledge_base population/clear endpoint responses.
interface KnowledgeBaseOpResponse {
  status?: string
  message?: string
  items_added?: number
  items_removed?: number
}

// State
const isPopulating = ref(false)
const isClearing = ref(false)
const showProgress = ref(false)
const currentOperation = ref('')
const progressPercentage = ref(0)
const itemsProcessed = ref(0)
const totalItems = ref(0)
const progressDetails = ref('')
const estimatedTimeRemaining = ref('')

// Population status tracking
const populateStatus = ref({
  systemCommands: 'idle', // 'idle' | 'loading' | 'success' | 'error'
  manPages: 'idle',
  autobotDocs: 'idle'
})

// Status messages
const statusMessages = ref<Array<{
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  details?: string
  timestamp: number
}>>([])

// Progress tracking — fake-progress counter drives itemsProcessed
// (#5237: extracted from manual setInterval simulating backend progress)
const fakeProgress = useFakeProgress({ intervalMs: 100, step: 1 })
const startTime = ref(0)

// Mirror fake-progress counter into itemsProcessed and derive percentage + ETA
watch(fakeProgress.progress, (value) => {
  const total = totalItems.value
  itemsProcessed.value = value
  if (total <= 0) {
    progressPercentage.value = 0
    estimatedTimeRemaining.value = ''
    return
  }
  progressPercentage.value = Math.round((value / total) * 100)

  const elapsed = Date.now() - startTime.value
  if (value <= 0 || elapsed <= 0) {
    estimatedTimeRemaining.value = ''
    return
  }
  const rate = value / elapsed
  const remaining = (total - value) / rate
  if (remaining > 60000) {
    estimatedTimeRemaining.value = `${Math.ceil(remaining / 60000)}m`
  } else if (remaining > 1000) {
    estimatedTimeRemaining.value = `${Math.ceil(remaining / 1000)}s`
  } else {
    estimatedTimeRemaining.value = '<1s'
  }
})

// Methods
const getButtonText = (type: keyof typeof populateStatus.value) => {
  const status = populateStatus.value[type]
  switch (status) {
    case 'loading': return t('knowledge.advanced.populating')
    case 'success': return t('knowledge.advanced.populated')
    case 'error': return t('knowledge.advanced.retryBtn')
    default: return t('knowledge.advanced.populate')
  }
}

const getMessageIcon = (type: string): IconName => {
  const icons: Record<string, IconName> = {
    success: 'check-circle',
    error: 'exclamation-circle',
    warning: 'exclamation-triangle',
    info: 'info-circle'
  }
  return icons[type as keyof typeof icons] || 'info-circle'
}

const addStatusMessage = (type: 'success' | 'error' | 'warning' | 'info', title: string, details?: string) => {
  statusMessages.value.unshift({
    type,
    title,
    details,
    timestamp: Date.now()
  })

  // Auto-dismiss success messages after 5 seconds
  if (type === 'success') {
    setTimeout(() => {
      const index = statusMessages.value.findIndex(m => m.timestamp === Date.now() - 5000)
      if (index >= 0) {
        statusMessages.value.splice(index, 1)
      }
    }, 5000)
  }
}

const dismissMessage = (index: number) => {
  statusMessages.value.splice(index, 1)
}

const startProgress = (operation: string, total: number) => {
  showProgress.value = true
  currentOperation.value = operation
  totalItems.value = total
  itemsProcessed.value = 0
  progressPercentage.value = 0
  startTime.value = Date.now()
  fakeProgress.start({ target: total })
}

const stopProgress = () => {
  fakeProgress.reset()
  showProgress.value = false
  currentOperation.value = ''
  progressPercentage.value = 0
  itemsProcessed.value = 0
  totalItems.value = 0
  estimatedTimeRemaining.value = ''
}

const populateSystemCommands = async () => {
  if (isPopulating.value) return

  try {
    isPopulating.value = true
    populateStatus.value.systemCommands = 'loading'

    startProgress(t('knowledge.advanced.progressPopulatingSystemCommands'), 150)
    progressDetails.value = t('knowledge.advanced.progressAddingCommands')

    const response = await ApiClient.post<KnowledgeBaseOpResponse>(`${getApiBase()}/knowledge_base/populate_system_commands`, {})

    if (response.status === 'success') {
      populateStatus.value.systemCommands = 'success'
      addStatusMessage('success', t('knowledge.advanced.systemCommandsAdded'),
        `Successfully added ${response.items_added} system commands to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate system commands')
    }
  } catch (error) {
    logger.error('Failed to populate system commands:', error)
    populateStatus.value.systemCommands = 'error'
    addStatusMessage('error', t('knowledge.advanced.systemCommandsFailed'),
      (error as { message?: string }).message || 'An error occurred while populating system commands')
  } finally {
    isPopulating.value = false
    stopProgress()

    // Reset status after a delay
    setTimeout(() => {
      populateStatus.value.systemCommands = 'idle'
    }, 3000)
  }
}

const populateManPages = async () => {
  if (isPopulating.value) return

  try {
    isPopulating.value = true
    populateStatus.value.manPages = 'loading'

    startProgress(t('knowledge.advanced.progressPopulatingManPages'), 50)
    progressDetails.value = t('knowledge.advanced.progressAddingManPages')

    const response = await ApiClient.post<KnowledgeBaseOpResponse>(`${getApiBase()}/knowledge_base/populate_man_pages`, {})

    if (response.status === 'success') {
      populateStatus.value.manPages = 'success'
      addStatusMessage('success', t('knowledge.advanced.manualPagesAdded'),
        `Successfully added ${response.items_added} manual pages to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate manual pages')
    }
  } catch (error) {
    logger.error('Failed to populate manual pages:', error)
    populateStatus.value.manPages = 'error'
    addStatusMessage('error', t('knowledge.advanced.manualPagesFailed'),
      (error as { message?: string }).message || 'An error occurred while populating manual pages')
  } finally {
    isPopulating.value = false
    stopProgress()

    // Reset status after a delay
    setTimeout(() => {
      populateStatus.value.manPages = 'idle'
    }, 3000)
  }
}

const populateAutoBotDocs = async () => {
  if (isPopulating.value) return

  try {
    isPopulating.value = true
    populateStatus.value.autobotDocs = 'loading'

    startProgress(t('knowledge.advanced.progressPopulatingAutobotDocs'), 30)
    progressDetails.value = t('knowledge.advanced.progressAddingAutobotDocs')

    const response = await ApiClient.post<KnowledgeBaseOpResponse>(`${getApiBase()}/knowledge_base/populate_autobot_docs`, {})

    if (response.status === 'success') {
      populateStatus.value.autobotDocs = 'success'
      addStatusMessage('success', t('knowledge.advanced.autobotDocsAdded'),
        `Successfully added ${response.items_added} AutoBot documents to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate AutoBot documentation')
    }
  } catch (error) {
    logger.error('Failed to populate AutoBot docs:', error)
    populateStatus.value.autobotDocs = 'error'
    addStatusMessage('error', t('knowledge.advanced.autobotDocsFailed'),
      (error as { message?: string }).message || 'An error occurred while populating AutoBot documentation')
  } finally {
    isPopulating.value = false
    stopProgress()

    // Reset status after a delay
    setTimeout(() => {
      populateStatus.value.autobotDocs = 'idle'
    }, 3000)
  }
}

const clearAllKnowledge = async () => {
  if (isClearing.value || isPopulating.value) return

  // Double confirmation for destructive action
  const firstConfirm = confirm(t('knowledge.advanced.confirmClearAll'))

  if (!firstConfirm) return

  const secondConfirm = confirm(t('knowledge.advanced.confirmClearFinal'))

  if (!secondConfirm) return

  const userInput = prompt(t('knowledge.advanced.promptDeleteAll'))

  if (userInput !== 'DELETE ALL') {
    addStatusMessage('warning', t('knowledge.advanced.clearCancelled'), t('knowledge.advanced.clearCancelledDetails'))
    return
  }

  try {
    isClearing.value = true

    startProgress(t('knowledge.advanced.progressClearingKB'), 1)
    progressDetails.value = t('knowledge.advanced.progressRemovingEntries')

    const response = await ApiClient.post<KnowledgeBaseOpResponse>(`${getApiBase()}/knowledge_base/clear_all`, {})

    if (response.status === 'success') {
      addStatusMessage('success', t('knowledge.advanced.clearSuccess'),
        `Successfully removed ${response.items_removed} entries from the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()

      // Reset all populate statuses
      populateStatus.value = {
        systemCommands: 'idle',
        manPages: 'idle',
        autobotDocs: 'idle'
      }
    } else {
      throw new Error(response.message || 'Failed to clear knowledge base')
    }
  } catch (error) {
    logger.error('Failed to clear knowledge base:', error)
    addStatusMessage('error', t('knowledge.advanced.clearFailed'),
      (error as { message?: string }).message || 'An error occurred while clearing the knowledge base')
  } finally{
    isClearing.value = false
    stopProgress()
  }
}

// Initial load
onMounted(() => {
  // Check if knowledge base has content to update populate statuses
  if (store.stats?.total_facts && store.stats.total_facts > 0) {
    // Could check for specific content types here
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.knowledge-advanced {
  padding: var(--spacing-6);
  max-width: 1200px;
  margin: 0 auto;
}

.advanced-header {
  text-align: center;
  margin-bottom: var(--spacing-8);
}

.advanced-header h3 {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-base);
}

.advanced-sections {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

.section-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.section-header {
  padding: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.section-header h4 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.section-header p {
  color: var(--text-secondary);
  margin: var(--spacing-0);
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-6);
  padding: var(--spacing-6);
}

.management-actions {
  padding: var(--spacing-6);
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

.action-card.danger-zone {
  border-color: var(--color-error-light);
  background: var(--color-error-bg);
}

.action-card.danger-zone:hover {
  border-color: var(--color-error);
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

.action-icon.system-commands {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.action-icon.man-pages {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.action-icon.autobot-docs {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.action-icon.danger {
  background: var(--color-error-bg-hover);
  color: var(--color-error);
}

.action-card h5 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.action-card p {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-4);
  line-height: 1.5;
}

.action-meta {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  display: block;
  margin-bottom: var(--spacing-4);
}

/* Action button layout */
.action-btn {
  width: 100%;
}

/* Progress Styles */
.progress-container {
  padding: var(--spacing-6);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-4);
}

.progress-text {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.progress-operation {
  font-weight: 600;
  color: var(--text-primary);
}

.progress-details {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.progress-percentage {
  font-weight: 600;
  color: var(--color-primary);
  font-size: var(--text-xl);
}

.progress-bar {
  width: 100%;
  height: 0.5rem;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
  margin-bottom: var(--spacing-4);
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-300) var(--ease-out);
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Status Messages */
.status-messages {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: var(--z-modal);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  max-width: 400px;
}

.status-message {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  box-shadow: var(--shadow-md);
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  position: relative;
}

.status-message.success {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.status-message.error {
  border-color: var(--color-error);
  background: var(--color-error-bg);
}

.status-message.warning {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.status-message.info {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

.status-message i {
  flex-shrink: 0;
  margin-top: var(--spacing-0-5);
}

.status-message.success i {
  color: var(--color-success);
}

.status-message.error i {
  color: var(--color-error);
}

.status-message.warning i {
  color: var(--color-warning);
}

.status-message.info i {
  color: var(--color-info);
}

.message-content {
  flex: 1;
}

.message-title {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.message-details {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

/* Dismiss button positioning */
.dismiss-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
}

/* Responsive */
@media (max-width: 768px) {
  .knowledge-advanced {
    padding: var(--spacing-4);
  }

  .action-grid {
    grid-template-columns: 1fr;
    gap: var(--spacing-4);
    padding: var(--spacing-4);
  }

  .action-card {
    min-height: auto;
  }

  .status-messages {
    right: 0.5rem;
    left: 0.5rem;
    max-width: none;
  }

  .progress-info {
    flex-direction: column;
    gap: var(--spacing-2);
  }

  .progress-stats {
    flex-direction: column;
    gap: var(--spacing-1);
  }
}
</style>
