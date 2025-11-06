<template>
  <div class="man-page-manager">

    <!-- Machine Profile Section -->
    <div class="machine-profile-section">
      <div class="section-header">
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
      </div>

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
    </div>

    <!-- Integration Status Section -->
    <div class="integration-status-section">
      <div class="section-header">
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
      </div>

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
    </div>

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
      <div v-if="showProgressTracking" class="progress-section">
        <div class="section-header">
          <h3><i class="fas fa-tasks"></i> Progress Tracking</h3>
          <BaseButton
            size="sm"
            variant="outline"
            @click="showProgressTracking = false"
          >
            <i class="fas fa-times"></i>
            Hide
          </BaseButton>
        </div>

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
            <i :class="websocketConnected ? 'fas fa-plug text-green-500' : 'fas fa-plug text-red-500'"></i>
            <span :class="websocketConnected ? 'text-green-600' : 'text-red-600'">
              {{ websocketConnected ? 'Connected' : 'Disconnected' }}
            </span>
          </div>
        </div>
      </div>

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
    <div v-if="showSearch" class="search-section">
      <div class="section-header">
        <h3><i class="fas fa-search"></i> Search Man Page Knowledge</h3>
      </div>

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
    </div>

    <!-- Progress Messages -->
    <div v-if="progressMessage" class="progress-message" :class="progressMessageType">
      <i class="fas" :class="getProgressIcon()"></i>
      {{ progressMessage }}
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import ApiClient from '../utils/ApiClient'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'

