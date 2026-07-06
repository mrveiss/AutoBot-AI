<template>
  <ErrorBoundary :fallback="$t('settings.panelLoadFailed')">
<div class="settings-panel-layout">
  <!-- Main Content -->
  <main class="settings-content">
    <!-- Loading indicator -->
    <div v-if="settingsLoadingStatus === 'loading'" class="settings-loading">
      <div class="loading-spinner"></div>
      <p>{{ $t('settings.loadingSettings') }}</p>
    </div>

    <!-- Settings status message -->
    <div v-if="settingsLoadingStatus === 'offline'" class="settings-status offline">
      <Icon name="exclamation-triangle" />
      <span>{{ $t('settings.backendOffline') }}</span>
    </div>

    <!-- Router View for Settings Sub-routes -->
    <div class="settings-content-inner">
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
    </div>

    <!-- Save Settings Button -->
    <div v-if="isSettingsLoaded && hasUnsavedChanges" class="settings-actions">
      <button @click="saveSettings" :disabled="isSaving" class="save-settings-btn">
        <i :class="isSaving ? 'fas fa-spinner fa-spin' : 'save'"></i>
        {{ isSaving ? $t('settings.saving') : $t('settings.save') }}
      </button>
      <button @click="discardChanges" :disabled="isSaving" class="discard-btn">
        <Icon name="undo" />
        {{ $t('settings.discardChanges') }}
      </button>
    </div>
  </main>
</div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, reactive, onMounted, provide } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SettingsPanel')
const { t } = useI18n()

// Import error handling composables
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { useNotificationBus } from '@/composables/useNotificationBus'

// Import sub-components
import ErrorBoundary from '../common/ErrorBoundary.vue'

// Import services and types
import cacheService from '@/services/CacheService'
import {
  createDefaultSettings,
  createDefaultCacheConfig,
  createCacheActivityItem
} from '@/types/settings'
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
} from '@/types/settings'

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
  { id: 'optimization', label: 'LLM Optimization' },
  { id: 'ui', label: 'UI' },
  { id: 'logging', label: 'Logging' },
  { id: 'log-forwarding', label: 'Log Forwarding' },
  { id: 'cache', label: 'Cache' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'infrastructure', label: 'Infrastructure' },
  { id: 'developer', label: 'Developer' },
  { id: 'feature-flags', label: 'Feature Flags' }
])
const activeBackendSubTab = ref('agents')

// Cache state
const cacheConfig = reactive<CacheConfig>(createDefaultCacheConfig())
const cacheActivity = ref<CacheActivityItem[]>([])
const cacheStats = ref<CacheStats | null>(null)

// Toast notifications
const { showToast } = useNotificationBus()

// Notification helper for useAsyncHandler
const notify = (message: string, type: 'success' | 'error' | 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// Helper functions
const markAsChanged = () => {
  hasUnsavedChanges.value = true
}

// Generic setting change handler that routes to appropriate update function
const handleSettingChanged = (key: string, value: unknown) => {
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

const updateChatSetting = (key: string, value: unknown) => {
  if (!settings.value.chat) {
    settings.value.chat = {
      auto_scroll: true,
      max_messages: 100,
      message_retention_days: 30
    } as ChatSettingsType
  }
  // Issue #156 Fix: Use Record<string, unknown> type assertion for dynamic property assignment
  const chatSettings = settings.value.chat as Record<string, unknown>
  chatSettings[key] = value
  markAsChanged()
}

// NOTE (#11024): No-op placeholder. There is no user-settings section in
// SettingsStructure yet and nothing in the app emits a `user.*` setting-changed
// event, so the `case 'user'` branch in handleSettingChanged is currently
// unreachable. Kept (not deleted) as the wire-in point for a future User
// Management settings section — persist into a `settings.value.user` section
// (mirroring updateChatSetting/updateUISetting) once that section is added and
// a child view emits `user.*`.
const updateUserSetting = (_key: string, _value: unknown) => {
  markAsChanged()
}

// #1721: Shared safe nested-set helper to prevent prototype pollution
const _UNSAFE_KEYS = new Set(['__proto__', 'constructor', 'prototype'])
function safeNestedSet(root: Record<string, unknown>, key: string, value: unknown): void {
  const keys = key.split('.')
  if (keys.some(k => _UNSAFE_KEYS.has(k))) return
  let obj: Record<string, unknown> = root
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i]
    if (!Object.prototype.hasOwnProperty.call(obj, k) || typeof obj[k] !== 'object') {
      obj[k] = Object.create(null) as Record<string, unknown> // codeql[js/prototype-pollution-utility]
    }
    obj = obj[k] as Record<string, unknown>
  }
  const finalKey = keys[keys.length - 1]
  if (!_UNSAFE_KEYS.has(finalKey)) {
    obj[finalKey] = value // codeql[js/prototype-pollution-utility]
  }
}

