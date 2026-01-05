<template>
  <ErrorBoundary fallback="Settings panel failed to load.">
<div class="settings-panel">
  <!-- Tab Navigation (now using router-links) -->
  <SettingsTabNavigation
    :hasUnsavedChanges="hasUnsavedChanges"
    :tabs="tabs"
  />

  <div class="settings-content">
    <!-- Loading indicator -->
    <div v-if="settingsLoadingStatus === 'loading'" class="settings-loading">
      <div class="loading-spinner"></div>
      <p>Loading settings...</p>
    </div>

    <!-- Settings status message -->
    <div v-if="settingsLoadingStatus === 'offline'" class="settings-status offline">
      <i class="fas fa-exclamation-triangle"></i>
      <span>Backend offline - using cached settings</span>
    </div>

    <!-- Router View for Settings Sub-routes -->
    <router-view
      v-if="isSettingsLoaded"
      :settings="settings"
      :isSettingsLoaded="isSettingsLoaded"
      :healthStatus="healthStatus"
      :cacheConfig="cacheConfig"
      :cacheActivity="cacheActivity"
      :cacheStats="cacheStats"
      :isSaving="isSaving"
      :isClearing="isClearing"
      :cacheApiAvailable="cacheApiAvailable"
      :activeBackendSubTab="activeBackendSubTab"
      @setting-changed="handleSettingChanged"
      @change="markAsChanged"
      @subtab-changed="activeBackendSubTab = $event"
      @cache-config-changed="updateCacheConfig"
      @save-cache-config="saveCacheConfig"
      @refresh-cache-activity="refreshCacheActivity"
      @refresh-cache-stats="refreshCacheStats"
      @clear-cache="clearCache"
      @clear-redis-cache="clearRedisCache"
      @clear-cache-type="clearCacheType"
      @warmup-caches="warmupCaches"
      @prompt-selected="selectPrompt"
      @edited-content-changed="updatePromptEditedContent"
      @selected-prompt-cleared="clearSelectedPrompt"
      @load-prompts="loadPrompts"
      @save-prompt="savePrompt"
      @revert-prompt-to-default="revertPromptToDefault"
    />

    <!-- Save Settings Button -->
    <div v-if="isSettingsLoaded && hasUnsavedChanges" class="settings-actions">
      <button @click="saveSettings" :disabled="isSaving" class="save-settings-btn">
        <i :class="isSaving ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
        {{ isSaving ? 'Saving...' : 'Save Settings' }}
      </button>
      <button @click="discardChanges" :disabled="isSaving" class="discard-btn">
        <i class="fas fa-undo"></i>
        Discard Changes
      </button>
    </div>
  </div>
</div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, provide } from 'vue'
import axios from 'axios'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SettingsPanel')

// Import error handling composables
import { useAsyncHandler } from '../composables/useErrorHandler'
import { useToast } from '../composables/useToast'

// Import sub-components
import ErrorBoundary from './ErrorBoundary.vue'
import SettingsTabNavigation from './settings/SettingsTabNavigation.vue'

// Import services and types
import cacheService from '../services/CacheService'
import {
  createDefaultSettings,
  createDefaultCacheConfig,
  createCacheActivityItem
} from '../types/settings'
import type {
  SettingsStructure,
  SettingsTab,
  ChatSettings as ChatSettingsType,
  UISettings as UISettingsType,
  LoggingSettings as LoggingSettingsType,
  PromptsSettings as PromptsSettingsType,
  DeveloperSettings as DeveloperSettingsType,
  BackendSettings as BackendSettingsType,
  HealthStatus,
  CacheActivityItem,
  CacheStats,
  CacheConfig,
  Prompt
} from '../types/settings'

// Initialize settings with proper structure to prevent undefined props
const getDefaultSettings = (): SettingsStructure => createDefaultSettings()

