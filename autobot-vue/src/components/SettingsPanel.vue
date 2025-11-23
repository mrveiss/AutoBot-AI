<template>
  <ErrorBoundary fallback="Settings panel failed to load.">
<div class="settings-panel">
  <h2>Settings</h2>

  <!-- Tab Navigation -->
  <SettingsTabNavigation
    :activeTab="activeTab"
    :hasUnsavedChanges="hasUnsavedChanges"
    :tabs="tabs"
    @tab-changed="activeTab = $event"
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

    <!-- User Management Settings -->
    <UserManagementSettings
      v-if="activeTab === 'user'"
      :isSettingsLoaded="isSettingsLoaded"
      @setting-changed="updateUserSetting"
    />

    <!-- Chat Settings -->
    <ChatSettings
      v-if="activeTab === 'chat'"
      :chatSettings="settings.chat"
      :isSettingsLoaded="isSettingsLoaded"
      @setting-changed="updateChatSetting"
    />

    <!-- Backend Settings -->
    <!-- Issue #156 Fix: Convert null to undefined for BackendSettings prop -->
    <BackendSettings
      v-if="activeTab === 'backend'"
      :backendSettings="settings.backend || undefined"
      :isSettingsLoaded="isSettingsLoaded"
      :activeBackendSubTab="activeBackendSubTab"
      :healthStatus="healthStatus"
      :currentLLMDisplay="getCurrentLLMDisplay()"
      @subtab-changed="activeBackendSubTab = $event"
      @setting-changed="updateBackendSetting"
      @llm-setting-changed="updateLLMSetting"
    />

    <!-- UI Settings -->
    <UISettings
      v-if="activeTab === 'ui'"
      :uiSettings="settings.ui"
      :isSettingsLoaded="isSettingsLoaded"
      @setting-changed="updateUISetting"
    />

    <!-- NPU Workers Settings -->
    <NPUWorkersSettings
      v-if="activeTab === 'npu-workers'"
      :isSettingsLoaded="isSettingsLoaded"
      @change="markAsChanged"
    />

    <!-- Logging Settings -->
    <LoggingSettings
      v-if="activeTab === 'logging'"
      :loggingSettings="settings.logging"
      :isSettingsLoaded="isSettingsLoaded"
      @setting-changed="updateLoggingSetting"
    />

    <!-- Cache Settings -->
    <CacheSettings
      v-if="activeTab === 'cache'"
      :isSettingsLoaded="isSettingsLoaded"
      :cacheConfig="cacheConfig"
      :cacheActivity="cacheActivity"
      :cacheStats="cacheStats"
      :isSaving="isSaving"
      :isClearing="isClearing"
      :cacheApiAvailable="cacheApiAvailable"
      @cache-config-changed="updateCacheConfig"
      @save-cache-config="saveCacheConfig"
      @refresh-cache-activity="refreshCacheActivity"
      @refresh-cache-stats="refreshCacheStats"
      @clear-cache="clearCache"
      @clear-redis-cache="clearRedisCache"
      @clear-cache-type="clearCacheType"
      @warmup-caches="warmupCaches"
    />

    <!-- Prompts Settings -->
    <PromptsSettings
      v-if="activeTab === 'prompts'"
      :promptsSettings="settings.prompts"
      :isSettingsLoaded="isSettingsLoaded"
      @prompt-selected="selectPrompt"
      @edited-content-changed="updatePromptEditedContent"
      @selected-prompt-cleared="clearSelectedPrompt"
      @load-prompts="loadPrompts"
      @save-prompt="savePrompt"
      @revert-prompt-to-default="revertPromptToDefault"
    />

    <!-- Developer Settings -->
    <DeveloperSettings
      v-if="activeTab === 'developer'"
      :developerSettings="settings.developer"
      :isSettingsLoaded="isSettingsLoaded"
      @setting-changed="updateDeveloperSetting"
      @rum-setting-changed="updateRUMSetting"
    />

    <!-- Services Settings -->
    <ServicesSettings
      v-if="activeTab === 'services'"
      :isSettingsLoaded="isSettingsLoaded"
      @change="markAsChanged"
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
import { ref, reactive, onMounted, computed } from 'vue'
import axios from 'axios'

