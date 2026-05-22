<template>
  <div class="man-page-manager">

    <!-- Machine Profile Section -->
    <BasePanel variant="bordered" size="md">
      <template #header>
        <h3><Icon name="desktop" /> {{ $t('manpage.manager.title') }}</h3>
        <BaseButton
          size="sm"
          variant="outline-solid"
          @click="refreshMachineProfile"
          :disabled="loading?.profile"
        >
          <Icon name="sync" />
          {{ $t('manpage.manager.refresh') }}
        </BaseButton>
      </template>

      <div v-if="machineProfile && !loading?.profile" class="machine-info">
        <div class="info-grid">
          <div class="info-item">
            <label>{{ $t('manpage.manager.machineId') }}</label>
            <span class="mono">{{ machineProfile.machine_id || $t('manpage.manager.notDetected') }}</span>
          </div>
          <div class="info-item">
            <label>{{ $t('manpage.manager.osType') }}</label>
            <span class="badge" :class="getOSBadgeClass(machineProfile.os_type)">
              {{ machineProfile.os_type || $t('manpage.manager.unknown') }}
            </span>
          </div>
          <div class="info-item">
            <label>{{ $t('manpage.manager.distribution') }}</label>
            <span>{{ machineProfile.distro || $t('manpage.manager.na') }}</span>
          </div>
          <div class="info-item">
            <label>{{ $t('manpage.manager.packageManager') }}</label>
            <span class="mono">{{ machineProfile.package_manager || $t('manpage.manager.unknown') }}</span>
          </div>
          <div class="info-item">
            <label>{{ $t('manpage.manager.availableTools') }}</label>
            <span class="highlight">{{ (machineProfile.available_tools || []).length }}</span>
          </div>
          <div class="info-item">
            <label>{{ $t('manpage.manager.architecture') }}</label>
            <span>{{ machineProfile.architecture || $t('manpage.manager.unknown') }}</span>
          </div>
        </div>
      </div>

      <div v-else-if="!loading?.profile" class="no-data">
        <Icon name="exclamation-triangle" />
        {{ $t('manpage.manager.noProfile') }}
      </div>

      <div v-if="loading?.profile" class="loading">
        <Icon name="spinner" class="animate-spin" />
        {{ $t('manpage.manager.detectingProfile') }}
      </div>
    </BasePanel>

    <!-- Integration Status Section -->
    <BasePanel variant="bordered" size="md">
      <template #header>
        <h3><Icon name="chart-bar" /> {{ $t('manpage.manager.integrationStatus') }}</h3>
        <BaseButton
          size="sm"
          variant="outline-solid"
          @click="refreshIntegrationStatus"
          :disabled="loading?.status"
        >
          <Icon name="sync" />
          {{ $t('manpage.manager.refresh') }}
        </BaseButton>
      </template>

      <div v-if="integrationStatus" class="status-info">
        <div v-if="integrationStatus.status === 'not_integrated'" class="not-integrated">
          <Icon name="info-circle" />
          <div>
            <strong>{{ $t('manpage.manager.notIntegrated') }}</strong>
            <p>{{ $t('manpage.manager.notIntegratedDesc') }}</p>
          </div>
        </div>

        <div v-else-if="integrationStatus.status === 'error'" class="error">
          <Icon name="exclamation-circle" />
          <div>
            <strong>{{ $t('manpage.manager.integrationError') }}</strong>
            <p>{{ integrationStatus.message }}</p>
          </div>
        </div>

        <div v-else class="integration-stats">
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.successful || 0 }}</div>
              <div class="stat-label">{{ $t('manpage.manager.successful') }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.processed || 0 }}</div>
              <div class="stat-label">{{ $t('manpage.manager.processed') }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.current_man_page_files || 0 }}</div>
              <div class="stat-label">{{ $t('manpage.manager.knowledgeFiles') }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ integrationStatus.total_available_tools || 0 }}</div>
              <div class="stat-label">{{ $t('manpage.manager.availableTools') }}</div>
            </div>
          </div>

          <div v-if="integrationStatus.integration_date" class="integration-date">
            <Icon name="clock" />
            {{ $t('manpage.manager.lastIntegrated') }} {{ formatDate(integrationStatus.integration_date) }}
          </div>

          <div v-if="integrationStatus.available_commands" class="available-commands">
            <h4>{{ $t('manpage.manager.integratedCommands', { count: integrationStatus.available_commands.length }) }}</h4>
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
        <Icon name="spinner" class="animate-spin" />
        {{ $t('manpage.manager.loadingStatus') }}
      </div>
    </BasePanel>

    <!-- Integration Actions -->
    <div class="integration-actions">
      <div class="section-header">
        <h3><Icon name="cogs" /> {{ $t('manpage.manager.integrationActions') }}</h3>
      </div>

      <div class="action-buttons">
        <BaseButton
          variant="primary"
          @click="initializeMachineKnowledgeWithProgress"
          :disabled="loading?.initialize || !canInitialize"
          :loading="loading?.initialize"
        >
          <Icon name="rocket" />
          {{ $t('manpage.manager.initializeMachineKnowledge') }}
        </BaseButton>

        <BaseButton
          variant="success"
          @click="integrateManPagesWithProgress"
          :disabled="loading?.integrate || !canIntegrate"
          :loading="loading?.integrate"
        >
          <Icon name="book-open" />
          {{ $t('manpage.manager.integrateManPages') }}
        </BaseButton>

        <BaseButton
          variant="info"
          @click="testSearchManPages"
          :disabled="loading?.search || !hasIntegration"
          :loading="loading?.search"
        >
          <Icon name="search" />
          {{ $t('manpage.manager.testSearch') }}
        </BaseButton>
      </div>

      <!-- Real-time Progress Tracking -->
      <BasePanel v-if="showProgressTracking" variant="bordered" size="md">
        <template #header>
          <h3><Icon name="tasks" /> {{ $t('manpage.manager.progressTitle') }}</h3>
          <BaseButton
            size="sm"
            variant="outline-solid"
            @click="showProgressTracking = false"
          >
            <Icon name="times" />
            {{ $t('manpage.manager.hideProgress') }}
          </BaseButton>
        </template>

        <div class="progress-container">
          <!-- Overall Progress -->
          <div class="progress-item">
            <div class="progress-label">
              <span>{{ progressState.currentTask || $t('manpage.progressTracking.waiting') }}</span>
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
              <span>{{ progressState.taskDetail || $t('manpage.progressTracking.processing') }}</span>
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
              <Icon :name="getMessageIcon(message.type)" />
              <span class="timestamp">{{ formatTime(message.timestamp) }}</span>
              <span class="message">{{ message.text }}</span>
            </div>
          </div>

          <!-- Connection Status -->
          <div class="connection-status">
            <Icon :name="websocketConnected ? 'plug' : 'plug'" :class="websocketConnected ? 'connected-icon' : 'disconnected-icon'" />
            <span :class="websocketConnected ? 'connected-text' : 'disconnected-text'">
              {{ websocketConnected ? $t('manpage.progressTracking.connected') : $t('manpage.progressTracking.disconnected') }}
            </span>
          </div>
        </div>
      </BasePanel>

      <div class="action-info">
        <div class="info-item">
          <strong>{{ $t('manpage.manager.initializeMachineKnowledge') }}:</strong>
          {{ $t('manpage.integrationActions.initializeDesc') }}
        </div>
        <div class="info-item">
          <strong>{{ $t('manpage.manager.integrateManPages') }}:</strong>
          {{ $t('manpage.integrationActions.integrateDesc') }}
        </div>
        <div class="info-item">
          <strong>{{ $t('manpage.manager.testSearch') }}:</strong>
          {{ $t('manpage.integrationActions.testSearchDesc') }}
        </div>
      </div>
    </div>

    <!-- Search Section -->
    <BasePanel v-if="showSearch" variant="bordered" size="md">
      <template #header>
        <h3><Icon name="search" /> {{ $t('manpage.manager.searchTitle') }}</h3>
      </template>

      <div class="search-input">
        <input
          v-model="searchQuery"
          @keyup.enter="searchManPages"
          type="text"
          :placeholder="$t('manpage.manager.searchPlaceholder')"
          class="form-input"
        >
        <BaseButton
          variant="primary"
          @click="searchManPages"
          :disabled="!searchQuery.trim() || loading?.search"
        >
          <Icon name="search" />
          {{ $t('manpage.manager.search') }}
        </BaseButton>
      </div>

      <div v-if="searchResults" class="search-results">
        <h4>{{ $t('manpage.manager.resultsFor', { query: lastSearchQuery }) }}</h4>

        <EmptyState
          v-if="searchResults.length === 0"
          icon="info-circle"
          :message="$t('manpage.manager.noResults')"
        />

        <div v-else class="result-list">
          <div v-for="result in searchResults" :key="result.command" class="result-item">
            <div class="result-header">
              <strong>{{ result.command }}</strong>
              <span class="relevance-score">{{ $t('manpage.manager.score', { score: result.relevance_score }) }}</span>
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
      <Icon :name="getProgressIcon()" />
      {{ progressMessage }}
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for ManPageManager
const logger = createLogger('ManPageManager')
import { useMachineKnowledge } from '@/composables/knowledge/useMachineKnowledge'
import { useManPages } from '@/composables/knowledge/useManPages'
import { useKnowledgeIcons } from '@/composables/knowledge/useKnowledgeIcons'
import { formatDate } from '@/utils/formatHelpers'
import { useLoadingState } from '@/composables/useLoadingState'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import Icon from '@/components/ui/Icon.vue'

