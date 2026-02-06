<template>
  <div class="man-page-manager">

    <!-- Machine Profile Section -->
    <BasePanel variant="bordered" size="medium">
      <template #header>
        <h3><i class="fas fa-desktop"></i> Current Machine Profile</h3>
        <BaseButton
          size="sm"
          variant="outline"
          @click="refreshMachineProfile"
          :disabled="loading?.profile"
        >
          <i class="fas fa-sync" :class="{ 'fa-spin': loading?.profile }"></i>
          Refresh
        </BaseButton>
      </template>

      <div v-if="machineProfile && !loading?.profile" class="machine-info">
        <div class="info-grid">
          <div class="info-item">
            <label>Machine ID:</label>
            <span class="mono">{{ machineProfile.machine_id || 'Not detected' }}</span>
          </div>
          <div class="info-item">
            <label>OS Type:</label>
            <span class="badge" :class="getOSBadgeClass(machineProfile.os_type)">
              {{ machineProfile.os_type || 'Unknown' }}
            </span>
          </div>
          <div class="info-item">
            <label>Distribution:</label>
            <span>{{ machineProfile.distro || 'N/A' }}</span>
          </div>
          <div class="info-item">
            <label>Package Manager:</label>
            <span class="mono">{{ machineProfile.package_manager || 'Unknown' }}</span>
          </div>
          <div class="info-item">
            <label>Available Tools:</label>
            <span class="highlight">{{ (machineProfile.available_tools || []).length }}</span>
          </div>
          <div class="info-item">
            <label>Architecture:</label>
            <span>{{ machineProfile.architecture || 'Unknown' }}</span>
          </div>
        </div>
      </div>

      <div v-else-if="!loading?.profile" class="no-data">
        <i class="fas fa-exclamation-triangle"></i>
        Machine profile not loaded. Click refresh to detect current machine.
      </div>

      <div v-if="loading?.profile" class="loading">
        <i class="fas fa-spinner fa-spin"></i>
        Detecting machine profile...
      </div>
    </BasePanel>

    <!-- Integration Status Section -->
    <BasePanel variant="bordered" size="medium">
      <template #header>
        <h3><i class="fas fa-chart-bar"></i> Integration Status</h3>
        <BaseButton
          size="sm"
          variant="outline"
          @click="refreshIntegrationStatus"
          :disabled="loading?.status"
        >
          <i class="fas fa-sync" :class="{ 'fa-spin': loading?.status }"></i>
          Refresh
        </BaseButton>
      </template>

      <div v-if="integrationStatus" class="status-info">
        <div v-if="integrationStatus.status === 'not_integrated'" class="not-integrated">
          <i class="fas fa-info-circle"></i>
          <div>
            <strong>Man pages not yet integrated</strong>
            <p>Click "Integrate Man Pages" below to extract documentation from your system.</p>
          </div>
        </div>

        <div v-else-if="integrationStatus.status === 'error'" class="error">
          <i class="fas fa-exclamation-circle"></i>
          <div>
            <strong>Integration Error</strong>
            <p>{{ integrationStatus.message }}</p>
          </div>
        </div>

        <div v-else class="integration-stats">
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.successful || 0 }}</div>
              <div class="stat-label">Successful</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.processed || 0 }}</div>
              <div class="stat-label">Processed</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.current_man_page_files || 0 }}</div>
              <div class="stat-label">Knowledge Files</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.total_available_tools || 0 }}</div>
              <div class="stat-label">Available Tools</div>
            </div>
          </div>

          <div v-if="integrationStatus.integration_date" class="integration-date">
            <i class="fas fa-clock"></i>
            Last integrated: {{ formatDate(integrationStatus.integration_date) }}
          </div>

          <div v-if="integrationStatus.available_commands" class="available-commands">
            <h4>Integrated Commands ({{ integrationStatus.available_commands.length }}):</h4>
            <div class="command-tags">
              <span
                v-for="command in integrationStatus.available_commands"
                :key="command"
                class="command-tag"
              >
                {{ command }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="loading?.status" class="loading">
        <i class="fas fa-spinner fa-spin"></i>
        Loading integration status...
      </div>
    </BasePanel>

    <!-- Integration Actions -->
    <div class="integration-actions">
      <div class="section-header">
        <h3><i class="fas fa-cogs"></i> Integration Actions</h3>
      </div>

      <div class="action-buttons">
        <BaseButton
          variant="primary"
          @click="initializeMachineKnowledgeWithProgress"
          :disabled="loading?.initialize || !canInitialize"
          :loading="loading?.initialize"
        >
          <i class="fas fa-rocket"></i>
          Initialize Machine Knowledge
        </BaseButton>

        <BaseButton
          variant="success"
          @click="integrateManPagesWithProgress"
          :disabled="loading?.integrate || !canIntegrate"
          :loading="loading?.integrate"
        >
          <i class="fas fa-book-open"></i>
          Integrate Man Pages
        </BaseButton>

        <BaseButton
          variant="info"
          @click="testSearchManPages"
          :disabled="loading?.search || !hasIntegration"
          :loading="loading?.search"
        >
          <i class="fas fa-search"></i>
          Test Search
        </BaseButton>
      </div>

      <!-- Real-time Progress Tracking -->
      <BasePanel v-if="showProgressTracking" variant="bordered" size="medium">
        <template #header>
          <h3><i class="fas fa-tasks"></i> Progress Tracking</h3>
          <BaseButton
            size="sm"
            variant="outline"
            @click="showProgressTracking = false"
          >
            <i class="fas fa-times"></i>
            Hide
          </BaseButton>
        </template>

        <div class="progress-container">
          <!-- Overall Progress -->
          <div class="progress-item">
            <div class="progress-label">
              <span>{{ progressState.currentTask || 'Waiting...' }}</span>
              <span class="progress-percentage">{{ Math.round(progressState.overallProgress) }}%</span>
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: progressState.overallProgress + '%' }"
                :class="progressState.status"
              ></div>
            </div>
          </div>

          <!-- Task-specific Progress -->
          <div v-if="progressState.taskProgress > 0" class="progress-item">
            <div class="progress-label">
              <span>{{ progressState.taskDetail || 'Processing...' }}</span>
              <span class="progress-percentage">{{ Math.round(progressState.taskProgress) }}%</span>
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill task-progress"
                :style="{ width: progressState.taskProgress + '%' }"
              ></div>
            </div>
          </div>

          <!-- Progress Messages -->
          <div class="progress-messages">
            <div
              v-for="(message, index) in progressState.messages.slice(-5)"
              :key="index"
              class="progress-message"
              :class="message.type"
            >
              <i :class="getMessageIcon(message.type)"></i>
              <span class="timestamp">{{ formatTime(message.timestamp) }}</span>
              <span class="message">{{ message.text }}</span>
            </div>
          </div>

          <!-- Connection Status -->
          <div class="connection-status">
            <i :class="websocketConnected ? 'fas fa-plug connected-icon' : 'fas fa-plug disconnected-icon'"></i>
            <span :class="websocketConnected ? 'connected-text' : 'disconnected-text'">
              {{ websocketConnected ? 'Connected' : 'Disconnected' }}
            </span>
          </div>
        </div>
      </BasePanel>

      <div class="action-info">
        <div class="info-item">
          <strong>Initialize Machine Knowledge:</strong>
          Detects your machine and creates machine-specific knowledge including man page integration.
        </div>
        <div class="info-item">
          <strong>Integrate Man Pages:</strong>
          Extracts manual pages for available Linux commands (Linux only).
        </div>
        <div class="info-item">
          <strong>Test Search:</strong>
          Tests searching through integrated man page knowledge.
        </div>
      </div>
    </div>

    <!-- Search Section -->
    <BasePanel v-if="showSearch" variant="bordered" size="medium">
      <template #header>
        <h3><i class="fas fa-search"></i> Search Man Page Knowledge</h3>
      </template>

      <div class="search-input">
        <input
          v-model="searchQuery"
          @keyup.enter="searchManPages"
          type="text"
          placeholder="Search for commands, patterns, network tools, etc..."
          class="form-input"
        >
        <BaseButton
          variant="primary"
          @click="searchManPages"
          :disabled="!searchQuery.trim() || loading?.search"
        >
          <i class="fas fa-search"></i>
          Search
        </BaseButton>
      </div>

      <div v-if="searchResults" class="search-results">
        <h4>Search Results for "{{ lastSearchQuery }}":</h4>

        <EmptyState
          v-if="searchResults.length === 0"
          icon="fas fa-info-circle"
          message='No results found. Try different keywords like "network", "file", "process".'
        />

        <div v-else class="result-list">
          <div v-for="result in searchResults" :key="result.command" class="result-item">
            <div class="result-header">
              <strong>{{ result.command }}</strong>
              <span class="relevance-score">Score: {{ result.relevance_score }}</span>
            </div>
            <div class="result-purpose">{{ result.purpose }}</div>
            <div class="result-meta">
              <span class="source">{{ result.source }}</span> •
              <span class="machine">{{ result.machine_id }}</span>
            </div>
          </div>
        </div>
      </div>
    </BasePanel>

    <!-- Progress Messages -->
    <div v-if="progressMessage" class="progress-message" :class="progressMessageType">
      <i class="fas" :class="getProgressIcon()"></i>
      {{ progressMessage }}
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for ManPageManager
const logger = createLogger('ManPageManager')
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BasePanel from '@/components/base/BasePanel.vue'