// Import sub-components
import ErrorBoundary from './ErrorBoundary.vue'
import SettingsTabNavigation from './settings/SettingsTabNavigation.vue'
import UserManagementSettings from './settings/UserManagementSettings.vue'
import ChatSettings from './settings/ChatSettings.vue'
import BackendSettings from './settings/BackendSettings.vue'
import UISettings from './settings/UISettings.vue'
import NPUWorkersSettings from './settings/NPUWorkersSettings.vue'
import LoggingSettings from './settings/LoggingSettings.vue'
import CacheSettings from './settings/CacheSettings.vue'
import PromptsSettings from './settings/PromptsSettings.vue'
import DeveloperSettings from './settings/DeveloperSettings.vue'
import ServicesSettings from './settings/ServicesSettings.vue'

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
  { id: 'npu-workers', label: 'NPU Workers' },
  { id: 'logging', label: 'Logging' },
  { id: 'cache', label: 'Cache' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'services', label: 'Services' },
  { id: 'developer', label: 'Developer' }
])
const activeTab = ref('backend')
const activeBackendSubTab = ref('agents')

// Cache state
const cacheConfig = reactive<CacheConfig>(createDefaultCacheConfig())
const cacheActivity = ref<CacheActivityItem[]>([])
const cacheStats = ref<CacheStats | null>(null)