// Reactive state
const settings = ref<SettingsStructure>(getDefaultSettings())
const hasUnsavedChanges = ref<boolean>(false)
const isSettingsLoaded = ref<boolean>(false)
const settingsLoadingStatus = ref<'loading' | 'loaded' | 'offline'>('loading')
const isSaving = ref<boolean>(false)
const isClearing = ref<boolean>(false)
const healthStatus = ref<HealthStatus | null>(null)
const cacheApiAvailable = ref<boolean>(false)

const tabs = ref<SettingsTab[]>([
  { id: 'user', label: 'User Management' },
  { id: 'chat', label: 'Chat' },
  { id: 'backend', label: 'Backend' },
  { id: 'ui', label: 'UI' },
  { id: 'logging', label: 'Logging' },
  { id: 'cache', label: 'Cache' },
  { id: 'data-storage', label: 'Data Storage' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'services', label: 'Services' },
  { id: 'infrastructure', label: 'Infrastructure' },
  { id: 'developer', label: 'Developer' }
])
const activeBackendSubTab = ref('agents')

// Cache state
const cacheConfig = reactive<CacheConfig>(createDefaultCacheConfig())
const cacheActivity = ref<CacheActivityItem[]>([])
const cacheStats = ref<CacheStats | null>(null)

// Toast notifications
const { showToast } = useToast()

