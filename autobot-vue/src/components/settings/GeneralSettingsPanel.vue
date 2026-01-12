<template>
  <div class="sub-tab-content">
    <h3>Backend General Settings</h3>

    <!-- Connection Status Banner -->
    <div class="connection-status-banner" :class="connectionStatus.status">
      <div class="status-info">
        <i :class="getConnectionIcon(connectionStatus.status)"></i>
        <span class="status-text">{{ connectionStatus.message }}</span>
        <span v-if="connectionStatus.responseTime" class="response-time">
          ({{ connectionStatus.responseTime }}ms)
        </span>
      </div>
      <div class="status-actions">
        <button
          @click="handleTestConnection"
          :disabled="isTestingConnection"
          class="test-connection-btn"
        >
          <i :class="isTestingConnection ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
          {{ isTestingConnection ? 'Testing...' : 'Test Connection' }}
        </button>
        <button @click="handleRefreshStatus" class="refresh-status-btn">
          <i class="fas fa-sync"></i>
        </button>
      </div>
    </div>

    <div class="setting-item">
      <label for="api-endpoint">API Endpoint</label>
      <div class="input-group">
        <input
          id="api-endpoint"
          type="text"
          :value="backendSettings?.api_endpoint || ''"
          @input="handleInputChange('api_endpoint')"
          :class="{ 'validation-error': validationErrors.api_endpoint }"
        />
        <div v-if="validationErrors.api_endpoint" class="validation-message error">
          {{ validationErrors.api_endpoint }}
        </div>
        <div v-else-if="validationSuccess.api_endpoint" class="validation-message success">
          Valid endpoint format
        </div>
      </div>
    </div>

    <div class="setting-item">
      <label for="server-host">Server Host</label>
      <div class="input-group">
        <input
          id="server-host"
          type="text"
          :value="backendSettings?.server_host || ''"
          @input="handleInputChange('server_host')"
          :class="{ 'validation-error': validationErrors.server_host }"
        />
        <div v-if="validationErrors.server_host" class="validation-message error">
          {{ validationErrors.server_host }}
        </div>
        <div v-else-if="validationSuccess.server_host" class="validation-message success">
          Valid host format
        </div>
      </div>
    </div>

    <div class="setting-item">
      <label for="server-port">Server Port</label>
      <div class="input-group">
        <input
          id="server-port"
          type="number"
          :value="backendSettings?.server_port || 8001"
          min="1"
          max="65535"
          @input="handleNumberInputChange('server_port')"
          :class="{ 'validation-error': validationErrors.server_port }"
        />
        <div v-if="validationErrors.server_port" class="validation-message error">
          {{ validationErrors.server_port }}
        </div>
        <div v-else-if="validationSuccess.server_port" class="validation-message success">
          Valid port range (1-65535)
        </div>
      </div>
    </div>

    <div class="setting-item">
      <label for="chat-data-dir">Chat Data Directory</label>
      <div class="input-group">
        <input
          id="chat-data-dir"
          type="text"
          :value="backendSettings?.chat_data_dir || ''"
          @input="handleInputChange('chat_data_dir')"
        />
        <button @click="handleValidatePath('chat_data_dir')" class="validate-path-btn">
          <i class="fas fa-folder-open"></i> Check Path
        </button>
      </div>
    </div>

    <div class="setting-item">
      <label for="chat-history-file">Chat History File</label>
      <input
        id="chat-history-file"
        type="text"
        :value="backendSettings?.chat_history_file || ''"
        placeholder="data/chat_history.json"
        @input="handleInputChange('chat_history_file')"
      />
    </div>

    <div class="setting-item">
      <label for="knowledge-base-db">Knowledge Base DB</label>
      <input
        id="knowledge-base-db"
        type="text"
        :value="backendSettings?.knowledge_base_db || ''"
        placeholder="data/knowledge_base.db"
        @input="handleInputChange('knowledge_base_db')"
      />
    </div>

    <div class="setting-item">
      <label for="reliability-stats-file">Reliability Stats File</label>
      <input
        id="reliability-stats-file"
        type="text"
        :value="backendSettings?.reliability_stats_file || ''"
        placeholder="data/reliability_stats.json"
        @input="handleInputChange('reliability_stats_file')"
      />
    </div>

    <div class="setting-item">
      <label for="logs-directory">Logs Directory</label>
      <input
        id="logs-directory"
        type="text"
        :value="backendSettings?.logs_directory || ''"
        placeholder="logs/"
        @input="handleInputChange('logs_directory')"
      />
    </div>

    <div class="setting-item">
      <label for="chat-enabled">Chat Enabled</label>
      <input
        id="chat-enabled"
        type="checkbox"
        :checked="backendSettings?.chat_enabled || false"
        @change="handleCheckboxChange('chat_enabled')"
      />
    </div>

    <div class="setting-item">
      <label for="knowledge-base-enabled">Knowledge Base Enabled</label>
      <input
        id="knowledge-base-enabled"
        type="checkbox"
        :checked="backendSettings?.knowledge_base_enabled || false"
        @change="handleCheckboxChange('knowledge_base_enabled')"
      />
    </div>

    <div class="setting-item">
      <label for="auto-backup-chat">Auto Backup Chat</label>
      <input
        id="auto-backup-chat"
        type="checkbox"
        :checked="backendSettings?.auto_backup_chat || false"
        @change="handleCheckboxChange('auto_backup_chat')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * General Settings Panel Component
 *
 * Manages backend general configuration settings.
 * Extracted from BackendSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, reactive, onMounted } from 'vue'
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('GeneralSettingsPanel')