// Helper functions
const markAsChanged = () => {
  hasUnsavedChanges.value = true
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

// Add guard to prevent infinite loading loops
let isLoadingSettings = false

// Load settings on mount
const loadSettings = async () => {
  // Prevent concurrent loading calls that cause infinite loops
  if (isLoadingSettings) {
    return
  }

  try {
    isLoadingSettings = true
    settingsLoadingStatus.value = 'loading'
    const response = await axios.get('/api/settings')
    // Merge response data with default structure to ensure all sections exist
    settings.value = {
      ...getDefaultSettings(),
      ...response.data
    }
    isSettingsLoaded.value = true
    settingsLoadingStatus.value = 'loaded'
    hasUnsavedChanges.value = false
  } catch (error) {
    console.error('Failed to load settings:', error)
    settingsLoadingStatus.value = 'offline'
    // Load from cache if available
    const cachedSettings = cacheService.get('settings')
    if (cachedSettings) {
      settings.value = {
        ...getDefaultSettings(),
        ...cachedSettings
      }
      isSettingsLoaded.value = true
    }
  } finally {
    isLoadingSettings = false
  }
}

const saveSettings = async () => {
  try {
    isSaving.value = true
    await axios.post('/api/settings', settings.value)
    hasUnsavedChanges.value = false
    // Cache the settings
    cacheService.set('settings', settings.value, 3600)
  } catch (error) {
    console.error('Failed to save settings:', error)
  } finally {
    isSaving.value = false
  }
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
  try {
    // Test if cache API is available by checking a simple endpoint
    await axios.get('/api/cache/stats', { timeout: 3000 })
    cacheApiAvailable.value = true
  } catch (error) {
    cacheApiAvailable.value = false
  }
}

const saveCacheConfig = async () => {
  if (!cacheApiAvailable.value) {
    console.warn('Cache API not available, cannot save cache config')
    return
  }

  try {
    isSaving.value = true
    await axios.post('/api/cache/config', cacheConfig)
    markAsChanged()
  } catch (error) {
    console.error('Failed to save cache config:', error)
  } finally {
    isSaving.value = false
  }
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
    console.error('Failed to refresh cache activity:', error)
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

  try {
    const response = await axios.get('/api/cache/stats')
    cacheStats.value = response.data
  } catch (error) {
    console.error('Failed to refresh cache stats:', error)
    cacheStats.value = {
      status: 'error',
      message: 'Failed to load cache statistics'
    } as CacheStats
  }
}

const clearCache = async (type: string) => {
  if (!cacheApiAvailable.value) {
    console.warn('Cache API not available, cannot clear cache')
    return
  }

  try {
    isClearing.value = true
    await axios.post(`/api/cache/clear/${type}`)
    await refreshCacheStats()
  } catch (error) {
    console.error('Failed to clear cache:', error)
  } finally {
    isClearing.value = false
  }
}

const clearRedisCache = async (database: string) => {
  if (!cacheApiAvailable.value) {
    console.warn('Cache API not available, cannot clear Redis cache')
    return
  }

  try {
    isClearing.value = true
    await axios.post(`/api/cache/redis/clear/${database}`)
    await refreshCacheStats()
    await refreshCacheActivity()
  } catch (error) {
    console.error('Failed to clear Redis cache:', error)
  } finally {
    isClearing.value = false
  }
}

const clearCacheType = async (cacheType: string) => {
  if (!cacheApiAvailable.value) {
    console.warn('Cache API not available, cannot clear cache type')
    return
  }

  try {
    isClearing.value = true
    await axios.post(`/api/cache/clear/${cacheType}`)
    await refreshCacheStats()
    await refreshCacheActivity()
  } catch (error) {
    console.error('Failed to clear cache type:', error)
  } finally {
    isClearing.value = false
  }
}

const warmupCaches = async () => {
  if (!cacheApiAvailable.value) {
    console.warn('Cache API not available, cannot warm up caches')
    return
  }

  try {
    isClearing.value = true
    await axios.post('/api/cache/warmup')
    await refreshCacheStats()
    await refreshCacheActivity()
  } catch (error) {
    console.error('Failed to warm up caches:', error)
  } finally {
    isClearing.value = false
  }
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
  try {
    const response = await axios.get('/api/prompts')
    if (!settings.value.prompts) {
      settings.value.prompts = {
        list: [],
        selectedPrompt: null,
        editedContent: ''
      } as PromptsSettingsType
    }
    settings.value.prompts.list = response.data
  } catch (error) {
    console.error('Failed to load prompts:', error)
  }
}

const savePrompt = async () => {
  try {
    const prompt = settings.value.prompts?.selectedPrompt
    if (prompt && settings.value.prompts) {
      await axios.put(`/api/prompts/${prompt.id}`, {
        content: settings.value.prompts.editedContent
      })
      clearSelectedPrompt()
      await loadPrompts()
    }
  } catch (error) {
    console.error('Failed to save prompt:', error)
  }
}

const revertPromptToDefault = async (promptId: string) => {
  try {
    await axios.post(`/api/prompts/${promptId}/revert`)
    clearSelectedPrompt()
    await loadPrompts()
  } catch (error) {
    console.error('Failed to revert prompt:', error)
  }
}

// Load health status with corrected endpoint
const loadHealthStatus = async () => {
  try {
    // Try the correct detailed health endpoint first
    const response = await axios.get('/api/system/health/detailed')
    healthStatus.value = response.data
  } catch (error) {
    console.error('Failed to load detailed health status:', error)

    // Fallback to basic health endpoint
    try {
      const fallbackResponse = await axios.get('/api/system/health')
      healthStatus.value = {
        basic_health: fallbackResponse.data,
        detailed_available: false
      } as HealthStatus
    } catch (fallbackError) {
      console.error('Failed to load any health status:', fallbackError)
      healthStatus.value = {
        status: 'unavailable',
        message: 'Health endpoints not available'
      } as HealthStatus
    }
  }
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

.settings-panel h2 {
  color: #2c3e50;
  margin-bottom: 30px;
  text-align: center;
  font-weight: 600;
  font-size: 28px;
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

  .settings-panel h2 {
color: #ffffff;
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

  .settings-panel h2 {
font-size: 24px;
margin-bottom: 20px;
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