export default {
  name: 'ManPageManager',
  components: {
    EmptyState,
    BaseButton,
    BasePanel,
    Icon,
  },
  setup() {
    const { t } = useI18n()

    // Domain composables (migrated from useKnowledgeBase BC shim in #5193)
    const {
      fetchMachineProfile: fetchMachineProfileAPI,
      initializeMachineKnowledge: initializeMachineKnowledgeAPI,
    } = useMachineKnowledge()
    const {
      fetchManPagesSummary: fetchManPagesSummaryAPI,
      integrateManPages: integrateManPagesAPI,
      searchManPages: searchManPagesAPI,
    } = useManPages()
    const { getOSBadgeClass, getMessageIcon, formatTime } = useKnowledgeIcons()

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
    const { isLoading: isLoadingProfile, wrap: wrapProfile } = useLoadingState()
    const { isLoading: isLoadingStatus, wrap: wrapStatus } = useLoadingState()
    const { isLoading: isLoadingInitialize, wrap: wrapInitialize } = useLoadingState()
    const { isLoading: isLoadingIntegrate, wrap: wrapIntegrate } = useLoadingState()
    const { isLoading: isLoadingSearch, wrap: wrapSearch } = useLoadingState()

    // Computed loading states for backward compatibility
    const loading = computed(() => ({
      profile: isLoadingProfile.value,
      status: isLoadingStatus.value,
      initialize: isLoadingInitialize.value,
      integrate: isLoadingIntegrate.value,
      search: isLoadingSearch.value
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
        case 'success': return 'check-circle'
        case 'error': return 'exclamation-circle'
        case 'warning': return 'exclamation-triangle'
        default: return 'info-circle'
      }
    }

    // Removed: getOSBadgeClass - now using composable
    // Removed: formatDate - now using composable

    const refreshMachineProfile = async () => {
      if (isLoadingProfile.value) return // Prevent concurrent calls

      await wrapProfile(async () => {
        const profile = await fetchMachineProfileAPI()

        if (profile) {
          machineProfile.value = profile
          setProgressMessage(t('manpage.manager.profileRefreshed'), 'success')
        } else {
          // Handle API errors gracefully
          machineProfile.value = null
          setProgressMessage(t('manpage.manager.noProfile'), 'warning')
        }
      }).catch(error => {
        logger.error('Error refreshing machine profile:', error)
        setProgressMessage('Could not connect to backend API', 'error')
        machineProfile.value = null
      })
    }

    const refreshIntegrationStatus = async () => {
      if (isLoadingStatus.value) return // Prevent concurrent calls

      await wrapStatus(async () => {
        const summary = await fetchManPagesSummaryAPI()

        if (summary) {
          integrationStatus.value = summary
          setProgressMessage('Integration status refreshed', 'success')
        } else {
          // Handle API errors gracefully
          integrationStatus.value = { status: 'not_integrated', message: 'Backend restart required' }
          setProgressMessage('Integration status not available (backend restart required)', 'warning')
        }
      }).catch(error => {
        logger.error('Error refreshing integration status:', error)
        setProgressMessage('Could not connect to backend API', 'error')
        integrationStatus.value = { status: 'error', message: 'Connection failed' }
      })
    }

    const initializeMachineKnowledge = async () => {
      if (isLoadingInitialize.value) return // Prevent concurrent calls
      setProgressMessage(t('manpage.manager.initializingKnowledge'), 'info', 0)

      await wrapInitialize(async () => {
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
      }).catch(error => {
        logger.error('Error initializing machine knowledge:', error)
        setProgressMessage(`Initialization failed: ${error.message}`, 'error')
      })
    }

    const integrateManPages = async () => {
      if (!canIntegrate.value) {
        setProgressMessage(t('manpage.manager.linuxOnly'), 'warning')
        return
      }

      if (isLoadingIntegrate.value) return // Prevent concurrent calls
      setProgressMessage('Integrating man pages... This may take a minute.', 'info', 0)

      await wrapIntegrate(async () => {
        const response = await integrateManPagesAPI()

        if (response.status === 'success') {
          setProgressMessage('Man pages integrated successfully!', 'success')
          await refreshIntegrationStatus()
        } else if (response.status === 'skipped') {
          setProgressMessage(`Integration skipped: ${response.message}`, 'warning')
        } else {
          throw new Error(response.message || 'Integration failed')
        }
      }).catch(error => {
        logger.error('Error integrating man pages:', error)
        setProgressMessage(`Integration failed: ${error.message}`, 'error')
      })
    }

    const searchManPages = async () => {
      if (!searchQuery.value.trim()) {
        setProgressMessage(t('manpage.manager.enterQuery'), 'warning')
        return
      }

      if (isLoadingSearch.value) return // Prevent concurrent calls
      lastSearchQuery.value = searchQuery.value.trim()

      await wrapSearch(async () => {
        const response = await searchManPagesAPI(lastSearchQuery.value)

        if (response.status === 'success') {
          searchResults.value = response.results
          showSearch.value = true
          setProgressMessage(`Found ${response.results_count} results`, 'success')
        } else {
          throw new Error('Search failed')
        }
      }).catch(error => {
        logger.error('Error searching man pages:', error)
        setProgressMessage(`Search failed: ${error.message}`, 'error')
        searchResults.value = []
      })
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

      setProgressMessage(t('manpage.manager.initializingKnowledge'), 'info', 0)
      updateProgress(t('manpage.manager.initializeMachineKnowledge'), 10, t('manpage.manager.initializingKnowledge'))
      addProgressMessage(t('manpage.manager.initializingKnowledge'), 'info')

      await wrapInitialize(async () => {
        const response = await initializeMachineKnowledgeAPI(false)

        if (response.status !== 'success') {
          throw new Error(response.message || 'Initialization failed')
        }

        updateProgress(t('manpage.manager.initializeMachineKnowledge'), 100, t('manpage.manager.initComplete'), 100, 'success')
        addProgressMessage(t('manpage.manager.initComplete'), 'success')
        setProgressMessage(t('manpage.manager.initComplete'), 'success')

        await refreshMachineProfile()
        await refreshIntegrationStatus()
      }).catch(error => {
        logger.error('Failed to initialize machine knowledge:', error)
        updateProgress('Initialization Failed', 0, error.message, 0, 'error')
        addProgressMessage(`Initialization failed: ${error.message}`, 'error')
        setProgressMessage(`Failed to initialize machine knowledge: ${error.message}`, 'error')
      })
    }

    const integrateManPagesWithProgress = async () => {
      showProgressTracking.value = true
      resetProgress()

      setProgressMessage(t('manpage.manager.integrateManPages'), 'info', 0)
      updateProgress(t('manpage.manager.integrateManPages'), 10, t('manpage.manager.integrateManPages'))
      addProgressMessage(t('manpage.manager.integrateManPages'), 'info')

      await wrapIntegrate(async () => {
        const response = await integrateManPagesAPI()

        if (response.status !== 'success') {
          throw new Error(response.message || 'Integration failed')
        }

        updateProgress(t('manpage.manager.integrateManPages'), 100, t('manpage.manager.integrationComplete'), 100, 'success')
        addProgressMessage(t('manpage.manager.integrationComplete'), 'success')
        setProgressMessage(t('manpage.manager.integrationComplete'), 'success')

        await refreshIntegrationStatus()
      }).catch(error => {
        logger.error('Failed to integrate man pages:', error)
        updateProgress('Integration Failed', 0, error.message, 0, 'error')
        addProgressMessage(`Integration failed: ${error.message}`, 'error')
        setProgressMessage(`Failed to integrate man pages: ${error.message}`, 'error')
      })
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
.form-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
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
  background: var(--color-info);
}

.progress-fill.success {
  background: var(--color-success);
}

.progress-fill.error {
  background: var(--color-error);
}

.progress-fill.task-progress {
  background: var(--chart-purple);
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