// Notification helper for useAsyncHandler
const notify = (message: string, type: 'success' | 'error' | 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// Helper functions
const markAsChanged = () => {
  hasUnsavedChanges.value = true
}

// Generic setting change handler that routes to appropriate update function
const handleSettingChanged = (key: string, value: any) => {
  const [category, ...rest] = key.split('.')
  const subKey = rest.join('.')

  switch (category) {
    case 'chat':
      updateChatSetting(subKey || key, value)
      break
    case 'user':
      updateUserSetting(subKey || key, value)
      break
    case 'backend':
      updateBackendSetting(subKey || key, value)
      break
    case 'ui':
      updateUISetting(subKey || key, value)
      break
    case 'logging':
      updateLoggingSetting(subKey || key, value)
      break
    case 'developer':
      if (subKey.startsWith('rum.')) {
        updateRUMSetting(subKey.replace('rum.', ''), value)
      } else {
        updateDeveloperSetting(subKey || key, value)
      }
      break
    case 'llm':
      updateLLMSetting(subKey || key, value)
      break
    default:
      // For settings without category prefix
      markAsChanged()
  }
}

const updateChatSetting = (key: string, value: any) => {
  if (!settings.value.chat) {
    settings.value.chat = {
      auto_scroll: true,
      max_messages: 100,
      message_retention_days: 30
    } as ChatSettingsType
  }
  // Issue #156 Fix: Use Record<string, any> type assertion for dynamic property assignment
  const chatSettings = settings.value.chat as Record<string, any>
  chatSettings[key] = value
  markAsChanged()
}

const updateUserSetting = (key: string, value: any) => {
  // Handle user management settings
  markAsChanged()
}

const updateBackendSetting = (key: string, value: any) => {
  if (!settings.value.backend) {
    settings.value.backend = {} as BackendSettingsType
  }
  // Handle nested settings for memory and agents
  if (key.includes('.')) {
    const keys = key.split('.')
    let obj: any = settings.value.backend
    for (let i = 0; i < keys.length - 1; i++) {
      if (!obj![keys[i]]) obj![keys[i]] = {}
      obj = obj![keys[i]]
    }
    obj![keys[keys.length - 1]] = value
  } else {
    (settings.value.backend as any)[key] = value
  }
  markAsChanged()
}

const updateLLMSetting = (key: string, value: any) => {
  if (!settings.value.backend) {
    settings.value.backend = {} as BackendSettingsType
  }
  if (!settings.value.backend.llm) {
    settings.value.backend.llm = {}
  }
  const keys = key.split('.')
  let obj: any = settings.value.backend.llm
  for (let i = 0; i < keys.length - 1; i++) {
    if (!obj![keys[i]]) obj![keys[i]] = {}
    obj = obj![keys[i]]
  }
  obj![keys[keys.length - 1]] = value
  markAsChanged()
}

const updateUISetting = (key: string, value: any) => {
  if (!settings.value.ui) {
    settings.value.ui = {
      theme: 'auto',
      language: 'en',
      show_timestamps: true,
      show_status_bar: true,
      auto_refresh_interval: 30
    } as UISettingsType
  }
  // Issue #156 Fix: Use Record<string, any> type assertion for dynamic property assignment
  const uiSettings = settings.value.ui as Record<string, any>
  uiSettings[key] = value
  markAsChanged()
}

const updateLoggingSetting = (key: string, value: any) => {
  if (!settings.value.logging) {
    settings.value.logging = {
      level: 'info',
      log_levels: ['debug', 'info', 'warn', 'error'],
      console: true,
      file: false,
      max_file_size: 10,
      log_requests: false,
      log_sql: false
    } as LoggingSettingsType
  }
  // Issue #156 Fix: Use Record<string, any> type assertion for dynamic property assignment
  const loggingSettings = settings.value.logging as Record<string, any>
  loggingSettings[key] = value
  markAsChanged()
}

const updateDeveloperSetting = (key: string, value: any) => {
  if (!settings.value.developer) {
    settings.value.developer = {
      enabled: false,
      enhanced_errors: true,
      endpoint_suggestions: true,
      debug_logging: false,
      rum: {
        enabled: false,
        error_tracking: true,
        performance_monitoring: true,
        interaction_tracking: false,
        session_recording: false,
        sample_rate: 100,
        max_events_per_session: 1000
      }
    } as DeveloperSettingsType
  }
  (settings.value.developer as DeveloperSettingsType)[key as keyof DeveloperSettingsType] = value
  markAsChanged()
}

const updateRUMSetting = (key: string, value: any) => {
  if (!settings.value.developer) {
    settings.value.developer = {
      enabled: false,
      enhanced_errors: true,
      endpoint_suggestions: true,
      debug_logging: false,
      rum: {
        enabled: false,
        error_tracking: true,
        performance_monitoring: true,
        interaction_tracking: false,
        session_recording: false,
        sample_rate: 100,
        max_events_per_session: 1000
      }
    } as DeveloperSettingsType
  }
  if (!settings.value.developer.rum) {
    settings.value.developer.rum = {
      enabled: false,
      error_tracking: true,
      performance_monitoring: true,
      interaction_tracking: false,
      session_recording: false,
      sample_rate: 100,
      max_events_per_session: 1000
    }
  }
  (settings.value.developer.rum as any)[key] = value
  markAsChanged()
}

const updateCacheConfig = (key: string, value: any) => {
  (cacheConfig as any)[key] = value
  markAsChanged()
}

const getCurrentLLMDisplay = (): string => {
  const llmConfig = settings.value.backend?.llm
  if (!llmConfig) return 'Not configured'

  const providerType = llmConfig.provider_type || 'local'
  if (providerType === 'local') {
    const provider = llmConfig.local?.provider || 'ollama'
    const model = llmConfig.local?.providers?.[provider]?.selected_model || 'Not selected'
    return `${provider.toUpperCase()}: ${model}`
  } else {
    const provider = llmConfig.cloud?.provider || 'openai'
    const model = llmConfig.cloud?.providers?.[provider]?.selected_model || 'Not selected'
    return `${provider.toUpperCase()}: ${model}`
  }
}

// Provide settings data for child components via router-view
provide('settingsData', {
  settings,
  isSettingsLoaded,
  healthStatus,
  getCurrentLLMDisplay
})

// Add guard to prevent infinite loading loops
let isLoadingSettings = false

// Load settings on mount with error handling
const loadSettings = async () => {
  // Prevent concurrent loading calls that cause infinite loops
  if (isLoadingSettings) {
    return
  }

  isLoadingSettings = true
  settingsLoadingStatus.value = 'loading'

  const { execute: fetchSettings } = useAsyncHandler(
    // Issue #552: Use trailing slash to match backend endpoint /api/settings/
    async () => axios.get('/api/settings/'),
    {
      errorMessage: 'Failed to load settings',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: (response) => {
        settings.value = {
          ...getDefaultSettings(),
          ...response.data
        }
        isSettingsLoaded.value = true
        settingsLoadingStatus.value = 'loaded'
        hasUnsavedChanges.value = false
      },
      onError: () => {
        settingsLoadingStatus.value = 'offline'
        // Load from cache if available
        const cachedSettings = cacheService.get('settings')
        if (cachedSettings) {
          settings.value = {
            ...getDefaultSettings(),
            ...cachedSettings
          }
          isSettingsLoaded.value = true
          notify('Using cached settings (backend offline)', 'info')
        }
      },
      onFinally: () => {
        isLoadingSettings = false
      }
    }
  )

  await fetchSettings()
}

const saveSettings = async () => {
  isSaving.value = true

  const { execute: postSettings } = useAsyncHandler(
    // Issue #552: Use trailing slash to match backend endpoint /api/settings/
    async () => axios.post('/api/settings/', settings.value),
    {
      errorMessage: 'Failed to save settings',
      successMessage: 'Settings saved successfully',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: () => {
        hasUnsavedChanges.value = false
        // Cache the settings
        cacheService.set('settings', settings.value, 3600)
      },
      onFinally: () => {
        isSaving.value = false
      }
    }
  )

  await postSettings()
}

const discardChanges = () => {
  hasUnsavedChanges.value = false
  // Only reload if not already loading to prevent loops
  if (!isLoadingSettings) {
    loadSettings()
  }
}

// Cache management functions with proper error handling
const checkCacheApiAvailability = async () => {
  const { execute: checkCache } = useAsyncHandler(
    async () => axios.get('/api/cache/stats', { timeout: 3000 }),
    {
      logErrors: false, // Silent check - don't log errors for availability check
      onSuccess: () => {
        cacheApiAvailable.value = true
      },
      onError: () => {
        cacheApiAvailable.value = false
      }
    }
  )

  await checkCache()
}

const saveCacheConfig = async () => {
  if (!cacheApiAvailable.value) {
    notify('Cache API not available', 'error')
    return
  }

  isSaving.value = true

  const { execute: postCacheConfig } = useAsyncHandler(
    async () => axios.post('/api/cache/config', cacheConfig),
    {
      errorMessage: 'Failed to save cache configuration',
      successMessage: 'Cache configuration saved',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: () => {
        markAsChanged()
      },
      onFinally: () => {
        isSaving.value = false
      }
    }
  )

  await postCacheConfig()
}

const refreshCacheActivity = async () => {
  if (!cacheApiAvailable.value) {
    cacheActivity.value = []
    return
  }

  try {
    // Note: There's no /api/cache/activity endpoint, creating fallback data
    cacheActivity.value = [
      createCacheActivityItem({
        timestamp: new Date().toISOString(),
        operation: 'cache_check',
        key: 'settings',
        result: 'hit',
        duration_ms: 1.2
      })
    ]
  } catch (error) {
    logger.error('Failed to refresh cache activity:', error)
    cacheActivity.value = []
  }
}

const refreshCacheStats = async () => {
  if (!cacheApiAvailable.value) {
    cacheStats.value = {
      status: 'unavailable',
      message: 'Cache API not available in fast backend'
    } as CacheStats
    return
  }

  const { execute: getCacheStats } = useAsyncHandler(
    async () => axios.get('/api/cache/stats'),
    {
      errorMessage: 'Failed to refresh cache statistics',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: (response) => {
        cacheStats.value = response.data
      },
      onError: () => {
        cacheStats.value = {
          status: 'error',
          message: 'Failed to load cache statistics'
        } as CacheStats
      }
    }
  )

  await getCacheStats()
}

const clearCache = async (type: string) => {
  if (!cacheApiAvailable.value) {
    notify('Cache API not available', 'error')
    return
  }

  isClearing.value = true

  const { execute: postClearCache } = useAsyncHandler(
    async () => axios.post(`/api/cache/clear/${type}`),
    {
      errorMessage: `Failed to clear ${type} cache`,
      successMessage: `${type} cache cleared successfully`,
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: async () => {
        await refreshCacheStats()
      },
      onFinally: () => {
        isClearing.value = false
      }
    }
  )

  await postClearCache()
}

const clearRedisCache = async (database: string) => {
  if (!cacheApiAvailable.value) {
    notify('Cache API not available', 'error')
    return
  }

  isClearing.value = true

  const { execute: postClearRedis } = useAsyncHandler(
    async () => axios.post(`/api/cache/redis/clear/${database}`),
    {
      errorMessage: `Failed to clear Redis ${database} database`,
      successMessage: `Redis ${database} database cleared`,
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: async () => {
        await refreshCacheStats()
        await refreshCacheActivity()
      },
      onFinally: () => {
        isClearing.value = false
      }
    }
  )

  await postClearRedis()
}

const clearCacheType = async (cacheType: string) => {
  if (!cacheApiAvailable.value) {
    notify('Cache API not available', 'error')
    return
  }

  isClearing.value = true

  const { execute: postClearCacheType } = useAsyncHandler(
    async () => axios.post(`/api/cache/clear/${cacheType}`),
    {
      errorMessage: `Failed to clear ${cacheType} cache`,
      successMessage: `${cacheType} cache cleared`,
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: async () => {
        await refreshCacheStats()
        await refreshCacheActivity()
      },
      onFinally: () => {
        isClearing.value = false
      }
    }
  )

  await postClearCacheType()
}

const warmupCaches = async () => {
  if (!cacheApiAvailable.value) {
    notify('Cache API not available', 'error')
    return
  }

  isClearing.value = true

  const { execute: postWarmup } = useAsyncHandler(
    async () => axios.post('/api/cache/warmup'),
    {
      errorMessage: 'Failed to warm up caches',
      successMessage: 'Cache warmup completed',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: async () => {
        await refreshCacheStats()
        await refreshCacheActivity()
      },
      onFinally: () => {
        isClearing.value = false
      }
    }
  )

  await postWarmup()
}

// Prompt management functions
const selectPrompt = (prompt: Prompt) => {
  if (!settings.value.prompts) {
    settings.value.prompts = {
      list: [],
      selectedPrompt: null,
      editedContent: ''
    } as PromptsSettingsType
  }
  settings.value.prompts.selectedPrompt = prompt
  settings.value.prompts.editedContent = prompt.content || ''
}

const updatePromptEditedContent = (content: string) => {
  if (!settings.value.prompts) {
    settings.value.prompts = {
      list: [],
      selectedPrompt: null,
      editedContent: ''
    } as PromptsSettingsType
  }
  settings.value.prompts.editedContent = content
}

const clearSelectedPrompt = () => {
  if (!settings.value.prompts) {
    settings.value.prompts = {
      list: [],
      selectedPrompt: null,
      editedContent: ''
    } as PromptsSettingsType
  }
  settings.value.prompts.selectedPrompt = null
  settings.value.prompts.editedContent = ''
}

const loadPrompts = async () => {
  const { execute: getPrompts } = useAsyncHandler(
    async () => axios.get('/api/prompts'),
    {
      errorMessage: 'Failed to load prompts',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: (response) => {
        if (!settings.value.prompts) {
          settings.value.prompts = {
            list: [],
            selectedPrompt: null,
            editedContent: ''
          } as PromptsSettingsType
        }
        settings.value.prompts.list = response.data
      }
    }
  )

  await getPrompts()
}

const savePrompt = async () => {
  const prompt = settings.value.prompts?.selectedPrompt
  if (!prompt || !settings.value.prompts) {
    return
  }

  const { execute: putPrompt } = useAsyncHandler(
    async () => axios.put(`/api/prompts/${prompt.id}`, {
      content: settings.value.prompts!.editedContent
    }),
    {
      errorMessage: 'Failed to save prompt',
      successMessage: 'Prompt saved successfully',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: async () => {
        clearSelectedPrompt()
        await loadPrompts()
      }
    }
  )

  await putPrompt()
}

const revertPromptToDefault = async (promptId: string) => {
  const { execute: postRevert } = useAsyncHandler(
    async () => axios.post(`/api/prompts/${promptId}/revert`),
    {
      errorMessage: 'Failed to revert prompt to default',
      successMessage: 'Prompt reverted to default',
      notify,
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: async () => {
        clearSelectedPrompt()
        await loadPrompts()
      }
    }
  )

  await postRevert()
}

// Load health status with corrected endpoint
const loadHealthStatus = async () => {
  // Try detailed health endpoint first
  const { execute: getDetailedHealth } = useAsyncHandler(
    async () => axios.get('/api/system/health/detailed'),
    {
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: (response) => {
        healthStatus.value = response.data
      },
      onError: async () => {
        // Fallback to basic health endpoint
        const { execute: getBasicHealth } = useAsyncHandler(
          async () => axios.get('/api/system/health'),
          {
            logErrors: true,
            errorPrefix: '[SettingsPanel]',
            onSuccess: (fallbackResponse) => {
              healthStatus.value = {
                basic_health: fallbackResponse.data,
                detailed_available: false
              } as HealthStatus
            },
            onError: () => {
              healthStatus.value = {
                status: 'unavailable',
                message: 'Health endpoints not available'
              } as HealthStatus
            }
          }
        )

        await getBasicHealth()
      }
    }
  )

  await getDetailedHealth()
}

onMounted(async () => {
  // Load settings first
  loadSettings()

  // Check cache API availability
  await checkCacheApiAvailability()

  // Load health status
  loadHealthStatus()

  // Load cache data only if API is available
  if (cacheApiAvailable.value) {
    refreshCacheStats()
    refreshCacheActivity()
  } else {
  }
})
</script>

<style scoped>
.settings-panel {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
  background: #f8f9fa;
  min-height: calc(100vh - 40px);
}

.settings-content {
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.settings-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #6c757d;
}

.loading-spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid #007acc;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.settings-status {
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 500;
}

.settings-status.offline {
  background: #fff3cd;
  color: #856404;
  border-bottom: 1px solid #ffeaa7;
}

.settings-actions {
  display: flex;
  gap: 16px;
  padding: 24px;
  background: #f8f9fa;
  border-top: 1px solid #dee2e6;
  justify-content: flex-end;
}

.save-settings-btn {
  background: #28a745;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background-color 0.2s ease;
}

.save-settings-btn:hover:not(:disabled) {
  background: #218838;
}

.save-settings-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.discard-btn {
  background: #6c757d;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background-color 0.2s ease;
}

.discard-btn:hover:not(:disabled) {
  background: #5a6268;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-panel {
background: #1a1a1a;
  }


  .settings-content {
background: #2d2d2d;
  }

  .settings-status.offline {
background: #664d03;
color: #ffecb5;
border-bottom-color: #b08800;
  }

  .settings-actions {
background: #383838;
border-top-color: #555;
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-panel {
padding: 12px;
  }

  .settings-actions {
flex-direction: column;
gap: 12px;
  }

  .save-settings-btn,
  .discard-btn {
width: 100%;
justify-content: center;
  }
}
</style>