// Type definitions
interface BackendSettings {
  api_endpoint?: string
  server_host?: string
  server_port?: number
  chat_data_dir?: string
  chat_history_file?: string
  knowledge_base_db?: string
  reliability_stats_file?: string
  logs_directory?: string
  chat_enabled?: boolean
  knowledge_base_enabled?: boolean
  auto_backup_chat?: boolean
}

interface ConnectionStatus {
  status: string
  message: string
  responseTime: number | null
}

interface Props {
  backendSettings?: BackendSettings | null
}

interface Emits {
  (e: 'setting-changed', key: string, value: unknown): void
  (e: 'test-connection'): void
  (e: 'validate-path', pathKey: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// State
const isTestingConnection = ref(false)
const validationErrors = reactive<Record<string, string>>({})
const validationSuccess = reactive<Record<string, boolean>>({})

const connectionStatus = reactive<ConnectionStatus>({
  status: 'unknown',
  message: 'Connection status unknown',
  responseTime: null
})

// Connection icon helper
const getConnectionIcon = (status: string): string => {
  const iconMap: Record<string, string> = {
    connected: 'fas fa-check-circle',
    disconnected: 'fas fa-times-circle',
    testing: 'fas fa-spinner fa-spin',
    unknown: 'fas fa-question-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}

// Validation helper
const validateSetting = (key: string, value: unknown): { isValid: boolean; error?: string } => {
  switch (key) {
    case 'api_endpoint':
      if (!value || typeof value !== 'string') {
        return { isValid: false, error: 'API endpoint is required' }
      }
      if (!value.startsWith('http://') && !value.startsWith('https://')) {
        return { isValid: false, error: 'Must start with http:// or https://' }
      }
      return { isValid: true }

    case 'server_host':
      if (!value || typeof value !== 'string') {
        return { isValid: false, error: 'Server host is required' }
      }
      const hostRegex = /^[a-zA-Z0-9.-]+$/
      if (!hostRegex.test(value)) {
        return { isValid: false, error: 'Invalid host format' }
      }
      return { isValid: true }

    case 'server_port':
      const port = value as number
      if (!port || isNaN(port) || port < 1 || port > 65535) {
        return { isValid: false, error: 'Port must be between 1 and 65535' }
      }
      return { isValid: true }

    default:
      return { isValid: true }
  }
}

// Event handlers
const handleInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  const value = target.value

  // Clear previous validation
  delete validationErrors[key]
  delete validationSuccess[key]

  // Validate
  const validation = validateSetting(key, value)
  if (validation.isValid) {
    validationSuccess[key] = true
    emit('setting-changed', key, value)
  } else {
    validationErrors[key] = validation.error || 'Validation failed'
  }
}

const handleNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  const value = parseInt(target.value, 10)

  // Clear previous validation
  delete validationErrors[key]
  delete validationSuccess[key]

  // Validate
  const validation = validateSetting(key, value)
  if (validation.isValid) {
    validationSuccess[key] = true
    emit('setting-changed', key, value)
  } else {
    validationErrors[key] = validation.error || 'Validation failed'
  }
}

const handleCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, target.checked)
}