export default {
  name: 'ManPageManager',
  components: {
    EmptyState,
    BaseButton,
    BasePanel
  },
  setup() {
    // Use the shared composable
    const {
      fetchMachineProfile: fetchMachineProfileAPI,
      fetchManPagesSummary: fetchManPagesSummaryAPI,
      initializeMachineKnowledge: initializeMachineKnowledgeAPI,
      integrateManPages: integrateManPagesAPI,
      searchManPages: searchManPagesAPI,
      formatDate,
      getOSBadgeClass,
      getMessageIcon,
      formatTime
    } = useKnowledgeBase()

    // Reactive data
    const machineProfile = ref(null)
    const integrationStatus = ref(null)
    const searchResults = ref(null)
    const searchQuery = ref('')
    const lastSearchQuery = ref('')
    const showSearch = ref(false)
    const progressMessage = ref('')
    const progressMessageType = ref('info')
    const showProgressTracking = ref(false)
    const websocketConnected = ref(false)

    // Progress tracking state
    const progressState = ref({
      currentTask: '',
      taskDetail: '',
      overallProgress: 0,
      taskProgress: 0,
      status: 'waiting', // waiting, running, success, error
      messages: []
    })

    // Use composables for async operations
    const { execute: fetchProfileOp, loading: loadingProfile } = useAsyncOperation()
    const { execute: fetchStatusOp, loading: loadingStatus } = useAsyncOperation()
    const { execute: initializeOp, loading: loadingInitialize } = useAsyncOperation()
    const { execute: integrateOp, loading: loadingIntegrate } = useAsyncOperation()
    const { execute: searchOp, loading: loadingSearch } = useAsyncOperation()

    // Computed loading states for backward compatibility
    const loading = computed(() => ({
      profile: loadingProfile.value,
      status: loadingStatus.value,
      initialize: loadingInitialize.value,
      integrate: loadingIntegrate.value,
      search: loadingSearch.value
    }))

    // Computed properties
    const canInitialize = computed(() => {
      return machineProfile.value && machineProfile.value.machine_id
    })

    const canIntegrate = computed(() => {
      return machineProfile.value &&
             machineProfile.value.os_type === 'linux'
    })

    const hasIntegration = computed(() => {
      return integrationStatus.value &&
             integrationStatus.value.status !== 'not_integrated' &&
             integrationStatus.value.status !== 'error'
    })

    // Methods
    const setProgressMessage = (message, type = 'info', duration = 5000) => {
      progressMessage.value = message
      progressMessageType.value = type

      if (duration > 0) {
        setTimeout(() => {
          progressMessage.value = ''
        }, duration)
      }
    }

    const getProgressIcon = () => {
      switch (progressMessageType.value) {
        case 'success': return 'fa-check-circle'
        case 'error': return 'fa-exclamation-circle'
        case 'warning': return 'fa-exclamation-triangle'
        default: return 'fa-info-circle'
      }
    }

    // Removed: getOSBadgeClass - now using composable
    // Removed: formatDate - now using composable

    const refreshMachineProfile = async () => {
      if (loading.value.profile) return // Prevent concurrent calls

      loading.value.profile = true
      try {
        const profile = await fetchMachineProfileAPI()

        if (profile) {
          machineProfile.value = profile
          setProgressMessage('Machine profile refreshed successfully', 'success')
        } else {
          // Handle API errors gracefully
          machineProfile.value = null
          setProgressMessage('Machine profile not available (backend restart required)', 'warning')
        }
      } catch (error) {
        logger.error('Error refreshing machine profile:', error)
        setProgressMessage('Could not connect to backend API', 'error')
        machineProfile.value = null
      } finally {
        if (loading.value) {
          loading.value.profile = false
        }
      }
    }

    const refreshIntegrationStatus = async () => {
      if (loading.value.status) return // Prevent concurrent calls

      loading.value.status = true
      try {
        const summary = await fetchManPagesSummaryAPI()

        if (summary) {
          integrationStatus.value = summary
          setProgressMessage('Integration status refreshed', 'success')
        } else {
          // Handle API errors gracefully
          integrationStatus.value = { status: 'not_integrated', message: 'Backend restart required' }
          setProgressMessage('Integration status not available (backend restart required)', 'warning')
        }
      } catch (error) {
        logger.error('Error refreshing integration status:', error)
        setProgressMessage('Could not connect to backend API', 'error')
        integrationStatus.value = { status: 'error', message: 'Connection failed' }
      } finally {
        if (loading.value) {
          loading.value.status = false
        }
      }
    }

    const initializeMachineKnowledge = async () => {
      if (loading.value.initialize) return // Prevent concurrent calls
      loading.value.initialize = true
      setProgressMessage('Initializing machine-aware knowledge...', 'info', 0)

      try {
        const response = await initializeMachineKnowledgeAPI(false)

        if (response.status === 'success') {
          setProgressMessage('Machine knowledge initialized successfully!', 'success')

          // Refresh both profile and status
          await Promise.all([
            refreshMachineProfile(),
            refreshIntegrationStatus()
          ])
        } else {
          throw new Error(response.message || 'Initialization failed')
        }
      } catch (error) {
        logger.error('Error initializing machine knowledge:', error)
        setProgressMessage(`Initialization failed: ${error.message}`, 'error')
      } finally {
        if (loading.value) loading.value.initialize = false
      }
    }

    const integrateManPages = async () => {
      if (!canIntegrate.value) {
        setProgressMessage('Man page integration requires a Linux system', 'warning')
        return
      }

      if (loading.value.integrate) return // Prevent concurrent calls
      loading.value.integrate = true
      setProgressMessage('Integrating man pages... This may take a minute.', 'info', 0)

      try {
        const response = await integrateManPagesAPI()

        if (response.status === 'success') {
          setProgressMessage('Man pages integrated successfully!', 'success')
          await refreshIntegrationStatus()
        } else if (response.status === 'skipped') {
          setProgressMessage(`Integration skipped: ${response.message}`, 'warning')
        } else {
          throw new Error(response.message || 'Integration failed')
        }
      } catch (error) {
        logger.error('Error integrating man pages:', error)
        setProgressMessage(`Integration failed: ${error.message}`, 'error')
      } finally {
        if (loading.value) loading.value.integrate = false
      }
    }

    const searchManPages = async () => {
      if (!searchQuery.value.trim()) {
        setProgressMessage('Please enter a search query', 'warning')
        return
      }

      if (loading.value.search) return // Prevent concurrent calls
      loading.value.search = true
      lastSearchQuery.value = searchQuery.value.trim()

      try {
        const response = await searchManPagesAPI(lastSearchQuery.value)

        if (response.status === 'success') {
          searchResults.value = response.results
          showSearch.value = true
          setProgressMessage(`Found ${response.results_count} results`, 'success')
        } else {
          throw new Error('Search failed')
        }
      } catch (error) {
        logger.error('Error searching man pages:', error)
        setProgressMessage(`Search failed: ${error.message}`, 'error')
        searchResults.value = []
      } finally {
        if (loading.value) loading.value.search = false
      }
    }

    const testSearchManPages = async () => {
      searchQuery.value = 'network interface'
      await searchManPages()
    }

    // Initialize on mount
    // Progress tracking methods
    const addProgressMessage = (text, type = 'info') => {
      const message = {
        text,
        type,
        timestamp: Date.now()
      }
      progressState.value.messages.push(message)

      // Keep only last 10 messages
      if (progressState.value.messages.length > 10) {
        progressState.value.messages = progressState.value.messages.slice(-10)
      }
    }

    const updateProgress = (currentTask, overallProgress, taskDetail = '', taskProgress = 0, status = 'running') => {
      progressState.value.currentTask = currentTask
      progressState.value.taskDetail = taskDetail
      progressState.value.overallProgress = overallProgress
      progressState.value.taskProgress = taskProgress
      progressState.value.status = status
    }

    const resetProgress = () => {
      progressState.value = {
        currentTask: '',
        taskDetail: '',
        overallProgress: 0,
        taskProgress: 0,
        status: 'waiting',
        messages: []
      }
    }

    // Removed: getMessageIcon - now using composable
    // Removed: formatTime - now using composable

    // Enhanced action methods with progress tracking
    const initializeMachineKnowledgeWithProgress = async () => {
      showProgressTracking.value = true
      resetProgress()

      try {
        loading.value.initialize = true
        setProgressMessage('Initializing machine knowledge...', 'info', 0)

        updateProgress('Initializing Machine Knowledge', 10, 'Starting initialization...')
        addProgressMessage('Starting machine knowledge initialization', 'info')

        const response = await initializeMachineKnowledgeAPI(false)

        if (response.status !== 'success') {
          throw new Error(response.message || 'Initialization failed')
        }

        updateProgress('Machine Knowledge Initialized', 100, 'Initialization complete', 100, 'success')
        addProgressMessage('Machine knowledge initialization completed', 'success')
        setProgressMessage('Machine knowledge initialized successfully!', 'success')

        await refreshMachineProfile()
        await refreshIntegrationStatus()

      } catch (error) {
        logger.error('Failed to initialize machine knowledge:', error)
        updateProgress('Initialization Failed', 0, error.message, 0, 'error')
        addProgressMessage(`Initialization failed: ${error.message}`, 'error')
        setProgressMessage(`Failed to initialize machine knowledge: ${error.message}`, 'error')
      } finally {
        if (loading.value) loading.value.initialize = false
      }
    }

    const integrateManPagesWithProgress = async () => {
      showProgressTracking.value = true
      resetProgress()

      try {
        loading.value.integrate = true
        setProgressMessage('Integrating man pages...', 'info', 0)

        updateProgress('Integrating Man Pages', 10, 'Starting man page extraction...')
        addProgressMessage('Starting man page integration', 'info')

        const response = await integrateManPagesAPI()

        if (response.status !== 'success') {
          throw new Error(response.message || 'Integration failed')
        }

        updateProgress('Man Pages Integrated', 100, 'Integration complete', 100, 'success')
        addProgressMessage('Man page integration completed', 'success')
        setProgressMessage('Man pages integrated successfully!', 'success')

        await refreshIntegrationStatus()

      } catch (error) {
        logger.error('Failed to integrate man pages:', error)
        updateProgress('Integration Failed', 0, error.message, 0, 'error')
        addProgressMessage(`Integration failed: ${error.message}`, 'error')
        setProgressMessage(`Failed to integrate man pages: ${error.message}`, 'error')
      } finally {
        if (loading.value) loading.value.integrate = false
      }
    }

    onMounted(async () => {
      await Promise.all([
        refreshMachineProfile(),
        refreshIntegrationStatus()
      ])
    })

    onBeforeUnmount(() => {
      // Cleanup if needed
    })

    return {
      // Data
      machineProfile,
      integrationStatus,
      searchResults,
      searchQuery,
      lastSearchQuery,
      showSearch,
      progressMessage,
      progressMessageType,
      showProgressTracking,
      websocketConnected,
      progressState,
      loading,

      // Computed
      canInitialize,
      canIntegrate,
      hasIntegration,

      // Methods
      getOSBadgeClass,
      formatDate,
      getProgressIcon,
      refreshMachineProfile,
      refreshIntegrationStatus,
      initializeMachineKnowledge,
      integrateManPages,
      searchManPages,
      testSearchManPages,

      // Progress tracking methods
      addProgressMessage,
      updateProgress,
      resetProgress,
      getMessageIcon,
      formatTime,
      initializeMachineKnowledgeWithProgress,
      integrateManPagesWithProgress
    }
  }
}
</script>

