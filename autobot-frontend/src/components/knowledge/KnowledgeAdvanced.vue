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
          <h4><i class="fas fa-database"></i> {{ $t('knowledge.advanced.knowledgeBasePopulation') }}</h4>
          <p>{{ $t('knowledge.advanced.populationDescription') }}</p>
        </div>

        <div class="action-grid">
          <!-- 1. AutoBot Documentation (FIRST - Product docs, highest priority) -->
          <div class="action-card">
            <div class="action-content">
              <div class="action-icon autobot-docs">
                <i class="fas fa-cogs"></i>
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
              <i v-if="populateStatus.autobotDocs !== 'loading'" class="fas fa-plus"></i>
              {{ getButtonText('autobotDocs') }}
            </BaseButton>
          </div>

          <!-- 2. System Commands (SECOND - Common CLI commands) -->
          <div class="action-card">
            <div class="action-content">
              <div class="action-icon system-commands">
                <i class="fas fa-terminal"></i>
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
              <i v-if="populateStatus.systemCommands !== 'loading'" class="fas fa-plus"></i>
              {{ getButtonText('systemCommands') }}
            </BaseButton>
          </div>

          <!-- 3. Manual Pages (THIRD - Detailed reference docs) -->
          <div class="action-card">
            <div class="action-content">
              <div class="action-icon man-pages">
                <i class="fas fa-book"></i>
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
              <i v-if="populateStatus.manPages !== 'loading'" class="fas fa-plus"></i>
              {{ getButtonText('manPages') }}
            </BaseButton>
          </div>
        </div>
      </div>

      <!-- Management Section -->
      <div class="section-card">
        <div class="section-header">
          <h4><i class="fas fa-tools"></i> {{ $t('knowledge.advanced.databaseManagement') }}</h4>
          <p>{{ $t('knowledge.advanced.databaseManagementDescription') }}</p>
        </div>

        <div class="management-actions">
          <div class="action-card danger-zone">
            <div class="action-content">
              <div class="action-icon danger">
                <i class="fas fa-trash-alt"></i>
              </div>
              <h5>{{ $t('knowledge.advanced.clearAllKnowledge') }}</h5>
              <p>{{ $t('knowledge.advanced.clearAllDescription') }} <strong>{{ $t('knowledge.advanced.clearAllWarning') }}</strong></p>
              <small class="action-meta">{{ $t('knowledge.advanced.clearAllMeta') }}</small>
            </div>
            <BaseButton
              variant="danger"
              @click="clearAllKnowledge"
              :disabled="isClearing || isPopulating"
              :loading="isClearing"
              class="action-btn"
            >
              <i v-if="!isClearing" class="fas fa-exclamation-triangle"></i>
              {{ isClearing ? $t('knowledge.advanced.clearing') : $t('knowledge.advanced.clearAll') }}
            </BaseButton>
          </div>
        </div>
      </div>

      <!-- Progress Section -->
      <div v-if="showProgress" class="section-card">
        <div class="section-header">
          <h4><i class="fas fa-chart-line"></i> {{ $t('knowledge.advanced.operationProgress') }}</h4>
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
        <i :class="getMessageIcon(message.type)"></i>
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
          <i class="fas fa-times"></i>
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import ApiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeAdvanced')
const { t } = useI18n()

const store = useKnowledgeStore()

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

// Progress tracking
let progressInterval: number | null = null
const startTime = ref(0)