const updateBackendSetting = (key: string, value: unknown) => {
  if (!settings.value.backend) {
    settings.value.backend = {} as BackendSettingsType
  }
  // Handle nested settings for memory and agents
  if (key.includes('.')) {
    safeNestedSet(settings.value.backend as Record<string, unknown>, key, value)
  } else {
    if (!_UNSAFE_KEYS.has(key)) {
      (settings.value.backend as Record<string, unknown>)[key] = value
    }
  }
  markAsChanged()
}

const updateLLMSetting = (key: string, value: unknown) => {
  if (!settings.value.backend) {
    settings.value.backend = {} as BackendSettingsType
  }
  if (!settings.value.backend.llm) {
    settings.value.backend.llm = {}
  }
  safeNestedSet(
    settings.value.backend.llm as Record<string, unknown>, key, value
  )
  markAsChanged()
}

const updateUISetting = (key: string, value: unknown) => {
  if (!settings.value.ui) {
    settings.value.ui = {
      theme: 'auto',
      language: 'en',
      show_timestamps: true,
      show_status_bar: true,
      auto_refresh_interval: 30
    } as UISettingsType
  }
  // Issue #156 Fix: Use Record<string, unknown> type assertion for dynamic property assignment
  const uiSettings = settings.value.ui as Record<string, unknown>
  uiSettings[key] = value
  markAsChanged()
}

const updateLoggingSetting = (key: string, value: unknown) => {
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
  // Issue #156 Fix: Use Record<string, unknown> type assertion for dynamic property assignment
  const loggingSettings = settings.value.logging as Record<string, unknown>
  loggingSettings[key] = value
  markAsChanged()
}