<style scoped>
/**
 * ManPageManager.vue - Styles migrated to design tokens
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 */

.man-page-manager {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-5);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

.header {
  text-align: center;
  margin-bottom: var(--spacing-10);
}

.title {
  font-size: var(--text-3xl);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.title i {
  margin-right: var(--spacing-2);
  color: var(--color-info);
}

.subtitle {
  color: var(--text-secondary);
  font-size: var(--text-lg);
}

/* BasePanel handles section containers - only .integration-actions remains as non-migrated */
.integration-actions {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-8);
  box-shadow: var(--shadow-md);
}

.machine-info {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-4);
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.info-item:last-child {
  border-bottom: none;
}

.info-item label {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.mono {
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
}

.badge {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  text-transform: uppercase;
}

.badge-success { background: var(--color-success); color: var(--text-on-success); }
.badge-info { background: var(--color-info); color: var(--text-on-primary); }
.badge-warning { background: var(--color-warning); color: var(--text-on-warning); }
.badge-secondary { background: var(--color-secondary); color: var(--text-on-primary); }

.highlight {
  font-weight: var(--font-bold);
  color: var(--color-success);
  font-size: var(--text-lg);
}

/* Integration Status */
.not-integrated,
.error {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
}

.not-integrated {
  border-left: 4px solid var(--color-info);
}

.not-integrated i {
  color: var(--color-info);
  font-size: var(--text-2xl);
}

.error {
  border-left: 4px solid var(--color-error);
}

.error i {
  color: var(--color-error);
  font-size: var(--text-2xl);
}

.integration-stats {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-5);
}