// Computed
const progressText = computed(() => {
  if (!showProgress.value) return ''
  return `${progressPercentage.value}% (${itemsProcessed.value}/${totalItems.value})`
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

const getMessageIcon = (type: string) => {
  const icons = {
    success: 'fas fa-check-circle',
    error: 'fas fa-exclamation-circle',
    warning: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle'
  }
  return icons[type as keyof typeof icons] || 'fas fa-info-circle'
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

  // Simulate progress updates (in real implementation, this would be driven by actual progress)
  progressInterval = setInterval(() => {
    if (itemsProcessed.value < totalItems.value) {
      itemsProcessed.value++
      progressPercentage.value = Math.round((itemsProcessed.value / totalItems.value) * 100)

      // Calculate ETA
      const elapsed = Date.now() - startTime.value
      const rate = itemsProcessed.value / elapsed
      const remaining = (totalItems.value - itemsProcessed.value) / rate

      if (remaining > 60000) {
        estimatedTimeRemaining.value = `${Math.ceil(remaining / 60000)}m`
      } else if (remaining > 1000) {
        estimatedTimeRemaining.value = `${Math.ceil(remaining / 1000)}s`
      } else {
        estimatedTimeRemaining.value = '<1s'
      }
    }
  }, 100)
}

const stopProgress = () => {
  showProgress.value = false
  currentOperation.value = ''
  progressPercentage.value = 0
  itemsProcessed.value = 0
  totalItems.value = 0
  estimatedTimeRemaining.value = ''

  if (progressInterval) {
    clearInterval(progressInterval)
    progressInterval = null
  }
}

const populateSystemCommands = async () => {
  if (isPopulating.value) return

  try {
    isPopulating.value = true
    populateStatus.value.systemCommands = 'loading'

    startProgress(t('knowledge.advanced.progressPopulatingSystemCommands'), 150)
    progressDetails.value = t('knowledge.advanced.progressAddingCommands')

    const apiResponse = await ApiClient.post('/api/knowledge_base/populate_system_commands', {})
    const response = await parseApiResponse(apiResponse)

    if (response.status === 'success') {
      populateStatus.value.systemCommands = 'success'
      addStatusMessage('success', t('knowledge.advanced.systemCommandsAdded'),
        `Successfully added ${response.items_added} system commands to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate system commands')
    }
  } catch (error: any) {
    logger.error('Failed to populate system commands:', error)
    populateStatus.value.systemCommands = 'error'
    addStatusMessage('error', t('knowledge.advanced.systemCommandsFailed'),
      error.message || 'An error occurred while populating system commands')
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

    const apiResponse = await ApiClient.post('/api/knowledge_base/populate_man_pages', {})
    const response = await parseApiResponse(apiResponse)

    if (response.status === 'success') {
      populateStatus.value.manPages = 'success'
      addStatusMessage('success', t('knowledge.advanced.manualPagesAdded'),
        `Successfully added ${response.items_added} manual pages to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate manual pages')
    }
  } catch (error: any) {
    logger.error('Failed to populate manual pages:', error)
    populateStatus.value.manPages = 'error'
    addStatusMessage('error', t('knowledge.advanced.manualPagesFailed'),
      error.message || 'An error occurred while populating manual pages')
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

    const apiResponse = await ApiClient.post('/api/knowledge_base/populate_autobot_docs', {})
    const response = await parseApiResponse(apiResponse)

    if (response.status === 'success') {
      populateStatus.value.autobotDocs = 'success'
      addStatusMessage('success', t('knowledge.advanced.autobotDocsAdded'),
        `Successfully added ${response.items_added} AutoBot documents to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate AutoBot documentation')
    }
  } catch (error: any) {
    logger.error('Failed to populate AutoBot docs:', error)
    populateStatus.value.autobotDocs = 'error'
    addStatusMessage('error', t('knowledge.advanced.autobotDocsFailed'),
      error.message || 'An error occurred while populating AutoBot documentation')
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

    const apiResponse = await ApiClient.post('/api/knowledge_base/clear_all', {})
    const response = await parseApiResponse(apiResponse)

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
  } catch (error: any) {
    logger.error('Failed to clear knowledge base:', error)
    addStatusMessage('error', t('knowledge.advanced.clearFailed'),
      error.message || 'An error occurred while clearing the knowledge base')
  } finally{
    isClearing.value = false
    stopProgress()
  }
}

// Cleanup on unmount
onUnmounted(() => {
  if (progressInterval) {
    clearInterval(progressInterval)
  }
})

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
  padding: 1.5rem;
  max-width: 1200px;
  margin: 0 auto;
}

.advanced-header {
  text-align: center;
  margin-bottom: 2rem;
}

.advanced-header h3 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.header-description {
  color: var(--text-secondary);
  font-size: 1rem;
}

.advanced-sections {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.section-card {
  background: var(--bg-card);
  border-radius: 0.75rem;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.section-header {
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.section-header h4 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.section-header p {
  color: var(--text-secondary);
  margin: 0;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  padding: 1.5rem;
}

.management-actions {
  padding: 1.5rem;
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
  font-size: 1.25rem;
  margin-bottom: 1rem;
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
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.action-card p {
  color: var(--text-secondary);
  margin-bottom: 1rem;
  line-height: 1.5;
}

.action-meta {
  color: var(--text-tertiary);
  font-size: 0.75rem;
  display: block;
  margin-bottom: 1rem;
}

/* Action button layout */
.action-btn {
  width: 100%;
}

/* Progress Styles */
.progress-container {
  padding: 1.5rem;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.progress-text {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.progress-operation {
  font-weight: 600;
  color: var(--text-primary);
}

.progress-details {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.progress-percentage {
  font-weight: 600;
  color: var(--color-primary);
  font-size: 1.25rem;
}

.progress-bar {
  width: 100%;
  height: 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 9999px;
  overflow: hidden;
  margin-bottom: 1rem;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

/* Status Messages */
.status-messages {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 400px;
}

.status-message {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1rem;
  box-shadow: var(--shadow-md);
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
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
  margin-top: 0.125rem;
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
  margin-bottom: 0.25rem;
}

.message-details {
  color: var(--text-secondary);
  font-size: 0.875rem;
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
    padding: 1rem;
  }

  .action-grid {
    grid-template-columns: 1fr;
    gap: 1rem;
    padding: 1rem;
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
    gap: 0.5rem;
  }

  .progress-stats {
    flex-direction: column;
    gap: 0.25rem;
  }
}
</style>