const updateDeveloperSetting = (key: string, value: unknown) => {
  if (!settings.value.developer) {
    settings.value.developer = {
      enabled: false,
      detailed_errors: true,
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
  (settings.value.developer as unknown as Record<string, unknown>)[key] = value
  markAsChanged()
}

const updateRUMSetting = (key: string, value: unknown) => {
  if (!settings.value.developer) {
    settings.value.developer = {
      enabled: false,
      detailed_errors: true,
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
  (settings.value.developer.rum as Record<string, unknown>)[key] = value
  markAsChanged()
}

const updateCacheConfig = (key: string, value: unknown) => {
  (cacheConfig as Record<string, unknown>)[key] = value
  markAsChanged()
}

const getCurrentLLMDisplay = (): string => {
  const llmConfig = settings.value.backend?.llm
  if (!llmConfig) return 'Not configured'

  const providerType = llmConfig.provider_type || 'local'
  if (providerType === 'local') {
    const provider = llmConfig.local?.provider || 'ollama'
    const model = (llmConfig.local?.providers?.[provider] as { selected_model?: string } | undefined)?.selected_model || 'Not selected'
    return `${provider.toUpperCase()}: ${model}`
  } else {
    const provider = llmConfig.cloud?.provider || 'openai'
    const model = (llmConfig.cloud?.providers?.[provider] as { selected_model?: string } | undefined)?.selected_model || 'Not selected'
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
    async () => axios.get(`${getApiBase()}/settings/`),
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
          notify(t('settings.cachedSettings'), 'info')
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
    async () => axios.post(`${getApiBase()}/settings/`, settings.value),
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
    async () => axios.get(`${getApiBase()}/cache/stats`, { timeout: 3000 }),
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
    notify(t('settings.cacheApiUnavailable'), 'error')
    return
  }

  isSaving.value = true

  const { execute: postCacheConfig } = useAsyncHandler(
    async () => axios.post(`${getApiBase()}/cache/config`, cacheConfig),
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
    async () => axios.get(`${getApiBase()}/cache/stats`),
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
    notify(t('settings.cacheApiUnavailable'), 'error')
    return
  }

  isClearing.value = true

  const { execute: postClearCache } = useAsyncHandler(
    async () => axios.post(`${getApiBase()}/cache/clear/${type}`),
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
    notify(t('settings.cacheApiUnavailable'), 'error')
    return
  }

  isClearing.value = true

  const { execute: postClearRedis } = useAsyncHandler(
    async () => axios.post(`${getApiBase()}/cache/redis/clear/${database}`),
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
    notify(t('settings.cacheApiUnavailable'), 'error')
    return
  }

  isClearing.value = true

  const { execute: postClearCacheType } = useAsyncHandler(
    async () => axios.post(`${getApiBase()}/cache/clear/${cacheType}`),
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
    notify(t('settings.cacheApiUnavailable'), 'error')
    return
  }

  isClearing.value = true

  const { execute: postWarmup } = useAsyncHandler(
    async () => axios.post(`${getApiBase()}/cache/warmup`),
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
    async () => axios.get(`${getApiBase()}/prompts`),
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
    async () => axios.put(`${getApiBase()}/prompts/${prompt.id}`, {
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
    async () => axios.post(`${getApiBase()}/prompts/${promptId}/revert`),
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
    async () => axios.get(`${getApiBase()}/system/health/detailed`),
    {
      logErrors: true,
      errorPrefix: '[SettingsPanel]',
      onSuccess: (response) => {
        healthStatus.value = response.data
      },
      onError: async () => {
        // Fallback to basic health endpoint
        const { execute: getBasicHealth } = useAsyncHandler(
          async () => axios.get(`${getApiBase()}/system/health`),
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
/* Issue #704: Sidebar layout matching SecretsManager style */

.settings-panel-layout {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

.settings-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.settings-content-inner {
  flex: 1;
  min-height: 0; /* Required for flex child to shrink and enable overflow */
  overflow-y: auto;
  padding: var(--spacing-6);
}

.settings-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-16) var(--spacing-5);
  color: var(--text-secondary);
}

.loading-spinner {
  border: 3px solid var(--bg-tertiary);
  border-top: 3px solid var(--color-primary);
  border-radius: var(--radius-full);
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin-bottom: var(--spacing-5);
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.settings-status {
  padding: var(--spacing-4) var(--spacing-6);
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  font-weight: var(--font-medium);
}

.settings-status.offline {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
  border-bottom: 1px solid var(--color-warning-border);
}

.settings-actions {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-default);
  justify-content: flex-end;
}

.save-settings-btn {
  background: var(--color-success);
  color: var(--text-on-success);
  border: none;
  padding: var(--spacing-3) var(--spacing-6);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: background-color var(--duration-200) var(--ease-in-out);
}

.save-settings-btn:hover:not(:disabled) {
  background: var(--color-success-hover);
}

.save-settings-btn:disabled {
  background: var(--color-secondary);
  cursor: not-allowed;
}

.discard-btn {
  background: var(--color-secondary);
  color: var(--text-on-primary);
  border: none;
  padding: var(--spacing-3) var(--spacing-6);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: background-color var(--duration-200) var(--ease-in-out);
}

.discard-btn:hover:not(:disabled) {
  background: var(--color-secondary-hover);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-panel-layout {
    flex-direction: column;
  }

  .settings-content-inner {
    padding: var(--spacing-4);
  }

  .settings-actions {
    flex-direction: column;
    gap: var(--spacing-3);
  }

  .save-settings-btn,
  .discard-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