.stat-item {
  text-align: center;
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.stat-number {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-label {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-1);
}

.integration-date {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-5);
}

.integration-date i {
  margin-right: var(--spacing-2);
}

.available-commands h4 {
  margin-bottom: var(--spacing-4);
  color: var(--text-primary);
}

.command-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.command-tag {
  background: var(--color-info);
  color: var(--text-on-primary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

/* Action Buttons */
.action-buttons {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
  flex-wrap: wrap;
}

.action-info {
  color: var(--text-secondary);
}

.action-info .info-item {
  margin-bottom: var(--spacing-2);
  padding: var(--spacing-2) 0;
  border-bottom: 1px solid var(--border-subtle);
  display: block;
}

.action-info .info-item:last-child {
  border-bottom: none;
}

/* Search Section */
.search-input {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.form-input {
  flex: 1;
  padding: var(--spacing-3) var(--spacing-4);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.search-results h4 {
  margin-bottom: var(--spacing-5);
  color: var(--text-primary);
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.result-item {
  background: var(--bg-card);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  border-left: 4px solid var(--color-info);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.result-header strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.relevance-score {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
}

.result-purpose {
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.result-meta {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.source {
  font-style: italic;
}

.machine {
  font-family: var(--font-mono);
}

/* Progress Messages (toast notifications) */
.progress-message {
  position: fixed;
  top: var(--spacing-5);
  right: var(--spacing-5);
  padding: var(--spacing-4) var(--spacing-5);
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-weight: var(--font-semibold);
  z-index: var(--z-toast);
  max-width: 400px;
  box-shadow: var(--shadow-lg);
}

.progress-message.info {
  background: var(--color-info);
}

.progress-message.success {
  background: var(--color-success);
}

.progress-message.warning {
  background: var(--color-warning);
  color: var(--text-on-warning);
}

.progress-message.error {
  background: var(--color-error);
}

.progress-message i {
  margin-right: var(--spacing-2);
}

/* Loading and No Data States */
.loading,
.no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  padding: var(--spacing-10);
  color: var(--text-secondary);
  font-style: italic;
}

.loading i,
.no-data i {
  font-size: var(--text-xl);
}

/* Responsive Design */
@media (max-width: 768px) {
  .man-page-manager {
    padding: var(--spacing-4);
  }

  .action-buttons {
    flex-direction: column;
  }

  .btn {
    min-width: 100%;
  }

  .search-input {
    flex-direction: column;
  }

  .info-grid {
    grid-template-columns: 1fr;
  }
}

/* BasePanel handles progress-section container - only content styles remain */
.progress-container {
  margin-top: var(--spacing-4);
}

.progress-item {
  margin-bottom: var(--spacing-4);
}

.progress-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.progress-percentage {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-default);
}

.progress-fill.waiting {
  background: var(--color-secondary);
}

.progress-fill.running {
  background: linear-gradient(90deg, var(--color-info), var(--color-info-hover));
}

.progress-fill.success {
  background: linear-gradient(90deg, var(--color-success), var(--color-success-hover));
}

.progress-fill.error {
  background: linear-gradient(90deg, var(--color-error), var(--color-error-hover));
}

.progress-fill.task-progress {
  background: linear-gradient(90deg, var(--chart-purple), var(--chart-purple-light));
}

.progress-messages {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  max-height: 200px;
  overflow-y: auto;
  margin: var(--spacing-4) 0;
  padding: var(--spacing-2);
}

/* Progress message items within the list (different from toast notifications) */
.progress-messages .progress-message {
  position: static;
  display: flex;
  align-items: center;
  padding: var(--spacing-2) 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-sm);
  background: transparent;
  color: var(--text-primary);
  font-weight: var(--font-normal);
  box-shadow: none;
  max-width: none;
  border-radius: 0;
}

.progress-messages .progress-message:last-child {
  border-bottom: none;
}

.progress-messages .progress-message .timestamp {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  margin-right: var(--spacing-2);
  min-width: 70px;
}

.progress-messages .progress-message .message {
  flex: 1;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
}

/* Connection status icons and text */
.connected-icon { color: var(--color-success); }
.disconnected-icon { color: var(--color-error); }
.connected-text { color: var(--color-success-hover); }
.disconnected-text { color: var(--color-error-hover); }

/* Custom scrollbar styling for better UX */
.man-page-manager::-webkit-scrollbar {
  width: var(--scrollbar-width);
}

.man-page-manager::-webkit-scrollbar-track {
  background: var(--scrollbar-track);
}

.man-page-manager::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: var(--scrollbar-radius);
}

.man-page-manager::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover);
}
</style>