const handleTestConnection = async () => {
  if (isTestingConnection.value) return

  isTestingConnection.value = true
  connectionStatus.status = 'testing'
  connectionStatus.message = 'Testing connection...'

  try {
    const endpoint =
      props.backendSettings?.api_endpoint ||
      `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`
    const startTime = Date.now()

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)

    const response = await fetch(`${endpoint}/health`, {
      method: 'GET',
      signal: controller.signal
    })

    clearTimeout(timeoutId)
    const responseTime = Date.now() - startTime
    connectionStatus.responseTime = responseTime

    if (response.ok) {
      connectionStatus.status = 'connected'
      connectionStatus.message = 'Backend connection successful'
    } else {
      connectionStatus.status = 'disconnected'
      connectionStatus.message = `Connection failed (${response.status})`
    }
  } catch (error) {
    const err = error as Error
    logger.error('Connection test failed:', err)
    connectionStatus.status = 'disconnected'
    connectionStatus.message = `Connection error: ${err.message}`
    connectionStatus.responseTime = null
  } finally {
    isTestingConnection.value = false
  }
}

const handleRefreshStatus = async () => {
  await handleTestConnection()
}

const handleValidatePath = (pathKey: string) => {
  emit('validate-path', pathKey)
}

// Initialize on mount
onMounted(() => {
  handleTestConnection()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.sub-tab-content {
  padding: var(--spacing-4) 0;
}

.sub-tab-content h3 {
  margin: 0 0 var(--spacing-5) 0;
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: 1.125rem;
  border-bottom: 2px solid var(--color-primary);
  padding-bottom: var(--spacing-2);
}

.connection-status-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-5);
  border: 1px solid;
}

.connection-status-banner.connected {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success);
}

.connection-status-banner.disconnected {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error);
}

.connection-status-banner.testing {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
  color: var(--color-warning);
}

.connection-status-banner.unknown {
  background: var(--bg-tertiary);
  border-color: var(--border-default);
  color: var(--text-secondary);
}

.status-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.status-actions {
  display: flex;
  gap: var(--spacing-2);
}

.test-connection-btn,
.refresh-status-btn {
  padding: var(--spacing-1-5) var(--spacing-3);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--duration-200) var(--ease-in-out);
}

.test-connection-btn {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.test-connection-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.test-connection-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-status-btn {
  background: var(--text-tertiary);
  color: var(--text-on-primary);
}

.refresh-status-btn:hover {
  background: var(--text-secondary);
}

.response-time {
  font-size: var(--text-xs);
  opacity: 0.8;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  padding: var(--spacing-3) 0;
  border-bottom: 1px solid var(--border-light);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  flex: 1;
  margin-right: var(--spacing-4);
  cursor: pointer;
}

.setting-item input,
.setting-item select {
  min-width: 200px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: border-color var(--duration-200) var(--ease-in-out);
}

.setting-item input[type='checkbox'] {
  min-width: auto;
  width: 1.25rem;
  height: 1.25rem;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-bg-transparent);
}

.input-group {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--spacing-2);
}

.input-group input {
  flex: 1;
}

.validate-path-btn {
  padding: var(--spacing-2) var(--spacing-3);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: var(--color-info);
  color: var(--text-on-primary);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.validate-path-btn:hover {
  background: var(--color-info-hover);
}

.validation-message {
  font-size: var(--text-xs);
  margin-top: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
}

.validation-message.error {
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error-border);
}

.validation-message.success {
  background: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--color-success-border);
}

.validation-error {
  border-color: var(--color-error) !important;
  box-shadow: 0 0 0 2px var(--color-error-bg-transparent) !important;
}

@media (max-width: 768px) {
  .connection-status-banner {
    flex-direction: column;
    gap: var(--spacing-3);
    align-items: stretch;
  }

  .status-actions {
    justify-content: center;
  }

  .setting-item {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-2);
  }

  .setting-item label {
    margin-right: 0;
  }

  .setting-item input,
  .setting-item select {
    min-width: unset;
    width: 100%;
  }

  .input-group {
    flex-direction: column;
  }
}
</style>