export default {
  name: 'ManPageManager',
  components: {
    EmptyState,
    BaseButton
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

    // Loading states - initialized with all properties
    const loading = ref({
      profile: false,
      status: false,  
      initialize: false,
      integrate: false,
      search: false
    })

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
        console.error('Error refreshing machine profile:', error)
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
        console.error('Error refreshing integration status:', error)
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
        console.error('Error initializing machine knowledge:', error)
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
        console.error('Error integrating man pages:', error)
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
        console.error('Error searching man pages:', error)
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
        console.error('Failed to initialize machine knowledge:', error)
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
        console.error('Failed to integrate man pages:', error)
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
.man-page-manager {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

.header {
  text-align: center;
  margin-bottom: 40px;
}

.title {
  font-size: 2rem;
  color: #2c3e50;
  margin-bottom: 10px;
}

.title i {
  margin-right: 10px;
  color: #3498db;
}

.subtitle {
  color: #7f8c8d;
  font-size: 1.1rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 2px solid #ecf0f1;
}

.section-header h3 {
  margin: 0;
  color: #2c3e50;
}

.section-header i {
  margin-right: 8px;
  color: #3498db;
}

/* Machine Profile Section */
.machine-profile-section,
.integration-status-section,
.integration-actions,
.search-section {
  background: #f8f9fa;
  border-radius: 10px;
  padding: 25px;
  margin-bottom: 30px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.machine-info {
  background: white;
  border-radius: 8px;
  padding: 20px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 15px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #ecf0f1;
}

.info-item:last-child {
  border-bottom: none;
}

.info-item label {
  font-weight: 600;
  color: #2c3e50;
}

.mono {
  font-family: 'Courier New', monospace;
  background: #ecf0f1;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9rem;
}

.badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: bold;
  text-transform: uppercase;
}

.badge-success { background: #27ae60; color: white; }
.badge-info { background: #3498db; color: white; }
.badge-warning { background: #f39c12; color: white; }
.badge-secondary { background: #95a5a6; color: white; }

.highlight {
  font-weight: bold;
  color: #27ae60;
  font-size: 1.1rem;
}

/* Integration Status */
.not-integrated,
.error {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px;
  border-radius: 8px;
  background: white;
}

.not-integrated {
  border-left: 4px solid #3498db;
}

.not-integrated i {
  color: #3498db;
  font-size: 1.5rem;
}

.error {
  border-left: 4px solid #e74c3c;
}

.error i {
  color: #e74c3c;
  font-size: 1.5rem;
}

.integration-stats {
  background: white;
  border-radius: 8px;
  padding: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-item {
  text-align: center;
  padding: 15px;
  background: #ecf0f1;
  border-radius: 8px;
}

.stat-number {
  font-size: 2rem;
  font-weight: bold;
  color: #2c3e50;
}

.stat-label {
  color: #7f8c8d;
  font-size: 0.9rem;
  margin-top: 5px;
}

.integration-date {
  color: #7f8c8d;
  margin-bottom: 20px;
}

.integration-date i {
  margin-right: 8px;
}

.available-commands h4 {
  margin-bottom: 15px;
  color: #2c3e50;
}

.command-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.command-tag {
  background: #3498db;
  color: white;
  padding: 4px 10px;
  border-radius: 15px;
  font-size: 0.8rem;
  font-family: 'Courier New', monospace;
}

/* Action Buttons */
.action-buttons {
  display: flex;
  gap: 15px;
  margin-bottom: 25px;
  flex-wrap: wrap;
}

.action-info {
  color: #7f8c8d;
}

.action-info .info-item {
  margin-bottom: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #ecf0f1;
  display: block;
}

.action-info .info-item:last-child {
  border-bottom: none;
}

/* Search Section */
.search-input {
  display: flex;
  gap: 15px;
  margin-bottom: 25px;
}

.form-input {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid #ecf0f1;
  border-radius: 6px;
  font-size: 1rem;
}

.form-input:focus {
  outline: none;
  border-color: #3498db;
}

.search-results h4 {
  margin-bottom: 20px;
  color: #2c3e50;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.result-item {
  background: white;
  padding: 15px;
  border-radius: 8px;
  border-left: 4px solid #3498db;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.result-header strong {
  color: #2c3e50;
  font-family: 'Courier New', monospace;
}

.relevance-score {
  font-size: 0.8rem;
  color: #7f8c8d;
  background: #ecf0f1;
  padding: 2px 8px;
  border-radius: 12px;
}

.result-purpose {
  color: #2c3e50;
  margin-bottom: 8px;
}

.result-meta {
  font-size: 0.8rem;
  color: #7f8c8d;
}

.source {
  font-style: italic;
}

.machine {
  font-family: 'Courier New', monospace;
}

/* Progress Messages */
.progress-message {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 15px 20px;
  border-radius: 8px;
  color: white;
  font-weight: 600;
  z-index: 1000;
  max-width: 400px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.progress-message.info {
  background: #3498db;
}

.progress-message.success {
  background: #27ae60;
}

.progress-message.warning {
  background: #f39c12;
}

.progress-message.error {
  background: #e74c3c;
}

.progress-message i {
  margin-right: 10px;
}

/* Loading and No Data States */
.loading,
.no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 15px;
  padding: 40px;
  color: #7f8c8d;
  font-style: italic;
}

.loading i,
.no-data i {
  font-size: 1.2rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .man-page-manager {
    padding: 15px;
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

/* Progress Tracking Styles */
.progress-section {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 20px;
  margin: 25px 0;
}

.progress-container {
  margin-top: 15px;
}

.progress-item {
  margin-bottom: 15px;
}

.progress-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
  color: #2c3e50;
}

.progress-percentage {
  font-size: 0.9em;
  color: #7f8c8d;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #ecf0f1;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width 0.3s ease;
  border-radius: 4px;
}

.progress-fill.waiting {
  background: #95a5a6;
}

.progress-fill.running {
  background: linear-gradient(90deg, #3498db, #2980b9);
}

.progress-fill.success {
  background: linear-gradient(90deg, #27ae60, #229954);
}

.progress-fill.error {
  background: linear-gradient(90deg, #e74c3c, #c0392b);
}

.progress-fill.task-progress {
  background: linear-gradient(90deg, #9b59b6, #8e44ad);
}

.progress-messages {
  background: #ffffff;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
  margin: 15px 0;
  padding: 10px;
}

.progress-message {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f1f3f4;
  font-size: 0.9em;
}

.progress-message:last-child {
  border-bottom: none;
}

.progress-message .timestamp {
  color: #6c757d;
  font-size: 0.8em;
  margin-right: 10px;
  min-width: 70px;
}

.progress-message .message {
  flex: 1;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #ffffff;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  font-size: 0.9em;
}

.text-green-500 { color: #10b981; }
.text-green-600 { color: #059669; }

/* Custom scrollbar styling for better UX */
.man-page-manager::-webkit-scrollbar {
  width: 8px;
}

.man-page-manager::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.man-page-manager::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.man-page-manager::-webkit-scrollbar-thumb:hover {
  background: #555;
}
.text-green-500 { color: #10b981; }
.text-green-600 { color: #059669; }
.text-red-500 { color: #ef4444; }
.text-red-600 { color: #dc2626; }
.text-blue-500 { color: #3b82f6; }
.text-yellow-500 { color: #eab308; }
</style>
