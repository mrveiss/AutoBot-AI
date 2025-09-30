<template>
  <div class="knowledge-advanced">
    <div class="advanced-header">
      <h3>Advanced Knowledge Management</h3>
      <p class="header-description">
        Administrative tools for populating and managing the knowledge base
      </p>
    </div>

    <div class="advanced-sections">
      <!-- Repopulate Section -->
      <div class="section-card">
        <div class="section-header">
          <h4><i class="fas fa-database"></i> Knowledge Base Population</h4>
          <p>Quickly populate the knowledge base with common documentation</p>
        </div>

        <div class="action-grid">
          <div class="action-card">
            <div class="action-content">
              <div class="action-icon system-commands">
                <i class="fas fa-terminal"></i>
              </div>
              <h5>System Commands</h5>
              <p>Add common Linux commands and usage examples (curl, grep, ssh, docker, etc.)</p>
              <small class="action-meta">~150 commands, ~5 minutes</small>
            </div>
            <button
              @click="populateSystemCommands"
              :disabled="isPopulating"
              class="action-btn primary"
            >
              <i v-if="populateStatus.systemCommands === 'loading'" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-plus"></i>
              {{ getButtonText('systemCommands') }}
            </button>
          </div>

          <div class="action-card">
            <div class="action-content">
              <div class="action-icon man-pages">
                <i class="fas fa-book"></i>
              </div>
              <h5>Manual Pages</h5>
              <p>Add selected system manual pages for common tools and utilities</p>
              <small class="action-meta">~50 man pages, ~8 minutes</small>
            </div>
            <button
              @click="populateManPages"
              :disabled="isPopulating"
              class="action-btn primary"
            >
              <i v-if="populateStatus.manPages === 'loading'" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-plus"></i>
              {{ getButtonText('manPages') }}
            </button>
          </div>

          <div class="action-card">
            <div class="action-content">
              <div class="action-icon autobot-docs">
                <i class="fas fa-cogs"></i>
              </div>
              <h5>AutoBot Documentation</h5>
              <p>Add AutoBot-specific documentation, configs, and setup guides</p>
              <small class="action-meta">~30 documents, ~3 minutes</small>
            </div>
            <button
              @click="populateAutoBotDocs"
              :disabled="isPopulating"
              class="action-btn primary"
            >
              <i v-if="populateStatus.autobotDocs === 'loading'" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-plus"></i>
              {{ getButtonText('autobotDocs') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Management Section -->
      <div class="section-card">
        <div class="section-header">
          <h4><i class="fas fa-tools"></i> Database Management</h4>
          <p>Administrative tools for knowledge base maintenance</p>
        </div>

        <div class="management-actions">
          <div class="action-card danger-zone">
            <div class="action-content">
              <div class="action-icon danger">
                <i class="fas fa-trash-alt"></i>
              </div>
              <h5>Clear All Knowledge</h5>
              <p>Remove all entries from the knowledge base. <strong>This action cannot be undone.</strong></p>
              <small class="action-meta">Requires confirmation</small>
            </div>
            <button
              @click="clearAllKnowledge"
              :disabled="isClearing || isPopulating"
              class="action-btn danger"
            >
              <i v-if="isClearing" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-exclamation-triangle"></i>
              {{ isClearing ? 'Clearing...' : 'Clear All' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Progress Section -->
      <div v-if="showProgress" class="section-card">
        <div class="section-header">
          <h4><i class="fas fa-chart-line"></i> Operation Progress</h4>
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
            <span>Items processed: {{ itemsProcessed }} / {{ totalItems }}</span>
            <span v-if="estimatedTimeRemaining">ETA: {{ estimatedTimeRemaining }}</span>
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
        <button @click="dismissMessage(index)" class="dismiss-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import ApiClient from '@/utils/ApiClient'

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
    case 'loading': return 'Populating...'
    case 'success': return 'Populated'
    case 'error': return 'Retry'
    default: return 'Populate'
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

    startProgress('Populating System Commands', 150)
    progressDetails.value = 'Adding common Linux commands and examples...'

    const response = await ApiClient.post('/api/knowledge_base/populate_system_commands', {})

    if (response.status === 'success') {
      populateStatus.value.systemCommands = 'success'
      addStatusMessage('success', 'System Commands Added',
        `Successfully added ${response.items_added} system commands to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate system commands')
    }
  } catch (error: any) {
    console.error('Failed to populate system commands:', error)
    populateStatus.value.systemCommands = 'error'
    addStatusMessage('error', 'System Commands Failed',
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

    startProgress('Populating Manual Pages', 50)
    progressDetails.value = 'Adding system manual pages...'

    const response = await ApiClient.post('/api/knowledge_base/populate_man_pages', {})

    if (response.status === 'success') {
      populateStatus.value.manPages = 'success'
      addStatusMessage('success', 'Manual Pages Added',
        `Successfully added ${response.items_added} manual pages to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate manual pages')
    }
  } catch (error: any) {
    console.error('Failed to populate manual pages:', error)
    populateStatus.value.manPages = 'error'
    addStatusMessage('error', 'Manual Pages Failed',
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

    startProgress('Populating AutoBot Documentation', 30)
    progressDetails.value = 'Adding AutoBot documentation and guides...'

    const response = await ApiClient.post('/api/knowledge_base/populate_autobot_docs', {})

    if (response.status === 'success') {
      populateStatus.value.autobotDocs = 'success'
      addStatusMessage('success', 'AutoBot Documentation Added',
        `Successfully added ${response.items_added} AutoBot documents to the knowledge base`)

      // Refresh knowledge store
      await store.refreshStats()
    } else {
      throw new Error(response.message || 'Failed to populate AutoBot documentation')
    }
  } catch (error: any) {
    console.error('Failed to populate AutoBot docs:', error)
    populateStatus.value.autobotDocs = 'error'
    addStatusMessage('error', 'AutoBot Documentation Failed',
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
  const firstConfirm = confirm(
    'Are you sure you want to clear ALL knowledge base entries?\n\n' +
    'This will permanently delete all documents, commands, and manual pages.\n' +
    'This action CANNOT be undone.'
  )

  if (!firstConfirm) return

  const secondConfirm = confirm(
    'FINAL CONFIRMATION:\n\n' +
    'Type "DELETE ALL" in the next dialog to proceed with clearing the entire knowledge base.'
  )

  if (!secondConfirm) return

  const userInput = prompt('Type "DELETE ALL" to confirm (case sensitive):')

  if (userInput !== 'DELETE ALL') {
    addStatusMessage('warning', 'Clear Operation Cancelled', 'Incorrect confirmation text entered')
    return
  }

  try {
    isClearing.value = true

    startProgress('Clearing Knowledge Base', 1)
    progressDetails.value = 'Removing all entries from the knowledge base...'

    const response = await ApiClient.post('/api/knowledge_base/clear_all', {})

    if (response.status === 'success') {
      addStatusMessage('success', 'Knowledge Base Cleared',
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
    console.error('Failed to clear knowledge base:', error)
    addStatusMessage('error', 'Clear Operation Failed',
      error.message || 'An error occurred while clearing the knowledge base')
  } finally {
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
  if (store.stats.total_facts > 0) {
    // Could check for specific content types here
  }
})
</script>

<style scoped>
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
  color: #1f2937;
  margin-bottom: 0.5rem;
}

.header-description {
  color: #6b7280;
  font-size: 1rem;
}

.advanced-sections {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.section-card {
  background: white;
  border-radius: 0.75rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.section-header {
  padding: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}

.section-header h4 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.section-header p {
  color: #6b7280;
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
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 200px;
  transition: all 0.2s;
}

.action-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.action-card.danger-zone {
  border-color: #fca5a5;
  background: #fef2f2;
}

.action-card.danger-zone:hover {
  border-color: #dc2626;
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
  background: #dbeafe;
  color: #3b82f6;
}

.action-icon.man-pages {
  background: #d1fae5;
  color: #10b981;
}

.action-icon.autobot-docs {
  background: #fde68a;
  color: #f59e0b;
}

.action-icon.danger {
  background: #fecaca;
  color: #dc2626;
}

.action-card h5 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.5rem;
}

.action-card p {
  color: #6b7280;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.action-meta {
  color: #9ca3af;
  font-size: 0.75rem;
  display: block;
  margin-bottom: 1rem;
}

.action-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 0.5rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
  font-size: 0.875rem;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.primary {
  background: #3b82f6;
  color: white;
}

.action-btn.primary:hover:not(:disabled) {
  background: #2563eb;
}

.action-btn.danger {
  background: #dc2626;
  color: white;
}

.action-btn.danger:hover:not(:disabled) {
  background: #b91c1c;
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
  color: #1f2937;
}

.progress-details {
  color: #6b7280;
  font-size: 0.875rem;
}

.progress-percentage {
  font-weight: 600;
  color: #3b82f6;
  font-size: 1.25rem;
}

.progress-bar {
  width: 100%;
  height: 0.5rem;
  background: #e5e7eb;
  border-radius: 9999px;
  overflow: hidden;
  margin-bottom: 1rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #1d4ed8);
  transition: width 0.3s ease;
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  font-size: 0.875rem;
  color: #6b7280;
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
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  position: relative;
}

.status-message.success {
  border-color: #10b981;
  background: #f0fdf4;
}

.status-message.error {
  border-color: #ef4444;
  background: #fef2f2;
}

.status-message.warning {
  border-color: #f59e0b;
  background: #fffbeb;
}

.status-message.info {
  border-color: #3b82f6;
  background: #eff6ff;
}

.status-message i {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.status-message.success i {
  color: #10b981;
}

.status-message.error i {
  color: #ef4444;
}

.status-message.warning i {
  color: #f59e0b;
}

.status-message.info i {
  color: #3b82f6;
}

.message-content {
  flex: 1;
}

.message-title {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.25rem;
}

.message-details {
  color: #6b7280;
  font-size: 0.875rem;
}

.dismiss-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  background: none;
  color: #9ca3af;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.25rem;
}

.dismiss-btn:hover {
  background: rgba(0, 0, 0, 0.1);
  color: #6b7280;
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